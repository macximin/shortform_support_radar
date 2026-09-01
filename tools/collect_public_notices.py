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

from shortform_support_radar.collection import HostRateLimiter, collect, utc_now  # noqa: E402
from shortform_support_radar.policy import PolicyViolation  # noqa: E402
from shortform_support_radar.receipts import diff_directories  # noqa: E402
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("validate", "collect", "diff"))
    parser.add_argument("--registry", type=Path, default=Path("config/sources.json"))
    parser.add_argument("--source", help="one source id, or 'all'; required for collect")
    parser.add_argument("--out", type=Path, default=Path("evidence"))
    parser.add_argument("--previous", type=Path, help="previous receipt directory; required for diff")
    parser.add_argument("--current", type=Path, help="current receipt directory; required for diff")
    args = parser.parse_args()

    if args.command == "diff":
        if not args.previous or not args.current:
            parser.error("--previous and --current are required for diff")
        print(json.dumps(diff_directories(args.previous, args.current, utc_now()), ensure_ascii=False, indent=2))
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
