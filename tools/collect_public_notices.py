#!/usr/bin/env python3
"""CLI over the support radar: validate the registry, collect receipts, diff runs.

The collection boundary lives in the package, not here. This file only parses
arguments and prints results.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from shortform_support_radar.collection import HostRateLimiter, collect, today_kst, utc_now  # noqa: E402
from shortform_support_radar.notion import (  # noqa: E402
    NotionConfig,
    NotionNotConfigured,
    apply_sync,
    create_payload,
    existing_keys,
    plan_sync,
)
from shortform_support_radar.policy import PolicyViolation  # noqa: E402
from shortform_support_radar.receipts import (  # noqa: E402
    diff_directories,
    load_directory,
    previous_run_dir,
    status_markdown,
)
from shortform_support_radar.registry import load_registry  # noqa: E402


def run_validate(sources: list, errors: list[str]) -> int:
    if errors:
        print(json.dumps({"status": "invalid", "errors": errors}, ensure_ascii=False))
        return 2
    print(json.dumps({"status": "valid", "source_count": len(sources)}, ensure_ascii=False))
    return 0


def run_collect(sources: list, selector: str, out_dir: Path) -> int:
    if selector == "all":
        selected = sources
    else:
        selected = [source for source in sources if source.id == selector]
        if not selected:
            print(json.dumps({"status": "error", "error": f"unknown source: {selector}"}, ensure_ascii=False))
            return 2

    # One limiter across the run: two sources can share a host, and pacing must
    # hold across that boundary as well as inside a source.
    limiter = HostRateLimiter()
    exit_code = 0
    for source in selected:
        try:
            receipt = collect(source, limiter=limiter)
        except (OSError, PolicyViolation, TimeoutError) as error:
            print(json.dumps({"status": "error", "source": source.id, "error": str(error)}, ensure_ascii=False))
            exit_code = 1
            continue
        except Exception as error:  # noqa: BLE001 - one bad board must not end the run
            print(
                json.dumps(
                    {"status": "error", "source": source.id, "error": f"{type(error).__name__}: {error}"},
                    ensure_ascii=False,
                )
            )
            exit_code = 1
            continue
        path = receipt.write(out_dir)
        print(
            json.dumps(
                {
                    "status": "ok",
                    "source": source.id,
                    "receipt": str(path),
                    "candidate_count": len(receipt.candidates),
                    "open_candidate_count": receipt.open_candidate_count,
                },
                ensure_ascii=False,
            )
        )
    return exit_code


def run_notion(current: Path, dry_run: bool) -> int:
    documents = load_directory(current)
    observed_on = today_kst()
    if dry_run:
        creates, updates = plan_sync(documents, observed_on, {})
        preview = [
            create_payload(e["candidate"], e["source_id"], observed_on, "DRY-RUN")["properties"]
            for e in creates[:3]
        ]
        print(
            json.dumps(
                {
                    "status": "dry-run",
                    "would_create_or_refresh": len(creates) + len(updates),
                    "sample_properties": preview,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    try:
        config = NotionConfig.from_env()
    except NotionNotConfigured as error:
        print(json.dumps({"status": "skipped", "reason": str(error)}, ensure_ascii=False))
        return 0
    known = existing_keys(config)
    creates, updates = plan_sync(documents, observed_on, known)
    result = apply_sync(config, creates, updates, observed_on)
    print(json.dumps({"status": "ok", **result, "already_in_db": len(known)}, ensure_ascii=False))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("validate", "collect", "diff", "status", "notion"))
    parser.add_argument("--registry", type=Path, default=Path("config/sources.json"))
    parser.add_argument("--source", help="one source id, or 'all'; required for collect")
    parser.add_argument("--out", type=Path, default=Path("evidence"))
    parser.add_argument("--previous", type=Path, help="previous receipt directory; defaults to the run before --current")
    parser.add_argument("--current", type=Path, help="current receipt directory; required for diff, status and notion")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="notion: show what would be written without contacting Notion",
    )
    args = parser.parse_args()

    if args.command == "notion":
        if not args.current:
            parser.error("--current is required for notion")
        return run_notion(args.current, args.dry_run)

    if args.command in {"diff", "status"}:
        if not args.current:
            parser.error(f"--current is required for {args.command}")
        previous = args.previous or previous_run_dir(args.current)
        report = diff_directories(previous, args.current, utc_now()) if previous else None
        if args.command == "diff":
            if report is None:
                parser.error("no earlier run found; pass --previous explicitly")
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 0
        documents = load_directory(args.current)
        collected = {d["source"]["id"] for d in documents}
        registered, registry_errors = load_registry(args.registry)
        missing = [s.id for s in registered if s.id not in collected] if not registry_errors else []
        markdown = status_markdown(documents, today_kst(), report, missing)
        if args.out and args.out != Path("evidence"):
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(markdown + "\n", encoding="utf-8")
            print(json.dumps({"status": "ok", "written": str(args.out)}, ensure_ascii=False))
        else:
            print(markdown)
        return 0

    sources, errors = load_registry(args.registry)
    if args.command == "validate":
        return run_validate(sources, errors)
    if errors:
        print(json.dumps({"status": "invalid", "errors": errors}, ensure_ascii=False))
        return 2
    if not args.source:
        parser.error("--source is required for collect")
    return run_collect(sources, args.source, args.out)


if __name__ == "__main__":
    sys.exit(main())
