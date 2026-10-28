#!/usr/bin/env python3
"""Tests for env_example_sync. Standard library only; run with:

    python3 tests/test_env_example_sync.py
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from env_example_sync import check, parse_example, scan_text  # noqa: E402


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


class TestParseExample(unittest.TestCase):
    def test_comments_export_and_values_with_equals(self):
        text = (
            "# comment\n"
            "\n"
            "export API_KEY=abc\n"
            "DATABASE_URL=postgres://host/db?x=1\n"
            "EMPTY=\n"
            "not a pair\n"
        )
        self.assertEqual(
            parse_example(text), {"API_KEY", "DATABASE_URL", "EMPTY"})

    def test_empty_example(self):
        self.assertEqual(parse_example(""), set())


class TestScanText(unittest.TestCase):
    def test_python_patterns(self):
        text = (
            "a = os.environ['API_KEY']\n"
            'b = os.environ.get("DATABASE_URL")\n'
            "c = os.getenv('TIMEOUT')\n"
        )
        self.assertEqual(
            scan_text(text), {"API_KEY", "DATABASE_URL", "TIMEOUT"})

    def test_js_ts_patterns(self):
        text = (
            "const k = process.env.STRIPE_KEY;\n"
            "const s = process.env['SENTRY_DSN'];\n"
            "const v = import.meta.env.VITE_API_URL;\n"
        )
        self.assertEqual(
            scan_text(text), {"STRIPE_KEY", "SENTRY_DSN", "VITE_API_URL"})

    def test_shell_and_go_and_php_patterns(self):
        text = (
            'd = os.Getenv("GO_KEY")\n'
            "e = getenv('PHP_KEY');\n"
            "f = $_ENV['SERVER_KEY'];\n"
            "echo ${SHELL_KEY} and $PLAIN_KEY\n"
        )
        self.assertEqual(
            scan_text(text),
            {"GO_KEY", "PHP_KEY", "SERVER_KEY", "SHELL_KEY", "PLAIN_KEY"})

    def test_lowercase_shell_words_are_not_variables(self):
        # Shell locals are lowercase by convention, so $home is a local
        # variable, not an environment variable, and is not flagged.
        self.assertEqual(scan_text("echo $home\n"), set())


class TestCheck(unittest.TestCase):
    def test_missing_and_extra(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root / "app.py",
                  "import os\nk = os.environ['API_KEY']\n")
            example = write(root / ".env.example",
                            "API_KEY=\nOLD_VAR=\n")
            result = check(root, example, [])
            self.assertEqual(result["missing"], [])
            self.assertEqual(result["extra"], ["OLD_VAR"])
            self.assertFalse(result["in_sync"])

    def test_in_sync(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root / "app.py",
                  "import os\nk = os.environ['API_KEY']\n")
            example = write(root / ".env.example", "API_KEY=\n")
            self.assertTrue(check(root, example, [])["in_sync"])

    def test_missing_example_file_means_all_used_are_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root / "app.py",
                  "import os\nk = os.environ['API_KEY']\n")
            result = check(root, root / ".env.example", [])
            self.assertEqual(result["missing"], ["API_KEY"])

    def test_ignore_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root / "app.py",
                  "import os\nk = os.environ['API_KEY']\n")
            example = write(root / ".env.example", "")
            self.assertTrue(check(root, example, ["API_KEY"])["in_sync"])

    def test_excluded_dirs_are_not_scanned(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root / "node_modules" / "pkg" / "index.js",
                  "const x = process.env.HIDDEN_KEY;\n")
            write(root / "app.py", "import os\nk = os.environ['API_KEY']\n")
            example = write(root / ".env.example", "API_KEY=\n")
            result = check(root, example, [])
            self.assertEqual(result["used"], ["API_KEY"])
            self.assertEqual(result["files_checked"], 1)

    def test_env_files_are_not_scanned_as_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root / ".env", "SECRET_IN_ENV_FILE=1\n")
            write(root / "app.py", "print('nothing')\n")
            example = write(root / ".env.example", "")
            result = check(root, example, [])
            self.assertEqual(result["used"], [])


class TestCli(unittest.TestCase):
    def run_tool(self, *args, cwd):
        tool = Path(__file__).resolve().parents[1] / "src" / "env_example_sync.py"
        return subprocess.run(
            [sys.executable, str(tool), *args],
            cwd=cwd, capture_output=True, text=True, check=False)

    def test_drift_exits_1_and_sync_exits_0(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root / "app.py",
                  "import os\nk = os.environ['API_KEY']\n")
            write(root / ".env.example", "API_KEY=\nOLD_VAR=\n")
            drift = self.run_tool(".", cwd=tmp)
            self.assertEqual(drift.returncode, 1)
            self.assertIn("OLD_VAR", drift.stdout)
            write(root / ".env.example", "API_KEY=\n")
            sync = self.run_tool(".", cwd=tmp)
            self.assertEqual(sync.returncode, 0)
            self.assertIn("IN SYNC", sync.stdout)

    def test_json_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root / "app.py",
                  "import os\nk = os.environ['API_KEY']\n")
            write(root / ".env.example", "")
            proc = self.run_tool(".", "--format", "json", cwd=tmp)
            data = json.loads(proc.stdout)
            self.assertEqual(data["missing"], ["API_KEY"])
            self.assertFalse(data["in_sync"])

    def test_fix_appends_missing_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root / "app.py",
                  "import os\nk = os.environ['API_KEY']\n"
                  "j = os.environ['SECOND_KEY']\n")
            write(root / ".env.example", "API_KEY=\nOLD_VAR=\n")
            proc = self.run_tool(".", "--fix", cwd=tmp)
            # OLD_VAR is still extra, so drift remains -- but SECOND_KEY
            # must now be documented, and API_KEY must not be duplicated.
            self.assertEqual(proc.returncode, 1)
            content = (root / ".env.example").read_text(encoding="utf-8")
            self.assertEqual(content.count("API_KEY="), 1)
            self.assertIn("SECOND_KEY=\n", content)
            self.assertIn("OLD_VAR=\n", content)


if __name__ == "__main__":
    unittest.main()
