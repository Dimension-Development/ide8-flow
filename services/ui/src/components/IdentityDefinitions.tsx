import {useEffect, useMemo, useState} from 'react';
import type {IdentityProfile, IdentitySource, Swatch} from '../api';
import {swatchColor} from '../identity';

interface Props {
  profile: IdentityProfile;
  onChange: (profile: IdentityProfile) => void;
  sources?: IdentitySource[];
  disabled?: boolean;
  /** Block workspace save/publication while definitions have unapplied edits. */
  onPendingChange?: (pending: boolean) => void;
}
interface ColourEdit {
  key: string;
  name: string;
  space: Swatch['space'];
  channels: string[];
  original: Swatch;
}
interface FontEdit {key: string; name: string}

const input = 'w-full rounded-xl border border-ink/15 bg-white px-3 py-2 text-sm outline-none focus:border-ink disabled:opacity-50';
const secondary = 'rounded-xl border border-ink/15 bg-white px-3 py-2 text-sm font-semibold disabled:opacity-40';
const signature = (profile: IdentityProfile) => JSON.stringify({swatches: profile.swatches, fonts: profile.fonts});
const colourRows = (swatches: Swatch[]): ColourEdit[] => swatches.map((s, index) => ({
  key: `colour-${index}`, name: s.name, space: s.space,
  channels: s.values.map(String), original: s,
}));
const fontRows = (fonts: string[]): FontEdit[] => fonts.map((name, index) => ({key: `font-${index}`, name}));
const channelNames = (space: Swatch['space']) => space === 'cmyk' ? ['C', 'M', 'Y', 'K'] : ['R', 'G', 'B'];

function colourErrors(rows: ColourEdit[]): string[] {
  const seen = new Set<string>();
  return rows.flatMap((row, index) => {
    const errors: string[] = [];
    const name = row.name.trim();
    const label = name || `Colour ${index + 1}`;
    if (!name) errors.push(`Colour ${index + 1} needs a name.`);
    if (name.length > 300) errors.push(`${label.slice(0, 30)}: use a name of at most 300 characters.`);
    if (name && seen.has(name.toLocaleLowerCase())) errors.push(`Colour name “${name}” is duplicated.`);
    seen.add(name.toLocaleLowerCase());
    const limit = row.space === 'cmyk' ? 100 : 255;
    if (row.channels.length !== channelNames(row.space).length || row.channels.some(value =>
      !value.trim() || !Number.isFinite(Number(value)) || Number(value) < 0 || Number(value) > limit
    )) errors.push(`${label}: enter ${channelNames(row.space).length} ${row.space.toUpperCase()} values between 0 and ${limit}.`);
    return errors;
  });
}

export default function IdentityDefinitions({profile, onChange, sources = [], disabled = false, onPendingChange}: Props) {
  const currentSignature = signature(profile);
  const [baseSignature, setBaseSignature] = useState(currentSignature);
  const [colours, setColours] = useState(() => colourRows(profile.swatches));
  const [fonts, setFonts] = useState(() => fontRows(profile.fonts));
  const [pending, setPending] = useState(false);
  const [notice, setNotice] = useState('');
  const conflict = pending && currentSignature !== baseSignature;

  useEffect(() => {onPendingChange?.(pending);}, [pending, onPendingChange]);
  useEffect(() => {
    if (!pending && currentSignature !== baseSignature) {
      setColours(colourRows(profile.swatches));
      setFonts(fontRows(profile.fonts));
      setBaseSignature(currentSignature);
    }
  }, [currentSignature, baseSignature, pending, profile.swatches, profile.fonts]);

  const errors = useMemo(() => {
    const found = colourErrors(colours);
    const seen = new Set<string>();
    fonts.forEach((row, index) => {
      const name = row.name.trim();
      if (!name) found.push(`Font ${index + 1} needs its exact reference name.`);
      if (name.length > 300) found.push(`Font ${index + 1}: use a name of at most 300 characters.`);
      if (name && seen.has(name.toLocaleLowerCase())) found.push(`Font reference “${name}” is duplicated.`);
      seen.add(name.toLocaleLowerCase());
    });
    // Existing named character styles must not be left pointing at removed
    // working definitions. Evidence card references are intentionally untouched.
    const styles = Array.isArray(profile.charStyles) ? profile.charStyles : [];
    for (const value of styles) {
      if (!value || typeof value !== 'object') continue;
      const style = value as {name?: string; color?: string; font?: string};
      if (style.color && profile.swatches.some(s => s.name === style.color) && !colours.some(s => s.name.trim() === style.color))
        found.push(`Character style “${style.name || 'unnamed'}” still uses colour “${style.color}”. Update its reference before removing or renaming that colour.`);
      if (style.font && profile.fonts.includes(style.font) && !fonts.some(f => f.name.trim() === style.font))
        found.push(`Character style “${style.name || 'unnamed'}” still uses font “${style.font}”. Update its reference before removing or renaming that font.`);
    }
    return found;
  }, [colours, fonts, profile.charStyles, profile.swatches, profile.fonts]);

  const changed = () => {setPending(true); setNotice('');};
  const editColour = (key: string, patch: Partial<ColourEdit>) => {
    setColours(rows => rows.map(row => row.key === key ? {...row, ...patch} : row)); changed();
  };
  const discard = () => {
    setColours(colourRows(profile.swatches)); setFonts(fontRows(profile.fonts));
    setBaseSignature(currentSignature); setPending(false); setNotice('Definition edits discarded.');
  };
  const apply = () => {
    if (disabled || conflict || errors.length || !pending) return;
    const swatches = colours.map(row => ({...row.original, name: row.name.trim(), space: row.space, values: row.channels.map(Number)}));
    const names = fonts.map(row => row.name.trim());
    const next = {...profile, swatches, fonts: names};
    // Only canonical working definitions change. card.swatch and source review
    // records describe source transcription and must remain historical facts.
    onChange(next);
    setColours(colourRows(swatches)); setFonts(fontRows(names));
    setBaseSignature(signature(next)); setPending(false);
    setNotice('Working definitions updated in this draft. Save the draft to retain them; publication is separate.');
  };

  return <section className="space-y-4 rounded-3xl border border-ink/10 bg-white p-5">
    <div><p className="text-xs uppercase tracking-widest text-ink-soft">Working definitions</p>
      <h2 className="mt-2 font-serif text-2xl">Colours & font references</h2>
      <p className="mt-2 max-w-3xl text-sm text-ink-soft">These values feed the working palette, DESIGN.md and future published generation profiles. Source transcription cards retain their original values and evidence. Changing a working value does not rewrite or approve its source.</p>
    </div>
    <fieldset disabled={disabled} className="space-y-4">
      <details className="rounded-2xl border border-ink/10" open>
        <summary className="cursor-pointer px-4 py-3 font-semibold">Working palette <span className="ml-2 text-xs font-normal text-ink-soft">{colours.length} colours</span></summary>
        <div className="space-y-3 border-t border-ink/10 p-4">
          <p className="text-xs text-ink-soft">CMYK previews are screen approximations. Changing colour space clears its channels: enter the intended source values; no conversion is inferred.</p>
          {colours.map((row, index) => {
            const valid = colourErrors([{...row, name: row.name || 'Preview'}]).length === 0;
            return <details key={row.key} className="rounded-xl border border-ink/10">
              <summary className="flex cursor-pointer items-center gap-3 px-3 py-2">
                <span className="h-8 w-8 shrink-0 rounded-lg border border-ink/15" style={valid ? {background: swatchColor({name: row.name, space: row.space, values: row.channels.map(Number)})} : {background: '#f1f5f9'}} />
                <span className="min-w-0 flex-1 truncate text-sm font-medium">{row.name.trim() || `Unnamed colour ${index + 1}`}</span>
                <span className="text-xs text-ink-soft">{row.space.toUpperCase()}{row.original.spot ? ' · spot' : ''} · edit</span>
              </summary>
              <div className="space-y-3 border-t border-ink/10 p-3">
                <div className="grid gap-3 sm:grid-cols-[1fr_8rem]">
                  <label className="text-xs">Colour name<input className={`${input} mt-1`} aria-label={`Colour ${index + 1} name`} value={row.name} onChange={e => editColour(row.key, {name: e.target.value})}/></label>
                  <label className="text-xs">Colour space<select className={`${input} mt-1`} aria-label={`Colour ${index + 1} space`} value={row.space} onChange={e => {
                    const space = e.target.value as Swatch['space'];
                    editColour(row.key, {space, channels: channelNames(space).map(() => '')});
                  }}><option value="cmyk">CMYK</option><option value="rgb">RGB</option></select></label>
                </div>
                <div className="grid grid-cols-4 gap-2">{channelNames(row.space).map((label, channel) => <label className="text-xs" key={label}>{label}{row.space === 'cmyk' ? ' %' : ''}<input className={`${input} mt-1`} aria-label={`Colour ${index + 1} ${label}`} type="number" min={0} max={row.space === 'cmyk' ? 100 : 255} step="any" value={row.channels[channel] ?? ''} onChange={e => editColour(row.key, {channels: row.channels.map((value, i) => i === channel ? e.target.value : value)})}/></label>)}</div>
                {row.original.spot && <p className="text-xs text-ink-soft">Existing spot designation is retained. Editing these channel values does not certify a spot-colour match.</p>}
                <button className="text-xs font-semibold text-red-700" type="button" onClick={() => {setColours(rows => rows.filter(c => c.key !== row.key)); changed();}}>Remove {row.name.trim() || 'colour'}</button>
              </div>
            </details>;
          })}
          {!colours.length && <p className="text-sm text-ink-soft">No working colours. Add the definitions needed by this brand.</p>}
          <button type="button" className={secondary} onClick={() => {setColours(rows => [...rows, {key: crypto.randomUUID(), name: '', space: 'cmyk', channels: ['', '', '', ''], original: {name: '', space: 'cmyk', values: []}}]); changed();}}>Add colour</button>
        </div>
      </details>
      <details className="rounded-2xl border border-ink/10">
        <summary className="cursor-pointer px-4 py-3 font-semibold">Working font references <span className="ml-2 text-xs font-normal text-ink-soft">{fonts.length} names</span></summary>
        <div className="space-y-3 border-t border-ink/10 p-4">
          <p className="text-xs text-ink-soft">Use exact font reference names. Matching below uses attached source names without inferring family, weight or italic styles. Adding a name does not upload or install its font.</p>
          {fonts.map((row, index) => {
            const matches = sources.filter(s => s.mime.startsWith('font/') && s.font_family === row.name.trim());
            return <div key={row.key} className="rounded-xl border border-ink/10 p-3">
              <div className="flex items-end gap-3"><label className="flex-1 text-xs">Font reference {index + 1}<input className={`${input} mt-1`} aria-label={`Font reference ${index + 1}`} value={row.name} onChange={e => {setFonts(rows => rows.map(f => f.key === row.key ? {...f, name: e.target.value} : f)); changed();}}/></label><button type="button" className="pb-2 text-xs font-semibold text-red-700" onClick={() => {setFonts(rows => rows.filter(f => f.key !== row.key)); changed();}}>Remove</button></div>
              <p className="mt-2 break-words text-xs text-ink-soft">{matches.length === 1 ? `Attached source: ${matches[0].filename}. Renderer availability remains a separate check.` : matches.length > 1 ? 'Multiple attached files use this name; resolve the source choice before relying on a specimen.' : 'Reference only — no attached source with this exact name.'}</p>
            </div>;
          })}
          {!fonts.length && <p className="text-sm text-ink-soft">No working font references.</p>}
          <button type="button" className={secondary} onClick={() => {setFonts(rows => [...rows, {key: crypto.randomUUID(), name: ''}]); changed();}}>Add font reference</button>
        </div>
      </details>
      {pending && <div className="rounded-xl bg-amber-50 p-3 text-sm text-amber-950">Working definition edits have not been applied. Apply or discard them before saving or publishing the workspace.</div>}
      {conflict && <p role="alert" className="text-sm text-red-700">Working definitions changed outside this editor. Discard these local edits to reload the current definitions before trying again.</p>}
      {!!errors.length && <ul role="alert" className="space-y-1 rounded-xl bg-red-50 p-3 text-sm text-red-800">{errors.map((error, index) => <li key={index}>{error}</li>)}</ul>}
      <div className="flex flex-wrap gap-2"><button type="button" className="rounded-xl bg-ink px-4 py-2 text-sm font-semibold text-white disabled:opacity-40" disabled={disabled || !pending || conflict || errors.length > 0} onClick={apply}>Apply working definitions</button><button type="button" className={secondary} disabled={disabled || !pending} onClick={discard}>Discard definition edits</button></div>
    </fieldset>
    {notice && <p role="status" className="text-sm text-emerald-800">{notice}</p>}
  </section>;
}
