from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
import tempfile
from pathlib import Path


def _fixture_paths(fixtures_dir: Path) -> list[Path]:
    result: list[Path] = []
    for cfg in sorted(fixtures_dir.glob("*/fixture.json")):
        loaded = json.loads(cfg.read_text(encoding="utf-8"))
        if bool(loaded.get("expect_bundle_success", False)):
            result.append(cfg)
    return result


def _run_one(fixture: Path, warmup: int, runs: int) -> dict[str, object]:
    cmd = [
        sys.executable,
        "scripts/benchmark.py",
        "--fixture",
        str(fixture),
        "--warmup",
        str(warmup),
        "--runs",
        str(runs),
        "--json",
    ]
    proc = subprocess.run(cmd, text=True, capture_output=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(
            f"benchmark failed for {fixture}\nstdout={proc.stdout}\nstderr={proc.stderr}"
        )
    return json.loads(proc.stdout.strip())


def _load_fixture_config(fixture: Path) -> dict[str, object]:
    return json.loads(fixture.read_text(encoding="utf-8"))


def _build_report_for_fixture(fixture: Path) -> dict[str, object]:
    cfg = _load_fixture_config(fixture)
    fixture_dir = fixture.parent
    project_dir = fixture_dir / "project"
    entry = project_dir / str(cfg["entry"])
    with tempfile.TemporaryDirectory() as td:
        report_path = Path(td) / "report.json"
        out_path = Path(td) / "bundle.py"
        cmd = [
            sys.executable,
            "-m",
            "pyfuse.cli",
            "build",
            str(entry),
            "-o",
            str(out_path),
            "--report",
            str(report_path),
        ]
        for module_root in cfg.get("module_roots", []):  # type: ignore[union-attr]
            cmd.extend(["--module-root", str(project_dir / str(module_root))])
        for include in cfg.get("includes", []):  # type: ignore[union-attr]
            cmd.extend(["--include", str(include)])
        for include in cfg.get("include_modules", []):  # type: ignore[union-attr]
            cmd.extend(["--include-module", str(include)])
        for include in cfg.get("include_packages", []):  # type: ignore[union-attr]
            cmd.extend(["--include-package", str(include)])
        proc = subprocess.run(cmd, text=True, capture_output=True, check=False)
        if proc.returncode != 0:
            raise RuntimeError(
                f"build report failed for {fixture}\nstdout={proc.stdout}\nstderr={proc.stderr}"
            )
        return json.loads(report_path.read_text(encoding="utf-8"))


def _print_table(results: list[dict[str, object]]) -> None:
    print("fixture,bundled_module_count,dependency_edges,direct_mean_ms,bundle_mean_ms,overhead_ratio")
    for row in results:
        print(
            f"{row['fixture']},{row['bundled_module_count']},{row['dependency_edges']},"
            f"{row['direct_mean_ms']},{row['bundle_mean_ms']},{row['overhead_ratio']}"
        )


def _write_csv(results: list[dict[str, object]], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "fixture",
        "bundled_module_count",
        "dependency_edges",
        "direct_mean_ms",
        "bundle_mean_ms",
        "overhead_ratio",
        "direct_p95_ms",
        "bundle_p95_ms",
    ]
    with output.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in results:
            writer.writerow({k: row[k] for k in fields})


def main() -> int:
    parser = argparse.ArgumentParser(description="Run benchmark.py for all successful fixtures")
    parser.add_argument(
        "--fixtures-dir",
        type=Path,
        default=Path("tests/fixtures"),
        help="Fixture directory (default: tests/fixtures)",
    )
    parser.add_argument("--warmup", type=int, default=2, help="Warmup run count")
    parser.add_argument("--runs", type=int, default=10, help="Benchmark run count")
    parser.add_argument("--csv", type=Path, help="Optional CSV output path")
    args = parser.parse_args()

    try:
        fixtures = _fixture_paths(args.fixtures_dir)
        results: list[dict[str, object]] = []
        for fixture in fixtures:
            bench = _run_one(fixture, warmup=args.warmup, runs=args.runs)
            report = _build_report_for_fixture(fixture)
            bench["bundled_module_count"] = report.get("bundled_module_count", 0)
            bench["dependency_edges"] = report.get("dependency_edges", 0)
            results.append(bench)
    except Exception as exc:
        print(f"benchmark-all failed: {exc}")
        return 2

    _print_table(results)
    if args.csv is not None:
        _write_csv(results, args.csv)
        print(f"wrote csv: {args.csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
