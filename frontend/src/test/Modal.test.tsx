import { useState } from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { Modal } from "../components/Modal";

function Harness() {
  const [open, setOpen] = useState(true);
  return open ? (
    <Modal labelledBy="test-modal-title" onClose={() => setOpen(false)}>
      <h2 id="test-modal-title">Подтверждение</h2>
      <button type="button">Внутри</button>
    </Modal>
  ) : null;
}

describe("Modal", () => {
  it("stays open for inside clicks and closes on outside click", async () => {
    const user = userEvent.setup();
    render(<Harness />);

    await user.click(screen.getByRole("button", { name: "Внутри" }));
    expect(screen.getByRole("dialog")).toBeInTheDocument();

    await user.click(document.body);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
