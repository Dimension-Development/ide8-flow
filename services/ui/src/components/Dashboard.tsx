import { useEffect, useState, type ReactNode } from "react";
import { api, type Stats } from "../api";

// ADM-1 v1: global usage + validation dashboard, read from the stored version
// provenance. Per-project rollups and render latency are deferred (no project
// entity yet; render isn't instrumented) — see the worker's usage_stats().
export default function Dashboard() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.stats().then(setStats).catch((e) => setError(String(e)));
  }, []);

  if (error) return <p className="text-brand">{error}</p>;
  if (!stats) return <p className="text-ink-soft">Loading usage…</p>;

  const errCodes = Object.entries(stats.validation.errors_by_code).sort(
    (a, b) => b[1] - a[1],
  );
  const warnCodes = Object.entries(stats.validation.warnings_by_code).sort(
    (a, b) => b[1] - a[1],
  );
  const maxModelCost = Math.max(
    0.0001,
    ...stats.cost_by_model.map((m) => m.cost_usd),
  );

  return (
    <div>
      <h1 className="mb-1 font-serif text-2xl font-bold">Usage &amp; validation</h1>
      <p className="mb-6 text-sm text-ink-soft">
        Global — all briefs · live from stored version provenance
      </p>

      <div className="mb-8 grid grid-cols-2 gap-4 sm:grid-cols-4">
        <StatCard label="Concepts" value={stats.concepts} />
        <StatCard label="Versions" value={stats.versions} />
        <StatCard label="LLM spend" value={`$${stats.cost_usd_total.toFixed(2)}`} />
        <StatCard
          label="Approved"
          value={stats.approved_versions}
          sub={`of ${stats.versions} versions`}
        />
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Panel title="Spend by model">
          {stats.cost_by_model.length === 0 ? (
            <Empty />
          ) : (
            <ul className="space-y-3">
              {stats.cost_by_model.map((m) => (
                <li key={m.model}>
                  <div className="mb-1 flex items-baseline justify-between text-sm">
                    <span className="font-mono text-xs">
                      {m.model}
                      {!m.priced && (
                        <span
                          className="ml-1 text-brand"
                          title="model has no price entry — cost excludes it"
                        >
                          *
                        </span>
                      )}
                    </span>
                    <span className="text-ink-soft">
                      ${m.cost_usd.toFixed(3)} · {m.calls} calls
                    </span>
                  </div>
                  <Bar pct={(m.cost_usd / maxModelCost) * 100} />
                </li>
              ))}
            </ul>
          )}
          <TokenFooter stats={stats} />
        </Panel>

        <Panel title="Generation mix">
          <ul className="space-y-2 text-sm">
            {Object.entries(stats.versions_by_origin).map(([origin, n]) => (
              <li key={origin} className="flex justify-between">
                <span className="capitalize text-ink-soft">
                  {origin.replace("_", " ")}
                </span>
                <span className="font-mono">{n}</span>
              </li>
            ))}
            <li className="flex justify-between border-t border-ink/10 pt-2">
              <span className="text-ink-soft">LLM calls</span>
              <span className="font-mono">{stats.llm_calls}</span>
            </li>
          </ul>
        </Panel>

        <Panel title="Validation by rule" className="lg:col-span-2">
          <p className="mb-3 text-xs text-ink-soft">
            {stats.validation.versions_with_errors} of {stats.versions} stored
            versions carry errors. Final-state only — in-loop repairs aren&apos;t
            counted.
          </p>
          <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
            <CodeBars title="Errors" entries={errCodes} tone="brand" />
            <CodeBars title="Warnings" entries={warnCodes} tone="ink" />
          </div>
        </Panel>
      </div>
    </div>
  );
}

function StatCard({
  label,
  value,
  sub,
}: {
  label: string;
  value: string | number;
  sub?: string;
}) {
  return (
    <div className="rounded-xl border border-ink/10 bg-paper p-4 shadow-sm">
      <div className="text-xs uppercase tracking-wide text-ink-soft">
        {label}
      </div>
      <div className="mt-1 font-serif text-2xl font-bold">{value}</div>
      {sub && <div className="text-xs text-ink-soft">{sub}</div>}
    </div>
  );
}

function Panel({
  title,
  children,
  className = "",
}: {
  title: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section
      className={`rounded-xl border border-ink/10 bg-paper p-5 shadow-sm ${className}`}
    >
      <h2 className="mb-3 font-semibold">{title}</h2>
      {children}
    </section>
  );
}

function Bar({ pct, tone = "brand" }: { pct: number; tone?: "brand" | "ink" }) {
  return (
    <div className="h-2 w-full rounded-full bg-ink/5">
      <div
        className={`h-2 rounded-full ${tone === "brand" ? "bg-brand" : "bg-ink"}`}
        style={{ width: `${Math.max(2, Math.min(100, pct))}%` }}
      />
    </div>
  );
}

function CodeBars({
  title,
  entries,
  tone,
}: {
  title: string;
  entries: [string, number][];
  tone: "brand" | "ink";
}) {
  const max = Math.max(1, ...entries.map((e) => e[1]));
  return (
    <div>
      <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-soft">
        {title}
      </h3>
      {entries.length === 0 ? (
        <Empty label={`No ${title.toLowerCase()}`} />
      ) : (
        <ul className="space-y-2">
          {entries.map(([code, n]) => (
            <li key={code}>
              <div className="mb-1 flex justify-between text-sm">
                <span className="font-mono text-xs">{code}</span>
                <span className="text-ink-soft">{n}</span>
              </div>
              <Bar pct={(n / max) * 100} tone={tone} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function TokenFooter({ stats }: { stats: Stats }) {
  const t = stats.tokens;
  const fmt = (n: number) => n.toLocaleString();
  return (
    <p className="mt-4 border-t border-ink/10 pt-3 text-xs text-ink-soft">
      Tokens — in {fmt(t.input)} · out {fmt(t.output)} · cache r{fmt(t.cache_read)}/w{fmt(t.cache_creation)}
    </p>
  );
}

function Empty({ label = "No data yet" }: { label?: string }) {
  return <p className="text-xs text-ink-soft">{label}</p>;
}
