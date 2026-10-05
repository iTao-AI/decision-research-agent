import type { ClientError } from "../apiClient";

export function LiveErrorCard({ error, fallbackFix }: { error: ClientError; fallbackFix: string }) {
  const fix = error.code === "connection_failed" ? fallbackFix : error.fix || fallbackFix;
  return (
    <article className="live-error-card">
      <strong>{error.code}</strong>
      <p>{error.problem}</p>
      <small>{fix}</small>
      {error.run_id && <code>{error.run_id}</code>}
    </article>
  );
}
