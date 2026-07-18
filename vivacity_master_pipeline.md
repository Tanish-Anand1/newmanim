# VIVACITY MASTER PIPELINE PROMPT
### Frontend request → script → active recall → Manim video
### Governs: FastAPI request handler, Gemma script-generation stage, Manim codegen stage.
### Depends on: vivacity_video_constitution.md (visual/pacing rules — this document does not repeat those, it feeds into them)

---

## 0. WHAT "UNDERSTANDABLE BY THE WEAKEST STUDENT" ACTUALLY MEANS HERE

Not defined as tone ("be friendly"). Defined as three testable requirements:
1. **Zero undefined jargon.** Every technical term is either defined in-video the first time it's used, or explicitly flagged as a prerequisite the student must already have (see §2).
2. **Every abstraction is preceded by a concrete number/example.** No formula appears before at least one worked concrete case using it.
3. **Every video has at least one recall checkpoint the student cannot pass by pattern-matching the immediately preceding sentence** — i.e., a question that requires them to apply the idea to a *new* instance, not repeat what was just said. This is the actual test of "did they understand it" vs "did they hear it."

If a generated video satisfies tone-friendliness but fails #2 or #3, it fails. Judge against the numbered list, not the vibe.

---

## 1. FRONTEND REQUEST SCHEMA

The frontend must capture more than "topic." Minimum required fields:

```json
{
  "topic": "string — specific concept, not a chapter name (e.g. 'finding critical points via first derivative' not 'calculus')",
  "exam_context": "JEE Main | JEE Advanced | NEET",
  "student_signal": {
    "self_rated_confidence": "1-5",
    "flagged_as_weak_topic": true/false,
    "prior_attempt_count": "integer, if this topic was shown before and failed recall"
  },
  "assumed_prerequisites": ["list of concepts the syllabus assumes but the student may not have — frontend should let the student flag any of these as 'not confident' via checkboxes, not free text"]
}
```

**Why this matters:** without `flagged_as_weak_topic` and `assumed_prerequisites`, the script-generation stage has no signal to decide how much scaffolding to add — it will default to exam-syllabus-standard density, which is exactly what already lost the weak student once. Precision without a difficulty signal produces the same video for a topper and a struggler.

---

## 2. PREREQUISITE GATE (runs before script generation, not optional)

Before generating the script, the pipeline must resolve: does this topic have prerequisites the student hasn't confirmed?

- If `assumed_prerequisites` contains anything the student marked "not confident" → the script generation prompt (§3) is instructed to insert a **30-45 second prerequisite refresher beat** at the start, using the concrete-example-first pattern, before touching the actual topic.
- If no prerequisite gaps are flagged → skip straight to the main sequence.

This single gate is the highest-leverage fix for "poorest student doesn't understand" — most comprehension failures in worked-example videos happen because the student is missing one prerequisite step, not because the main explanation was unclear.

---

## 3. SCRIPT-GENERATION PROMPT (system prompt for the LLM/Gemma stage)

See `app/vivacity_prompts.py` — `build_script_generation_system_prompt()`.

---

## 4. ACTIVE RECALL — EXACT MECHANICS

See `app/vivacity_prompts.py` — recall checkpoint and end-of-video question builders.

---

## 5. MANIM CODEGEN PROMPT

See `app/vivacity_prompts.py` — `build_manim_codegen_addon()`.

---

## 6. QA CHECKLIST

See `app/pipeline_qa.py` — `run_master_pipeline_qa()`.

---

**What this doesn't solve:** no prompt fixes a bad prerequisite gate if the frontend doesn't actually collect `assumed_prerequisites` per topic — that mapping is a content-authoring task (`data/topic_prerequisites.json`).
