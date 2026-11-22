import { describe, expect, it } from "vitest";
import { readThemeMode, resolveTheme } from "./theme";

describe("theme preference", () => {
  it.each([
    ["light", "light"],
    ["dark", "dark"],
    ["system", "system"],
    ["unknown", "system"],
    [null, "system"],
  ] as const)("reads %s as %s", (value, expected) => {
    expect(readThemeMode(value)).toBe(expected);
  });

  it("uses the system preference only while the mode is system", () => {
    expect(resolveTheme("system", true)).toBe("dark");
    expect(resolveTheme("system", false)).toBe("light");
    expect(resolveTheme("light", true)).toBe("light");
    expect(resolveTheme("dark", false)).toBe("dark");
  });
});
