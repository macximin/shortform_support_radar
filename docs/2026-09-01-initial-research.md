# 2026-09-01 initial public support-program scan

Status: discovery only. This note is not a funding decision, an eligibility
opinion, or an instruction to apply.

## Time-sensitive public candidates

| Candidate | Observed status | Relevance | Required human check before any application |
| --- | --- | --- | --- |
| [2027 Content Americas Korea Pavilion and showcase](https://welcon.kocca.kr/ko/event/content-americas-2027--578) | Open 2026-08-31 to 2026-09-21 11:00; broadcast category | Conditional export route for a short-drama producer/distributor. The notice asks for overseas broadcast/OTT references **or** strong content-IP business competitiveness, and requires both pavilion and showcase participation. | Applicant entity, export/OTT or IP evidence, ability to present, cost exposure (airfare/lodging are excluded), and who may represent each IP. |
| [Suncheon 2026 global IP creation/production support](https://www.bizinfo.go.kr/sii/siia/selectSIIA200Detail.do?pblancId=PBLN_000000000125979) | Listed as 2026-08-25 to 2026-09-09; regional program | A live IP-production candidate, but not proof that a Lezhin Snack title, its rightsholder, or an AI short-drama producer qualifies. | Full notice, regional/company requirements, permitted rights chain, matching-fund terms, and output obligations. |
| [Gyeonggi AI Cluster SLUSH participation](https://www.bizinfo.go.kr/sii/siia/selectSIIA200Detail.do?pblancId=PBLN_000000000125977) | Listed as 2026-08-28 to 2026-09-11; export category | General AI-export candidate. It is not content-specific, so it ranks below direct content programs. | Gyeonggi cluster eligibility, company technology fit, overseas-event costs, and whether the project can be described without unapproved IP claims. |

The linked Content Americas notice provides six places and includes business
matching, showcase, and promotional support; it explicitly excludes airfare,
lodging, and international freight. The source, not this scan, is authoritative
for the current terms.

## 2027 planning watchlist (not open calls)

- **MCST/KOCCA AI content production support**: the 2026 program announced KRW
  19.8 billion total across entry, leading, and collaboration tracks. It is the
  strongest recurring watch for an AI short-drama production plan, but the 2026
  call is historical/closed and must not be treated as open.
- **MCST/KOCCA broadcast-video production support**: 2026 included an LG Channel
  original route for domestic small/mid-sized broadcast-video production firms.
  It is a useful next-cycle marker, not a currently open opportunity. Its
  published structure involved joint IP ownership with LG, so no title can be
  proposed without an explicit rights and commercial review.
- **Webtoon/IP export and production calls**: track KOCCA and regional content
  agencies for a new round. “Webtoon”, “IP”, or “AI” in a title is only a search
  signal, not a grant-fit conclusion.

## Ministry and subsidy-system split

- **MCST**: a policy/announcement index and the ministry behind the KOCCA paths.
  The crawler includes its public culture-support index as a discovery source.
- **MOEF / e-Naradoum**: treated as the national subsidy-application/execution
  route, not as a direct content-call source. The radar does not log in, collect
  applicant information, upload anything, or attempt an application. Once a
  human selects a specific official call, its stated e-Naradoum requirements can
  be checked manually.

## Evidence and operation

The initial no-auth canary receipts are under
`evidence/2026-09-01/canary-v2/`. They retain source URL, observed time, page
SHA-256, byte count, and matching links only—never HTML, cookies, credentials,
application forms, applicant data, or rights documents.

Run the collector only against the registry:

```bash
python3 tools/collect_public_notices.py validate
python3 tools/collect_public_notices.py collect --source welcon_events --out evidence/YYYY-MM-DD/canary
```

Any candidate must pass a separate human review for entity eligibility, regional
conditions, tax/subsidy restrictions, ownership/representation rights, and
application contents. No collection result can promote a Lezhin Snack title or
an AI short-drama proposal.

## Public sources

- [WelCon: Content Americas 2027](https://welcon.kocca.kr/ko/event/content-americas-2027--578)
- [WelCon: 2026 AI content production-support announcement](https://welcon.kocca.kr/ko/info/business/1957212)
- [Bizinfo: Suncheon global IP creation/production](https://www.bizinfo.go.kr/sii/siia/selectSIIA200Detail.do?pblancId=PBLN_000000000125979)
- [Bizinfo: Gyeonggi AI Cluster SLUSH](https://www.bizinfo.go.kr/sii/siia/selectSIIA200Detail.do?pblancId=PBLN_000000000125977)
- [Bizinfo: 2026 LG Channel original production-support archive](https://www.bizinfo.go.kr/sii/siia/selectSIIA200Detail.do?pblancId=PBLN_000000000118683)
- [MCST culture-support index](https://www.mcst.go.kr/site/s_culture/cultureSp/cultureSpList.jsp)
- [e-Naradoum public portal](https://www.gosims.go.kr/)
