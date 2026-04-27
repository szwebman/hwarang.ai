"use client";

import { useCallback, useEffect, useState } from "react";
import type { Conversation } from "@/types/chat";

export function useConversations() {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [loading, setLoading] = useState(false);

  const fetchConversations = useCallback(async () => {
    setLoading(true);
    try {
      const response = await fetch("/api/conversations");
      if (response.ok) {
        const data = await response.json();
        // 서버는 { conversations: [...] } 형식. 구버전 호환을 위해 배열도 허용.
        const list: Array<Record<string, string>> = Array.isArray(data)
          ? data
          : data?.conversations ?? [];
        setConversations(
          list.map((c) => ({
            ...c,
            messages: [],
            createdAt: new Date(c.createdAt),
            updatedAt: new Date(c.updatedAt),
          })) as unknown as Conversation[]
        );
      }
    } catch (error) {
      console.error("Failed to fetch conversations:", error);
    } finally {
      setLoading(false);
    }
  }, []);

  const createConversation = useCallback(
    async (title?: string, model?: string) => {
      const response = await fetch("/api/conversations", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title, model }),
      });
      if (response.ok) {
        const data = await response.json();
        const newConv: Conversation = {
          ...data,
          messages: [],
          createdAt: new Date(data.createdAt),
          updatedAt: new Date(data.updatedAt),
        };
        setConversations((prev) => [newConv, ...prev]);
        return newConv;
      }
      return null;
    },
    []
  );

  const deleteConversation = useCallback(async (id: string) => {
    const response = await fetch(`/api/conversations?id=${id}`, {
      method: "DELETE",
    });
    if (response.ok) {
      setConversations((prev) => prev.filter((c) => c.id !== id));
    }
  }, []);

  useEffect(() => {
    fetchConversations();
  }, [fetchConversations]);

  return {
    conversations,
    loading,
    createConversation,
    deleteConversation,
    refresh: fetchConversations,
  };
}
