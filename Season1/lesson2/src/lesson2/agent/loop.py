import json
from typing import Any

from openai import OpenAI

from ..tools.handlers import ToolHandlers
from .state import AgentState


def _assistant_message_to_dict(message: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"role": "assistant", "content": message.content or ""}
    if getattr(message, "tool_calls", None):
        payload["tool_calls"] = [
            {
                "id": call.id,
                "type": "function",
                "function": {"name": call.function.name, "arguments": call.function.arguments},
            }
            for call in message.tool_calls
        ]
    return payload


def run_agent_loop(
    *,
    client: OpenAI,
    model: str,
    tools: list[dict],
    handlers: ToolHandlers,
    state: AgentState,
    system_prompt: str,
    user_prompt: str,
    max_iterations: int,
) -> dict[str, Any]:
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

        state.log({"iteration": iteration, "assistant": message.content, "tool_calls": bool(message.tool_calls)})

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
            state.log({"iteration": iteration, "tool": tool_name, "args": arguments, "result": result})

    return {
        "status": "max_iterations_reached",
        "iterations": max_iterations,
        "final_message": "Stopped due to max iteration limit.",
        "messages": messages,
    }

