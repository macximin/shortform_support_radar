# 2026-09-01 Board-defined scope, vocabulary alignment, and KOFIC registered

Status: source and tooling change. No funding decision or eligibility opinion.

## KOFIC: the earlier assessment was too strong

The previous note concluded KOFIC had nothing reachable and excluded it. That was
based on title searches for 인공지능, AI and 숏폼 returning no notice, which was
true but too narrow a probe. Searching its board for 첨단 and 온라인 returns:

- 2025년 첨단영화제작교육 - AI 단편영화제작 교육 - 교육생 모집
- 일자리 연계형 온라인·뉴미디어 영상콘텐츠 제작지원사업 (시행공고, 심사결과, 선정자 공고)

KOFIC does fund AI filmmaking education, and has run an online/new-media video
content production programme. Neither is short drama, and both are historical, but
"nothing here" was the wrong call. It is now registered as a watch.

Its board publishes 작성일자 only, with no 모집기간 column, so its candidates carry
no period and never report as open. The board is a change signal, not a deadline
source: use `diff` on it rather than `period_state`.

## The discovery vocabulary was subtracting real notices

Two faults, both found by looking at what the filter dropped rather than at what
it kept.

**The filter vocabulary and the query vocabulary disagreed.** The registry queried
MCST and Bizinfo for 만화 and 애니메이션, and the filter held neither word, so a
title that said only 만화 was searched for and then discarded. Both words are now
in `KEYWORDS`, and a test now fails if any non-probe query names a word the filter
cannot match.

**A content agency's own board was being screened as if it were a mixed index.**
The vocabulary gate exists to separate notices from navigation on a broad board.
On WelCon's event list, where every row is a content export event, it dropped 9 of
10 rows:

| Dropped by the vocabulary | |
| --- | --- |
| 2026 콘텐츠IP 마켓 | has 콘텐츠 but no 공고/모집 wording |
| 아시아 TV 포럼 & 마켓 (애니메이션) | event name only |
| 2026 KOMICS Thailand | event name only |
| 2026 한태 K-콘텐츠 비즈위크(2차) | event name only |
| 2026 론치패드 싱가포르 / UAE 참가기업 추가모집 | no vocabulary word |

`allRowsInScope` now marks a board whose every row is already in scope, and the
vocabulary is skipped there. A row still needs a date or a recruitment state, so
navigation is still excluded. Applied to `kocca_pims_open` and `welcon_events`; not
to MCST, Bizinfo, or the KOCCA archive, where most rows belong to other sectors.

## Probe searches

KOFIC is queried with 첨단, 온라인 and 시리즈, none of which belong in the global
vocabulary - putting 온라인 there would flood MCST and Bizinfo. A `probe` flag marks
a plan that deliberately searches outside the vocabulary and lets the filter screen
what comes back. The consistency test skips probe plans and enforces the invariant
everywhere else.

## Bizinfo gained a second axis

Bizinfo indexes by programme name and by the body running the programme. Anything
KOCCA runs is in scope by the body, whatever its title says, so
`condition=searchExcInsttNm` with 한국콘텐츠진흥원 was added alongside the title
queries. It surfaced 3 notices the title search missed.

The agency axis was not extended to KOTRA or NIPA: those returned 15 and 5 extra
rows respectively, almost all outside scope (방산 멘토링, BABY AND KIDS FAIR,
공개SW 유공자 표창). A body-level axis only pays where the body's whole mandate is
in scope.

Adding a second axis exposed a counting fault the previous fix did not cover.
Bizinfo echoes both the search field and the term into its detail link, so one
notice reached by a title hit and an agency hit differed by two parameters, not
one. Identity now strips every parameter the source's searches inject, taken from
the plans themselves rather than guessed.

## Effect

| Source | Before | After | Open on 2026-09-01 |
| --- | --- | --- | --- |
| kocca_pims_open | 2 | 6 | 5 |
| kocca_pims_archive | 58 | 58 | 0 |
| welcon_events | 1 | 10 | 3 |
| kofic_business_notices | - | 11 | 0 (board has no period column) |
| mcst_culture_support | 69 | 71 | 0 |
| bizinfo_notices | 22 | 23 | 12 |

Open candidates went from 14 to 20. Receipts: `evidence/2026-09-01/canary-v9/`.
179 candidates, no duplicate title within any source. Cross-source duplicates are
kept deliberately: 콘텐츠 아메리카 is a real observation of both the KOCCA board and
WelCon.

The run is 38 requests and about 38s, nearly all of it pacing.

## Still open

- No scheduled execution. Owned by the repository owner.
- Notice attachments are not collected; only list rows are read.
- KOFIC candidates carry no period, so open/closed cannot be read from its list.
- Search vocabulary is fixed in the registry.
