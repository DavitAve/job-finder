import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AppShell } from "../components/AppShell";
import { api } from "../lib/api";

vi.mock("../lib/api", () => ({ api: { me: vi.fn(), logout: vi.fn() } }));

describe("AppShell", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.mocked(api.me).mockResolvedValue({ id: "local", email: "david@example.com", display_name: "David", created_at: "2026-08-29T00:00:00Z" });
    vi.mocked(api.logout).mockResolvedValue(undefined);
  });

  it("collapses the desktop sidebar and opens the mobile drawer", async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const user = userEvent.setup();
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter>
          <Routes><Route element={<AppShell />}><Route index element={<div>Контент</div>} /></Route></Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    await user.click(screen.getByRole("button", { name: "Свернуть боковое меню" }));
    expect(screen.getByRole("button", { name: "Развернуть боковое меню" })).toBeInTheDocument();
    expect(localStorage.getItem("job-finder-sidebar-collapsed")).toBe("1");

    const mobileToggle = screen.getByRole("button", { name: "Открыть боковое меню" });
    await user.click(mobileToggle);
    expect(mobileToggle).toHaveAttribute("aria-expanded", "true");
    await user.keyboard("{Escape}");
    expect(mobileToggle).toHaveAttribute("aria-expanded", "false");
  });
});
