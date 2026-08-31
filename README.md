# Shortform Support Radar

## Current public source coverage

- KOCCA PIMS direct-support announcements
- WelCon / KOCCA export-event announcements
- MCST culture-support announcement index
- Bizinfo government-support announcement index

The registry intentionally excludes e-Naradoum from crawling. It is an application
and subsidy-execution system, so it is a human-led procedural route only after a
specific notice has been selected.

## Run a bounded public canary

```bash
python3 tools/collect_public_notices.py validate
python3 tools/collect_public_notices.py collect --source kocca_pims_support --out evidence/2026-09-01/canary
```

Each receipt records a page hash and candidate links only; it does not store HTML,
session state, credentials, applicant data, or application documents.

AI 숏드라마와 Lezhin Snack IP 사업에 관련된 공개 지원사업을 **후보 단계**에서 수집·검증하는 private repository다.

## 범위

- KOCCA, WelCon, KOCCA PMS의 공개 공고 및 첨부문서
- KOFIC, KOTRA, 지역 콘텐츠진흥원, Bizinfo 등 공공·공식 보조 소스
- AI 제작, 방송영상·숏드라마, 웹툰 IP, 해외진출 지원사업

## 운영 경계

- 수집 결과는 후보이며, 지원가능·선정가능 판단은 공고 원문과 회사의 권리·납세·제재·수출 실적을 대조한 뒤에만 기록한다.
- 신청서 제출, WelCon/PMS 로그인, 계정 생성, 첨부 업로드, 자동 신청은 이 repository의 범위가 아니다.
- 로그인 정보, 세션, API key, 계약서, 권리증빙 원본, 미공개 사업 성과는 저장·커밋하지 않는다.
- Lezhin Snack 또는 관계사의 실제 IP·계약권한은 추정하지 않는다.

## 초기 조사 결론

기존 `shortform_platform`에는 GDELT/RSS/SEC/OpenDART 기반의 시장 신호 후보 수집기가 있으나, KOCCA/WelCon/PMS 공고 전용 수집·첨부 검증 라이브러리는 없다. 이 repository가 그 공백을 소유한다.
