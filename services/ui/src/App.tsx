import { useState } from "react";
import ConceptGrid from "./components/ConceptGrid";
import ConceptDetail from "./components/ConceptDetail";

type View = { kind: "grid" } | { kind: "concept"; id: string };

export default function App() {
  const [view, setView] = useState<View>({ kind: "grid" });

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
        </div>
      </header>
      <main className="mx-auto max-w-7xl px-6 py-8">
        {view.kind === "grid" ? (
          <ConceptGrid onOpen={(id) => setView({ kind: "concept", id })} />
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
