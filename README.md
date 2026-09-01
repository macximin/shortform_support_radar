# Shortform Support Radar

## Current public source coverage

- KOCCA PIMS open programs (`kocca_pims_open`)
- KOCCA PIMS `종료된사업` archive, queried by keyword (`kocca_pims_archive`)
- WelCon / KOCCA export-event announcements
- MCST culture-support announcement index, queried by keyword
- Bizinfo government-support announcement index

On KOCCA PIMS an absent `category` is the open-programs view and `category=4` is
the archive of 2,115 ended programs. The two hold disjoint notices, so both are
registered; the archive is what dates a recurring program's annual cycle.

The registry intentionally excludes e-Naradoum from crawling. It is an application
and subsidy-execution system, so it is a human-led procedural route only after a
specific notice has been selected.

A board that publishes thousands of notices is queried through its own search
index rather than scraped page by page. `mcst_culture_support` (3,383 notices) and
`kocca_pims_archive` (2,115) both carry a `search` block for this reason: on a
date-sorted list, page one is almost never a content call. `search.pages` widens
the window where a board's posting rate can push a still-open notice off page one.

Requests are paced per host across the whole run, so two sources sharing a board
do not fire back to back.

## Run a bounded public canary

```bash
python3 tools/collect_public_notices.py validate
python3 tools/collect_public_notices.py collect --source all --out evidence/2026-09-01/canary
```

Compare two runs to see what opened and what fell off the board:

```bash
python3 tools/collect_public_notices.py diff --previous evidence/2026-09-01/canary --current evidence/2026-09-08/canary
```

Each receipt records per-fetch page hashes and candidate rows only; it does not
store HTML, session state, credentials, applicant data, or application documents.
A candidate carries the `period_start`, `period_end`, and `status_label` the board
already publishes, plus `period_state` and `open_on_observation` computed against
the collection date. `period_state` is `open`, `upcoming`, `closed`, or `null`: a
window that has not started yet is not open, and the radar must not say otherwise.
Both restate the board's own dates and are not eligibility findings.

A page hash cannot answer "what changed": view counters and session tokens move it
on every fetch. Use `diff`, which compares candidate sets.

Run the tests, lint, and type checks:

```bash
python3 -m pip install -e ".[dev]"
python3 tests/test_support_radar.py
python3 -m ruff check src tools tests
python3 -m mypy
```

## Module map

The collection boundary is enforced by types, not by convention. `policy.py` owns
it: a `PublicUrl` cannot be constructed from a credentialed or plaintext URL, the
response cap raises rather than buffers, and `policy_stamp()` is the one place the
candidate-only claim is written.

| Module | Owns |
| --- | --- |
| `policy.py` | `PublicUrl`, response cap, the candidate-only stamp |
| `notice.py` | `NoticePeriod`, `Candidate`, the discovery vocabulary |
| `registry.py` | `Source`, `SearchPlan`, registry parsing |
| `boards.py` | HTML row reading; the only module shaped by how boards render |
| `receipts.py` | `Receipt`, `Fetch`, run-over-run diff |
| `collection.py` | Fetching a source and assembling one receipt |

`Candidate` has no field capable of holding a verdict, and it is not given one.
Whether a company may apply, and whether it would be selected, is decided against
the notice text outside this context.

AI 숏드라마와 Lezhin Snack IP 사업에 관련된 공개 지원사업을 **후보 단계**에서 수집·검증하는 private repository다.

## 범위

- KOCCA, WelCon, KOCCA PMS의 공개 공고 및 첨부문서
- KOFIC, KOTRA, 지역 콘텐츠진흥원, Bizinfo 등 공공·공식 보조 소스
- AI 제작, 방송영상·숏드라마, 웹툰 IP, 해외진출 지원사업

### 등록 현황과 미등록 구간

선언된 범위와 `config/sources.json`의 실제 등록분은 아직 일치하지 않는다.

- 지역 콘텐츠진흥원(경남·충북 콘텐츠코리아랩 등)은 MCST 문화지원사업 통합 색인이 기관 공고를
  모아 싣기 때문에 `mcst_culture_support` 검색을 통해 간접 수집된다. 별도 소스가 아니다.
- KOFIC, KOTRA는 미등록이다. 범위 문장이 곧 수집 근거는 아니므로, 필요해지면 소스로 등록한 뒤에
  수집 대상이라고 기술한다.
- 공고 첨부문서는 수집하지 않는다. 현재 도구는 목록 행만 읽는다.

## 운영 경계

- 수집 결과는 후보이며, 지원가능·선정가능 판단은 공고 원문과 회사의 권리·납세·제재·수출 실적을 대조한 뒤에만 기록한다.
- 신청서 제출, WelCon/PMS 로그인, 계정 생성, 첨부 업로드, 자동 신청은 이 repository의 범위가 아니다.
- 로그인 정보, 세션, API key, 계약서, 권리증빙 원본, 미공개 사업 성과는 저장·커밋하지 않는다.
- Lezhin Snack 또는 관계사의 실제 IP·계약권한은 추정하지 않는다.

## 초기 조사 결론

기존 `shortform_platform`에는 GDELT/RSS/SEC/OpenDART 기반의 시장 신호 후보 수집기가 있으나, KOCCA/WelCon/PMS 공고 전용 수집·첨부 검증 라이브러리는 없다. 이 repository가 그 공백을 소유한다.
