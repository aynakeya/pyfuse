from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


class IntegrationTests(unittest.TestCase):
    def test_all_fixtures(self) -> None:
        fixtures_dir = Path(__file__).parent / "fixtures"
        for cfg_path in sorted(fixtures_dir.glob("*/fixture.json")):
            with self.subTest(fixture=cfg_path.parent.name):
                self._run_fixture(cfg_path)

    def _run_fixture(self, cfg_path: Path) -> None:
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        project_dir = cfg_path.parent / "project"
        repo_root = Path(__file__).resolve().parent.parent

        env = os.environ.copy()
        src_path = str(repo_root / "src")
        env["PYTHONPATH"] = src_path if not env.get("PYTHONPATH") else f"{src_path}:{env['PYTHONPATH']}"

        original_cmd = cfg["original"]["cmd"]
        original = subprocess.run(
            original_cmd,
            cwd=project_dir,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )

        bundle_out = Path(tempfile.gettempdir()) / f"pyfuse-{cfg_path.parent.name}.py"
        bundle_cmd = [
            "python",
            "-m",
            "pyfuse.cli",
            "build",
            str(project_dir / cfg["entry"]),
            "-o",
            str(bundle_out),
        ]
        built = subprocess.run(bundle_cmd, cwd=repo_root, env=env, text=True, capture_output=True, check=False)

        if cfg["expect_bundle_success"]:
            self.assertEqual(
                built.returncode,
                0,
                msg=f"bundle failed for {cfg_path.parent.name}:\nstdout={built.stdout}\nstderr={built.stderr}",
            )

            bundled = subprocess.run(
                ["python", str(bundle_out)],
                cwd=project_dir,
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(
                bundled.returncode,
                original.returncode,
                msg=(
                    f"return code mismatch for {cfg_path.parent.name}:\n"
                    f"original={original.returncode} bundled={bundled.returncode}\n"
                    f"orig_stdout={original.stdout}\norig_stderr={original.stderr}\n"
                    f"bundled_stdout={bundled.stdout}\nbundled_stderr={bundled.stderr}"
                ),
            )
            self.assertEqual(bundled.stdout, original.stdout)
            self.assertEqual(bundled.stderr, original.stderr)
        else:
            self.assertNotEqual(
                built.returncode,
                0,
                msg=f"bundle unexpectedly succeeded for {cfg_path.parent.name}",
            )
            expected_error = cfg.get("expected_error_contains")
            if expected_error:
                combined = built.stdout + built.stderr
                self.assertIn(expected_error, combined)

    def test_bundled_file_can_be_imported_for_entry_exports(self) -> None:
        repo_root = Path(__file__).resolve().parent.parent
        env = os.environ.copy()
        src_path = str(repo_root / "src")
        env["PYTHONPATH"] = src_path if not env.get("PYTHONPATH") else f"{src_path}:{env['PYTHONPATH']}"

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "a.py").write_text(
                "def aa() -> str:\n"
                "    return 'AA_OK'\n",
                encoding="utf-8",
            )
            (root / "consumer.py").write_text(
                "from compiled_a import aa\n"
                "print(aa())\n",
                encoding="utf-8",
            )

            bundle_cmd = [
                "python",
                "-m",
                "pyfuse.cli",
                "build",
                str(root / "a.py"),
                "-o",
                str(root / "compiled_a.py"),
            ]
            built = subprocess.run(bundle_cmd, cwd=repo_root, env=env, text=True, capture_output=True, check=False)
            self.assertEqual(
                built.returncode,
                0,
                msg=f"bundle failed:\nstdout={built.stdout}\nstderr={built.stderr}",
            )

            imported = subprocess.run(
                ["python", "consumer.py"],
                cwd=root,
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(
                imported.returncode,
                0,
                msg=f"consumer failed:\nstdout={imported.stdout}\nstderr={imported.stderr}",
            )
            self.assertEqual(imported.stdout, "AA_OK\n")

    def test_build_verbose_outputs_debug_logs(self) -> None:
        repo_root = Path(__file__).resolve().parent.parent
        env = os.environ.copy()
        src_path = str(repo_root / "src")
        env["PYTHONPATH"] = src_path if not env.get("PYTHONPATH") else f"{src_path}:{env['PYTHONPATH']}"

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "main.py").write_text("print('v')\n", encoding="utf-8")
            bundle_cmd = [
                "python",
                "-m",
                "pyfuse.cli",
                "build",
                str(root / "main.py"),
                "-o",
                str(root / "compiled.py"),
                "--verbose",
            ]
            built = subprocess.run(bundle_cmd, cwd=repo_root, env=env, text=True, capture_output=True, check=False)
            self.assertEqual(built.returncode, 0, msg=f"bundle failed:\n{built.stdout}\n{built.stderr}")
            self.assertIn("[pyfuse] entry file:", built.stdout)

    def test_build_report_outputs_json_summary(self) -> None:
        repo_root = Path(__file__).resolve().parent.parent
        env = os.environ.copy()
        src_path = str(repo_root / "src")
        env["PYTHONPATH"] = src_path if not env.get("PYTHONPATH") else f"{src_path}:{env['PYTHONPATH']}"

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "main.py").write_text("import helper\nprint(helper.v)\n", encoding="utf-8")
            (root / "helper.py").write_text("v = 1\n", encoding="utf-8")
            report_path = root / "report.json"

            bundle_cmd = [
                "python",
                "-m",
                "pyfuse.cli",
                "build",
                str(root / "main.py"),
                "-o",
                str(root / "compiled.py"),
                "--report",
                str(report_path),
            ]
            built = subprocess.run(bundle_cmd, cwd=repo_root, env=env, text=True, capture_output=True, check=False)
            self.assertEqual(built.returncode, 0, msg=f"bundle failed:\n{built.stdout}\n{built.stderr}")
            self.assertTrue(report_path.exists())

            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertIn("bundled_modules", report)
            self.assertIn("skipped_imports", report)
            self.assertIn("dependency_edges", report)
            self.assertIn("main", report["bundled_modules"])
            self.assertIn("helper", report["bundled_modules"])

    def test_bundled_file_runs_outside_project_directory(self) -> None:
        repo_root = Path(__file__).resolve().parent.parent
        env = os.environ.copy()
        src_path = str(repo_root / "src")
        env["PYTHONPATH"] = src_path if not env.get("PYTHONPATH") else f"{src_path}:{env['PYTHONPATH']}"

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            project = root / "project"
            project.mkdir()
            (project / "main.py").write_text("import helper\nprint(helper.value())\n", encoding="utf-8")
            (project / "helper.py").write_text("def value():\n    return 'outside-ok'\n", encoding="utf-8")
            bundled_path = root / "compiled.py"

            bundle_cmd = [
                "python",
                "-m",
                "pyfuse.cli",
                "build",
                str(project / "main.py"),
                "-o",
                str(bundled_path),
            ]
            built = subprocess.run(bundle_cmd, cwd=repo_root, env=env, text=True, capture_output=True, check=False)
            self.assertEqual(built.returncode, 0, msg=f"bundle failed:\n{built.stdout}\n{built.stderr}")

            outside = root / "outside"
            outside.mkdir()
            ran = subprocess.run(
                ["python", str(bundled_path)],
                cwd=outside,
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(ran.returncode, 0, msg=f"run failed:\n{ran.stdout}\n{ran.stderr}")
            self.assertEqual(ran.stdout, "outside-ok\n")


if __name__ == "__main__":
    unittest.main()
