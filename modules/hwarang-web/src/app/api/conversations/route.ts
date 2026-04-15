/**
 * Conversations API routes.
 * CRUD operations for chat conversations.
 */

import { NextRequest } from "next/server";

// In-memory store for development (replace with Prisma in production)
interface StoredConversation {
  id: string;
  title: string;
  model: string;
  messages: { role: string; content: string; id: string; createdAt: string }[];
  createdAt: string;
  updatedAt: string;
}

const conversations = new Map<string, StoredConversation>();

export async function GET() {
  const list = Array.from(conversations.values())
    .sort((a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime());
  return Response.json(list);
}

export async function POST(request: NextRequest) {
  const body = await request.json();
  const id = crypto.randomUUID();
  const now = new Date().toISOString();

  const conversation: StoredConversation = {
    id,
    title: body.title || "새 대화",
    model: body.model || "hwarang-small",
    messages: [],
    createdAt: now,
    updatedAt: now,
  };

  conversations.set(id, conversation);
  return Response.json(conversation, { status: 201 });
}

export async function DELETE(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const id = searchParams.get("id");

  if (!id || !conversations.has(id)) {
    return Response.json({ error: "Not found" }, { status: 404 });
  }

  conversations.delete(id);
  return Response.json({ deleted: true });
}
