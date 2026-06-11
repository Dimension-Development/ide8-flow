// Typed client for the generation worker API (proxied at /api).

export interface LatestSummary {
  id: string;
  approved: boolean;
  origin: "generation" | "mutation" | "hand_finished";
  has_proof: boolean;
  created_at: string;
  validation_ok: boolean | null;
  warnings: number;
  cost_usd: number | null;
}

export interface Concept {
  id: string;
  brief: { title?: string; copy?: Record<string, unknown> };
  archetype: string;
  discarded: boolean;
  created_at: string;
  latest: LatestSummary | null;
}

export interface Version {
  id: string;
  concept_id: string;
  parent_version_id: string | null;
  content_hash: string;
  schema_version: string;
  prompt_pack: string;
  model_history: string[];
  validation: { ok: boolean; errors: unknown[]; warnings: unknown[] };
  critique: { approve: boolean; issues?: { issue: string }[] } | null;
  usage: { cost_usd?: number } | null;
  approved: boolean;
  origin: string;
  mutation_instruction: string | null;
  has_proof: boolean;
  created_at: string;
}

export interface ConceptDetail extends Concept {
  versions: Version[];
}

export interface MutationResponse {
  version_id: string;
  parent_version_id: string;
  diff: { path: string; change: string }[];
  iterations: number;
  cost_usd: number | null;
}

async function j<T>(r: Response): Promise<T> {
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.json() as Promise<T>;
}

export interface Brief {
  title: string;
  brand: string;
  format: {
    size: string;
    orientation: string;
    bleed: number;
    margins: number[];
  };
  copy: {
    headline: string;
    subhead: string;
    body: string[];
    legal: string | null;
  };
  mandatoryElements: string[];
  tone: string;
  notes: string;
}

export interface Job {
  id: string;
  status: "queued" | "running" | "done" | "failed";
  n: number;
  error: string | null;
  concepts: Concept[];
}

export const api = {
  generate: (brief: Brief, n: number) =>
    fetch("/api/generate", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ brief, n }),
    }).then((r) => j<{ job_id: string }>(r)),
  job: (id: string) => fetch(`/api/jobs/${id}`).then((r) => j<Job>(r)),
  slaUrl: (versionId: string) => `/api/versions/${versionId}/document.sla`,
  documentUrl: (versionId: string) =>
    `/api/versions/${versionId}/document.json`,
  concepts: (includeDiscarded: boolean) =>
    fetch(`/api/concepts?include_discarded=${includeDiscarded}`).then((r) =>
      j<{ concepts: Concept[] }>(r),
    ),
  concept: (id: string) =>
    fetch(`/api/concepts/${id}`).then((r) => j<ConceptDetail>(r)),
  discard: (id: string) =>
    fetch(`/api/concepts/${id}/discard`, { method: "POST" }).then(j),
  restore: (id: string) =>
    fetch(`/api/concepts/${id}/restore`, { method: "POST" }).then(j),
  mutate: (versionId: string, instruction: string) =>
    fetch(`/api/versions/${versionId}/mutate`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ instruction }),
    }).then((r) => j<MutationResponse>(r)),
  proofUrl: (versionId: string) => `/api/versions/${versionId}/proof.png`,
};
