# Vivacity Video Constitution

Visual layout, pacing, and on-screen discipline rules for all Manim scenes.
Referenced by script generation, template planning, craft planning, and legacy codegen.

---

## §1 Layout

### §1.1 Persistent split-screen (anchor / equation zones)

When a graph or diagram is introduced and equations are derived from it in later beats:

- Do **not** `FadeOut` the diagram to make room for equations.
- Partition the frame at the start of the sequence:
  - **Portrait partitioning**:
    - **Upper 45% (UP * 1.5 to UP * 3.0)**: Designated Math & Text Safe-Zone. All formulas, titles, and step-by-step evaluations must stay here.
    - **Lower 55% (DOWN * 0.5 to DOWN * 3.0)**: Designated Geometric Workspace. All Axes, coordinate grids, vectors, and graphs must be locked here.
  - **Landscape partitioning**:
    - **Anchor zone** (graph/diagram): left half of the frame.
    - **Equation zone**: right half of the frame.
- Keep the diagram visible in the anchor/geometric zone; confine all equation work to the equation/safe-zone.
- Equations morph via `ReplacementTransform` in the equation zone while the diagram stays visible.
- Remove the diagram only when transitioning to a completely different section.

### §1.2 Portrait padding

For portrait (1080×1920):

- Headers/titles: `.to_edge(UP, buff=0.5)` minimum from top.
- At least 0.4 units clearance below headers before content.
- Use slightly more generous spacing than landscape — narrow width makes tight layouts feel cramped.

### §1.3 Swap rule (recall checkpoint placement)

The `[RECALL_CHECKPOINT]` pause screen is **not** a full-frame interstitial. It continues the same persistent layout:

- Place the new-instance numbers **where the STEP 1 example numbers were** in the equation zone.
- Render "Pause and try this" + countdown timer in the anchor zone (or above the equation zone if no diagram).
- After the pause, reveal the worked solution in the equation zone using the same concrete-first pacing as the main lesson.

### §1.4 Action-title caption clearance

Short action captions ("Solve for the center", "Set up the area") must sit above the equation zone with guaranteed clearance — use `.next_to(equation_zone, UP, buff=0.3)` or equivalent. Never overlap fractions or exponents.

---

## §2 Pacing

### §2.1 Beat duration

- Each beat: **3–8 seconds**.
- One idea per beat; at most **three new semantic elements** per beat.
- Hold the completed visual briefly before moving on.
- Split dense content into sequential sub-beats rather than shrinking text below readable size.

### §2.2 Sentence length (voiceover)

- Prefer sentences under **20 words**.
- No "obviously", "simply", "just", or "clearly" in narration.

### §2.3 Recall checkpoint timing

- Pause countdown: **5–8 seconds** on screen.
- Post-pause solution walkthrough: compressed reinforcement, not a second full lesson.

### §2.4 Complex equation reveal

- Do **not** use `Write()` on complex `MathTex` with nested fractions, exponents, or integrals.
- Use `FadeIn(mobject, scale=1.05)` or plain `FadeIn()` instead.

### §2.5 Double-exposure prevention

- Never `Write()` new text while old text occupies the same slot.
- Use `ReplacementTransform(old, new)` for equation morphs, or explicit `FadeOut(old)` then `Write(new)`.

### §2.6 Timing delays

- Every major animation phase, transition, or structural state change MUST be followed by an explicit breathing window. Enforce a strict delay of exactly 1.25 to 1.5 seconds using `self.wait(1.25)` or `self.wait(1.5)`. No exceptions.

---

## §3 Color and composition

- Define a video-level semantic palette **once** above the Scene class.
- Reuse the same color for the same semantic role across all beats.
- Call `avoid_overlap()` after placing every `Text`, `Tex`, or `MathTex` mobject.
- Minimum **0.3** Manim units buffer between simultaneously visible mobjects.
- **Object scaling**: Never allow long text lines. Scale all multi-term equations (fractions, matrices, summations) downward using `.scale(0.75)` or `.scale(0.8)` to prevent edge clipping.
- **Spacing buffers**: Always utilize strict vertical layout tracking. Use `VGroup` with an explicit vertical buffer (`buff=0.35` to `0.45`) or pin text explicitly to edges using `to_edge(UP, buff=0.5)`.

---

## §4 Attached labels and morphs

- Labels attached with `.next_to(parent, ...)` must be in the **same VGroup** as the parent before any transition.
- When storyboard says "morphs into" / "becomes", use `ReplacementTransform` — never stack duplicates.
- Build each on-screen element with one continuous animation sequence; no near-duplicate recreation.
