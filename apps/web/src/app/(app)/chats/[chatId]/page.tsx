import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { ChatView } from "@/components/chat/chat-view";
import { isUuid } from "@/lib/markdown/card-refs";

export const metadata: Metadata = { title: "Chat" };
export const instant = false;

export default async function ChatPage({ params }: PageProps<"/chats/[chatId]">) {
  const { chatId } = await params;
  if (!isUuid(chatId)) notFound();
  return <ChatView key={chatId} chatId={chatId.toLowerCase()} />;
}
