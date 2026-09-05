import {useEffect, useRef, useState} from 'react';

export type ReviewAction = 'comment' | 'approved' | 'changes_requested';
export interface ClientReviewEvent {
  id: string; author: string; body: string; action: ReviewAction; created_at: string;
}
export interface ClientReviewItem {
  version_id: string; concept_id: string; label: string; version_label: string;
  decision: null | 'approved' | 'changes_requested'; events: ClientReviewEvent[];
  content_hash?: string; proof_url?: string; superseded?: boolean; warning_count?: number;
}
interface Review {
  id: string; title: string; project_name: string; created_at: string; expires_at: string;
  items: ClientReviewItem[];
}

const field = 'w-full rounded-xl border border-ink/20 bg-white px-3 py-3 text-sm outline-none focus:border-ink disabled:opacity-50';
const button = 'rounded-xl border border-ink/20 bg-white px-4 py-2 text-sm font-semibold disabled:opacity-40';
const decisionLabel = (decision: ClientReviewItem['decision']) => decision === 'approved' ? 'Approval recorded' : decision === 'changes_requested' ? 'Changes requested' : 'Awaiting your review';

export function reviewDate(value: string): string {
  const date = new Date(/^\d{4}-\d\d-\d\d[ T]\d\d:\d\d:\d\d(?:\.\d+)?$/.test(value) ? value.replace(' ', 'T') + 'Z' : value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString(undefined, {dateStyle: 'medium', timeStyle: 'short'});
}

export async function reviewResponse<T>(response: Response): Promise<T> {
  if (response.status === 204) return undefined as T;
  if (response.ok) return response.json() as Promise<T>;
  let detail = '';
  try {const data = await response.json(); if (typeof data.detail === 'string') detail = data.detail;} catch { /* Keep a useful status message for non-JSON failures. */ }
  if (response.status === 410) throw new Error(detail || 'This review link has expired or been revoked. Ask the studio for a new link.');
  if (response.status === 404 || response.status === 403) throw new Error(detail || 'This review is unavailable. Check the link or ask the studio for a new one.');
  if (response.status === 409) throw new Error(detail || 'This version has changed or already received a decision. Refresh the review before continuing.');
  throw new Error(detail || `The request could not be completed (${response.status}). Please try again.`);
}

function ReviewArtwork({item, token, author, onRefresh}: {item: ClientReviewItem; token: string; author: string; onRefresh: () => Promise<void>}) {
  const [body, setBody] = useState('');
  const [action, setAction] = useState<ReviewAction>('comment');
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [expanded, setExpanded] = useState(false);
  const [proofFailed, setProofFailed] = useState(false);
  const [proofLoaded, setProofLoaded] = useState(false);
  const [recordedDecision, setRecordedDecision] = useState<ClientReviewItem['decision']>(null);
  const attempt = useRef<{signature: string; key: string} | null>(null);
  const decision = item.decision || recordedDecision;
  const versionLabel = item.version_label || `Version ${item.version_id.slice(0, 8)}`;
  const canDecide = !decision;
  const canApprove = canDecide && !item.superseded && proofLoaded && !proofFailed && !!item.proof_url;
  const formValid = !!author.trim() && (action === 'approved' ? canApprove && confirmed : !!body.trim()) && (action === 'comment' || canDecide);

  useEffect(() => {
    if (decision || (item.superseded && action === 'approved')) {setAction('comment'); setConfirmed(false);}
  }, [decision, item.superseded, action]);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!formValid || busy) return;
    const payload = {version_id: item.version_id, author: author.trim(), body: body.trim(), action};
    const signature = JSON.stringify(payload);
    if (attempt.current?.signature !== signature) attempt.current = {signature, key: crypto.randomUUID()};
    setBusy(true); setError(''); setNotice('');
    try {
      await reviewResponse<ClientReviewEvent>(await fetch(`/api/client-reviews/${encodeURIComponent(token)}/events`, {
        method: 'POST', headers: {'content-type': 'application/json'},
        body: JSON.stringify({...payload, idempotency_key: attempt.current.key}),
      }));
      if (action !== 'comment') setRecordedDecision(action);
      setBody(''); setConfirmed(false); setAction('comment'); attempt.current = null;
      setNotice(action === 'comment' ? 'Your comment has been recorded.' : action === 'approved' ? `Your approval of ${versionLabel} has been recorded.` : `Your change request for ${versionLabel} has been recorded.`);
      try {await onRefresh();} catch {setError('Your response was recorded, but the latest review could not be loaded. Use Refresh review to see it.');}
    } catch (reason) {
      // Keep this submission's key after an uncertain network response. Retrying
      // identical content cannot accidentally create a duplicate approval/event.
      setError(reason instanceof Error ? reason.message : 'Your response could not be confirmed. Retry to check or record it safely.');
    } finally {setBusy(false);}
  };

  return <article className="overflow-hidden rounded-3xl border border-ink/10 bg-white shadow-sm">
    <header className="flex flex-wrap items-start justify-between gap-3 border-b border-ink/10 p-5 sm:p-6">
      <div><p className="text-xs uppercase tracking-widest text-ink-soft">{versionLabel}</p><h2 className="mt-1 font-serif text-2xl">{item.label || 'Artwork'}</h2></div>
      <span className={`rounded-full px-3 py-1.5 text-xs font-semibold ${decision === 'approved' ? 'bg-emerald-50 text-emerald-800' : decision === 'changes_requested' ? 'bg-amber-50 text-amber-900' : 'bg-slate-100 text-slate-700'}`}>{decisionLabel(decision)}</span>
    </header>
    <div className="grid lg:grid-cols-[minmax(0,1.2fr)_minmax(20rem,1fr)]">
      <div className="min-w-0 bg-slate-100 p-4 sm:p-6">
        <div id={`proof-${item.version_id}`} className={`rounded-xl border border-ink/10 bg-white ${expanded ? 'max-h-[75vh] overflow-auto' : 'overflow-hidden p-2'}`}>
          {item.proof_url && !proofFailed ? <img src={item.proof_url} alt={`${item.label || 'Artwork'}, ${versionLabel}`} className={expanded ? 'block w-auto max-w-none' : 'mx-auto block max-h-[65vh] w-full object-contain'} onLoad={() => setProofLoaded(true)} onError={() => {setProofFailed(true); setProofLoaded(false);}}/> : <div className="p-6"><p role="alert" className="text-sm text-red-800">The proof could not be loaded. Check the proof before making an approval decision.</p>{item.proof_url && <button type="button" className={`${button} mt-3`} onClick={() => {setProofLoaded(false); setProofFailed(false);}}>Retry proof</button>}</div>}
        </div>
        <button type="button" className={`${button} mt-3`} aria-controls={`proof-${item.version_id}`} aria-expanded={expanded} disabled={proofFailed || !item.proof_url} onClick={() => setExpanded(value => !value)}>{expanded ? 'Fit artwork to view' : 'Inspect at full size'}</button>
        <p className="mt-3 text-xs leading-relaxed text-ink-soft">This proof identifies the exact artwork version being reviewed. Later artwork revisions do not replace this proof.</p>
        {item.content_hash && <details className="mt-3 text-xs text-ink-soft"><summary className="cursor-pointer">Version reference</summary><p className="mt-2 break-all">{item.content_hash}</p></details>}
      </div>
      <div className="min-w-0 space-y-5 p-5 sm:p-6">
        {item.superseded && <p className="rounded-xl bg-amber-50 p-3 text-sm text-amber-950">The studio has a newer version of this artwork. You can comment or request changes on this proof, but approval is disabled. Ask the studio for the latest review link.</p>}
        {!!item.warning_count && <p className="rounded-xl border border-amber-200 bg-amber-50/60 p-3 text-sm text-amber-950">The studio’s technical checks reported {item.warning_count} warning{item.warning_count === 1 ? '' : 's'} on this version. Ask the studio about any concern before approving.</p>}
        {decision && <p className="text-sm text-ink-soft">A decision has been recorded for this version in this review. You can still add comments. A new decision requires a new review from the studio.</p>}
        <form className="space-y-3" onSubmit={submit}>
          <fieldset disabled={busy} className="space-y-3">
            <label className="block text-sm font-semibold" htmlFor={`action-${item.version_id}`}>Your response</label>
            <select id={`action-${item.version_id}`} className={field} value={action} onChange={event => {setAction(event.target.value as ReviewAction); setConfirmed(false); setNotice('');}}>
              <option value="comment">Add a comment</option>
              <option value="changes_requested" disabled={!canDecide}>Request changes</option>
              <option value="approved" disabled={!canApprove}>Approve this version</option>
            </select>
            <label className="block text-sm" htmlFor={`body-${item.version_id}`}>{action === 'approved' ? 'Note (optional)' : action === 'changes_requested' ? 'What needs to change?' : 'Comment'}</label>
            <textarea id={`body-${item.version_id}`} className={field} rows={4} maxLength={5000} required={action !== 'approved'} value={body} onChange={event => setBody(event.target.value)} placeholder={action === 'changes_requested' ? 'Describe the change and where it is needed…' : 'Share your feedback…'}/>
            {action === 'approved' && <label className="flex items-start gap-3 rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-sm"><input className="mt-1 h-4 w-4 shrink-0" type="checkbox" checked={confirmed} onChange={event => setConfirmed(event.target.checked)}/><span>I approve <strong>{item.label || 'this artwork'} — {versionLabel}</strong>, exactly as shown in this proof.</span></label>}
            {!author.trim() && <p className="text-xs text-ink-soft">Enter your name at the top of this page to send a response.</p>}
            <button type="submit" disabled={busy || !formValid} className="w-full rounded-xl bg-ink px-4 py-3 text-sm font-semibold text-white disabled:opacity-40">{busy ? 'Recording response…' : action === 'approved' ? 'Record approval' : action === 'changes_requested' ? 'Send change request' : 'Post comment'}</button>
          </fieldset>
          {error && <p role="alert" className="rounded-xl bg-red-50 p-3 text-sm text-red-800">{error}</p>}
          {notice && <p role="status" className="rounded-xl bg-emerald-50 p-3 text-sm text-emerald-900">{notice}</p>}
        </form>
        <section aria-label={`Responses for ${item.label}`} className="border-t border-ink/10 pt-4">
          <h3 className="text-sm font-semibold">Review history</h3>
          {!item.events.length ? <p className="mt-3 text-sm text-ink-soft">No responses yet.</p> : <ol className="mt-3 space-y-3">{item.events.map(event => <li key={event.id} className="rounded-xl bg-cream p-3 text-sm"><div className="flex flex-wrap items-baseline justify-between gap-2"><strong>{event.author}</strong><time className="text-xs text-ink-soft" dateTime={event.created_at}>{reviewDate(event.created_at)}</time></div><p className="mt-1 text-xs font-semibold text-ink-soft">{event.action === 'approved' ? 'Approved this version' : event.action === 'changes_requested' ? 'Requested changes' : 'Commented'}</p>{event.body && <p className="mt-2 whitespace-pre-wrap break-words leading-relaxed">{event.body}</p>}</li>)}</ol>}
        </section>
      </div>
    </div>
  </article>;
}

export default function ClientReview({token}: {token: string}) {
  const [review, setReview] = useState<Review | null>(null);
  const [author, setAuthor] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const endpoint = `/api/client-reviews/${encodeURIComponent(token)}`;
  const activeEndpoint = useRef(endpoint);
  activeEndpoint.current = endpoint;
  const refresh = async () => {
    const next = await reviewResponse<Review>(await fetch(endpoint, {cache: 'no-store'}));
    if (activeEndpoint.current !== endpoint) return;
    setReview(next); setError('');
  };
  useEffect(() => {
    const controller = new AbortController(); setLoading(true); setReview(null); setError(''); setAuthor('');
    fetch(endpoint, {signal: controller.signal, cache: 'no-store'}).then(reviewResponse<Review>).then(next => {if (!controller.signal.aborted) setReview(next);}).catch(reason => {if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : 'The review could not be loaded.');}).finally(() => {if (!controller.signal.aborted) setLoading(false);});
    return () => controller.abort();
  }, [endpoint]);

  return <main className="min-h-screen bg-paper px-4 py-8 text-ink sm:px-8 sm:py-12"><div className="mx-auto max-w-7xl space-y-7">
    <header className="flex flex-wrap items-start justify-between gap-4"><div><p className="text-xs font-semibold uppercase tracking-[.2em] text-ink-soft">Artwork review</p><h1 className="mt-3 font-serif text-3xl sm:text-4xl">{review?.title || 'Your artwork review'}</h1>{review && <p className="mt-2 text-sm text-ink-soft">{review.project_name} · Link expires {reviewDate(review.expires_at)}</p>}</div><button type="button" className={button} disabled={loading} onClick={async () => {setLoading(true); try {await refresh();} catch (reason) {setError(reason instanceof Error ? reason.message : 'The review could not be refreshed.'); setReview(null);} finally {setLoading(false);}}}>{loading ? 'Loading…' : 'Refresh review'}</button></header>
    {error && <div role="alert" className="rounded-2xl border border-red-200 bg-red-50 p-5 text-red-900"><h2 className="font-semibold">Review unavailable</h2><p className="mt-2 text-sm">{error}</p></div>}
    {review && <><section className="grid gap-5 rounded-2xl border border-ink/10 bg-white p-5 sm:grid-cols-[minmax(14rem,22rem)_1fr]"><label className="text-sm font-semibold" htmlFor="reviewer-name">Your name<input id="reviewer-name" className={`${field} mt-2`} autoComplete="name" maxLength={120} value={author} onChange={event => setAuthor(event.target.value)} placeholder="Name shown with your feedback"/></label><p className="self-center text-sm leading-relaxed text-ink-soft">Anyone with this link can respond. Your name is self-declared; this page does not verify your identity. Approval records your decision on the exact version shown, separately from the studio’s automated checks.</p></section>{review.items.map(item => <ReviewArtwork key={`${review.id}-${item.version_id}`} item={item} token={token} author={author} onRefresh={refresh}/>)}{!review.items.length && <p className="rounded-2xl bg-white p-6 text-sm text-ink-soft">No artwork versions are included in this review.</p>}</>}
    {!review && loading && <p role="status" className="py-12 text-center text-ink-soft">Loading the shared artwork…</p>}
  </div></main>;
}
