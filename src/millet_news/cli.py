from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

from .config import env_bool, load_all
from .logging_setup import configure_logging
from .pipeline import Pipeline
from .publisher import refresh_instagram_token, verify_instagram_credentials
from .samples import generate_samples


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="millet-news", description="Millet-only Instagram content automation")
    parser.add_argument("--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="Collect, generate, validate and optionally publish one post")
    run.add_argument("--mode", choices=["dry-run", "approval", "automatic"], default=os.getenv("RUN_MODE", "dry-run"))
    run.add_argument("--mock-generation", action="store_true", default=env_bool("MOCK_GENERATION"))
    run.add_argument("--mock-publish", action="store_true", default=env_bool("MOCK_PUBLISH"))
    approve = sub.add_parser("approve", help="Revalidate and publish a pending draft")
    approve.add_argument("draft_id")
    approve.add_argument("--mock-publish", action="store_true")
    sub.add_parser("samples", help="Generate three deterministic sample posts without publishing")
    ready = sub.add_parser("readiness", help="Run tests and a mocked end-to-end check")
    ready.add_argument("--skip-tests", action="store_true")
    sub.add_parser("refresh-token", help="Refresh a compatible long-lived Instagram token")
    sub.add_parser("verify-instagram", help="Validate the Instagram credentials without publishing")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    configure_logging(args.verbose)
    config = load_all()
    try:
        if args.command == "samples":
            result = generate_samples(config)
        elif args.command == "run":
            pipeline = Pipeline(config)
            result = pipeline.run(args.mode, args.mock_generation, args.mock_publish)
        elif args.command == "approve":
            pipeline = Pipeline(config)
            result = pipeline.approve(args.draft_id, args.mock_publish)
        elif args.command == "refresh-token":
            result = refresh_instagram_token()
        elif args.command == "verify-instagram":
            result = verify_instagram_credentials()
        elif args.command == "readiness":
            if not args.skip_tests:
                completed = subprocess.run([sys.executable, "-m", "pytest"], cwd=config["root"], check=False)
                if completed.returncode:
                    return completed.returncode
            result = Pipeline(config, config["root"] / "data/readiness.db").run("automatic", mock_generation=True, mock_publish=True)
            result["note"] = "Mock end-to-end passed. Review samples before setting AUTOMATION_APPROVED=true."
        else:
            raise AssertionError(args.command)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
