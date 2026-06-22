import { useEffect, useState } from "react";
import { api, type BrandSummary, type Swatch } from "../api";

function swatchCss(s: Swatch): string {
  if (s.space === "rgb") {
    const [r, g, b] = s.values;
    return `rgb(${r}, ${g}, ${b})`;
  }
  const [c, m, y, k] = s.values.map((v) => v / 100);
  const r = Math.round(255 * (1 - c) * (1 - k));
  const g = Math.round(255 * (1 - m) * (1 - k));
  const b = Math.round(255 * (1 - y) * (1 - k));
  return `rgb(${r}, ${g}, ${b})`;
}

function SwatchChip({ s }: { s: Swatch }) {
  return (
    <div className="flex items-center gap-2">
      <span
        className="h-6 w-6 shrink-0 rounded border border-ink/15"
        style={{ background: swatchCss(s) }}
        title={`${s.space.toUpperCase()} ${s.values.join(", ")}`}
      />
      <span className="truncate text-xs">
        {s.name}
        {s.spot && (
          <span className="ml-1 rounded bg-ink/10 px-1 text-[10px] font-semibold uppercase">
            spot
          </span>
        )}
      </span>
    </div>
  );
}

export default function BrandsView() {
  const [brands, setBrands] = useState<BrandSummary[] | null>(null);
  const [def, setDef] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);

  const load = () =>
    api
      .brands()
      .then((d) => {
        setBrands(d.brands);
        setDef(d.default);
      })
      .catch((e) => setError(String(e)));

  useEffect(() => {
    load();
  }, []);

  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      const profile = JSON.parse(draft);
      await api.saveBrand(profile);
      setDraft("");
      await load();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  };

  const remove = async (name: string) => {
    setError(null);
    try {
      await api.deleteBrand(name);
      await load();
    } catch (e) {
      setError(String(e));
    }
  };

  const field =
    "w-full rounded-lg border border-ink/15 bg-white p-2 font-mono text-xs outline-none focus:border-brand";

  return (
    <div className="mx-auto max-w-4xl">
      <div className="mb-6">
        <h1 className="font-serif text-3xl font-bold">Brand profiles</h1>
        <p className="mt-1 text-sm text-ink-soft">
          Locked colour, type and rules the engine compiles against (BRAND-3).
          A brief selects one by name; unknown names fall back to the default
          <span className="font-semibold"> {def || "—"}</span>.
        </p>
      </div>

      {error && <p className="mb-4 text-sm text-brand">{error}</p>}

      {!brands ? (
        <p className="text-ink-soft">Loading…</p>
      ) : brands.length === 0 ? (
        <p className="rounded-xl border border-dashed border-ink/20 p-8 text-center text-ink-soft">
          No brand profiles yet — paste one below to create it.
        </p>
      ) : (
        <div className="space-y-4">
          {brands.map((b) => {
            const rules = b.rules as Record<string, unknown>;
            return (
              <div
                key={b.name}
                className="rounded-xl border border-ink/10 bg-paper p-5 shadow-sm"
              >
                <div className="mb-3 flex items-baseline justify-between">
                  <div>
                    <span className="font-serif text-xl font-bold">
                      {b.name}
                    </span>
                    {b.version && (
                      <span className="ml-2 text-xs text-ink-soft">
                        v{b.version}
                      </span>
                    )}
                  </div>
                  <button
                    onClick={() => remove(b.name)}
                    className="text-xs font-semibold text-brand hover:underline"
                  >
                    Delete
                  </button>
                </div>
                <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
                  {b.swatches.map((s) => (
                    <SwatchChip key={s.name} s={s} />
                  ))}
                </div>
                <div className="mt-3 flex flex-wrap gap-x-6 gap-y-1 text-xs text-ink-soft">
                  <span>
                    <span className="font-semibold">Fonts:</span>{" "}
                    {b.fonts.join(", ") || "—"}
                  </span>
                  {rules?.minTypeSize != null && (
                    <span>min type {String(rules.minTypeSize)}pt</span>
                  )}
                  {rules?.contrastFloor != null && (
                    <span>contrast ≥ {String(rules.contrastFloor)}</span>
                  )}
                  {Array.isArray(rules?.mandatoryElements) &&
                    (rules.mandatoryElements as string[]).length > 0 && (
                      <span>
                        mandatory:{" "}
                        {(rules.mandatoryElements as string[]).join(", ")}
                      </span>
                    )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      <div className="mt-8 rounded-xl border border-ink/10 bg-paper p-5 shadow-sm">
        <h2 className="mb-2 font-semibold">Create / update from JSON</h2>
        <p className="mb-2 text-xs text-ink-soft">
          Paste a brand profile (BRAND-1 shape). Saving by an existing name
          updates it in place.
        </p>
        <textarea
          className={field}
          rows={8}
          value={draft}
          placeholder='{ "name": "Meridian Market", "swatches": [...], "fonts": [...], "rules": {...} }'
          onChange={(e) => setDraft(e.target.value)}
        />
        <button
          onClick={save}
          disabled={busy || !draft.trim()}
          className="mt-3 rounded-lg bg-ink px-4 py-2 text-sm font-semibold text-cream transition hover:bg-ink-soft disabled:opacity-40"
        >
          {busy ? "Saving…" : "Save profile"}
        </button>
      </div>
    </div>
  );
}
