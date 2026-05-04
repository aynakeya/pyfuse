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

        original_env = env.copy()
        for pythonpath in cfg.get("original_pythonpath", []):
            path = str(project_dir / pythonpath)
            original_env["PYTHONPATH"] = (
                path if not original_env.get("PYTHONPATH") else f"{path}:{original_env['PYTHONPATH']}"
            )

        bundler_env = env.copy()
        for pythonpath in cfg.get("bundler_pythonpath", cfg.get("original_pythonpath", [])):
            path = str(project_dir / pythonpath)
            bundler_env["PYTHONPATH"] = (
                path if not bundler_env.get("PYTHONPATH") else f"{path}:{bundler_env['PYTHONPATH']}"
            )

        original_cmd = cfg["original"]["cmd"]
        original = subprocess.run(
            original_cmd,
            cwd=project_dir,
            env=original_env,
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
        for module_root in cfg.get("module_roots", []):
            bundle_cmd.extend(["--module-root", str(project_dir / module_root)])
        for include in cfg.get("includes", []):
            bundle_cmd.extend(["--include", include])
        for include in cfg.get("include_modules", []):
            bundle_cmd.extend(["--include-module", include])
        for include in cfg.get("include_packages", []):
            bundle_cmd.extend(["--include-package", include])
        for vendor in cfg.get("vendor_packages", []):
            bundle_cmd.extend(["--vendor-package", vendor])
        built = subprocess.run(bundle_cmd, cwd=repo_root, env=bundler_env, text=True, capture_output=True, check=False)

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
            # fmt: off
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
            # fmt: on

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
            self.assertIn("module_roots", report)
            self.assertIn("module_origins", report)
            self.assertIn("included_modules_exact", report)
            self.assertIn("included_packages_tree", report)
            self.assertIn("uncertain_imports", report)
            self.assertIn("risk_level", report)

    def test_build_report_tracks_module_origins_for_module_root(self) -> None:
        repo_root = Path(__file__).resolve().parent.parent
        env = os.environ.copy()
        src_path = str(repo_root / "src")
        env["PYTHONPATH"] = src_path if not env.get("PYTHONPATH") else f"{src_path}:{env['PYTHONPATH']}"

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            scripts = root / "scripts"
            local_src = root / "src"
            package = local_src / "package_a"
            scripts.mkdir(parents=True)
            package.mkdir(parents=True)
            (scripts / "main.py").write_text("from package_a import value\nprint(value())\n", encoding="utf-8")
            (package / "__init__.py").write_text("from .core import value\n", encoding="utf-8")
            (package / "core.py").write_text("def value():\n    return 'origin-ok'\n", encoding="utf-8")
            report_path = root / "report.json"

            bundle_cmd = [
                "python",
                "-m",
                "pyfuse.cli",
                "build",
                str(scripts / "main.py"),
                "-o",
                str(root / "compiled.py"),
                "--module-root",
                str(local_src),
                "--report",
                str(report_path),
            ]
            built = subprocess.run(bundle_cmd, cwd=repo_root, env=env, text=True, capture_output=True, check=False)
            self.assertEqual(built.returncode, 0, msg=f"bundle failed:\n{built.stdout}\n{built.stderr}")

            report = json.loads(report_path.read_text(encoding="utf-8"))
            origins = report["module_origins"]
            self.assertIn("package_a", origins)
            self.assertEqual(origins["package_a"], str(local_src.resolve()))

    def test_include_module_report_does_not_bundle_entire_package_tree(self) -> None:
        repo_root = Path(__file__).resolve().parent.parent
        env = os.environ.copy()
        src_path = str(repo_root / "src")
        env["PYTHONPATH"] = src_path if not env.get("PYTHONPATH") else f"{src_path}:{env['PYTHONPATH']}"

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            scripts = root / "scripts"
            local_src = root / "src"
            package = local_src / "package_a"
            scripts.mkdir(parents=True)
            package.mkdir(parents=True)
            (scripts / "main.py").write_text(
                "import importlib\nPLUGIN = 'package_a.plugin'\nprint(importlib.import_module(PLUGIN).run())\n",
                encoding="utf-8",
            )
            (package / "__init__.py").write_text("", encoding="utf-8")
            (package / "plugin.py").write_text("def run():\n    return 'exact-report'\n", encoding="utf-8")
            (package / "unused.py").write_text("VALUE = 'unused'\n", encoding="utf-8")
            report_path = root / "report.json"

            built = subprocess.run(
                [
                    "python",
                    "-m",
                    "pyfuse.cli",
                    "build",
                    str(scripts / "main.py"),
                    "-o",
                    str(root / "compiled.py"),
                    "--module-root",
                    str(local_src),
                    "--include-module",
                    "package_a.plugin",
                    "--report",
                    str(report_path),
                ],
                cwd=repo_root,
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(built.returncode, 0, msg=f"bundle failed:\n{built.stdout}\n{built.stderr}")

            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertIn("package_a.plugin", report["bundled_modules"])
            self.assertNotIn("package_a.unused", report["bundled_modules"])
            self.assertEqual(report["included_modules_exact"], ["package_a.plugin"])
            self.assertEqual(report["risk_level"], "low")

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

    def test_module_root_bundles_local_package_outside_entry_dir(self) -> None:
        repo_root = Path(__file__).resolve().parent.parent
        env = os.environ.copy()
        src_path = str(repo_root / "src")
        env["PYTHONPATH"] = src_path if not env.get("PYTHONPATH") else f"{src_path}:{env['PYTHONPATH']}"

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            scripts = root / "scripts" / "s1"
            package = root / "src" / "package_a"
            scripts.mkdir(parents=True)
            package.mkdir(parents=True)
            (scripts / "main.py").write_text(
                "from package_a import value\nprint(value())\n",
                encoding="utf-8",
            )
            (package / "__init__.py").write_text(
                "from .core import value\n",
                encoding="utf-8",
            )
            (package / "core.py").write_text(
                "def value():\n    return 'module-root-ok'\n",
                encoding="utf-8",
            )

            bundled_path = root / "dist" / "s1.py"
            built = subprocess.run(
                [
                    "python",
                    "-m",
                    "pyfuse.cli",
                    "build",
                    str(scripts / "main.py"),
                    "-o",
                    str(bundled_path),
                    "--module-root",
                    str(root / "src"),
                ],
                cwd=repo_root,
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )
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
            self.assertEqual(ran.stdout, "module-root-ok\n")

    def test_include_bundles_dynamic_local_package_tree(self) -> None:
        repo_root = Path(__file__).resolve().parent.parent
        env = os.environ.copy()
        src_path = str(repo_root / "src")
        env["PYTHONPATH"] = src_path if not env.get("PYTHONPATH") else f"{src_path}:{env['PYTHONPATH']}"

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            scripts = root / "scripts" / "s1"
            package = root / "src" / "package_a"
            scripts.mkdir(parents=True)
            package.mkdir(parents=True)
            (scripts / "main.py").write_text(
                "import importlib\n"
                "PLUGIN = 'package_a.plugin'\n"
                "mod = importlib.import_module(PLUGIN)\n"
                "print(mod.run())\n",
                encoding="utf-8",
            )
            (package / "__init__.py").write_text("", encoding="utf-8")
            # fmt: off
            (package / "plugin.py").write_text(
                "from .helper import msg\n"
                "def run():\n"
                "    return msg()\n",
                encoding="utf-8",
            )
            # fmt: on
            (package / "helper.py").write_text(
                "def msg():\n    return 'include-ok'\n",
                encoding="utf-8",
            )

            bundled_path = root / "dist" / "s1.py"
            built = subprocess.run(
                [
                    "python",
                    "-m",
                    "pyfuse.cli",
                    "build",
                    str(scripts / "main.py"),
                    "-o",
                    str(bundled_path),
                    "--module-root",
                    str(root / "src"),
                    "--include-package",
                    "package_a",
                ],
                cwd=repo_root,
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )
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
            self.assertEqual(ran.stdout, "include-ok\n")

    def test_include_nested_package_runs_outside_project_directory(self) -> None:
        repo_root = Path(__file__).resolve().parent.parent
        env = os.environ.copy()
        src_path = str(repo_root / "src")
        env["PYTHONPATH"] = src_path if not env.get("PYTHONPATH") else f"{src_path}:{env['PYTHONPATH']}"

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            project = root / "project"
            pkg = project / "pkg"
            subpkg = pkg / "subpkg"
            outside = root / "outside"
            subpkg.mkdir(parents=True)
            outside.mkdir()
            (pkg / "__init__.py").write_text("", encoding="utf-8")
            (subpkg / "__init__.py").write_text("", encoding="utf-8")
            (subpkg / "plugin.py").write_text("VALUE = 'nested-include-ok'\n", encoding="utf-8")
            (project / "main.py").write_text(
                "import importlib\n"
                "name = '.'.join(['pkg', 'subpkg', 'plugin'])\n"
                "print(importlib.import_module(name).VALUE)\n",
                encoding="utf-8",
            )

            bundled_path = root / "dist" / "app.py"
            built = subprocess.run(
                [
                    "python",
                    "-m",
                    "pyfuse.cli",
                    "build",
                    str(project / "main.py"),
                    "-o",
                    str(bundled_path),
                    "--include-package",
                    "pkg.subpkg",
                ],
                cwd=repo_root,
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(built.returncode, 0, msg=f"bundle failed:\n{built.stdout}\n{built.stderr}")

            ran = subprocess.run(
                ["python", str(bundled_path)],
                cwd=outside,
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(ran.returncode, 0, msg=f"run failed:\n{ran.stdout}\n{ran.stderr}")
            self.assertEqual(ran.stdout, "nested-include-ok\n")

    def test_module_root_ambiguous_module_fails(self) -> None:
        repo_root = Path(__file__).resolve().parent.parent
        env = os.environ.copy()
        src_path = str(repo_root / "src")
        env["PYTHONPATH"] = src_path if not env.get("PYTHONPATH") else f"{src_path}:{env['PYTHONPATH']}"

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            scripts = root / "scripts"
            left = root / "left" / "dup"
            right = root / "right" / "dup"
            scripts.mkdir()
            left.mkdir(parents=True)
            right.mkdir(parents=True)
            (scripts / "main.py").write_text("import dup\nprint(dup.VALUE)\n", encoding="utf-8")
            (left / "__init__.py").write_text("VALUE = 'left'\n", encoding="utf-8")
            (right / "__init__.py").write_text("VALUE = 'right'\n", encoding="utf-8")

            built = subprocess.run(
                [
                    "python",
                    "-m",
                    "pyfuse.cli",
                    "build",
                    str(scripts / "main.py"),
                    "-o",
                    str(root / "out.py"),
                    "--module-root",
                    str(root / "left"),
                    "--module-root",
                    str(root / "right"),
                ],
                cwd=repo_root,
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertNotEqual(built.returncode, 0)
            self.assertIn("ambiguous local module", built.stdout + built.stderr)

    def test_vendor_package_bundles_installed_package_tree(self) -> None:
        repo_root = Path(__file__).resolve().parent.parent
        env = os.environ.copy()
        src_path = str(repo_root / "src")
        env["PYTHONPATH"] = src_path if not env.get("PYTHONPATH") else f"{src_path}:{env['PYTHONPATH']}"

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            site_dir = root / "fake_site"
            vendor_pkg = site_dir / "third_pkg"
            vendor_pkg.mkdir(parents=True)
            (vendor_pkg / "__init__.py").write_text("from .core import value\n", encoding="utf-8")
            (vendor_pkg / "core.py").write_text("def value():\n    return 'vendor-ok'\n", encoding="utf-8")

            script_dir = root / "project"
            script_dir.mkdir()
            (script_dir / "main.py").write_text("from third_pkg import value\nprint(value())\n", encoding="utf-8")

            bundler_env = env.copy()
            bundler_env["PYTHONPATH"] = (
                f"{site_dir}:{bundler_env['PYTHONPATH']}" if bundler_env.get("PYTHONPATH") else str(site_dir)
            )
            bundled_path = root / "bundled.py"
            built = subprocess.run(
                [
                    "python",
                    "-m",
                    "pyfuse.cli",
                    "build",
                    str(script_dir / "main.py"),
                    "-o",
                    str(bundled_path),
                    "--vendor-package",
                    "third_pkg",
                ],
                cwd=repo_root,
                env=bundler_env,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(built.returncode, 0, msg=f"bundle failed:\n{built.stdout}\n{built.stderr}")

            run_env = env.copy()
            # Ensure runtime does not rely on third_pkg being importable from outside.
            run_env.pop("PYTHONPATH", None)
            ran = subprocess.run(
                ["python", str(bundled_path)],
                cwd=script_dir,
                env=run_env,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(ran.returncode, 0, msg=f"run failed:\n{ran.stdout}\n{ran.stderr}")
            self.assertEqual(ran.stdout, "vendor-ok\n")

    def test_vendor_package_report_contains_vendor_metadata(self) -> None:
        repo_root = Path(__file__).resolve().parent.parent
        env = os.environ.copy()
        src_path = str(repo_root / "src")
        env["PYTHONPATH"] = src_path if not env.get("PYTHONPATH") else f"{src_path}:{env['PYTHONPATH']}"

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            site_dir = root / "fake_site"
            vendor_pkg = site_dir / "third_pkg"
            vendor_pkg.mkdir(parents=True)
            (vendor_pkg / "__init__.py").write_text("from .core import value\n", encoding="utf-8")
            (vendor_pkg / "core.py").write_text("def value():\n    return 'vendor-ok'\n", encoding="utf-8")
            script_dir = root / "project"
            script_dir.mkdir()
            (script_dir / "main.py").write_text("from third_pkg import value\nprint(value())\n", encoding="utf-8")
            report_path = root / "report.json"

            bundler_env = env.copy()
            bundler_env["PYTHONPATH"] = (
                f"{site_dir}:{bundler_env['PYTHONPATH']}" if bundler_env.get("PYTHONPATH") else str(site_dir)
            )
            built = subprocess.run(
                [
                    "python",
                    "-m",
                    "pyfuse.cli",
                    "build",
                    str(script_dir / "main.py"),
                    "-o",
                    str(root / "bundled.py"),
                    "--vendor-package",
                    "third_pkg",
                    "--report",
                    str(report_path),
                ],
                cwd=repo_root,
                env=bundler_env,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(built.returncode, 0, msg=f"bundle failed:\n{built.stdout}\n{built.stderr}")
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["vendor_packages"], ["third_pkg"])
            self.assertEqual(report["included_packages_tree"], [])
            self.assertEqual(report["risk_level"], "medium")

    def test_vendor_package_rejects_plain_module(self) -> None:
        repo_root = Path(__file__).resolve().parent.parent
        env = os.environ.copy()
        src_path = str(repo_root / "src")
        env["PYTHONPATH"] = src_path if not env.get("PYTHONPATH") else f"{src_path}:{env['PYTHONPATH']}"

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            site_dir = root / "fake_site"
            site_dir.mkdir(parents=True)
            (site_dir / "modonly.py").write_text("VALUE = 1\n", encoding="utf-8")
            script_dir = root / "project"
            script_dir.mkdir()
            (script_dir / "main.py").write_text("print('x')\n", encoding="utf-8")

            bundler_env = env.copy()
            bundler_env["PYTHONPATH"] = (
                f"{site_dir}:{bundler_env['PYTHONPATH']}" if bundler_env.get("PYTHONPATH") else str(site_dir)
            )
            built = subprocess.run(
                [
                    "python",
                    "-m",
                    "pyfuse.cli",
                    "build",
                    str(script_dir / "main.py"),
                    "-o",
                    str(root / "bundled.py"),
                    "--vendor-package",
                    "modonly",
                ],
                cwd=repo_root,
                env=bundler_env,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertNotEqual(built.returncode, 0)
            self.assertIn("is not a package", built.stdout + built.stderr)

    def test_vendor_package_rejects_missing_package(self) -> None:
        repo_root = Path(__file__).resolve().parent.parent
        env = os.environ.copy()
        src_path = str(repo_root / "src")
        env["PYTHONPATH"] = src_path if not env.get("PYTHONPATH") else f"{src_path}:{env['PYTHONPATH']}"

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            script_dir = root / "project"
            script_dir.mkdir()
            (script_dir / "main.py").write_text("print('x')\n", encoding="utf-8")

            built = subprocess.run(
                [
                    "python",
                    "-m",
                    "pyfuse.cli",
                    "build",
                    str(script_dir / "main.py"),
                    "-o",
                    str(root / "bundled.py"),
                    "--vendor-package",
                    "pkg_that_does_not_exist_for_pyfuse_test",
                ],
                cwd=repo_root,
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertNotEqual(built.returncode, 0)
            self.assertIn("was not found", built.stdout + built.stderr)

    def test_vendor_package_rejects_namespace_package(self) -> None:
        repo_root = Path(__file__).resolve().parent.parent
        env = os.environ.copy()
        src_path = str(repo_root / "src")
        env["PYTHONPATH"] = src_path if not env.get("PYTHONPATH") else f"{src_path}:{env['PYTHONPATH']}"

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            site_dir = root / "fake_site"
            (site_dir / "ns_pkg").mkdir(parents=True)
            # No __init__.py => namespace package.
            (site_dir / "ns_pkg" / "mod.py").write_text("VALUE = 1\n", encoding="utf-8")

            script_dir = root / "project"
            script_dir.mkdir()
            (script_dir / "main.py").write_text("print('x')\n", encoding="utf-8")

            bundler_env = env.copy()
            bundler_env["PYTHONPATH"] = (
                f"{site_dir}:{bundler_env['PYTHONPATH']}" if bundler_env.get("PYTHONPATH") else str(site_dir)
            )
            built = subprocess.run(
                [
                    "python",
                    "-m",
                    "pyfuse.cli",
                    "build",
                    str(script_dir / "main.py"),
                    "-o",
                    str(root / "bundled.py"),
                    "--vendor-package",
                    "ns_pkg",
                ],
                cwd=repo_root,
                env=bundler_env,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertNotEqual(built.returncode, 0)
            self.assertIn("namespace vendor package", built.stdout + built.stderr)

    def test_vendor_module_bundles_installed_single_file_module(self) -> None:
        repo_root = Path(__file__).resolve().parent.parent
        env = os.environ.copy()
        src_path = str(repo_root / "src")
        env["PYTHONPATH"] = src_path if not env.get("PYTHONPATH") else f"{src_path}:{env['PYTHONPATH']}"

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            site_dir = root / "fake_site"
            site_dir.mkdir(parents=True)
            (site_dir / "third_mod.py").write_text("def value():\n    return 'vendor-mod-ok'\n", encoding="utf-8")

            script_dir = root / "project"
            script_dir.mkdir()
            (script_dir / "main.py").write_text("import third_mod\nprint(third_mod.value())\n", encoding="utf-8")

            bundler_env = env.copy()
            bundler_env["PYTHONPATH"] = (
                f"{site_dir}:{bundler_env['PYTHONPATH']}" if bundler_env.get("PYTHONPATH") else str(site_dir)
            )
            bundled_path = root / "bundled.py"
            built = subprocess.run(
                [
                    "python",
                    "-m",
                    "pyfuse.cli",
                    "build",
                    str(script_dir / "main.py"),
                    "-o",
                    str(bundled_path),
                    "--vendor-module",
                    "third_mod",
                ],
                cwd=repo_root,
                env=bundler_env,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(built.returncode, 0, msg=f"bundle failed:\n{built.stdout}\n{built.stderr}")

            run_env = env.copy()
            run_env.pop("PYTHONPATH", None)
            ran = subprocess.run(
                ["python", str(bundled_path)],
                cwd=script_dir,
                env=run_env,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(ran.returncode, 0, msg=f"run failed:\n{ran.stdout}\n{ran.stderr}")
            self.assertEqual(ran.stdout, "vendor-mod-ok\n")

    def test_vendor_module_report_contains_vendor_modules(self) -> None:
        repo_root = Path(__file__).resolve().parent.parent
        env = os.environ.copy()
        src_path = str(repo_root / "src")
        env["PYTHONPATH"] = src_path if not env.get("PYTHONPATH") else f"{src_path}:{env['PYTHONPATH']}"

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            site_dir = root / "fake_site"
            site_dir.mkdir(parents=True)
            (site_dir / "third_mod.py").write_text("def value():\n    return 'vendor-mod-ok'\n", encoding="utf-8")

            script_dir = root / "project"
            script_dir.mkdir()
            (script_dir / "main.py").write_text("import third_mod\nprint(third_mod.value())\n", encoding="utf-8")
            report_path = root / "report.json"

            bundler_env = env.copy()
            bundler_env["PYTHONPATH"] = (
                f"{site_dir}:{bundler_env['PYTHONPATH']}" if bundler_env.get("PYTHONPATH") else str(site_dir)
            )
            built = subprocess.run(
                [
                    "python",
                    "-m",
                    "pyfuse.cli",
                    "build",
                    str(script_dir / "main.py"),
                    "-o",
                    str(root / "bundled.py"),
                    "--vendor-module",
                    "third_mod",
                    "--report",
                    str(report_path),
                ],
                cwd=repo_root,
                env=bundler_env,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(built.returncode, 0, msg=f"bundle failed:\n{built.stdout}\n{built.stderr}")
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["vendor_modules"], ["third_mod"])
            self.assertEqual(report["risk_level"], "medium")

    def test_vendor_module_rejects_package_target(self) -> None:
        repo_root = Path(__file__).resolve().parent.parent
        env = os.environ.copy()
        src_path = str(repo_root / "src")
        env["PYTHONPATH"] = src_path if not env.get("PYTHONPATH") else f"{src_path}:{env['PYTHONPATH']}"

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            site_dir = root / "fake_site"
            pkg = site_dir / "pkg_as_mod"
            pkg.mkdir(parents=True)
            (pkg / "__init__.py").write_text("", encoding="utf-8")
            script_dir = root / "project"
            script_dir.mkdir()
            (script_dir / "main.py").write_text("print('x')\n", encoding="utf-8")

            bundler_env = env.copy()
            bundler_env["PYTHONPATH"] = (
                f"{site_dir}:{bundler_env['PYTHONPATH']}" if bundler_env.get("PYTHONPATH") else str(site_dir)
            )
            built = subprocess.run(
                [
                    "python",
                    "-m",
                    "pyfuse.cli",
                    "build",
                    str(script_dir / "main.py"),
                    "-o",
                    str(root / "bundled.py"),
                    "--vendor-module",
                    "pkg_as_mod",
                ],
                cwd=repo_root,
                env=bundler_env,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertNotEqual(built.returncode, 0)
            self.assertIn("is a package; use --vendor-package", built.stdout + built.stderr)

    def test_vendor_module_rejects_missing_module(self) -> None:
        repo_root = Path(__file__).resolve().parent.parent
        env = os.environ.copy()
        src_path = str(repo_root / "src")
        env["PYTHONPATH"] = src_path if not env.get("PYTHONPATH") else f"{src_path}:{env['PYTHONPATH']}"

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            script_dir = root / "project"
            script_dir.mkdir()
            (script_dir / "main.py").write_text("print('x')\n", encoding="utf-8")

            built = subprocess.run(
                [
                    "python",
                    "-m",
                    "pyfuse.cli",
                    "build",
                    str(script_dir / "main.py"),
                    "-o",
                    str(root / "bundled.py"),
                    "--vendor-module",
                    "mod_that_does_not_exist_for_pyfuse_test",
                ],
                cwd=repo_root,
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertNotEqual(built.returncode, 0)
            self.assertIn("vendor module", built.stdout + built.stderr)
            self.assertIn("was not found", built.stdout + built.stderr)

    def test_vendor_module_rejects_non_python_extension_module(self) -> None:
        repo_root = Path(__file__).resolve().parent.parent
        env = os.environ.copy()
        src_path = str(repo_root / "src")
        env["PYTHONPATH"] = src_path if not env.get("PYTHONPATH") else f"{src_path}:{env['PYTHONPATH']}"

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            script_dir = root / "project"
            script_dir.mkdir()
            (script_dir / "main.py").write_text("print('x')\n", encoding="utf-8")

            built = subprocess.run(
                [
                    "python",
                    "-m",
                    "pyfuse.cli",
                    "build",
                    str(script_dir / "main.py"),
                    "-o",
                    str(root / "bundled.py"),
                    "--vendor-module",
                    "math",
                ],
                cwd=repo_root,
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertNotEqual(built.returncode, 0)
            self.assertIn("not a pure Python .py module", built.stdout + built.stderr)


if __name__ == "__main__":
    unittest.main()
