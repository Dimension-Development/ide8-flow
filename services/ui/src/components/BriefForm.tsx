import { useState } from "react";
import { api, type Brief, type EnginePreset } from "../api";

const SIZES = ["A4", "A3", "A2", "A1", "A5", "SRA3"];

const ENGINES: { value: EnginePreset; label: string }[] = [
  { value: "draft", label: "Draft — Haiku, fastest & cheapest" },
  { value: "standard", label: "Standard — Sonnet, Opus escalation" },
  { value: "premium", label: "Premium — Opus throughout" },
];

export default function BriefForm({
  onStarted,
}: {
  onStarted: (jobId: string) => void;
}) {
  const [title, setTitle] = useState("");
  const [headline, setHeadline] = useState("");
  const [subhead, setSubhead] = useState("");
  const [body, setBody] = useState("");
  const [legal, setLegal] = useState("");
  const [tone, setTone] = useState("");
  const [notes, setNotes] = useState("");
  const [size, setSize] = useState("A4");
  const [orientation, setOrientation] = useState("portrait");
  const [n, setN] = useState(6);
  const [engine, setEngine] = useState<EnginePreset>("standard");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    setBusy(true);
    setError(null);
    const brief: Brief = {
      title: title.trim() || "Untitled brief",
      brand: "Example Brand",
      format: {
        size,
        orientation,
        bleed: 8.5,
        margins: [12, 12, 12, 12],
      },
      copy: {
        headline: headline.trim(),
        subhead: subhead.trim(),
        body: body
          .split("\n")
          .map((l) => l.trim())
          .filter(Boolean),
        legal: legal.trim() || null,
      },
      mandatoryElements: [],
      tone: tone.trim(),
      notes: notes.trim(),
    };
    try {
      const { job_id } = await api.generate(brief, n, engine);
      onStarted(job_id);
    } catch (e) {
      setError(String(e));
      setBusy(false);
    }
  };

  const field =
    "w-full rounded-lg border border-ink/15 bg-white p-2 text-sm outline-none focus:border-brand";
  const label = "mb-1 block text-sm font-semibold";

  return (
    <div className="mx-auto max-w-2xl">
      <h1 className="mb-1 font-serif text-3xl font-bold">New brief</h1>
      <p className="mb-6 text-sm text-ink-soft">
        Fan-out generates {n} distinct concepts — typically 2–4 minutes,
        roughly £0.20–0.35 per concept.
      </p>

      <div className="space-y-4 rounded-xl border border-ink/10 bg-paper p-6 shadow-sm">
        <div>
          <label className={label}>Campaign title</label>
          <input className={field} value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Autumn Warmers — Aisle Fin Set" />
        </div>
        <div className="grid grid-cols-3 gap-4">
          <div>
            <label className={label}>Format</label>
            <select className={field} value={size}
              onChange={(e) => setSize(e.target.value)}>
              {SIZES.map((s) => <option key={s}>{s}</option>)}
            </select>
          </div>
          <div>
            <label className={label}>Orientation</label>
            <select className={field} value={orientation}
              onChange={(e) => setOrientation(e.target.value)}>
              <option>portrait</option>
              <option>landscape</option>
            </select>
          </div>
          <div>
            <label className={label}>Concepts</label>
            <select className={field} value={n}
              onChange={(e) => setN(Number(e.target.value))}>
              {[2, 4, 6, 8].map((v) => <option key={v}>{v}</option>)}
            </select>
          </div>
        </div>
        <div>
          <label className={label}>Engine</label>
          <select
            className={field}
            value={engine}
            onChange={(e) => setEngine(e.target.value as EnginePreset)}
          >
            {ENGINES.map((m) => (
              <option key={m.value} value={m.value}>
                {m.label}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className={label}>Headline *</label>
          <input className={field} value={headline}
            onChange={(e) => setHeadline(e.target.value)}
            placeholder="AUTUMN, POURED" />
        </div>
        <div>
          <label className={label}>Subhead</label>
          <input className={field} value={subhead}
            onChange={(e) => setSubhead(e.target.value)}
            placeholder="Hot drinks &amp; bakes — end of aisle 2" />
        </div>
        <div>
          <label className={label}>Body copy (one paragraph per line)</label>
          <textarea className={field} rows={3} value={body}
            onChange={(e) => setBody(e.target.value)} />
        </div>
        <div>
          <label className={label}>Legal line</label>
          <input className={field} value={legal}
            onChange={(e) => setLegal(e.target.value)}
            placeholder="optional — reproduced verbatim" />
        </div>
        <div>
          <label className={label}>Tone / direction</label>
          <input className={field} value={tone}
            onChange={(e) => setTone(e.target.value)}
            placeholder="Cosy, premium, generous colour blocking" />
        </div>
        <div>
          <label className={label}>Notes for the engine</label>
          <input className={field} value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="Sits at eye level; headline legible from 5 m" />
        </div>

        <button
          onClick={submit}
          disabled={busy || !headline.trim()}
          className="w-full rounded-lg bg-brand px-4 py-3 font-semibold text-white transition hover:opacity-90 disabled:opacity-40"
        >
          {busy ? "Starting fan-out…" : `Generate ${n} concepts`}
        </button>
        {error && <p className="text-sm text-brand">{error}</p>}
      </div>
    </div>
  );
}
