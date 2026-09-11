"""Agent loop for OpenAI-style function calling in sendit workflow."""

import json
from typing import Any

from .tool_handlers import SenditToolHandlers


def _assistant_message_to_dict(message: Any) -> dict[str, Any]:
    """Convert SDK assistant message object into serializable dict.

    Args:
        message: Assistant message object returned by OpenAI-compatible SDK.

    Returns:
        dict[str, Any]: Dict with `role`, `content`, and normalized `tool_calls`.
    """

    payload: dict[str, Any] = {"role": "assistant", "content": message.content or ""}
    if getattr(message, "tool_calls", None):
        payload["tool_calls"] = [
            {
                "id": call.id,
                "type": "function",
                "function": {
                    "name": call.function.name,
                    "arguments": call.function.arguments,
                },
            }
            for call in message.tool_calls
        ]
    return payload


def run_agent_loop(
    *,
    client: Any,
    model: str,
    tools: list[dict],
    handlers: SenditToolHandlers,
    system_prompt: str,
    user_prompt: str,
    max_iterations: int,
) -> dict[str, Any]:
    """Run iterative function-calling loop until completion or iteration limit.

    Flow per iteration:
    1. Ask model for next step with tool schemas.
    2. If model returns tool calls, execute each via dispatcher.
    3. Append tool outputs to conversation and continue.
    4. Stop when model responds without tool calls.

    Args:
        client: OpenAI-compatible client.
        model: Model name used for orchestration.
        tools: Function tool definitions JSON.
        handlers: Tool dispatcher and implementations.
        system_prompt: Agent behavior constraints.
        user_prompt: Initial task instruction.
        max_iterations: Hard safety limit for loop.

    Returns:
        dict[str, Any]: Status, iteration count, final assistant message, and full message trace.
    """

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    for iteration in range(1, max_iterations + 1):
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=tools,
            tool_choice="auto",
            temperature=0,
        )
        message = response.choices[0].message
        messages.append(_assistant_message_to_dict(message))

        if not message.tool_calls:
            return {
                "status": "completed",
                "iterations": iteration,
                "final_message": message.content or "",
                "messages": messages,
            }

        for tool_call in message.tool_calls:
            tool_name = tool_call.function.name
            arguments = json.loads(tool_call.function.arguments or "{}")
            result = handlers.dispatch(tool_name, arguments)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": tool_name,
                    "content": json.dumps(result, ensure_ascii=False),
                }
            )

    return {
        "status": "max_iterations_reached",
        "iterations": max_iterations,
        "final_message": "Stopped due to max iteration limit.",
        "messages": messages,
    }
