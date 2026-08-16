import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { PropsWithChildren } from "react";
import { describe, expect, it, vi } from "vitest";
import { useCrawler } from "../hooks/useCrawler";
import { api } from "../lib/api";

vi.mock("../lib/api", () => ({ api: { active: vi.fn(), start: vi.fn() } }));

describe("useCrawler", () => {
  it("invalidates current report and history after running completes", async () => {
    vi.mocked(api.active)
      .mockResolvedValueOnce({ run_id: "run-1", state: "running", processed: 2, total: 3, jobs_found: 2 })
      .mockResolvedValueOnce({ run_id: "run-1", state: "completed", processed: 3, total: 3, jobs_found: 4 });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const invalidate = vi.spyOn(client, "invalidateQueries");
    const wrapper = ({ children }: PropsWithChildren) => <QueryClientProvider client={client}>{children}</QueryClientProvider>;
    const { result } = renderHook(() => useCrawler(), { wrapper });
    await waitFor(() => expect(result.current.active.data?.state).toBe("running"));
    await act(async () => { await result.current.active.refetch(); });
    await waitFor(() => expect(result.current.active.data?.state).toBe("completed"));
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["latest-run"] });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["history"] });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["companies"] });
  });
});
