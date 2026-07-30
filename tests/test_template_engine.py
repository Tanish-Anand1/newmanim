import ast

from manim import Text, WHITE

from app.pipeline import validate_generated_python, validate_video_semantic_palette
from app.template_engine import (
    TemplateBeatInput,
    TemplateBeatPlan,
    TemplateVideoPlan,
    build_heuristic_template_plan,
    compile_template_scene,
    enrich_template_plan_visuals,
    parse_template_plan,
    validate_template_plan_topic_isolation,
)


def test_parse_template_plan_requires_exact_beat_order():
    raw = (
        '{"title":"Vectors","beats":['
        '{"beat_number":1,"layout":"concept","heading":"Vector",'
        '"lines":["Magnitude and direction"],"equations":[],"visual_kind":"vector","visual_labels":["F"]}'
        "]}"
    )
    plan = parse_template_plan(raw, [1])
    assert plan.beats[0].visual_kind == "vector"


def test_parse_template_plan_rejects_imperative_stage_direction_as_text():
    raw = (
        '{"title":"Atwood","beats":['
        '{"beat_number":1,"layout":"concept","heading":"Draw a pulley",'
        '"lines":[],"equations":[],"visual_kind":"atwood","visual_labels":[]}'
        "]}"
    )

    try:
        parse_template_plan(raw, [1])
    except ValueError as exc:
        assert "imperative stage direction" in str(exc)
    else:
        raise AssertionError("Expected a stage direction in a rendered heading to be rejected")


def test_parse_template_plan_rejects_duplicate_connector_and_math_in_plain_text():
    duplicate = (
        '{"title":"Taylor","beats":['
        '{"beat_number":1,"layout":"concept","heading":"Then then continue",'
        '"lines":[],"equations":[],"visual_kind":"none","visual_labels":[]}'
        "]}"
    )
    plain_math = (
        '{"title":"Taylor","beats":['
        '{"beat_number":1,"layout":"concept","heading":"Coefficient",'
        '"lines":["$f(x)$"],"equations":[],"visual_kind":"none","visual_labels":[]}'
        "]}"
    )

    for raw, expected in ((duplicate, "duplicate connector"), (plain_math, "places math syntax")):
        try:
            parse_template_plan(raw, [1])
        except ValueError as exc:
            assert expected in str(exc)
        else:
            raise AssertionError(f"Expected template-plan failure containing {expected!r}")


def test_parse_template_plan_repairs_stripped_latex_caption_and_generic_process_labels():
    raw = (
        '{"title":"Integral by parts","beats":['
        '{"beat_number":1,"layout":"equation",'
        '"heading":"Displaystyle I Big x cos x","lines":[],'
        '"equations":["\\\\displaystyle I=\\\\int_{0}^{\\\\pi}x\\\\sin x"],'
        '"visual_kind":"process","visual_labels":["Start","Change","Result"]}'
        "]}"
    )
    plan = parse_template_plan(raw, [1], {1: "An equation step"})

    assert plan.beats[0].heading == "Key equation"
    assert "\\displaystyle" not in plan.beats[0].equations[0]
    assert plan.beats[0].visual_kind == "none"
    assert plan.beats[0].visual_labels == []


def test_parse_template_plan_repairs_integral_zero_and_rejects_unescaped_math_commands():
    lower_bound_typo = (
        '{"title":"Integral by parts","beats":['
        '{"beat_number":1,"layout":"equation","heading":"Evaluate the integral",'
        '"lines":[],"equations":["\\\\int_{o}^{\\\\pi}x\\\\sin x\\\\,dx"],'
        '"visual_kind":"none","visual_labels":[]}'
        "]}"
    )
    plan = parse_template_plan(lower_bound_typo, [1])
    assert plan.beats[0].equations == [r"\int_{0}^{\pi}x\sin x\,dx"]

    malformed = (
        '{"title":"Integral by parts","beats":['
        '{"beat_number":1,"layout":"equation","heading":"Evaluate the integral",'
        '"lines":[],"equations":["Displaystyle I Big x cos x"],'
        '"visual_kind":"none","visual_labels":[]}'
        "]}"
    )
    try:
        parse_template_plan(malformed, [1])
    except ValueError as exc:
        assert "malformed LaTeX" in str(exc)
    else:
        raise AssertionError("Expected malformed equation source to be rejected")


def test_equation_reveals_use_complete_math_objects_without_progressive_write():
    plan = TemplateVideoPlan(
        title="Integral",
        beats=[TemplateBeatPlan(beat_number=1, heading="Equation", equations=[r"\int_0^\pi x\sin x\,dx"])]
    )
    code = compile_template_scene(
        "IntegralRevealScene",
        "portrait",
        [TemplateBeatInput(1, 5.0, 0.0, "Show the equation", "")],
        plan,
    )

    assert "Write(beat1_equation1)" not in code
    assert "FadeIn(beat1_equation1)" in code


def test_heuristic_plan_keeps_a_cued_final_equation_from_a_dense_beat():
    plan = build_heuristic_template_plan(
        "Integration by parts",
        [
            TemplateBeatInput(
                1,
                6.0,
                0.0,
                (
                    "Evaluate $$[-x\\cos(x)]_{0}^{\\pi}=\\pi$$ and "
                    "$$\\int_{0}^{\\pi}\\cos(x)\\,dx=0$$, hence $$I=\\pi$$."
                ),
                "The boundary term is pi and the remaining integral is zero.",
            )
        ],
    )

    assert plan.beats[0].equations == [r"\int_{0}^{\pi}\cos(x)\,dx=0", r"I=\pi"]


def test_cued_final_equation_uses_the_result_highlight_color():
    beat = TemplateBeatInput(
        1,
        6.0,
        0.0,
        r"Evaluate $$\int_{0}^{\pi}\cos(x)\,dx=0$$, hence $$I=\pi$$.",
        "The remaining integral is zero, so I equals pi.",
    )
    plan = build_heuristic_template_plan("Integration by parts", [beat])

    code = compile_template_scene("HighlightedConclusionScene", "portrait", [beat], plan)

    assert "beat1_equation2 = safe_math('I=\\\\pi', font_size=64, color=HIGHLIGHT_COLOR)" in code


def test_derivation_morphs_one_equation_into_the_next_instead_of_stacking_them():
    plan = TemplateVideoPlan(
        title="Integration by parts",
        beats=[
            TemplateBeatPlan(
                beat_number=1,
                layout="derivation",
                heading="Apply parts formula",
                equations=[
                    r"I=\int_{0}^{\pi}x\sin x\,dx",
                    r"I=[-x\cos x]_{0}^{\pi}+\int_{0}^{\pi}\cos x\,dx",
                ],
            )
        ],
    )
    code = compile_template_scene(
        "IntegrationDerivationScene",
        "portrait",
        [TemplateBeatInput(1, 4.0, 0.0, "Apply integration by parts", "")],
        plan,
    )

    assert "stepwise_derivation=True" in code
    assert "TransformMatchingTex(beat1_equation1, beat1_equation2)" in code
    assert "beat1_items.add(beat1_equation2)" not in code
    assert "self.wait(1.5100)" in code
    validate_generated_python(code)


def test_compile_template_scene_never_emits_debug_button_defaults():
    plan = TemplateVideoPlan(
        title="Reaction sequence",
        beats=[TemplateBeatPlan(beat_number=1, heading="Reaction stages", visual_kind="process")],
    )
    code = compile_template_scene(
        "ProcessWithoutLabelsScene",
        "portrait",
        [TemplateBeatInput(1, 4.0, 0.0, "Show the reaction sequence", "")],
        plan,
    )

    assert "['Start', 'Change', 'Result']" not in code
    assert "if not names:" in code
    validate_generated_python(code)


def test_integration_by_parts_visual_builds_the_method_relationship():
    plan = TemplateVideoPlan(
        title="Integration by parts",
        beats=[
            TemplateBeatPlan(
                beat_number=1,
                heading="Choose u and dv",
                visual_kind="integration_by_parts",
                visual_labels=[r"u=x", r"dv=\sin x\,dx"],
            )
        ],
    )
    code = compile_template_scene(
        "IntegrationMethodScene",
        "portrait",
        [TemplateBeatInput(1, 4.0, 0.0, "Choose u and dv for integration by parts", "")],
        plan,
    )

    assert "if kind == 'integration_by_parts':" in code
    assert r"\int u\,dv=uv-\int v\,du" in code
    assert "GrowArrow(visual[2])" in code
    assert "label.scale_to_fit_width(box.width * 0.78)" in code
    validate_generated_python(code)


def test_heuristic_plan_uses_integration_by_parts_visual_for_the_method_beat():
    plan = build_heuristic_template_plan(
        "IntegrationByPartsScene",
        [
            TemplateBeatInput(
                1,
                4.0,
                0.0,
                "Choose u and dv before applying integration by parts.",
                "",
            )
        ],
    )

    assert plan.beats[0].visual_kind == "integration_by_parts"


def test_heuristic_plan_uses_the_integration_by_parts_visual_once():
    plan = build_heuristic_template_plan(
        "Integration by parts",
        [
            TemplateBeatInput(1, 4.0, 0.0, "Define the definite integral.", ""),
            TemplateBeatInput(2, 4.0, 0.0, "Choose u equals x and dv equals sin x dx.", ""),
            TemplateBeatInput(3, 4.0, 0.0, "Apply the formula and evaluate the bounds.", ""),
        ],
    )

    assert [beat.visual_kind for beat in plan.beats] == ["none", "integration_by_parts", "none"]


def test_heuristic_plan_uses_method_specific_integration_headings():
    plan = build_heuristic_template_plan(
        "Integration by parts",
        [
            TemplateBeatInput(1, 4.0, 0.0, "Define the integral.", ""),
            TemplateBeatInput(2, 4.0, 0.0, "Choose u equals x and dv equals sin x dx.", ""),
            TemplateBeatInput(3, 4.0, 0.0, "Apply the formula and evaluate the bounds.", ""),
            TemplateBeatInput(4, 4.0, 0.0, "Conclude with the result.", ""),
        ],
    )

    assert [beat.heading for beat in plan.beats] == [
        "Set up the integral",
        "Choose u and dv",
        "Apply parts formula",
        "Final value",
    ]


def test_heuristic_plan_keeps_atwood_diagram_for_the_final_force_result():
    plan = build_heuristic_template_plan(
        "Atwood machine",
        [
            TemplateBeatInput(1, 4.0, 0.0, "Show the Atwood machine pulley and masses.", ""),
            TemplateBeatInput(2, 4.0, 0.0, r"Write $T-m_1g=m_1a$ and $m_2g-T=m_2a$.", ""),
            TemplateBeatInput(3, 4.0, 0.0, r"Combine to get $a=\frac{(m_2-m_1)g}{m_1+m_2}$.", ""),
        ],
    )

    assert [beat.visual_kind for beat in plan.beats] == ["atwood", "none", "atwood"]
    assert [beat.heading for beat in plan.beats] == [
        "Atwood machine forces",
        "Force equations",
        "Solve for acceleration",
    ]
    assert plan.beats[2].equations == [r"a=\frac{(m_2-m_1)g}{m_1+m_2}"]


def test_diagram_titles_are_not_nudged_away_from_an_already_arranged_visual():
    plan = TemplateVideoPlan(
        title="Atwood machine",
        beats=[TemplateBeatPlan(beat_number=1, heading="Atwood machine forces", visual_kind="atwood")],
    )
    code = compile_template_scene(
        "AtwoodTitleLayoutScene",
        "portrait",
        [TemplateBeatInput(1, 4.0, 0.0, "Show the Atwood machine pulley.", "")],
        plan,
    )

    assert "avoid_overlap(beat1_heading, beat1_overlap_obstacles, min_gap=0.0)" in code
    assert "w_left = safe_math('m_1g'" in code
    assert "w_right = safe_math('m_2g'" in code
    assert "a_label = safe_math" not in code


def test_heuristic_plan_deduplicates_instruction_prefix_from_inline_math():
    plan = build_heuristic_template_plan(
        "Integration by parts",
        [
            TemplateBeatInput(
                1,
                4.0,
                0.0,
                r"Define $I=\int_{0}^{\pi}x\sin x\,dx$.",
                "",
            )
        ],
    )

    assert plan.beats[0].equations == [r"I=\int_{0}^{\pi}x\sin x\,dx"]


def test_heuristic_plan_removes_conclude_prefix_from_inline_math():
    plan = build_heuristic_template_plan(
        "Integration by parts",
        [TemplateBeatInput(1, 4.0, 0.0, r"Conclude $I=\pi$.", "")],
    )

    assert plan.beats[0].equations == [r"I=\pi"]


def test_natural_language_integration_storyboard_becomes_typeset_math_and_full_method_visual():
    beat_inputs = [
        TemplateBeatInput(
            1,
            8.0,
            0.0,
            "Display I = integral from 0 to pi of x sin(x) dx beside a coordinate-free equation panel",
            "",
        ),
        TemplateBeatInput(
            2,
            8.0,
            0.0,
            "Choose u = x and dv = sin(x) dx; derive du = dx and v = -cos(x)",
            "",
        ),
        TemplateBeatInput(3, 8.0, 0.0, "Substitute into I = uv minus integral of v du", ""),
    ]
    plan = build_heuristic_template_plan("IntegrationByPartsRecallScene", beat_inputs)
    plan = enrich_template_plan_visuals(
        "integration by parts",
        plan,
        {beat.beat_number: beat.on_screen for beat in beat_inputs},
    )

    assert plan.beats[0].equations == [r"I = \int_{0}^{\pi} x  \sin(x) dx"]
    assert plan.beats[1].visual_kind == "integration_by_parts"
    assert plan.beats[1].visual_labels == [
        r"u = x",
        r"dv =  \sin(x) dx",
        r"du = dx",
        r"v = - \cos(x)",
    ]
    assert plan.beats[2].equations == [r"I = uv - \int v du"]

    code = compile_template_scene("NaturalLanguageIntegrationScene", "portrait", beat_inputs, plan)
    assert "coordinate-free" not in code
    assert "integral from" not in code
    validate_generated_python(code)


def test_natural_language_recall_and_reveal_beats_keep_standalone_math():
    beat_inputs = [
        TemplateBeatInput(
            1,
            8.0,
            0.0,
            "[RECALL_CHECKPOINT] Pause and try this: evaluate integral from 0 to 2 of x sin(x) dx",
            "",
        ),
        TemplateBeatInput(2, 8.0, 0.0, "Reveal [-x cos(x) + sin(x)] from 0 to 2", ""),
    ]
    plan = build_heuristic_template_plan("IntegrationByPartsRecallScene", beat_inputs)
    assert plan.beats[0].equations == [r"\int_{0}^{2} x  \sin(x) dx"]
    assert plan.beats[1].equations == [r"[-x  \cos(x) +  \sin(x)]_{0}^{2}"]

    code = compile_template_scene("StandaloneMathRecallScene", "portrait", beat_inputs, plan)
    assert "Pause and try this" not in code
    assert "Reveal [" not in code
    validate_generated_python(code)


def test_natural_language_bounds_group_the_full_antiderivative_term():
    plan = build_heuristic_template_plan(
        "Integration by parts",
        [
            TemplateBeatInput(
                1,
                8.0,
                0.0,
                "Substitute to obtain I = -x cos(x) evaluated from 0 to pi plus integral from 0 to pi of cos(x) dx",
                "",
            ),
            TemplateBeatInput(
                2,
                8.0,
                0.0,
                "Reveal the antiderivative [-x cos(x) + sin(x)] from 0 to pi",
                "",
            ),
        ],
    )

    assert plan.beats[0].equations == [
        r"I =[ -x  \cos(x)]_{0}^{\pi} + \int_{0}^{\pi}  \cos(x) dx"
    ]
    assert plan.beats[1].equations == [r"[-x  \cos(x) +  \sin(x)]_{0}^{\pi}"]


def test_integration_recap_uses_concrete_process_cards_instead_of_heading_only():
    beat_inputs = [
        TemplateBeatInput(
            1,
            8.0,
            0.0,
            "Recap: choose u, integrate dv, then evaluate the bounds",
            "",
        )
    ]
    plan = build_heuristic_template_plan("IntegrationByPartsRecapScene", beat_inputs)
    beat = plan.beats[0]

    assert beat.visual_kind == "process"
    assert beat.heading == "Integration by parts recap"
    assert beat.visual_labels == ["choose u", "integrate dv", "evaluate the bounds"]

    enriched = enrich_template_plan_visuals(
        "Integration by parts",
        plan,
        {1: beat_inputs[0].on_screen},
    )
    assert enriched.beats[0].visual_kind == "process"
    assert enriched.beats[0].heading == "Integration by parts recap"
    assert enriched.beats[0].visual_labels == [
        "choose u",
        "integrate dv",
        "evaluate the bounds",
    ]

    code = compile_template_scene("IntegrationByPartsRecapScene", "portrait", beat_inputs, plan)
    assert "make_visual('process', ['choose u', 'integrate dv', 'evaluate the bounds']" in code
    validate_generated_python(code)


def test_integration_by_parts_cards_do_not_duplicate_assignment_equations():
    plan = TemplateVideoPlan(
        title="Integration by parts",
        beats=[
            TemplateBeatPlan(
                beat_number=1,
                heading="Choose u and dv",
                equations=[r"u=x", r"dv=\sin x\,dx"],
                visual_kind="integration_by_parts",
            )
        ],
    )
    code = compile_template_scene(
        "IntegrationAssignmentCardsScene",
        "portrait",
        [TemplateBeatInput(1, 4.0, 0.0, "Choose u and dv", "")],
        plan,
    )

    assert "beat1_equation1 = safe_math" not in code
    assert "TransformMatchingTex(beat1_equation1" not in code
    assert "make_visual('integration_by_parts', ['u=x', 'dv=\\\\sin x\\\\,dx']" in code


def test_unrelated_equations_crossfade_instead_of_ghosting_through_a_morph():
    plan = TemplateVideoPlan(
        title="Integration by parts",
        beats=[
            TemplateBeatPlan(
                beat_number=1,
                layout="derivation",
                heading="Apply parts formula",
                equations=[
                    r"\int u\,dv=uv-\int v\,du",
                    r"I=[-x\cos x]_{0}^{\pi}+\int_{0}^{\pi}\cos x\,dx",
                ],
            )
        ],
    )
    code = compile_template_scene(
        "IntegrationCrossfadeScene",
        "portrait",
        [TemplateBeatInput(1, 4.0, 0.0, "Apply integration by parts", "")],
        plan,
    )

    assert "TransformMatchingTex(beat1_equation1, beat1_equation2)" not in code
    assert "FadeOut(beat1_equation1)" in code
    assert "FadeIn(beat1_equation2)" in code


def test_independent_equation_results_remain_visible_together():
    plan = TemplateVideoPlan(
        title="Integration by parts",
        beats=[
            TemplateBeatPlan(
                beat_number=1,
                layout="derivation",
                heading="Evaluate the bounds",
                equations=[
                    r"[-x\cos x]_{0}^{\pi}=\pi",
                    r"\int_{0}^{\pi}\cos x\,dx=0",
                ],
            )
        ],
    )

    code = compile_template_scene(
        "IndependentResultsScene",
        "portrait",
        [
            TemplateBeatInput(
                1,
                5.0,
                0.0,
                "Evaluate the boundary term and the remaining cosine integral.",
                "",
            )
        ],
        plan,
    )

    assert "stepwise_derivation=False" in code
    assert "TransformMatchingTex(beat1_equation1, beat1_equation2)" not in code
    assert "beat1_items.add(beat1_equation2)" in code
    validate_generated_python(code)


def test_integration_substitution_uses_a_matching_transform_from_the_parts_formula():
    plan = TemplateVideoPlan(
        title="Integration by parts",
        beats=[
            TemplateBeatPlan(beat_number=1, heading="Set up the integral", equations=[r"I=\int_0^\pi x\sin(x)\,dx"]),
            TemplateBeatPlan(
                beat_number=2,
                heading="Choose u and dv",
                equations=[r"u=x", r"dv=\sin(x)\,dx"],
                visual_kind="integration_by_parts",
                visual_labels=[r"u=x", r"dv=\sin(x)\,dx"],
            ),
            TemplateBeatPlan(beat_number=3, heading="Apply parts formula", equations=[r"\int u\,dv=uv-\int v\,du"]),
            TemplateBeatPlan(
                beat_number=4,
                heading="Substitute the parts",
                equations=[r"I=[-x\cos(x)]_0^\pi+\int_0^\pi\cos(x)\,dx"],
            ),
        ],
    )
    beat_inputs = [
        TemplateBeatInput(1, 4.0, 0.0, "Define the integral.", ""),
        TemplateBeatInput(2, 4.0, 0.0, "Choose u and dv.", ""),
        TemplateBeatInput(3, 4.0, 0.0, "Apply the formula.", ""),
        TemplateBeatInput(4, 4.0, 0.0, "Substitute the selected parts.", ""),
    ]

    code = compile_template_scene("IntegrationSubstitutionScene", "portrait", beat_inputs, plan)

    assert "cross_beat_substitution=True" in code
    assert "beat4_transition_source = safe_math('\\\\int u\\\\,dv=uv-\\\\int v\\\\,du'" in code
    assert "avoid_overlap(beat4_equation1, beat4_transition_obstacles, min_gap=0.3)" in code
    assert "Indicate(beat4_transition_source, color=HIGHLIGHT_COLOR, scale_factor=1.03)" in code
    assert "FadeOut(beat4_transition_source, shift=UP * 0.14)" in code
    assert "FadeIn(beat4_equation1, shift=DOWN * 0.14)" in code
    assert "TransformMatchingTex(beat4_transition_source, beat4_equation1)" not in code
    validate_generated_python(code, "Apply integration by parts.")


def test_plan_enrichment_requires_integration_by_parts_visual_when_planner_omits_it():
    plan = TemplateVideoPlan(
        title="Definite integral",
        beats=[
            TemplateBeatPlan(
                beat_number=1,
                heading="Choose the parts",
                equations=[r"I=\int_{0}^{\pi}x\sin x\,dx"],
                visual_kind="none",
            ),
            TemplateBeatPlan(
                beat_number=2,
                heading="Apply the formula",
                equations=[r"\int u\,dv=uv-\int v\,du"],
                visual_kind="none",
            ),
        ],
    )

    enriched = enrich_template_plan_visuals(
        "Determine the integral using integration by parts.",
        plan,
        {1: "Choose u and dv.", 2: "Apply integration by parts."},
    )

    assert [beat.visual_kind for beat in enriched.beats] == ["none", "integration_by_parts"]


def test_plan_enrichment_moves_empty_parts_visual_to_the_actual_u_dv_choice():
    plan = TemplateVideoPlan(
        title="Definite integral",
        beats=[
            TemplateBeatPlan(
                beat_number=1,
                heading="Key equation",
                equations=[r"I=\int_{0}^{\pi}x\sin(x)\,dx"],
                visual_kind="integration_by_parts",
            ),
            TemplateBeatPlan(
                beat_number=2,
                heading="Key equation",
                equations=[r"u=x", r"dv=\sin(x)\,dx"],
            ),
            TemplateBeatPlan(
                beat_number=3,
                heading="Key equation",
                equations=[r"\int u\,dv=uv-\int v\,du"],
            ),
        ],
    )

    enriched = enrich_template_plan_visuals(
        "Determine the integral using integration by parts.",
        plan,
        {
            1: "Define the integral.",
            2: "Choose u=x and dv=sin(x) dx.",
            3: "Apply the method.",
        },
    )

    assert [beat.visual_kind for beat in enriched.beats] == ["none", "integration_by_parts", "none"]
    assert enriched.beats[1].visual_labels == [r"u=x", r"dv=\sin(x)\,dx"]
    assert [beat.heading for beat in enriched.beats] == [
        "Set up the integral",
        "Choose u and dv",
        "Apply parts formula",
    ]


def test_parse_template_plan_rejects_maclaurin_letter_o():
    raw = (
        '{"title":"Maclaurin","beats":['
        '{"beat_number":1,"layout":"equation","heading":"Derivative coefficient",'
        '"lines":["Evaluate at the expansion center"],"equations":["f^{(n)}(o)"],'
        '"visual_kind":"none","visual_labels":[]}'
        "]}"
    )

    try:
        parse_template_plan(raw, [1])
    except ValueError as exc:
        assert "numeral 0" in str(exc)
    else:
        raise AssertionError("Expected Maclaurin letter o to fail template-plan validation")


def test_heuristic_plan_strips_inline_math_delimiters_before_mathtex():
    plan = build_heuristic_template_plan(
        "Integral",
        [
            TemplateBeatInput(
                1,
                5.0,
                0.0,
                r"Let \(u=x\) and \(dv=\sin(x)\,dx\);",
                "Choose the parts.",
            )
        ],
    )
    equations = plan.beats[0].equations
    assert equations
    assert all("\\(" not in equation and "\\)" not in equation for equation in equations)


def test_heuristic_plan_removes_instruction_prefixes_from_math_equations():
    plan = build_heuristic_template_plan(
        "Integral",
        [
            TemplateBeatInput(
                1,
                5.0,
                0.0,
                "Write ∫ u dv = uv - ∫ v du;",
                "Apply integration by parts.",
            )
        ],
    )
    equation = plan.beats[0].equations[0]
    assert not equation.lower().startswith("write")
    assert r"\int" in equation


def test_delimited_equation_does_not_absorb_trailing_prose_into_mathtex():
    plan = build_heuristic_template_plan(
        "Atwood machine",
        [
            TemplateBeatInput(
                1,
                5.0,
                0.0,
                r"Solve $a=\frac{(m_2-m_1)g}{m_1+m_2}$ for the Atwood machine.",
                "State the result.",
            )
        ],
    )

    assert plan.beats[0].equations == [r"a=\frac{(m_2-m_1)g}{m_1+m_2}"]
    assert plan.beats[0].visual_kind == "atwood"


def test_atwood_force_law_beats_keep_the_system_diagram():
    plan = build_heuristic_template_plan(
        "Atwood machine",
        [
            TemplateBeatInput(1, 5.0, 0.0, "Draw the pulley with masses m1 and m2.", "Set up the system."),
            TemplateBeatInput(2, 5.0, 0.0, r"Use $T-m_1g=m_1a$ for m1.", "Apply Newton's law."),
            TemplateBeatInput(3, 5.0, 0.0, r"Add $m_2g-T=m_2a$ to solve for acceleration.", "Combine the equations."),
        ],
    )

    assert [beat.visual_kind for beat in plan.beats] == ["atwood", "atwood", "atwood"]


def test_heuristic_integral_normalizes_plain_commands_and_instruction_prefix():
    plan = build_heuristic_template_plan(
        "Integral by parts",
        [
            TemplateBeatInput(
                1,
                5.0,
                0.0,
                "Substitute into I=uv-int v du and simplify to I=pi",
                "Apply the limits.",
            )
        ],
    )
    equations = plan.beats[0].equations
    assert equations
    assert all("into " not in equation.lower() for equation in equations)
    assert any(r"\int" in equation for equation in equations)
    assert any(r"\pi" in equation for equation in equations)


def test_parse_template_plan_rejects_operational_spec_caption_by_word_overlap():
    on_screen = "Compare the graph of sin x with its linear and cubic approximations near the origin"
    raw = (
        '{"title":"Taylor","beats":['
        '{"beat_number":1,"layout":"comparison",'
        f'"heading":"{on_screen}","lines":[],"equations":[],"visual_kind":"taylor_axes","visual_labels":[]}}'
        "]}"
    )

    try:
        parse_template_plan(raw, [1], {1: on_screen})
    except ValueError as exc:
        assert "copies its operational ON SCREEN spec" in str(exc)
    else:
        raise AssertionError("Expected copied operational template caption to fail validation")


def test_compile_template_scene_is_valid_and_uses_composition_contract():
    plan = TemplateVideoPlan(
        title="Force",
        beats=[
            TemplateBeatPlan(
                beat_number=1,
                heading="Resolve the force",
                lines=["Along the incline"],
                equations=[r"F_{x}=F\cos\theta"],
                visual_kind="vector",
                visual_labels=["F"],
            )
        ],
    )
    code = compile_template_scene(
        "ForceScene",
        "portrait",
        [TemplateBeatInput(1, 2.0, 0.0, "Resolve F", "Resolve the force")],
        plan,
    )

    ast.parse(code)
    storyboard = '[0-2] ON SCREEN: Resolve the force along the incline | VO: "Resolve the force."'
    validate_generated_python(code, storyboard)
    assert "# --- Beat 1 params ---" in code
    assert "scale_to_fit_height(config.frame_height * 0.55)" in code
    assert "def avoid_overlap" in code
    assert "def animate_visual" in code
    assert "GrowArrow" in code
    assert "Indicate(" not in code
    assert "self.wait(0.6500)" in code
    assert "def safe_scale" in code
    assert "except Exception" not in code
    assert "avoid_overlap(beat1_heading, beat1_overlap_obstacles" in code
    assert "avoid_overlap(beat1_line1, beat1_overlap_obstacles" in code
    assert "avoid_overlap(beat1_equation1, beat1_overlap_obstacles" in code


def test_compile_template_scene_uses_readable_reveal_or_nonprogressive_fade():
    short_plan = TemplateVideoPlan(
        title="Taylor",
        beats=[
            TemplateBeatPlan(
                beat_number=1,
                heading="Coefficient meaning",
                lines=["This deliberately long explanation cannot be written legibly inside a very short beat."],
            )
        ],
    )
    short_code = compile_template_scene(
        "ShortTaylorScene",
        "portrait",
        [TemplateBeatInput(1, 2.0, 0.0, "Explain the coefficient", "A short narration")],
        short_plan,
    )
    assert "# text_reveal=fade" in short_code
    assert "min_post_reveal_hold=0.6500" in short_code
    assert "self.play(FadeIn(beat1_line1), run_time=" in short_code
    assert "Write(beat1_line1)" not in short_code
    validate_generated_python(short_code)

    write_plan = TemplateVideoPlan(
        title="Taylor",
        beats=[TemplateBeatPlan(beat_number=1, heading="Term", equations=[r"x^2"])],
    )
    write_code = compile_template_scene(
        "ReadableWriteScene",
        "portrait",
        [TemplateBeatInput(1, 5.0, 0.0, "Write the quadratic term", "The quadratic term appears")],
        write_plan,
    )
    assert "# text_reveal=fade min_post_reveal_hold=0.6500 required_write_time=1.5000" in write_code
    assert "beat1_speed = 0.8000" in write_code
    assert "self.play(FadeIn(beat1_equation1), run_time=0.8000)" in write_code
    assert "beat1_entry_anims" not in write_code
    validate_generated_python(write_code)


def test_compile_template_scene_morphs_two_noncomparison_formula_items():
    plan = TemplateVideoPlan(
        title="Formula sequence",
        beats=[
            TemplateBeatPlan(
                beat_number=1,
                heading="Equivalent forms",
                equations=[r"f(x)=x+x^2", r"P_2(x)=x+x^2"],
            )
        ],
    )
    code = compile_template_scene(
        "FormulaSequenceScene",
        "portrait",
        [TemplateBeatInput(1, 6.0, 0.0, "Show both equivalent formulas", "")],
        plan,
    )

    assert "self.play(FadeIn(beat1_equation1), run_time=0.9500)" in code
    assert "TransformMatchingTex(beat1_equation1, beat1_equation2)" in code
    assert "beat1_items.add(beat1_equation2)" not in code
    assert "beat1_entry_anims" not in code
    validate_generated_python(code)


def test_template_curve_labels_reuse_their_curve_color_variables():
    plan = TemplateVideoPlan(
        title="Taylor graph",
        beats=[TemplateBeatPlan(beat_number=1, heading="Taylor approximations", visual_kind="taylor_axes")],
    )
    code = compile_template_scene(
        "CurveColorScene",
        "portrait",
        [TemplateBeatInput(1, 5.0, 0.0, "Compare Taylor curves", "")],
        plan,
    )

    assert "linear_curve = axes.plot(lambda x: x, color=linear_color)" in code
    assert "linear_label = safe_math(r'P_1(x)=x', font_size=22, color=linear_color)" in code
    assert "cubic_color = SECONDARY_CURVE_COLOR" in code
    assert "cubic_curve = axes.plot(lambda x: x - x**3 / 6, color=cubic_color)" in code


def test_taylor_axes_do_not_repeat_curve_formulas_as_extra_text():
    plan = TemplateVideoPlan(
        title="Taylor graph",
        beats=[
            TemplateBeatPlan(
                beat_number=1,
                heading="Taylor approximations",
                equations=[r"P_1(x)=x", r"P_3(x)=x-\frac{x^3}{6}"],
                visual_kind="taylor_axes",
            )
        ],
    )
    code = compile_template_scene(
        "TaylorNoDuplicateFormulaScene",
        "portrait",
        [TemplateBeatInput(1, 5.0, 0.0, "Compare the Taylor curves", "")],
        plan,
    )

    assert "beat1_equation1 =" not in code
    assert "linear_label = safe_math(r'P_1(x)=x'" in code
    assert "cubic_label = safe_math(r'P_3(x)=x-\\frac{x^3}{6}'" in code
    assert "cubic_label = safe_math(r'P_3(x)=x-\\frac{x^3}{6}', font_size=22, color=cubic_color)" in code


def test_graph_titles_are_rechecked_against_axes_after_final_fit():
    plan = TemplateVideoPlan(
        title="Taylor graph titles",
        beats=[
            TemplateBeatPlan(beat_number=1, heading="Taylor approximations", visual_kind="taylor_axes"),
            TemplateBeatPlan(beat_number=2, heading="Truncation error", visual_kind="taylor_error"),
        ],
    )
    code = compile_template_scene(
        "GraphTitleClearanceScene",
        "portrait",
        [
            TemplateBeatInput(1, 5.0, 0.0, "Compare Taylor curves", ""),
            TemplateBeatInput(2, 5.0, 0.0, "Show truncation error", ""),
        ],
        plan,
    )

    for number in (1, 2):
        final_fit = f"beat{number}_diagram.scale_to_fit_width(config.frame_width * 0.76)"
        axes_assignment = f"beat{number}_axes = beat{number}_visual[0]"
        title_position = f"beat{number}_heading.next_to(beat{number}_axes, UP, buff=0.4)"
        axis_guard = (
            f"avoid_overlap(beat{number}_heading, [beat{number}_visual, beat{number}_axes], min_gap=0.3)"
        )
        axis_y = f"beat{number}_axis_line_y = beat{number}_axes.x_axis.get_center()[1]"
        minimum_bottom = f"beat{number}_minimum_title_bottom = beat{number}_axis_line_y + 0.3"
        numeric_guard = f"beat{number}_heading.get_bottom()[1] <= beat{number}_minimum_title_bottom"
        assert final_fit in code
        assert axes_assignment in code
        assert title_position in code
        assert axis_guard in code
        assert axis_y in code
        assert minimum_bottom in code
        assert numeric_guard in code
        assert code.index(final_fit) < code.index(axes_assignment) < code.index(title_position) < code.index(axis_guard)

    validate_generated_python(
        code,
        '[0-5] ON SCREEN: Compare Taylor curves | VO: "Compare."\n'
        '[5-10] ON SCREEN: Show truncation error | VO: "Show error."',
    )


def test_graph_title_bottom_is_numerically_above_x_axis():
    plan = TemplateVideoPlan(
        title="Taylor graph titles",
        beats=[
            TemplateBeatPlan(beat_number=1, heading="Taylor approximations", visual_kind="taylor_axes"),
            TemplateBeatPlan(beat_number=2, heading="Truncation error", visual_kind="taylor_error"),
        ],
    )
    code = compile_template_scene(
        "NumericGraphTitleClearanceScene",
        "portrait",
        [
            TemplateBeatInput(1, 5.0, 0.0, "Compare Taylor curves", ""),
            TemplateBeatInput(2, 5.0, 0.0, "Show truncation error", ""),
        ],
        plan,
    )
    namespace: dict[str, object] = {}
    exec(code, namespace)
    captured_titles: dict[str, object] = {}
    captured_visuals: dict[str, object] = {}
    original_fitted_text = namespace["fitted_text"]
    original_make_visual = namespace["make_visual"]

    def capture_fitted_text(value, *args, **kwargs):
        title = original_fitted_text(value, *args, **kwargs)
        if value in {"Taylor approximations", "Truncation error"}:
            captured_titles[value] = title
        return title

    def lightweight_math(value, font_size=42, color=WHITE):
        return Text(value, font_size=min(font_size, 22), color=color)

    def capture_visual(kind, *args, **kwargs):
        visual = original_make_visual(kind, *args, **kwargs)
        if kind in {"taylor_axes", "taylor_error"}:
            captured_visuals[kind] = visual
        return visual

    namespace["fitted_text"] = capture_fitted_text
    namespace["safe_math"] = lightweight_math
    namespace["make_visual"] = capture_visual
    scene = namespace["NumericGraphTitleClearanceScene"]()
    scene.play = lambda *args, **kwargs: None
    scene.wait = lambda *args, **kwargs: None
    scene.construct()

    for title_text, kind in (
        ("Taylor approximations", "taylor_axes"),
        ("Truncation error", "taylor_error"),
    ):
        title = captured_titles[title_text]
        axes = captured_visuals[kind][0]
        assert title.get_bottom()[1] > axes.x_axis.get_center()[1] + 0.3


def test_final_process_recap_uses_stronger_staggered_reveal():
    plan = TemplateVideoPlan(
        title="Taylor recap",
        beats=[
            TemplateBeatPlan(
                beat_number=1,
                heading="Taylor series recap",
                visual_kind="process",
                visual_labels=["Derivatives", "Maclaurin", "Approximation"],
            )
        ],
    )
    code = compile_template_scene(
        "RecapScene",
        "portrait",
        [TemplateBeatInput(1, 5.0, 0.0, "Recap the three Taylor ideas", "")],
        plan,
    )

    assert "lag_ratio = 0.35 if stagger and len(cards) >= 3 else 0.18" in code
    assert "GrowArrow(connector)" in code
    assert "animate_visual(self, 'process', beat1_visual, 1.6000, stagger=True)" in code


def test_compile_template_scene_clears_previous_beat_before_next_text():
    plan = TemplateVideoPlan(
        title="Taylor",
        beats=[
            TemplateBeatPlan(beat_number=1, heading="Function", visual_kind="axes"),
            TemplateBeatPlan(beat_number=2, heading="Polynomial", equations=[r"P_2(x)=1+x+x^2"]),
        ],
    )
    code = compile_template_scene(
        "ContinuousTaylorScene",
        "portrait",
        [
            TemplateBeatInput(1, 4.0, 0.0, "Plot the function", "Start with the function graph"),
            TemplateBeatInput(2, 4.0, 0.0, "Show the polynomial", "Replace it with the polynomial"),
        ],
        plan,
    )

    assert "beat2_entry_anims.append(FadeOut(beat1_diagram" not in code
    beat1_block = code.split("# --- Beat 1 ---", 1)[1].split("# --- Beat 2 params ---", 1)[0]
    assert "self.play(FadeOut(beat1_heading), FadeOut(beat1_items), FadeOut(beat1_visual)" in beat1_block
    assert "self.remove(beat1_heading, beat1_items, beat1_visual)" in beat1_block
    storyboard = (
        '[0-4] ON SCREEN: Plot the function | VO: "Start with the function graph"\n'
        '[4-8] ON SCREEN: Show the polynomial | VO: "Replace it with the polynomial"'
    )
    validate_generated_python(code, storyboard)


def test_compile_template_scene_hands_off_repeated_diagrams_without_a_black_reset():
    plan = TemplateVideoPlan(
        title="Atwood machine",
        beats=[
            TemplateBeatPlan(beat_number=1, heading="Atwood machine forces", visual_kind="atwood"),
            TemplateBeatPlan(
                beat_number=2,
                heading="Force equations",
                equations=[r"T-m_1g=m_1a"],
                visual_kind="atwood",
            ),
        ],
    )
    code = compile_template_scene(
        "ContinuousAtwoodScene",
        "portrait",
        [
            TemplateBeatInput(1, 4.0, 0.0, "Draw the Atwood machine", "Identify the two masses."),
            TemplateBeatInput(2, 4.0, 0.0, "Write the force equation", "Apply Newton's law."),
        ],
        plan,
    )

    beat1_block = code.split("# --- Beat 1 ---", 1)[1].split("# --- Beat 2 params ---", 1)[0]
    beat2_block = code.split("# --- Beat 2 ---", 1)[1]
    assert "visual_handoff_from_previous=True" in beat2_block
    assert "safe_visual_transform(beat1_visual, beat2_visual, zone='anchor', run_time=1.2800)" in beat2_block
    assert "animate_visual(self, 'atwood', beat2_visual" not in beat2_block
    assert "FadeOut(beat1_heading), FadeOut(beat1_items)" in beat1_block
    assert "FadeOut(beat1_diagram" not in beat1_block
    validate_generated_python(code, "[0-4] ON SCREEN: Atwood machine | VO: \"Identify the two masses.\"")


def test_graph_titles_can_fade_while_an_axes_visual_hands_off_to_the_next_beat():
    plan = TemplateVideoPlan(
        title="Taylor graph",
        beats=[
            TemplateBeatPlan(beat_number=1, heading="Taylor approximations", visual_kind="taylor_axes"),
            TemplateBeatPlan(beat_number=2, heading="Taylor approximations", visual_kind="taylor_axes"),
        ],
    )
    code = compile_template_scene(
        "ContinuousTaylorAxesScene",
        "portrait",
        [
            TemplateBeatInput(1, 4.0, 0.0, "Plot sin x and its first approximation", "Compare the curves."),
            TemplateBeatInput(2, 4.0, 0.0, "Keep the graph visible while highlighting the cubic approximation", "Add the cubic curve."),
        ],
        plan,
    )

    assert "safe_visual_transform(beat1_visual, beat2_visual" in code
    validate_generated_python(code)


def test_enrich_template_plan_keeps_the_atwood_machine_present_through_force_steps():
    plan = TemplateVideoPlan(
        title="Atwood machine",
        beats=[
            TemplateBeatPlan(beat_number=1, heading="Setup", visual_kind="atwood"),
            TemplateBeatPlan(beat_number=2, heading="Equation", equations=[r"T-m_1g=m_1a"]),
            TemplateBeatPlan(beat_number=3, heading="Equation", equations=[r"m_2g-T=m_2a"]),
            TemplateBeatPlan(
                beat_number=4,
                heading="Combine",
                equations=[r"a=\\frac{(m_2-m_1)g}{m_1+m_2}"],
            ),
            TemplateBeatPlan(
                beat_number=5,
                heading="Result",
                equations=[r"T=\\frac{2m_1m_2g}{m_1+m_2}"],
            ),
        ],
    )
    on_screen = {
        1: "Construct an Atwood machine with a pulley and two masses.",
        2: "Keep the Atwood diagram visible and write the left force equation.",
        3: "Keep the same Atwood diagram visible and write the right force equation.",
        4: "Keep the diagram visible while combining the equations for acceleration.",
        5: "Keep the diagram visible and conclude the tension.",
    }

    enriched = enrich_template_plan_visuals("Atwood machine", plan, on_screen)

    assert [beat.visual_kind for beat in enriched.beats] == ["atwood"] * 5
    assert [beat.heading for beat in enriched.beats] == [
        "Atwood machine forces",
        "Force equations",
        "Force equations",
        "Solve for acceleration",
        "Solve for tension",
    ]


def test_compile_template_scene_routes_latex_lines_to_mathtex_helper():
    plan = TemplateVideoPlan(
        title="Taylor series",
        beats=[
            TemplateBeatPlan(
                beat_number=1,
                heading="Maclaurin expansion",
                lines=[r"\sin x=x-\frac{x^3}{3!}+\cdots"],
                equations=[],
            )
        ],
    )
    code = compile_template_scene(
        "TaylorScene",
        "portrait",
        [TemplateBeatInput(1, 3.0, 0.0, "Show expansion", "")],
        plan,
    )

    assert "beat1_line1 = safe_math(" in code
    assert "beat1_line1 = fitted_text" not in code
    validate_generated_python(code)


def test_compile_template_scene_rejects_decorative_zoom_for_requested_emphasis():
    plan = TemplateVideoPlan(
        title="Zoom",
        beats=[TemplateBeatPlan(beat_number=1, heading="Zoom in", lines=["Focus on the result."])],
    )
    code = compile_template_scene(
        "ZoomScene",
        "portrait",
        [TemplateBeatInput(1, 3.0, 0.0, "Zoom in for emphasis", "")],
        plan,
    )

    assert "safe_scale(beat1_diagram, 1.12)" not in code
    assert "Indicate(beat1_heading" not in code
    assert "min_post_reveal_hold=0.6500" in code
    validate_generated_python(code)


def test_heuristic_template_plan_selects_visual_without_provider():
    plan = build_heuristic_template_plan(
        "Forces",
        [TemplateBeatInput(1, 3.0, 0.0, 'Draw a force vector labeled "F"', None)],
    )
    assert plan.beats[0].visual_kind == "vector"
    assert plan.beats[0].visual_labels == ["F"]


def test_heuristic_template_plan_does_not_typeset_prose_containing_x_equals_zero():
    source = "Compare the graph of sin x with its Taylor approximations near x=0."
    plan = build_heuristic_template_plan(
        "Taylor graph",
        [
            TemplateBeatInput(
                1,
                5.0,
                0.0,
                source,
                None,
            )
        ],
    )

    assert plan.beats[0].visual_kind == "taylor_axes"
    assert plan.beats[0].equations == []
    assert plan.beats[0].heading == "Taylor approximations"
    assert plan.beats[0].lines == []

    code = compile_template_scene(
        "TaylorComparisonScene",
        "portrait",
        [TemplateBeatInput(1, 5.0, 0.0, source, None)],
        plan,
    )
    assert "function_curve" in code
    assert "linear_curve" in code
    assert "cubic_curve" in code
    assert "P_3(x)=x-\\frac{x^3}{6}" in code
    assert source not in code
    validate_generated_python(code, f'[0-5] ON SCREEN: {source} | VO: "Compare the curves."')


def test_heuristic_caption_prioritizes_beat_subject_over_mixed_scene_title():
    plan = build_heuristic_template_plan(
        "Taylor and Maclaurin series",
        [
            TemplateBeatInput(
                1,
                5.0,
                0.0,
                r"Build Taylor's formula: `f(x)=\sum_{n=0}^{\infty}\frac{f^{(n)}(a)}{n!}(x-a)^n`.",
                None,
            )
        ],
    )

    assert plan.beats[0].heading == "Taylor series"


def test_heuristic_template_plan_builds_taylor_error_region():
    source = "Keep the graph visible while the truncation-error region grows away from x=0."
    plan = build_heuristic_template_plan(
        "Taylor error",
        [TemplateBeatInput(1, 5.0, 0.0, source, None)],
    )
    code = compile_template_scene(
        "TaylorErrorScene",
        "portrait",
        [TemplateBeatInput(1, 5.0, 0.0, source, None)],
        plan,
    )

    assert plan.beats[0].visual_kind == "taylor_error"
    assert "error_region = Polygon" in code
    assert "|R_3(x)|" in code
    validate_generated_python(code)


def test_heuristic_process_plan_uses_specific_colon_separated_labels():
    plan = build_heuristic_template_plan(
        "Sine derivatives",
        [
            TemplateBeatInput(
                1,
                5.0,
                0.0,
                "The sine derivative cycle is a four-step process: sin x, cos x, -sin x, -cos x.",
                None,
            )
        ],
    )

    assert plan.beats[0].visual_kind == "process"
    assert plan.beats[0].visual_labels == ["sin x", "cos x", "-sin x", "-cos x"]


def test_heuristic_integration_plan_keeps_method_context_across_camel_case_scene_name():
    beat_inputs = [
        TemplateBeatInput(
            1,
            6.0,
            0.0,
            r"Define \(I=\int_{0}^{\pi}x\sin x\,dx\) for integration by parts.",
            None,
        ),
        TemplateBeatInput(
            2,
            6.0,
            0.0,
            r"Choose \(u=x\), \(dv=\sin x\,dx\), \(du=dx\), and \(v=-\cos x\).",
            None,
        ),
        TemplateBeatInput(
            3,
            6.0,
            0.0,
            r"Substitute into \(I=uv-\int v\,du\) and simplify the boundary terms.",
            None,
        ),
        TemplateBeatInput(
            4,
            6.0,
            0.0,
            r"Conclude \(I=\pi\) after both definite terms are evaluated.",
            None,
        ),
    ]

    plan = build_heuristic_template_plan("IntegrationByPartsRenderGuard", beat_inputs)
    code = compile_template_scene("IntegrationByPartsRenderGuard", "portrait", beat_inputs, plan)

    assert [beat.heading for beat in plan.beats] == [
        "Set up the integral",
        "Choose u and dv",
        "Apply parts formula",
        "Final value",
    ]
    assert [beat.visual_kind for beat in plan.beats] == [
        "integration_by_parts",
        "integration_by_parts",
        "none",
        "none",
    ]
    assert "Key equation" not in code
    assert code.count("make_visual('integration_by_parts'") == 2
    assert "beat2_equation1 = safe_math" not in code
    assert "beat2_heading = fitted_text('Choose u and dv'" in code
    assert "beat3_heading = fitted_text('Apply parts formula', font_size=18" in code
    assert "beat3_equation1 = safe_math('I=uv-\\\\int v\\\\,du', font_size=64)" in code
    assert "beat3_diagram.scale_to_fit_height(config.frame_height * 0.55)" in code
    validate_generated_python(code)


def test_heuristic_template_plan_does_not_copy_operational_sentence():
    source = (
        "The constant linear and quadratic terms match the function value slope and curvature "
        "near the selected expansion point"
    )
    plan = build_heuristic_template_plan(
        "Taylor coefficients",
        [TemplateBeatInput(1, 5.0, 0.0, source, None)],
    )

    rendered_content = " ".join([plan.beats[0].heading, *plan.beats[0].lines]).strip()
    assert rendered_content == "Matched derivatives"
    assert source not in rendered_content
    assert plan.beats[0].visual_kind == "process"
    assert plan.beats[0].visual_labels == ["Value", "Slope", "Curvature"]


def test_heuristic_atwood_plan_constructs_diagram_instead_of_rendering_instruction():
    plan = build_heuristic_template_plan(
        "Atwood machine",
        [TemplateBeatInput(1, 4.0, 0.0, "Draw a pulley with m1 and m2; label tension T", None)],
    )
    code = compile_template_scene(
        "AtwoodScene",
        "portrait",
        [TemplateBeatInput(1, 4.0, 0.0, "Draw a pulley with m1 and m2; label tension T", None)],
        plan,
    )

    assert plan.beats[0].visual_kind == "atwood"
    assert plan.beats[0].heading == "Atwood machine forces"
    assert "if kind == 'atwood':" in code
    assert "Circle(radius=0.40" in code
    assert "Square(side_length=0.68" in code
    assert "Arrow(left_mass" in code
    assert "Draw a pulley with m1 and m2" not in code
    validate_generated_python(code)


def test_heuristic_vsepr_plan_builds_wedge_dash_models_with_angles_and_lone_pair():
    beat_inputs = [
        TemplateBeatInput(
            1,
            5.0,
            0.0,
            "Construct CH4 tetrahedral geometry with four bonding pairs, 0 lone pairs, and a 109.5 degree bond angle",
            None,
        ),
        TemplateBeatInput(
            2,
            5.0,
            0.0,
            "Construct NH3 trigonal pyramidal geometry with a lone pair and 107 degree bond angle",
            None,
        ),
        TemplateBeatInput(
            3,
            5.0,
            0.0,
            "Compare CH4 at 109.5 degrees with NH3 at 107 degrees and highlight the NH3 lone pair",
            None,
        ),
    ]
    plan = build_heuristic_template_plan("VSEPR NH3 CH4", beat_inputs)
    code = compile_template_scene("VSEPRScene", "portrait", beat_inputs, plan)

    assert [beat.visual_kind for beat in plan.beats] == ["vsepr_ch4", "vsepr_nh3", "vsepr_compare"]
    assert [beat.heading for beat in plan.beats] == [
        "CH4 tetrahedral geometry",
        "NH3 trigonal pyramidal geometry",
        "CH4 and NH3 compared",
    ]
    assert "wedge = Polygon" in code
    assert "dashed_bond = DashedLine" in code
    assert "center_symbol = 'C' if kind == 'vsepr_ch4' else 'N'" in code
    assert "109.5^\\circ" in code
    assert "107^\\circ" in code
    assert "lone_pair = VGroup(Dot" in code
    assert "kind in ('vsepr_ch4', 'vsepr_nh3')" in code
    assert "if kind == 'vsepr_compare':" in code
    assert "make_visual('vsepr_ch4'" in code
    assert "make_visual('vsepr_nh3'" in code
    assert "molecule_scale = 0.92 if portrait else 0.72" in code
    assert "arrange(DOWN if portrait else RIGHT" in code
    validate_generated_python(code)


def test_heuristic_vsepr_plan_recognizes_latex_formatted_molecular_formulas():
    beat_inputs = [
        TemplateBeatInput(1, 4.0, 0.0, r"Show tetrahedral $CH_4$ with a $109.5^\circ$ bond angle.", None),
        TemplateBeatInput(2, 4.0, 0.0, r"Show trigonal pyramidal $NH_3$ with a $107^\circ$ bond angle.", None),
        TemplateBeatInput(3, 4.0, 0.0, r"Compare $CH_4$ and $NH_3$ molecular geometries.", None),
    ]

    plan = build_heuristic_template_plan(r"VSEPR examples: $CH_4$ and $NH_3$", beat_inputs)

    assert [beat.visual_kind for beat in plan.beats] == ["vsepr_ch4", "vsepr_nh3", "vsepr_compare"]


def test_tetrahedral_dot_product_plan_keeps_structure_and_vector_math_separate():
    beat_inputs = [
        TemplateBeatInput(1, 4.0, 0.0, r"Show tetrahedral methane $CH_4$ and select two C-H bond vectors $\vec r_1$ and $\vec r_2$.", None),
        TemplateBeatInput(2, 4.0, 0.0, r"Use $\vec r_1=(1,1,1)$ and $\vec r_2=(1,-1,-1)$.", None),
        TemplateBeatInput(3, 4.0, 0.0, r"Compute $\vec r_1\cdot\vec r_2=-1$ and $|\vec r_1|=|\vec r_2|=\sqrt 3$.", None),
        TemplateBeatInput(4, 4.0, 0.0, r"Substitute into $\cos\theta=-\frac13$, so $\theta=\arccos(-\frac13)\approx109.5^\circ$.", None),
    ]

    plan = build_heuristic_template_plan(
        "Angle between C-H bonds in tetrahedral methane using vector dot product",
        beat_inputs,
    )
    code = compile_template_scene("TetrahedralDotProductScene", "portrait", beat_inputs, plan)

    assert [beat.visual_kind for beat in plan.beats] == ["vsepr_ch4", "dot_product_vectors", "dot_product_vectors", "dot_product_vectors"]
    assert [beat.heading for beat in plan.beats] == [
        "CH4 tetrahedral geometry",
        "Bond vectors",
        "Compute the dot product",
        "Solve for cos theta",
    ]
    assert "if kind == 'dot_product_vectors':" in code
    assert "r2_direction = LEFT / 3 + UP * (2 * np.sqrt(2) / 3)" in code
    assert "angle=np.arccos(-1 / 3)" in code
    assert "angle_arc.point_from_proportion(0.50) + UP * 0.30 + RIGHT * 0.16" in code
    validate_generated_python(code)


def test_mixed_vsepr_vector_plan_preserves_nh3_and_filters_prose_from_mathtex():
    beat_inputs = [
        TemplateBeatInput(1, 8.0, 0.0, "Construct methane CH4 tetrahedral geometry", None),
        TemplateBeatInput(2, 8.0, 0.0, "Show the 109.5 degree H-C-H bond angle", None),
        TemplateBeatInput(
            3,
            8.0,
            0.0,
            "Use two C-H bond vectors and their dot product to derive cos theta = -1/3",
            None,
        ),
        TemplateBeatInput(4, 8.0, 0.0, "Construct ammonia NH3 with a distinct lone pair", None),
        TemplateBeatInput(5, 8.0, 0.0, "Compare tetrahedral methane with trigonal pyramidal ammonia", None),
    ]
    plan = build_heuristic_template_plan("Tetrahedral vector-dot-product VSEPR", beat_inputs)

    assert [beat.visual_kind for beat in plan.beats] == [
        "vsepr_ch4",
        "vsepr_ch4",
        "dot_product_vectors",
        "vsepr_nh3",
        "vsepr_compare",
    ]
    assert plan.beats[2].equations == [r"\cos \theta = -1/3"]
    assert "bond vectors" not in plan.beats[2].equations[0]


def test_vsepr_topic_allows_geometry_visuals_from_topic_heuristics():
    plan = TemplateVideoPlan(
        title="CH4 and NH3 geometry",
        beats=[
            TemplateBeatPlan(beat_number=1, heading="Methane", visual_kind="vsepr_ch4"),
            TemplateBeatPlan(beat_number=2, heading="Compare shapes", visual_kind="geometry"),
            TemplateBeatPlan(beat_number=3, heading="Molecular transition", visual_kind="molecule"),
            TemplateBeatPlan(beat_number=4, heading="Ammonia", visual_kind="vsepr_nh3"),
        ],
    )

    validate_template_plan_topic_isolation("Compare CH4 tetrahedral and NH3 geometry", plan)


def test_video_semantic_palette_is_defined_once_and_reused_across_domains():
    beat_inputs = [
        TemplateBeatInput(1, 4.0, 0.0, 'Show force vector "F"', None),
        TemplateBeatInput(2, 4.0, 0.0, 'Show the same force vector "F" again', None),
        TemplateBeatInput(3, 4.0, 0.0, "Plot a function curve on axes", None),
        TemplateBeatInput(4, 4.0, 0.0, "Plot the function curve on axes again", None),
        TemplateBeatInput(5, 4.0, 0.0, "Construct CH4 tetrahedral geometry", None),
        TemplateBeatInput(6, 4.0, 0.0, "Construct NH3 trigonal pyramidal geometry with a lone pair", None),
    ]
    plan = build_heuristic_template_plan("Cross-domain palette", beat_inputs)
    code = compile_template_scene("SemanticPaletteScene", "portrait", beat_inputs, plan)

    assert [beat.visual_kind for beat in plan.beats[:2]] == ["vector", "vector"]

    expected_assignments = {
        "TITLE_COLOR": "TEAL_C",
        "PRIMARY_COLOR": "BLUE_C",
        "SECONDARY_COLOR": "WHITE",
        "BOND_COLOR": "RELATION_COLOR",
        "LONE_PAIR_COLOR": "SPECIAL_COLOR",
        "ANGLE_COLOR": "HIGHLIGHT_COLOR",
        "FORCE_COLOR": "PRIMARY_COLOR",
        "PRIMARY_CURVE_COLOR": "BLUE_C",
    }
    for role, color in expected_assignments.items():
        assert code.count(f"{role} = {color}") == 1
    assert "accent" not in code
    assert "color=FORCE_COLOR" in code
    assert "color=PRIMARY_CURVE_COLOR" in code
    assert "color=CENTRAL_ATOM_COLOR" in code
    assert "color=BOND_COLOR" in code
    assert "color=LONE_PAIR_COLOR" in code
    assert "color=ANGLE_COLOR" in code
    for number in range(1, 7):
        assert f"beat{number}_heading" in code
        assert f"beat{number}_visual = make_visual" in code
    validate_generated_python(code)
    validate_video_semantic_palette(code)

    changed_code = code.replace("BOND_COLOR = RELATION_COLOR", "BOND_COLOR = SPECIAL_COLOR", 1)
    try:
        validate_video_semantic_palette(changed_code)
    except SyntaxError as exc:
        assert "changed roles" in str(exc)
        assert "BOND_COLOR" in str(exc)
    else:
        raise AssertionError("Expected a changed cross-beat color assignment to fail validation")

    namespace: dict[str, object] = {}
    exec(code, namespace)
    namespace["safe_math"] = lambda value, font_size=42, color=WHITE: Text(
        value,
        font_size=min(font_size, 22),
        color=color,
    )
    make_visual = namespace["make_visual"]
    ch4_first = make_visual("vsepr_ch4", [], portrait=True)
    ch4_second = make_visual("vsepr_ch4", [], portrait=True)
    nh3 = make_visual("vsepr_nh3", [], portrait=True)
    force_first = make_visual("vector", ["F"], portrait=True)
    force_second = make_visual("vector", ["F"], portrait=True)
    curve_first = make_visual("axes", [], portrait=True)
    curve_second = make_visual("axes", [], portrait=True)

    assert ch4_first[1][0].get_color() == ch4_second[1][0].get_color() == namespace["CENTRAL_ATOM_COLOR"]
    assert ch4_first[0][1].get_color() == ch4_second[0][1].get_color() == namespace["BOND_COLOR"]
    assert ch4_first[3][0].get_color() == nh3[3][0].get_color() == namespace["ANGLE_COLOR"]
    assert nh3[2][0].get_color() == namespace["LONE_PAIR_COLOR"]
    assert force_first[1].get_color() == force_second[1].get_color() == namespace["FORCE_COLOR"]
    assert curve_first[1].get_color() == curve_second[1].get_color() == namespace["PRIMARY_CURVE_COLOR"]
