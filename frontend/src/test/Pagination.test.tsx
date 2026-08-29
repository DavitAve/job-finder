import { createRef } from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { Pagination } from "../components/Pagination";

describe("Pagination", () => {
  it("changes the page and scrolls the table to its top", async () => {
    const user = userEvent.setup();
    const target = document.createElement("section");
    const scrollIntoView = vi.fn();
    target.scrollIntoView = scrollIntoView;
    const ref = createRef<HTMLElement>();
    ref.current = target;
    vi.spyOn(window, "requestAnimationFrame").mockImplementation((callback) => {
      callback(0);
      return 1;
    });
    const onChange = vi.fn();

    render(<Pagination page={1} pages={2} onChange={onChange} scrollTarget={ref} />);
    await user.click(screen.getByRole("button", { name: "Далее" }));

    expect(onChange).toHaveBeenCalledWith(2);
    expect(scrollIntoView).toHaveBeenCalledWith({ behavior: "smooth", block: "start" });
  });
});
