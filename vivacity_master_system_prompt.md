# Vivacity Master System Prompt

This is the canonical rule set for every generated Vivacity video. It
supersedes older per-round prompt fragments when they conflict.

## Technical Foundation

- Use Manim Community Edition only; never use ManimGL syntax.
- Every scene subclasses `VivacityScene`, never raw `Scene`.
- Use the shared palette/constants file. Do not introduce inline colors.
- Render at 60 fps with CFR export. Target 1920x1080 landscape or 1080x1920
  portrait and verify `r_frame_rate == avg_frame_rate` with ffprobe.
- Every generated scene must pass `test_scene_compliance.py` before delivery:
  base class, transform safety, tracker-label safety, and overlap safety.

## Teaching Sequence

For each scene/chapter, follow this order:

1. Concrete instance with one specific number or shape.
2. Guided noticing while varying one part in plain language.
3. General claim in words, before notation.
4. Formula introduced term by term and mapped to the example.
5. Edge case or explanation of why the result works.
6. Active recall: a genuinely new numerical instance, pause and predict,
   then reveal the solution.

## Layout and Motion

- Keep the main visual in a persistent anchor zone. Transform it; do not
  destroy and rebuild it within one topic.
- Keep equations/text in a separate non-overlapping zone. Enforce
  `_check_overlap` for every mobject placement.
- Use `TransformMatchingTex` for structurally related equations. Use
  FadeOut then FadeIn only for genuinely unrelated content. Never use raw
  Transform, ReplacementTransform, or `.animate` on mismatched text.
- Hold each newly introduced equation or diagram legibly for at least two
  seconds before transforming it.
- Every beat must retain a subtle, low-opacity animated anchor element during
  holds; never use distracting motion or decorative effects.
- Use one complete Tex/MathTex string or an arranged VGroup. Never position
  text character by character.
- Call `fit_to_frame()` after text/equation construction and again after
  every `.next_to()` or position change. Enforce `ensure_contrast()` using
  shared palette constants.

## Dynamic State

- Every changing value uses `ValueTracker` plus `always_redraw` or
  `live_value_label`; never leave a static label beside a changing tracker.
- Growing histograms, rectangle collections, and similar accumulations use
  `always_redraw` and one batched animation per discrete step, never one
  `self.play` call per element.

## Portrait Safe Zone

For new portrait videos, clamp all content to:

```python
PORTRAIT_SAFE_ZONE = {
    "right_margin_pct": 0.16,
    "bottom_margin_pct": 0.14,
    "top_margin_pct": 0.04,
}
```

Apply this to titles, text, anchors, and characters through the base-class
fit and overlap helpers. Existing landscape videos are not retroactively
changed unless portrait output is explicitly requested.

## Multi-Scene Delivery

- Target 15-22 seconds per chapter, approximately 18 seconds.
- Use separate `VivacityScene` subclasses and import the same shared
  constants file in every chapter.
- Stitch chapters with approximately 0.6-second `xfade` video and
  `acrossfade` audio. Never hard-concatenate chapters.
- Compute offsets from actual ffprobe durations, never planned durations.
- Reject mismatched resolution, fps, or codec before stitching. Verify
  boundary frames show a blend and verify no audio pop, gap, or dead air.

## Recall and Mascot

- Use the existing prerequisite gate and recall pipeline. Recall instances
  must use genuinely different numbers and show a pause/countdown before the
  reveal. Persist the end-of-video retrieval response through the existing
  endpoint and follow-up task.
- When used, `VivacityCharacter` is the original project character with its
  defined expression states. It occupies its own overlap-checked zone.

## Delivery Evidence

Do not consider a video complete from source inspection alone. Run the
production test suite in the production environment, extract and inspect
real frames/timestamps, and run ffprobe on the final file. Every new gate
must be sanity-tested against a deliberately broken fixture and the fixture
removed afterward. If execution is blocked, report the exact error instead
of predicting success.

Do not expand this prompt into prerequisite authoring, recall recap logic,
student-signal frontend work, or unit-economics work.
