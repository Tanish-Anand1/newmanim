import base64
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

DEFAULT_ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5")
DEFAULT_OPENAI_CODE_MODEL = os.getenv("OPENAI_CODE_MODEL", "gpt-5.5")
DEFAULT_GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
DEFAULT_ANTHROPIC_FAST_MODEL = os.getenv("ANTHROPIC_MODEL_FAST", DEFAULT_ANTHROPIC_MODEL)
DEFAULT_OPENAI_FAST_MODEL = os.getenv("OPENAI_CODE_MODEL_FAST", "gpt-5.4-mini")
DEFAULT_GEMINI_FAST_MODEL = os.getenv("GEMINI_MODEL_FAST", "gemini-2.5-flash-lite")
OPENAI_REASONING_EFFORT = os.getenv("OPENAI_REASONING_EFFORT", "low").strip().lower()
LOGGER = logging.getLogger(__name__)
PROVIDER_API_KEY_ENV = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "gemini": "GOOGLE_API_KEY",
    "nvidia_nim": "NVIDIA_NIM_API_KEY",
}
PROVIDER_FAILOVER_COOLDOWN_SECONDS = 0
_FAILOVER_MAX_RETRIES = int(os.getenv("FAILOVER_MAX_RETRIES", "5"))
_FAILOVER_BASE_DELAY = float(os.getenv("FAILOVER_BASE_DELAY", "2.0"))
_PROVIDER_COOLDOWN_UNTIL: dict[str, float] = {}


@dataclass(frozen=True)
class LLMResponse:
    text: str
    truncated: bool
    input_tokens: int
    output_tokens: int
    provider_name: str | None = None
    model: str | None = None


class LLMProvider:
    name: str
    model: str
    fast_model: str

    def generate(self, system: str, user_message: str, max_tokens: int, model: str | None = None) -> LLMResponse:
        raise NotImplementedError

    def inspect_image(self, frame_path: Path, prompt: str, max_tokens: int) -> LLMResponse:
        raise NotImplementedError(f"{self.name} provider does not support image inspection.")


class ProviderUnavailableError(RuntimeError):
    pass


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(self, api_key: str | None = None, model: str | None = None):
        try:
            import anthropic
        except ImportError as exc:
            raise RuntimeError("Anthropic SDK is not installed. Run: pip install anthropic") from exc

        api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is not configured.")
        self.model = model or DEFAULT_ANTHROPIC_MODEL
        self.fast_model = DEFAULT_ANTHROPIC_FAST_MODEL
        self.client = anthropic.Anthropic(api_key=api_key)

    def generate(self, system: str, user_message: str, max_tokens: int, model: str | None = None) -> LLMResponse:
        active_model = model or self.model
        response = self.client.messages.create(
            model=active_model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user_message}],
        )
        usage = getattr(response, "usage", None)
        return LLMResponse(
            text=response.content[0].text,
            truncated=getattr(response, "stop_reason", None) == "max_tokens",
            input_tokens=int(getattr(usage, "input_tokens", 0) or 0),
            output_tokens=int(getattr(usage, "output_tokens", 0) or 0),
            provider_name=self.name,
            model=active_model,
        )

    def inspect_image(self, frame_path: Path, prompt: str, max_tokens: int) -> LLMResponse:
        image_b64 = base64.b64encode(frame_path.read_bytes()).decode("ascii")
        response = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": image_b64,
                            },
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
        )
        usage = getattr(response, "usage", None)
        return LLMResponse(
            text=response.content[0].text,
            truncated=getattr(response, "stop_reason", None) == "max_tokens",
            input_tokens=int(getattr(usage, "input_tokens", 0) or 0),
            output_tokens=int(getattr(usage, "output_tokens", 0) or 0),
            provider_name=self.name,
            model=self.model,
        )


class OpenAIProvider(LLMProvider):
    name = "openai"

    def __init__(self, api_key: str | None = None, model: str | None = None):
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("OpenAI SDK is not installed. Run: pip install openai") from exc

        api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not configured.")
        self.model = model or DEFAULT_OPENAI_CODE_MODEL
        self.fast_model = DEFAULT_OPENAI_FAST_MODEL
        base_url = os.getenv("OPENAI_BASE_URL")
        if base_url:
            self.client = OpenAI(api_key=api_key, base_url=base_url)
        else:
            self.client = OpenAI(api_key=api_key)

    def _chat_completion_options(self, max_tokens: int, model: str | None = None) -> dict:
        options = {"max_completion_tokens": max_tokens}
        if model_supports_reasoning_effort(model or self.model) and OPENAI_REASONING_EFFORT:
            options["reasoning_effort"] = OPENAI_REASONING_EFFORT
        return options

    def generate(self, system: str, user_message: str, max_tokens: int, model: str | None = None) -> LLMResponse:
        active_model = model or self.model
        response = self.client.chat.completions.create(
            **self._chat_completion_options(max_tokens, active_model),
            model=active_model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_message},
            ],
        )
        choice = response.choices[0]
        usage = getattr(response, "usage", None)
        return LLMResponse(
            text=choice.message.content or "",
            truncated=getattr(choice, "finish_reason", None) == "length",
            input_tokens=int(getattr(usage, "prompt_tokens", 0) or 0),
            output_tokens=int(getattr(usage, "completion_tokens", 0) or 0),
            provider_name=self.name,
            model=active_model,
        )

    def inspect_image(self, frame_path: Path, prompt: str, max_tokens: int) -> LLMResponse:
        image_b64 = base64.b64encode(frame_path.read_bytes()).decode("ascii")
        response = self.client.chat.completions.create(
            **self._chat_completion_options(max_tokens, self.model),
            model=self.model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_b64}"}},
                    ],
                }
            ],
        )
        choice = response.choices[0]
        usage = getattr(response, "usage", None)
        return LLMResponse(
            text=choice.message.content or "",
            truncated=getattr(choice, "finish_reason", None) == "length",
            input_tokens=int(getattr(usage, "prompt_tokens", 0) or 0),
            output_tokens=int(getattr(usage, "completion_tokens", 0) or 0),
            provider_name=self.name,
            model=self.model,
        )


class GeminiProvider(LLMProvider):
    name = "gemini"

    def __init__(self, api_key: str | None = None, model: str | None = None):
        api_key = api_key or os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise RuntimeError("GOOGLE_API_KEY is not configured.")
        self.model_name = model or os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        self.model = self.model_name
        self.fast_model = os.getenv("GEMINI_MODEL_FAST", "gemini-2.5-flash-lite")

        # Prefer the current google-genai client. Keep the legacy SDK as a
        # fallback for environments that have not migrated yet.
        try:
            from google import genai
            from google.genai import types

            self.client = genai.Client(api_key=api_key)
            self.types = types
            self._legacy = False
        except ImportError:
            try:
                import google.generativeai as genai
            except ImportError as exc:
                raise RuntimeError(
                    "Google Generative AI SDK is not installed. Run: pip install google-genai"
                ) from exc
            genai.configure(api_key=api_key)
            self._model = genai.GenerativeModel(self.model_name)
            self._legacy = True

    @staticmethod
    def _usage(response) -> dict[str, int]:
        metadata = getattr(response, "usage_metadata", None)
        return {
            "prompt_token_count": int(getattr(metadata, "prompt_token_count", 0) or 0),
            "candidates_token_count": int(getattr(metadata, "candidates_token_count", 0) or 0),
        }

    @staticmethod
    def _finish_reason(response) -> str:
        candidates = getattr(response, "candidates", None) or []
        if not candidates:
            return ""
        value = getattr(candidates[0], "finish_reason", "")
        return getattr(value, "name", str(value)).upper()

    def _generate_content(self, prompt: str, max_tokens: int, image=None, system: str | None = None, model: str | None = None):
        if not getattr(self, "_legacy", False) and hasattr(self, "client"):
            contents = prompt if image is None else [prompt, self.types.Part.from_bytes(data=image, mime_type="image/png")]
            config_kwargs = {"temperature": 0.2, "top_p": 0.7, "max_output_tokens": max_tokens}
            if system:
                config_kwargs["system_instruction"] = system
            config = self.types.GenerateContentConfig(**config_kwargs)
            response = self.client.models.generate_content(
                model=model or getattr(self, "model_name", self.model),
                contents=contents,
                config=config,
            )
            return getattr(response, "text", "") or "", self._usage(response), self._finish_reason(response)

        import google.generativeai as genai

        generation_config = {"temperature": 0.2, "top_p": 0.7, "max_output_tokens": max_tokens}
        active_model = self._model if model in (None, getattr(self, "model_name", self.model)) else genai.GenerativeModel(model)
        payload = prompt if image is None else [prompt, image]
        response = active_model.generate_content(payload, generation_config=generation_config)
        if getattr(response, "text", None):
            text = response.text
        else:
            text = ""
            for part in getattr(getattr(response, "candidates", [None])[0], "content", None).parts:
                if hasattr(part, "text"):
                    text += part.text
        return text, self._usage(response), self._finish_reason(response)

    def generate(self, system: str, user_message: str, max_tokens: int, model: str | None = None) -> LLMResponse:
        text, usage_info, finish_reason = self._generate_content(
            user_message, max_tokens, system=system, model=model
        )
        truncated = finish_reason in {"MAX_TOKENS", "LENGTH"}

        return LLMResponse(
            text=text,
            truncated=truncated,
            input_tokens=usage_info.get("prompt_token_count", 0),
            output_tokens=usage_info.get("candidates_token_count", 0),
            provider_name=self.name,
            model=model if model is not None else getattr(self, "model_name", self.model),
        )

    def inspect_image(self, frame_path: Path, prompt: str, max_tokens: int) -> LLMResponse:
        image = frame_path.read_bytes()
        text, usage_info, finish_reason = self._generate_content(prompt, max_tokens, image=image)
        truncated = finish_reason in {"MAX_TOKENS", "LENGTH"}

        return LLMResponse(
            text=text,
            truncated=truncated,
            input_tokens=usage_info.get("prompt_token_count", 0),
            output_tokens=usage_info.get("candidates_token_count", 0),
            provider_name=self.name,
            model=getattr(self, "model_name", self.model),
        )


class NvidiaNimProvider(LLMProvider):
    """NVIDIA NIM — its own provider identity, never 'openai' in logs or errors.

    NIM exposes an OpenAI-compatible API, so we reuse the openai SDK internally,
    but every log line, error message, and response identifies as ``nvidia_nim``
    so failures are never ambiguous about which service caused them.
    """

    name = "nvidia_nim"

    def __init__(self, api_key: str | None = None, model: str | None = None):
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("OpenAI SDK is not installed. Run: pip install openai") from exc

        api_key = api_key or os.getenv("NVIDIA_NIM_API_KEY")
        if not api_key:
            raise RuntimeError("NVIDIA_NIM_API_KEY is not configured.")
        base_url = os.getenv("NVIDIA_NIM_BASE_URL", "https://integrate.api.nvidia.com/v1")
        self.model = model or os.getenv("NVIDIA_NIM_MODEL", "nvidia/llama-3.1-nemotron-nano-8b-v1")
        self.fast_model = self.model
        self._client = OpenAI(api_key=api_key, base_url=base_url)

    def generate(self, system: str, user_message: str, max_tokens: int, model: str | None = None) -> LLMResponse:
        active_model = model or self.model
        response = self._client.chat.completions.create(
            model=active_model,
            max_tokens=max_tokens,
            temperature=0.2,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_message},
            ],
        )
        choice = response.choices[0]
        usage = getattr(response, "usage", None)
        return LLMResponse(
            text=choice.message.content or "",
            truncated=getattr(choice, "finish_reason", None) == "length",
            input_tokens=int(getattr(usage, "prompt_tokens", 0) or 0),
            output_tokens=int(getattr(usage, "completion_tokens", 0) or 0),
            provider_name=self.name,
            model=active_model,
        )

    def inspect_image(self, frame_path: Path, prompt: str, max_tokens: int) -> LLMResponse:
        """NIM vision models accept base64-embedded image URLs."""
        import base64
        image_b64 = base64.b64encode(frame_path.read_bytes()).decode("ascii")
        response = self._client.chat.completions.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=0.2,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_b64}"}},
                    ],
                }
            ],
        )
        choice = response.choices[0]
        usage = getattr(response, "usage", None)
        return LLMResponse(
            text=choice.message.content or "",
            truncated=getattr(choice, "finish_reason", None) == "length",
            input_tokens=int(getattr(usage, "prompt_tokens", 0) or 0),
            output_tokens=int(getattr(usage, "completion_tokens", 0) or 0),
            provider_name=self.name,
            model=self.model,
        )


class FailoverProvider(LLMProvider):
    """Try configured providers in order when one is temporarily unavailable."""

    def __init__(self, providers: list[LLMProvider]):
        if not providers:
            raise ValueError("At least one LLM provider is required.")
        self.providers = providers
        self.primary = providers[0]
        self.name = self.primary.name
        self.model = self.primary.model
        self.fast_model = self.primary.fast_model

    def _model_for(self, provider: LLMProvider, requested_model: str | None) -> str:
        use_fast_model = requested_model is not None and requested_model == self.fast_model
        if provider is self.primary:
            return requested_model or self.model
        return provider.fast_model if use_fast_model else provider.model

    def _call_with_failover(
        self,
        call_fn,
        model: str | None,
        log_label: str,
    ) -> LLMResponse:
        """Try all providers with exponential backoff up to _FAILOVER_MAX_RETRIES.

        *call_fn(provider, active_model)* is invoked for each provider.  Non-capacity
        exceptions propagate immediately.  If every provider returns a capacity error
        (or is in cooldown) the entire cycle is retried after an exponential sleep.
        """
        last_error: Exception | None = None
        for attempt in range(1, _FAILOVER_MAX_RETRIES + 1):
            attempted = False
            for provider in self.providers:
                if _PROVIDER_COOLDOWN_UNTIL.get(provider.name, 0.0) > time.monotonic():
                    continue
                attempted = True
                active_model = self._model_for(provider, model)
                try:
                    return call_fn(provider, active_model)
                except Exception as exc:
                    last_error = exc
                    if not is_provider_capacity_exception(exc):
                        raise
                    _PROVIDER_COOLDOWN_UNTIL[provider.name] = (
                        time.monotonic() + PROVIDER_FAILOVER_COOLDOWN_SECONDS
                    )
                    remaining = [candidate for candidate in self.providers if candidate is not provider]
                    next_provider = next(
                        (
                            candidate
                            for candidate in remaining
                            if _PROVIDER_COOLDOWN_UNTIL.get(candidate.name, 0.0) <= time.monotonic()
                        ),
                        None,
                    )
                    if next_provider is not None:
                        LOGGER.warning(
                            "%s %s is capacity-limited; retrying with %s.",
                            log_label,
                            provider.name,
                            next_provider.name,
                        )

            sleep_seconds = _FAILOVER_BASE_DELAY * (2 ** (attempt - 1))
            reason = "all providers in cooldown" if not attempted else "all providers returned capacity errors"
            LOGGER.warning(
                "%s: %s; sleeping %.1fs and retrying (attempt %d/%d).",
                log_label,
                reason,
                sleep_seconds,
                attempt,
                _FAILOVER_MAX_RETRIES,
            )
            time.sleep(sleep_seconds)

        message = (
            f"All configured {log_label.lower()} providers are temporarily unavailable "
            f"after {_FAILOVER_MAX_RETRIES} retries."
        )
        raise ProviderUnavailableError(message) from last_error

    def generate(self, system: str, user_message: str, max_tokens: int, model: str | None = None) -> LLMResponse:
        def _call(provider: LLMProvider, active_model: str) -> LLMResponse:
            return provider.generate(system, user_message, max_tokens, model=active_model)
        return self._call_with_failover(_call, model, "LLM provider")

    def inspect_image(self, frame_path: Path, prompt: str, max_tokens: int) -> LLMResponse:
        def _call(provider: LLMProvider, _model: str | None = None) -> LLMResponse:
            return provider.inspect_image(frame_path=frame_path, prompt=prompt, max_tokens=max_tokens)
        return self._call_with_failover(_call, None, "Vision provider")


def is_provider_capacity_exception(exc: Exception) -> bool:
    status_code = getattr(exc, "status_code", None)
    response = getattr(exc, "response", None)
    response_status = getattr(response, "status_code", None)
    code = getattr(exc, "code", None)
    if status_code in {429, 502, 503, 504} or response_status in {429, 502, 503, 504}:
        return True
    if code in {429, 502, 503, 504}:
        return True
    message = str(exc).lower()
    return any(
        marker in message
        for marker in (
            "429",
            "rate limit",
            "too many requests",
            "resource_exhausted",
            "resource exhausted",
            "quota exceeded",
            "exceeded your current quota",
            "insufficient_quota",
            "service unavailable",
        )
    )


def model_supports_reasoning_effort(model: str) -> bool:
    normalized = model.lower()
    return normalized.startswith("gpt-5") or normalized.startswith("o")


def _build_provider(provider: str) -> LLMProvider:
    if provider == "anthropic":
        return AnthropicProvider()
    if provider == "openai":
        return OpenAIProvider()
    if provider == "gemini":
        return GeminiProvider()
    if provider == "nvidia_nim":
        return NvidiaNimProvider()
    raise RuntimeError("LLM_PROVIDER must be 'anthropic', 'openai', 'gemini', or 'nvidia_nim'.")


def get_llm_provider(provider_name: str | None = None) -> LLMProvider:
    primary_name = (provider_name or os.getenv("LLM_PROVIDER", "anthropic")).strip().lower()
    failover_enabled = os.getenv("LLM_PROVIDER_FAILOVER", "1").strip().lower() not in {"0", "false", "no"}
    fallback_names = [
        item.strip().lower()
        for item in os.getenv("LLM_PROVIDER_FALLBACKS", "anthropic,gemini,nvidia_nim").split(",")
        if item.strip()
    ]
    ordered_names = list(dict.fromkeys([primary_name, *fallback_names])) if failover_enabled else [primary_name]

    providers: list[LLMProvider] = []
    errors: list[str] = []
    for name in ordered_names:
        key_env = PROVIDER_API_KEY_ENV.get(name)
        if name != primary_name and key_env and not os.getenv(key_env):
            continue
        try:
            providers.append(_build_provider(name))
        except RuntimeError as exc:
            errors.append(f"{name}: {exc}")
            if name == primary_name and not failover_enabled:
                raise

    if not providers:
        details = "; ".join(errors) or "no provider API keys are configured"
        raise RuntimeError(f"No usable LLM provider is configured: {details}")
    if len(providers) == 1:
        return providers[0]
    return FailoverProvider(providers)

