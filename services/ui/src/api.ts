// Typed client for the generation worker API (proxied at /api).

export interface LatestSummary {
  id: string;
  approved: boolean;
  origin: "generation" | "mutation" | "hand_finished";
  has_proof: boolean;
  created_at: string;
  validation_ok: boolean | null;
  error_codes: string[];
  warnings: number;
  cost_usd: number | null;
}

export interface ConceptFailure {
  error: string;
  iterations: number;
  model_history: string[];
  cost_usd: number;
}

export interface Concept {
  id: string;
  brief: { title?: string; copy?: Record<string, unknown> };
  archetype: string;
  discarded: boolean;
  created_at: string;
  latest: LatestSummary | null;
  failure: ConceptFailure | null;
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

export interface Comment {
  id: string;
  concept_id: string;
  version_id: string | null;
  anchor_name: string | null;
  author: string;
  body: string;
  resolved: boolean;
  created_at: string;
}

export interface Stats {
  scope: "global" | "job";
  job_id: string | null;
  concepts: number;
  versions: number;
  versions_by_origin: Record<string, number>;
  approved_versions: number;
  llm_calls: number;
  cost_usd_total: number;
  tokens: {
    input: number;
    output: number;
    cache_read: number;
    cache_creation: number;
  };
  cost_by_model: {
    model: string;
    calls: number;
    input_tokens: number;
    output_tokens: number;
    cost_usd: number;
    priced: boolean;
  }[];
  validation: {
    versions_with_errors: number;
    errors_by_code: Record<string, number>;
    warnings_by_code: Record<string, number>;
  };
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
  references?: { imageAssets: string[] };
}

export interface Swatch {
  name: string;
  space: "cmyk" | "rgb";
  values: number[];
  spot?: boolean;
}

export interface BrandSummary {
  name: string;
  version: string | null;
  swatches: Swatch[];
  fonts: string[];
  rules: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface BrandProfile {
  name: string;
  profile: {
    name: string;
    version?: string;
    swatches: Swatch[];
    fonts: string[];
    rules?: Record<string, unknown>;
    [k: string]: unknown;
  };
}

export interface Job {
  id: string;
  status: "queued" | "running" | "done" | "failed";
  n: number;
  error: string | null;
  concepts: Concept[];
}

export type EnginePreset = "draft" | "standard" | "premium";

export interface Asset {
  name: string;
  filename: string;
  mime: string;
  width: number | null;
  height: number | null;
  size: number;
  created_at: string;
}

export const api = {
  generate: (brief: Brief, n: number, engine: EnginePreset) =>
    fetch("/api/generate", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ brief, n, engine }),
    }).then((r) => j<{ job_id: string }>(r)),
  job: (id: string) => fetch(`/api/jobs/${id}`).then((r) => j<Job>(r)),
  stats: () => fetch("/api/stats").then((r) => j<Stats>(r)),
  brands: () =>
    fetch("/api/brands").then((r) =>
      j<{ brands: BrandSummary[]; default: string }>(r),
    ),
  brand: (name: string) =>
    fetch(`/api/brands/${encodeURIComponent(name)}`).then((r) =>
      j<BrandProfile>(r),
    ),
  saveBrand: (profile: Record<string, unknown>) =>
    fetch("/api/brands", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(profile),
    }).then((r) => j<BrandProfile>(r)),
  deleteBrand: (name: string) =>
    fetch(`/api/brands/${encodeURIComponent(name)}`, {
      method: "DELETE",
    }).then(j),
  assets: () =>
    fetch("/api/assets").then((r) => j<{ assets: Asset[] }>(r)),
  uploadAsset: (name: string, filename: string, dataB64: string) =>
    fetch("/api/assets", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ name, filename, data_b64: dataB64 }),
    }).then((r) => j<Asset>(r)),
  assetUrl: (name: string) => `/api/assets/${name}`,
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
  thumbUrl: (versionId: string) => `/api/versions/${versionId}/thumb.png`,
  comments: (conceptId: string) =>
    fetch(`/api/concepts/${conceptId}/comments`).then((r) =>
      j<{ comments: Comment[] }>(r),
    ),
  addComment: (conceptId: string, body: string, versionId?: string | null) =>
    fetch(`/api/concepts/${conceptId}/comments`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ body, version_id: versionId ?? null }),
    }).then((r) => j<Comment>(r)),
  resolveComment: (commentId: string, resolved: boolean) =>
    fetch(`/api/comments/${commentId}/${resolved ? "resolve" : "reopen"}`, {
      method: "POST",
    }).then(j),
};
