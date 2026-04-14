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
        setConversations(
          data.map((c: Record<string, string>) => ({
            ...c,
            createdAt: new Date(c.createdAt),
            updatedAt: new Date(c.updatedAt),
          }))
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
