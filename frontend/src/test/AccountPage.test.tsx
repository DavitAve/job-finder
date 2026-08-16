import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { api } from "../lib/api";
import { AccountPage } from "../pages/AccountPage";

vi.mock("../lib/api", () => ({ api: {
  resumes: vi.fn(), uploadResume: vi.fn(), activateResume: vi.fn(), deleteResume: vi.fn(),
} }));

const data = {
  active_id: "resume-1", limit: 3,
  resumes: [{ id: "resume-1", filename: "frontend-en.pdf", language: "en" as const, created_at: "2026-08-16T10:00:00Z", size_bytes: 1024, page_count: 2, skills: ["React", "TypeScript"], active: true }],
};

describe("AccountPage", () => {
  it("shows active resume and uploads a second PDF", async () => {
    vi.mocked(api.resumes).mockResolvedValue(data);
    vi.mocked(api.uploadResume).mockResolvedValue(data);
    const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
    const user = userEvent.setup();
    render(<QueryClientProvider client={client}><AccountPage /></QueryClientProvider>);

    expect(await screen.findByText("frontend-en.pdf")).toBeInTheDocument();
    expect(screen.getByText("Активное")).toBeInTheDocument();
    const file = new File(["%PDF-resume"], "resume-ru.pdf", { type: "application/pdf" });
    await user.upload(screen.getByLabelText(/PDF-резюме/), file);
    await user.selectOptions(screen.getByLabelText("Язык резюме"), "ru");
    await user.click(screen.getByRole("button", { name: "Добавить резюме" }));

    await waitFor(() => expect(api.uploadResume).toHaveBeenCalledWith(file, "ru"));
  });
});
