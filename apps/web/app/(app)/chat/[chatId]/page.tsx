import { ChatView } from "@/features/chat/ChatView";

export default async function ChatPage({
  params,
}: {
  params: Promise<{ chatId: string }>;
}) {
  const { chatId } = await params;
  return (
    <main>
      <h1>Chat</h1>
      <ChatView chatId={chatId} />
    </main>
  );
}
