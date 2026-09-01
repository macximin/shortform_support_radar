# 2026-09-01 KOFIC and KOTRA assessed; Bizinfo turned into the aggregator route

Status: source assessment and tooling change. No funding decision or eligibility
opinion.

## The question

Both agencies appear in this repository's stated scope but were never registered.
Is there anything at either that reaches AI short drama?

## KOFIC: nothing, and it is excluded on its own terms

Its business board (`promotionBoardList.do`, searchable by title through
`searchTitle`) carries 영화 programs only: 기획개발지원, 독립예술영화 제작지원,
중예산 한국영화 제작지원, 국제공동제작영화, 한국영화 첨단제작 집중지원.

Title searches for `인공지능`, `AI`, and `숏폼` return no notice - the only rows
that come back are navigation chrome. KOFIC also does not appear in Bizinfo under
`영화진흥위원회`.

The reason is structural rather than seasonal. KOFIC's mandate is 영화 under the
영화·비디오물법, and vertical short drama distributed as an app series is not 영화.
Registering it would add requests without adding reachable candidates.

## KOTRA: real programs, but they already arrive through Bizinfo

Searching Bizinfo by 수행기관 `대한무역투자진흥공사` returns its programme stream -
KOTRA-이베이 파워셀러, Invest KOREA Startup Program, 지사화사업, and a long run of
overseas trade fairs. The published programmes are export services and trade
fairs, not content production calls.

Because Bizinfo already carries them, a separate KOTRA source would duplicate what
is collected rather than widen it.

## What the question actually exposed

Bizinfo is not just an SME board. It aggregates:

| Body | Reachable through Bizinfo |
| --- | --- |
| 한국콘텐츠진흥원 (KOCCA) | yes |
| 대한무역투자진흥공사 (KOTRA) | yes |
| 부산정보산업진흥원, 세종테크노파크, 대구디지털혁신진흥원, 경기콘텐츠진흥원, 전남정보문화산업진흥원, 정보통신산업진흥원 | yes |
| 영화진흥위원회 (KOFIC) | no |

And the radar was reading its front page only, with no search - the same defect
already fixed for MCST and the KOCCA archive.

Bizinfo's search rejected a plain GET with HTTP 500. That turned out to be missing
required parameters rather than a session requirement: with the full form set
(`condition1=AND`, `schEndAt=N`, `rowsSel`, `rows`, `cpage`) it answers anonymously,
with no cookie and no login. The boundary is unchanged.

## Effect

| Source | Before | After | Open on 2026-09-01 |
| --- | --- | --- | --- |
| bizinfo_notices | 3 | 22 | 11 |

Open candidates across all sources went from 5 to 14. What the Bizinfo search
surfaced that page one never showed:

- 2026년 ATF 연계 방송콘텐츠 해외유통 지원 사업 (~2026-09-08)
- [세종] 2026년 지역특화콘텐츠개발지원 사업 (웹툰콘텐츠분야) (~2026-09-10)
- [경기] 2026년 문화프로슈머·크라우드 펀딩 콘텐츠 기업 상시모집 (~2026-09-18)
- 2026년 실감콘텐츠 스튜디오 프로젝트 현물지원기업 모집 (~2026-12-01)
- [인천] 2026년 가상융합산업 콘텐츠 제작 장비 임차지원 (~2026-12-31)

These are candidates. None of them has been checked against company eligibility,
regional conditions, or rights.

## One notice, one candidate

Adding a second and third searching source exposed a counting fault: a board
echoes the search term into its detail link, so the same notice reached by two
queries produced two URLs and was counted twice. `Candidate.key()` now drops query
parameters carrying the matched term, so identity is the notice rather than the
path that reached it. The stored URL is left as the board issued it, so the link
still works.

This removed 12 double counts from the KOCCA archive and 1 from Bizinfo. No source
now reports a duplicate title.

## Still open

- No scheduled execution. Owned by the repository owner.
- Notice attachments are not collected; only list rows are read.
- Search vocabulary is fixed in the registry.
- Cross-source duplicates are deliberately kept: 콘텐츠 아메리카 appears under both
  `kocca_pims_open` and `welcon_events`, and each is a real observation of a
  separate board.
