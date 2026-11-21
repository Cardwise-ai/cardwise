import type { CardDetail, CardRef, Chat, Message } from "@/lib/api/client";
import cardsJson from "./fixtures/cards.json";

export const mockCards = cardsJson as CardDetail[];

const cardsByName = new Map(mockCards.map((card) => [card.name, card]));

export function cardByName(name: string): CardDetail {
  const card = cardsByName.get(name);
  if (!card) throw new Error(`Mock card missing: ${name}`);
  return card;
}

export function toCardRef(card: CardDetail): CardRef {
  return { oracle_id: card.oracle_id, name: card.name, image_uri: card.image_uri };
}

/** Writes the answer-text reference the model is told to use. */
export function ref(name: string): string {
  const card = cardByName(name);
  return `[[${card.oracle_id}|${card.name}]]`;
}

export interface MockAnswer {
  text: string;
  cards: CardRef[];
}

function answer(text: string, names: string[]): MockAnswer {
  return { text, cards: names.map((name) => toCardRef(cardByName(name))) };
}

export const answers = {
  sacOutlets: answer(
    `Meren wants free, repeatable sacrifice outlets so every creature you lose becomes experience and a return trigger. These are the strongest at the price of zero mana:

- ${ref("Viscera Seer")} and ${ref("Carrion Feeder")} are cheap bodies that turn each sacrifice into scry or a bigger blocker.
- ${ref("Yahenni, Undying Partisan")} grows when opponents' creatures die and can protect itself by sacrificing.
- ${ref("Ashnod's Altar")} and ${ref("Phyrexian Altar")} make mana from each sacrifice, which helps you recast what Meren returns.
- ${ref("Spawning Pit")} banks counters early and turns them into spawn tokens later.

If you only add two, start with ${ref("Viscera Seer")} and ${ref("Ashnod's Altar")}. They are cheap and do the most with Meren's end step trigger.`,
    [
      "Viscera Seer",
      "Carrion Feeder",
      "Yahenni, Undying Partisan",
      "Ashnod's Altar",
      "Phyrexian Altar",
      "Spawning Pit",
    ],
  ),
  finishers: answer(
    `Selvala gives you a lot of mana from big creatures, so the best finishers turn that mana into damage the same turn.

1. ${ref("Craterhoof Behemoth")} ends most games on resolution if you have a few creatures out.
2. ${ref("Finale of Devastation")} finds a creature from your library or graveyard, and with X of 10 or more it pumps the team.
3. ${ref("End-Raze Forerunners")} is a second overrun that also gives vigilance, so you keep blockers back.
4. ${ref("Pathbreaker Ibex")} scales with your largest creature, which Selvala decks usually have.

Lists that already run ${ref("Craterhoof Behemoth")} often add ${ref("Finale of Devastation")} as a tutor for it.`,
    ["Craterhoof Behemoth", "Finale of Devastation", "End-Raze Forerunners", "Pathbreaker Ibex"],
  ),
  ramp: answer(
    `For an Abzan ramp deck, ${ref("Esika, God of the Tree // The Prismatic Bridge")} is a flexible pick: the front face taps for any color, and the back face is an enchantment that puts a free creature or planeswalker into play each upkeep.

Pair it with ${ref("Selvala, Heart of the Wilds")} if your deck leans on big creatures, since both reward a high average power.`,
    ["Esika, God of the Tree // The Prismatic Bridge", "Selvala, Heart of the Wilds"],
  ),
  spells: answer(
    `${ref("Fire // Ice")} is a good fit for an Izzet spells deck. Fire splits 2 damage between creatures or players, and Ice taps a permanent and draws a card, so it is never dead.

It counts as one instant with mana value 4 in your graveyard, which matters for cards that care about mana value.`,
    ["Fire // Ice"],
  ),
} satisfies Record<string, MockAnswer>;

export function pickAnswer(content: string): MockAnswer {
  const text = content.toLowerCase();
  if (/finisher|selvala|craterhoof|win/.test(text)) return answers.finishers;
  if (/ramp|esika|abzan/.test(text)) return answers.ramp;
  if (/izzet|spell|fire/.test(text)) return answers.spells;
  return answers.sacOutlets;
}

interface StoredChat extends Chat {
  messages: Message[];
}

const HOUR = 3_600_000;
const DAY = 24 * HOUR;

function iso(msAgo: number): string {
  return new Date(Date.now() - msAgo).toISOString();
}

function seedChat(
  id: string,
  title: string,
  msAgo: number,
  question: string,
  reply: MockAnswer | null,
): StoredChat {
  const messages: Message[] = [
    {
      id: crypto.randomUUID(),
      role: "user",
      content: question,
      cards: [],
      status: "complete",
      created_at: iso(msAgo + 60_000),
    },
  ];
  if (reply) {
    messages.push({
      id: crypto.randomUUID(),
      role: "assistant",
      content: reply.text,
      cards: reply.cards,
      status: "complete",
      created_at: iso(msAgo),
    });
  }
  return { id, title, created_at: iso(msAgo + 60_000), updated_at: iso(msAgo), messages };
}

export const SEEDED_CHAT_ID = "6f1c2a9e-3b4d-4e5f-8a7b-1c2d3e4f5a6b";

function seed(): StoredChat[] {
  return [
    seedChat(
      SEEDED_CHAT_ID,
      "Sacrifice outlets for Meren",
      2 * HOUR,
      "What are the best free sacrifice outlets for my Meren of Clan Nel Toth deck?",
      answers.sacOutlets,
    ),
    seedChat(
      "0b8f3c1d-2e4a-4b6c-9d8e-7f6a5b4c3d2e",
      "Finishers for Selvala",
      26 * HOUR,
      "My Selvala deck makes a ton of mana but stalls out. What finishers should I run?",
      answers.finishers,
    ),
    seedChat(
      "9a7b6c5d-4e3f-4a2b-8c1d-0e9f8a7b6c5d",
      "Abzan ramp creatures",
      3 * DAY,
      "Good ramp creatures for an Abzan deck?",
      answers.ramp,
    ),
    seedChat(
      "3c4d5e6f-7a8b-4c9d-8e0f-1a2b3c4d5e6f",
      "Fire // Ice in Izzet spells",
      19 * DAY,
      "Is Fire // Ice good in an Izzet spells deck?",
      answers.spells,
    ),
  ];
}

let chats: StoredChat[] = seed();

function summary(chat: StoredChat): Chat {
  return {
    id: chat.id,
    title: chat.title,
    created_at: chat.created_at,
    updated_at: chat.updated_at,
  };
}

export const db = {
  reset() {
    chats = seed();
  },
  listChats(): Chat[] {
    return [...chats].sort((a, b) => b.updated_at.localeCompare(a.updated_at)).map(summary);
  },
  getChat(id: string): StoredChat | undefined {
    return chats.find((chat) => chat.id === id);
  },
  createChat(title: string | null | undefined): Chat {
    const now = new Date().toISOString();
    const chat: StoredChat = {
      id: crypto.randomUUID(),
      title: title?.trim() || "New chat",
      created_at: now,
      updated_at: now,
      messages: [],
    };
    chats.unshift(chat);
    return summary(chat);
  },
  renameChat(id: string, title: string): Chat | undefined {
    const chat = this.getChat(id);
    if (!chat) return undefined;
    chat.title = title;
    chat.updated_at = new Date().toISOString();
    return summary(chat);
  },
  deleteChat(id: string): boolean {
    const before = chats.length;
    chats = chats.filter((chat) => chat.id !== id);
    return chats.length < before;
  },
  addMessage(chatId: string, message: Message) {
    const chat = this.getChat(chatId);
    if (!chat) return;
    chat.messages.push(message);
    chat.updated_at = message.created_at;
    if (chat.title === "New chat" && message.role === "user") {
      chat.title =
        message.content.length > 48
          ? `${message.content.slice(0, 47).trimEnd()}…`
          : message.content;
    }
  },
  getCard(oracleId: string): CardDetail | undefined {
    return mockCards.find((card) => card.oracle_id === oracleId);
  },
};
