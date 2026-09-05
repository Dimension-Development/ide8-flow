import { useEffect, useId, useRef, useState } from "react";
import { workspaceApi, type IdentityCard, type IdentityDraft, type IdentitySource } from "../api";

type CandidateCard = IdentityCard & {
  confidence?: "high" | "medium" | "low";
  source?: NonNullable<IdentityCard["source"]> & { quote?: string };
};
type ExtractionRun = {
  id: string;
  source_id: string;
  filename: string;
  status: "queued" | "running" | "done" | "failed";
  pages: number[];
  completed_pages: number;
  error: string | null;
  cards: CandidateCard[];
  usage: { calls: number; cost_usd: number };
  created_at: string;
};

export interface PdfExtractionProps {
  name: string;
  sources: IdentitySource[];
  disabled?: boolean;
  onImported: () => void;
}

class ExtractionError extends Error {
  constructor(message: string, readonly status: number) { super(message); }
}

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, options);
  if (!response.ok) {
    let detail = `Request failed (${response.status}).`;
    try {
      const body: { detail?: unknown } = await response.json();
      if (typeof body.detail === "string") detail = body.detail;
    } catch { /* Keep the useful status if the server did not return JSON. */ }
    throw new ExtractionError(detail, response.status);
  }
  return response.json() as Promise<T>;
}

function message(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function isActive(run: ExtractionRun): boolean {
  return run.status === "queued" || run.status === "running";
}

function rangeError(value: string, pageCount?: number): string | null {
  if (!value.trim()) return null;
  if (!/^\s*\d+\s*(?:-\s*\d+\s*)?(?:,\s*\d+\s*(?:-\s*\d+\s*)?)*$/.test(value)) {
    return "Use page numbers and ranges, such as 21, 56-59, 107.";
  }
  for (const part of value.split(",")) {
    const [start, end = start] = part.split("-").map(Number);
    if (!Number.isSafeInteger(start) || !Number.isSafeInteger(end) || start < 1 || end < start) {
      return "Page numbers start at 1. Put the lower number first in each range.";
    }
    if (pageCount !== undefined && end > pageCount) return `This PDF has ${pageCount} pages. Choose pages within that range.`;
  }
  return null;
}

function runLabel(run: ExtractionRun): string {
  const date = new Date(run.created_at.includes("T") ? run.created_at : run.created_at.replace(" ", "T") + "Z");
  const when = Number.isNaN(date.getTime()) ? "" : ` · ${date.toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}`;
  const status = { queued: "Queued", running: "Reading", done: "Ready to review", failed: "Stopped" }[run.status];
  return `${run.filename}${when} · ${status}`;
}

function sourceHref(brand: string, run: ExtractionRun, card: CandidateCard): string {
  // Resolve the uploaded document ourselves: model-provided URLs cannot
  // introduce an unrelated destination or executable scheme into a citation.
  const page = card.source?.page;
  return workspaceApi.sourceUrl(brand, run.source_id) +
    (typeof page === "number" && Number.isInteger(page) && page > 0 ? `#page=${page}` : "");
}

const field = "w-full rounded-lg border border-ink/20 bg-paper px-3 py-2.5 text-sm outline-none focus:border-ink focus:ring-1 focus:ring-ink disabled:opacity-50";
const focus = "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2";

export default function PdfExtraction({ name, sources, disabled = false, onImported }: PdfExtractionProps) {
  const formId = useId();
  const brandPath = `/api/brands/${encodeURIComponent(name)}`;
  const pdfs = sources.filter((source) => source.mime === "application/pdf");
  const [sourceId, setSourceId] = useState("");
  const [pages, setPages] = useState("");
  const [pageCounts, setPageCounts] = useState<Record<string, number>>({});
  const [inspecting, setInspecting] = useState(false);
  const [runs, setRuns] = useState<ExtractionRun[]>([]);
  const [selectedRunId, setSelectedRunId] = useState("");
  const [selections, setSelections] = useState<Record<string, string[]>>({});
  const [loading, setLoading] = useState(true);
  const [starting, setStarting] = useState(false);
  const [importing, setImporting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [refresh, setRefresh] = useState(0);
  const currentBrand = useRef<string | null>(name);
  const parentDisabled = useRef(disabled);
  parentDisabled.current = disabled;

  useEffect(() => {
    currentBrand.current = name;
    setRuns([]);
    setSourceId("");
    setInspecting(false);
    setStarting(false);
    setImporting(false);
    setSelectedRunId("");
    setSelections({});
    setPageCounts({});
    setPages("");
    setError(null);
    setNotice(null);
    return () => { currentBrand.current = null; };
  }, [name]);

  useEffect(() => {
    if (!pdfs.some((source) => source.id === sourceId)) setSourceId(pdfs[0]?.id ?? "");
  }, [sources, sourceId]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setLoadError(null);
    request<{ extractions: ExtractionRun[] }>(`${brandPath}/extractions`)
      .then(({ extractions }) => {
        if (cancelled) return;
        const sorted = [...extractions].sort((a, b) => b.created_at.localeCompare(a.created_at));
        setRuns(sorted);
        setSelectedRunId((previous) => sorted.some((run) => run.id === previous) ? previous : sorted[0]?.id ?? "");
      })
      .catch((e: unknown) => { if (!cancelled) setLoadError(message(e)); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [brandPath, refresh]);

  // Restore the full saved run when a user reopens it. The server remains the
  // source of truth, so leaving this panel does not lose an extraction job.
  useEffect(() => {
    if (!selectedRunId) return;
    let cancelled = false;
    request<ExtractionRun>(`${brandPath}/extractions/${encodeURIComponent(selectedRunId)}`)
      .then((run) => {
        if (!cancelled) setRuns((current) => current.map((r) => r.id === run.id ? run : r));
      })
      .catch((e: unknown) => { if (!cancelled) setLoadError(message(e)); });
    return () => { cancelled = true; };
  }, [brandPath, selectedRunId]);

  const activeIds = runs.filter(isActive).map((run) => run.id).sort().join(",");
  useEffect(() => {
    if (!activeIds) return;
    let cancelled = false;
    let inFlight = false;
    const poll = async () => {
      if (inFlight) return;
      inFlight = true;
      try {
        const updates = await Promise.all(activeIds.split(",").map((id) =>
          request<ExtractionRun>(`${brandPath}/extractions/${encodeURIComponent(id)}`)));
        if (!cancelled) {
          setRuns((current) => current.map((run) => updates.find((update) => update.id === run.id) ?? run));
          setLoadError(null);
        }
      } catch (e: unknown) {
        if (!cancelled) setLoadError(`Couldn’t refresh progress. ${message(e)} Saved results are retained; retrying automatically.`);
      } finally { inFlight = false; }
    };
    const timer = setInterval(() => { void poll(); }, 3000);
    return () => { cancelled = true; clearInterval(timer); };
  }, [brandPath, activeIds]);

  const selectedRun = runs.find((run) => run.id === selectedRunId);
  const selectedIds = (selections[selectedRunId] ?? []).filter((id) => selectedRun?.cards.some((card) => card.id === id));
  const selectedSource = pdfs.find((source) => source.id === sourceId);
  const invalidRange = rangeError(pages, pageCounts[sourceId]);
  const busy = starting || importing;
  const canStart = !disabled && !busy && !!selectedSource && !invalidRange;
  const canImport = !disabled && !busy && !!selectedRun && !isActive(selectedRun) && selectedIds.length > 0;

  const inspect = async () => {
    if (!sourceId || inspecting) return;
    const requestedSource = sourceId;
    setInspecting(true);
    setError(null);
    try {
      const info = await request<{ pages: number }>(`${brandPath}/sources/${encodeURIComponent(requestedSource)}/pdf-info`);
      if (currentBrand.current === name) setPageCounts((current) => ({ ...current, [requestedSource]: info.pages }));
    } catch (e: unknown) { if (currentBrand.current === name) setError(message(e)); }
    finally { if (currentBrand.current === name) setInspecting(false); }
  };

  const start = async () => {
    if (!canStart || parentDisabled.current) return;
    setStarting(true);
    setError(null);
    setNotice(null);
    try {
      const run = await request<ExtractionRun>(`${brandPath}/extractions`, {
        method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({ source_id: sourceId, pages: pages.trim() }),
      });
      if (currentBrand.current !== name) return;
      setRuns((current) => [run, ...current.filter((r) => r.id !== run.id)]);
      setSelectedRunId(run.id);
      setSelections((current) => ({ ...current, [run.id]: [] }));
    } catch (e: unknown) { if (currentBrand.current === name) setError(message(e)); }
    finally { if (currentBrand.current === name) setStarting(false); }
  };

  const importCards = async () => {
    if (!canImport || !selectedRun || parentDisabled.current) return;
    const runId = selectedRun.id;
    const cardIds = [...selectedIds];
    setImporting(true);
    setError(null);
    setNotice(null);
    try {
      const draft = await workspaceApi.draft(name);
      if (currentBrand.current !== name) return;
      if (parentDisabled.current) {
        setError("Finish saving or editing the brand above before importing cards.");
        return;
      }
      await request<IdentityDraft>(`${brandPath}/extractions/${encodeURIComponent(runId)}/import`, {
        method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({ card_ids: cardIds, expected_revision: draft.revision }),
      });
      if (currentBrand.current !== name) return;
      setSelections((current) => ({ ...current, [runId]: [] }));
      setNotice("Selected guidance is now on the identity board. Review and publish the draft cards there before using them for generation.");
      onImported();
    } catch (e: unknown) {
      if (currentBrand.current === name) setError(e instanceof ExtractionError && e.status === 409
        ? "The identity board changed while importing. Refresh the board, then try importing your selected cards again."
        : message(e));
    } finally { if (currentBrand.current === name) setImporting(false); }
  };

  const toggleCard = (id: string) => {
    setSelections((current) => {
      const selected = current[selectedRunId] ?? [];
      return { ...current, [selectedRunId]: selected.includes(id) ? selected.filter((value) => value !== id) : [...selected, id] };
    });
  };

  return <section className="mt-8 space-y-6 rounded-2xl border border-ink/15 bg-paper p-5 sm:p-6" aria-labelledby={`${formId}-heading`}>
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div><h2 id={`${formId}-heading`} className="font-serif text-2xl">Read guidance from a PDF</h2><p className="mt-2 max-w-3xl text-sm leading-relaxed text-ink-soft">Turn source pages into guidance cards with their evidence attached. Choose what to bring onto the identity board, then review it there.</p></div>
      <span className="shrink-0 rounded-full border border-ink/15 px-3 py-1 text-xs text-ink-soft">Claude Opus 4.8</span>
    </div>

    {!pdfs.length ? <p className="rounded-lg bg-cream p-4 text-sm text-ink-soft">Upload a PDF in Sources above to begin. Uploaded fonts stay available as specimens.</p> : <div className="space-y-4 rounded-xl bg-cream/70 p-4">
      <div className="grid gap-4 sm:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)]">
        <div><label htmlFor={`${formId}-pdf`} className="mb-1.5 block text-sm font-semibold">Source PDF</label><select id={`${formId}-pdf`} className={field} value={sourceId} onChange={(e) => { setSourceId(e.target.value); setPages(""); setError(null); }} disabled={busy}>{pdfs.map((source) => <option key={source.id} value={source.id}>{source.filename}</option>)}</select><div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-ink-soft"><button type="button" onClick={() => { void inspect(); }} disabled={!sourceId || inspecting} className={`underline underline-offset-4 disabled:opacity-50 ${focus}`}>{inspecting ? "Counting pages…" : "Inspect page count"}</button>{pageCounts[sourceId] !== undefined && <span role="status">{pageCounts[sourceId]} pages</span>}{selectedSource && <a href={workspaceApi.sourceUrl(name, sourceId)} target="_blank" rel="noreferrer" className={`underline underline-offset-4 ${focus}`}>Open source PDF ↗</a>}</div></div>
        <div><label htmlFor={`${formId}-pages`} className="mb-1.5 block text-sm font-semibold">Pages to read</label><input id={`${formId}-pages`} className={field} value={pages} onChange={(e) => setPages(e.target.value)} placeholder="All pages, or 21, 56-59, 107" disabled={busy} aria-invalid={!!invalidRange} aria-describedby={`${formId}-page-hint`} /><p id={`${formId}-page-hint`} className={`mt-2 text-xs ${invalidRange ? "text-brand" : "text-ink-soft"}`}>{invalidRange || "Leave blank for all pages. A few relevant pages make a useful first check."}</p></div>
      </div>
      <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-center"><p className="max-w-xl text-xs leading-relaxed text-ink-soft">The model reads page images and extracted text. Suggested cards remain drafts; colours and font definitions are not changed automatically.</p><button type="button" onClick={() => { void start(); }} disabled={!canStart} className={`shrink-0 rounded-lg bg-ink px-4 py-2.5 text-sm font-semibold text-paper transition hover:bg-ink-soft disabled:cursor-not-allowed disabled:opacity-40 ${focus}`}>{starting ? "Starting extraction…" : "Extract guidance"}</button></div>
      {disabled && <p className="text-xs text-amber-800">Finish saving or editing the brand above before starting an extraction or importing cards.</p>}
    </div>}

    {error && <p role="alert" className="rounded-lg border border-brand/20 bg-brand/5 p-3 text-sm text-brand">{error}</p>}
    {notice && <p role="status" className="rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-900">{notice}</p>}
    {loadError && <div role="alert" className="flex flex-wrap items-center gap-3 rounded-lg border border-brand/20 bg-brand/5 p-3 text-sm text-brand"><p className="flex-1">{loadError}</p><button type="button" onClick={() => setRefresh((n) => n + 1)} className={`font-semibold underline underline-offset-4 ${focus}`}>Refresh saved extractions</button></div>}
    {loading && !runs.length && <p role="status" className="text-sm text-ink-soft">Loading saved extractions…</p>}

    {runs.length > 0 && <div className="space-y-5 border-t border-ink/10 pt-5">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-end"><div className="min-w-0 flex-1"><label htmlFor={`${formId}-runs`} className="mb-1.5 block text-sm font-semibold">Saved extractions</label><select id={`${formId}-runs`} className={field} value={selectedRunId} onChange={(e) => { setSelectedRunId(e.target.value); setError(null); setNotice(null); }} disabled={importing}>{runs.map((run) => <option key={run.id} value={run.id}>{runLabel(run)}</option>)}</select></div><button type="button" onClick={() => setRefresh((n) => n + 1)} disabled={loading} className={`self-start px-1 py-2.5 text-xs text-ink-soft underline underline-offset-4 disabled:opacity-50 sm:self-auto ${focus}`}>Refresh history</button></div>
      {selectedRun && <>
        <div className="rounded-xl border border-ink/10 p-4" aria-live="polite">
          <div className="flex flex-wrap items-center justify-between gap-2 text-sm"><p className="font-semibold">{selectedRun.status === "queued" ? "Queued for reading" : selectedRun.status === "running" ? "Reading your source pages" : selectedRun.status === "failed" ? "Extraction stopped" : "Ready for your review"}</p><span className="text-xs text-ink-soft">{selectedRun.completed_pages} of {selectedRun.pages.length} pages read</span></div>
          <progress value={selectedRun.completed_pages} max={Math.max(1, selectedRun.pages.length)} aria-label="Source pages read" className="mt-3 h-2 w-full accent-ink" />
          <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-soft"><span>{selectedRun.cards.length} candidate {selectedRun.cards.length === 1 ? "card" : "cards"}</span><span>{selectedRun.usage?.calls ?? 0} model {(selectedRun.usage?.calls ?? 0) === 1 ? "call" : "calls"}</span><span>Model cost ${(selectedRun.usage?.cost_usd ?? 0).toFixed(3)}</span></div>
          {selectedRun.error && <p role="alert" className="mt-3 break-words text-sm text-brand">{selectedRun.error}{selectedRun.cards.length > 0 ? " Cards already extracted are preserved below." : ""}</p>}
        </div>

        {selectedRun.cards.length > 0 ? <>
          <div className="flex flex-wrap items-center justify-between gap-3"><label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={selectedIds.length === selectedRun.cards.length} onChange={(e) => setSelections((current) => ({ ...current, [selectedRunId]: e.target.checked ? selectedRun.cards.map((card) => card.id) : [] }))} disabled={importing} className="h-4 w-4 accent-ink" /><span>Select all {selectedRun.cards.length} cards</span></label><span className="text-xs text-ink-soft">{selectedIds.length} selected · all candidates are drafts</span></div>
          <div className="grid gap-4 xl:grid-cols-2">
            {selectedRun.cards.map((card, index) => <article key={card.id} className={`rounded-xl border p-4 transition ${selectedIds.includes(card.id) ? "border-ink/40 bg-cream/50" : "border-ink/10 bg-paper"}`}>
              <div className="flex items-start gap-3"><input id={`${formId}-card-${index}`} type="checkbox" checked={selectedIds.includes(card.id)} onChange={() => toggleCard(card.id)} disabled={importing} className="mt-1 h-4 w-4 shrink-0 accent-ink" /><div className="min-w-0 flex-1"><div className="mb-1 flex flex-wrap items-center gap-2 text-[11px] text-ink-soft"><span className="capitalize">{card.category.replace(/[-_]/g, " ")}</span><span aria-hidden="true">·</span><span>Draft</span>{card.confidence && <span className={`ml-auto rounded-full px-2 py-0.5 ${card.confidence === "low" ? "bg-amber-100 text-amber-900" : "bg-ink/5 text-ink-soft"}`}>{card.confidence[0].toUpperCase() + card.confidence.slice(1)} confidence</span>}</div><label htmlFor={`${formId}-card-${index}`} className="cursor-pointer text-base font-semibold leading-snug">{card.title}</label><p className="mt-2 whitespace-pre-wrap break-words text-sm leading-relaxed text-ink-soft">{card.body}</p></div></div>
              <div className="ml-7 mt-3 space-y-2 text-xs leading-relaxed"><p><span className="font-semibold">Applies to: </span>{card.scope || "Scope needs review"}</p>{card.conditions && (Array.isArray(card.conditions) ? card.conditions.length > 0 : !!card.conditions.trim()) && <p><span className="font-semibold">Conditions: </span>{Array.isArray(card.conditions) ? card.conditions.join(" · ") : card.conditions}</p>}{card.source?.quote && <blockquote className="border-l-2 border-ink/15 pl-3 text-ink-soft">“{card.source.quote}”</blockquote>}<a href={sourceHref(name, selectedRun, card)} target="_blank" rel="noreferrer" className={`inline-block font-semibold text-ink-soft underline decoration-ink/25 underline-offset-4 hover:text-ink ${focus}`}>{card.source?.page ? `View source · page ${card.source.page}` : "View source PDF"} ↗</a></div>
            </article>)}
          </div>
          <div className="flex flex-col justify-between gap-3 rounded-xl bg-cream p-4 sm:flex-row sm:items-center"><p className="max-w-xl text-xs leading-relaxed text-ink-soft">{isActive(selectedRun) ? "You can choose cards as they arrive. Import them once this run finishes." : "Import adds draft cards to the identity board. Review their wording, scope and evidence, then publish the guidance before generation."}</p><button type="button" onClick={() => { void importCards(); }} disabled={!canImport} className={`shrink-0 rounded-lg bg-ink px-4 py-2.5 text-sm font-semibold text-paper transition hover:bg-ink-soft disabled:cursor-not-allowed disabled:opacity-40 ${focus}`}>{importing ? "Adding draft cards…" : `Add ${selectedIds.length || "selected"} ${selectedIds.length === 1 ? "card" : "cards"} to board`}</button></div>
        </> : !isActive(selectedRun) && <p className="py-4 text-sm text-ink-soft">No candidate cards were extracted from these pages. Check the source and page range before trying again.</p>}
      </>}
    </div>}
  </section>;
}
