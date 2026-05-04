"""
Multi-agent pipeline: orchestrator delegates to specialist agents.

Pattern:
  1. Orchestrator receives a task and produces a structured plan
  2. Each step in the plan is executed by the appropriate specialist
  3. Outputs are collected in a shared context and passed to dependent steps
  4. Final output is returned to the caller

This is a minimal, runnable demonstration — not production-complete.
Production additions: async execution for parallel steps, retry logic,
persistent context store, observability hooks.
"""

import json
import os
from typing import Any
import anthropic

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

SPECIALISTS: dict[str, str] = {
    "research_agent": (
        "You are a research agent. Given a topic and focus areas, produce a concise "
        "factual summary. Return JSON: {\"findings\": [\"...\"], \"sources_consulted\": int, "
        "\"confidence\": float}"
    ),
    "drafting_agent": (
        "You are a drafting agent. Given structured research inputs, write a clear, "
        "professional document for the specified audience. Return JSON: "
        "{\"document\": \"...\", \"word_count\": int}"
    ),
    "validation_agent": (
        "You are a validation agent. Check the provided content for factual accuracy, "
        "completeness, and clarity. Return JSON: {\"passed\": bool, \"issues\": [\"...\"], "
        "\"suggestions\": [\"...\"]}"
    ),
}

ORCHESTRATOR_PROMPT = """
You are an orchestrator agent. Break the user's task into subtasks and return a structured plan.

Available agents: {agents}

Return valid JSON only:
{{
  "task_summary": "string",
  "plan": [
    {{
      "step": 1,
      "agent": "agent_name",
      "description": "what this agent should do",
      "inputs": {{"key": "value or step_N.output.field reference"}},
      "depends_on": []
    }}
  ],
  "final_output_from_step": 1
}}
""".format(agents=", ".join(SPECIALISTS.keys()))


def resolve_inputs(inputs: dict, context: dict) -> dict:
    """Replace step_N.output.field references with actual values from context."""
    resolved = {}
    for key, val in inputs.items():
        if isinstance(val, str) and val.startswith("step_"):
            parts = val.split(".")  # e.g. ["step_1", "output", "findings"]
            step_key = parts[0]
            nested = context.get(step_key, {})
            for part in parts[1:]:
                nested = nested.get(part, nested) if isinstance(nested, dict) else nested
            resolved[key] = nested
        else:
            resolved[key] = val
    return resolved


def call_specialist(agent_name: str, description: str, inputs: dict) -> dict:
    system = SPECIALISTS[agent_name]
    user_message = f"Task: {description}\n\nInputs:\n{json.dumps(inputs, indent=2)}"

    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=1024,
        system=system,
        messages=[{"role": "user", "content": user_message}],
    )
    text = response.content[0].text
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"raw_output": text, "parse_error": True}


def run_pipeline(task: str) -> Any:
    # Step 1: orchestrator produces a plan
    print(f"\n[orchestrator] Planning task: {task}")
    plan_response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=1024,
        system=ORCHESTRATOR_PROMPT,
        messages=[{"role": "user", "content": task}],
    )
    plan = json.loads(plan_response.content[0].text)
    print(f"[orchestrator] Plan: {plan['task_summary']} ({len(plan['plan'])} steps)")

    # Step 2: execute plan steps in order (sequential for simplicity)
    context: dict[str, Any] = {}
    for step in plan["plan"]:
        step_key = f"step_{step['step']}"
        resolved = resolve_inputs(step["inputs"], context)
        print(f"[{step['agent']}] Executing step {step['step']}: {step['description']}")
        output = call_specialist(step["agent"], step["description"], resolved)
        context[step_key] = {"output": output}
        print(f"[{step['agent']}] Done")

    # Step 3: return the designated final output
    final_step_key = f"step_{plan['final_output_from_step']}"
    return context[final_step_key]["output"]


if __name__ == "__main__":
    result = run_pipeline(
        "Research the three main benefits of multi-agent AI systems and write "
        "a two-paragraph executive briefing."
    )
    print("\n=== Final Output ===")
    print(json.dumps(result, indent=2))
