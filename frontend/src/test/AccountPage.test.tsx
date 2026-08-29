import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { api } from "../lib/api";
import { AccountPage } from "../pages/AccountPage";

vi.mock("../lib/api", () => ({ api: {
  me: vi.fn(), logout: vi.fn(), resumes: vi.fn(), uploadResume: vi.fn(), activateResume: vi.fn(), deleteResume: vi.fn(),
} }));

const data = {
  active_id: "resume-1", limit: 3,
  resumes: [{ id: "resume-1", filename: "frontend-en.pdf", language: "en" as const, created_at: "2026-08-16T10:00:00Z", size_bytes: 1024, page_count: 2, skills: ["React", "TypeScript"], active: true }],
};

describe("AccountPage", () => {
  it("shows active resume and uploads a second PDF", async () => {
    vi.mocked(api.me).mockResolvedValue({ id: "user-1", email: "david@example.com", display_name: "David Avetisyan", created_at: "2026-08-01T10:00:00Z" });
    vi.mocked(api.resumes).mockResolvedValue(data);
    vi.mocked(api.uploadResume).mockResolvedValue(data);
    const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
    const user = userEvent.setup();
    render(<QueryClientProvider client={client}><AccountPage /></QueryClientProvider>);

    expect((await screen.findAllByText("frontend-en.pdf")).length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText("Активное")).toBeInTheDocument();
    const file = new File(["%PDF-resume"], "resume-ru.pdf", { type: "application/pdf" });
    await user.upload(screen.getByLabelText(/PDF-резюме/), file);
    await user.selectOptions(screen.getByLabelText("Язык резюме"), "ru");
    await user.click(screen.getByRole("button", { name: "Добавить резюме" }));

    await waitFor(() => expect(api.uploadResume).toHaveBeenCalledWith(file, "ru"));
  });

  it("shows user details and logs out", async () => {
    vi.mocked(api.me).mockResolvedValue({ id: "user-1", email: "david@example.com", display_name: "David Avetisyan", created_at: "2026-08-01T10:00:00Z" });
    vi.mocked(api.resumes).mockResolvedValue(data);
    vi.mocked(api.logout).mockResolvedValue(undefined);
    const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
    const user = userEvent.setup();
    render(<QueryClientProvider client={client}><AccountPage /></QueryClientProvider>);

    expect(await screen.findByText("David Avetisyan")).toBeInTheDocument();
    expect(screen.getByText("david@example.com")).toBeInTheDocument();
    expect(screen.getByText("user-1")).toBeInTheDocument();
    expect(screen.getByText("1 из 3")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Выйти из аккаунта" }));

    await waitFor(() => expect(api.logout).toHaveBeenCalledOnce());
    expect(client.getQueryData(["auth"])).toBeNull();
  });
});
