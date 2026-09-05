import { useEffect, useState } from "react";
import { api, type BrandSummary, type Project, type Swatch } from "../api";

type StudioProject = Project & {
  concepts?: number;
  created_at?: string;
  updated_at?: string;
  campaign_name?: string | null;
};
type StudioBrand = BrandSummary & { identity?: { brandName?: string } };

export interface StudioHomeProps {
  onOpenBrand: (name: string) => void;
  onOpenProject: (id: string) => void;
  onCreateBrand?: () => void;
  onNewBrief?: () => void;
}

const focus = "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-4";

function swatchColour(swatch: Swatch): string | null {
  const v = swatch.values;
  if (!v.every(Number.isFinite)) return null;
  if (swatch.space === "rgb" && v.length === 3) {
    return `rgb(${v.map((n) => Math.max(0, Math.min(255, n))).join(" ")})`;
  }
  if (swatch.space === "cmyk" && v.length === 4) {
    const [c, m, y, k] = v.map((n) => Math.max(0, Math.min(100, n)) / 100);
    return `rgb(${[c, m, y].map((n) => Math.round(255 * (1 - n) * (1 - k))).join(" ")})`;
  }
  return null;
}

function displayDate(value?: string): string | null {
  if (!value) return null;
  const date = new Date(value.includes("T") ? value : value.replace(" ", "T") + "Z");
  return Number.isNaN(date.getTime()) ? null : date.toLocaleDateString("en-GB", {
    day: "numeric", month: "short", year: "numeric",
  });
}

function Arrow() {
  return <svg viewBox="0 0 24 24" fill="none" aria-hidden="true" className="h-5 w-5 shrink-0"><path d="M5 12h14m-6-6 6 6-6 6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" /></svg>;
}

export default function StudioHome({ onOpenBrand, onOpenProject, onCreateBrand, onNewBrief }: StudioHomeProps) {
  const [data, setData] = useState<{ brands: StudioBrand[]; projects: StudioProject[] } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refresh, setRefresh] = useState(0);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    Promise.all([api.brands(), api.projects()])
      .then(([brands, projects]) => {
        if (!cancelled) setData({ brands: brands.brands, projects: projects.projects });
      })
      .catch((e: unknown) => { if (!cancelled) setError(e instanceof Error ? e.message : String(e)); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [refresh]);

  const projects = [...(data?.projects ?? [])].sort((a, b) =>
    (b.updated_at ?? b.created_at ?? "").localeCompare(a.updated_at ?? a.created_at ?? ""));
  const activeProjects = projects.filter((project) => project.status === "active");
  const artworkCount = activeProjects.every((project) => typeof project.concepts === "number")
    ? activeProjects.reduce((sum, project) => sum + (project.concepts ?? 0), 0) : null;

  return (
    <div className="space-y-12 pb-8">
      <section className="flex flex-col justify-between gap-6 border-b border-ink/10 pb-9 sm:flex-row sm:items-end">
        <div>
          <p className="mb-3 text-xs font-semibold uppercase tracking-[0.2em] text-ink-soft">Studio overview</p>
          <h1 className="font-serif text-4xl font-medium tracking-tight sm:text-5xl">Your studio.</h1>
          <p className="mt-3 max-w-xl text-base leading-relaxed text-ink-soft">Start with a brand. Pick up a project. Make something worth sharing.</p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          {onCreateBrand && <button onClick={onCreateBrand} className={`rounded-full border border-ink/20 bg-paper px-5 py-2.5 text-sm font-semibold transition hover:border-ink/50 ${focus}`}>Add a brand</button>}
          {onNewBrief && <button onClick={onNewBrief} className={`flex items-center gap-3 rounded-full bg-ink px-5 py-2.5 text-sm font-semibold text-paper transition hover:bg-ink-soft ${focus}`}>New brief <Arrow /></button>}
        </div>
      </section>

      {error && <div role="alert" className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-brand/25 bg-brand/5 p-4 text-sm text-brand"><p>We couldn’t load the studio. {error}</p><button onClick={() => setRefresh((n) => n + 1)} className={`font-semibold underline underline-offset-4 ${focus}`}>Try again</button></div>}
      {!data && loading && <p role="status" className="py-12 text-ink-soft">Opening your studio…</p>}

      {data && <>
        <div className="flex flex-wrap items-center gap-x-7 gap-y-3 text-sm text-ink-soft">
          <span><strong className="mr-1 text-ink">{data.brands.length}</strong> {data.brands.length === 1 ? "brand" : "brands"}</span>
          <span><strong className="mr-1 text-ink">{activeProjects.length}</strong> active {activeProjects.length === 1 ? "project" : "projects"}</span>
          {artworkCount !== null && <span><strong className="mr-1 text-ink">{artworkCount}</strong> artwork {artworkCount === 1 ? "concept" : "concepts"}</span>}
          <button onClick={() => setRefresh((n) => n + 1)} disabled={loading} className={`ml-auto text-xs underline decoration-ink/25 underline-offset-4 hover:text-ink disabled:opacity-50 ${focus}`}>{loading ? "Refreshing…" : "Refresh studio"}</button>
        </div>

        <section aria-labelledby="studio-brands-heading">
          <div className="mb-5 flex items-baseline justify-between gap-4"><h2 id="studio-brands-heading" className="font-serif text-2xl">Your brands</h2><span className="text-xs text-ink-soft">Guidance, assets and campaigns</span></div>
          {data.brands.length ? <div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-3">
            {data.brands.map((brand) => {
              const brandProjects = activeProjects.filter((project) => project.brand === brand.name);
              const colours = brand.swatches.map((swatch) => ({ swatch, colour: swatchColour(swatch) })).filter((s) => s.colour !== null);
              return <button key={brand.name} onClick={() => onOpenBrand(brand.name)} className={`group flex min-h-60 flex-col overflow-hidden rounded-2xl border border-ink/10 bg-paper text-left transition hover:-translate-y-0.5 hover:border-ink/25 hover:shadow-lg hover:shadow-ink/5 ${focus}`}>
                <div className="flex flex-1 flex-col p-6">
                  <div className="mb-8 flex items-center justify-between gap-3"><span className="rounded-full border border-ink/10 px-2.5 py-1 text-[11px] font-medium text-ink-soft">Brand profile · v{brand.version}</span><span className="text-ink/40 transition group-hover:translate-x-1 group-hover:text-ink"><Arrow /></span></div>
                  <h3 className="break-words font-serif text-2xl leading-tight">{brand.identity?.brandName || brand.name}</h3>
                  <p className="mt-2 text-sm text-ink-soft">{brandProjects.length} active {brandProjects.length === 1 ? "project" : "projects"} <span className="mx-1.5 text-ink/25">·</span> {brand.designPrinciples ? "Guidance saved" : "Guidance to add"}</p>
                  <div className="mt-6 flex items-center justify-between gap-3">
                    <div className="flex items-center -space-x-1.5" aria-label={colours.length ? `${colours.length} saved colours; approximate screen previews` : "No saved colours"}>
                      {colours.slice(0, 6).map(({ swatch, colour }) => <span key={swatch.name} title={`${swatch.name} — screen approximation`} className="h-7 w-7 rounded-full border-2 border-paper shadow-sm" style={{ backgroundColor: colour! }} />)}
                      {!colours.length && <span className="text-xs text-ink-soft">No colours added</span>}
                    </div>
                    <span className="text-xs text-ink-soft">{brand.fonts.length} {brand.fonts.length === 1 ? "font" : "fonts"}</span>
                  </div>
                </div>
              </button>;
            })}
          </div> : <div className="rounded-2xl border border-dashed border-ink/20 bg-paper/60 px-6 py-12 text-center"><h3 className="font-serif text-xl">Give your first brand a home.</h3><p className="mx-auto mt-2 max-w-md text-sm leading-relaxed text-ink-soft">Bring its guidance, colours and type together before starting a project.</p>{onCreateBrand && <button onClick={onCreateBrand} className={`mt-5 rounded-full bg-ink px-5 py-2.5 text-sm font-semibold text-paper ${focus}`}>Add your first brand</button>}</div>}
        </section>

        <section aria-labelledby="studio-projects-heading">
          <div className="mb-5 flex items-baseline justify-between gap-4"><h2 id="studio-projects-heading" className="font-serif text-2xl">Recent projects</h2><span className="text-xs text-ink-soft">{Math.min(projects.length, 8)} of {projects.length}</span></div>
          {projects.length ? <div className="overflow-hidden rounded-2xl border border-ink/10 bg-paper">
            {projects.slice(0, 8).map((project) => {
              const date = displayDate(project.updated_at ?? project.created_at);
              return <button key={project.id} onClick={() => onOpenProject(project.id)} className={`group flex w-full items-center gap-4 border-b border-ink/10 px-5 py-5 text-left transition last:border-0 hover:bg-cream/60 sm:px-6 ${focus}`}>
                <span className="hidden h-12 w-10 shrink-0 items-center justify-center rounded-md border border-ink/15 bg-cream text-ink/40 sm:flex" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" className="h-5 w-5"><path d="M7 4h10v16H7zM10 9h4m-4 3h4m-4 3h3" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" /></svg></span>
                <span className="min-w-0 flex-1"><span className="mb-1 block text-xs text-ink-soft">{project.brand || "Brand not assigned"}{project.campaign_name ? ` / ${project.campaign_name}` : ""}</span><span className="block break-words font-semibold leading-snug">{project.name}</span>{date && <span className="mt-1 block text-xs text-ink-soft sm:hidden">Updated {date}</span>}</span>
                <span className="hidden text-right sm:block"><span className="block text-sm text-ink-soft">{typeof project.concepts === "number" ? `${project.concepts} ${project.concepts === 1 ? "concept" : "concepts"}` : "Open project"}</span>{date && <span className="mt-1 block text-xs text-ink-soft/75">Updated {date}</span>}</span>
                <span className="ml-2 text-ink/35 transition group-hover:translate-x-1 group-hover:text-ink"><Arrow /></span>
              </button>;
            })}
          </div> : <div className="rounded-2xl border border-ink/10 bg-paper px-6 py-9"><h3 className="font-serif text-xl">Ready for your first project.</h3><p className="mt-2 text-sm text-ink-soft">Open a brand to start a campaign and save its brief here.</p></div>}
        </section>
      </>}
    </div>
  );
}
