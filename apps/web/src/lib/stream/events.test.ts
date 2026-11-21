import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { z } from "zod";
import { parseStreamEvent, streamEventSchema } from "./events";
import { readStreamEvents } from "./read-events";

const ORACLE_ID = "5f5a9c5d-6b1e-4a43-9e0e-0d4b3b1f7f11";
const MESSAGE_ID = "0b8a3a52-9f9f-4f6e-8a1b-6c1a3f2e9d10";

interface JsonSchemaObject {
  properties: Record<string, { const?: string; enum?: string[] }>;
  required?: string[];
  additionalProperties?: boolean;
}

const contract = JSON.parse(
  readFileSync(resolve(process.cwd(), "../../api/openapi/stream-events.schema.json"), "utf8"),
) as {
  $defs: Record<string, JsonSchemaObject>;
  oneOf?: Array<{ $ref: string }>;
  anyOf?: Array<{ $ref: string }>;
};

describe("stream event schema", () => {
  it("covers the same event types and fields as the API contract", () => {
    const refs = (contract.oneOf ?? contract.anyOf ?? []).map((entry) =>
      entry.$ref.split("/").pop()!,
    );
    expect(refs.length).toBeGreaterThan(0);

    const fromContract = Object.fromEntries(
      refs.map((name) => {
        const def = contract.$defs[name]!;
        return [def.properties.type!.const!, Object.keys(def.properties).sort()];
      }),
    );
    const fromZod = Object.fromEntries(
      streamEventSchema.options.map((option) => [
        option.shape.type.value,
        Object.keys(option.shape).sort(),
      ]),
    );
    expect(fromZod).toEqual(fromContract);
  });

  it("matches the contract's enums", () => {
    const toolDef = contract.$defs.ToolEvent!;
    const errorDef = contract.$defs.ErrorEvent!;
    const shapeOf = (type: string) =>
      streamEventSchema.options.find((o) => o.shape.type.value === type)!.shape as Record<
        string,
        z.ZodType
      >;
    const enumOf = (schema: z.ZodType | undefined) => [...(schema as z.ZodEnum).options].sort();
    expect(enumOf(shapeOf("tool").name)).toEqual([...toolDef.properties.name!.enum!].sort());
    expect(enumOf(shapeOf("tool").status)).toEqual([...toolDef.properties.status!.enum!].sort());
    expect(enumOf(shapeOf("error").code)).toEqual([...errorDef.properties.code!.enum!].sort());
  });
});

describe("parseStreamEvent", () => {
  it("accepts each event in the contract", () => {
    const events = [
      { type: "start", message_id: MESSAGE_ID },
      { type: "text", text: "Try [[" },
      { type: "tool", name: "search_cards", status: "running" },
      { type: "cards", cards: [{ oracle_id: ORACLE_ID, name: "Viscera Seer", image_uri: null }] },
      { type: "done", message_id: MESSAGE_ID, usage: { input_tokens: 812, output_tokens: 240 } },
      { type: "error", code: "model_unavailable", request_id: "req_1" },
    ];
    for (const event of events) {
      expect(parseStreamEvent(JSON.stringify(event))).toEqual({ kind: "event", event });
    }
  });

  it("reports unknown event types separately so they can be skipped", () => {
    expect(parseStreamEvent('{"type":"reasoning","text":"..."}')).toEqual({
      kind: "unknown",
      type: "reasoning",
    });
  });

  it.each([
    ["not JSON", "{oops"],
    ["not an object", "[1,2]"],
    ["missing type", '{"text":"hi"}'],
    ["malformed text event", '{"type":"text"}'],
    ["malformed text event", '{"type":"text","text":"a","html":"<b>"}'],
    [
      "malformed cards event",
      '{"type":"cards","cards":[{"oracle_id":"nope","name":"x","image_uri":null}]}',
    ],
    ["malformed error event", '{"type":"error","code":"teapot","request_id":"r"}'],
    [
      "malformed done event",
      `{"type":"done","message_id":"${MESSAGE_ID}","usage":{"input_tokens":1.5,"output_tokens":1}}`,
    ],
  ])("rejects %s: %s", (reason, data) => {
    expect(parseStreamEvent(data)).toEqual({ kind: "invalid", reason });
  });
});

describe("readStreamEvents", () => {
  it("yields valid events and reports the ones it skipped", async () => {
    const lines = [
      `data: {"type":"start","message_id":"${MESSAGE_ID}"}`,
      ": heartbeat",
      'data: {"type":"thinking"}',
      'data: {"type":"text","text":"Hello"}',
      "data: {broken",
      `data: {"type":"done","message_id":"${MESSAGE_ID}","usage":{"input_tokens":1,"output_tokens":2}}`,
    ];
    const body = new Response(lines.map((line) => `${line}\n\n`).join("")).body!;
    const skipped: string[] = [];
    const types: string[] = [];
    for await (const event of readStreamEvents(body, {
      onSkipped: (reason) => skipped.push(reason),
    })) {
      types.push(event.type);
    }
    expect(types).toEqual(["start", "text", "done"]);
    expect(skipped).toEqual(["unknown type thinking", "not JSON"]);
  });
});
