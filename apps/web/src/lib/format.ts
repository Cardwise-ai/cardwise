import type { Chat } from "@/lib/api/client";

export type ChatGroupLabel = "Today" | "Previous 7 days" | "Earlier";

/** Groups chats (already newest first) by when they were last updated, in the reader's time zone. */
export function groupChats(
  chats: readonly Chat[],
  now = new Date(),
): Array<{ label: ChatGroupLabel; chats: Chat[] }> {
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const weekAgo = startOfToday - 7 * 24 * 3_600_000;
  const groups: Record<ChatGroupLabel, Chat[]> = { Today: [], "Previous 7 days": [], Earlier: [] };
  for (const chat of chats) {
    const time = Date.parse(chat.updated_at);
    if (time >= startOfToday) groups.Today.push(chat);
    else if (time >= weekAgo) groups["Previous 7 days"].push(chat);
    else groups.Earlier.push(chat);
  }
  return (Object.keys(groups) as ChatGroupLabel[])
    .filter((label) => groups[label].length > 0)
    .map((label) => ({ label, chats: groups[label] }));
}

/** "14:20" in the reader's locale, for "Try again at …" messages. */
export function clockTime(date: Date, locale?: string): string {
  return new Intl.DateTimeFormat(locale, { hour: "numeric", minute: "2-digit" }).format(date);
}

/** The API asks for a retry this soon only when another answer is still streaming. */
const STREAM_BUSY_MAX_SECONDS = 30;

export function rateLimitMessage(
  retryAfterSeconds: number | null,
  now = new Date(),
  locale?: string,
): string {
  if (!retryAfterSeconds) return "Too many messages this hour. Try again later.";
  if (retryAfterSeconds <= STREAM_BUSY_MAX_SECONDS) {
    return "Cardwise is still answering another message, maybe in another tab. Try again in a few seconds.";
  }
  const at = new Date(now.getTime() + retryAfterSeconds * 1000);
  return `Too many messages this hour. Try again at ${clockTime(at, locale)}.`;
}
