"""
MCP integration pattern: Claude with declared tools that call external services.

Demonstrates the tool use loop:
  1. Send message + tool definitions to Claude
  2. Claude decides which tool(s) to call and with what arguments
  3. Execute the tool locally, return the result
  4. Claude uses the result to continue reasoning
  5. Repeat until Claude returns a final text response (no more tool calls)

This is the foundation for MCP-connected agents. In production, replace the
stub tool functions with real API calls to your CRM, calendar, email service, etc.
"""

import json
import os
from datetime import datetime
import anthropic

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

# Tool definitions — these are what Claude sees. Keep them precise.
TOOLS = [
    {
        "name": "get_customer",
        "description": "Look up a customer record by email address. Returns name, account status, and recent order history.",
        "input_schema": {
            "type": "object",
            "properties": {
                "email": {
                    "type": "string",
                    "description": "Customer email address"
                }
            },
            "required": ["email"]
        }
    },
    {
        "name": "create_crm_task",
        "description": "Create a follow-up task in the CRM assigned to the support team.",
        "input_schema": {
            "type": "object",
            "properties": {
                "customer_email": {"type": "string"},
                "title": {"type": "string", "description": "Short task title"},
                "description": {"type": "string"},
                "urgency": {"type": "string", "enum": ["low", "normal", "high", "critical"]},
                "due_date": {"type": "string", "description": "ISO 8601 date, e.g. 2025-08-20"}
            },
            "required": ["customer_email", "title", "urgency"]
        }
    },
    {
        "name": "send_acknowledgement_email",
        "description": "Send an automated acknowledgement email to the customer.",
        "input_schema": {
            "type": "object",
            "properties": {
                "to_email": {"type": "string"},
                "customer_name": {"type": "string"},
                "message_summary": {"type": "string", "description": "One sentence describing what was received"}
            },
            "required": ["to_email", "customer_name", "message_summary"]
        }
    }
]

SYSTEM_PROMPT = """You are a customer support operations agent. When you receive a support enquiry:
1. Look up the customer record
2. Create a CRM task for the support team with appropriate urgency
3. Send an acknowledgement email to the customer
4. Report what you did

Use the available tools. Be concise in your final report."""


# --- Stub tool implementations ---
# Replace these with real API calls in production.

def get_customer(email: str) -> dict:
    return {
        "found": True,
        "name": "Alex Chen",
        "email": email,
        "account_status": "active",
        "customer_since": "2023-03-15",
        "recent_orders": [
            {"order_id": "ORD-8821", "date": "2025-08-01", "status": "shipped", "total": 149.00}
        ]
    }


def create_crm_task(customer_email: str, title: str, urgency: str,
                    description: str = "", due_date: str = "") -> dict:
    task_id = f"TASK-{abs(hash(customer_email + title)) % 10000:04d}"
    return {"task_id": task_id, "status": "created", "assigned_to": "support_team"}


def send_acknowledgement_email(to_email: str, customer_name: str, message_summary: str) -> dict:
    print(f"  [email stub] Sending to {to_email}: acknowledged '{message_summary}'")
    return {"status": "sent", "message_id": f"msg_{abs(hash(to_email)):08x}"}


TOOL_FUNCTIONS = {
    "get_customer": get_customer,
    "create_crm_task": create_crm_task,
    "send_acknowledgement_email": send_acknowledgement_email,
}


def execute_tool(name: str, inputs: dict) -> str:
    fn = TOOL_FUNCTIONS.get(name)
    if not fn:
        return json.dumps({"error": f"Unknown tool: {name}"})
    result = fn(**inputs)
    return json.dumps(result)


def run_agent(enquiry: str) -> str:
    """Run the agent until it produces a final text response."""
    messages = [{"role": "user", "content": enquiry}]

    while True:
        response = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )

        if response.stop_reason == "end_turn":
            # Final response — extract text
            for block in response.content:
                if hasattr(block, "text"):
                    return block.text

        if response.stop_reason == "tool_use":
            # Append Claude's response (which includes tool_use blocks)
            messages.append({"role": "assistant", "content": response.content})

            # Execute each tool call and collect results
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    print(f"  [tool] {block.name}({json.dumps(block.input)})")
                    result = execute_tool(block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })

            messages.append({"role": "user", "content": tool_results})
            continue

        # Unexpected stop reason
        return f"Unexpected stop_reason: {response.stop_reason}"


if __name__ == "__main__":
    enquiry = (
        "Hi, I placed order ORD-8821 two weeks ago and it still hasn't arrived. "
        "My email is alex.chen@example.com. Can someone help? I need it urgently."
    )

    print(f"Enquiry: {enquiry}\n")
    print("Agent running...\n")
    result = run_agent(enquiry)
    print(f"\nAgent report:\n{result}")
