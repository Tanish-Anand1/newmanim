# Vivacity Video Constitution

Visual layout, pacing, and on-screen discipline rules for all Manim scenes.
Referenced by script generation, template planning, craft planning, and legacy codegen.

---

## §1 Layout Engine Architectural Rules

### §1.1 Rigid Multi-Zone Split
- Divide the screen viewport into an upper 45% "Text Safe-Zone" and a lower 55% "Geometric/Physics Workspace" (especially in Portrait mode).
- The origin of your coordinate tracking grid or 3D axes must be shifted downward into the absolute center of the lower workspace. Never let the camera default to the screen origin (0,0,0) if it causes mathematical geometry to cross into the upper text field.
- **Landscape partitioning**:
  - **Anchor zone** (graph/diagram): left half of the frame.
  - **Equation zone**: right half of the frame.
  - Keep the diagram visible in the anchor/geometric zone; confine all equation work to the equation/safe-zone.

### §1.2 Zero Absolute Text Coordinates
- Completely ban the use of hardcoded coordinates or manual spatial offsets (e.g., `UP * 2.5`) for text arrangement. 
- All text blocks—including titles, subtitles, live variable readouts, and mathematical formulas—must be compiled inside a single parent `VGroup`.

### §1.3 Dynamic Relative Stacking
- Arrange elements within the parent text block strictly using relative alignment methods (such as `.next_to()` with an explicit buffer direction or `VGroup.arrange()`).
- Enforce a minimum safety padding buffer of 0.4 units between adjacent text elements.
- When text values or formula terms update dynamically mid-scene, trigger an explicit layout update function to recalculate the entire block's bounding boxes. This ensures elements automatically scale or shift to accommodate length changes without overlapping neighboring text layers.

### §1.4 Explicit Z-Index and Separation
- If utilizing 3D objects or trails, restrict their maximum bounding boxes so they mathematically cannot clip the boundaries of the text safe-zone.
- Group text and background overlays on a higher rendering layer than geometric plots to guarantee absolute readability. (For ThreeDScene, use `add_fixed_in_frame_mobjects()` for text).

### §1.5 Swap rule (recall checkpoint placement)
The `[RECALL_CHECKPOINT]` pause screen is **not** a full-frame interstitial. It continues the same persistent layout:
- Place the new-instance numbers **where the STEP 1 example numbers were** in the equation zone.
- Render "Pause and try this" + countdown timer in the geometric zone (or above the equation zone if no diagram).
- After the pause, reveal the worked solution in the equation zone using the same concrete-first pacing as the main lesson.

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
- **Spacing buffers**: As mandated in §1.3, always utilize strict relative layout stacking (e.g. `VGroup.arrange(DOWN, buff=0.4)`). Ban the use of absolute spacing like `UP * 2`.

---

## §4 Attached labels and morphs

- Labels attached with `.next_to(parent, ...)` must be in the **same VGroup** as the parent before any transition.
- When storyboard says "morphs into" / "becomes", use `ReplacementTransform` — never stack duplicates.
- Build each on-screen element with one continuous animation sequence; no near-duplicate recreation.
