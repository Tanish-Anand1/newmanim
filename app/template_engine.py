from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Literal, Mapping, Sequence

from pydantic import BaseModel, Field, ValidationError


TemplateLayout = Literal["title", "concept", "equation", "derivation", "comparison", "process"]
VisualKind = Literal[
    "none",
    "axes",
    "vector",
    "dot_product_vectors",
    "geometry",
    "molecule",
    "vsepr_ch4",
    "vsepr_compare",
    "vsepr_nh3",
    "process",
    "atwood",
    "taylor_coefficient_filter",
    "taylor_derivative_cycle",
    "taylor_axes",
    "taylor_error",
    "integration_by_parts",
]
LATEX_SYNTAX_PATTERN = re.compile(r"[$\\]|(?:\^|_)\s*[\{\(]")
IMPERATIVE_STAGE_PATTERN = re.compile(
    r"^\s*(?:draw|label|show|illustrate|add|highlight|display|construct|place|mark|write)\b",
    re.IGNORECASE,
)
DUPLICATE_CONSECUTIVE_WORD_PATTERN = re.compile(
    r"\b([A-Za-z]{2,})\b(?:\s|[,;:.!-])+\1\b",
    re.IGNORECASE,
)
# Some providers strip backslashes while producing a plan, turning a LaTeX
# expression into a caption such as "Displaystyle I Big x cos x".  Such text
# is never a legitimate heading or line; the actual expression belongs in
# the equations field and is rendered by MathTex.
LEAKED_MATH_CAPTION_PATTERN = re.compile(
    r"\b(?:displaystyle|textstyle|scriptstyle|scriptscriptstyle)\b"
    r"|\b(?:big|bigg|Big|Bigg)\b.*\b(?:int|sum|frac|sin|cos|tan|pi)\b",
    re.IGNORECASE,
)
BARE_LATEX_COMMAND_PATTERN = re.compile(
    r"(?<!\\)\b(?:displaystyle|textstyle|scriptstyle|scriptscriptstyle|"
    r"big|bigg|int|sum|frac|sqrt|sin|cos|tan|pi|theta|cdot)\b",
    re.IGNORECASE,
)
INTEGRAL_BOUND_LETTER_O_PATTERN = re.compile(
    r"(\\int\s*(?:_\s*\{\s*|_\s*|\{\s*)?)o(?=\s*(?:\}|\^|\\pi\b|pi\b))",
    re.IGNORECASE,
)
MACLAURIN_ZERO_TYPO_PATTERN = re.compile(
    r"\bf\s*\^\s*(?:\{\s*)?\(?\s*n\s*\)?(?:\s*\})?\s*\(\s*o\s*\)|\b(?:x|a)\s*=\s*o\b",
    re.IGNORECASE,
)
PLAIN_EQUATION_PREFIX = re.compile(
    r"^\s*(?:equation(?:s)?|write|show|display|compute|calculate|find|derive|use|apply|evaluate|substitute(?:\s+into)?|simplify(?:\s+to)?|"
    r"therefore|hence|thus|conclude(?:\s+with)?|"
    r"then\s+show\s+them\s+being\s+added)\s*:?\s*",
    re.IGNORECASE,
)
VSEPR_TOPIC_MARKERS = (
    "vsepr",
    "molecular geometry",
    "tetrahedral",
    "tetrahedron",
    "tetrahedra",
    "trigonal pyramidal",
    "methane",
    "ammonia",
    "ch4",
    "ch₄",
    "nh3",
)
VECTOR_DOT_PRODUCT_MARKERS = (
    "dot product",
    "spatial coordinate",
    "spatial coordinates",
    "coordinate system",
    r"\cdot",
    "cos(",
    "arccos",
)
TAYLOR_TOPIC_MARKERS = ("taylor", "maclaurin")
ATWOOD_TOPIC_MARKERS = ("atwood", "pulley", "m_1", "m_2", "m1", "m2")
STOICHIOMETRY_TOPIC_MARKERS = ("stoichiometry", "limiting reagent", "balanced reaction")
INTEGRATION_BY_PARTS_MARKERS = ("integration by parts", "integrate by parts", "integrationbyparts")
MAX_SUPPORTING_ITEMS_PER_BEAT = 3
CONTINUOUS_VISUAL_KINDS = {
    "atwood",
    "axes",
    "dot_product_vectors",
    "integration_by_parts",
    "taylor_axes",
    "vector",
    "vsepr_ch4",
    "vsepr_nh3",
}
MIN_POST_REVEAL_HOLD_SECONDS = 0.65


class TemplateBeatPlan(BaseModel):
    beat_number: int = Field(ge=1)
    layout: TemplateLayout = "concept"
    heading: str = Field(min_length=1, max_length=100)
    lines: list[str] = Field(default_factory=list, max_length=2)
    equations: list[str] = Field(default_factory=list, max_length=2)
    visual_kind: VisualKind = "none"
    visual_labels: list[str] = Field(default_factory=list, max_length=4)


class TemplateVideoPlan(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    beats: list[TemplateBeatPlan] = Field(min_length=1, max_length=80)


@dataclass(frozen=True)
class TemplateBeatInput:
    beat_number: int
    target_duration: float
    gap_before: float
    on_screen: str
    vo_text: str | None


def _json_object_from_response(raw_text: str) -> str:
    text = raw_text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.IGNORECASE | re.DOTALL)
    if fenced:
        return fenced.group(1)
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("Template plan response did not contain a JSON object.")
    return text[start : end + 1]


def _word_tokens(value: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9]+", value.lower())


def _word_overlap(value: str, source: str) -> float:
    value_words = set(_word_tokens(value))
    if not value_words:
        return 0.0
    return len(value_words & set(_word_tokens(source))) / len(value_words)


def _contains_chemical_formula(value: str, formula: str) -> bool:
    """Match plain or LaTeX-formatted molecular formulas such as CH_4."""
    compact_value = re.sub(r"[^a-z0-9]+", "", value.casefold())
    compact_formula = re.sub(r"[^a-z0-9]+", "", formula.casefold())
    return bool(compact_formula and compact_formula in compact_value)


GENERIC_PROCESS_LABELS = {"start", "change", "result"}


def _visual_kind_has_topic_support(visual_kind: str, context: str) -> bool:
    """Keep an LLM plan from adding an unrelated stock diagram to a beat."""
    markers_by_kind = {
        "axes": ("graph", "curve", "plot", "axis", "axes"),
        "taylor_axes": ("taylor", "maclaurin", "graph", "curve", "plot"),
        "taylor_error": ("taylor", "maclaurin", "error", "remainder", "gap"),
        "taylor_coefficient_filter": ("taylor", "maclaurin", "coefficient", "odd", "even", "substitute"),
        "taylor_derivative_cycle": ("taylor", "maclaurin", "derivative", "sin", "cos"),
        "integration_by_parts": ("integration by parts", "integrate by parts", "integral"),
        "vector": ("vector", "coordinate", "dot product", "magnitude", "force", "arrow", r"\vec", r"\cdot", "cdot"),
        "dot_product_vectors": ("vector", "coordinate", "dot product", "magnitude", r"\vec", r"\cdot", "cdot", "cos"),
        "geometry": ("geometry", "circle", "triangle", "angle", "polygon", "radius"),
        "molecule": ("molecule", "atom", "bond", "orbital", "vsepr", "methane", "ammonia"),
        "vsepr_ch4": ("vsepr", "methane", "ch4", "tetrahedral"),
        "vsepr_nh3": ("vsepr", "ammonia", "nh3", "pyramidal"),
        "vsepr_compare": ("vsepr", "ch4", "nh3", "methane", "ammonia"),
        "atwood": ("atwood", "pulley", "m_1", "m_2", "m1", "m2"),
        "process": ("process", "sequence", "reaction", "step", "derivative cycle", "compare"),
    }
    markers = markers_by_kind.get(visual_kind)
    if markers is None:
        return True
    return any(
        _contains_chemical_formula(context, marker)
        if marker in {"ch4", "nh3"}
        else re.search(rf"(?<!\w){re.escape(marker)}(?!\w)", context)
        for marker in markers
    )


def parse_template_plan(
    raw_text: str,
    expected_beat_numbers: Sequence[int],
    on_screen_by_beat: Mapping[int, str] | None = None,
) -> TemplateVideoPlan:
    try:
        payload = json.loads(_json_object_from_response(raw_text))
        plan = TemplateVideoPlan.model_validate(payload)
    except (json.JSONDecodeError, ValidationError, ValueError) as exc:
        raise ValueError(f"Template plan was not valid JSON: {exc}") from exc

    actual = [beat.beat_number for beat in plan.beats]
    expected = list(expected_beat_numbers)
    if actual != expected:
        raise ValueError(f"Template plan beat numbers must be exactly {expected}; received {actual}.")
    # Repair a provider response that has lost LaTeX backslashes in a
    # rendered caption.  Do this before validation so one malformed heading
    # cannot reach the generated scene or consume a render retry.
    sanitized_beats = []
    for beat in plan.beats:
        heading = "Key equation" if LEAKED_MATH_CAPTION_PATTERN.search(beat.heading) else beat.heading
        lines = [line for line in beat.lines if not LEAKED_MATH_CAPTION_PATTERN.search(line)]
        beat_context = " ".join(
            [
                plan.title,
                (on_screen_by_beat or {}).get(beat.beat_number, ""),
                *lines,
                *beat.equations,
            ]
        ).lower()
        visual_kind = beat.visual_kind
        if visual_kind != "none" and not _visual_kind_has_topic_support(visual_kind, beat_context):
            visual_kind = "none"
        normalized_equations = [_normalize_math_expression(equation) for equation in beat.equations]
        visual_labels = [label for label in beat.visual_labels if label.casefold() not in GENERIC_PROCESS_LABELS]
        if visual_kind == "process" and not visual_labels:
            visual_kind = "none"
        if (
            heading != beat.heading
            or lines != beat.lines
            or visual_kind != beat.visual_kind
            or visual_labels != beat.visual_labels
        ):
            beat = beat.model_copy(
                update={
                    "heading": heading,
                    "lines": lines,
                    "equations": normalized_equations,
                    "visual_kind": visual_kind,
                    "visual_labels": visual_labels,
                }
            )
        elif normalized_equations != beat.equations:
            beat = beat.model_copy(update={"equations": normalized_equations})
        sanitized_beats.append(beat)
    if sanitized_beats != plan.beats:
        plan = plan.model_copy(update={"beats": sanitized_beats})

    for beat in plan.beats:
        for field_name, value in [("heading", beat.heading), *( ("line", line) for line in beat.lines )]:
            if IMPERATIVE_STAGE_PATTERN.match(value):
                raise ValueError(
                    f"Template plan Beat {beat.beat_number} uses an imperative stage direction as rendered {field_name}: "
                    f"{value!r}. Put the actual visual in visual_kind and use a concise descriptive heading instead."
                )
            duplicate = DUPLICATE_CONSECUTIVE_WORD_PATTERN.search(value)
            if duplicate:
                raise ValueError(
                    f"Template plan Beat {beat.beat_number} contains duplicate connector text "
                    f"{duplicate.group(0)!r} in rendered {field_name}."
                )
            math_marker = LATEX_SYNTAX_PATTERN.search(value)
            if math_marker:
                raise ValueError(
                    f"Template plan Beat {beat.beat_number} places math syntax {math_marker.group(0)!r} in rendered "
                    f"{field_name}; move the complete expression to equations."
                )
            on_screen = (on_screen_by_beat or {}).get(beat.beat_number, "")
            word_count = len(_word_tokens(value))
            overlap = _word_overlap(value, on_screen) if on_screen else 0.0
            if on_screen and _word_tokens(value) == _word_tokens(on_screen):
                raise ValueError(
                    f"Template plan Beat {beat.beat_number} copies its operational ON SCREEN spec verbatim "
                    f"into rendered {field_name}. Construct the requested visual and use a separate short label."
                )
            if word_count > 8 and overlap > 0.60:
                raise ValueError(
                    f"Template plan Beat {beat.beat_number} copies its operational ON SCREEN spec into rendered "
                    f"{field_name} ({word_count} words, {overlap:.0%} overlap). Construct the requested visual and "
                    "use a separately authored short label."
                )
        if len(beat.lines) + len(beat.equations) > MAX_SUPPORTING_ITEMS_PER_BEAT:
            raise ValueError(
                f"Template plan Beat {beat.beat_number} has too many supporting items. Split the explanation across beats."
            )
        for equation in beat.equations:
            if MACLAURIN_ZERO_TYPO_PATTERN.search(equation):
                raise ValueError(
                    f"Template plan Beat {beat.beat_number} uses the letter o where the Maclaurin center requires numeral 0."
                )
    return plan


def validate_template_plan_topic_isolation(topic_context: str, plan: TemplateVideoPlan) -> None:
    normalized = f"{topic_context} {plan.title}".lower()
    if any(marker in normalized for marker in ("cross-domain", "cross domain", "multidisciplinary")):
        return
    family: str | None = None
    allowed: set[str] = set()
    is_vsepr_topic = any(marker in normalized for marker in VSEPR_TOPIC_MARKERS) or any(
        _contains_chemical_formula(normalized, formula) for formula in ("ch4", "nh3")
    )
    is_vector_dot_product_topic = any(marker in normalized for marker in VECTOR_DOT_PRODUCT_MARKERS)
    if is_vsepr_topic and is_vector_dot_product_topic:
        family = "tetrahedral vector-dot-product geometry"
        allowed = {"none", "process", "vsepr_ch4", "vsepr_nh3", "vector", "dot_product_vectors", "geometry", "vsepr_compare"}
    elif is_vsepr_topic:
        family = "VSEPR/molecular geometry"
        allowed = {"none", "process", "geometry", "molecule", "vsepr_ch4", "vsepr_compare", "vsepr_nh3"}
    elif any(marker in normalized for marker in TAYLOR_TOPIC_MARKERS):
        family = "Taylor/Maclaurin"
        allowed = {"none", "process", "axes", "taylor_coefficient_filter", "taylor_derivative_cycle", "taylor_axes", "taylor_error"}
    elif any(marker in normalized for marker in ATWOOD_TOPIC_MARKERS):
        family = "Atwood machine"
        allowed = {"none", "process", "vector", "atwood"}
    elif any(marker in normalized for marker in STOICHIOMETRY_TOPIC_MARKERS):
        family = "stoichiometry/reaction"
        allowed = {"none", "process"}

    if family is None:
        return
    incompatible = [
        (beat.beat_number, beat.visual_kind)
        for beat in plan.beats
        if beat.visual_kind not in allowed
    ]
    if incompatible:
        details = ", ".join(f"Beat {number}: {kind}" for number, kind in incompatible)
        raise ValueError(
            f"Template plan for {family} contains topic-incompatible visual kinds ({details}). "
            "Use only visuals that construct this job's requested subject matter."
        )


def enrich_template_plan_visuals(
    topic_context: str,
    plan: TemplateVideoPlan,
    on_screen_by_beat: Mapping[int, str] | None = None,
) -> TemplateVideoPlan:
    """Apply deterministic method visuals when a valid plan omits a required concept.

    A layout model can identify the method but still attach its visual to the
    setup equation instead of the beat that actually chooses ``u`` and ``dv``.
    That leaves generic empty cards on screen and reduces a derivation to
    animated text.  Normalize this family from the equations themselves so
    the explanatory visual always appears with the substitutions it depicts.
    """
    context_parts = [topic_context, plan.title]
    context_parts.extend(
        " ".join(
            [
                (on_screen_by_beat or {}).get(beat.beat_number, ""),
                beat.heading,
                *beat.lines,
                *beat.equations,
            ]
        )
        for beat in plan.beats
    )
    normalized_topic = " ".join(context_parts).casefold()
    has_parts_formula = bool(re.search(r"\\int\s*u(?:\\,|\s)*d\s*v", normalized_topic))
    has_integration_by_parts = any(marker in normalized_topic for marker in INTEGRATION_BY_PARTS_MARKERS) or has_parts_formula
    has_atwood_sequence = any(marker in normalized_topic for marker in ("atwood", "pulley"))
    has_taylor_sequence = any(marker in normalized_topic for marker in TAYLOR_TOPIC_MARKERS)
    if not has_integration_by_parts and not has_atwood_sequence and not has_taylor_sequence:
        return plan

    if has_taylor_sequence and not has_integration_by_parts and not has_atwood_sequence:
        normalized_beats: list[TemplateBeatPlan] = []
        for beat in plan.beats:
            source = (on_screen_by_beat or {}).get(beat.beat_number, "")
            normalized_source = source.casefold()
            derivative_cycle = (
                "derivative cycle" in normalized_source
                or ("derivative" in normalized_source and r"\sin" in source and r"\cos" in source)
            )
            coefficient_filter = any(
                marker in normalized_source
                for marker in ("coefficient", "odd-power", "odd power", "even-power", "even power")
            ) and any(marker in source for marker in (r"\dfrac", r"\frac", r"\cdot"))
            extracted_equations = _math_delimited_equations_from_source(source)
            equations = beat.equations or extracted_equations
            visual_kind = beat.visual_kind
            visual_labels = beat.visual_labels
            layout = beat.layout
            heading = beat.heading

            if derivative_cycle:
                visual_kind = "taylor_derivative_cycle"
                visual_labels = _taylor_derivative_cycle_terms(source)
                equations = []
                layout = "concept"
                heading = "Sine derivative cycle"
            elif coefficient_filter:
                visual_kind = "taylor_coefficient_filter"
                visual_labels = []
                equations = extracted_equations or equations
                layout = "equation"
                heading = "Filter the coefficients"
            elif extracted_equations:
                # A Taylor formula or a partially built series is already a
                # concrete substitution visual. A generic process card would
                # erase the stated mathematics and introduce empty UI-like
                # boxes instead.
                equations = extracted_equations
                if visual_kind == "process" and not any(
                    marker in normalized_source for marker in ("recap", "summary")
                ):
                    visual_kind = "none"
                    visual_labels = []
                layout = "derivation" if len(equations) >= 2 else "equation"
                heading = _short_heuristic_caption(plan.title, source, visual_kind, equations)

            normalized_beats.append(
                beat.model_copy(
                    update={
                        "heading": heading,
                        "layout": layout,
                        "equations": equations[:2],
                        "visual_kind": visual_kind,
                        "visual_labels": visual_labels[:4],
                    }
                )
            )
        return plan.model_copy(update={"beats": normalized_beats})

    if has_atwood_sequence and not has_integration_by_parts:
        normalized_beats: list[TemplateBeatPlan] = []
        for beat in plan.beats:
            source = " ".join(
                [
                    (on_screen_by_beat or {}).get(beat.beat_number, ""),
                    beat.heading,
                    *beat.lines,
                    *beat.equations,
                ]
            ).casefold()
            if re.search(r"^\s*t\s*=|\\frac\{2m_1m_2g\}|(?:conclude|final|result).*tension", source):
                heading = "Solve for tension"
            elif re.search(r"(?:^|[^a-z])a\s*=|acceleration|combine", source):
                heading = "Solve for acceleration"
            elif any(marker in source for marker in ("t-m_1g", "m_2g-t", "force equation", "newton")):
                heading = "Force equations"
            else:
                heading = "Atwood machine forces"
            # Every force-law step refers to the same pulley, rope, and two
            # masses. Keeping one concrete visual throughout makes the
            # algebra causal instead of alternating between a diagram and
            # detached equations.
            normalized_beats.append(
                beat.model_copy(update={"heading": heading, "visual_kind": "atwood", "visual_labels": []})
            )
        return plan.model_copy(update={"beats": normalized_beats})

    if not has_integration_by_parts:
        return plan

    storyboard_equations_by_beat = {
        beat.beat_number: _all_normalized_equations_from_source(
            (on_screen_by_beat or {}).get(beat.beat_number, "")
        )
        for beat in plan.beats
    }
    storyboard_assignments_by_beat = {
        beat_number: _integration_part_assignments(equations)
        for beat_number, equations in storyboard_equations_by_beat.items()
    }
    all_method_assignments = _integration_part_assignments(
        [
            equation
            for beat in plan.beats
            for equation in [*beat.equations, *storyboard_equations_by_beat[beat.beat_number]]
        ]
    )

    def assignments_for_beat(beat: TemplateBeatPlan) -> list[str]:
        """Use both planner and storyboard equations when locating u/dv."""
        return _integration_part_assignments(
            [*beat.equations, *storyboard_equations_by_beat[beat.beat_number]]
        )

    assignment_target = next(
        (beat for beat in plan.beats if len(assignments_for_beat(beat)) >= 2),
        None,
    )

    def relevance(beat: TemplateBeatPlan) -> tuple[int, int]:
        text = " ".join(
            [
                (on_screen_by_beat or {}).get(beat.beat_number, ""),
                beat.heading,
                *beat.lines,
                *beat.equations,
            ]
        ).casefold()
        direct_match = int(any(marker in text for marker in INTEGRATION_BY_PARTS_MARKERS))
        has_equation = int(bool(beat.equations))
        return direct_match, has_equation

    target = assignment_target or max(plan.beats, key=relevance)
    normalized_beats: list[TemplateBeatPlan] = []
    for beat in plan.beats:
        source_equations = storyboard_equations_by_beat[beat.beat_number]
        assignment_values = assignments_for_beat(beat)
        method_equations = [
            equation
            for equation in source_equations
            if re.search(r"\\int\s*u(?:\\,|\s)*d\s*v", equation)
        ]
        visual_kind = beat.visual_kind
        visual_labels = beat.visual_labels
        display_equations = list(beat.equations)
        storyboard_source = (on_screen_by_beat or {}).get(beat.beat_number, "")
        if beat.beat_number == target.beat_number:
            visual_kind = "integration_by_parts"
            if all_method_assignments:
                visual_labels = all_method_assignments[:4]
        elif visual_kind == "integration_by_parts":
            # The setup beat owns the connected u/dv/du/v method visual.
            # Later beats must advance the derivation instead of recreating
            # a second, detached copy of the same cards.
            visual_kind = "none"
            visual_labels = []

        if visual_kind == "integration_by_parts":
            # The assignment cards are the actual visual for u, dv, du, and
            # v. Rendering those same assignments as detached equations
            # duplicates content and makes the opening beat visually crowded.
            display_equations = [
                equation
                for equation in display_equations
                if _integration_part_assignment_key(equation) not in {"u", "dv", "du", "v"}
            ]
        elif method_equations:
            # Once the linked u/dv/du/v diagram has established the choices,
            # the next beat should show the parts identity itself. Do not
            # morph unrelated derivative and antiderivative assignments into
            # each other or recreate a stale value as a transition source.
            display_equations = method_equations[:1]

        source = " ".join(
            [
                (on_screen_by_beat or {}).get(beat.beat_number, ""),
                *display_equations,
            ]
        ).casefold()
        recap_source = (on_screen_by_beat or {}).get(beat.beat_number, "")
        is_recap = any(word in recap_source.casefold() for word in ("recap", "summary"))
        if is_recap:
            # Do not let operation-specific heading inference turn a recap
            # into a duplicate "evaluate" step. Keep the recap as a compact
            # process map with the authored actions as its cards.
            visual_kind = "process"
            visual_labels = [
                re.sub(r"^then\s+", "", value.strip(" ."), flags=re.IGNORECASE)
                for value in recap_source.rsplit(":", 1)[-1].split(",")
                if 1 <= len(value.strip(" .")) <= 40 and len(_word_tokens(value)) <= 6
            ][:4]
            heading = "Integration by parts recap"
        # These headings identify a derivation operation, so they are derived
        # from the actual equation rather than trusted from a generic planner
        # label. This prevents a valid-looking but misplaced title from
        # teaching the wrong operation.
        elif visual_kind == "integration_by_parts":
            heading = "Choose u and dv"
        elif method_equations or re.search(r"\\int\s*u(?:\\,|\s)*d\s*v", source):
            heading = "Apply parts formula"
        elif any(marker in source for marker in ("evaluate", "=0", "=\\pi", "hence")):
            heading = "Evaluate the bounds"
        elif any(marker in source for marker in ("[-x", "\\cos", "substitute")):
            heading = "Substitute the parts"
        elif "\\int" in source:
            heading = "Set up the integral"
        else:
            heading = beat.heading
        normalized_beats.append(
            beat.model_copy(
                update={
                    "heading": heading,
                    "equations": display_equations,
                    "visual_kind": visual_kind,
                    "visual_labels": visual_labels,
                }
            )
        )

    return plan.model_copy(
        update={"beats": normalized_beats}
    )


def template_plan_schema_prompt() -> str:
    return (
        "Return one JSON object only, with no Markdown or commentary. The exact shape is: "
        '{"title":"short title","beats":[{"beat_number":1,"layout":"concept",'
        '"heading":"short heading","lines":["line"],"equations":["valid LaTeX without $ delimiters"],'
        '"visual_kind":"none","visual_labels":[]}]}.'
        " Allowed layout values: title, concept, equation, derivation, comparison, process. "
        "Allowed visual_kind values: none, axes, vector, dot_product_vectors, geometry, molecule, vsepr_ch4, vsepr_compare, vsepr_nh3, process, "
        "atwood, taylor_coefficient_filter, taylor_derivative_cycle, taylor_axes, "
        "taylor_error, integration_by_parts. Use taylor_axes when comparing a function with Taylor polynomials and taylor_error when "
        "showing the region between a function and a truncated Taylor polynomial. "
        "For taylor_axes, the plotted curve labels already identify P_1 and P_3; do not repeat those same formulas "
        "in equations unless the beat performs a different algebraic derivation. "
        "For VSEPR or molecular-geometry beats, use vsepr_ch4 for methane/tetrahedral CH4, vsepr_nh3 for "
        "ammonia/trigonal-pyramidal NH3, and vsepr_compare when both molecules appear in one comparison. These "
        "visuals construct labeled atoms, an in-plane bond, a filled wedge "
        "bond, a dashed bond, a numeric bond-angle arc, and the NH3 lone pair; never substitute flat circles in a row. "
        "For a hybrid lesson that combines tetrahedral methane with spatial coordinates or vector dot product, treat it "
        "as a vector-dot-product geometry lesson: use vsepr_ch4 for the CH4 structure and dot_product_vectors for "
        "selected C-H bond vectors, coordinate, magnitude, dot-product, and angle steps. Do NOT use the generic "
        "molecule or axes visual kinds for this hybrid topic; those do not show the requested four C-H bonds or vector "
        "calculation. Keep the dot-product equations in equations and preserve the exact result cos(theta)=-1/3 and "
        "theta=arccos(-1/3) when stated by the storyboard. "
        "Preserve the storyboard's mathematical and scientific claims; do not add a new equation or result. "
        "Use at most three supporting items total across lines and equations in a beat, and at most four visual labels. "
        "Use one idea per beat and introduce no more than three new semantic objects at once. If more are needed, split "
        "the lesson across beats with a pause. Prioritize a simple, longer-held static diagram over decorative motion. "
        "Text appearing with FadeIn or Write is not itself a visualization: choose a visual_kind only when it constructs "
        "the requested relationship, such as a graph, a diagram, or a stepwise substitution. Do not use cosmetic scaling, "
        "bouncing, pulses, or color changes merely to make text move. "
        "Put every equation or LaTeX expression in equations, never in heading or lines. "
        "For a multi-step algebraic derivation, use layout derivation and put the before-and-after forms of one "
        "algebraic step in the two equations entries for that beat. They are animated as a single equation morph, "
        "not displayed as two static lines. Keep each morph to one meaningful substitution, rearrangement, or "
        "simplification. "
        "The storyboard ON SCREEN field is an operational specification, never a caption. Do not copy that field, "
        "paraphrase its full sentence, or pass it through as heading or line text. Construct the visual or mathematical "
        "objects it requests. If a visible caption is useful, author a separate label of no more than six words. Never "
        "put imperative instructions beginning with Draw, Label, Show, Illustrate, Add, Highlight, Display, Construct, "
        "Place, Mark, or Write in heading or lines. "
        "For an Atwood machine, use visual_kind atwood and a short label such as 'Atwood machine forces'. "
        "For integration by parts, use visual_kind integration_by_parts when the beat introduces the method; it "
        "constructs the u, dv, and transformed-integral relationship. Use labels only for actual substitutions stated "
        "by the storyboard, such as u=x and dv=\\sin x\\,dx. "
        "Use valid Manim MathTex LaTeX without dollar signs. For a Maclaurin center or evaluation point, use numeral "
        "0, never letter o. Never emit duplicate connector text such as 'then then'. Keep every heading and line "
        "to six words or fewer. Use full standard scientific terminology in headings and labels; never shorten a "
        "recognized geometry or process name into an informal form. Use 'trigonal pyramidal', not merely 'pyramidal', "
        "for NH3, and 'tetrahedral', never an invented shorthand. "
        "Choose none when a generic diagram would not accurately represent the stated content."
    )


def template_plan_user_message(storyboard: str, orientation: str) -> str:
    layout_note = (
        "Portrait output: prefer stacked content and very short lines."
        if orientation == "portrait"
        else "Landscape output: comparisons may use two columns, but keep vertical content compact."
    )
    return f"{layout_note}\n\nConvert this approved storyboard into the JSON plan:\n{storyboard}"


def _normalize_plain_equation(value: str) -> str:
    expression = re.sub(
        r"^\s*(?:choose|derive|define|let|take|conclude|(?:combine|add|adding)(?:\s+to\s+get)?|write|show|display|compute|calculate|find|use|set|evaluate|substitute(?:\s+into|\s+to\s+obtain)?|reveal|using|since|therefore|then|"
        r"simplify(?:\s+to)?|apply|obtain|the\s+antiderivative|the\s+final\s+result|final\s+result|keep(?:\s+the\s+remaining\s+integral)?)\s+",
        "",
        value,
        flags=re.IGNORECASE,
    ).strip(" .")
    expression = re.sub(
        r"^\s*\[[A-Z_]+\]\s*(?:pause\s+and\s+try\s+this:\s*)?",
        "",
        expression,
        flags=re.IGNORECASE,
    )
    expression = re.sub(r"^\s*the\s+antiderivative\s+", "", expression, flags=re.IGNORECASE)
    expression = re.sub(
        r"^\s*(?:their\s+)?(?:dot|\\cdot)\s+product\s+to\s+derive\s+",
        "",
        expression,
        flags=re.IGNORECASE,
    )
    expression = re.sub(r"^\s*reveal\s+", "", expression, flags=re.IGNORECASE)
    if ":" in expression:
        expression = expression.rsplit(":", 1)[-1].strip()
    expression = re.sub(r"^\(\d+\)\s*", "", expression)
    expression = re.sub(r"\bm([12])(?=\b|[ag]\b)", r"m_\1", expression)
    return expression


def _normalize_math_expression(value: str) -> str:
    """Convert common storyboard math glyphs into MathTex-safe LaTeX."""
    expression = value.strip().strip('"').strip("'").replace("$", "")
    expression = _rewrite_natural_math_phrases(expression)
    # Storyboard models sometimes return inline/display delimiters even
    # though the template-plan contract asks for delimiter-free LaTeX.
    # MathTex supplies its own math environment, so nested delimiters cause
    # a LaTeX "Bad math environment delimiter" failure at render time.
    expression = re.sub(r"\\(?:\(|\)|\[|\])", "", expression)
    expression = re.sub(r"\\begin\{(?:aligned|align\*?|gathered)\}", "", expression)
    expression = re.sub(r"\\end\{(?:aligned|align\*?|gathered)\}", "", expression)
    # MathTex already typesets in display style. Keeping this command is
    # unnecessary and makes malformed provider output more likely to leak.
    expression = re.sub(r"\\displaystyle\b", "", expression)
    expression = expression.replace(r"\\", " ")
    expression = re.sub(
        r"^\s*(?:choose|derive|define|let|take|conclude|(?:combine|add|adding)(?:\s+to\s+get)?|write|show|display|compute|calculate|find|use|set|evaluate|substitute(?:\s+into|\s+to\s+obtain)?|reveal|using|since|therefore|then|"
        r"simplify(?:\s+to)?|apply|obtain|the\s+antiderivative|the\s+final\s+result|final\s+result|keep(?:\s+the\s+remaining\s+integral)?)\s+",
        "",
        expression,
        flags=re.IGNORECASE,
    )
    expression = re.sub(r"^\s*the\s+antiderivative\s+", "", expression, flags=re.IGNORECASE)
    expression = re.sub(
        r"^\s*(?:their\s+)?(?:dot|\\cdot)\s+product\s+to\s+derive\s+",
        "",
        expression,
        flags=re.IGNORECASE,
    )
    # ── Unicode → LaTeX replacements ───────────────────────────────────────
    # Greek letters
    expression = expression.replace("Σ", r"\sum ").replace("∑", r"\sum ")
    expression = expression.replace("Π", r"\Pi ").replace("∏", r"\prod ")
    expression = expression.replace("Δ", r"\Delta ").replace("∇", r"\nabla ")
    expression = expression.replace("Ω", r"\Omega ").replace("Φ", r"\Phi ")
    expression = expression.replace("Ψ", r"\Psi ").replace("Γ", r"\Gamma ")
    expression = expression.replace("Λ", r"\Lambda ")
    expression = expression.replace("α", r"\alpha ").replace("β", r"\beta ")
    expression = expression.replace("γ", r"\gamma ").replace("δ", r"\delta ")
    expression = expression.replace("ε", r"\epsilon ").replace("η", r"\eta ")
    expression = expression.replace("λ", r"\lambda ").replace("μ", r"\mu ")
    expression = expression.replace("ν", r"\nu ").replace("ξ", r"\xi ")
    expression = expression.replace("ρ", r"\rho ").replace("σ", r"\sigma ")
    expression = expression.replace("τ", r"\tau ").replace("υ", r"\upsilon ")
    expression = expression.replace("φ", r"\phi ").replace("χ", r"\chi ")
    expression = expression.replace("ψ", r"\psi ").replace("ω", r"\omega ")
    # Calculus / set / misc operators
    expression = (
        expression.replace("∫", r"\int ")
        .replace("∂", r"\partial ")
        .replace("π", r"\pi ")
        .replace("∞", r"\infty")
        .replace("≤", r"\leq ")
        .replace("≥", r"\geq ")
        .replace("≠", r"\neq ")
        .replace("≡", r"\equiv ")
        .replace("≈", r"\approx ")
        .replace("∝", r"\propto ")
        .replace("∈", r"\in ")
        .replace("∉", r"\notin ")
        .replace("∠", r"\angle ")
        .replace("⊥", r"\perp ")
        .replace("∥", r"\parallel ")
        .replace("±", r"\pm ")
        .replace("×", r"\times ")
        .replace("÷", r"\div ")
        .replace("′", "'")
        .replace("−", "-")
    )
    expression = expression.replace("**", "")
    expression = expression.replace("θ", r"\theta ").replace("·", r"\cdot ")
    # Superscript / subscript Unicode digits and letters
    expression = expression.replace("⁻¹", r"^{-1}").replace("²", "^2").replace("³", "^3").replace("⁴", "^4")
    expression = expression.translate(str.maketrans({"₀": "_0", "₁": "_1", "₂": "_2", "₃": "_3", "₄": "_4", "₅": "_5", "₆": "_6", "₇": "_7", "₈": "_8", "₉": "_9"}))
    # Fix bare-paren superscripts from LLM output: f^(n) → f^{n}, x^(2) → x^{2}
    expression = re.sub(r"\^\(([^)]{1,40})\)", r"^{\1}", expression)
    expression = re.sub(
        r"√\s*([A-Za-z0-9]+)",
        lambda match: rf"\sqrt{{{match.group(1)}}}",
        expression,
    )
    expression = re.sub(
        r"\bcos\s*\^\s*\{\s*-1\s*\}",
        lambda _: r"\arccos",
        expression,
        flags=re.IGNORECASE,
    )
    expression = re.sub(
        r"\bcos\s+\\theta\b",
        lambda _: r"\cos\theta",
        expression,
        flags=re.IGNORECASE,
    )
    # Recover common backslash-free command spellings from provider output.
    expression = re.sub(r"(?<!\\)\bint\b", r"\\int", expression, flags=re.IGNORECASE)
    expression = re.sub(r"(?<!\\)\bpi\b", r"\\pi", expression, flags=re.IGNORECASE)
    expression = re.sub(r"(?<!\\)\bfrac\b", r"\\frac", expression, flags=re.IGNORECASE)
    expression = re.sub(r"(?<!\\)\b(sin|cos|tan|log|ln)\b", r"\\\1", expression, flags=re.IGNORECASE)
    expression = re.sub(r"(?<!\\)\barccos\b", lambda _: r"\arccos", expression, flags=re.IGNORECASE)
    # Direct storyboard input often uses readable plain notation. Normalize
    # these forms before the strict guard below so valid lessons do not fail
    # after voiceover audio has already been generated.
    expression = re.sub(r"(?<!\\)\btheta\b", r"\\theta", expression, flags=re.IGNORECASE)
    expression = re.sub(
        r"(?<!\\)\bsqrt\s*\(\s*([^()]{1,80}?)\s*\)",
        lambda match: rf"\sqrt{{{match.group(1).strip()}}}",
        expression,
        flags=re.IGNORECASE,
    )
    expression = re.sub(r"(?<!\\)\bsqrt\s+([A-Za-z0-9]+)", r"\\sqrt{\1}", expression, flags=re.IGNORECASE)
    expression = re.sub(r"(?<!\\)\bdot\b", r"\\cdot", expression, flags=re.IGNORECASE)
    expression = re.sub(r"(?<![A-Za-z_])r([12])\b", r"r_\1", expression)
    expression = re.sub(r"(\d+(?:\.\d+)?)\s*(?:degrees?|deg)\b", r"\1^\\circ", expression, flags=re.IGNORECASE)
    # A provider may confuse the numeral zero with the letter o in an
    # integral bound. Perform this after restoring missing command
    # backslashes so both "int o pi" and "\\int_{o}^{\\pi}" are fixed.
    expression = INTEGRAL_BOUND_LETTER_O_PATTERN.sub(r"\g<1>0", expression)
    malformed = LEAKED_MATH_CAPTION_PATTERN.search(expression)
    if malformed:
        raise ValueError(
            "Math expression contains malformed LaTeX source "
            f"({malformed.group(0)!r}); regenerate it with complete LaTeX commands."
        )
    bare_command = BARE_LATEX_COMMAND_PATTERN.search(expression)
    if bare_command:
        raise ValueError(
            "Math expression contains an unescaped LaTeX command "
            f"({bare_command.group(0)!r}); use its backslash form before rendering."
        )
    return expression.strip(" .;:")


def _rewrite_natural_math_phrases(value: str) -> str:
    """Turn the small, predictable prose vocabulary used in storyboards into LaTeX.

    The template renderer must never send instructional prose to ``MathTex``.
    This covers common hand-authored and provider-produced forms while leaving
    unsupported prose available for the validation gate to reject.
    """
    if not re.search(
        r"\bintegral\b|\bminus\b|\bplus\b|(?<!\\)\b(?:sin|cos|tan|pi)\b|\bbeside\b",
        value,
        flags=re.IGNORECASE,
    ):
        return value
    expression = re.sub(r"\bintegral\s+from\s+([^\s]+)\s+to\s+([^\s]+)\s+of\s+(.+)$", r"\\int_{\1}^{\2} \3", value, flags=re.IGNORECASE)
    expression = re.sub(r"\bintegral\s+(?:of\s+)?(.+)$", r"\\int \g<1>", expression, flags=re.IGNORECASE)
    expression = re.sub(r"\bintegral\s+from\s+([^\s]+)\s+to\s+([^\s]+)\s+of\s+(.+?)\s+dx\b", r"\\int_{\1}^{\2} \3\\,dx", expression, flags=re.IGNORECASE)
    expression = re.sub(r"\s+beside\s+a\s+coordinate[- ]free\s+equation\s+panel\b", "", expression, flags=re.IGNORECASE)
    expression = re.sub(
        r"(?P<term>[^=+]+?)\s+evaluated\s+from\s+(?P<lower>[^\s]+)\s+to\s+(?P<upper>[^\s]+)",
        r"[\g<term>]_{\g<lower>}^{\g<upper>}",
        expression,
        flags=re.IGNORECASE,
    )
    expression = re.sub(r"\s+from\s+([^\s]+)\s+to\s+([^\s]+)\b", r"_{\1}^{\2}", expression, flags=re.IGNORECASE)
    expression = re.sub(r"\bminus\b", "-", expression, flags=re.IGNORECASE)
    expression = re.sub(r"\bplus\b", "+", expression, flags=re.IGNORECASE)
    expression = re.sub(r"\bof\b", " ", expression, flags=re.IGNORECASE)
    expression = re.sub(r"\b(sin|cos|tan)\s*\(([^)]*)\)", r"\\\1(\2)", expression, flags=re.IGNORECASE)
    expression = re.sub(r"\b(sin|cos|tan)\b", r"\\\1", expression, flags=re.IGNORECASE)
    expression = re.sub(r"\bpi\b", r"\\pi", expression, flags=re.IGNORECASE)
    return expression


def _plain_equations_from_source(source: str) -> list[str]:
    # Inline/display-delimited math is extracted separately below.  Leaving it
    # in this prose parser allows a sentence such as
    # ``Solve $a=...$ for the Atwood machine`` to become a second, invalid
    # MathTex string containing the trailing English words.  Treat delimited
    # math as authoritative and only inspect the surrounding plain prose here.
    source = re.sub(
        r"\$\$(?:.|\n){1,180}?\$\$|(?<!\$)\$[^$]{1,180}\$(?!\$)|\\\([^)]{1,180}\\\)|\\\[[^]]{1,180}\\\]",
        " ",
        source,
        flags=re.DOTALL,
    )
    equations: list[str] = []
    # Do not split decimal values such as 109.47 at the period. A period is
    # sentence punctuation here only when followed by whitespace and a new
    # sentence-like token.
    for sentence in re.split(r"(?<=[;])\s+|(?<=[.!?])\s+(?=[A-Z$\\])", source):
        has_standalone_math = bool(
            re.search(
                r"\\int\b|\bintegral\b|\[[^\]]*(?:\\?sin|\\?cos)|"
                r"\b(?:sin|cos|tan)\s*\(|\b(?:arccos|arcsin|arctan)\b",
                sentence,
                flags=re.IGNORECASE,
            )
        )
        if ("=" not in sentence and not has_standalone_math) or "`" in sentence:
            continue
        starts_as_equation = bool(PLAIN_EQUATION_PREFIX.match(sentence))
        prose_word_count = len(re.findall(r"[A-Za-z]{2,}", sentence))
        if not starts_as_equation and prose_word_count > 6 and not has_standalone_math:
            continue
        # Keep a sentence's mathematical conclusion while dropping a trailing
        # prose clause such as ", the tetrahedral bond angle." Coordinate
        # tuples remain untouched because this only splits before prose cues.
        sentence = re.split(
            r",\s+(?=(?:the|a|an|which|where|for|with|as)\b)",
            sentence,
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0]
        expression = _normalize_plain_equation(sentence)
        for part in re.split(r",\s*(?=\(\d+\)|[A-Za-z(].*=)", expression):
            part = _normalize_plain_equation(part)
            if ("=" in part or has_standalone_math) and part not in equations:
                equations.append(part)
    return equations


def _looks_like_display_math(expression: str) -> bool:
    """Return whether a delimited value is meaningful MathTex content.

    A storyboard can legitimately contain a mathematical relationship without
    an equals sign.  The sine derivative cycle and a partially built Taylor
    polynomial are both teaching content, not prose.  Keeping them here
    prevents the planner from turning those beats into empty title cards.
    """
    normalized = expression.strip()
    if not normalized:
        return False
    if "=" in normalized or r"\approx" in normalized:
        return True
    if re.search(r"\\(?:sin|cos|tan|frac|dfrac|sum|int|cdot|pi|theta|infty|ldots|cdots)\b", normalized):
        return True
    # A hyphen in ordinary prose (for example, "C-H bond vectors") is not
    # enough to make the sentence a mathematical display.  Keep the
    # fallback for short expressions such as ``x - y`` only.
    arithmetic_candidate = re.search(
        r"(?:[A-Za-z0-9]\s*[+\-]\s*){1,}[A-Za-z0-9\\]", normalized
    )
    return bool(
        arithmetic_candidate
        and len(re.findall(r"[A-Za-z]+", normalized)) <= 2
        or re.search(r"[A-Za-z]\s*\^\s*(?:\{|\(|[A-Za-z0-9])", normalized)
    )


def _taylor_derivative_cycle_terms(source: str) -> list[str]:
    """Extract the four sine/cosine derivatives for the concrete cycle visual."""
    for expression in _math_delimited_values_from_source(source):
        normalized = _normalize_math_expression(expression)
        if r"\sin" not in normalized or r"\cos" not in normalized:
            continue
        terms = [
            _normalize_math_expression(part)
            for part in re.split(r"\s*,\s*", normalized)
        ]
        terms = [term for term in terms if term]
        if 2 <= len(terms) <= 4:
            return terms[:4]
    return []


def _math_delimited_values_from_source(source: str) -> list[str]:
    """Extract inline/display math without allowing surrounding prose into MathTex."""
    matches = re.findall(
        r"\$\$(.{1,180}?)\$\$|(?<!\$)\$([^$]{1,180})\$(?!\$)|\\\((.{1,180}?)\\\)|\\\[(.{1,180}?)\\\]",
        source,
        flags=re.DOTALL,
    )
    return [next((part for part in match if part), "") for match in matches]


def _math_delimited_equations_from_source(source: str) -> list[str]:
    equations: list[str] = []
    for value in _math_delimited_values_from_source(source):
        normalized = _normalize_math_expression(value)
        if _looks_like_display_math(normalized) and normalized not in equations:
            equations.append(normalized)
    return equations


def _select_display_equations(source: str, candidates: Sequence[str]) -> list[str]:
    """Choose two equations that keep a dense beat's stated conclusion visible."""
    equations = list(candidates)
    if len(equations) <= 2:
        return equations

    # A final cue such as "hence" or "therefore" means the final relation is
    # the teaching objective. Keep it with the step immediately before it,
    # rather than silently discarding it because the beat is dense.
    conclusion_cued = bool(
        re.search(r"\b(?:hence|therefore|thus|finally|answer|result|gives|obtain)\b", source, re.IGNORECASE)
    )
    if conclusion_cued:
        return [equations[-2], equations[-1]]

    result_equations = [
        value
        for value in equations
        if any(marker in value.lower() for marker in (r"\arccos", r"\theta", r"\cos"))
    ]
    return result_equations[-2:] if len(result_equations) >= 2 else equations[:2]


def _all_normalized_equations_from_source(source: str) -> list[str]:
    """Extract every trustworthy equation, including prose-form assignments.

    Display layout may be limited to two equations, but method visuals such as
    integration by parts need the complete set of assignments (u, dv, du, v).
    """
    raw_values = [*_math_delimited_values_from_source(source), *_plain_equations_from_source(source)]
    normalized: list[str] = []
    for value in raw_values:
        for part in re.split(r"\s+and\s+(?=[|A-Za-z\\])", value):
            candidate = _normalize_math_expression(part)
            if _looks_like_display_math(candidate) and candidate not in normalized:
                normalized.append(candidate)
    return normalized


def _integration_part_assignment_key(expression: str) -> str | None:
    """Return the canonical integration-by-parts assignment name, when present."""
    if "=" not in expression:
        return None
    left_hand_side = expression.split("=", 1)[0]
    key = re.sub(r"[^A-Za-z]", "", left_hand_side).casefold()
    return key if key in {"u", "du", "dv", "v"} else None


def _integration_part_assignments(candidates: Sequence[str]) -> list[str]:
    """Keep u, dv, du, and v together for a method visual when supplied."""
    assignments: dict[str, str] = {}
    for expression in candidates:
        key = _integration_part_assignment_key(expression)
        if key is not None and key not in assignments:
            assignments[key] = expression
    return [assignments[key] for key in ("u", "dv", "du", "v") if key in assignments]


def _equation_left_hand_side(expression: str) -> str:
    """Return a compact left-hand side when an expression is an equation."""
    if "=" not in expression:
        return ""
    return re.sub(r"\s+", "", expression.split("=", 1)[0])


def _should_morph_equations(source: str, target: str) -> bool:
    """Morph only a continuing equation, never two independent facts.

    Token overlap alone is misleading: ``[-x cos x]_0^pi = pi`` and
    ``int_0^pi cos x dx = 0`` share symbols but are separate evaluations.
    A stable left-hand side gives the learner a visual anchor while the right
    side is substituted or simplified.
    """
    source_lhs = _equation_left_hand_side(source)
    target_lhs = _equation_left_hand_side(target)
    if source_lhs and target_lhs and source_lhs == target_lhs:
        return True

    # Equivalent labelled functions, such as f(x) and P_2(x), can retain a
    # clear visual anchor despite different names. A loose token-overlap rule
    # is not sufficient: sin(pi)=sin(0)=0 and I=pi share pi but are separate
    # statements and must transition through a clean replacement instead.
    function_lhs = re.compile(r"^[A-Za-z](?:_[0-9]+)?\([^)]*\)$")
    return bool(function_lhs.fullmatch(source_lhs) and function_lhs.fullmatch(target_lhs))


def _vector_visual_labels(source: str) -> list[str]:
    labels: list[str] = []
    if re.search(r"\bC\s+is\s+at\s+origin\s+\(0,0,0\)", source, flags=re.IGNORECASE):
        labels.append(r"C=(0,0,0)")
    for name, coords in re.findall(
        r"\b(C|H\s*[12]?|H[₁₂])\s*(?:at\s+)?\(([^)]{3,40})\)",
        source,
        flags=re.IGNORECASE,
    ):
        label = f"{name.replace(' ', '')}=({coords})"
        if label not in labels:
            labels.append(label)
    for value in re.findall(r"\$([^$]{1,120})\$", source):
        if any(marker in value.lower() for marker in (r"\vec", "coordinate", "=<", r"\langle")):
            normalized = _normalize_math_expression(value)
            if normalized and normalized not in labels:
                labels.append(normalized)
    return labels[:3]


CAPTION_STOP_WORDS = {
    "a",
    "add",
    "and",
    "at",
    "caption",
    "central",
    "compare",
    "concrete",
    "construct",
    "define",
    "diagram",
    "display",
    "draw",
    "final",
    "governing",
    "highlight",
    "illustrate",
    "in",
    "keep",
    "label",
    "main",
    "mark",
    "of",
    "on",
    "place",
    "recap",
    "relationship",
    "return",
    "show",
    "specific",
    "state",
    "substitute",
    "the",
    "to",
    "trace",
    "view",
    "with",
    "write",
}


def _caption_tokens(value: str) -> list[str]:
    without_math = re.sub(r"`[^`]*`", " ", value)
    return [
        token
        for token in re.findall(r"\d+(?:\.\d+)?|[A-Za-z][A-Za-z0-9]*(?:[-'][A-Za-z0-9]+)*", without_math)
        if token.casefold() not in CAPTION_STOP_WORDS
    ]


def _topic_specific_caption(title: str, on_screen: str) -> str:
    tokens = _caption_tokens(on_screen)
    if not tokens:
        humanized_title = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", title)
        humanized_title = re.sub(r"[_-]+", " ", humanized_title)
        tokens = _caption_tokens(humanized_title)
    selected = tokens[:6]
    if not selected:
        return "Lesson focus"
    caption = " ".join(selected)
    return caption if selected[0].isupper() else caption[0].upper() + caption[1:]


def _humanize_context(value: str) -> str:
    """Turn a scene identifier into useful lesson context for deterministic planning."""
    spaced = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", " ", value)
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", spaced)
    return re.sub(r"[_-]+", " ", spaced)


def _short_heuristic_caption(title: str, on_screen: str, visual_kind: VisualKind, equations: Sequence[str]) -> str:
    screen_context = on_screen.lower()
    context = f"{_humanize_context(title)} {on_screen}".lower()
    if visual_kind == "taylor_axes":
        return "Taylor approximations"
    if visual_kind == "taylor_error":
        return "Truncation error"
    if visual_kind == "taylor_coefficient_filter":
        return "Filter the coefficients"
    if visual_kind == "taylor_derivative_cycle":
        return "Sine derivative cycle"
    if "atwood" in context:
        if visual_kind == "atwood" and any(
            word in screen_context for word in ("draw", "pulley", "rope", "mass")
        ):
            return "Atwood machine forces"
        if any(word in screen_context for word in ("combine", "solve", "acceleration", "a=")):
            return "Solve for acceleration"
        if any(word in screen_context for word in ("force", "tension", "equation", "m_1", "m_2")):
            return "Force equations"
        if visual_kind == "atwood":
            return "Atwood machine forces"
    if visual_kind == "vsepr_ch4":
        return "CH4 tetrahedral geometry"
    if visual_kind == "vsepr_compare":
        return "CH4 and NH3 compared"
    if visual_kind == "vsepr_nh3":
        return "NH3 trigonal pyramidal geometry"
    if visual_kind in {"vector", "dot_product_vectors"}:
        if any(word in context for word in ("arccos", "cos theta", "final result", "substitute")):
            return "Solve for cos theta"
        if any(token in screen_context for token in ("\\cdot", "cdot", "dot product")):
            return "Compute the dot product"
        if "magnitude" in context:
            return "Bond-vector magnitudes"
        if any(word in context for word in ("coordinate", "coordinates", "origin")):
            return "Bond coordinates"
        return "Bond vectors"
    if visual_kind == "molecule" and "vsepr" in context:
        return "VSEPR molecular geometry"
    if any(word in context for word in ("recap", "summary")) and any(
        word in context for word in ("taylor", "maclaurin")
    ):
        return "Taylor series recap"
    if all(word in context for word in ("constant", "linear", "quadratic")):
        return "Matched derivatives"
    if "derivative cycle" in context:
        return "Sine derivative cycle"
    if "maclaurin" in screen_context and "sin" in screen_context:
        return "Sine Maclaurin series"
    if "maclaurin" in screen_context:
        return "Maclaurin series"
    if "taylor" in screen_context:
        return "Taylor series"
    if "sin" in screen_context and any(word in context for word in ("taylor", "maclaurin")):
        return "Sine Maclaurin series"
    if "maclaurin" in context:
        return "Maclaurin series"
    if "taylor" in context:
        return "Taylor series"
    if "integration by parts" in context or "integrate by parts" in context:
        if any(word in screen_context for word in ("recap", "summary")):
            return "Integration by parts recap"
        if any(phrase in screen_context for phrase in ("choose u", "choose dv", "u=", "dv=", "u equals", "dv equals")):
            return "Choose u and dv"
        if any(word in screen_context for word in ("apply", "formula", "substitute")):
            return "Apply parts formula"
        if any(word in screen_context for word in ("conclude", "result", "therefore")):
            return "Final value"
        if any(word in screen_context for word in ("evaluate", "bounds", "bound")):
            return "Evaluate the bounds"
        if any(word in screen_context for word in ("define", "integral", "set up")):
            return "Set up the integral"
    if visual_kind == "geometry":
        if any(marker in screen_context for marker in ("same count", "same number", "different visible")):
            return "Electron groups versus shape"
        if any(marker in screen_context for marker in ("edge case", "common mistake", "does not mean")):
            return "Bond-angle caveat"
        if any(marker in screen_context for marker in ("lone pair", "unused electron", "compress", "push")):
            return "Lone-pair repulsion"
    specific_caption = _topic_specific_caption(title, on_screen)
    if visual_kind == "axes":
        return specific_caption
    if visual_kind == "vector":
        return "Bond vectors"
    if visual_kind == "geometry":
        return specific_caption
    if visual_kind == "molecule":
        return specific_caption
    if visual_kind == "process":
        return specific_caption
    if equations:
        return "Key equation"
    return specific_caption


def build_heuristic_template_plan(
    title: str,
    beat_inputs: Sequence[TemplateBeatInput],
) -> TemplateVideoPlan:
    beats: list[TemplateBeatPlan] = []
    normalized_title = _humanize_context(title).lower()
    full_source_context = " ".join(beat.on_screen for beat in beat_inputs).lower()
    full_topic_context = f"{normalized_title} {full_source_context}"
    global_molecular_geometry_context = any(
        marker in full_topic_context for marker in VSEPR_TOPIC_MARKERS
    ) or any(
        _contains_chemical_formula(full_topic_context, formula) for formula in ("ch4", "nh3")
    )
    global_vector_dot_product_context = global_molecular_geometry_context and any(
        marker in full_topic_context for marker in VECTOR_DOT_PRODUCT_MARKERS
    )
    global_integration_by_parts_context = any(
        marker in full_topic_context for marker in INTEGRATION_BY_PARTS_MARKERS
    )
    global_atwood_context = any(
        marker in full_topic_context for marker in ("atwood", "pulley")
    )
    atwood_visual_assigned = False
    integration_method_visual_assigned = False
    for beat_input in beat_inputs:
        source = re.sub(r"\s+", " ", beat_input.on_screen).strip()
        normalized = source.lower()
        topic_context = f"{normalized_title} {normalized}"
        taylor_context = any(word in topic_context for word in ("taylor", "maclaurin"))
        molecular_geometry_context = any(
            word in topic_context
            for word in ("vsepr", "molecular geometry", "tetrahedral", "pyramidal", "methane", "ammonia", "nh3", "ch4")
        ) or any(
            _contains_chemical_formula(topic_context, formula) for formula in ("ch4", "nh3")
        )
        has_ch4 = _contains_chemical_formula(normalized, "ch4") or "methane" in normalized
        has_nh3 = _contains_chemical_formula(normalized, "nh3") or "ammonia" in normalized
        derivative_match = taylor_context and all(
            word in normalized for word in ("constant", "linear", "quadratic")
        )
        taylor_derivative_cycle = taylor_context and (
            "derivative cycle" in normalized
            or (
                "derivative" in normalized
                and r"\sin" in source
                and r"\cos" in source
            )
        )
        taylor_coefficient_filter = taylor_context and any(
            marker in normalized for marker in ("coefficient", "odd-power", "odd power", "even-power", "even power")
        ) and any(marker in source for marker in (r"\dfrac", r"\frac", r"\cdot"))
        taylor_recap = taylor_context and any(word in normalized for word in ("recap", "summary"))
        vector_dot_product_context = global_vector_dot_product_context
        integration_by_parts_context = global_integration_by_parts_context
        atwood_force_law_context = global_atwood_context and (
            any(
                word in normalized
                for word in (
                    "force",
                    "tension",
                    "acceleration",
                    "equation",
                    "combine",
                    "add",
                    "solve",
                )
            )
            or bool(re.search(r"\bm_?[12]\b", normalized))
        )
        stoichiometry_context = any(marker in topic_context for marker in STOICHIOMETRY_TOPIC_MARKERS)
        reaction_flow = stoichiometry_context and any(
            word in normalized
            for word in ("reaction", "reactant", "product", "ratio", "moles", "cards", "process", "step", "sequence")
        )
        vector_calculation_cues = (
            "dot product",
            " dot ",
            "r1=",
            "r2=",
            "r_1=",
            "r_2=",
            "magnitude",
            "cos(",
            "cos theta",
            "arccos",
            "theta=",
            "|r",
            r"\cdot",
            "cdot",
        )
        vector_expression_cues = (
            "vector",
            "vectors",
            "coordinate",
            "coordinates",
            "dot product",
            "dot",
            "magnitude",
            "cos",
            r"\vec",
            r"\cdot",
            "cdot",
            "r1",
            "r2",
            "r_1",
            "r_2",
        )
        structure_cues = ("tetrahedral", "methane", "molecule", "ch4", "bond")
        molecular_comparison = has_ch4 and has_nh3 and any(
            cue in normalized for cue in ("compare", "comparison", "versus", " vs ")
        )
        explicit_ammonia_structure = has_nh3 and not has_ch4 and not any(
            cue in normalized for cue in vector_calculation_cues
        )
        if molecular_comparison:
            # Explicit comparison beats must remain comparison visuals even
            # when an earlier beat established a vector-dot-product context.
            visual_kind = "vsepr_compare"
        elif explicit_ammonia_structure:
            visual_kind = "vsepr_nh3"
        elif vector_dot_product_context and any(cue in normalized for cue in vector_calculation_cues):
            # A hybrid methane/vector lesson starts with the concrete CH4
            # structure, then switches to the vector diagram for coordinate,
            # dot-product, magnitude, cosine, and final-angle calculations.
            # This avoids showing a static 109.5-degree VSEPR label beneath a
            # more precise dot-product conclusion such as 109.47 degrees.
            visual_kind = "dot_product_vectors"
        elif vector_dot_product_context and (
            has_ch4 or any(word in normalized for word in structure_cues)
        ):
            visual_kind = "vsepr_ch4"
        elif vector_dot_product_context and any(word in normalized for word in vector_expression_cues):
            visual_kind = "dot_product_vectors"
        elif integration_by_parts_context and any(
            word in normalized for word in ("recap", "summary")
        ):
            # A recap is a compact process map, even when its text mentions
            # the same u/dv choices as the method beat.
            visual_kind = "process"
        elif integration_by_parts_context and any(
            phrase in normalized
            for phrase in (
                "choose u",
                "choose dv",
                "u=",
                "dv=",
                "u equals",
                "dv equals",
            )
        ):
            # The paired u/dv cards are the explanation for this selection;
            # do not reduce the two choices to one equation morph.
            visual_kind = "integration_by_parts"
        elif (
            integration_by_parts_context
            and not integration_method_visual_assigned
            and any(
                phrase in normalized
                for phrase in ("integration by parts", "integrate by parts")
            )
        ):
            visual_kind = "integration_by_parts"
        elif (
            taylor_context
            and any(word in normalized for word in ("graph", "curve", "plot", "axis", "axes"))
        ):
            visual_kind: VisualKind = (
                "taylor_error"
                if any(word in normalized for word in ("error", "gap", "region", "remainder"))
                else "taylor_axes"
            )
        elif taylor_derivative_cycle:
            visual_kind = "taylor_derivative_cycle"
        elif taylor_coefficient_filter:
            visual_kind = "taylor_coefficient_filter"
        elif derivative_match or taylor_recap:
            visual_kind = "process"
        elif taylor_context and any(marker in source for marker in (r"\sin", r"\cos", r"\dfrac", r"\sum")):
            # Formula construction is already the visual explanation for a
            # Taylor beat. Do not replace it with generic process cards just
            # because the storyboard says "step by step" or "pattern".
            visual_kind = "none"
        elif atwood_force_law_context:
            # A force-law derivation should retain the actual pulley and mass
            # system, rather than falling back to a generic single-arrow
            # visual after the opening diagram beat.
            visual_kind = "atwood"
        elif (
            not atwood_visual_assigned
            and any(word in normalized for word in ("atwood", "pulley", "rope", "hanging mass", "hanging masses"))
        ):
            visual_kind = "atwood"
        elif molecular_geometry_context and has_ch4 and has_nh3:
            visual_kind = "vsepr_compare"
        elif molecular_geometry_context and has_ch4:
            visual_kind = "vsepr_ch4"
        elif molecular_geometry_context and has_nh3:
            visual_kind = "vsepr_nh3"
        elif molecular_geometry_context and any(word in normalized for word in ("tetrahedral", "109.5")):
            visual_kind = "vsepr_ch4"
        elif molecular_geometry_context and any(word in normalized for word in ("lone pair", "pyramidal", "107")):
            visual_kind = "vsepr_nh3"
        elif reaction_flow:
            visual_kind = "process"
        elif any(word in normalized for word in ("graph", "curve", "plot", "axis", "axes")):
            visual_kind: VisualKind = "axes"
        elif any(word in normalized for word in ("force", "vector", "velocity", "acceleration", "arrow")):
            visual_kind = "vector"
        elif any(word in normalized for word in ("triangle", "circle", "geometry", "angle", "polygon")):
            visual_kind = "geometry"
        elif molecular_geometry_context or any(word in normalized for word in ("molecule", "atom", "bond", "orbital")):
            visual_kind = "molecule"
        elif any(word in normalized for word in ("process", "reaction", "sequence", "step")):
            visual_kind = "process"
        else:
            visual_kind = "none"

        if visual_kind == "atwood":
            atwood_visual_assigned = True
        if visual_kind == "integration_by_parts":
            integration_method_visual_assigned = True

        equations = _math_delimited_equations_from_source(source)
        equations.extend(
            value.strip()
            for value in re.findall(r"`([^`]{1,120})`", source)
            if value.strip() and value.strip() not in equations
        )
        for equation in _plain_equations_from_source(source):
            if equation not in equations:
                equations.append(equation)
        normalized_equations: list[str] = []
        for equation in equations:
            parts = re.split(r"\s+and\s+(?=[|A-Za-z\\])", equation, flags=re.IGNORECASE)
            for part in parts:
                normalized_part = _normalize_math_expression(part)
                if _looks_like_display_math(normalized_part) and normalized_part not in normalized_equations:
                    normalized_equations.append(normalized_part)
        equations = _select_display_equations(source, normalized_equations)
        parts_assignments = _integration_part_assignments(normalized_equations)
        quoted = [
            value.strip()
            # Apostrophes in f'(0) are derivative notation, not quoted card
            # labels. Only double-quoted storyboard labels belong here.
            for value in re.findall(r'"([^"\r\n]{1,40})"', source)
            if value.strip() and len(_word_tokens(value)) <= 6
        ]
        if taylor_derivative_cycle:
            equations = []
            quoted = _taylor_derivative_cycle_terms(source)
        elif derivative_match:
            quoted = ["Value", "Slope", "Curvature"]
        elif taylor_recap:
            quoted = ["Derivatives", "Maclaurin", "Approximation"]
        elif visual_kind == "process" and not quoted and ":" in source:
            quoted = [
                re.sub(r"^then\s+", "", value.strip(" ."), flags=re.IGNORECASE)
                for value in source.rsplit(":", 1)[-1].split(",")
                if 1 <= len(value.strip(" .")) <= 40 and len(_word_tokens(value)) <= 6
            ][:4]
        heading = _short_heuristic_caption(title, source, visual_kind, equations)
        visual_labels = quoted[:4]
        if visual_kind == "integration_by_parts" and len(parts_assignments) >= 2:
            # The method diagram can show all four supplied consequences even
            # when the text layout intentionally limits itself to two display
            # equations. This makes differentiation and integration visible.
            visual_labels = parts_assignments[:4]
        if visual_kind == "vector":
            visual_labels = _vector_visual_labels(source) or quoted[:4]
            if equations:
                has_coordinate_context = bool(
                    re.search(r"coordinate|origin|\bH[₁₂12]?\s+at\s+\(", source, re.IGNORECASE)
                )
                visual_labels = (
                    [value for value in visual_labels if re.match(r"^(?:C|H[₁₂12]?)=\(", value)]
                    if has_coordinate_context
                    else []
                )
        lines: list[str] = []
        layout: TemplateLayout = (
            "derivation"
            if len(equations) >= 2
            else ("equation" if equations else ("process" if visual_kind == "process" else "concept"))
        )
        beats.append(
            TemplateBeatPlan(
                beat_number=beat_input.beat_number,
                layout=layout,
                heading=heading or f"Beat {beat_input.beat_number}",
                lines=lines[:4],
                equations=equations,
                visual_kind=visual_kind,
                visual_labels=visual_labels,
            )
        )
    return TemplateVideoPlan(title=title[:120] or "Vivacity video", beats=beats)


def _py_string(value: str) -> str:
    return repr(value.replace("\x00", "").strip())


def _contains_latex_syntax(value: str) -> bool:
    return bool(LATEX_SYNTAX_PATTERN.search(value))


def _visual_kinds_for_branch(line: str) -> set[str] | None:
    single = re.fullmatch(r"    if kind == '([a-z0-9_]+)':", line)
    if single:
        return {single.group(1)}
    multiple = re.fullmatch(r"    if kind in \(([^)]+)\):", line)
    if multiple:
        return set(re.findall(r"'([a-z0-9_]+)'", multiple.group(1)))
    return None


def _prune_unused_visual_branches(lines: list[str], used_visual_kinds: set[str]) -> list[str]:
    required = set(used_visual_kinds)
    if "vsepr_compare" in required:
        required.update({"vsepr_ch4", "vsepr_nh3"})

    pruned: list[str] = []
    index = 0
    while index < len(lines):
        branch_kinds = _visual_kinds_for_branch(lines[index])
        if branch_kinds is None or branch_kinds & required:
            pruned.append(lines[index])
            index += 1
            continue

        index += 1
        while index < len(lines):
            line = lines[index]
            if line.strip() and len(line) - len(line.lstrip()) <= 4:
                break
            index += 1
    return pruned


def compile_template_scene(
    scene_name: str,
    orientation: str,
    beat_inputs: Sequence[TemplateBeatInput],
    plan: TemplateVideoPlan,
    *,
    use_mathtex: bool = True,
) -> str:
    topic_context = " ".join(
        [
            plan.title,
            *(beat.on_screen for beat in beat_inputs),
            *(beat.vo_text or "" for beat in beat_inputs),
        ]
    )
    validate_template_plan_topic_isolation(topic_context, plan)
    plan_by_number = {beat.beat_number: beat for beat in plan.beats}
    portrait = orientation == "portrait"
    lines = [
        "from manim import *",
        "import numpy as np",
        "import re",
        "",
        "# --- Video semantic color palette (defined once, reused by every beat) ---",
        "TITLE_COLOR = TEAL_C",
        "PRIMARY_COLOR = BLUE_C",
        "SECONDARY_COLOR = WHITE",
        "STRUCTURE_COLOR = GREY_B",
        "RELATION_COLOR = YELLOW_C",
        "HIGHLIGHT_COLOR = ORANGE",
        "SPECIAL_COLOR = PURPLE_C",
        "POSITIVE_COLOR = GREEN_C",
        "NEGATIVE_COLOR = RED_C",
        "REFERENCE_CURVE_COLOR = WHITE",
        "PRIMARY_CURVE_COLOR = BLUE_C",
        "SECONDARY_CURVE_COLOR = GOLD_A",
        "CENTRAL_ATOM_COLOR = PRIMARY_COLOR",
        "SURROUNDING_ATOM_COLOR = SECONDARY_COLOR",
        "BOND_COLOR = RELATION_COLOR",
        "LONE_PAIR_COLOR = SPECIAL_COLOR",
        "ANGLE_COLOR = HIGHLIGHT_COLOR",
        "FORCE_COLOR = PRIMARY_COLOR",
        "",
        "def avoid_overlap(mobj, others, min_gap=0.3):",
        "    for _ in range(24):",
        "        left = mobj.get_left()[0] - min_gap",
        "        right = mobj.get_right()[0] + min_gap",
        "        bottom = mobj.get_bottom()[1] - min_gap",
        "        top = mobj.get_top()[1] + min_gap",
        "        collision = None",
        "        for other in others:",
        "            separated = (right < other.get_left()[0] or left > other.get_right()[0] or",
        "                         top < other.get_bottom()[1] or bottom > other.get_top()[1])",
        "            if not separated:",
        "                collision = other",
        "                break",
        "        if collision is None:",
        "            return mobj",
        "        direction = mobj.get_center() - collision.get_center()",
        "        if np.linalg.norm(direction) < 1e-6:",
        "            direction = UP",
        "        mobj.shift(direction / np.linalg.norm(direction) * 0.16)",
        "    return mobj",
        "",
        "def fitted_text(value, font_size=34, color=SECONDARY_COLOR, max_width=None):",
        "    item = Text(value, font_size=font_size, color=color)",
        "    # Keep a generous horizontal safety margin for emphasis animations.",
        "    width_limit = max_width or config.frame_width * 0.76",
        "    if item.width > width_limit:",
        "        item.scale_to_fit_width(width_limit)",
        "    return item",
        "",
            "def safe_math(value, font_size=42, color=SECONDARY_COLOR):",
            "    value = re.sub(r'\\\\displaystyle\\b', '', str(value)).strip()",
            "    item = MathTex(value, font_size=font_size, color=color)",
        "    if item.width > config.frame_width * 0.76:",
        "        item.scale_to_fit_width(config.frame_width * 0.76)",
        "    return item",
        "",
        "def safe_scale(mobj, scale_factor, max_width_pct=0.85, max_height_pct=0.75):",
            "    if mobj.width <= 1e-6 or mobj.height <= 1e-6:",
            "        return mobj.animate.scale(scale_factor)",
            "    max_w = config.frame_width * max_width_pct",
            "    max_h = config.frame_height * max_height_pct",
            "    allowed_scale = min(max_w / mobj.width, max_h / mobj.height)",
            "    return mobj.animate.scale(min(scale_factor, allowed_scale))",
            "",
            "def place_graph_title(title, axes, min_buffer=0.4, min_clearance=0.3):",
            "    # Dynamic relative stacking per strict architectural rules",
            "    title.next_to(axes, UP, buff=max(0.4, min_buffer))",
            "    return title",
            "",
            "def make_visual(kind, labels, portrait=True):",
            "    if kind == 'axes':",
            "        axes = Axes(x_range=[-3, 3, 1], y_range=[-2, 2, 1], x_length=4.6, y_length=2.8, tips=False, axis_config={'color': STRUCTURE_COLOR}).shift(DOWN * 1.5)",
            "        curve = axes.plot(lambda x: 0.65 * np.sin(1.1 * x), color=PRIMARY_CURVE_COLOR)",
            "        tracer = Dot(curve.get_start(), color=HIGHLIGHT_COLOR)",
            "        return VGroup(axes, curve, tracer)",
            "    if kind == 'taylor_axes':",
            "        axes = Axes(x_range=[-2.5, 2.5, 1], y_range=[-2, 2, 1], x_length=4.8, y_length=3.0, tips=False, axis_config={'color': STRUCTURE_COLOR}).shift(DOWN * 1.5)",
            "        function_color = REFERENCE_CURVE_COLOR",
            "        linear_color = PRIMARY_CURVE_COLOR",
            "        cubic_color = SECONDARY_CURVE_COLOR",
            "        function_curve = axes.plot(lambda x: np.sin(x), color=function_color)",
            "        linear_curve = axes.plot(lambda x: x, color=linear_color)",
            "        cubic_curve = axes.plot(lambda x: x - x**3 / 6, color=cubic_color)",
            "        sin_label = safe_math(r'\\sin x', font_size=22, color=function_color)",
            "        linear_label = safe_math(r'P_1(x)=x', font_size=22, color=linear_color)",
            "        cubic_label = safe_math(r'P_3(x)=x-\\frac{x^3}{6}', font_size=22, color=cubic_color)",
            "        legend = VGroup(sin_label, linear_label, cubic_label).arrange(DOWN if portrait else RIGHT, buff=0.18, aligned_edge=LEFT)",
            "        legend.next_to(axes, DOWN, buff=0.3)",
            "        avoid_overlap(sin_label, [axes, function_curve, linear_curve, cubic_curve], min_gap=0.3)",
            "        avoid_overlap(linear_label, [axes, function_curve, linear_curve, cubic_curve, sin_label], min_gap=0.3)",
            "        avoid_overlap(cubic_label, [axes, function_curve, linear_curve, cubic_curve, sin_label, linear_label], min_gap=0.3)",
            "        return VGroup(axes, function_curve, linear_curve, cubic_curve, legend)",
            "    if kind == 'taylor_error':",
            "        axes = Axes(x_range=[-2.5, 2.5, 1], y_range=[-2, 2, 1], x_length=4.8, y_length=3.0, tips=False, axis_config={'color': STRUCTURE_COLOR})",
            "        error_color = NEGATIVE_COLOR",
            "        function_curve = axes.plot(lambda x: np.sin(x), color=REFERENCE_CURVE_COLOR)",
            "        cubic_curve = axes.plot(lambda x: x - x**3 / 6, color=SECONDARY_CURVE_COLOR)",
            "        x_values = np.linspace(-2.35, 2.35, 56)",
            "        region_points = [axes.c2p(x, np.sin(x)) for x in x_values]",
            "        region_points += [axes.c2p(x, x - x**3 / 6) for x in reversed(x_values)]",
            "        error_region = Polygon(*region_points, stroke_width=0, fill_color=HIGHLIGHT_COLOR, fill_opacity=0.24)",
            "        error_label = safe_math(r'|R_3(x)|', font_size=24, color=HIGHLIGHT_COLOR).next_to(axes, UP, buff=0.3)",
            "        avoid_overlap(error_label, [axes, function_curve, cubic_curve, error_region], min_gap=0.3)",
            "        return VGroup(axes, function_curve, cubic_curve, error_region, error_label)",
            "    if kind == 'taylor_coefficient_filter':",
            "        coefficient_specs = [('0', '1'), ('1', 'x'), ('0', r'\\dfrac{x^2}{2!}'), ('-1', r'\\dfrac{x^3}{3!}')]",
            "        cards = VGroup()",
            "        for coefficient_value, term_value in coefficient_specs:",
            "            survives = coefficient_value != '0'",
            "            box_color = PRIMARY_COLOR if survives else STRUCTURE_COLOR",
            "            box = RoundedRectangle(width=1.74, height=0.92, corner_radius=0.08, color=box_color)",
            "            coefficient = safe_math(coefficient_value, font_size=29, color=HIGHLIGHT_COLOR if survives else NEGATIVE_COLOR)",
            "            multiply = safe_math(r'\\cdot', font_size=24, color=STRUCTURE_COLOR)",
            "            term = safe_math(term_value, font_size=25, color=SECONDARY_COLOR if survives else STRUCTURE_COLOR)",
            "            expression = VGroup(coefficient, multiply, term).arrange(RIGHT, buff=0.08)",
            "            if expression.width > box.width * 0.80:",
            "                expression.scale_to_fit_width(box.width * 0.80)",
            "            expression.move_to(box)",
            "            card = VGroup(box, expression)",
            "            if not survives:",
            "                cancellation = Line(box.get_corner(DL) + RIGHT * 0.10 + UP * 0.10, box.get_corner(UR) + LEFT * 0.10 + DOWN * 0.10, color=NEGATIVE_COLOR, stroke_width=5)",
            "                card.add(cancellation)",
            "            cards.add(card)",
            "        cards.arrange_in_grid(rows=2, cols=2, buff=(0.28, 0.34))",
            "        return cards",
            "    if kind == 'taylor_derivative_cycle':",
            "        terms = labels[:4] or [r'\\sin x', r'\\cos x', r'-\\sin x', r'-\\cos x']",
            "        positions = [UP * 1.10, RIGHT * 1.72, DOWN * 1.10, LEFT * 1.72]",
            "        colors = [PRIMARY_COLOR, RELATION_COLOR, NEGATIVE_COLOR, SPECIAL_COLOR]",
            "        nodes = VGroup()",
            "        placed_nodes = []",
            "        for term, position, color in zip(terms, positions, colors):",
            "            node = safe_math(term, font_size=30, color=color).move_to(position)",
            "            avoid_overlap(node, placed_nodes, min_gap=0.30)",
            "            nodes.add(node)",
            "            placed_nodes.append(node)",
            "        arrows = VGroup()",
            "        if len(nodes) >= 2:",
            "            for index in range(len(nodes)):",
            "                next_index = (index + 1) % len(nodes)",
            "                direction = nodes[next_index].get_center() - nodes[index].get_center()",
            "                unit_direction = direction / max(np.linalg.norm(direction), 1e-6)",
            "                start = nodes[index].get_boundary_point(unit_direction)",
            "                end = nodes[next_index].get_boundary_point(-unit_direction)",
            "                arrows.add(CurvedArrow(start, end, angle=-0.34, tip_length=0.12, color=STRUCTURE_COLOR))",
            "        cycle_label = fitted_text('differentiate', font_size=22, color=STRUCTURE_COLOR)",
            "        cycle_label.move_to(ORIGIN)",
            "        avoid_overlap(cycle_label, list(nodes) + list(arrows), min_gap=0.22)",
            "        return VGroup(nodes, arrows, cycle_label)",
            "    if kind == 'vector':",
            "        origin = Dot(ORIGIN, color=SECONDARY_COLOR)",
            "        arrow = Arrow(ORIGIN, RIGHT * 2.3 + UP * 0.8, buff=0, color=FORCE_COLOR)",
            "        label_group = VGroup()",
            "        for label_value in labels:",
            "            label = safe_math(label_value, font_size=25, color=FORCE_COLOR) if any(token in label_value for token in ('\\\\', '=', '^', '_')) else fitted_text(label_value, font_size=25, color=FORCE_COLOR)",
            "            label_group.add(label)",
            "        if len(label_group) > 0:",
            "            label_group.arrange(DOWN, buff=0.18, aligned_edge=LEFT)",
            "            label_group.next_to(arrow, UP, buff=0.3)",
            "            avoid_overlap(label_group, [origin, arrow], min_gap=0.3)",
            "        return VGroup(origin, arrow, label_group)",
            "    if kind == 'dot_product_vectors':",
            "        origin = Dot(ORIGIN, color=SECONDARY_COLOR)",
            "        r1 = Arrow(ORIGIN, RIGHT * 2.0, buff=0, color=FORCE_COLOR)",
            "        r2_direction = LEFT / 3 + UP * (2 * np.sqrt(2) / 3)",
            "        r2 = Arrow(ORIGIN, r2_direction * 2.0, buff=0, color=RELATION_COLOR)",
            "        r1_label = safe_math(r'\\vec r_1', font_size=27, color=FORCE_COLOR).next_to(r1, DOWN, buff=0.24)",
            "        r2_label = safe_math(r'\\vec r_2', font_size=27, color=RELATION_COLOR).next_to(r2, LEFT, buff=0.24)",
            "        angle_arc = Arc(radius=0.62, start_angle=0, angle=np.arccos(-1 / 3), color=ANGLE_COLOR)",
            "        theta_label = safe_math(r'\\theta', font_size=25, color=ANGLE_COLOR).move_to(angle_arc.point_from_proportion(0.50) + UP * 0.30 + RIGHT * 0.16)",
            "        placed_labels = [r1_label]",
            "        avoid_overlap(r2_label, [origin, r1, r2] + placed_labels, min_gap=0.3)",
            "        placed_labels.append(r2_label)",
            "        avoid_overlap(theta_label, [origin, r1, r2, angle_arc] + placed_labels, min_gap=0.1)",
            "        return VGroup(origin, r1, r2, r1_label, r2_label, angle_arc, theta_label)",
            "    if kind == 'geometry':",
            "        circle = Circle(radius=1.2, color=PRIMARY_COLOR)",
            "        radius = Line(circle.get_center(), circle.get_right(), color=STRUCTURE_COLOR)",
            "        label = fitted_text(labels[0] if labels else 'r', font_size=27, color=PRIMARY_COLOR)",
            "        label.next_to(radius, UP, buff=0.3)",
            "        avoid_overlap(label, [circle, radius], min_gap=0.3)",
            "        return VGroup(circle, radius, label)",
            "    if kind == 'vsepr_compare':",
            "        molecule_scale = 0.92 if portrait else 0.72",
            "        ch4 = make_visual('vsepr_ch4', [], portrait=portrait).scale(molecule_scale)",
            "        nh3 = make_visual('vsepr_nh3', [], portrait=portrait).scale(molecule_scale)",
            "        ch4_label = safe_math(r'CH_4', font_size=26, color=CENTRAL_ATOM_COLOR)",
            "        nh3_label = safe_math(r'NH_3', font_size=26, color=CENTRAL_ATOM_COLOR)",
            "        ch4_descriptor = fitted_text('tetrahedral', font_size=17, color=STRUCTURE_COLOR)",
            "        nh3_descriptor = fitted_text('trigonal pyramidal', font_size=17, color=STRUCTURE_COLOR, max_width=2.4)",
            "        ch4_group = VGroup(ch4_label, ch4, ch4_descriptor).arrange(DOWN, buff=0.16)",
            "        nh3_group = VGroup(nh3_label, nh3, nh3_descriptor).arrange(DOWN, buff=0.16)",
            "        comparison = VGroup(ch4_group, nh3_group).arrange(DOWN if portrait else RIGHT, buff=0.56 if portrait else 0.72)",
            "        return comparison",
            "    if kind in ('vsepr_ch4', 'vsepr_nh3'):",
            "        center_symbol = 'C' if kind == 'vsepr_ch4' else 'N'",
            "        center_atom = Circle(radius=0.34, color=CENTRAL_ATOM_COLOR, fill_color=CENTRAL_ATOM_COLOR, fill_opacity=0.22)",
            "        center_label = safe_math(center_symbol, font_size=31, color=SURROUNDING_ATOM_COLOR).move_to(center_atom)",
            "        if kind == 'vsepr_ch4':",
            "            plane_left = LEFT * 1.35 + UP * 0.38",
            "            plane_right = RIGHT * 1.35 + UP * 0.38",
            "            front = RIGHT * 0.88 + DOWN * 1.08",
            "            back = LEFT * 0.88 + DOWN * 1.08",
            "            plane_bonds = VGroup(Line(ORIGIN, plane_left, color=BOND_COLOR), Line(ORIGIN, plane_right, color=BOND_COLOR))",
            "            wedge = Polygon(ORIGIN + DOWN * 0.04, front + LEFT * 0.16, front + RIGHT * 0.16, color=BOND_COLOR, fill_color=BOND_COLOR, fill_opacity=0.78)",
            "            dashed_bond = DashedLine(ORIGIN, back, dash_length=0.13, color=BOND_COLOR)",
            "            atom_positions = [plane_left, plane_right, front, back]",
            "            atom_offsets = [LEFT * 0.26 + UP * 0.12, RIGHT * 0.26 + UP * 0.12, RIGHT * 0.18 + DOWN * 0.20, LEFT * 0.18 + DOWN * 0.20]",
            "            angle_arc = Arc(radius=0.58, start_angle=-2.25, angle=1.36, color=ANGLE_COLOR)",
            "            angle_label = safe_math(r'109.5^\\circ', font_size=24, color=ANGLE_COLOR).move_to(DOWN * 0.82)",
            "            lone_pair = VGroup()",
            "        else:",
            "            plane = DOWN * 1.32",
            "            front = RIGHT * 1.08 + UP * 0.18",
            "            back = LEFT * 1.08 + UP * 0.18",
            "            plane_bonds = VGroup(Line(ORIGIN, plane, color=BOND_COLOR))",
            "            wedge = Polygon(ORIGIN + RIGHT * 0.03, front + UP * 0.15, front + DOWN * 0.15, color=BOND_COLOR, fill_color=BOND_COLOR, fill_opacity=0.78)",
            "            dashed_bond = DashedLine(ORIGIN, back, dash_length=0.13, color=BOND_COLOR)",
            "            atom_positions = [plane, front, back]",
            "            atom_offsets = [DOWN * 0.24, RIGHT * 0.24, LEFT * 0.24]",
            "            angle_arc = Arc(radius=0.60, start_angle=-2.98, angle=1.68, color=ANGLE_COLOR)",
            "            angle_label = safe_math(r'107^\\circ', font_size=24, color=ANGLE_COLOR).move_to(LEFT * 0.12 + DOWN * 0.73)",
            "            lone_pair = VGroup(Dot(LEFT * 0.10 + UP * 0.58, radius=0.055, color=LONE_PAIR_COLOR), Dot(RIGHT * 0.10 + UP * 0.58, radius=0.055, color=LONE_PAIR_COLOR))",
            "        bonds = VGroup(plane_bonds, wedge, dashed_bond)",
            "        atom_labels = VGroup(center_label)",
            "        placed_labels = [center_label]",
            "        for atom_position, atom_offset in zip(atom_positions, atom_offsets):",
            "            atom_label = safe_math('H', font_size=29, color=SURROUNDING_ATOM_COLOR).move_to(atom_position + atom_offset)",
            "            avoid_overlap(atom_label, placed_labels, min_gap=0.3)",
            "            atom_labels.add(atom_label)",
            "            placed_labels.append(atom_label)",
            "        avoid_overlap(angle_label, placed_labels, min_gap=0.3)",
            "        angle_group = VGroup(angle_arc, angle_label)",
            "        return VGroup(bonds, VGroup(center_atom, atom_labels), lone_pair, angle_group)",
            "    if kind == 'molecule':",
            "        center = Circle(radius=0.34, color=CENTRAL_ATOM_COLOR, fill_opacity=0.25)",
            "        left = Circle(radius=0.25, color=SURROUNDING_ATOM_COLOR).shift(LEFT * 1.3)",
            "        right = Circle(radius=0.25, color=SURROUNDING_ATOM_COLOR).shift(RIGHT * 1.3)",
            "        bonds = VGroup(Line(center.get_left(), left.get_right(), color=BOND_COLOR), Line(center.get_right(), right.get_left(), color=BOND_COLOR))",
            "        return VGroup(bonds, center, left, right)",
            "    if kind == 'integration_by_parts':",
            "        assignments = {}",
            "        for value in labels:",
            "            if '=' not in value:",
            "                continue",
            "            key = re.sub(r'[^A-Za-z]', '', value.split('=', 1)[0]).lower()",
            "            if key in ('u', 'du', 'dv', 'v') and key not in assignments:",
            "                assignments[key] = value",
            "        u_value = assignments.get('u', labels[0] if len(labels) > 0 else 'u')",
            "        dv_value = assignments.get('dv', labels[1] if len(labels) > 1 else r'dv')",
            "        has_full_parts = all(key in assignments for key in ('u', 'du', 'dv', 'v'))",
            "        def parts_card(value, width, color):",
            "            box = RoundedRectangle(width=width, height=0.78, corner_radius=0.08, color=color)",
            "            label = safe_math(value, font_size=25, color=SECONDARY_COLOR) if any(token in value for token in ('\\\\', '=', '^', '_')) else fitted_text(value, font_size=25, color=SECONDARY_COLOR, max_width=width * 0.72)",
            "            if label.width > box.width * 0.78:",
            "                label.scale_to_fit_width(box.width * 0.78)",
            "            label.move_to(box)",
            "            return VGroup(box, label)",
            "        u_card = parts_card(u_value, 1.45, PRIMARY_COLOR)",
            "        dv_card = parts_card(dv_value, 1.86, RELATION_COLOR)",
            "        method = safe_math(r'\\int u\\,dv=uv-\\int v\\,du', font_size=25, color=HIGHLIGHT_COLOR)",
            "        if has_full_parts:",
            "            du_card = parts_card(assignments['du'], 1.45, PRIMARY_COLOR)",
            "            v_card = parts_card(assignments['v'], 1.86, RELATION_COLOR)",
            "            horizontal_offset = 1.18 if portrait else 1.42",
            "            top_offset = 0.66 if portrait else 0.56",
            "            bottom_offset = 0.72 if portrait else 0.68",
            "            u_card.move_to(LEFT * horizontal_offset + UP * top_offset)",
            "            dv_card.move_to(RIGHT * horizontal_offset + UP * top_offset)",
            "            du_card.move_to(LEFT * horizontal_offset + DOWN * bottom_offset)",
            "            v_card.move_to(RIGHT * horizontal_offset + DOWN * bottom_offset)",
            "            differentiate_arrow = Arrow(u_card.get_bottom(), du_card.get_top(), buff=0.12, color=HIGHLIGHT_COLOR)",
            "            integrate_arrow = Arrow(dv_card.get_bottom(), v_card.get_top(), buff=0.12, color=HIGHLIGHT_COLOR)",
            "            differentiate_label = safe_math(r'\\frac{d}{dx}', font_size=17, color=HIGHLIGHT_COLOR).next_to(differentiate_arrow, LEFT, buff=0.08)",
            "            integrate_label = safe_math(r'\\int', font_size=22, color=HIGHLIGHT_COLOR).next_to(integrate_arrow, RIGHT, buff=0.08)",
            "            avoid_overlap(differentiate_label, [u_card, du_card, dv_card, v_card, differentiate_arrow], min_gap=0.12)",
            "            avoid_overlap(integrate_label, [u_card, du_card, dv_card, v_card, integrate_arrow, differentiate_label], min_gap=0.12)",
            "            differentiate_connector = VGroup(differentiate_arrow, differentiate_label)",
            "            integrate_connector = VGroup(integrate_arrow, integrate_label)",
            "            method.next_to(VGroup(u_card, dv_card, du_card, v_card), DOWN, buff=0.36)",
            "            avoid_overlap(method, [u_card, dv_card, du_card, v_card, differentiate_connector, integrate_connector], min_gap=0.3)",
            "            return VGroup(u_card, dv_card, du_card, v_card, differentiate_connector, integrate_connector, method)",
            "        if portrait:",
            "            u_card.shift(UP * 0.82)",
            "            dv_card.shift(DOWN * 0.34)",
            "            relation_arrow = Arrow(u_card.get_bottom(), dv_card.get_top(), buff=0.14, color=HIGHLIGHT_COLOR)",
            "        else:",
            "            u_card.shift(LEFT * 1.05 + UP * 0.28)",
            "            dv_card.shift(RIGHT * 0.95 + UP * 0.28)",
            "            relation_arrow = Arrow(u_card.get_right(), dv_card.get_left(), buff=0.14, color=HIGHLIGHT_COLOR)",
            "        method.next_to(VGroup(u_card, dv_card), DOWN, buff=0.38)",
            "        avoid_overlap(method, [u_card, dv_card, relation_arrow], min_gap=0.3)",
            "        return VGroup(u_card, dv_card, relation_arrow, method)",
            "    if kind == 'process':",
            "        # Never render UI/debug controls in an instructional video, even if a planner returns them.",
            "        names = [name for name in labels[:4] if str(name).strip().casefold() not in ('start', 'change', 'result')]",
            "        if not names:",
            "            return VGroup()",
            "        boxes = VGroup()",
            "        for name in names:",
            "            shape = RoundedRectangle(width=2.1, height=0.72, corner_radius=0.08, color=PRIMARY_COLOR)",
            "            label = fitted_text(name, font_size=24, max_width=1.8)",
            "            label.move_to(shape)",
            "            boxes.add(VGroup(shape, label))",
            "        boxes.arrange(DOWN if portrait else RIGHT, buff=0.55)",
            "        placed_labels = []",
            "        for card in boxes:",
            "            label = card[1]",
            "            other_shapes = [other[0] for other in boxes if other is not card]",
            "            avoid_overlap(label, other_shapes + placed_labels, min_gap=0.3)",
            "            placed_labels.append(label)",
            "        connectors = VGroup()",
            "        for current, following in zip(boxes, list(boxes)[1:]):",
            "            if portrait:",
            "                connector = Arrow(current.get_bottom(), following.get_top(), buff=0.12, max_tip_length_to_length_ratio=0.22, color=HIGHLIGHT_COLOR)",
            "            else:",
            "                connector = Arrow(current.get_right(), following.get_left(), buff=0.12, max_tip_length_to_length_ratio=0.22, color=HIGHLIGHT_COLOR)",
            "            connectors.add(connector)",
            "        return VGroup(boxes, connectors)",
            "    if kind == 'atwood':",
            "        pulley = Circle(radius=0.55, color=PRIMARY_COLOR).shift(UP * 1.25)",
            "        left_mass = Square(side_length=0.68, color=PRIMARY_COLOR, fill_opacity=0.18).shift(LEFT * 1.65 + DOWN * 1.05)",
            "        right_mass = Square(side_length=0.68, color=POSITIVE_COLOR, fill_opacity=0.18).shift(RIGHT * 1.65 + DOWN * 1.05)",
            "        rope = VGroup(Line(left_mass.get_top(), LEFT * 1.65 + UP * 1.25, color=STRUCTURE_COLOR), Line(LEFT * 1.65 + UP * 1.25, RIGHT * 1.65 + UP * 1.25, color=STRUCTURE_COLOR), Line(RIGHT * 1.65 + UP * 1.25, right_mass.get_top(), color=STRUCTURE_COLOR))",
            "        left_weight = Arrow(left_mass.get_bottom(), left_mass.get_bottom() + DOWN * 0.9, buff=0, color=RELATION_COLOR)",
            "        right_weight = Arrow(right_mass.get_bottom(), right_mass.get_bottom() + DOWN * 0.9, buff=0, color=RELATION_COLOR)",
            "        left_tension = Arrow(left_mass.get_top() + DOWN * 0.05, left_mass.get_top() + UP * 0.7, buff=0, color=SECONDARY_COLOR)",
            "        right_tension = Arrow(right_mass.get_top() + DOWN * 0.05, right_mass.get_top() + UP * 0.7, buff=0, color=SECONDARY_COLOR)",
            "        m1 = safe_math('m_1', font_size=28, color=SECONDARY_COLOR).move_to(left_mass)",
            "        m2 = safe_math('m_2', font_size=28, color=SECONDARY_COLOR).move_to(right_mass)",
            "        t_left = safe_math('T', font_size=25, color=SECONDARY_COLOR).next_to(left_tension, LEFT, buff=0.18)",
            "        t_right = safe_math('T', font_size=25, color=SECONDARY_COLOR).next_to(right_tension, RIGHT, buff=0.18)",
            "        w_left = safe_math('m_1g', font_size=22, color=RELATION_COLOR).next_to(left_weight, LEFT, buff=0.16)",
            "        w_right = safe_math('m_2g', font_size=22, color=RELATION_COLOR).next_to(right_weight, RIGHT, buff=0.16)",
            "        base_geometry = [rope, pulley, left_mass, right_mass, left_weight, right_weight, left_tension, right_tension]",
            "        # Mass labels deliberately remain inside their blocks; only external arrow labels are nudged.",
            "        avoid_overlap(t_left, [rope, pulley, left_mass, right_mass, left_weight, right_weight, right_tension, m1, m2], min_gap=0.3)",
            "        avoid_overlap(t_right, [rope, pulley, left_mass, right_mass, left_weight, right_weight, left_tension, m1, m2, t_left], min_gap=0.3)",
            "        avoid_overlap(w_left, [rope, pulley, left_mass, right_mass, right_weight, left_tension, right_tension, m1, m2, t_left, t_right], min_gap=0.3)",
            "        avoid_overlap(w_right, [rope, pulley, left_mass, right_mass, left_weight, left_tension, right_tension, m1, m2, t_left, t_right, w_left], min_gap=0.3)",
            "        labels = VGroup(m1, m2, t_left, t_right, w_left, w_right)",
            "        return VGroup(rope, pulley, left_mass, right_mass, left_weight, right_weight, left_tension, right_tension, labels)",
            "    return VGroup()",
            "",
            "def animate_visual(scene, kind, visual, duration, stagger=False):",
            "    duration = max(0.08, duration)",
            "    if len(visual) == 0:",
            "        return",
            "    if kind == 'axes':",
            "        scene.play(Create(visual[0]), Create(visual[1]), FadeIn(visual[2]), run_time=duration * 0.45)",
            "        scene.play(MoveAlongPath(visual[2], visual[1]), run_time=duration * 0.55, rate_func=linear)",
            "        return",
            "    if kind == 'taylor_axes':",
            "        scene.play(Create(visual[0]), run_time=duration * 0.25)",
            "        scene.play(LaggedStart(*[Create(visual[index]) for index in range(1, 4)], FadeIn(visual[4]), lag_ratio=0.12), run_time=duration * 0.75)",
            "        return",
            "    if kind == 'taylor_error':",
            "        scene.play(Create(visual[0]), Create(visual[1]), Create(visual[2]), run_time=duration * 0.62)",
            "        scene.play(FadeIn(visual[3]), FadeIn(visual[4]), run_time=duration * 0.38)",
            "        return",
            "    if kind == 'taylor_coefficient_filter':",
            "        scene.play(LaggedStart(*[FadeIn(VGroup(card[0], card[1])) for card in visual], lag_ratio=0.14), run_time=duration * 0.58)",
            "        zero_marks = [card[2] for card in visual if len(card) > 2]",
            "        if zero_marks:",
            "            scene.play(LaggedStart(*[Create(mark) for mark in zero_marks], lag_ratio=0.18), run_time=duration * 0.42)",
            "        return",
            "    if kind == 'taylor_derivative_cycle':",
            "        scene.play(LaggedStart(*[FadeIn(node) for node in visual[0]], lag_ratio=0.18), run_time=duration * 0.55)",
            "        scene.play(Create(visual[1]), FadeIn(visual[2]), run_time=duration * 0.45)",
            "        return",
            "    if kind == 'vector':",
            "        animations = [FadeIn(visual[0]), GrowArrow(visual[1])]",
            "        if len(visual[2]) > 0:",
            "            animations.append(FadeIn(visual[2]))",
            "        scene.play(*animations, run_time=duration)",
            "        return",
            "    if kind == 'dot_product_vectors':",
            "        scene.play(FadeIn(visual[0]), GrowArrow(visual[1]), FadeIn(visual[3]), run_time=duration * 0.34)",
            "        scene.play(GrowArrow(visual[2]), FadeIn(visual[4]), run_time=duration * 0.36)",
            "        scene.play(Create(visual[5]), FadeIn(visual[6]), run_time=duration * 0.30)",
            "        return",
            "    if kind == 'geometry':",
            "        scene.play(Create(visual[0]), Create(visual[1]), FadeIn(visual[2]), run_time=duration)",
            "        return",
            "    if kind == 'molecule':",
            "        scene.play(Create(visual[0]), GrowFromCenter(visual[1]), run_time=duration * 0.50)",
            "        scene.play(GrowFromCenter(visual[2]), GrowFromCenter(visual[3]), run_time=duration * 0.50)",
            "        return",
            "    if kind == 'integration_by_parts':",
            "        if len(visual) >= 7:",
            "            scene.play(LaggedStart(FadeIn(visual[0]), FadeIn(visual[1]), lag_ratio=0.20), run_time=duration * 0.28)",
            "            scene.play(GrowArrow(visual[4][0]), FadeIn(visual[4][1]), GrowArrow(visual[5][0]), FadeIn(visual[5][1]), run_time=duration * 0.34)",
            "            scene.play(LaggedStart(FadeIn(visual[2]), FadeIn(visual[3]), lag_ratio=0.18), run_time=duration * 0.24)",
            "            scene.play(FadeIn(visual[6]), run_time=duration * 0.14)",
            "            return",
            "        scene.play(LaggedStart(FadeIn(visual[0]), FadeIn(visual[1]), lag_ratio=0.20), run_time=duration * 0.42)",
            "        scene.play(GrowArrow(visual[2]), FadeIn(visual[3]), run_time=duration * 0.58)",
            "        return",
            "    if kind == 'vsepr_compare':",
            "        def reveal_molecule(group, portion):",
            "            molecule = group[1]",
            "            scene.play(FadeIn(group[0]), run_time=portion * 0.12)",
            "            scene.play(Create(molecule[0]), GrowFromCenter(molecule[1][0]), run_time=portion * 0.30)",
            "            scene.play(LaggedStart(*[FadeIn(label) for label in molecule[1][1]], lag_ratio=0.14), run_time=portion * 0.24)",
            "            if len(molecule[2]) > 0:",
            "                scene.play(FadeIn(molecule[2]), run_time=portion * 0.10)",
            "            scene.play(FadeIn(molecule[3]), FadeIn(group[2]), run_time=portion * 0.24)",
            "        reveal_molecule(visual[0], duration * 0.48)",
            "        reveal_molecule(visual[1], duration * 0.52)",
            "        return",
            "    if kind in ('vsepr_ch4', 'vsepr_nh3'):",
            "        scene.play(FadeIn(visual[0]), GrowFromCenter(visual[1][0]), LaggedStart(*[FadeIn(label) for label in visual[1][1]], lag_ratio=0.14), run_time=duration * 0.58)",
            "        if len(visual[2]) > 0:",
            "            scene.play(FadeIn(visual[2]), run_time=duration * 0.16)",
            "        # Keep the angle arc and its numeric label in one animation state.",
            "        scene.play(FadeIn(visual[3]), run_time=duration * (0.26 if len(visual[2]) > 0 else 0.42))",
            "        return",
            "    if kind == 'process':",
            "        cards = visual[0]",
            "        connectors = visual[1] if len(visual) > 1 else VGroup()",
            "        lag_ratio = 0.35 if stagger and len(cards) >= 3 else 0.18",
            "        scene.play(LaggedStart(*[FadeIn(card) for card in cards], lag_ratio=lag_ratio), run_time=duration * 0.72)",
            "        if len(connectors) > 0:",
            "            scene.play(LaggedStart(*[GrowArrow(connector) for connector in connectors], lag_ratio=0.16), run_time=duration * 0.28)",
            "        return",
            "    if kind == 'atwood':",
            "        scene.play(Create(visual[0]), Create(visual[1]), run_time=duration * 0.20)",
            "        scene.play(FadeIn(visual[2]), FadeIn(visual[3]), run_time=duration * 0.20)",
            "        scene.play(LaggedStart(*[GrowArrow(visual[index]) for index in range(4, 8)], lag_ratio=0.16), run_time=duration * 0.42)",
            "        scene.play(FadeIn(visual[8]), run_time=duration * 0.18)",
            "        return",
            "    scene.play(FadeIn(visual), run_time=duration)",
            "",
            f"class {scene_name}(Scene):",
            "    def construct(self):",
            "        self.camera.background_color = BLACK",
    ]

    used_visual_kinds = {beat.visual_kind for beat in plan.beats if beat.visual_kind != "none"}
    lines = _prune_unused_visual_branches(lines, used_visual_kinds)

    ordered_beat_numbers = [beat_input.beat_number for beat_input in beat_inputs]
    first_beat_number = ordered_beat_numbers[0]
    last_beat_number = ordered_beat_numbers[-1]
    gap_before_by_number = {beat_input.beat_number: beat_input.gap_before for beat_input in beat_inputs}
    integration_by_parts_sequence = any(
        beat.visual_kind == "integration_by_parts"
        or any(re.search(r"\\int\s*u(?:\\,|\s)*d\s*v", equation) for equation in beat.equations)
        for beat in plan.beats
    )
    previous_primary_equation: str | None = None
    previous_primary_equation_variable: str | None = None
    previous_visual_kind: str | None = None
    previous_beat_number: int | None = None
    for beat_index, beat_input in enumerate(beat_inputs):
        beat = plan_by_number[beat_input.beat_number]
        number = beat_input.beat_number
        visual_handoff_from_previous = (
            previous_beat_number is not None
            and previous_visual_kind == beat.visual_kind
            and beat.visual_kind in CONTINUOUS_VISUAL_KINDS
        )
        # Formula-only beats should foreground the mathematical relation;
        # their heading remains a compact orienting label rather than the
        # dominant object on screen.
        equation_only = beat.visual_kind == "none" and bool(beat.equations) and not beat.lines
        # The required full-diagram scale normalizes a sparse derivation beat
        # to the frame. Keep its orienting heading deliberately subordinate so
        # the equation, rather than a generic title, is the visual anchor.
        # A diagram or graph is the teaching surface for a visual beat. Keep
        # its heading orienting and compact so it cannot compete with the
        # constructed relationship after the full diagram is fitted to frame.
        heading_size = (18 if portrait else 22) if equation_only else (24 if portrait else 28)
        equation_size = 64 if equation_only else 42
        diagram_height_ratio = 0.55
        body_size = 29 if portrait else 32
        content_lines = beat.lines[:2]
        equations = beat.equations[: max(0, MAX_SUPPORTING_ITEMS_PER_BEAT - len(content_lines))]
        visual_labels = beat.visual_labels[:4]
        # The integration-by-parts visual already presents u and dv as linked
        # cards. Rendering the same assignments above it duplicates the idea
        # and makes the transition look like unrelated moving text.
        if beat.visual_kind == "integration_by_parts":
            assignments = _integration_part_assignments(equations)
            if assignments and not visual_labels:
                visual_labels = assignments[:4]
            if assignments and len(assignments) == len(equations):
                equations = []
        # Portrait lessons become unreadable when two tall equations are shown
        # as a static stack. Unless the beat explicitly compares alternatives,
        # present two expressions as one causal transformation.
        # Equations joined as separate results ("A=... and B=...") should
        # remain visible together. They are not stages of one expression and
        # morphing one into the other hides the relationship being explained.
        independent_equations = len(equations) >= 2 and bool(
            re.search(r"\b(?:and|while|respectively)\b", beat_input.on_screen, re.IGNORECASE)
        )
        stepwise_derivation = (
            len(equations) >= 2
            and beat.layout != "comparison"
            and not independent_equations
        )
        use_matching_transform = stepwise_derivation and _should_morph_equations(equations[0], equations[1])
        if beat.visual_kind == "taylor_axes":
            equations = [
                equation
                for equation in equations
                if not re.fullmatch(r"\s*(?:\\sin\s*x|P_[13]\s*\([^)]*\)\s*=.*)\s*", equation)
            ]
        # A true substitution beat may briefly retain its immediately prior
        # parts formula as an explicit causal anchor. Other equation changes
        # must use the normal clear-then-reveal handoff: recreating an old
        # MathTex object in every derivation step leaves independently timed
        # glyphs that can visibly overlap during dense transitions.
        # Only the authored on-screen specification may request this special
        # handoff. Planner headings and VO paraphrases often say
        # "substitute" while describing a normal next step; treating those
        # as a transition instruction needlessly reconstructs stale MathTex.
        substitution_cue = beat_input.on_screen
        cross_beat_substitution = bool(
            previous_primary_equation is not None
            and previous_primary_equation_variable is not None
            and previous_visual_kind == "none"
            and beat.visual_kind == "none"
            and len(equations) == 1
            and not content_lines
            and re.search(r"\bsubstitut(?:e|ing|ion)\b", substitution_cue, re.IGNORECASE)
            and re.search(r"\\int\s*u(?:\\,|\s)*d\s*v", previous_primary_equation)
        )
        same_equation_continuation = (
            previous_primary_equation is not None
            and previous_primary_equation_variable is not None
            and previous_visual_kind == "none"
            and beat.visual_kind == "none"
            and len(equations) == 1
            and equations[0] == previous_primary_equation
        )
        cross_beat_equation_transition = (
            previous_primary_equation is not None
            and previous_primary_equation_variable is not None
            and previous_visual_kind == "none"
            and beat.visual_kind == "none"
            and not content_lines
            and len(equations) == 1
            and equations[0] != previous_primary_equation
            and not cross_beat_substitution
            and _should_morph_equations(previous_primary_equation, equations[0])
        )
        continuation_source_variable = previous_primary_equation_variable if same_equation_continuation else None
        equation_transition_source_variable = (
            previous_primary_equation_variable if cross_beat_equation_transition else None
        )
        transition_source_equation = previous_primary_equation if cross_beat_substitution else None
        displayed_items = [*content_lines, *equations]
        target_duration = max(0.3, beat_input.target_duration)
        outro = min(0.5, max(0.10, target_duration * 0.12))
        heading_runtime = min(0.45, max(0.18, target_duration * 0.08))
        minimum_motion = min(0.8, max(0.15, target_duration * 0.18)) if beat.visual_kind != "none" else 0.0
        preferred_motion = min(1.8, max(minimum_motion, target_duration * 0.32))
        equation_transition_active = (
            stepwise_derivation or cross_beat_substitution or cross_beat_equation_transition
        )
        derivation_transition_runtime = (
            min(0.80, max(0.35, target_duration * 0.22)) if equation_transition_active else 0.0
        )
        derivation_preview_hold = 0.25 if equation_transition_active else 0.0
        per_item_write_runtime = (
            max(1.5, max(len(value) for value in displayed_items) * 0.05)
            if displayed_items
            else 0.0
        )
        write_lag_ratio = 0.18 if len(displayed_items) > 1 else 0.0
        required_write_runtime = per_item_write_runtime * (
            1.0 + write_lag_ratio * max(0, len(displayed_items) - 1)
        )
        # Complete-object fades avoid half-drawn glyphs and preserve a quiet pace.
        use_progressive_write = False
        content_runtime = min(0.95, max(0.22 * len(displayed_items), target_duration * 0.16)) if displayed_items else 0.0
        content_runtime = min(
            content_runtime,
            max(
                0.0,
                target_duration
                - outro
                - heading_runtime
                - minimum_motion
                - derivation_transition_runtime
                - derivation_preview_hold
                - MIN_POST_REVEAL_HOLD_SECONDS,
            ),
        )
        entry_runtime = heading_runtime + content_runtime
        motion = (
            min(
                preferred_motion,
                max(
                    0.0,
                    target_duration
                    - outro
                    - entry_runtime
                    - derivation_transition_runtime
                    - derivation_preview_hold
                    - MIN_POST_REVEAL_HOLD_SECONDS,
                ),
            )
            if beat.visual_kind != "none"
            else 0.0
        )
        # A handoff replaces the normal visual reveal, so it must occupy the
        # same budget. Using a shorter transform silently compressed every
        # later beat and desynchronized the visuals from their voiceover.
        visual_handoff_runtime = motion if visual_handoff_from_previous else 0.0
        hold = max(
            MIN_POST_REVEAL_HOLD_SECONDS,
            target_duration
            - entry_runtime
            - motion
            - outro
            - derivation_transition_runtime
            - derivation_preview_hold,
        )
        tunable_reveal_runtime = content_runtime if displayed_items else heading_runtime

        lines.extend(
            [
                "",
                f"        # --- Beat {number} params ---",
                f"        beat{number}_scale = 1.0",
                f"        beat{number}_gap = 0.3",
                f"        beat{number}_speed = {tunable_reveal_runtime:.4f}",
                f"        # --- Beat {number} ---",
                f"        # text_reveal=fade min_post_reveal_hold={MIN_POST_REVEAL_HOLD_SECONDS:.4f} required_write_time={required_write_runtime:.4f} stepwise_derivation={stepwise_derivation} cross_beat_substitution={cross_beat_substitution} cross_beat_equation_transition={cross_beat_equation_transition} same_equation_continuation={same_equation_continuation} matching_transform={use_matching_transform} visual_handoff_from_previous={visual_handoff_from_previous}",
            ]
        )
        if number == first_beat_number and beat_input.gap_before > 0:
            lines.append(f"        self.wait({beat_input.gap_before:.4f})")
        heading_factory = "safe_math" if _contains_latex_syntax(beat.heading) else "fitted_text"
        text_variable_names = [f"beat{number}_heading"]
        item_variable_names: list[str] = []
        final_equation_is_conclusion = bool(
            equations
            and re.search(
                r"\b(?:hence|therefore|thus|finally|answer|result|gives|obtain)\b",
                beat_input.on_screen,
                re.IGNORECASE,
            )
        )
        lines.extend(
            [
                f"        beat{number}_heading = {heading_factory}({_py_string(beat.heading)}, font_size={heading_size}, color=TITLE_COLOR)",
                f"        beat{number}_items = VGroup()",
            ]
        )
        for index, body in enumerate(content_lines, start=1):
            body_factory = "safe_math" if _contains_latex_syntax(body) else "fitted_text"
            text_variable_names.append(f"beat{number}_line{index}")
            item_variable_names.append(f"beat{number}_line{index}")
            lines.extend(
                [
                    f"        beat{number}_line{index} = {body_factory}({_py_string(body)}, font_size={body_size})",
                    f"        beat{number}_items.add(beat{number}_line{index})",
                ]
        )
        for index, equation in enumerate(equations, start=1):
            if same_equation_continuation and index == 1 and continuation_source_variable is not None:
                # Keep an explicitly split continuation on screen rather than
                # fading out and recreating the exact same formula.
                lines.append(f"        beat{number}_equation{index} = {continuation_source_variable}")
                continue
            if not (
                (cross_beat_substitution or cross_beat_equation_transition)
                and index == 1
            ):
                text_variable_names.append(f"beat{number}_equation{index}")
            equation_color = (
                ", color=HIGHLIGHT_COLOR"
                if final_equation_is_conclusion and index == len(equations)
                else ""
            )
            lines.extend(
                [
                    f"        beat{number}_equation{index} = safe_math({_py_string(equation)}, font_size={equation_size}{equation_color})",
                ]
            )
            if (
                (not stepwise_derivation or index == 1)
                and not (
                    (cross_beat_substitution or cross_beat_equation_transition)
                    and index == 1
                )
            ):
                item_variable_names.append(f"beat{number}_equation{index}")
                lines.append(f"        beat{number}_items.add(beat{number}_equation{index})")
        if cross_beat_substitution and transition_source_equation is not None:
            text_variable_names.append(f"beat{number}_transition_source")
            item_variable_names.append(f"beat{number}_transition_source")
            lines.extend(
                [
                    f"        beat{number}_transition_source = safe_math({_py_string(transition_source_equation)}, font_size={equation_size})",
                    f"        beat{number}_items.add(beat{number}_transition_source)",
                ]
            )
        lines.extend(
            [
                f"        if len(beat{number}_items) > 0:",
                f"            beat{number}_items.arrange(DOWN, buff=beat{number}_gap, aligned_edge=LEFT)",
                f"        beat{number}_visual = make_visual({_py_string(beat.visual_kind)}, {repr(visual_labels)}, portrait={portrait})",
                f"        beat{number}_content = VGroup(beat{number}_items, beat{number}_visual)",
                f"        beat{number}_content.arrange(DOWN if {portrait} else RIGHT, buff=0.45)",
                f"        beat{number}_diagram = VGroup(beat{number}_heading, beat{number}_content).arrange(DOWN, buff=0.38)",
                f"        beat{number}_diagram.scale(beat{number}_scale)",
            ]
        )
        if not (same_equation_continuation or cross_beat_equation_transition):
            lines.extend(
                [
                    f"        beat{number}_diagram.scale_to_fit_height(config.frame_height * {diagram_height_ratio:.2f})",
                    f"        if beat{number}_diagram.width > config.frame_width * 0.76:",
                    f"            beat{number}_diagram.scale_to_fit_width(config.frame_width * 0.76)",
                    f"        beat{number}_diagram.move_to(ORIGIN)",
                ]
            )
        else:
            lines.append(
                f"        # Keep the continuation heading at its authored size; the shared equation already fills the frame."
            )
        if beat.visual_kind == "atwood":
            # Force-law beats need three distinct vertical bands. A generic
            # centered stack leaves the lower equation competing with the
            # pulley rim, so reserve top space for the title and formulas and
            # move the complete force diagram lower as one attached group.
            lines.extend(
                [
                    f"        beat{number}_heading.to_edge(UP, buff=0.60)",
                    f"        beat{number}_visual.shift(DOWN * 0.60)",
                ]
            )
            if equations:
                lines.extend(
                    [
                        f"        beat{number}_items.move_to(beat{number}_heading.get_bottom() + DOWN * (beat{number}_items.height / 2 + 0.45))",
                        f"        avoid_overlap(beat{number}_items, [beat{number}_visual], min_gap=0.30)",
                    ]
                )
        lines.append(
            f"        beat{number}_overlap_obstacles = [beat{number}_visual] if len(beat{number}_visual) > 0 else []"
        )
        skip_heading_overlap_nudge = beat.visual_kind not in {"none", "axes", "taylor_axes", "taylor_error"}
        for variable_name in text_variable_names:
            if variable_name == f"beat{number}_heading" and skip_heading_overlap_nudge:
                lines.extend(
                    [
                        f"        avoid_overlap({variable_name}, beat{number}_overlap_obstacles, min_gap=0.0)",
                        f"        beat{number}_overlap_obstacles.append({variable_name})",
                    ]
                )
                continue
            lines.extend(
                [
                    f"        avoid_overlap({variable_name}, beat{number}_overlap_obstacles, min_gap=0.3)",
                    f"        beat{number}_overlap_obstacles.append({variable_name})",
                ]
            )
        if not (same_equation_continuation or cross_beat_equation_transition):
            lines.extend(
                [
                    f"        if beat{number}_diagram.height > config.frame_height * {diagram_height_ratio:.2f}:",
                    f"            beat{number}_diagram.scale_to_fit_height(config.frame_height * {diagram_height_ratio:.2f})",
                    f"        if beat{number}_diagram.width > config.frame_width * 0.76:",
                    f"            beat{number}_diagram.scale_to_fit_width(config.frame_width * 0.76)",
                    f"        beat{number}_diagram.move_to(ORIGIN)",
                ]
            )
        if stepwise_derivation:
            lines.extend(
                [
                    f"        beat{number}_equation2.move_to(beat{number}_equation1)",
                    f"        if beat{number}_equation2.width > config.frame_width * 0.76:",
                    f"            beat{number}_equation2.scale_to_fit_width(config.frame_width * 0.76)",
                ]
            )
        if cross_beat_substitution:
            lines.extend(
                [
                    f"        beat{number}_equation1.match_height(beat{number}_transition_source)",
                    f"        if beat{number}_equation1.width > config.frame_width * 0.76:",
                    f"            beat{number}_equation1.scale_to_fit_width(config.frame_width * 0.76)",
                    f"        beat{number}_equation1.move_to(beat{number}_transition_source)",
                    # The source already occupies this location, so exclude it
                    # while checking the target against all other visible
                    # mobjects. This preserves a continuous transform without
                    # allowing a wider result to collide with the heading.
                    f"        beat{number}_transition_obstacles = [other for other in beat{number}_overlap_obstacles if other is not beat{number}_transition_source]",
                    f"        avoid_overlap(beat{number}_equation1, beat{number}_transition_obstacles, min_gap=0.3)",
                ]
            )
        if cross_beat_equation_transition and equation_transition_source_variable is not None:
            lines.extend(
                [
                    # The preceding relation remains in the scene until the
                    # target is ready. This turns a simplification into a
                    # readable causal change rather than a card swap.
                    f"        beat{number}_equation1.match_height({equation_transition_source_variable})",
                    f"        if beat{number}_equation1.width > config.frame_width * 0.76:",
                    f"            beat{number}_equation1.scale_to_fit_width(config.frame_width * 0.76)",
                    f"        beat{number}_equation1.move_to({equation_transition_source_variable})",
                    f"        avoid_overlap(beat{number}_equation1, beat{number}_overlap_obstacles, min_gap=0.3)",
                    f"        beat{number}_text_group = VGroup(beat{number}_heading, beat{number}_equation1).arrange(DOWN, buff=0.4)",
                    f"        beat{number}_text_group.to_edge(UP, buff=0.5)",
                ]
            )
        if same_equation_continuation and continuation_source_variable is not None:
            lines.extend(
                [
                    # The continuing formula remains the visual anchor. Place
                    # the fresh orienting heading above it without rebuilding
                    # or moving the already-visible equation.
                    f"        beat{number}_text_group = VGroup(beat{number}_heading, {continuation_source_variable}).arrange(DOWN, buff=0.4)",
                    f"        beat{number}_text_group.to_edge(UP, buff=0.5)",
                ]
            )
        if beat.visual_kind in {"axes", "taylor_axes", "taylor_error"}:
            lines.extend(
                [
                    f"        beat{number}_axes = beat{number}_visual[0]",
                    f"        beat{number}_heading.next_to(beat{number}_axes, UP, buff=0.4)",
                    f"        place_graph_title(beat{number}_heading, beat{number}_axes)",
                    f"        beat{number}_diagram.move_to(ORIGIN)",
                ]
            )
        if not cross_beat_equation_transition:
            lines.append(
                f"        self.play(FadeIn(beat{number}_heading), run_time="
                + (f"{heading_runtime:.4f})" if item_variable_names else f"beat{number}_speed)")
            )
        if item_variable_names:
            item_animations = [
                f"Write({variable_name})"
                if use_progressive_write
                else f"FadeIn({variable_name})"
                for variable_name in item_variable_names
            ]
            per_item_runtime = max(0.18, content_runtime / len(item_animations))
            for item_animation in item_animations:
                lines.append(f"        self.play({item_animation}, run_time={per_item_runtime:.4f})")
        lines.extend(
            [
                f"        if len(beat{number}_visual) > 0:",
                (
                    f"            self.play(ReplacementTransform(beat{previous_beat_number}_visual, beat{number}_visual), run_time={visual_handoff_runtime:.4f})"
                    if visual_handoff_from_previous
                    else f"            animate_visual(self, {_py_string(beat.visual_kind)}, beat{number}_visual, {motion:.4f}, stagger={number == last_beat_number and beat.visual_kind == 'process' and len(beat.visual_labels) >= 3})"
                ),
                f"        else:",
                "            pass",
            ]
        )
        if stepwise_derivation:
            lines.append(f"        self.wait({derivation_preview_hold:.4f})")
            if use_matching_transform:
                lines.append(
                    f"        self.play(TransformMatchingTex(beat{number}_equation1, beat{number}_equation2), run_time={derivation_transition_runtime:.4f})"
                )
                lines.extend(
                    [
                        # Manim can retain unmatched source glyphs after a
                        # matching transform. Replace the displayed object
                        # explicitly so the held frame contains one equation.
                        f"        self.remove(beat{number}_equation1)",
                        f"        self.add(beat{number}_equation2)",
                    ]
                )
            else:
                fade_out_runtime = derivation_transition_runtime * 0.42
                fade_in_runtime = derivation_transition_runtime - fade_out_runtime
                lines.extend(
                    [
                        f"        self.play(FadeOut(beat{number}_equation1), run_time={fade_out_runtime:.4f})",
                        f"        self.play(FadeIn(beat{number}_equation2), run_time={fade_in_runtime:.4f})",
                    ]
                )
        elif cross_beat_substitution:
            emphasis_runtime = derivation_transition_runtime * 0.24
            clear_runtime = derivation_transition_runtime * 0.31
            reveal_runtime = derivation_transition_runtime - emphasis_runtime - clear_runtime
            lines.extend(
                [
                    f"        self.wait({derivation_preview_hold:.4f})",
                    "        # Keep the substitution causal without placing two incompatible equation layouts on top of each other.",
                    f"        self.play(Indicate(beat{number}_transition_source, color=HIGHLIGHT_COLOR, scale_factor=1.03), run_time={emphasis_runtime:.4f})",
                    f"        self.play(FadeOut(beat{number}_transition_source, shift=UP * 0.14), run_time={clear_runtime:.4f})",
                    f"        self.play(FadeIn(beat{number}_equation1, shift=DOWN * 0.14), run_time={reveal_runtime:.4f})",
                ]
            )
        elif same_equation_continuation and continuation_source_variable is not None:
            lines.extend(
                [
                    "        # The same relation carries across a storyboard split; emphasize it instead of restarting it.",
                    f"        self.play(Indicate({continuation_source_variable}, color=HIGHLIGHT_COLOR, scale_factor=1.025), run_time={content_runtime:.4f})",
                ]
            )
        elif cross_beat_equation_transition and equation_transition_source_variable is not None:
            clear_runtime = derivation_transition_runtime * 0.46
            reveal_runtime = derivation_transition_runtime - clear_runtime
            lines.extend(
                [
                    f"        self.wait({derivation_preview_hold:.4f})",
                    # Matching-glyph transforms can briefly stack incompatible
                    # terms. Keep the common algebraic anchor, but clear and
                    # reveal the two expressions sequentially for clean frames.
                    "        # Carry shared terms forward without ever overlaying old and new glyphs.",
                    f"        self.play(FadeOut({equation_transition_source_variable}, shift=UP * 0.12), run_time={clear_runtime:.4f})",
                    f"        self.play(FadeIn(beat{number}_heading), run_time={heading_runtime:.4f})",
                    f"        self.play(FadeIn(beat{number}_equation1, shift=DOWN * 0.12), run_time={reveal_runtime:.4f})",
                ]
            )
        if hold > 0:
            lines.append(f"        self.wait({hold:.4f})")
        if number != last_beat_number:
            next_number = ordered_beat_numbers[ordered_beat_numbers.index(number) + 1]
            next_gap = gap_before_by_number.get(next_number, 0.0)
            if next_gap > 0:
                lines.append(f"        self.wait({next_gap:.4f})")
        next_beat = plan_by_number[beat_inputs[beat_index + 1].beat_number] if beat_index + 1 < len(beat_inputs) else None
        preserve_visual_for_next = (
            next_beat is not None
            and beat.visual_kind == next_beat.visual_kind
            and beat.visual_kind in CONTINUOUS_VISUAL_KINDS
        )
        preserve_equation_for_next = (
            next_beat is not None
            and beat.visual_kind == "none"
            and next_beat.visual_kind == "none"
            and len(equations) == 1
            and len(next_beat.equations) == 1
            and (
                equations[0] == next_beat.equations[0]
                or (
                    not content_lines
                    and not next_beat.lines
                    and _should_morph_equations(equations[0], next_beat.equations[0])
                )
            )
        )
        if preserve_visual_for_next:
            fade_members = [f"beat{number}_heading", f"beat{number}_items"]
            if stepwise_derivation:
                fade_members.append(f"beat{number}_equation2")
            elif cross_beat_substitution:
                fade_members.append(f"beat{number}_equation1")
            fade_target = f"VGroup({', '.join(fade_members)})"
        elif preserve_equation_for_next:
            # The next beat explicitly continues this exact equation. Fade
            # only the old heading now; the equation remains the shared
            # visual anchor for the continuation beat.
            fade_target = f"beat{number}_heading"
        else:
            fade_target = (
                f"VGroup(beat{number}_diagram, beat{number}_equation2)"
                if stepwise_derivation
                else (
                    f"VGroup(beat{number}_diagram, beat{number}_equation1)"
                    if cross_beat_substitution or cross_beat_equation_transition
                    else f"beat{number}_diagram"
                )
            )
        lines.append(f"        self.play(FadeOut({fade_target}), run_time={outro:.4f})")
        if equations:
            previous_primary_equation = equations[-1]
            previous_primary_equation_variable = f"beat{number}_equation{len(equations)}"
        else:
            previous_primary_equation = None
            previous_primary_equation_variable = None
        previous_visual_kind = beat.visual_kind
        previous_beat_number = number

    lines.append("")
    return "\n".join(lines)
