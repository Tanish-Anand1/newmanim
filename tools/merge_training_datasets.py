"""
Consolidates all three training data sources into one JSONL file ready to
paste into the Kaggle fine-tuning notebook's Cell 4.

Sources:
  1. bespokelabs/bespoke-manim (1,000 rows, pre-verified via Docker render)
  2. generaleoley/manim-codegen (filtered - drops query/code mismatches)
  3. Your own JEE-specific pairs (`data/jee_training_pairs.jsonl`, from
     `tools/collect_jee_training_data.py`)

Run this after the collector has produced the JEE pairs file.

USAGE:
    python tools/merge_training_datasets.py
"""

import json
import re
from pathlib import Path
from datasets import load_dataset

PROJECT_DIR = Path(__file__).resolve().parents[1]

SYSTEM_PROMPT = (
    "You write Manim Community Edition code only. Only use valid Manim CE "
    "color constants (WHITE, BLACK, RED, GREEN, BLUE, YELLOW, ORANGE, PURPLE, "
    "PINK, TEAL, GRAY, GREY, MAROON, GOLD, and _A/_B/_C/_D/_E shade variants) - "
    "never invent compound color names. Output ONLY Python code, no explanation."
)

OUTPUT_FILE = PROJECT_DIR / "data" / "combined_manim_training_data.jsonl"
JEE_PAIRS_FILE = PROJECT_DIR / "data" / "jee_training_pairs.jsonl"


def extract_keywords(text):
    stopwords = {"the", "a", "an", "and", "or", "with", "to", "of", "in", "on",
                 "then", "that", "this", "for", "show", "create", "animate",
                 "scene", "manim", "animation"}
    words = re.findall(r"[a-zA-Z]{4,}", text.lower())
    return set(w for w in words if w not in stopwords)


def code_contains_keywords(code, keywords, min_matches=2):
    code_lower = code.lower()
    return sum(1 for kw in keywords if kw in code_lower) >= min_matches


def format_pair(system, user, assistant):
    return {"text": f"<system>{system}</system>\n<user>{user}</user>\n<assistant>{assistant}</assistant>"}


def load_bespoke():
    print("Loading bespoke-manim...")
    ds = load_dataset("bespokelabs/bespoke-manim", split="train")
    print(f"  {len(ds)} rows found. First row fields: {list(ds[0].keys())}")

    pairs = []
    skipped_errors = 0
    for row in ds:
        # Actual schema confirmed: question, narration, python_code (not
        # the guessed script/code/manim_code names from before)
        error_field = row.get("error")
        if error_field:  # non-empty error field means this row's generation/render failed
            skipped_errors += 1
            continue

        question = row.get("question", "")
        narration = row.get("narration", "")
        code = row.get("python_code", "")
        if question and code:
            user_text = f"{question}"
            if narration:
                user_text += f"\n\nNarration: {narration}"
            pairs.append(format_pair(SYSTEM_PROMPT, user_text, code))
    print(f"  Formatted {len(pairs)} bespoke-manim pairs "
          f"(skipped {skipped_errors} rows with a non-empty error field)")
    return pairs


def load_generaleoley_filtered():
    print("Loading and filtering generaleoley/manim-codegen...")
    ds = load_dataset("generaleoley/manim-codegen", split="train")
    print(f"  {len(ds)} rows found. First row fields: {list(ds[0].keys())}")
    print("  >>> VERIFY these field names match the .get() calls below before trusting output <<<")

    pairs = []
    dropped = 0
    for row in ds:
        query = row.get("query") or row.get("prompt") or row.get("instruction")
        code = row.get("answer") or row.get("code") or row.get("output")
        if not query or not code:
            dropped += 1
            continue
        keywords = extract_keywords(query)
        if len(keywords) >= 2 and not code_contains_keywords(code, keywords, min_matches=2):
            dropped += 1
            continue
        pairs.append(format_pair(SYSTEM_PROMPT, query, code))
    print(f"  Kept {len(pairs)} pairs, dropped {dropped} likely-mismatched/malformed pairs")
    return pairs


def load_jee_pairs():
    if not JEE_PAIRS_FILE.exists():
        print(f"WARNING: {JEE_PAIRS_FILE} not found. Run collect_jee_training_data.py first "
              "if you want JEE-specific examples included. Continuing without them for now.")
        return []

    pairs = []
    with open(JEE_PAIRS_FILE, "r", encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            user_text = f"Explain and animate: {row['topic']} (audience: JEE/NEET aspirants)"
            pairs.append(format_pair(SYSTEM_PROMPT, user_text, row["code"]))
    print(f"Loaded {len(pairs)} JEE-specific pairs from your own pipeline")
    return pairs


def main():
    bespoke_pairs = load_bespoke()
    generaleoley_pairs = load_generaleoley_filtered()
    jee_pairs = load_jee_pairs()

    all_pairs = bespoke_pairs + generaleoley_pairs + jee_pairs

    print(f"\n--- SUMMARY ---")
    print(f"bespoke-manim:        {len(bespoke_pairs)}")
    print(f"generaleoley (filtered): {len(generaleoley_pairs)}")
    print(f"your JEE pairs:        {len(jee_pairs)}")
    print(f"TOTAL:                 {len(all_pairs)}")

    if len(all_pairs) < 500:
        print(f"\nWARNING: {len(all_pairs)} total pairs is below the ~500 minimum "
              "recommended before fine-tuning. Consider running more topics through "
              "collect_jee_training_data.py before proceeding.")

    if len(jee_pairs) == 0:
        print("\nWARNING: zero JEE-specific pairs included. This training run will "
              "produce a model with NO domain-specific improvement over the base "
              "public datasets - run collect_jee_training_data.py first if JEE/NEET "
              "performance is the actual goal.")

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        for pair in all_pairs:
            f.write(json.dumps(pair) + "\n")

    print(f"\nWrote combined dataset to {OUTPUT_FILE}")
    print("Upload this file to Kaggle as a dataset, then load it directly in Cell 4 "
          "of the fine-tuning notebook INSTEAD OF separately loading bespoke-manim "
          "and generaleoley there - this file already contains both, pre-merged and "
          "pre-filtered, plus your own JEE examples.")


if __name__ == "__main__":
    main()
