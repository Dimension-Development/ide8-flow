import { useEffect, useState } from "react";
import { api, type Concept, type Job, type Project } from "../api";
import { Cost } from "./Badges";
import ReviewManager from './ReviewManager';

type WorkspaceProject = Omit<Project, "concepts"> & {
  concepts: Concept[];
  campaign_id?: string | null;
  campaign_name?: string | null;
};

export interface ProjectWorkspaceProps {
  projectId: string;
  onOpenConcept: (id: string) => void;
  onEditBrief: (projectId: string) => void;
  onBack: () => void;
  onOpenBrand?: (name: string) => void;
  activeJobId?: string | null;
  onJobSettled?: () => void;
}

const focus = "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-4";

async function loadProject(id: string): Promise<WorkspaceProject> {
  const response = await fetch(`/api/projects/${encodeURIComponent(id)}`);
  if (!response.ok) throw new Error(`Could not load this project (${response.status}).`);
  return response.json() as Promise<WorkspaceProject>;
}

function formatLabel(project: WorkspaceProject): string {
  const format = project.brief?.format;
  if (!format) return "Format to choose";
  const size = format.size;
  if (Array.isArray(size)) {
    let [width, height] = size;
    if (format.orientation === "landscape" && height > width) [width, height] = [height, width];
    const mm = (pt: number) => Number((pt * 25.4 / 72).toFixed(1));
    return `${mm(width)} × ${mm(height)} mm · ${format.orientation}`;
  }
  return `${size} · ${format.orientation}`;
}

function ArtworkCard({ concept, onOpen }: { concept: Concept; onOpen: () => void }) {
  const latest = concept.latest;
  const reason = concept.failure?.error || (latest?.error_codes.length ? latest.error_codes.join(", ") : null);
  const title = concept.archetype.split(":")[0] || "Artwork concept";
  const status = !latest ? (reason ? "Generation failed" : "Awaiting a proof")
    : latest.validation_ok === false ? "Needs attention" : latest.origin === "mutation" ? "Revised" : latest.origin === "hand_finished" ? "Studio edit"
      : latest.approved ? "AI check passed" : "Needs craft review";
  return <article className="group overflow-hidden rounded-2xl border border-ink/10 bg-paper transition hover:border-ink/25 hover:shadow-md hover:shadow-ink/5">
    <button onClick={onOpen} disabled={!latest} aria-label={latest ? `Open ${title}` : `${title}: ${status}`} className={`flex aspect-[4/5] w-full items-center justify-center bg-ink/[0.035] p-5 disabled:cursor-default ${focus}`}>
      {latest?.has_proof ? <img src={api.thumbUrl(latest.id)} alt={`${title} artwork proof`} loading="lazy" className="max-h-full max-w-full object-contain shadow-md shadow-ink/10" /> : <span className="max-w-full space-y-2 px-3 text-center"><span className={`block text-sm font-semibold ${reason ? "text-brand" : "text-ink-soft"}`}>{status}</span>{reason && <span className="block break-words text-xs leading-relaxed text-ink-soft">{reason}</span>}</span>}
    </button>
    <div className="space-y-3 px-5 py-4">
      <div className="flex items-start justify-between gap-3"><h3 className="font-semibold leading-snug">{title}</h3><Cost usd={latest?.cost_usd ?? concept.failure?.cost_usd} /></div>
      <div className="flex flex-wrap items-center gap-2 text-xs"><span className={`rounded-full px-2.5 py-1 ${reason && !latest?.has_proof ? "bg-brand/10 text-brand" : latest?.origin === "mutation" ? "bg-violet-50 text-violet-800" : latest?.approved ? "bg-emerald-50 text-emerald-800" : "bg-ink/5 text-ink-soft"}`}>{status}</span>{!!latest?.warnings && <span className="text-amber-800">{latest.warnings} {latest.warnings === 1 ? "warning" : "warnings"}</span>}</div>
    </div>
  </article>;
}

export default function ProjectWorkspace({ projectId, onOpenConcept, onEditBrief, onBack, onOpenBrand, activeJobId = null, onJobSettled }: ProjectWorkspaceProps) {
  const [project, setProject] = useState<WorkspaceProject | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refresh, setRefresh] = useState(0);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setProject((current) => current?.id === projectId ? current : null);
    setError(null);
    setLoading(true);
    loadProject(projectId)
      .then((data) => { if (!cancelled) setProject(data); })
      .catch((e: unknown) => { if (!cancelled) setError(e instanceof Error ? e.message : String(e)); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [projectId, refresh]);

  useEffect(() => {
    setJob(null);
    if (!activeJobId) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const tick = async () => {
      let settled = false;
      try {
        const [nextJob, nextProject] = await Promise.all([api.job(activeJobId), loadProject(projectId)]);
        if (cancelled) return;
        // Only the scoped project endpoint supplies artwork; a global job never
        // supplies another campaign's concept cards to this workspace.
        const jobProject = (nextJob as Job & { project_id?: string | null }).project_id;
        if (jobProject !== projectId) {
          setJob(null);
          return;
        }
        setJob(nextJob);
        setProject(nextProject);
        setError(null);
        settled = nextJob.status === "done" || nextJob.status === "failed";
        if (settled) onJobSettled?.();
      } catch (e: unknown) {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      }
      if (!cancelled && !settled) timer = setTimeout(tick, 4000);
    };
    void tick();
    return () => { cancelled = true; if (timer) clearTimeout(timer); };
  }, [activeJobId, projectId, onJobSettled]);

  const concepts = project?.concepts.filter((concept) => !concept.discarded) ?? [];
  const proofCount = concepts.filter((concept) => concept.latest?.has_proof).length;
  const failedCount = concepts.filter((concept) => !concept.latest && concept.failure).length;
  const pendingCount = concepts.filter((concept) => !concept.latest && !concept.failure).length;
  const latestWarnings = concepts.reduce((sum, concept) => sum + (concept.latest?.warnings ?? 0), 0);
  const requiredCopy = project?.brief?.mandatoryCopy ?? [];

  return <div className="space-y-7 pb-8">
    <button onClick={onBack} className={`text-sm text-ink-soft transition hover:text-ink ${focus}`}><span aria-hidden="true" className="mr-2">←</span> Back</button>
    {error && <div role="alert" className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-brand/25 bg-brand/5 p-4 text-sm text-brand"><p>{error}</p><button onClick={() => setRefresh((n) => n + 1)} className={`font-semibold underline underline-offset-4 ${focus}`}>Try again</button></div>}
    {loading && !project && <p role="status" className="py-12 text-ink-soft">Opening project…</p>}
    {project && <>
      <section className="border-b border-ink/10 pb-7">
        <div className="mb-4 flex flex-wrap items-center gap-2 text-xs text-ink-soft">
          {project.brand && onOpenBrand ? <button onClick={() => onOpenBrand(project.brand!)} className={`rounded-full border border-ink/15 bg-paper px-3 py-1.5 transition hover:border-ink/40 ${focus}`}>{project.brand}</button> : <span className="rounded-full border border-ink/15 bg-paper px-3 py-1.5">{project.brand || "Brand not assigned"}</span>}
          {project.campaign_name && <><span aria-hidden="true">/</span><span>{project.campaign_name}</span></>}
          <span className="ml-auto capitalize">{project.status} project</span>
        </div>
        <div className="flex flex-col justify-between gap-5 sm:flex-row sm:items-end"><div className="min-w-0"><p className="mb-2 text-xs font-semibold uppercase tracking-[0.18em] text-ink-soft">Project workspace</p><h1 className="break-words font-serif text-3xl leading-tight sm:text-4xl">{project.name}</h1><p className="mt-3 text-sm text-ink-soft">{formatLabel(project)} <span className="mx-2 text-ink/25">·</span> {project.brand_version == null ? "No brand profile pinned" : `Brand profile v${project.brand_version}`}</p></div><button onClick={() => onEditBrief(projectId)} className={`shrink-0 rounded-full bg-ink px-5 py-2.5 text-sm font-semibold text-paper transition hover:bg-ink-soft ${focus}`}>{project.brief?.title ? "Edit brief & generate" : "Write the brief"}</button></div>
      </section>

      {job && job.status !== "done" && <div role="status" className={`rounded-xl border p-4 text-sm ${job?.status === "failed" ? "border-brand/20 bg-brand/5 text-brand" : "border-amber-200 bg-amber-50 text-amber-900"}`}>{job?.status === "failed" ? `Generation stopped: ${job.error || "Open the affected concept for details."}` : <><span className="mr-2 inline-block h-2 w-2 animate-pulse rounded-full bg-amber-500" />Creating artwork{job ? ` · ${job.concepts.filter((concept) => concept.latest || concept.failure).length} of ${job.n} concepts complete` : "…"}. Proofs will appear here.</>}</div>}

      <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_280px]">
        <section aria-labelledby="project-artworks-heading" className="min-w-0">
          <div className="mb-5 flex items-end justify-between gap-4"><div><h2 id="project-artworks-heading" className="font-serif text-2xl">Artwork</h2><p className="mt-1 text-xs text-ink-soft">{concepts.length} {concepts.length === 1 ? "concept" : "concepts"} · {proofCount} with proofs{pendingCount ? ` · ${pendingCount} awaiting proof` : ""}{failedCount ? ` · ${failedCount} failed` : ""}</p></div><button onClick={() => setRefresh((n) => n + 1)} disabled={loading} className={`text-xs text-ink-soft underline decoration-ink/25 underline-offset-4 hover:text-ink disabled:opacity-50 ${focus}`}>Refresh artwork</button></div>
          {concepts.length ? <div className="grid gap-5 sm:grid-cols-2">{concepts.map((concept) => <ArtworkCard key={concept.id} concept={concept} onOpen={() => onOpenConcept(concept.id)} />)}</div> : <div className="rounded-2xl border border-dashed border-ink/20 bg-paper/70 px-6 py-16 text-center"><h3 className="font-serif text-2xl">The next idea starts here.</h3><p className="mx-auto mt-3 max-w-sm text-sm leading-relaxed text-ink-soft">Check the brief, choose your images and generate the first concepts for this project.</p><button onClick={() => onEditBrief(projectId)} className={`mt-6 rounded-full border border-ink/20 bg-paper px-5 py-2.5 text-sm font-semibold transition hover:border-ink/50 ${focus}`}>Open the brief</button></div>}
        </section>

        <aside className="space-y-5 lg:pt-1" aria-label="Project brief summary">
          <div className="rounded-2xl border border-ink/10 bg-paper p-5"><h2 className="font-serif text-xl">At a glance</h2><dl className="mt-5 space-y-4 text-sm"><div><dt className="text-xs text-ink-soft">Brief</dt><dd className="mt-1 leading-snug">{project.brief?.title || "No brief saved"}</dd></div><div><dt className="text-xs text-ink-soft">Headline</dt><dd className="mt-1 leading-snug">{project.brief?.copy?.headline || "Not set"}</dd></div>{requiredCopy.length > 0 && <div><dt className="text-xs text-ink-soft">Required wording</dt><dd className="mt-1 space-y-1">{requiredCopy.map((text, index) => <p key={index}>{text}</p>)}</dd></div>}<div><dt className="text-xs text-ink-soft">Selected images</dt><dd className="mt-1">{project.brief?.references?.imageAssets?.length ?? 0} in this brief</dd></div></dl><button onClick={() => onEditBrief(projectId)} className={`mt-5 text-sm font-semibold underline decoration-ink/25 underline-offset-4 ${focus}`}>View full brief <span aria-hidden="true">↗</span></button></div>
          <div className="rounded-2xl border border-ink/10 px-5 py-5 text-sm leading-relaxed text-ink-soft"><h2 className="mb-2 font-semibold text-ink">Review before sharing</h2><p>{latestWarnings ? `${latestWarnings} ${latestWarnings === 1 ? "warning remains" : "warnings remain"} across the latest proofs. ` : ""}Check the artwork against the brief and brand guidance. An AI check is separate from studio or client approval.</p></div>
        </aside>
      </div>
      <ReviewManager projectId={projectId} concepts={concepts}/>
    </>}
  </div>;
}
