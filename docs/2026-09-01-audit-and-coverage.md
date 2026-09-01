# 2026-09-01 internal audit: DDD-lite effect, then coverage and correctness fixes

Status: audit and tooling change. No funding decision or eligibility opinion.

## Did the DDD-lite move change behaviour?

Neither up nor down. It was verified neutral: the five `canary-v5` receipts were
reproduced field for field after the refactor, and `diff` between the runs
reported 0 appeared and 0 disappeared. What improved was checkability, not
behaviour - installing the declared `ruff` and `mypy` immediately found two real
type errors in `registry.py` that the flat script had been carrying unchecked.

One deliberate difference: the CLI narrowed its `except` clause from
`(HTTPError, URLError, TimeoutError, ValueError)` to
`(OSError, PolicyViolation, TimeoutError)`. `OSError` still covers both URL
errors, but a plain `ValueError` from anywhere else would no longer be caught,
and under `--source all` that would end the run. A per-source catch-all now
closes that.

So: DDD-lite was neutral on output and positive on defect detection. The findings
below are separate, and they are what the audit was actually for.

## Findings

### 1. The two KOCCA sources were named backwards, and one was misunderstood

Their candidate sets overlapped by zero, which is not what a filter and its
superset look like. Enumerating the parameter settled it:

| `category` | Total notices | What it is |
| --- | --- | --- |
| absent | 5 | the open-programs view |
| `1` | 0 | empty |
| `2` | 0 | empty |
| `3` | 5 | mirrors the open view |
| `4` | 2,115 | the `종료된사업` archive (`activeSubMenu` says so) |

`kocca_pims_support_all` was in fact the *open* view holding 5 notices, and
`kocca_pims_support` was the 2,115-notice archive read one page deep. Renamed to
`kocca_pims_open` and `kocca_pims_archive`, and the meaning of the parameter is
recorded in the registry so the next reader does not have to re-derive it.

### 2. The KOCCA archive was scraped page-one-only

The same defect MCST had. PIMS accepts `search=01` (제목) with `searchWrd` over
GET, so the archive is now queried the way MCST is: 5 candidates became 70.

### 3. A window that had not opened yet was reported as open

`is_open_on` compared only the end date, so a notice accepting applications from
2026-10-01 read as open on 2026-09-01. Corrected to require the window to have
started, and `period_state` now carries `open` / `upcoming` / `closed` / `null`
so the distinction survives into the receipt. The live run caught one real case:
`중소제조 특화 Multi AI Agent 개발(R&D) 점프업 Track`, opening 2026-10-01.

### 4. Requests to a shared host were not paced across sources

Pacing lived inside one source's request loop, so two sources pointing at
`www.kocca.kr` fired back to back. A `HostRateLimiter` now paces per host across
the whole run and counts elapsed time against the interval rather than sleeping
blindly.

### 5. MCST search read one page of a multi-page result

`콘텐츠` alone returns 160 notices across 16 pages at 10 rows a page. Pages 2 and
3 were checked and held no open notice on 2026-09-01, so nothing was being missed
that day - but at roughly 13 postings a month against application windows of
about a month, page one is a thin margin. `search.pages` now exists and MCST uses
2.

## Effect

| Source | Before | After | Open on 2026-09-01 |
| --- | --- | --- | --- |
| kocca_pims_open (was `_all`) | 2 | 2 | 2 |
| kocca_pims_archive (was `kocca_pims_support`) | 5 | 70 | 0 |
| welcon_events | 1 | 1 | 1 |
| mcst_culture_support | 43 | 69 | 0 |
| bizinfo_notices | 3 | 3 | 2 |

Bizinfo's open count fell from 3 to 2 because one of them had not opened yet.

Receipts: `evidence/2026-09-01/canary-v7/`. Receipt schema is now
`shortform-support-radar-public-receipt/v3`, adding `period_state`. Because two
sources were renamed, a diff from `canary-v5` reports their receipts as new
rather than as changes.

## On crawler performance

Measured before the change: 11 requests, 2.51s of network in total (0.23s
average), 0.15s of parsing, and 6.0s of deliberate pacing. Speed was not a
problem and was not optimised. The run is now 24 requests and about 21s, and the
extra time is pacing against public government boards, which is the behaviour we
want. For a radar that should run weekly, wall-clock is not the constraint;
coverage is.

## Still open

- No scheduled execution. Owned by the repository owner.
- Notice attachments are not collected; only list rows are read.
- KOFIC and KOTRA remain unregistered.
- Search vocabulary is fixed in the registry. A program named outside it stays
  invisible to this radar.
- No conditional requests (`ETag` / `If-Modified-Since`). Worth having only if
  the run frequency rises well above weekly.
