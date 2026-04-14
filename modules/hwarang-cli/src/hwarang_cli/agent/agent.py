"""ReAct-style agent loop."""

from __future__ import annotations

import logging

from hwarang_cli.agent.context import ConversationContext
from hwarang_cli.providers.base import LLMProvider
from hwarang_cli.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

DEFAULT_SYSTEM_PROMPT = """You are Hwarang, an AI coding assistant running in the terminal.
You have access to tools for reading/writing files, searching code, and executing commands.
Use tools when needed to help the user with their tasks.
Be concise and helpful. When modifying code, explain what you changed and why."""

MAX_TOOL_ITERATIONS = 20


class Agent:
    """ReAct agent that can use tools to accomplish tasks."""

    def __init__(
        self,
        provider: LLMProvider,
        tool_registry: ToolRegistry,
        model: str = "",
        system_prompt: str | None = None,
        temperature: float = 0.7,
    ):
        self.provider = provider
        self.tools = tool_registry
        self.model = model
        self.temperature = temperature
        self.context = ConversationContext(
            system_prompt=system_prompt or DEFAULT_SYSTEM_PROMPT
        )

    async def run(self, user_message: str) -> str:
        """Process a user message through the agent loop.

        The agent will:
        1. Send the message to the LLM with tool definitions
        2. If the LLM requests tool calls, execute them and loop
        3. If the LLM returns text, return it as the final response
        """
        self.context.add_user_message(user_message)

        for iteration in range(MAX_TOOL_ITERATIONS):
            response = await self.provider.chat(
                messages=self.context.to_messages(),
                model=self.model,
                tools=self.tools.get_tool_definitions() or None,
                temperature=self.temperature,
            )

            if response.tool_calls:
                # Add assistant message with tool calls
                self.context.add_assistant_message(
                    content=response.content,
                    tool_calls=[
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {"name": tc.name, "arguments": tc.arguments},
                        }
                        for tc in response.tool_calls
                    ],
                )

                # Execute each tool call
                for tc in response.tool_calls:
                    logger.info(f"Executing tool: {tc.name}")
                    result = await self.tools.execute(tc.name, tc.arguments)
                    self.context.add_tool_result(tc.id, result.output)

                continue  # Loop back for next LLM call

            # No tool calls - final response
            final_text = response.content or ""
            self.context.add_assistant_message(content=final_text)
            return final_text

        return "Maximum tool iterations reached. Please try a simpler request."

    async def stream_run(self, user_message: str):
        """Stream the agent response (for non-tool responses only)."""
        self.context.add_user_message(user_message)

        async for chunk in self.provider.stream_chat(
            messages=self.context.to_messages(),
            model=self.model,
            temperature=self.temperature,
        ):
            yield chunk
