"""
Eval harness: run a prompt against a labelled dataset and measure accuracy.

Use this before promoting a new prompt version to production.
Target: ≥95% field-level accuracy across your eval set.

Usage:
  python eval_harness.py --cases evals/triage/ --verbose

Eval case format (JSON file):
  {
    "input": "the message to classify",
    "expected": {
      "category": "support_request",
      "urgency": "high"
    },
    "description": "frustrated customer, delayed order"
  }

Only fields listed in "expected" are evaluated — you don't need to specify every field.
"""

import argparse
import json
import os
from pathlib import Path
from typing import Any
import anthropic

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

SYSTEM_PROMPT = """You are a triage agent. Classify the message and return JSON only.
Fields: category (sales_enquiry|support_request|billing_question|feedback|spam|other),
confidence (float), urgency (low|normal|high|critical),
sentiment (positive|neutral|negative|frustrated), summary (string, max 20 words),
requires_human_review (boolean)."""


def classify(message: str) -> dict[str, Any]:
    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=512,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": message}],
    )
    return json.loads(response.content[0].text)


def evaluate_case(case: dict, verbose: bool) -> dict[str, Any]:
    predicted = classify(case["input"])
    expected = case["expected"]

    field_results = {}
    for field, expected_val in expected.items():
        predicted_val = predicted.get(field)
        correct = predicted_val == expected_val
        field_results[field] = {
            "correct": correct,
            "expected": expected_val,
            "predicted": predicted_val,
        }

    all_correct = all(r["correct"] for r in field_results.values())

    if verbose:
        status = "PASS" if all_correct else "FAIL"
        print(f"  [{status}] {case.get('description', case['input'][:60])}")
        for field, result in field_results.items():
            if not result["correct"]:
                print(f"         {field}: expected={result['expected']!r}, got={result['predicted']!r}")

    return {"passed": all_correct, "fields": field_results}


def run_evals(cases_dir: str, verbose: bool) -> None:
    cases_path = Path(cases_dir)
    case_files = sorted(cases_path.glob("*.json"))

    if not case_files:
        print(f"No eval cases found in {cases_dir}")
        return

    print(f"Running {len(case_files)} eval cases from {cases_dir}\n")

    results = []
    for path in case_files:
        case = json.loads(path.read_text())
        result = evaluate_case(case, verbose)
        results.append(result)

    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    accuracy = passed / total * 100

    # Field-level accuracy
    field_totals: dict[str, list[bool]] = {}
    for result in results:
        for field, fr in result["fields"].items():
            field_totals.setdefault(field, []).append(fr["correct"])

    print(f"\n{'='*50}")
    print(f"Results: {passed}/{total} cases passed ({accuracy:.1f}%)")
    print(f"\nField-level accuracy:")
    for field, outcomes in field_totals.items():
        field_acc = sum(outcomes) / len(outcomes) * 100
        print(f"  {field:<30} {field_acc:.1f}%")

    target = 95.0
    print(f"\n{'PASS' if accuracy >= target else 'FAIL'} (target: {target}%)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run prompt evals against a labelled dataset")
    parser.add_argument("--cases", required=True, help="Directory containing eval case JSON files")
    parser.add_argument("--verbose", action="store_true", help="Print per-case results")
    args = parser.parse_args()
    run_evals(args.cases, args.verbose)
