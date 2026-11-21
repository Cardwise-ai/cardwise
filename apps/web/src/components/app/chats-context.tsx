"use client";

import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { getApiClient } from "@/lib/api/browser";
import type { Chat } from "@/lib/api/client";
import { createChat, deleteChat, listChats, renameChat } from "@/lib/api/endpoints";

type LoadState = "loading" | "ready" | "error";

interface ChatsContextValue {
  chats: Chat[];
  state: LoadState;
  reload: () => void;
  create: () => Promise<Chat>;
  rename: (chatId: string, title: string) => Promise<void>;
  remove: (chatId: string) => Promise<void>;
  /** Moves a chat to the top after a message, and picks up a server-generated title. */
  touch: (chatId: string) => void;
  /** A message to send as soon as the chat view for this chat mounts. */
  takePendingMessage: (chatId: string) => string | undefined;
  setPendingMessage: (chatId: string, content: string) => void;
}

const ChatsContext = createContext<ChatsContextValue | null>(null);

export function useChats(): ChatsContextValue {
  const value = useContext(ChatsContext);
  if (!value) throw new Error("useChats must be used inside <ChatsProvider>");
  return value;
}

export function ChatsProvider({ children }: { children: ReactNode }) {
  const [chats, setChats] = useState<Chat[]>([]);
  const [state, setState] = useState<LoadState>("loading");
  const pending = useRef(new Map<string, string>());

  // "reload" shows the loading state again; "quiet" keeps the current list if the refresh fails.
  const load = useCallback(async (mode: "reload" | "quiet") => {
    if (mode === "reload") setState("loading");
    try {
      const page = await listChats(getApiClient());
      setChats(page.items);
      setState("ready");
    } catch {
      if (mode !== "quiet") setState("error");
    }
  }, []);

  useEffect(() => {
    // The list loads in the browser because the API needs the user's bearer token.
    let active = true;
    listChats(getApiClient()).then(
      (page) => {
        if (!active) return;
        setChats(page.items);
        setState("ready");
      },
      () => {
        if (active) setState("error");
      },
    );
    return () => {
      active = false;
    };
  }, []);

  const value = useMemo<ChatsContextValue>(
    () => ({
      chats,
      state,
      reload: () => void load("reload"),
      async create() {
        const chat = await createChat(getApiClient());
        setChats((current) => [chat, ...current.filter((c) => c.id !== chat.id)]);
        return chat;
      },
      async rename(chatId, title) {
        const chat = await renameChat(getApiClient(), chatId, title);
        setChats((current) => current.map((c) => (c.id === chatId ? chat : c)));
      },
      async remove(chatId) {
        await deleteChat(getApiClient(), chatId);
        setChats((current) => current.filter((c) => c.id !== chatId));
      },
      touch(chatId) {
        setChats((current) => {
          const chat = current.find((c) => c.id === chatId);
          if (!chat) return current;
          const updated = { ...chat, updated_at: new Date().toISOString() };
          return [updated, ...current.filter((c) => c.id !== chatId)];
        });
        void load("quiet");
      },
      takePendingMessage(chatId) {
        const content = pending.current.get(chatId);
        pending.current.delete(chatId);
        return content;
      },
      setPendingMessage(chatId, content) {
        pending.current.set(chatId, content);
      },
    }),
    [chats, state, load],
  );

  return <ChatsContext.Provider value={value}>{children}</ChatsContext.Provider>;
}
