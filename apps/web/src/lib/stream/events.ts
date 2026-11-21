import { z } from "zod";

// Mirrors api/openapi/stream-events.schema.json. events.test.ts fails if the two drift apart.

// Python's UUID type accepts any 8-4-4-4-12 hex string, so match that rather than RFC 9562 only.
const uuid = z.guid();

export const cardRefSchema = z.strictObject({
  oracle_id: uuid,
  name: z.string(),
  image_uri: z.string().nullable(),
});

export const startEventSchema = z.strictObject({
  type: z.literal("start"),
  message_id: uuid,
});

export const textEventSchema = z.strictObject({
  type: z.literal("text"),
  text: z.string(),
});

export const toolNames = ["search_cards", "get_card", "get_rulings", "similar_cards"] as const;

export const toolEventSchema = z.strictObject({
  type: z.literal("tool"),
  name: z.enum(toolNames),
  status: z.enum(["running", "done"]),
});

export const cardsEventSchema = z.strictObject({
  type: z.literal("cards"),
  cards: z.array(cardRefSchema),
});

export const usageSchema = z.strictObject({
  input_tokens: z.int(),
  output_tokens: z.int(),
});

export const doneEventSchema = z.strictObject({
  type: z.literal("done"),
  message_id: uuid,
  usage: usageSchema,
});

export const streamErrorCodes = ["rate_limited", "model_unavailable", "internal"] as const;

export const errorEventSchema = z.strictObject({
  type: z.literal("error"),
  code: z.enum(streamErrorCodes),
  request_id: z.string(),
});

export const streamEventSchema = z.discriminatedUnion("type", [
  startEventSchema,
  textEventSchema,
  toolEventSchema,
  cardsEventSchema,
  doneEventSchema,
  errorEventSchema,
]);

export type StreamEvent = z.infer<typeof streamEventSchema>;
export type StreamCardRef = z.infer<typeof cardRefSchema>;
export type ToolName = (typeof toolNames)[number];
export type StreamErrorCode = (typeof streamErrorCodes)[number];

const knownTypes = new Set<string>(streamEventSchema.options.map((o) => o.shape.type.value));

export type ParsedEvent =
  | { kind: "event"; event: StreamEvent }
  | { kind: "unknown"; type: string }
  | { kind: "invalid"; reason: string };

/** Validates one `data:` payload. Unknown event types are reported separately so callers can skip them. */
export function parseStreamEvent(data: string): ParsedEvent {
  let value: unknown;
  try {
    value = JSON.parse(data);
  } catch {
    return { kind: "invalid", reason: "not JSON" };
  }
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return { kind: "invalid", reason: "not an object" };
  }
  const type = (value as { type?: unknown }).type;
  if (typeof type !== "string") return { kind: "invalid", reason: "missing type" };
  if (!knownTypes.has(type)) return { kind: "unknown", type };
  const result = streamEventSchema.safeParse(value);
  if (!result.success) return { kind: "invalid", reason: `malformed ${type} event` };
  return { kind: "event", event: result.data };
}
