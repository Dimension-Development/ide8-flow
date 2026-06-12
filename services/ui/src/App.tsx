import { useState } from "react";
import ConceptGrid from "./components/ConceptGrid";
import ConceptDetail from "./components/ConceptDetail";
import BriefForm from "./components/BriefForm";
import AssetsView from "./components/AssetsView";

type View =
  | { kind: "grid" }
  | { kind: "concept"; id: string }
  | { kind: "brief" }
  | { kind: "assets" };

export default function App() {
  const [view, setView] = useState<View>({ kind: "grid" });
  const [activeJobId, setActiveJobId] = useState<string | null>(null);

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-10 border-b border-ink/10 bg-paper/90 backdrop-blur">
        <div className="mx-auto flex max-w-7xl items-baseline gap-3 px-6 py-4">
          <button
            onClick={() => setView({ kind: "grid" })}
            className="font-serif text-2xl font-bold tracking-tight"
          >
            ide8<span className="text-brand">.flow</span>
          </button>
          <span className="text-sm text-ink-soft">
            proof grid — M2 internal preview
          </span>
          <button
            onClick={() => setView({ kind: "assets" })}
            className="ml-auto text-sm font-semibold text-ink-soft transition hover:text-ink"
          >
            Assets
          </button>
          <button
            onClick={() => setView({ kind: "brief" })}
            className="rounded-lg bg-ink px-3 py-1.5 text-sm font-semibold text-cream transition hover:bg-ink-soft"
          >
            + New brief
          </button>
        </div>
      </header>
      <main className="mx-auto max-w-7xl px-6 py-8">
        {view.kind === "assets" ? (
          <AssetsView />
        ) : view.kind === "brief" ? (
          <BriefForm
            onStarted={(jobId) => {
              setActiveJobId(jobId);
              setView({ kind: "grid" });
            }}
          />
        ) : view.kind === "grid" ? (
          <ConceptGrid
            activeJobId={activeJobId}
            onJobSettled={() => setActiveJobId(null)}
            onOpen={(id) => setView({ kind: "concept", id })}
          />
        ) : (
          <ConceptDetail
            conceptId={view.id}
            onBack={() => setView({ kind: "grid" })}
          />
        )}
      </main>
    </div>
  );
}
