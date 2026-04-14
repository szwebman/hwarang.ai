"""Conversation context management."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ConversationContext:
    """Manages the conversation history for the agent."""

    system_prompt: str = ""
    messages: list[dict] = field(default_factory=list)

    def add_user_message(self, content: str) -> None:
        self.messages.append({"role": "user", "content": content})

    def add_assistant_message(
        self, content: str | None = None, tool_calls: list[dict] | None = None
    ) -> None:
        msg: dict = {"role": "assistant"}
        if content:
            msg["content"] = content
        if tool_calls:
            msg["tool_calls"] = tool_calls
        self.messages.append(msg)

    def add_tool_result(self, tool_call_id: str, output: str) -> None:
        self.messages.append({
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": output,
        })

    def to_messages(self) -> list[dict]:
        """Convert to the format expected by LLM providers."""
        result = []
        if self.system_prompt:
            result.append({"role": "system", "content": self.system_prompt})
        result.extend(self.messages)
        return result

    def clear(self) -> None:
        """Clear conversation history."""
        self.messages.clear()

    @property
    def num_messages(self) -> int:
        return len(self.messages)
