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
  project_id?: string | null;
  brief: { title?: string; copy?: Record<string, unknown> };
  archetype: string;
  discarded: boolean;
  created_at: string;
  latest: LatestSummary | null;
  failure: ConceptFailure | null;
}

export interface ValidationIssue {
  code: string;
  path: string;
  message: string;
}

export interface Version {
  id: string;
  concept_id: string;
  parent_version_id: string | null;
  content_hash: string;
  schema_version: string;
  prompt_pack: string;
  model_history: string[];
  validation: { ok: boolean; errors: ValidationIssue[]; warnings: ValidationIssue[] };
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

export interface ArtworkDocument {
  pages: { items: {
    type: string;
    name?: string;
    paragraphs?: { text?: string; runs?: { text: string }[] }[];
  }[] }[];
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
    size: string | [number, number];
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
  mandatoryCopy?: string[];
  tone: string;
  notes: string;
  references?: { imageAssets: string[] };
  [key: string]: unknown;
}

export interface Project {
  id: string;
  name: string;
  brand: string | null;
  brand_version: number | null;
  brief: Brief | null;
  status: "active" | "archived";
  campaign_id?: string | null;
  campaign_name?: string | null;
}

export interface Swatch {
  name: string;
  space: "cmyk" | "rgb";
  values: number[];
  spot?: boolean;
}

export interface BrandSummary {
  name: string;
  version: number; // store version (BRAND-4) — head of the immutable chain
  versions: number;
  swatches: Swatch[];
  fonts: string[];
  rules: Record<string, unknown>;
  designPrinciples: string | null;
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
  projects: () =>
    fetch("/api/projects").then((r) => j<{ projects: Project[] }>(r)),
  saveProjectBrief: (id: string, brief: Brief) =>
    fetch(`/api/projects/${encodeURIComponent(id)}`, {
      method: "PATCH",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ brief }),
    }).then((r) => j<Project>(r)),
  generateProject: (id: string, brief: Brief, n: number, engine: EnginePreset) =>
    fetch(`/api/projects/${encodeURIComponent(id)}/generate`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ brief, n, engine }),
    }).then((r) => j<{ job_id: string }>(r)),
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
  bundleUrl: (versionId: string) => `/api/versions/${versionId}/bundle.zip`,
  documentUrl: (versionId: string) =>
    `/api/versions/${versionId}/document.json`,
  document: (versionId: string) =>
    fetch(`/api/versions/${versionId}/document.json`).then((r) => j<ArtworkDocument>(r)),
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
  mutate: (versionId: string, instruction: string, textChanges: Record<string, string> = {}) =>
    fetch(`/api/versions/${versionId}/mutate`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ instruction, text_changes: textChanges }),
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

export type IdentityStatus = 'draft' | 'reviewed' | 'provisional' | 'rejected';
export interface IdentityCard {
  id: string; category: string; title: string; body: string; status: IdentityStatus;
  scope: string; conditions?: string | string[];
  source?: { label: string; page?: number; path?: string; sha256?: string; url?: string; quote?: string };
  assetNames?: string[];
  [key: string]: unknown;
}
export interface Identity {
  schemaVersion: number; brandName?: string; campaignName?: string; ranges?: string[];
  cards: IdentityCard[]; [key: string]: unknown;
}
export type IdentityProfile = BrandProfile['profile'] & { identity?: Identity; designPrinciples?: string };
export interface IdentityDraft {
  brand: string; profile: IdentityProfile; revision: number; base_version_id: string;
  updated_at: string | null; published_version_id: string | null;
}
export interface Campaign {
  id: string; name: string; brand: string; ranges: string[]; status: 'active'|'archived'; project_count?: number;
}
export interface IdentitySource {
  id: string; filename: string; mime: string; font_family: string|null; size: number;
}
const brandPath = (name: string) => `/api/brands/${encodeURIComponent(name)}`;
const send = <T,>(url: string, method: string, body: unknown) => fetch(url, {method,headers:{'content-type':'application/json'},body:JSON.stringify(body)}).then(r=>j<T>(r));
export const workspaceApi = {
  draft: (name:string) => fetch(`${brandPath(name)}/identity-draft`).then(r=>j<IdentityDraft>(r)),
  saveDraft: (name:string,profile:IdentityProfile,revision:number) => send<IdentityDraft>(`${brandPath(name)}/identity-draft`,'PUT',{profile,expected_revision:revision}),
  publish: (name:string,revision:number) => send<unknown>(`${brandPath(name)}/identity-draft/publish`,'POST',{revision}),
  campaigns: () => fetch('/api/campaigns').then(r=>j<{campaigns:Campaign[]}>(r)),
  createCampaign: (name:string,brand:string,ranges:string[]) => send<Campaign>('/api/campaigns','POST',{name,brand,ranges}),
  createProject: (name:string,brand:string,campaign_id:string|null,brief:Brief) => send<Project>('/api/projects','POST',{name,brand,campaign_id,brief}),
  project: (id:string) => fetch(`/api/projects/${encodeURIComponent(id)}`).then(r=>j<Project & {concepts:Concept[]}>(r)),
  assignProject: (id:string,campaign_id:string|null) => send<Project>(`/api/projects/${encodeURIComponent(id)}`,'PATCH',{campaign_id}),
  membership: (name:string) => fetch(`${brandPath(name)}/assets`).then(r=>j<{assigned:boolean;names:string[]}>(r)),
  setMembership: (name:string,names:string[]) => send<unknown>(`${brandPath(name)}/assets`,'PUT',{names}),
  sources: (name:string) => fetch(`${brandPath(name)}/sources`).then(r=>j<{sources:IdentitySource[]}>(r)),
  sourceUrl: (name:string,id:string) => `${brandPath(name)}/sources/${encodeURIComponent(id)}`,
  uploadSource: (name:string,filename:string,data_b64:string,font_family?:string) => send<IdentitySource>(`${brandPath(name)}/sources`,'POST',{filename,data_b64,font_family}),
};
