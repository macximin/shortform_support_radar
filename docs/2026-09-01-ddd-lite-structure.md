# 2026-09-01 DDD-lite structure

Status: structural change only. Collection behaviour is unchanged, and this note
records no funding decision or eligibility opinion.

## Why

The collector had grown to 453 lines in one file, and the invariants this context
exists to hold were spread across it by convention rather than by structure:

- `is_public_https_url` was called at two sites, and forgetting either would have
  admitted a credentialed URL.
- `candidate_only` and `not_an_eligibility_decision` were dict literals written
  twice, so a third artifact type could have been added without either.
- The response byte cap sat inline in the fetch function.

Those are exactly the rules that separate this radar from an application tool.
They belong in types.

## House convention followed

`bounded context` is used at repo level across this organisation - see
`shortform_platform/AGENTS.md`, `lezhin_webtoon_crawler/README.md`, and
`kidari_ip_catalog/README.md`. No repo layers code into
domain/application/infrastructure, and none is introduced here.

The code shape follows `v4_shortform_script_foundry`: a `pyproject.toml`, a
`src/<package>/` tree with one module per domain concept, and `tools/*.py` CLIs
that insert `src` on the path and import the package. `shortform_script_eval` uses
the same src layout.

## Shape

| Module | Owns |
| --- | --- |
| `policy.py` | `PublicUrl`, response cap, `policy_stamp()` |
| `notice.py` | `NoticePeriod`, `Candidate`, discovery vocabulary |
| `registry.py` | `Source`, `SearchPlan`, registry parsing |
| `boards.py` | HTML row reading |
| `receipts.py` | `Receipt`, `Fetch`, diff |
| `collection.py` | Fetch and assemble one receipt |

`tools/collect_public_notices.py` is now argument parsing and printing only.

What the types now make unrepresentable:

- A `PublicUrl` carrying credentials, a plaintext scheme, or no host. Construction
  raises `PolicyViolation`; `PublicUrl.parse` returns `None` for the filtering
  paths that should skip rather than fail.
- A `Candidate` holding an eligibility verdict. It has no such field, and a test
  asserts both that the serialised form carries no verdict key and that
  constructing one with an `eligible` argument raises.
- A receipt written without the candidate-only stamp. `Receipt.to_json` spreads
  `policy_stamp()`; there is no second literal to drift.

## Equivalence check

`canary-v5` was collected before the refactor and re-collected after it. Every
receipt matched field for field once the volatile fields were excluded
(`observed_at`, `page_sha256`, `requested_url`, `final_url`, `page_bytes`), and
`diff` between the two runs reported 0 appeared and 0 disappeared across all five
sources. The post-refactor run was then deleted; `canary-v5` remains the current
receipt set.

Tests went from 13 to 21, with the new ones concentrated on the boundary rather
than on parsing.

## Unchanged

The CLI, the receipt schema (`shortform-support-radar-public-receipt/v2`), the
registry schema, and the source list are all the same. Scheduled execution remains
absent and is owned by the repository owner.

## Lint and type checking

`ruff` and `mypy` are declared as optional dev dependencies to match the foundry
repo, and are now installed:

```bash
python3 -m pip install -e ".[dev]"
python3 -m ruff check src tools tests
python3 -m mypy
```

`ruff` passed on the first run. `mypy` found two real errors in `registry.py`: the
`ok = False` flag pattern used while validating a `search` block never narrowed
`param` and `queries`, so both reached the `SearchPlan` constructor typed
`Any | None`. Validation now binds a narrowed local per field and bails only after
every field has been checked, which keeps `validate` reporting the whole problem
rather than the first bad field. A test locks that multi-error behaviour in.

The fix changed no output: the five `canary-v5` receipts were reproduced field for
field afterwards, excluding volatile fields.

`.gitignore` gained the foundry entries (`.pytest_cache/`, `.venv/`, `dist/`,
`build/`, `*.egg-info/`) so the editable install leaves nothing tracked. Ruff and
mypy write self-ignoring caches, so those need no entry.
