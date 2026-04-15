"use client";

import { useCallback, useState } from "react";
import { parseSSEStream } from "@/lib/stream-parser";
import { generateId } from "@/lib/utils";
import type { Message } from "@/types/chat";

interface UseChatOptions {
  model?: string;
  apiUrl?: string;
}

export function useChat(options: UseChatOptions = {}) {
  const { model = "/mnt/nvme2/hwarang/models/qwen2.5-32b-int4", apiUrl = "/api/chat" } = options;
  const [messages, setMessages] = useState<Message[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const sendMessage = useCallback(
    async (content: string) => {
      setError(null);

      // Add user message
      const userMessage: Message = {
        id: generateId(),
        role: "user",
        content,
        createdAt: new Date(),
      };

      const assistantId = generateId();
      const assistantMessage: Message = {
        id: assistantId,
        role: "assistant",
        content: "",
        createdAt: new Date(),
      };

      setMessages((prev) => [...prev, userMessage, assistantMessage]);
      setIsStreaming(true);

      try {
        const allMessages = [...messages, userMessage];
        const response = await fetch(apiUrl, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            model,
            messages: allMessages.map((m) => ({
              role: m.role,
              content: m.content,
            })),
            stream: true,
          }),
        });

        if (!response.ok) {
          throw new Error(`API error: ${response.status}`);
        }

        for await (const chunk of parseSSEStream(response)) {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId
                ? { ...m, content: m.content + chunk }
                : m
            )
          );
        }
      } catch (err) {
        const errorMessage =
          err instanceof Error ? err.message : "An error occurred";
        setError(errorMessage);
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId
              ? { ...m, content: `Error: ${errorMessage}` }
              : m
          )
        );
      } finally {
        setIsStreaming(false);
      }
    },
    [messages, model, apiUrl]
  );

  const clearMessages = useCallback(() => {
    setMessages([]);
    setError(null);
  }, []);

  return { messages, sendMessage, isStreaming, error, clearMessages };
}
