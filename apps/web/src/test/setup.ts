import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterAll, afterEach, beforeAll } from "vitest";
import { db } from "@/mocks/db";
import { mockTiming } from "@/mocks/handlers";
import { server } from "@/mocks/node";

mockTiming.chunkDelayMs = 0;

// jsdom has no layout, so scrolling is a no-op that components may still call.
Element.prototype.scrollTo ??= function scrollTo() {};
Element.prototype.scrollIntoView ??= function scrollIntoView() {};

beforeAll(() => server.listen({ onUnhandledFrame: "error" }));
afterEach(() => {
  cleanup();
  server.resetHandlers();
  db.reset();
});
afterAll(() => server.close());
