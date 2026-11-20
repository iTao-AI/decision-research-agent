import { useEffect, useState } from "react";
import { getHealth } from "./apiClient";

export function useWorkspaceConnection(baseUrl: string) {
  const [attempt, setAttempt] = useState(0);
  const [observation, setObservation] = useState<{ baseUrl: string; attempt: number; ready: boolean }>();
  useEffect(() => {
    const controller = new AbortController();
    const timer = window.setTimeout(async () => {
      let ready = false;
      try {
        await getHealth(baseUrl, controller.signal);
        ready = true;
      } catch {
        // Keep the configured address visible so it can be corrected or checked again.
      }
      if (!controller.signal.aborted) setObservation({ baseUrl, attempt, ready });
    }, 0);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [baseUrl, attempt]);
  const current = observation?.baseUrl === baseUrl && observation.attempt === attempt ? observation : undefined;
  return {
    status: !current ? "checking" : current.ready ? "connected" : "disconnected",
    retry: () => setAttempt((value) => value + 1)
  } as const;
}
