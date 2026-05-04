from __future__ import annotations

import argparse
import traceback
from pathlib import Path

from .bundler import bundle_project
from .errors import PyfuseError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pyfuse", description="Bundle Python project into one file")
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build", help="Build a single-file bundle")
    build.add_argument("entry", type=Path, help="Entry Python file")
    build.add_argument("-o", "--output", type=Path, required=True, help="Output bundled .py file")
    build.add_argument(
        "--module-root",
        action="append",
        type=Path,
        default=[],
        help="Additional local source root; can be used multiple times",
    )
    build.add_argument(
        "--include",
        action="append",
        default=[],
        help="Legacy alias for --include-package; can be used multiple times",
    )
    build.add_argument(
        "--include-module",
        action="append",
        default=[],
        help="Additional exact local module to bundle from module roots; can be used multiple times",
    )
    build.add_argument(
        "--include-package",
        action="append",
        default=[],
        help="Additional local package tree to bundle from module roots; can be used multiple times",
    )
    build.add_argument(
        "--vendor-package",
        action="append",
        default=[],
        help="Experimental: package from current Python environment to vendor (pure Python package only)",
    )
    build.add_argument(
        "--vendor-module",
        action="append",
        default=[],
        help="Experimental: single-file module from current Python environment to vendor (pure Python .py only)",
    )
    build.add_argument("--report", type=Path, help="Write JSON build report")
    build.add_argument(
        "--code-format",
        choices=("source", "marshal"),
        default="source",
        help="Module payload format: source keeps embedded source text; marshal embeds compiled code bytes",
    )
    build.add_argument("--debug", action="store_true", help="Show traceback for failures")
    build.add_argument("--verbose", action="store_true", help="Show verbose build logs")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "build":
        try:
            logger = (lambda msg: print(f"[pyfuse] {msg}")) if args.verbose else None
            include_packages = [*args.include_package, *args.include]
            result = bundle_project(
                args.entry,
                args.output,
                report_path=args.report,
                module_roots=args.module_root,
                include_modules=args.include_module,
                include_packages=include_packages,
                vendor_packages=args.vendor_package,
                vendor_modules=args.vendor_module,
                code_format=args.code_format,
                logger=logger,
            )
        except PyfuseError as exc:
            print(f"pyfuse: error: {exc}")
            if args.debug:
                traceback.print_exc()
            return 2
        except Exception as exc:
            print(f"pyfuse: internal error: {exc}")
            if args.debug:
                traceback.print_exc()
            return 3

        print(f"bundled: {result.entry_path}")
        print(f"output:  {result.output_path}")
        print(f"root:    {result.root_dir}")
        print(f"modules: {len(result.graph.modules)}")
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
