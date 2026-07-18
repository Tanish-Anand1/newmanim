from pathlib import Path
from types import SimpleNamespace

from app.llm_provider import AnthropicProvider, FailoverProvider, GeminiProvider, LLMResponse, OpenAIProvider


class FakeAnthropicMessages:
    def __init__(self):
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(
            content=[SimpleNamespace(text='{"collision": false, "summary": "clear"}')],
            stop_reason="end_turn",
            usage=SimpleNamespace(input_tokens=12, output_tokens=4),
        )


class FakeOpenAICompletions:
    def __init__(self):
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content='{"collision": false, "summary": "clear"}'),
                    finish_reason="stop",
                )
            ],
            usage=SimpleNamespace(prompt_tokens=15, completion_tokens=5),
        )


class FakeGeminiModels:
    last_kwargs = None
    last_contents = None
    last_system_instruction = None

    def generate_content(self, *, model, contents, config):
        FakeGeminiModels.last_contents = contents
        FakeGeminiModels.last_kwargs = {"config": config, "model_name": model}
        FakeGeminiModels.last_system_instruction = config.get("system_instruction")
        return SimpleNamespace(
            text='{"collision": false, "summary": "clear"}',
            candidates=[SimpleNamespace(finish_reason="STOP")],
            usage_metadata=SimpleNamespace(prompt_token_count=21, candidates_token_count=7),
        )


class FakeGeminiTypes:
    @staticmethod
    def GenerateContentConfig(**kwargs):
        return kwargs

    class Part:
        @staticmethod
        def from_bytes(*, data: bytes, mime_type: str):
            return {"data": data, "mime_type": mime_type}


class FakeCapacityProvider:
    def __init__(self, name: str, model: str, fast_model: str, error: Exception | None = None):
        self.name = name
        self.model = model
        self.fast_model = fast_model
        self.error = error
        self.models_requested: list[str | None] = []

    def generate(self, system: str, user_message: str, max_tokens: int, model: str | None = None) -> LLMResponse:
        self.models_requested.append(model)
        if self.error is not None:
            raise self.error
        return LLMResponse(
            text="ok",
            truncated=False,
            input_tokens=8,
            output_tokens=3,
            provider_name=self.name,
            model=model or self.model,
        )


class QuotaError(Exception):
    status_code = 429


def test_anthropic_inspect_image_accepts_pipeline_keyword_arguments(tmp_path: Path):
    frame_path = tmp_path / "frame.png"
    frame_path.write_bytes(b"fake png")
    messages = FakeAnthropicMessages()
    provider = AnthropicProvider.__new__(AnthropicProvider)
    provider.model = "claude-sonnet-4-6"
    provider.client = SimpleNamespace(messages=messages)

    response = provider.inspect_image(frame_path=frame_path, prompt="Inspect frame.", max_tokens=200)

    assert response.text.startswith("{")
    assert response.input_tokens == 12
    assert messages.kwargs["max_tokens"] == 200
    assert messages.kwargs["messages"][0]["content"][0]["type"] == "image"


def test_openai_inspect_image_accepts_pipeline_keyword_arguments(tmp_path: Path):
    frame_path = tmp_path / "frame.png"
    frame_path.write_bytes(b"fake png")
    completions = FakeOpenAICompletions()
    provider = OpenAIProvider.__new__(OpenAIProvider)
    provider.model = "gpt-5.5"
    provider.client = SimpleNamespace(chat=SimpleNamespace(completions=completions))

    response = provider.inspect_image(frame_path=frame_path, prompt="Inspect frame.", max_tokens=200)

    assert response.text.startswith("{")
    assert response.input_tokens == 15
    assert completions.kwargs["max_completion_tokens"] == 200
    assert "max_tokens" not in completions.kwargs
    content = completions.kwargs["messages"][0]["content"]
    assert content[0]["type"] == "text"
    assert content[1]["type"] == "image_url"


def test_openai_generate_uses_completion_token_parameter_for_configured_model():
    completions = FakeOpenAICompletions()
    provider = OpenAIProvider.__new__(OpenAIProvider)
    provider.model = "gpt-5.5"
    provider.client = SimpleNamespace(chat=SimpleNamespace(completions=completions))

    response = provider.generate(system="System prompt.", user_message="User prompt.", max_tokens=123)

    assert response.text.startswith("{")
    assert response.input_tokens == 15
    assert completions.kwargs["model"] == "gpt-5.5"
    assert completions.kwargs["max_completion_tokens"] == 123
    assert completions.kwargs["reasoning_effort"] == "low"
    assert "max_tokens" not in completions.kwargs
    assert completions.kwargs["messages"][0]["role"] == "system"
    assert completions.kwargs["messages"][1]["role"] == "user"


def test_openai_generate_does_not_send_reasoning_effort_to_non_reasoning_model():
    completions = FakeOpenAICompletions()
    provider = OpenAIProvider.__new__(OpenAIProvider)
    provider.model = "gpt-4.1"
    provider.client = SimpleNamespace(chat=SimpleNamespace(completions=completions))

    provider.generate(system="System prompt.", user_message="User prompt.", max_tokens=123)

    assert completions.kwargs["model"] == "gpt-4.1"
    assert "reasoning_effort" not in completions.kwargs


def test_gemini_generate_maps_response_shape():
    provider = GeminiProvider.__new__(GeminiProvider)
    provider.model = "gemini-2.5-flash-lite"
    provider.client = SimpleNamespace(models=FakeGeminiModels())
    provider.types = FakeGeminiTypes

    response = provider.generate(system="System prompt.", user_message="User prompt.", max_tokens=321)

    assert response.text.startswith("{")
    assert response.input_tokens == 21
    assert response.output_tokens == 7
    assert response.truncated is False
    assert FakeGeminiModels.last_system_instruction == "System prompt."
    assert FakeGeminiModels.last_contents == "User prompt."
    assert FakeGeminiModels.last_kwargs["model_name"] == "gemini-2.5-flash-lite"
    assert FakeGeminiModels.last_kwargs["config"]["max_output_tokens"] == 321


def test_gemini_inspect_image_accepts_pipeline_keyword_arguments(tmp_path: Path):
    from PIL import Image

    frame_path = tmp_path / "frame.png"
    Image.new("RGB", (1, 1), color="black").save(frame_path)
    provider = GeminiProvider.__new__(GeminiProvider)
    provider.model = "gemini-2.5-flash-lite"
    provider.client = SimpleNamespace(models=FakeGeminiModels())
    provider.types = FakeGeminiTypes

    response = provider.inspect_image(frame_path=frame_path, prompt="Inspect frame.", max_tokens=200)

    assert response.text.startswith("{")
    assert response.input_tokens == 21
    assert FakeGeminiModels.last_contents[0] == "Inspect frame."
    assert FakeGeminiModels.last_contents[1]["mime_type"] == "image/png"
    assert FakeGeminiModels.last_kwargs["config"]["max_output_tokens"] == 200


def test_failover_provider_switches_on_quota_without_reusing_primary_model_name():
    primary = FakeCapacityProvider("gemini", "gemini-pro", "gemini-fast", QuotaError("quota exceeded"))
    fallback = FakeCapacityProvider("anthropic", "claude-pro", "claude-fast")
    provider = FailoverProvider([primary, fallback])

    response = provider.generate("system", "user", 200, model="gemini-fast")

    assert primary.models_requested == ["gemini-fast"]
    assert fallback.models_requested == ["claude-fast"]
    assert response.provider_name == "anthropic"
    assert response.model == "claude-fast"


def test_failover_provider_does_not_mask_non_capacity_errors():
    primary = FakeCapacityProvider("test-primary", "primary-pro", "primary-fast", ValueError("invalid request"))
    fallback = FakeCapacityProvider("test-fallback", "fallback-pro", "fallback-fast")
    provider = FailoverProvider([primary, fallback])

    try:
        provider.generate("system", "user", 200)
    except ValueError as exc:
        assert str(exc) == "invalid request"
    else:
        raise AssertionError("A non-capacity provider error must be raised.")
    assert fallback.models_requested == []

