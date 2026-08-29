import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { ToastProvider, useToast } from "../components/Toast";
import { API_UNAVAILABLE_EVENT } from "../lib/events";

function Trigger() {
  const { showToast } = useToast();
  return (
    <button
      onClick={() => showToast({ title: "Поиск запущен", dedupeKey: "started" })}
      type="button"
    >
      Показать
    </button>
  );
}

describe("toast notifications", () => {
  it("can be closed by the user", async () => {
    const user = userEvent.setup();
    render(<ToastProvider><Trigger /></ToastProvider>);

    await user.click(screen.getByRole("button", { name: "Показать" }));
    expect(screen.getByText("Поиск запущен")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Закрыть уведомление «Поиск запущен»" }));
    expect(screen.queryByText("Поиск запущен")).not.toBeInTheDocument();
  });

  it("shows only one API unavailable notification for concurrent failures", () => {
    render(<ToastProvider><div /></ToastProvider>);

    act(() => {
      window.dispatchEvent(new Event(API_UNAVAILABLE_EVENT));
      window.dispatchEvent(new Event(API_UNAVAILABLE_EVENT));
    });

    expect(screen.getAllByText("API недоступен")).toHaveLength(1);
  });
});
