# Prompt Engineering Guide

Practical rules I follow when writing and maintaining system prompts for production agents.

---

## The Basics

### 1. Lead with role, not instructions

The first sentence of every system prompt defines who the agent is. Claude responds to identity — an agent that knows it's a "triage agent optimising for accurate routing" will behave more consistently than one given a list of instructions with no identity anchor.

```
# Good
You are a triage agent. Your job is to classify inbound enquiries accurately 
so they reach the right team without delay.

# Worse
Follow these steps: 1. Read the message. 2. Classify it into one of these categories...
```

### 2. Declare constraints explicitly

Don't assume the model will infer what it shouldn't do. State it.

```
## Constraints
- Do not attempt to answer the customer's question — only classify
- Do not guess at entities not present in the message
- If confidence < 0.7, set requires_human_review to true
```

### 3. Specify output format and give an example

Vague format instructions produce inconsistent outputs. Include the exact JSON schema and at least one complete example.

```
## Output format
Return valid JSON only. No preamble, no explanation.

{
  "category": "support_request",
  "confidence": 0.94,
  ...
}
```

### 4. Define every enumerated value

If a field has allowed values, list them. If a value has a specific meaning, define it.

```
## Urgency levels
- critical: legal threat, chargeback, safety issue
- high: time-sensitive; customer clearly frustrated; order significantly delayed
- normal: standard enquiry, no time pressure
- low: general question, feedback, compliment
```

---

## Evaluating Prompts

A prompt isn't ready for production until it's been evaluated against labelled examples.

**Minimum eval set:** 20 cases covering:
- 3–4 normal cases in each category
- Edge cases (ambiguous category, missing information, multiple issues in one message)
- Adversarial cases (very short messages, messages in other languages, spam)
- Known failure modes from production (if any)

**What to measure:**
- Category accuracy (exact match)
- Urgency accuracy (exact match)
- Confidence calibration (is confidence 0.9 actually correct 90% of the time?)
- Requires-human-review precision (how often does flagging = actually needs review?)

**Target before shipping:** ≥95% accuracy on evaluated fields.

---

## Updating Prompts Safely

Treat prompt changes like code changes:

1. **Version the prompt** — keep old versions; never overwrite in place
2. **Run the full eval set** — not just the cases that motivated the change
3. **Check for regressions** — a change that fixes 3 edge cases but breaks 5 normal cases is a net loss
4. **Document the change** — what changed, why, what the eval result was

```
## Changelog
v1.2 — 2025-08-10
  Added examples for billing vs refund distinction
  Eval accuracy: 96.3% (up from 94.8%)
  Motivated by: 12 misclassifications in July production data
```

---

## Common Failure Modes

### Hallucinated entities

The model extracts data that isn't in the source text. Usually happens when the prompt doesn't explicitly forbid it.

Fix: add `"Do not infer entities not present in the source text"` to constraints. Validate extracted entities against a set of plausible patterns (email regex, order ID format, etc.) in downstream code.

---

### Confidence miscalibration

The model returns high confidence on cases it's actually wrong about, or low confidence on easy cases.

Fix: add calibration examples to the prompt — show what a 0.95 confidence case looks like vs. a 0.6 confidence case. Measure calibration in evals: group predictions by confidence bucket and check accuracy within each bucket.

---

### Category drift under distribution shift

Classification accuracy degrades as inbound enquiry types change over time (new products, seasonal patterns, policy changes).

Fix: monitor the low-confidence rate in production. Spikes in `requires_human_review` are an early signal. Pull recent misclassified cases, identify the new pattern, and add examples to the prompt.

---

### Format non-compliance

The model returns explanation text before or after the JSON, or wraps it in markdown code fences.

Fix: be explicit — `"Return valid JSON only. No explanation, no preamble, no markdown."` Add a JSON parse step in your pipeline that strips code fences before parsing. If it fails, retry once with the parse error as feedback.

---

## Token Efficiency

Token cost = prompt tokens + completion tokens × price per token × call volume.

Rules I follow:
- Keep system prompts under 800 tokens for classification/extraction tasks — beyond that, evaluate whether you actually need the extra context
- For document processing, split large documents and summarise chunks rather than feeding everything in one call
- Use `max_tokens` conservatively — for classification returning a 200-token JSON object, `max_tokens: 512` is plenty
- Cache system prompts when calling the same prompt repeatedly — Anthropic's prompt caching reduces cost significantly at volume
