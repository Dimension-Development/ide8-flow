export function ApprovalBadge({ approved }: { approved: boolean }) {
  return approved ? (
    <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-semibold text-emerald-800">
      AI check passed
    </span>
  ) : (
    <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-semibold text-amber-800">
      needs craft pass
    </span>
  );
}

export function OriginBadge({ origin }: { origin: string }) {
  if (origin === "generation") return null;
  const styles =
    origin === "mutation"
      ? "bg-violet-100 text-violet-800"
      : "bg-sky-100 text-sky-800";
  return (
    <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${styles}`}>
      {origin.replace("_", " ")}
    </span>
  );
}

export function Cost({ usd }: { usd: number | null | undefined }) {
  if (usd == null) return null;
  return (
    <span className="font-mono text-xs text-ink-soft">${usd.toFixed(3)}</span>
  );
}
