# 2026-09-01 collector v2: row-aware collection, server-side search, run diff

Status: tooling change and discovery only. Nothing here is a funding decision, an
eligibility opinion, or an instruction to apply.

## What was wrong with v1

Measured against the live boards on 2026-09-01:

| Defect | Evidence |
| --- | --- |
| MCST source returned 1 candidate | The board holds 3,383 notices across 339 date-sorted pages. v1 read page one only, where content calls are a rare minority. |
| Deadlines were discarded | KOCCA PIMS rows carry `구분`, `공고일`, `접수기간` (e.g. `26.08.31 ~ 26.09.21`) and MCST carries `모집기간`. The v1 receipt stored only title and URL, so an open call and a closed one were indistinguishable. |
| `page_sha256` could not detect change | Two runs minutes apart returned identical candidate sets on all four sources with different hashes. View counters and session tokens move the hash on every fetch. |
| Navigation links entered the candidate set | `kocca_pims_support_all` returned 5 candidates of which 3 were footer related-agency links (`수출 플러스 지원단`, `뉴콘텐츠기업지원센터`, `지역콘텐츠기업지원센터`). |

## What changed

- **Row-aware parsing.** The collector reads list rows (`<tr>`, `<li>`) instead of
  bare anchors, so a candidate carries `period_start`, `period_end`, and
  `status_label` from the columns the board already publishes.
  `open_on_observation` compares `period_end` to the collection date in KST. It
  restates the board's dates; it is not an eligibility finding.
- **Server-side search.** A source may declare a `search` block. MCST now queries
  its own index for `콘텐츠`, `웹툰`, `만화`, `영상`, `드라마`, `인공지능`,
  `해외진출` rather than scraping page one.
- **Navigation filter.** A row with neither a date nor a recruitment-state label is
  treated as site navigation and dropped.
- **`diff` command.** Compares two receipt directories and reports `appeared` and
  `disappeared` candidates per source. This replaces the page hash as the change
  signal.
- **Charset from the response.** `Content-Type` now decides decoding instead of a
  hardcoded UTF-8. All four current sources declare UTF-8, so this is a guard
  against a future non-UTF-8 board, not a fix for observed corruption.

## Effect

| Source | v1 candidates | v2 candidates | Open on 2026-09-01 |
| --- | --- | --- | --- |
| kocca_pims_support | 8 (3 navigation) | 5 | 0 |
| kocca_pims_support_all | 5 (3 navigation) | 2 | 2 |
| welcon_events | 1 | 1 | 1 |
| mcst_culture_support | 1 | 43 | 0 |
| bizinfo_notices | 3 | 3 | 3 |

Receipts: `evidence/2026-09-01/canary-v5/`. The v1 receipts remain under
`canary-v2` and `canary-v3` for comparison.

## What the MCST search surfaced

The 43 MCST candidates are almost entirely closed calls, which is the useful part:
they date the annual cycle for the programs already on the watchlist.

| Program | Observed 2026 window |
| --- | --- |
| 2026 방송영상콘텐츠제작지원(드라마 장편 부문) | 2026-02-05 ~ 2026-03-04 |
| 2026 방송영상콘텐츠제작지원(드라마 중단편 부문) | 2026-02-05 ~ 2026-03-04 |
| 2026년 인공지능 콘텐츠 제작지원(선도형) 공고 | 2026-02-19 ~ 2026-03-06 |
| 2026년 인공지능 콘텐츠 제작지원(협력형) 수요기업 모집 공고 | 2026-02-23 ~ 2026-03-09 |
| 2026년 인공지능 콘텐츠 제작지원(협력형) 수행기업 모집 공고 | 2026-03-18 ~ 2026-04-02 |
| [재공고] 2026년 인공지능 콘텐츠 제작지원(진입형) 공고 | 2026-04-29 ~ 2026-05-08 |
| 2026년 글로벌 웹툰 IP 제작지원 추가 모집 | 2026-05-22 ~ 2026-06-05 |
| 2026 방송영상콘텐츠제작지원(드라마/장편 부문)_재공고 | 2026-06-29 ~ 2026-07-06 |

The AI 콘텐츠 제작지원 program ran 진입형, 선도형, and 협력형 tracks with repeated
추가모집 and 재공고 rounds from February to June 2026. A single missed February
window did not close the year, but the initial calls opened in February.

These windows are observations of the 2026 round. They are not a commitment that a
2027 round opens, nor that its dates repeat. Treat them as a reason to check the
board from January 2027, not as a schedule.

MCST also aggregates regional agency notices (경남·충북 콘텐츠코리아랩 and others),
so regional programs arrive through this source rather than through separate
regional registrations.

## Open gaps

- No scheduled execution. Every run is manual, and the boards move weekly.
- Notice attachments are not collected; only list rows are read.
- KOFIC and KOTRA appear in the README scope but are not registered sources.
- Search queries are fixed in the registry. A program named outside that vocabulary
  is not discoverable by this radar.
