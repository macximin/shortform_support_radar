# Shortform Support Radar

## Current public source coverage

- KOCCA PIMS open programs (`kocca_pims_open`)
- KOFIC business notices, probed by keyword (`kofic_business_notices`) - a watch;
  its list carries no 모집기간, so read it with `diff`, not `period_state`
- KOCCA PIMS `종료된사업` archive, queried by keyword (`kocca_pims_archive`)
- WelCon / KOCCA export-event announcements
- MCST culture-support announcement index, queried by keyword
- Bizinfo government-support index, queried by keyword. It aggregates KOCCA,
  KOTRA, and the regional content agencies, so those are reached through it
  rather than registered one by one.

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

A board may carry more than one search axis. Bizinfo indexes by programme name and
by the body running it, and anything KOCCA runs is in scope by the body whatever its
title says.

`allRowsInScope` marks a board whose every row is already in scope, and skips the
discovery vocabulary there. On WelCon's event list the vocabulary dropped 9 of 10
rows, 콘텐츠IP 마켓 and ATF 애니메이션 among them. A row still needs a date or a
recruitment state, so navigation stays out. Broad indexes keep the vocabulary.

Every non-probe query word must exist in the filter vocabulary, and a test enforces
it: querying a board for 만화 and then dropping the result for not saying 웹툰 loses
exactly what was searched for. A `probe` plan is exempt - it widens the net into an
adjacent board with words that are not themselves in scope.

Requests are paced per host across the whole run, so two sources sharing a board
do not fire back to back.

## Daily run

`.github/workflows/daily-radar.yml` collects every day at 04:00 UTC (13:00 KST),
writes the run to `evidence/<date>/daily`, regenerates [STATUS.md](STATUS.md), and
commits. GitHub can start a scheduled run late under load, so treat the hour as
approximate; nothing depends on the exact minute.

[STATUS.md](STATUS.md) is the file to read: what is open, sorted by closing date
with days remaining, plus what appeared since the previous run. Deadlines come
from the boards; eligibility does not.

The job runs on a standard GitHub-hosted runner in a public repository and uploads
no artifacts, so it consumes no billable minutes or storage. Keep it that way -
switching to a larger runner or adding `upload-artifact` would start charges.

## Run a bounded public canary

```bash
python3 tools/collect_public_notices.py validate
python3 tools/collect_public_notices.py collect --source all --out evidence/2026-09-01/canary
```

Compare two runs to see what opened and what fell off the board. `--previous`
defaults to the run before `--current`, so a dated series needs only one argument:

```bash
python3 tools/collect_public_notices.py diff --current evidence/2026-09-08/daily
```

Regenerate the readable summary:

```bash
python3 tools/collect_public_notices.py status --current evidence/2026-09-08/daily --out STATUS.md
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
- KOTRA, 지역 콘텐츠진흥원, Bizinfo 등 공공·공식 보조 소스
- AI 제작, 방송영상·숏드라마, 웹툰 IP, 해외진출 지원사업

### 등록 현황과 미등록 구간

선언된 범위와 `config/sources.json`의 실제 등록분은 아직 일치하지 않는다.

- 지역 콘텐츠진흥원은 MCST 문화지원사업 색인과 Bizinfo가 기관 공고를 모아 싣기 때문에 두 소스의
  검색을 통해 수집된다. 별도 소스가 아니다.
- KOTRA도 Bizinfo를 통해 들어온다. 별도 등록은 중복만 만든다.
- KOFIC은 제외했다. 사업공지 게시판이 전부 영화 사업이고 `인공지능`·`AI`·`숏폼` 제목 검색에
  걸리는 공고가 없으며 Bizinfo에도 올라오지 않는다. 근거는 `config/sources.json#excluded`에 있다.
- 공고 첨부문서는 수집하지 않는다. 현재 도구는 목록 행만 읽는다.

## 운영 경계

- 수집 결과는 후보이며, 지원가능·선정가능 판단은 공고 원문과 회사의 권리·납세·제재·수출 실적을 대조한 뒤에만 기록한다.
- 신청서 제출, WelCon/PMS 로그인, 계정 생성, 첨부 업로드, 자동 신청은 이 repository의 범위가 아니다.
- 로그인 정보, 세션, API key, 계약서, 권리증빙 원본, 미공개 사업 성과는 저장·커밋하지 않는다.
- Lezhin Snack 또는 관계사의 실제 IP·계약권한은 추정하지 않는다.

## 초기 조사 결론

기존 `shortform_platform`에는 GDELT/RSS/SEC/OpenDART 기반의 시장 신호 후보 수집기가 있으나, KOCCA/WelCon/PMS 공고 전용 수집·첨부 검증 라이브러리는 없다. 이 repository가 그 공백을 소유한다.
