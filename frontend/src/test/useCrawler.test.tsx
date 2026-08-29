import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, screen, waitFor } from "@testing-library/react";
import type { PropsWithChildren } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useCrawler } from "../hooks/useCrawler";
import { api } from "../lib/api";
import { ToastProvider } from "../components/Toast";

vi.mock("../lib/api", () => ({ api: { active: vi.fn(), start: vi.fn(), stop: vi.fn() } }));

describe("useCrawler", () => {
  beforeEach(() => vi.clearAllMocks());

  it("invalidates current report and history after running completes", async () => {
    vi.mocked(api.active)
      .mockResolvedValueOnce({ run_id: "run-1", state: "running", processed: 2, total: 3, jobs_found: 2 })
      .mockResolvedValueOnce({ run_id: "run-1", state: "completed", processed: 3, total: 3, jobs_found: 4 });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const invalidate = vi.spyOn(client, "invalidateQueries");
    const wrapper = ({ children }: PropsWithChildren) => <QueryClientProvider client={client}><ToastProvider>{children}</ToastProvider></QueryClientProvider>;
    const { result } = renderHook(() => useCrawler(), { wrapper });
    await waitFor(() => expect(result.current.active.data?.state).toBe("running"));
    await act(async () => { await result.current.active.refetch(); });
    await waitFor(() => expect(result.current.active.data?.state).toBe("completed"));
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["latest-run"] });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["history"] });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["companies"] });
    expect(document.body).toHaveTextContent("Поиск завершён");
  });

  it("notifies when a crawl starts and stops", async () => {
    vi.mocked(api.active).mockResolvedValue({ run_id: null, state: "idle", processed: 0, total: 0, jobs_found: 0 });
    vi.mocked(api.start).mockResolvedValue({ run_id: "run-2", state: "queued", processed: 0, total: 12, jobs_found: 0 });
    vi.mocked(api.stop).mockResolvedValue({ run_id: "run-2", state: "cancelled", processed: 3, total: 12, jobs_found: 1 });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const wrapper = ({ children }: PropsWithChildren) => <QueryClientProvider client={client}><ToastProvider>{children}</ToastProvider></QueryClientProvider>;
    const { result } = renderHook(() => useCrawler(), { wrapper });

    await waitFor(() => expect(result.current.active.data?.state).toBe("idle"));
    await act(async () => { await result.current.start.mutateAsync({ scope: "full" }); });
    expect(screen.getByText("Поиск запущен")).toBeInTheDocument();

    await act(async () => { await result.current.stop.mutateAsync(); });
    expect(screen.getByText("Поиск остановлен")).toBeInTheDocument();
  });

  it("notifies when there are no new companies", async () => {
    vi.mocked(api.active).mockResolvedValue({ run_id: null, state: "idle", processed: 0, total: 0, jobs_found: 0 });
    vi.mocked(api.start).mockResolvedValue({ run_id: null, state: "completed", processed: 0, total: 0, jobs_found: 0, scope: "new" });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const wrapper = ({ children }: PropsWithChildren) => <QueryClientProvider client={client}><ToastProvider>{children}</ToastProvider></QueryClientProvider>;
    const { result } = renderHook(() => useCrawler(), { wrapper });

    await waitFor(() => expect(result.current.active.data?.state).toBe("idle"));
    await act(async () => { await result.current.start.mutateAsync({ scope: "new" }); });
    expect(screen.getByText("Новых компаний нет")).toBeInTheDocument();
  });
});
