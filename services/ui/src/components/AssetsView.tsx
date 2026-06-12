import { useEffect, useRef, useState } from "react";
import { api, type Asset } from "../api";

export default function AssetsView() {
  const [assets, setAssets] = useState<Asset[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const load = () =>
    api.assets().then((d) => setAssets(d.assets)).catch((e) =>
      setError(String(e)));

  useEffect(() => {
    load();
  }, []);

  const upload = async (file: File) => {
    setBusy(true);
    setError(null);
    try {
      const dataB64 = await new Promise<string>((res, rej) => {
        const r = new FileReader();
        r.onload = () => res((r.result as string).split(",")[1]);
        r.onerror = rej;
        r.readAsDataURL(file);
      });
      const name = file.name
        .replace(/\.[^.]+$/, "")
        .toLowerCase()
        .replace(/[^a-z0-9_-]+/g, "-")
        .replace(/^-+|-+$/g, "");
      await api.uploadAsset(name, file.name, dataB64);
      await load();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  return (
    <div className="mx-auto max-w-4xl">
      <div className="mb-6 flex items-end justify-between">
        <div>
          <h1 className="font-serif text-3xl font-bold">Image assets</h1>
          <p className="mt-1 text-sm text-ink-soft">
            Uploaded assets are offered to the engine by name — concepts may
            only place images from this library (write-once; missing
            references fail validation).
          </p>
        </div>
        <label className="cursor-pointer rounded-lg bg-ink px-3 py-2 text-sm font-semibold text-cream transition hover:bg-ink-soft">
          {busy ? "Uploading…" : "Upload image"}
          <input
            ref={fileRef}
            type="file"
            accept="image/png,image/jpeg,image/tiff"
            className="hidden"
            disabled={busy}
            onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])}
          />
        </label>
      </div>
      {error && <p className="mb-4 text-sm text-brand">{error}</p>}
      {!assets ? (
        <p className="text-ink-soft">Loading assets…</p>
      ) : assets.length === 0 ? (
        <p className="rounded-xl border border-dashed border-ink/20 p-10 text-center text-ink-soft">
          No assets yet — upload a logo or product shot to let concepts
          place real imagery.
        </p>
      ) : (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
          {assets.map((a) => (
            <div
              key={a.name}
              className="overflow-hidden rounded-xl border border-ink/10 bg-paper shadow-sm"
            >
              <div className="flex aspect-square items-center justify-center bg-ink/5 p-3">
                <img
                  src={api.assetUrl(a.name)}
                  alt={a.name}
                  className="max-h-full max-w-full rounded"
                />
              </div>
              <div className="p-3">
                <p className="truncate font-mono text-sm font-semibold">
                  {a.name}
                </p>
                <p className="text-xs text-ink-soft">
                  {a.width && a.height ? `${a.width}×${a.height}px · ` : ""}
                  {(a.size / 1024).toFixed(0)} KB
                </p>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
