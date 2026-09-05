import { useEffect, useState } from "react";
import {
  api,
  workspaceApi,
  type Asset,
  type Brief,
  type BrandSummary,
  type EnginePreset,
  type Project,
} from "../api";

const SIZES = ["A4", "A3", "A2", "A1", "A5", "SRA3"];

const ENGINES: { value: EnginePreset; label: string }[] = [
  { value: "draft", label: "Draft — Haiku 4.5, Sonnet 4.6 escalation" },
  { value: "standard", label: "Standard — Sonnet 4.6, Opus 4.8 escalation" },
  { value: "premium", label: "Premium — Opus 4.8 throughout" },
];

const DEFAULT_BRAND = "Example Brand";

function parseMargins(s: string): number[] | null {
  const parts = s.split(",").map((x) => x.trim() ? Number(x.trim()) : NaN);
  if (parts.length === 4 && parts.every((n) => Number.isFinite(n) && n >= 0))
    return parts;
  return null;
}

export default function BriefForm({
  onStarted,
  initialProjectId,
}: {
  onStarted: (jobId: string, projectId?: string) => void;
  initialProjectId?: string;
}) {
  const [title, setTitle] = useState("");
  const [headline, setHeadline] = useState("");
  const [subhead, setSubhead] = useState("");
  const [body, setBody] = useState("");
  const [legal, setLegal] = useState("");
  const [tone, setTone] = useState("");
  const [notes, setNotes] = useState("");
  const [size, setSize] = useState("A4");
  const [customWidth, setCustomWidth] = useState("150");
  const [customHeight, setCustomHeight] = useState("100");
  const [customUnit, setCustomUnit] = useState("mm");
  const [orientation, setOrientation] = useState("portrait");
  const [bleed, setBleed] = useState(8.5);
  const [margins, setMargins] = useState("12, 12, 12, 12");
  const [mandatory, setMandatory] = useState("");
  const [mandatoryCopy, setMandatoryCopy] = useState("");
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectChoice, setProjectChoice] = useState("");
  const [project, setProject] = useState<Project | null>(null);
  const [baseBrief, setBaseBrief] = useState<Partial<Brief>>({});
  const [loading, setLoading] = useState(true);
  const [assetsLoading, setAssetsLoading] = useState(false);
  const [saved, setSaved] = useState(false);
  const [saving, setSaving] = useState(false);
  const [refs, setRefs] = useState<string[]>([]);
  const [n, setN] = useState(6);
  const [engine, setEngine] = useState<EnginePreset>("premium");
  const [brand, setBrand] = useState(DEFAULT_BRAND);
  const [brands, setBrands] = useState<BrandSummary[]>([]);
  const [assets, setAssets] = useState<Asset[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    Promise.allSettled([api.brands(), api.projects()]).then(
      ([brandResult, projectResult]) => {
        if (!active) return;
        const failures: string[] = [];
        if (brandResult.status === "fulfilled") {
          const d = brandResult.value;
          setBrands(d.brands);
          setBrand(d.brands[0]?.name ?? d.default ?? DEFAULT_BRAND);
        } else failures.push(`Brand profiles: ${String(brandResult.reason)}`);
        if (projectResult.status === "fulfilled") setProjects(projectResult.value.projects);
        else failures.push(`Saved projects: ${String(projectResult.reason)}`);
        setError(failures.length ? failures.join(" · ") : null);
        setLoading(false);
      },
    );
    return () => { active = false; };
  }, []);

  const loadProject = (requestedId = projectChoice) => {
    const selected = projects.find((p) => p.id === requestedId);
    if (!selected?.brief) return;
    const b = selected.brief;
    const savedSize = b.format?.size;
    const custom = Array.isArray(savedSize) && savedSize.length === 2
      && savedSize.every((v) => Number.isFinite(v) && v > 0);
    if ((!custom && (typeof savedSize !== "string" || !SIZES.includes(savedSize))) || b.formats) {
      setError("This project uses a format this brief editor cannot edit yet.");
      return;
    }
    setProject(selected);
    setBaseBrief(b);
    setTitle(b.title ?? selected.name);
    setBrand(selected.brand ?? b.brand ?? DEFAULT_BRAND);
    setHeadline(b.copy?.headline ?? "");
    setSubhead(b.copy?.subhead ?? "");
    setBody((b.copy?.body ?? []).join("\n"));
    setLegal(b.copy?.legal ?? "");
    if (Array.isArray(savedSize)) {
      let [w, h] = savedSize;
      if (b.format.orientation === "landscape" && h > w) [w, h] = [h, w];
      setSize("Custom");
      setCustomUnit("pt");
      setCustomWidth(String(w));
      setCustomHeight(String(h));
    } else setSize(savedSize);
    setOrientation(b.format.orientation ?? "portrait");
    setBleed(b.format.bleed ?? 8.5);
    setMargins((b.format.margins ?? [12, 12, 12, 12]).join(", "));
    setMandatory((b.mandatoryElements ?? []).join(", "));
    setMandatoryCopy((b.mandatoryCopy ?? []).join("\n"));
    setRefs(b.references?.imageAssets ?? []);
    setTone(b.tone ?? "");
    setNotes(b.notes ?? "");
    setSaved(false);
    setError(null);
  };

  useEffect(() => {
    if (initialProjectId && projects.length && !project) {
      setProjectChoice(initialProjectId);
      loadProject(initialProjectId);
    }
  }, [initialProjectId, projects]);

  useEffect(() => {
    if (loading) return;
    let active = true;
    setAssets([]);setAssetsLoading(true);
    Promise.all([api.assets(), workspaceApi.membership(brand)]).then(([library,membership]) => {
      if (active) setAssets(membership.assigned ? library.assets.filter(a=>membership.names.includes(a.name)) : library.assets);
    }).catch(e=>{if(active){setAssets([]);setError(String(e));}}).finally(()=>{if(active)setAssetsLoading(false)});
    return ()=>{active=false};
  }, [brand, loading]);

  const toggleRef = (name: string) => {
    setSaved(false);
    setRefs((r) => (r.includes(name) ? r.filter((x) => x !== name) : [...r, name]));
  };

  const customDimensions: [number, number] = [Number(customWidth), Number(customHeight)];
  const customValid = customWidth.trim() !== "" && customHeight.trim() !== ""
    && customDimensions.every((v) => Number.isFinite(v) && v > 0);
  const formatValid = !!parseMargins(margins) && Number.isFinite(bleed) && bleed >= 0
    && (size !== "Custom" || customValid);

  const currentBrief = (): Brief => ({
      ...baseBrief,
      title: title.trim() || "Untitled brief",
      brand,
      format: {
        ...baseBrief.format,
        size: size === "Custom"
          ? customDimensions.map((v) => customUnit === "mm" ? v * 72 / 25.4 : v) as [number, number]
          : size,
        orientation: size === "Custom"
          ? (customDimensions[0] > customDimensions[1] ? "landscape" : "portrait") : orientation,
        bleed,
        margins: parseMargins(margins) ?? [],
      },
      copy: {
        ...baseBrief.copy,
        headline: headline.trim(),
        subhead: subhead.trim(),
        body: body
          .split("\n")
          .map((l) => l.trim())
          .filter(Boolean),
        legal: legal.trim() || null,
      },
      mandatoryElements: mandatory
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean),
      mandatoryCopy: mandatoryCopy.split("\n").map((s) => s.trim()).filter(Boolean),
      tone: tone.trim(),
      notes: notes.trim(),
      references: { ...baseBrief.references, imageAssets: refs },
  });

  const save = async () => {
    if (!project || !formatValid) return;
    setBusy(true);
    setSaving(true);
    setError(null);
    setSaved(false);
    try {
      const updated = await api.saveProjectBrief(project.id, currentBrief());
      setProject(updated);
      setBaseBrief(updated.brief ?? {});
      setProjects((ps) => ps.map((p) => p.id === updated.id ? updated : p));
      setSaved(true);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
      setSaving(false);
    }
  };

  const submit = async () => {
    if (!formatValid || assetsLoading) return;
    setBusy(true);
    setError(null);
    const brief = currentBrief();
    try {
      const { job_id } = project
        ? await api.generateProject(project.id, brief, n, engine)
        : await api.generate(brief, n, engine);
      onStarted(job_id, project?.id);
    } catch (e) {
      setError(String(e));
      setBusy(false);
    }
  };

  const field =
    "w-full rounded-lg border border-ink/15 bg-white p-2 text-sm outline-none focus:border-brand";
  const label = "mb-1 block text-sm font-semibold";
  const missingRefs = refs.filter((name) => !assets.some((a) => a.name === name));

  return (
    <div className="mx-auto max-w-2xl">
      <h1 className="mb-1 font-serif text-3xl font-bold">
        {project ? "Project brief" : "New brief"}
      </h1>
      <p className="mb-6 text-sm text-ink-soft">
        Load a saved project or prepare a new brief with its copy, format and images.
      </p>

      {loading ? <p className="mb-4 text-sm">Loading project materials…</p> : projects.length > 0 && (
        <div className="mb-6 rounded-xl border border-ink/15 bg-white p-4">
          <label className={label} htmlFor="saved-campaign">Saved project</label>
          <div className="flex gap-2">
            <select id="saved-campaign" className={`${field} min-w-0`} value={projectChoice}
              disabled={busy} onChange={(e) => setProjectChoice(e.target.value)}>
              <option value="">Choose a project…</option>
              {projects.map((p) => <option key={p.id} value={p.id} disabled={!p.brief}>{p.name}</option>)}
            </select>
            <button onClick={()=>loadProject()} disabled={busy || !projectChoice}
              className="shrink-0 rounded-lg bg-ink px-3 py-2 text-sm font-semibold text-cream disabled:opacity-40">
              Load brief
            </button>
          </div>
          <p className="mt-2 text-xs text-ink-soft">
            Loads saved copy, format and selected images into this form.
          </p>
          {project && <p className="mt-2 text-sm font-semibold">
            {project.name} · {project.brand ?? brand}
            {project.brand_version != null ? ` (v${project.brand_version})` : ""}
          </p>}
        </div>
      )}

      <fieldset disabled={busy || loading} onChange={() => setSaved(false)}
        className="space-y-4 rounded-xl border border-ink/10 bg-paper p-6 shadow-sm">
        <div>
          <label className={label} htmlFor="brief-title">Project title</label>
          <input id="brief-title" className={field} value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Autumn Warmers — Aisle Fin Set" />
        </div>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className={label} htmlFor="brief-brand">Brand profile</label>
            <select id="brief-brand" className={field} value={brand} disabled={!!project}
              onChange={(e) => setBrand(e.target.value)}>
              {project && <option value={brand}>
                {brand}{project.brand_version != null ? ` (v${project.brand_version})` : ""}
              </option>}
              {brands.length === 0 && <option>{DEFAULT_BRAND}</option>}
              {!project && brands.map((b) => (
                <option key={b.name} value={b.name}>
                  {b.name}
                  {b.version ? ` (v${b.version})` : ""}
                </option>
              ))}
            </select>
            {project && <p className="mt-1 text-xs text-ink-soft">Uses this project’s saved brand version.</p>}
          </div>
          <div>
            <label className={label} htmlFor="brief-engine">Engine</label>
            <select id="brief-engine" className={field} value={engine}
              onChange={(e) => setEngine(e.target.value as EnginePreset)}>
              {ENGINES.map((m) => (
                <option key={m.value} value={m.value}>{m.label}</option>
              ))}
            </select>
            <p className="mt-1 text-xs text-ink-soft">Generation provider: Anthropic.</p>
          </div>
        </div>
        <div className="grid grid-cols-3 gap-4">
          <div>
            <label className={label} htmlFor="brief-format">Format</label>
            <select id="brief-format" className={field} value={size}
              onChange={(e) => setSize(e.target.value)}>
              {SIZES.map((s) => <option key={s}>{s}</option>)}
              <option>Custom</option>
            </select>
          </div>
          <div>
            <label className={label} htmlFor="brief-orientation">Orientation</label>
            <select id="brief-orientation" className={field}
              disabled={size === "Custom"}
              value={size === "Custom" ? (customDimensions[0] > customDimensions[1] ? "landscape" : "portrait") : orientation}
              onChange={(e) => setOrientation(e.target.value)}>
              <option>portrait</option>
              <option>landscape</option>
            </select>
          </div>
          <div>
            <label className={label} htmlFor="brief-count">Concepts</label>
            <select id="brief-count" className={field} value={n}
              onChange={(e) => setN(Number(e.target.value))}>
              {[1, 2, 4, 6, 8].map((v) => <option key={v}>{v}</option>)}
            </select>
          </div>
        </div>
        {size === "Custom" && <div>
          <div className="grid grid-cols-3 gap-4">
            <div>
              <label className={label} htmlFor="brief-width">Width</label>
              <input id="brief-width" type="number" min="0" step="any" className={field}
                value={customWidth} onChange={(e) => setCustomWidth(e.target.value)} />
            </div>
            <div>
              <label className={label} htmlFor="brief-height">Height</label>
              <input id="brief-height" type="number" min="0" step="any" className={field}
                value={customHeight} onChange={(e) => setCustomHeight(e.target.value)} />
            </div>
            <div>
              <label className={label} htmlFor="brief-unit">Units</label>
              <select id="brief-unit" className={field} value={customUnit}
                onChange={(e) => {
                  const unit = e.target.value;
                  if (customValid) {
                    const factor = unit === "pt" ? 72 / 25.4 : 25.4 / 72;
                    setCustomWidth(String(customDimensions[0] * factor));
                    setCustomHeight(String(customDimensions[1] * factor));
                  }
                  setCustomUnit(unit);
                }}>
                <option value="mm">mm</option><option value="pt">pt</option>
              </select>
            </div>
          </div>
          <p className="mt-1 text-xs text-ink-soft">Orientation follows the entered width and height.</p>
          {!customValid && <p className="mt-1 text-xs text-brand">Enter a positive width and height.</p>}
        </div>}
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className={label} htmlFor="brief-bleed">Bleed (pt)</label>
            <input id="brief-bleed" type="number" min="0" step="0.5" className={field} value={bleed}
              onChange={(e) => setBleed(Number(e.target.value))} />
          </div>
          <div>
            <label className={label} htmlFor="brief-margins">Margins L,R,T,B (pt)</label>
            <input id="brief-margins" className={field} value={margins}
              onChange={(e) => setMargins(e.target.value)} />
            {!parseMargins(margins) && <p className="mt-1 text-xs text-brand">
              Enter four non-negative numbers, separated by commas.
            </p>}
          </div>
        </div>
        <div>
          <label className={label} htmlFor="brief-headline">Headline *</label>
          <input id="brief-headline" className={field} value={headline}
            onChange={(e) => setHeadline(e.target.value)}
            placeholder="AUTUMN, POURED" />
        </div>
        <div>
          <label className={label} htmlFor="brief-subhead">Subhead</label>
          <input id="brief-subhead" className={field} value={subhead}
            onChange={(e) => setSubhead(e.target.value)}
            placeholder="Hot drinks &amp; bakes — end of aisle 2" />
        </div>
        <div>
          <label className={label} htmlFor="brief-body">Body copy (one paragraph per line)</label>
          <textarea id="brief-body" className={field} rows={3} value={body}
            onChange={(e) => setBody(e.target.value)} />
        </div>
        <div>
          <label className={label} htmlFor="brief-legal">Legal line</label>
          <input id="brief-legal" className={field} value={legal}
            onChange={(e) => setLegal(e.target.value)}
            placeholder="optional — reproduced verbatim" />
        </div>
        <div>
          <label className={label} htmlFor="mandatory-copy">Required wording (one phrase per line)</label>
          <textarea id="mandatory-copy" className={field} rows={2} value={mandatoryCopy}
            onChange={(e) => setMandatoryCopy(e.target.value)} />
          <p className="mt-1 text-xs text-ink-soft">Each phrase must appear exactly as written, such as a campaign endline.</p>
        </div>
        <div>
          <label className={label} htmlFor="brief-mandatory">Mandatory elements (comma-separated item names)</label>
          <input id="brief-mandatory" className={field} value={mandatory}
            onChange={(e) => setMandatory(e.target.value)}
            placeholder="meridian-logo, legal-line, harvest-recipe-qr" />
          <p className="mt-1 text-xs text-ink-soft">
            Each becomes a hard requirement — every concept must include a
            named item matching it.
          </p>
        </div>
        <div>
          <label className={label}>Reference assets · {refs.length} selected</label>
          {assets.length === 0 ? (
            <p className="text-xs text-ink-soft">
              No assets are assigned to this brand — assign them in its asset library.
            </p>
          ) : (
            <div className="grid max-h-80 grid-cols-2 gap-3 overflow-y-auto rounded-lg border border-ink/10 p-2 sm:grid-cols-3">
              {assets.map((a) => (
                <button
                  key={a.name}
                  type="button"
                  onClick={() => toggleRef(a.name)}
                  aria-pressed={refs.includes(a.name)}
                  className={`overflow-hidden rounded-lg border-2 text-left text-xs transition ${
                    refs.includes(a.name)
                      ? "border-brand bg-brand text-white"
                      : "border-ink/20 text-ink-soft hover:border-ink/40"
                  }`}
                >
                  <div className="flex h-28 items-center justify-center bg-slate-600 p-2">
                    <img src={api.assetUrl(a.name)} alt="" className="max-h-full max-w-full object-contain" />
                  </div>
                  <span className="block break-all p-2">{a.name} · {refs.includes(a.name) ? "Selected" : "Select"}</span>
                </button>
              ))}
            </div>
          )}
          {missingRefs.length > 0 && <p className="mt-2 text-sm text-brand">
            Missing from the image library: {missingRefs.join(", ")}. Upload these assets before generating.
          </p>}
        </div>
        <div>
          <label className={label} htmlFor="brief-tone">Tone / direction</label>
          <input id="brief-tone" className={field} value={tone}
            onChange={(e) => setTone(e.target.value)}
            placeholder="Cosy, premium, generous colour blocking" />
        </div>
        <div>
          <label className={label} htmlFor="brief-notes">Notes for the engine</label>
          <textarea id="brief-notes" className={field} rows={6} value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="Sits at eye level; headline legible from 5 m" />
        </div>

        {project && <button onClick={save} disabled={busy || loading || !formatValid}
          className="w-full rounded-lg border border-ink/20 px-4 py-2 font-semibold disabled:opacity-40">
          {saving ? "Saving project brief…" : "Save project brief"}
        </button>}
        {saved && <p role="status" className="text-sm text-ink-soft">Project brief saved.</p>}
        <button
          onClick={submit}
          disabled={busy || loading || assetsLoading || !headline.trim() || missingRefs.length > 0 || !formatValid}
          className="w-full rounded-lg bg-brand px-4 py-3 font-semibold text-white transition hover:opacity-90 disabled:opacity-40"
        >
          {busy && !saving ? "Starting fan-out…" : `Generate ${n} concept${n === 1 ? "" : "s"}`}
        </button>
        {error && <p className="text-sm text-brand">{error}</p>}
      </fieldset>
    </div>
  );
}
