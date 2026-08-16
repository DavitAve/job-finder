import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef } from "react";
import { api } from "../lib/api";

export function useCrawler() {
  const client = useQueryClient();
  const invalidatedCompletedRuns = useRef(new Set<string>());
  const active = useQuery({
    queryKey: ["active-run"],
    queryFn: api.active,
    refetchInterval: (query) => query.state.data?.state === "running" || query.state.data?.state === "queued" ? 2000 : false,
  });
  useEffect(() => {
    const status = active.data;
    if (status?.state === "completed" && status.run_id && !invalidatedCompletedRuns.current.has(status.run_id)) {
      invalidatedCompletedRuns.current.add(status.run_id);
      void client.invalidateQueries({ queryKey: ["latest-run"] });
      void client.invalidateQueries({ queryKey: ["history"] });
      void client.invalidateQueries({ queryKey: ["companies"] });
      void client.invalidateQueries({ queryKey: ["job-changes"] });
      void client.invalidateQueries({ queryKey: ["resume-matches"] });
    }
  }, [active.data, client]);
  const start = useMutation({ mutationFn: api.start, onSuccess: (status) => {
    client.setQueryData(["active-run"], status);
    void client.invalidateQueries({ queryKey: ["active-run"] });
  } });
  const isRunning = active.data?.state === "running" || active.data?.state === "queued" || start.isPending;
  return { active, start, isRunning };
}
