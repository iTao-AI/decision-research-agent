export type Mode = "replay" | "mke-replay" | "live";
export type Area = "demo" | "live_access" | "interview";
export type ProposalStatus = "pending" | "accepted" | "returned" | "superseded";

export interface Material {
  id: string;
  title: string;
  sha256: string;
  source_id: string;
  publication_id: string;
  revision: number;
  material_version?: number;
  producer_run_id: string;
  active: boolean;
}

export interface Evidence {
  id: string;
  material_id: string;
  title: string;
  source_id: string;
  publication_id: string;
  revision: number;
  material_version?: number;
  producer_run_id: string;
  consumer_run_id: string;
  page_start: number;
  page_end: number;
  text: string;
  sha256: string;
  byte_start: number;
  byte_end: number;
}

export interface Item {
  area: Area;
  state: "proceed" | "waiting";
  priority: "high" | "normal";
  action: string;
  owner: string;
  reason: string;
  question: string;
  evidence_ids: string[];
}

export interface Decision {
  headline: string;
  summary: string;
  items: Item[];
  evidence: Evidence[];
}

export interface Confirmed extends Decision {
  version: number;
  proposal_id: string | null;
}

export interface Proposal extends Decision {
  id: string;
  dra_run_id: string;
  basis_revision: number;
  material_id: string;
  status: ProposalStatus;
  mode: Mode;
  feedback: string;
}

export interface Intake {
  title: string;
  replace: string | null;
  sha256: string;
  state: "pending" | "failed";
  error_code: string | null;
}

export interface Project {
  id: string;
  title: string;
  stage: string;
  revision: number;
  sample_prepared: boolean;
  mode: Mode;
  confirmed: Confirmed;
  proposal: Proposal | null;
  materials: Material[];
  intake?: Intake | null;
  deliverables: { version: number; sha256: string }[];
}

export interface History {
  confirmed: Pick<Confirmed, "version" | "proposal_id" | "headline">[];
  proposals: Pick<Proposal, "id" | "status" | "headline" | "material_id" | "feedback">[];
}

export interface LiveEvidence {
  status: "available" | "unavailable";
  frozen: Evidence;
  current: Evidence | null;
  reason?: string;
}

export class FieldworkRequestError extends Error {}

const base = "/api/fieldwork/projects/northstar";

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(base + path, { ...init, redirect: "error" });
  if (!response.ok) {
    const payload = await response.json().catch(() => null) as { detail?: { message?: string } } | null;
    throw new FieldworkRequestError(payload?.detail?.message || "工作台暂时无法完成操作。");
  }
  return response.json() as Promise<T>;
}

function post(path: string, body: object) {
  return request<Project>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export const fieldworkApi = {
  project: (signal?: AbortSignal) => request<Project>("", { signal }),
  history: () => request<History>("/history"),
  proposal: (id: string) => request<Proposal>(`/proposals/${encodeURIComponent(id)}`),
  upload: (file: File, title: string, predecessor: string) => {
    const params = new URLSearchParams({ title });
    if (predecessor) params.set("replace", predecessor);
    return request<Project>(`/materials?${params}`, {
      method: "POST",
      headers: { "Content-Type": "application/pdf" },
      body: file,
    });
  },
  analyze: (material_id: string) => post("/analysis", { material_id }),
  review: (proposal_id: string, decision: "accept" | "return", feedback: string) =>
    post("/review", { proposal_id, decision, feedback }),
  progress: () => post("/progress", { sample_prepared: true }),
  liveEvidence: (proposal: string, evidence: string) =>
    request<LiveEvidence>(`/proposals/${encodeURIComponent(proposal)}/evidence/${encodeURIComponent(evidence)}/live`),
  export: (version: number, format: "md" | "json" | "html") => `${base}/exports/${version}.${format}`,
};
