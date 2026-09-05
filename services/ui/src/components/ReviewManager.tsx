import {useEffect, useRef, useState} from 'react';
import {api, type Concept} from '../api';
import {reviewDate, reviewResponse, type ClientReviewItem} from './ClientReview';

interface Share {
  id: string; title: string; created_at: string; expires_at: string; revoked_at: string | null;
  items: ClientReviewItem[];
}
interface CreatedShare extends Share {token: string; review_base_url?: string | null}
const field = 'w-full rounded-xl border border-ink/15 bg-white px-3 py-2 text-sm outline-none focus:border-ink disabled:opacity-50';
const button = 'rounded-xl border border-ink/15 bg-white px-4 py-2 text-sm font-semibold disabled:opacity-40';

export default function ReviewManager({projectId, concepts}: {projectId: string; concepts: Concept[]}) {
  const [shares, setShares] = useState<Share[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [title, setTitle] = useState('Artwork review');
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [created, setCreated] = useState<{id: string; link: string} | null>(null);
  const [revokeConfirm, setRevokeConfirm] = useState<string | null>(null);
  const endpoint = `/api/projects/${encodeURIComponent(projectId)}/reviews`;
  const activeEndpoint = useRef(endpoint);
  activeEndpoint.current = endpoint;
  const eligible = concepts.filter(concept => !concept.discarded && concept.latest?.has_proof && concept.latest.validation_ok === true);
  const eligibleIds = eligible.map(concept => concept.latest!.id);
  const chosen = selected.filter(id => eligibleIds.includes(id));
  const warningCount = eligible.filter(concept => chosen.includes(concept.latest!.id)).reduce((count, concept) => count + concept.latest!.warnings, 0);

  const refresh = async () => {
    const data = await reviewResponse<{reviews: Share[]}>(await fetch(endpoint, {cache: 'no-store'}));
    if (activeEndpoint.current !== endpoint) return;
    setShares(data.reviews);
  };
  useEffect(() => {
    const controller = new AbortController(); setSelected([]); setShares([]); setCreated(null); setError(''); setNotice(''); setLoading(true); setRevokeConfirm(null);
    fetch(endpoint, {signal: controller.signal, cache: 'no-store'}).then(reviewResponse<{reviews: Share[]}>).then(data => {if (!controller.signal.aborted) setShares(data.reviews);}).catch(reason => {if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : 'Reviews could not be loaded.');}).finally(() => {if (!controller.signal.aborted) setLoading(false);});
    return () => controller.abort();
  }, [endpoint]);

  const create = async (event: React.FormEvent) => {
    event.preventDefault(); if (!title.trim() || !chosen.length || busy) return;
    setBusy(true); setError(''); setNotice('');
    try {
      const share = await reviewResponse<CreatedShare>(await fetch(endpoint, {method: 'POST', headers: {'content-type': 'application/json'}, body: JSON.stringify({title: title.trim(), version_ids: chosen, expires_days: 7})}));
      if (activeEndpoint.current !== endpoint) return;
      if (!share.token) throw new Error('The review was created without a usable link. Refresh the review list before trying again.');
      const base = new URL(share.review_base_url || `${window.location.origin}${window.location.pathname}`, window.location.origin);
      if (!['http:', 'https:'].includes(base.protocol) || base.username || base.password) throw new Error('The review was created, but its configured public URL is invalid. Correct the review server address before creating another link.');
      base.hash = `review=${encodeURIComponent(share.token)}`;
      const link = base.toString();
      setCreated({id: share.id, link}); setSelected([]);
      setNotice('Review link created. Copy it below and share it yourself; no message has been sent.');
      try {await refresh();} catch {setError('The link was created, but the review list could not be refreshed. Keep the link below and refresh the list when ready.');}
    } catch (reason) {setError(reason instanceof Error ? reason.message : 'Link creation could not be confirmed. Refresh the review list before retrying.');}
    finally {setBusy(false);}
  };
  const revoke = async (share: Share) => {
    if (busy) return; setBusy(true); setError(''); setNotice('');
    try {
      await reviewResponse<unknown>(await fetch(`${endpoint}/${encodeURIComponent(share.id)}/revoke`, {method: 'POST', headers: {'content-type': 'application/json'}, body: '{}'}));
      if (created?.id === share.id) setCreated(null);
      setRevokeConfirm(null); setNotice('Review link revoked. Existing responses remain in the history.');
      try {await refresh();} catch {setError('The link was revoked, but the list could not be refreshed. Refresh it before taking another action.');}
    } catch (reason) {setError(reason instanceof Error ? reason.message : 'The link could not be revoked.');}
    finally {setBusy(false);}
  };

  return <section className="space-y-5">
    <header className="flex flex-wrap items-start justify-between gap-3"><div><h2 className="font-serif text-2xl">Client review & approval</h2><p className="mt-2 max-w-3xl text-sm text-ink-soft">Share exact artwork versions for comments, change requests or approval. Client decisions remain separate from model self-critique and production checks.</p></div><button type="button" className={button} disabled={busy || loading} onClick={async () => {setLoading(true); setError(''); try {await refresh();} catch (reason) {setError(reason instanceof Error ? reason.message : 'Reviews could not be refreshed.');} finally {setLoading(false);}}}>{loading ? 'Loading…' : 'Refresh reviews'}</button></header>
    {error && <p role="alert" className="rounded-xl bg-red-50 p-4 text-sm text-red-800">{error}</p>}
    {notice && <p role="status" className="rounded-xl bg-emerald-50 p-4 text-sm text-emerald-900">{notice}</p>}
    {created && <div className="space-y-3 rounded-2xl border border-emerald-200 bg-emerald-50/60 p-5"><h3 className="font-semibold">Your review link</h3><p className="text-sm text-ink-soft">Copy this link now. Its token is shown only when the link is created and cannot be recovered after leaving or refreshing this page. Anyone holding it can respond until it expires or is revoked.</p><label className="block text-sm" htmlFor="new-review-link">Shareable link<input id="new-review-link" className={`${field} mt-2`} readOnly value={created.link} onFocus={event => event.target.select()}/></label><div className="flex flex-wrap gap-2"><button type="button" className={button} onClick={async () => {try {await navigator.clipboard.writeText(created.link); setNotice('Review link copied.');} catch {setError('Clipboard access is unavailable. Select and copy the link from the field above.');}}}>Copy link</button><a className={button} href={created.link} target="_blank" rel="noopener noreferrer">Preview client page ↗</a></div></div>}
    <form className="space-y-4 rounded-2xl border border-ink/10 bg-white p-5" onSubmit={create}>
      <fieldset disabled={busy} className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-[1fr_12rem]"><label className="text-sm font-semibold" htmlFor="review-share-title">Review title<input id="review-share-title" className={`${field} mt-2`} required maxLength={300} value={title} onChange={event => setTitle(event.target.value)}/></label><div><p className="text-sm font-semibold">Link expiry</p><p className="mt-2 rounded-xl bg-cream px-3 py-2 text-sm">7 days after creation</p></div></div>
        <p className="text-xs text-ink-soft">Select the current proof versions to include. Only non-discarded concepts with a proof and passing technical validation are available. Warnings remain visible to the reviewer.</p>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">{eligible.map(concept => {
          const version = concept.latest!;
          return <label key={version.id} className={`cursor-pointer rounded-2xl border p-3 ${chosen.includes(version.id) ? 'border-ink bg-cream' : 'border-ink/10'}`}><div className="mb-3 flex items-start gap-3"><input type="checkbox" className="mt-1 h-4 w-4" checked={chosen.includes(version.id)} onChange={event => setSelected(ids => event.target.checked ? [...ids.filter(id => id !== version.id), version.id] : ids.filter(id => id !== version.id))}/><span className="min-w-0 text-sm font-semibold">{concept.archetype || concept.brief.title || 'Artwork concept'}</span></div><img src={api.proofUrl(version.id)} alt={`Current proof for ${concept.archetype || concept.brief.title || 'artwork'}`} className="h-40 w-full rounded-xl bg-slate-100 object-contain"/><p className="mt-2 text-xs text-ink-soft">Version {version.id.slice(0, 8)} · {reviewDate(version.created_at)}</p>{!!version.warnings && <p className="mt-1 text-xs font-medium text-amber-800">{version.warnings} technical warning{version.warnings === 1 ? '' : 's'}</p>}</label>;
        })}</div>
        {!eligible.length && <p className="rounded-xl bg-cream p-4 text-sm text-ink-soft">No eligible proof versions yet. Generate or repair a concept before creating a client review.</p>}
        {!!warningCount && <p className="rounded-xl bg-amber-50 p-3 text-sm text-amber-950">Selected proofs have {warningCount} technical warning{warningCount === 1 ? '' : 's'}. Creating a review does not resolve these checks or make the artwork production-ready.</p>}
        <button type="submit" disabled={busy || !chosen.length || !title.trim()} className="rounded-xl bg-ink px-4 py-3 text-sm font-semibold text-white disabled:opacity-40">{busy ? 'Working…' : `Create review link${chosen.length ? ` · ${chosen.length} version${chosen.length === 1 ? '' : 's'}` : ''}`}</button>
      </fieldset>
    </form>
    <section className="space-y-3" aria-label="Client review history"><h3 className="font-serif text-xl">Review history</h3>{!loading && !shares.length && <p className="text-sm text-ink-soft">No client reviews have been created for this project.</p>}{shares.map(share => <article key={share.id} className="rounded-2xl border border-ink/10 bg-white p-5"><div className="flex flex-wrap items-start justify-between gap-3"><div><h4 className="font-semibold">{share.title}</h4><p className="mt-1 text-xs text-ink-soft">Created {reviewDate(share.created_at)} · Expires {reviewDate(share.expires_at)}</p></div>{share.revoked_at ? <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-medium text-slate-600">Revoked</span> : Date.parse(share.expires_at) <= Date.now() ? <span className="rounded-full bg-amber-50 px-3 py-1 text-xs font-medium text-amber-900">Expired</span> : <button type="button" disabled={busy} className="text-xs font-semibold text-red-700" onClick={() => setRevokeConfirm(share.id)}>Revoke link</button>}</div>{revokeConfirm === share.id && !share.revoked_at && <div className="mt-3 rounded-xl bg-amber-50 p-3 text-sm"><p>Revoke this link? People holding it will lose access. Recorded responses remain available here.</p><div className="mt-3 flex gap-2"><button type="button" className={button} disabled={busy} onClick={() => revoke(share)}>Revoke this link</button><button type="button" className={button} disabled={busy} onClick={() => setRevokeConfirm(null)}>Keep link active</button></div></div>}<div className="mt-4 space-y-3">{share.items.map(item => <div key={item.version_id} className="rounded-xl bg-cream p-3"><div className="flex flex-wrap items-start justify-between gap-2"><div><p className="text-sm font-semibold">{item.label}</p><p className="mt-1 text-xs text-ink-soft">{item.version_label || `Version ${item.version_id.slice(0, 8)}`}</p></div><span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${item.decision === 'approved' ? 'bg-emerald-100 text-emerald-900' : item.decision === 'changes_requested' ? 'bg-amber-100 text-amber-950' : 'bg-white text-ink-soft'}`}>{item.decision === 'approved' ? 'Client approval recorded' : item.decision === 'changes_requested' ? 'Changes requested' : 'Awaiting response'}</span></div>{!!item.events.length && <details className="mt-3 text-sm"><summary className="cursor-pointer text-xs font-semibold">{item.events.length} recorded response{item.events.length === 1 ? '' : 's'}</summary><ol className="mt-3 space-y-3">{item.events.map(event => <li key={event.id} className="border-t border-ink/10 pt-2"><p className="text-xs"><strong>{event.author}</strong> · {event.action === 'approved' ? 'Approved this version' : event.action === 'changes_requested' ? 'Requested changes' : 'Commented'} · {reviewDate(event.created_at)}</p>{event.body && <p className="mt-1 whitespace-pre-wrap break-words text-sm">{event.body}</p>}</li>)}</ol></details>}</div>)}</div><p className="mt-3 text-xs text-ink-soft">Reviewer names are self-declared through the share link. These decisions do not replace production checks.</p></article>)}</section>
  </section>;
}
