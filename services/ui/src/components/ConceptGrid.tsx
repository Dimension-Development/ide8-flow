import { useEffect, useState } from "react";
import { api, type Concept, type Job } from "../api";
import { ApprovalBadge, Cost, OriginBadge } from "./Badges";

export default function ConceptGrid({
  onOpen,
  activeJobId,
  onJobSettled,
}: {
  onOpen: (id: string) => void;
  activeJobId: string | null;
  onJobSettled: () => void;
}) {
  const [concepts, setConcepts] = useState<Concept[] | null>(null);
  const [showDiscarded, setShowDiscarded] = useState(false);
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = (incl: boolean) =>
    api
      .concepts(incl)
      .then((d) => setConcepts(d.concepts))
      .catch((e) => setError(String(e)));

  useEffect(() => {
    load(showDiscarded);
  }, [showDiscarded]);

  // While a fan-out job runs, poll it and refresh the grid so concept
  // cards appear as each one lands (BRF-1 live-fill UX).
  useEffect(() => {
    if (!activeJobId) return;
    const tick = async () => {
      try {
        const j = await api.job(activeJobId);
        setJob(j);
        await load(showDiscarded);
        if (j.status === "done" || j.status === "failed") onJobSettled();
      } catch {
        /* transient — keep polling */
      }
    };
    tick();
    const t = setInterval(tick, 4000);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeJobId, showDiscarded]);

  if (error)
    return (
      <p className="text-brand">
        Worker API unreachable — is it running on :8200? ({error})
      </p>
    );
  if (!concepts) return <p className="text-ink-soft">Loading proof grid…</p>;

  const briefTitles = new Set(concepts.map((c) => c.brief?.title ?? "Untitled brief"));
  const briefTitle = briefTitles.size > 1
    ? "Artwork across briefs"
    : concepts[0]?.brief?.title ?? "Untitled brief";

  return (
    <div>
      {(activeJobId || job?.status === "failed") && (
        <div
          className={`mb-6 rounded-lg border p-3 text-sm ${
            job?.status === "failed"
              ? "border-brand/40 bg-brand/5 text-brand"
              : "border-amber-300 bg-amber-50 text-amber-900"
          }`}
        >
          {job?.status === "failed" ? (
            <>Fan-out failed: {job.error}</>
          ) : (
            <>
              <span className="mr-2 inline-block h-2 w-2 animate-pulse rounded-full bg-amber-500" />
              Generating {job?.n ?? "…"} concepts — proofs appear below as
              each one finishes (
              {job?.concepts?.filter((c) => c.latest).length ?? 0} done)
            </>
          )}
        </div>
      )}
      <div className="mb-6 flex items-end justify-between">
        <div>
          <h1 className="font-serif text-3xl font-bold">{briefTitle}</h1>
          <p className="mt-1 text-sm text-ink-soft">
            {concepts.filter((c) => !c.discarded).length} concepts ·{" "}
            {concepts.filter((c) => c.latest?.approved).length} approved by
            self-critique
          </p>
        </div>
        <label className="flex cursor-pointer items-center gap-2 text-sm text-ink-soft">
          <input
            type="checkbox"
            checked={showDiscarded}
            onChange={(e) => setShowDiscarded(e.target.checked)}
          />
          show discarded
        </label>
      </div>

      <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
        {concepts.map((c) => (
          <ConceptCard
            key={c.id}
            concept={c}
            onOpen={() => onOpen(c.id)}
            onCurate={async () => {
              await (c.discarded ? api.restore(c.id) : api.discard(c.id));
              load(showDiscarded);
            }}
          />
        ))}
      </div>
    </div>
  );
}

function NoProof({ concept: c }: { concept: Concept }) {
  // A concept can lack a proof two ways: the whole run died before storing
  // a version (concept.failure carries the reason), or the latest stored
  // version failed validation pre-proof (error codes on the summary).
  const reason = c.failure
    ? c.failure.error
    : c.latest && c.latest.error_codes.length > 0
      ? `validation failed: ${c.latest.error_codes.join(", ")}`
      : null;
  return (
    <span className="px-4 text-center text-sm text-ink-soft">
      {reason ? (
        <>
          <span className="mb-1 block font-medium text-brand">
            generation failed
          </span>
          {reason}
        </>
      ) : (
        "no proof"
      )}
    </span>
  );
}

function ConceptCard({
  concept: c,
  onOpen,
  onCurate,
}: {
  concept: Concept;
  onOpen: () => void;
  onCurate: () => void;
}) {
  const archetypeName = c.archetype.split(":")[0];
  return (
    <div
      className={`group overflow-hidden rounded-xl border border-ink/10 bg-paper shadow-sm transition hover:shadow-md ${
        c.discarded ? "opacity-50" : ""
      }`}
    >
      <button
        onClick={onOpen}
        aria-label={`Open ${c.brief?.title ?? "Untitled brief"} — ${archetypeName}`}
        className="block w-full"
      >
        <div className="flex aspect-[3/4] items-center justify-center bg-ink/5 p-3">
          {c.latest?.has_proof ? (
            <img
              src={api.thumbUrl(c.latest.id)}
              alt={archetypeName}
              className="max-h-full max-w-full rounded shadow"
              loading="lazy"
            />
          ) : (
            <NoProof concept={c} />
          )}
        </div>
      </button>
      <div className="space-y-2 p-4">
        <p className="text-sm text-ink-soft">{c.brief?.title ?? "Untitled brief"}</p>
        <div className="flex items-center justify-between gap-2">
          <h3 className="truncate font-semibold">{archetypeName}</h3>
          <Cost usd={c.latest?.cost_usd ?? c.failure?.cost_usd} />
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {c.latest && <ApprovalBadge approved={c.latest.approved} />}
          {c.latest && <OriginBadge origin={c.latest.origin} />}
          {c.latest && c.latest.warnings > 0 && (
            <span className="text-xs text-amber-700">
              {c.latest.warnings} warning(s)
            </span>
          )}
          <button
            onClick={onCurate}
            className="ml-auto text-xs text-ink-soft underline-offset-2 hover:underline"
          >
            {c.discarded ? "restore" : "discard"}
          </button>
        </div>
      </div>
    </div>
  );
}
