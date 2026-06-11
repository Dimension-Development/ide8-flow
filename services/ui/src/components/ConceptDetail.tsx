import { useEffect, useMemo, useState } from "react";
import {
  api,
  type ConceptDetail as Detail,
  type MutationResponse,
  type Version,
} from "../api";
import { ApprovalBadge, Cost, OriginBadge } from "./Badges";

export default function ConceptDetail({
  conceptId,
  onBack,
}: {
  conceptId: string;
  onBack: () => void;
}) {
  const [detail, setDetail] = useState<Detail | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [mutation, setMutation] = useState<MutationResponse | null>(null);

  const load = () =>
    api.concept(conceptId).then((d) => {
      setDetail(d);
      setSelectedId((cur) => cur ?? d.versions[d.versions.length - 1]?.id);
    });

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conceptId]);

  const selected = useMemo(
    () => detail?.versions.find((v) => v.id === selectedId) ?? null,
    [detail, selectedId],
  );

  if (!detail) return <p className="text-ink-soft">Loading concept…</p>;

  return (
    <div>
      <button
        onClick={onBack}
        className="mb-4 text-sm text-ink-soft hover:text-ink"
      >
        ← back to grid
      </button>
      <h1 className="mb-1 font-serif text-2xl font-bold">
        {detail.archetype.split(":")[0]}
      </h1>
      <p className="mb-6 max-w-3xl text-sm text-ink-soft">
        {detail.archetype.split(":").slice(1).join(":").trim()}
      </p>

      <div className="grid grid-cols-1 gap-8 lg:grid-cols-[1fr_360px]">
        <div>
          {mutation && selected && (
            <BeforeAfter mutation={mutation} detail={detail} />
          )}
          {!mutation && selected?.has_proof && (
            <a
              href={api.proofUrl(selected.id)}
              target="_blank"
              rel="noreferrer"
              title="open full size"
            >
              <img
                src={api.proofUrl(selected.id)}
                alt="proof"
                className="mx-auto max-h-[75vh] rounded-lg shadow-lg"
              />
            </a>
          )}
        </div>

        <aside className="space-y-6">
          {selected && (
            <div className="flex gap-2">
              <DownloadLink href={api.slaUrl(selected.id)} label=".sla" />
              <DownloadLink href={api.documentUrl(selected.id)} label=".json" />
              {selected.has_proof && (
                <DownloadLink
                  href={api.proofUrl(selected.id)}
                  label="proof.png"
                />
              )}
            </div>
          )}
          <MutateBox
            selected={selected}
            onDone={(m) => {
              setMutation(m);
              setSelectedId(m.version_id);
              load();
            }}
          />
          <VersionTimeline
            versions={detail.versions}
            selectedId={selectedId}
            onSelect={(id) => {
              setSelectedId(id);
              setMutation(null);
            }}
          />
        </aside>
      </div>
    </div>
  );
}

function DownloadLink({ href, label }: { href: string; label: string }) {
  // EXP-1: the escape hatch — a designer is never blocked by the tool.
  return (
    <a
      href={href}
      download
      className="flex-1 rounded-lg border border-ink/15 bg-paper px-3 py-2 text-center text-xs font-semibold text-ink transition hover:border-ink/40"
    >
      ↓ {label}
    </a>
  );
}

function BeforeAfter({
  mutation,
  detail,
}: {
  mutation: MutationResponse;
  detail: Detail;
}) {
  return (
    <div>
      <div className="mb-3 rounded-lg border border-violet-200 bg-violet-50 p-3 text-sm">
        Mutation applied in {mutation.iterations} iteration(s) —{" "}
        {mutation.diff.length} change(s)
        {mutation.cost_usd != null && <> · ${mutation.cost_usd.toFixed(3)}</>}
        <details className="mt-1">
          <summary className="cursor-pointer text-violet-800">
            changed paths
          </summary>
          <ul className="mt-1 max-h-32 overflow-auto font-mono text-xs">
            {mutation.diff.slice(0, 30).map((d, i) => (
              <li key={i}>
                {d.change} {d.path}
              </li>
            ))}
          </ul>
        </details>
      </div>
      <div className="grid grid-cols-2 gap-4">
        {[mutation.parent_version_id, mutation.version_id].map((id, i) => (
          <figure key={id}>
            <figcaption className="mb-1 text-center text-xs font-semibold uppercase tracking-wide text-ink-soft">
              {i === 0 ? "before" : "after"}
            </figcaption>
            <img
              src={api.proofUrl(id)}
              alt={i === 0 ? "before" : "after"}
              className="rounded-lg shadow"
            />
          </figure>
        ))}
      </div>
      {void detail}
    </div>
  );
}

function MutateBox({
  selected,
  onDone,
}: {
  selected: Version | null;
  onDone: (m: MutationResponse) => void;
}) {
  const [instruction, setInstruction] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!selected) return null;

  const submit = async () => {
    if (!instruction.trim()) return;
    setBusy(true);
    setError(null);
    try {
      onDone(await api.mutate(selected.id, instruction.trim()));
      setInstruction("");
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="rounded-xl border border-ink/10 bg-paper p-4 shadow-sm">
      <h2 className="mb-2 font-semibold">Refine this version</h2>
      <textarea
        value={instruction}
        onChange={(e) => setInstruction(e.target.value)}
        rows={3}
        placeholder='e.g. "Swap the headline band to DeepInk with Cream type, keep everything else"'
        className="w-full rounded-lg border border-ink/15 bg-white p-2 text-sm outline-none focus:border-brand"
        disabled={busy}
      />
      <button
        onClick={submit}
        disabled={busy || !instruction.trim()}
        className="mt-2 w-full rounded-lg bg-ink px-4 py-2 text-sm font-semibold text-cream transition hover:bg-ink-soft disabled:opacity-40"
      >
        {busy ? "Mutating — validating & rendering (≈1 min)…" : "Mutate"}
      </button>
      {error && <p className="mt-2 text-xs text-brand">{error}</p>}
    </div>
  );
}

function VersionTimeline({
  versions,
  selectedId,
  onSelect,
}: {
  versions: Version[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  const newestFirst = [...versions].reverse();
  return (
    <div className="rounded-xl border border-ink/10 bg-paper p-4 shadow-sm">
      <h2 className="mb-3 font-semibold">Version history</h2>
      <ol className="space-y-3">
        {newestFirst.map((v, i) => (
          <li key={v.id}>
            <button
              onClick={() => onSelect(v.id)}
              className={`w-full rounded-lg border p-3 text-left transition ${
                v.id === selectedId
                  ? "border-brand bg-brand/5"
                  : "border-ink/10 hover:border-ink/30"
              }`}
            >
              <div className="flex items-center gap-2">
                <span className="font-mono text-xs text-ink-soft">
                  v{versions.length - i}
                </span>
                <ApprovalBadge approved={v.approved} />
                <OriginBadge origin={v.origin} />
                <span className="ml-auto">
                  <Cost usd={v.usage?.cost_usd} />
                </span>
              </div>
              {v.mutation_instruction && (
                <p className="mt-1 line-clamp-2 text-xs italic text-ink-soft">
                  “{v.mutation_instruction}”
                </p>
              )}
              <p className="mt-1 font-mono text-[10px] text-ink-soft/70">
                {v.content_hash.slice(0, 16)} · {v.created_at}
              </p>
            </button>
          </li>
        ))}
      </ol>
    </div>
  );
}
