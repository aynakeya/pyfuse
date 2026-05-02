from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict, cast


@dataclass(frozen=True)
class RunStats:
    samples_ms: list[float]

    @property
    def mean_ms(self) -> float:
        return statistics.fmean(self.samples_ms)

    @property
    def p95_ms(self) -> float:
        if len(self.samples_ms) == 1:
            return self.samples_ms[0]
        return statistics.quantiles(self.samples_ms, n=100, method="inclusive")[94]


class OriginalConfig(TypedDict):
    cmd: list[str]


class FixtureConfig(TypedDict, total=False):
    entry: str
    original: OriginalConfig
    expect_bundle_success: bool
    module_roots: list[str]
    includes: list[str]
    include_modules: list[str]
    include_packages: list[str]


def _normalize_python_cmd(cmd: list[str]) -> list[str]:
    if not cmd:
        raise ValueError("empty command")
    if cmd[0] in {"python", "python3"}:
        return [sys.executable, *cmd[1:]]
    return cmd


def _run_once(cmd: list[str], cwd: Path, env: dict[str, str]) -> tuple[float, int, str, str]:
    start = time.perf_counter()
    proc = subprocess.run(
        cmd,
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    return elapsed_ms, proc.returncode, proc.stdout, proc.stderr


def _bench_command(
    cmd: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    warmup: int,
    runs: int,
) -> RunStats:
    for _ in range(warmup):
        _, code, out, err = _run_once(cmd, cwd, env)
        if code != 0:
            raise RuntimeError(f"warmup run failed: code={code}\nstdout={out}\nstderr={err}")

    samples: list[float] = []
    for _ in range(runs):
        elapsed_ms, code, out, err = _run_once(cmd, cwd, env)
        if code != 0:
            raise RuntimeError(f"benchmark run failed: code={code}\nstdout={out}\nstderr={err}")
        samples.append(elapsed_ms)
    return RunStats(samples_ms=samples)


def _load_fixture(fixture_json: Path) -> FixtureConfig:
    loaded = json.loads(fixture_json.read_text(encoding="utf-8"))
    return cast(FixtureConfig, loaded)


def _build_bundle_from_fixture(
    *,
    repo_root: Path,
    fixture_dir: Path,
    fixture: FixtureConfig,
    output_path: Path,
) -> None:
    project_dir = fixture_dir / "project"
    entry = project_dir / fixture["entry"]
    cmd = [sys.executable, "-m", "pyfuse.cli", "build", str(entry), "-o", str(output_path)]

    for module_root in fixture.get("module_roots", []):
        cmd.extend(["--module-root", str(project_dir / module_root)])
    for include in fixture.get("includes", []):
        cmd.extend(["--include", include])
    for include in fixture.get("include_modules", []):
        cmd.extend(["--include-module", include])
    for include in fixture.get("include_packages", []):
        cmd.extend(["--include-package", include])

    env = os.environ.copy()
    src_path = str(repo_root / "src")
    env["PYTHONPATH"] = src_path if not env.get("PYTHONPATH") else f"{src_path}:{env['PYTHONPATH']}"

    proc = subprocess.run(cmd, cwd=repo_root, env=env, text=True, capture_output=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(
            "bundle build failed\n"
            f"cmd={' '.join(cmd)}\n"
            f"stdout={proc.stdout}\n"
            f"stderr={proc.stderr}"
        )


def benchmark_fixture(fixture_json: Path, *, warmup: int, runs: int) -> None:
    repo_root = Path(__file__).resolve().parent.parent
    fixture_dir = fixture_json.resolve().parent
    fixture = _load_fixture(fixture_json.resolve())
    if not bool(fixture.get("expect_bundle_success", False)):
        raise RuntimeError("fixture is not expected to bundle successfully")

    project_dir = fixture_dir / "project"
    original_cmd = _normalize_python_cmd(fixture["original"]["cmd"])

    with tempfile.TemporaryDirectory() as td:
        bundle_path = Path(td) / "bench_bundle.py"
        _build_bundle_from_fixture(
            repo_root=repo_root,
            fixture_dir=fixture_dir,
            fixture=fixture,
            output_path=bundle_path,
        )

        run_env = os.environ.copy()
        direct_stats = _bench_command(
            original_cmd,
            cwd=project_dir,
            env=run_env,
            warmup=warmup,
            runs=runs,
        )
        bundled_stats = _bench_command(
            [sys.executable, str(bundle_path)],
            cwd=project_dir,
            env=run_env,
            warmup=warmup,
            runs=runs,
        )

    ratio = bundled_stats.mean_ms / direct_stats.mean_ms if direct_stats.mean_ms > 0 else float("inf")

    print(f"fixture: {fixture_json}")
    print(f"runs: {runs} (warmup: {warmup})")
    print(f"direct  mean={direct_stats.mean_ms:.3f} ms p95={direct_stats.p95_ms:.3f} ms")
    print(f"bundle  mean={bundled_stats.mean_ms:.3f} ms p95={bundled_stats.p95_ms:.3f} ms")
    print(f"overhead ratio (bundle/direct): {ratio:.3f}x")


def benchmark_fixture_stats(fixture_json: Path, *, warmup: int, runs: int) -> dict[str, object]:
    repo_root = Path(__file__).resolve().parent.parent
    fixture_dir = fixture_json.resolve().parent
    fixture = _load_fixture(fixture_json.resolve())
    if not bool(fixture.get("expect_bundle_success", False)):
        raise RuntimeError("fixture is not expected to bundle successfully")

    project_dir = fixture_dir / "project"
    original_cmd = _normalize_python_cmd(fixture["original"]["cmd"])

    with tempfile.TemporaryDirectory() as td:
        bundle_path = Path(td) / "bench_bundle.py"
        _build_bundle_from_fixture(
            repo_root=repo_root,
            fixture_dir=fixture_dir,
            fixture=fixture,
            output_path=bundle_path,
        )

        run_env = os.environ.copy()
        direct_stats = _bench_command(
            original_cmd,
            cwd=project_dir,
            env=run_env,
            warmup=warmup,
            runs=runs,
        )
        bundled_stats = _bench_command(
            [sys.executable, str(bundle_path)],
            cwd=project_dir,
            env=run_env,
            warmup=warmup,
            runs=runs,
        )

    ratio = bundled_stats.mean_ms / direct_stats.mean_ms if direct_stats.mean_ms > 0 else float("inf")
    return {
        "fixture": str(fixture_json),
        "runs": runs,
        "warmup": warmup,
        "direct_mean_ms": round(direct_stats.mean_ms, 3),
        "direct_p95_ms": round(direct_stats.p95_ms, 3),
        "bundle_mean_ms": round(bundled_stats.mean_ms, 3),
        "bundle_p95_ms": round(bundled_stats.p95_ms, 3),
        "overhead_ratio": round(ratio, 3),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark pyfuse bundled script vs direct run")
    parser.add_argument(
        "--fixture",
        type=Path,
        required=True,
        help="Path to fixture.json, e.g. tests/fixtures/01_simple_two_file/fixture.json",
    )
    parser.add_argument("--warmup", type=int, default=3, help="Warmup run count for each command")
    parser.add_argument("--runs", type=int, default=20, help="Benchmark run count for each command")
    parser.add_argument("--json", action="store_true", help="Print benchmark result as JSON")
    args = parser.parse_args()

    try:
        if args.json:
            stats = benchmark_fixture_stats(args.fixture, warmup=args.warmup, runs=args.runs)
            print(json.dumps(stats, sort_keys=True))
        else:
            benchmark_fixture(args.fixture, warmup=args.warmup, runs=args.runs)
    except Exception as exc:
        print(f"benchmark failed: {exc}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
