import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { api } from "../lib/api";
import { AuthPage } from "../pages/AuthPage";

vi.mock("../lib/api", () => ({ api: { login: vi.fn(), register: vi.fn() } }));

const account = {
  id: "local",
  email: "david@example.com",
  display_name: "David",
  created_at: "2026-08-28T10:00:00Z",
};

function setup(onAuthenticated = vi.fn()) {
  const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  const user = userEvent.setup();
  render(<QueryClientProvider client={client}><AuthPage onAuthenticated={onAuthenticated} /></QueryClientProvider>);
  return { user, onAuthenticated };
}

describe("AuthPage", () => {
  it("logs in and returns the authenticated user", async () => {
    vi.mocked(api.login).mockResolvedValue(account);
    const { user, onAuthenticated } = setup();

    await user.type(screen.getByLabelText("Email"), "david@example.com");
    await user.type(screen.getByLabelText("Пароль"), "password123");
    await user.click(screen.getByRole("button", { name: "Войти" }));

    await waitFor(() => expect(api.login).toHaveBeenCalledWith({ email: "david@example.com", password: "password123" }));
    expect(onAuthenticated).toHaveBeenCalledWith(account);
  });

  it("validates password confirmation before registration", async () => {
    vi.mocked(api.register).mockResolvedValue(account);
    const { user } = setup();
    await user.click(screen.getByRole("tab", { name: "Регистрация" }));
    await user.type(screen.getByLabelText("Имя"), "David");
    await user.type(screen.getByLabelText("Email"), "david@example.com");
    await user.type(screen.getByLabelText("Пароль"), "password123");
    await user.type(screen.getByLabelText("Повторите пароль"), "different123");
    await user.click(screen.getByRole("button", { name: "Создать аккаунт" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Пароли не совпадают");
    expect(api.register).not.toHaveBeenCalled();
  });
});
