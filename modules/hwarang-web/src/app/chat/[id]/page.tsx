import { ChatPage } from "@/components/chat/chat-page";

export default async function ConversationPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <ChatPage initialConversationId={id} />;
}
