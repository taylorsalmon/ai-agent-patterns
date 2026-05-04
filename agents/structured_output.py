"""
Structured output pattern: enforce a JSON schema on every Claude response.

The core idea: define your expected output schema once, validate every response
against it, and retry with an error message if validation fails. This makes
agent outputs deterministic enough to pass into downstream systems safely.

Production additions: schema versioning, logging validation failures,
alerting on sustained retry loops.
"""

import json
import os
from typing import Any
import anthropic

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

# Define your expected output schema. In production, load this from a versioned file.
TRIAGE_SCHEMA = {
    "required": ["category", "confidence", "urgency", "sentiment", "summary", "requires_human_review"],
    "types": {
        "category": str,
        "confidence": float,
        "urgency": str,
        "sentiment": str,
        "summary": str,
        "requires_human_review": bool,
    },
    "allowed_values": {
        "urgency": ["low", "normal", "high", "critical"],
        "sentiment": ["positive", "neutral", "negative", "frustrated"],
    },
}

SYSTEM_PROMPT = """You are a triage agent. Classify the inbound message and return valid JSON only.

Required fields:
- category (string): one of sales_enquiry, support_request, billing_question, feedback, spam, other
- confidence (float 0.0–1.0): your confidence in the classification
- urgency (string): one of low, normal, high, critical
- sentiment (string): one of positive, neutral, negative, frustrated
- summary (string): one sentence, max 20 words
- requires_human_review (boolean): true if confidence < 0.75 or situation is ambiguous

Return JSON only. No explanation."""


def validate(output: dict, schema: dict) -> list[str]:
    errors = []
    for field in schema["required"]:
        if field not in output:
            errors.append(f"Missing required field: {field}")
            continue
        expected_type = schema["types"].get(field)
        if expected_type and not isinstance(output[field], expected_type):
            errors.append(f"Field '{field}' must be {expected_type.__name__}, got {type(output[field]).__name__}")
        if field in schema.get("allowed_values", {}):
            allowed = schema["allowed_values"][field]
            if output[field] not in allowed:
                errors.append(f"Field '{field}' must be one of {allowed}, got '{output[field]}'")
    return errors


def call_with_schema(message: str, schema: dict, max_retries: int = 2) -> dict[str, Any]:
    messages = [{"role": "user", "content": message}]
    last_errors: list[str] = []

    for attempt in range(max_retries + 1):
        if attempt > 0:
            # Feed validation errors back so the model can self-correct
            messages.append({
                "role": "assistant",
                "content": "I'll fix those issues."
            })
            messages.append({
                "role": "user",
                "content": f"Your previous response had these issues:\n{chr(10).join(last_errors)}\n\nPlease return the corrected JSON."
            })

        response = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=512,
            system=SYSTEM_PROMPT,
            messages=messages,
        )
        text = response.content[0].text.strip()

        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as e:
            last_errors = [f"Response was not valid JSON: {e}"]
            print(f"[attempt {attempt + 1}] JSON parse error — retrying")
            messages.append({"role": "assistant", "content": text})
            continue

        last_errors = validate(parsed, schema)
        if not last_errors:
            return {"output": parsed, "attempts": attempt + 1}

        print(f"[attempt {attempt + 1}] Validation failed: {last_errors}")
        messages.append({"role": "assistant", "content": text})

    return {"output": None, "attempts": max_retries + 1, "errors": last_errors}


if __name__ == "__main__":
    test_message = (
        "Hi, I've been waiting three weeks for my order and it still hasn't arrived. "
        "This is completely unacceptable — I need this resolved immediately or I'm "
        "disputing the charge."
    )

    print(f"Input: {test_message}\n")
    result = call_with_schema(test_message, TRIAGE_SCHEMA)

    if result["output"]:
        print(f"Output (after {result['attempts']} attempt(s)):")
        print(json.dumps(result["output"], indent=2))
    else:
        print(f"Failed after {result['attempts']} attempts: {result['errors']}")
