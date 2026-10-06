# Artifacts

An artifact is any file that entered or left a conversation, agent run, or pipeline. The
requirement is a single page listing everything across all chats, filterable and searchable,
handling every data type, with detection, validation, limits, malware scanning, preview,
versioning, and download.

## 1. Upload path

File bytes never pass through Cloud Run. This is both a cost decision (Cloud Run bills CPU
while proxying) and a correctness one (a 100 MB upload through a request handler is a timeout
and a memory spike waiting to happen).

```mermaid
sequenceDiagram
    participant B as Browser
    participant A as api
    participant DB as Postgres
    participant S as GCS uploads-staging
    participant PS as Pub/Sub
    participant W as worker
    participant C as scanner
    participant G as GCS artifacts

    B->>A: POST /v1/artifacts {filename, byte_size, declared_mime, chat_id}
    A->>A: authorize; check size limit and workspace quota
    A->>DB: artifacts(status=pending) + artifact_versions(v1)
    A->>S: signed resumable upload URL, 15 min,<br/>x-goog-content-length-range bound
    A-->>B: {artifact_id, upload_url, version}
    B->>S: PUT in chunks (resumable, retryable, progress UI)
    S->>PS: OBJECT_FINALIZE
    PS->>W: push (OIDC)
    W->>S: read first 8 KB
    W->>W: magic-byte detection, extension cross-check
    W->>DB: status=scanning, detected_mime, byte_size, sha256
    alt type mismatch or disallowed
        W->>DB: status=failed, reason=unsupported_file_type
        W->>S: delete object
    else allowed
        W->>C: stream scan
        alt clean
            C-->>W: OK
            W->>G: copy to artifacts bucket (CMEK), delete from staging
            W->>W: generate preview + thumbnail
            W->>DB: status=clean, preview_meta
            W->>DB: outbox artifact.ready
        else infected
            C-->>W: FOUND signature
            W->>S: move to quarantine/ prefix
            W->>DB: status=infected, artifact_scans row
            W->>DB: audit security event + notify user
        end
    end
```

Why a staging bucket rather than one bucket with a status column: an unscanned or infected file
must be physically incapable of being served. Staging has no public path, no signed-URL issuance
code path, and a 24-hour lifecycle rule that cleans up abandoned uploads for free. Promotion to
the `artifacts` bucket **is** the clean signal, so a bug in the status check cannot serve
malware.

`x-goog-content-length-range` on the signed URL is what stops a client from ignoring the size
it declared and uploading 10 GB. GCS enforces it, not us.

## 2. Type detection and validation

Order of operations, and the order matters:

1. **Magic bytes** via `python-magic` (libmagic) on the first 8 KB. This is the only source of
   truth.
2. **Extension cross-check.** A `.pdf` whose content is `application/zip` is rejected, not
   silently reclassified — that mismatch is the signature of an attack, not a user mistake.
3. **Declared MIME is logged and ignored** for security decisions. Client-supplied
   `Content-Type` is attacker-controlled.
4. **Structural validation** per type: CSV must parse with a consistent column count (sniffed
   dialect, configurable tolerance); JSON must parse and is depth-limited to 100 and
   size-limited to 50 MB to stop billion-laughs-style expansion; XLSX is opened with
   `openpyxl` in read-only mode with macros and external links rejected; PDF page count is read
   but **no embedded JavaScript is executed, ever**; images are dimension-capped at 50
   megapixels to prevent decompression bombs; archives are **not** extracted server-side.

| Group | Types | Preview |
| --- | --- | --- |
| Tabular | CSV, TSV, XLSX, XLS, Parquet | Virtualized table, first 100 rows, inferred schema, row and column counts |
| Structured | JSON, JSONL, YAML, XML | Collapsible tree, syntax-highlighted, with a search box |
| Documents | PDF, DOCX, TXT, MD, RTF | PDF.js in a **sandboxed iframe**; DOCX converted to HTML server-side |
| Images | PNG, JPEG, GIF, WEBP, SVG | Thumbnail plus full view. **SVG is sanitized with DOMPurify and served from a separate origin**, because SVG is an XSS vector. |
| Code | 40+ languages by extension and shebang | Shiki highlighting, line numbers, copy button |
| Archives | ZIP, TAR, GZ | Listing only, from the central directory. No extraction. |
| Other | Anything passing the scan | Metadata plus download only |

Rejected outright: executables (`.exe`, `.dll`, `.so`, `.app`), scripts with an executable bit,
`.lnk`, Office files with macros (`.docm`, `.xlsm`), and anything libmagic cannot identify.
A denylist alone would be wrong, so the real control is an **allowlist of detected MIME types**
per workspace plan, with the denylist as a second layer.

## 3. Malware scanning

ClamAV as a private Cloud Run service (`scanner`), with `freshclam` updating signatures on
boot and every 6 hours.

| Decision | Reason |
| --- | --- |
| Self-hosted ClamAV rather than VirusTotal | User file content never leaves our perimeter. Sending customer documents to a third-party multi-scanner is a privacy problem and, for some users, a compliance violation. |
| Scan on the staging object, before promotion | The file is unservable until it passes |
| 60-second timeout | On timeout the artifact becomes `failed` with `artifact_scan_failed` and the user can retry. We do **not** fail open. |
| Files over 100 MB | Rejected at reservation time, so the scanner is never the bottleneck |
| Generated artifacts | Also scanned. A model can generate a file from untrusted input, and "we made it so it is safe" is not a security argument. |
| EICAR test file | A permanent E2E test asserts it is quarantined and never downloadable |

ClamAV catches known signatures, not novel or targeted malware. That is stated plainly in the
docs rather than implied otherwise. The real defences against a malicious artifact are that we
never execute files, previews are sandboxed, and downloads are explicit user actions.

## 4. Versioning

`artifacts` is the stable identity; `artifact_versions` holds immutable content. A new version
is a new row with `version + 1`; `artifacts.current_version_id` moves.

- A `message_parts.artifact_version_id` points at a **specific version**, so a transcript
  always shows the file as it was at that moment. A pipeline that overwrites its output weekly
  does not rewrite last week's email attachment.
- GCS object versioning is enabled as a second layer against accidental deletion.
- Version history shows who, when, which run, `byte_size`, and `sha256`, with per-version
  download.
- `sha256` is computed on every version, so re-uploading identical content is detected and
  deduplicated to the same GCS object with a new metadata row — cheap, and common with
  pipelines.

## 5. Download and access

```python
@router.get("/v1/artifacts/{artifact_id}/download")
async def download(artifact_id: UUID, p: Principal = Depends(authorize_artifact_read)):
    v = await get_current_version(artifact_id)
    if v.status != "clean":
        raise ProblemDetail(409, "artifact_not_clean", status=v.status)
    url = await gcs.signed_url(v.gcs_bucket, v.gcs_object, ttl=timedelta(minutes=5),
                               response_disposition=f'attachment; filename="{safe(v.name)}"')
    await audit(p, "artifact.download", artifact_id)
    return RedirectResponse(url, status_code=302)
```

| Control | Value |
| --- | --- |
| Signed URL TTL | 5 minutes. Long enough for a slow connection, short enough that a URL in a shared log or browser history is near-useless. |
| Uniform bucket-level access | Enabled. No per-object ACLs, so object permissions cannot drift from our model. |
| `Content-Disposition` | `attachment` with a sanitized filename, except for inline-previewable types. Prevents a stored HTML or SVG file from executing on our origin. |
| Preview origin | Previews that render untrusted markup (HTML, SVG) are served from a **separate origin** with a restrictive CSP, so an XSS there cannot reach session cookies on the main origin. |
| Audit | Every download is an audit event with actor, IP, and artifact |
| Share-link access | Permitted for artifacts derived from the shared chat ([authorization doc §5](authorization-and-sharing.md)), rate-limited per token |
| Quota | Per-workspace total bytes, checked at reservation. `413 file_too_large` or `402 quota_exceeded` with the current usage in the body. |

## 6. The Artifacts page

```
GET /v1/artifacts
  ?chat_id=         single chat
  &origin=          uploaded | generated
  &mime_group=      tabular | structured | document | image | code | archive | other
  &from=&to=        created_at range
  &status=          clean | scanning | infected | failed
  &run_id=          produced by a specific run
  &q=               name search (trigram) + content search for text types
  &sort=-created_at|name|byte_size
  &cursor=&limit=
```

Name search uses the `gin_trgm_ops` index, so partial and misspelled matches work. Content
search for text-like types is Postgres full-text over an extracted text column, populated at
scan time for CSV headers, JSON keys, PDF text (first 50 pages), and code — capped at 1 MB of
extracted text per artifact. Full-document semantic search is deliberately out of scope; it is
a RAG product, not a file manager.

The page has three views: a grid of type-aware cards with thumbnails, a dense table for bulk
operations, and a timeline grouped by day. Each artifact card links to the chat or run that
produced it, which is the navigation users actually want — "where did this file come from" is
the most common question about a file.

The per-chat panel (`GET /v1/chats/{id}/artifacts`) is the same component with `chat_id` fixed,
satisfying the "per-chat view of all files and artifacts" requirement with no additional
backend work.

## 7. Generated artifacts

When a tool or node produces output, `ctx.emit_artifact()` registers it:

- `origin = 'generated'`, with `created_by_run_id` and `created_by_run_step_id` set.
- Written directly to the artifacts bucket by the worker, then scanned in place before being
  marked `clean`.
- `internal = true` for pipeline intermediates, which keeps them out of the Artifacts page while
  remaining available to the step inspector and to `source.previous_run`. Retention is 30 days,
  except the latest successful output per node, which is kept so week-over-week baselines
  survive.
- Appears in the chat as an `artifact_ref` message part with an inline preview, which is how a
  generated CSV or chart shows up in the conversation rather than as a download link.

## 8. Sandboxed preview in chat

The requirement mentions "sandboxed preview where applicable". Two distinct cases:

**Rendered documents** (PDF, DOCX, SVG, HTML artifacts) go in an `<iframe sandbox>` with no
`allow-same-origin`, served from the separate preview origin, with
`Content-Security-Policy: default-src 'none'; img-src data: blob:; style-src 'unsafe-inline'`.
No script execution, no network, no access to our origin.

**Model-generated interactive code** (a React component, an HTML page the model wrote) is
higher risk because the content is adversarially influenceable. It renders in the same
sandboxed iframe with an explicit "Run preview" click — never automatically — and a visible
banner stating the code is AI-generated and runs in isolation. It executes in the browser only;
there is no server-side execution until the v2 sandbox.

## 9. Testing

| Test | Proves |
| --- | --- |
| EICAR quarantine (E2E) | Infected file is never downloadable and surfaces an `infected` state |
| Extension and magic-byte mismatch | A ZIP renamed `.pdf` is rejected with `unsupported_file_type` |
| Polyglot file | A file valid as both GIF and JS is classified by magic bytes and served `Content-Disposition: attachment` |
| Scan-state gating | `GET /download` returns `409` for `pending`, `scanning`, `infected`, and `failed` |
| Size enforcement | Exceeding the declared length fails at GCS via the content-length-range binding |
| Signed URL expiry | A URL older than 5 minutes returns 403 from GCS |
| Cross-tenant | Workspace A cannot download workspace B's artifact; returns `404`, not `403` |
| Derived share access | A share-link visitor can download artifacts of the shared chat and nothing else |
| Version immutability | A new version does not alter the object a prior message part references |
| Dedupe | Identical content re-uploaded reuses the GCS object and creates a new metadata row |
| Decompression bomb | A 50000x50000 PNG is rejected at the megapixel cap |
| JSON depth bomb | 1000-deep nesting is rejected at depth 100 |
| Preview sanitization | An SVG with an embedded `<script>` has it stripped and is served from the preview origin |

**Not tested:** ClamAV's detection efficacy (that is ClamAV's job), every file format's preview
rendering (one representative per group), and performance of very large file uploads in CI
(covered by a manual pre-release check instead, because a 100 MB upload in CI is slow and
tests the network more than the code).
