# PDF extraction and client review — 5 September 2026

This milestone connects source PDFs to the identity review workflow and gives clients a separate, version-specific artwork review screen. Both are implemented in the app and tested locally. No public deployment, email delivery or client authentication service was added.

## PDF workflow

Open a brand → Sources & fonts → Read guidance from a PDF. Upload a source if necessary, select it, optionally inspect its physical page count, then extract all pages or a range such as `56-57,107-108`.

The worker renders each page with Poppler, supplies its visible image and text layer to Opus 4.8, and requests structured findings in batches of four pages. Each finding preserves its physical PDF page, source hash, short evidence quote, scope, conditions and model confidence. Confidence is the model's assessment, not calibrated accuracy or human approval. The model has no filesystem/network tools; source content is evidence, not instructions. Output is validated and its citation URL/status are assigned by the server.

Jobs persist progress, completed findings, failures and recorded usage. Reloading the browser retains the job. A worker restart marks unfinished jobs stopped and preserves completed findings; remaining pages need an explicit new run. The current implementation uses one process-local extraction queue, not a distributed task service. Maximum 300 pages per run; maximum 500 cards on an identity board. Poppler is required locally and added to the worker Dockerfile.

Importing selected findings merges them into the current identity draft with revision-conflict protection and exact-card deduplication. Findings start as draft and must be reviewed, provisionally accepted or rejected before publication. Publication is blocked server-side while draft cards remain. Re-running a model can paraphrase a finding, so semantic duplicates still need human review. Working fonts and swatches are never created or changed automatically. Literal colour transcriptions are treated as source evidence and excluded from model guidance even after review; intended values belong in Definitions.

### Live check

The supplied 115-page No7 BVI was processed for pages 56, 57, 107 and 108. One Opus 4.8 call produced 21 draft findings; recorded cost was $0.18228 using the app's rate table. Inspection against all four rendered pages confirmed useful logo/palette findings, including the conflicting hidden text beneath the visible PF Violet swatch. This is a four-page integration check, not a claim of complete PDF extraction accuracy. The model also separated illustrative advertising copy from approved live copy.

The findings remain in the benchmark brand's extraction history, without changing its 86-card identity draft or published version 4. Import, rejection and publication were exercised in an isolated QA database.

## Client review workflow

Open a project and find Client review & approval below its artwork. Select current, technically valid proof versions, enter a review title and create a link. The screen shows a copyable link and a client preview. No message is sent. The UI issues seven-day links; the API permits 1–30 days. Links can be revoked from the project history.

The client page displays only the selected proofs, version references, warning counts, feedback and decision controls. Reviewers enter a name, then comment, request changes or explicitly approve the displayed version. Proof loading and a confirmation checkbox are required by the UI for approval. Names are self-declared; link possession is the access mechanism, not verified client identity. One final decision is allowed per version per review; comments remain available afterward. A new decision requires a new review.

Reviews snapshot exact version IDs, document hashes and proof hashes. Newer or discarded artwork cannot receive approval through an older review. Decisions never modify model self-approval or carry forward to later versions. Events are append-only, timestamped and protected against duplicate retries and simultaneous conflicting decisions. Tokens are random, returned only at creation and stored as hashes. Public responses omit briefs, profiles, source assets, generation costs and internal critique.

### Delivery boundary

The private studio worker remains unauthenticated and must stay private. The new `services/worker/review_app.py` is a separate delivery surface exposing only `/api/client-reviews/*`, its client-only index and built UI assets. Studio, source, document-download and API-documentation routes return 404. It uses no-store, no-referrer, nosniff and frame restrictions. Configure HTTPS/proxy access-log redaction before public use: review tokens are bearer capabilities in API paths.

Run the review surface beside the private worker, using the same SQLite database and compiled UI:

```sh
WORKER_DB=/absolute/path/ide8.db \
UI_DIST=/absolute/path/services/ui/dist \
PYTHONPATH=/absolute/path/services/worker \
python -m uvicorn review_app:build_app --factory --host 127.0.0.1 --port 8134 --no-access-log
```

Set `CLIENT_REVIEW_BASE_URL` on the studio worker to the delivery origin. Without it, links use the current studio origin for local preview only. In the current benchmark, 8132 is the studio and 8134 is the restricted review page, both using the benchmark database. The original app on 5174/8200 uses its separate database and is not connected to the benchmark's review origin. Public hosting and a choice of verified-login requirements remain rollout work.

## Verification and retained evidence

- 280 worker unittest tests passed, including extraction page bounds, source isolation, partial failures/usage retention, draft merge and publication guards, review token scope, idempotency/concurrency, revocation/expiry, superseded versions and restricted delivery routes.
- TypeScript typecheck and Vite production build passed. At the PR checkpoint, the updated worker Docker image built successfully; an isolated container smoke check loaded both document schemas, all three required Poppler tools and the worker application.
- Browser QA: real PDF page inspection/extraction; candidate selection/import; draft publication disabled; reject/save/publish in isolated QA; client comment, approval and change request; reload persistence; studio history; link revocation and denied access.
- The dedicated local review server successfully displayed a selected real proof. Its studio endpoints were probed and returned 404.
- Exact pre/post database comparisons confirmed unchanged projects, concepts, document versions, assets, published brands and existing identity drafts in both real databases. Zero real client decision events were submitted. The isolated QA database contains explicitly labelled simulated decisions only.

Local evidence and pre-feature backups live under `out/no7-trial/extraction-approval/`. No7 extraction ID: `4a5871ccc7ba4c36a2a71ef9c5b59ad2`. An unsubmitted internal review preview of the fresh Diagonal energy proof was created in the real benchmark for Luke to inspect; it remains awaiting response. Its raw token is intentionally omitted from this repository document.
