import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { Composer } from "./composer";

function Harness({
  onSubmit,
  streaming = false,
  onStop,
}: {
  onSubmit: (v: string) => void;
  streaming?: boolean;
  onStop?: () => void;
}) {
  const [value, setValue] = useState("");
  return (
    <Composer
      value={value}
      onChange={setValue}
      onSubmit={onSubmit}
      streaming={streaming}
      {...(onStop ? { onStop } : {})}
    />
  );
}

describe("Composer", () => {
  it("sends on Enter and adds a line on Shift+Enter", async () => {
    const onSubmit = vi.fn();
    render(<Harness onSubmit={onSubmit} />);
    const box = screen.getByRole("textbox", { name: "Message" });
    await userEvent.type(box, "Sac outlets{Shift>}{Enter}{/Shift}for Meren");
    expect(box).toHaveValue("Sac outlets\nfor Meren");
    expect(onSubmit).not.toHaveBeenCalled();
    await userEvent.keyboard("{Enter}");
    expect(onSubmit).toHaveBeenCalledWith("Sac outlets\nfor Meren");
  });

  it("does not send a blank message", async () => {
    const onSubmit = vi.fn();
    render(<Harness onSubmit={onSubmit} />);
    await userEvent.type(screen.getByRole("textbox", { name: "Message" }), "   {Enter}");
    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
  });

  it("offers Stop instead of Send while an answer streams", async () => {
    const onSubmit = vi.fn();
    const onStop = vi.fn();
    render(<Harness onSubmit={onSubmit} onStop={onStop} streaming />);
    await userEvent.type(screen.getByRole("textbox", { name: "Message" }), "next question{Enter}");
    expect(onSubmit).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Stop" }));
    expect(onStop).toHaveBeenCalledOnce();
  });
});
