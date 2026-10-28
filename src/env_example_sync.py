#!/usr/bin/env python3
"""Keep .env.example in sync with the environment variables code actually uses.

One job only: scan source files for environment-variable references, compare
them with the keys in .env.example, and report the drift:

- missing: used in code, but not documented in .env.example
- extra:   documented in .env.example, but not used in code

Exit codes: 0 = in sync, 1 = drift found, 2 = usage error (argparse).

With --fix, variables that are missing from .env.example are appended to it
as ``NAME=`` (no value is ever invented). Extra variables are never removed
automatically: deleting a documented variable is a human decision.

Standard library only. Nothing is sent anywhere; everything runs locally.

Supported references (text patterns, not an AST -- see README limits):
- Python: os.environ["X"], os.environ.get("X"), os.getenv("X")
- JavaScript/TypeScript: process.env.X, process.env["X"],
  import.meta.env.X, import.meta.env["X"]
- Go: os.Getenv("X")
- PHP: getenv("X"), $_ENV["X"], $_SERVER["X"]
- Shell: ${X}, $X
"""

import argparse
import json
import re
import sys
from pathlib import Path

VAR = r"[A-Za-z_][A-Za-z0-9_]*"
# Shell locals are lowercase by convention, so shell patterns only match
# uppercase names -- otherwise every $count in a script would be flagged.
SHELL_VAR = r"[A-Z_][A-Z0-9_]*"

PATTERNS = [
    # Python
    re.compile(r"os\.environ\[\s*['\"](" + VAR + r")['\"]\s*\]"),
    re.compile(r"os\.environ\.get\(\s*['\"](" + VAR + r")['\"]"),
    re.compile(r"os\.getenv\(\s*['\"](" + VAR + r")['\"]"),
    # JavaScript / TypeScript
    re.compile(r"process\.env\.(" + VAR + r")"),
    re.compile(r"process\.env\[\s*['\"](" + VAR + r")['\"]\s*\]"),
    re.compile(r"import\.meta\.env\.(" + VAR + r")"),
    re.compile(r"import\.meta\.env\[\s*['\"](" + VAR + r")['\"]\s*\]"),
    # Go
    re.compile(r"os\.Getenv\(\s*\"(" + VAR + r")\""),
    # PHP
    re.compile(r"getenv\(\s*['\"](" + VAR + r")['\"]"),
    re.compile(r"\$_(?:ENV|SERVER)\[\s*['\"](" + VAR + r")['\"]\s*\]"),
    # Shell: ${VAR} and $VAR (braced form first, so ${VAR} is not double-counted)
    re.compile(r"\$\{(" + SHELL_VAR + r")"),
    # Exclude PHP's $_ENV / $_SERVER, which have their own pattern above.
    re.compile(r"\$(?!\{)(?!_(?:ENV|SERVER)\b)(" + SHELL_VAR + r")"),
]

EXTENSIONS = {".py", ".js", ".jsx", ".ts", ".tsx", ".sh", ".bash", ".zsh", ".go", ".php"}

EXCLUDED_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", "env",
    "dist", "build", ".tox", ".pytest_cache", "coverage", ".idea", ".vscode",
}

ENV_FILENAMES = {".env", ".env.example", ".env.local", ".env.sample"}


def parse_example(text):
    """Return the set of variable names documented in .env.example text."""
    keys = set()
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        if "=" not in line:
            continue
        key = line.split("=", 1)[0].strip()
        if re.fullmatch(VAR, key):
            keys.add(key)
    return keys


def scan_text(text):
    """Return the set of variable names referenced in one source file."""
    used = set()
    for pattern in PATTERNS:
        used.update(pattern.findall(text))
    return used


def iter_source_files(root):
    """Yield source files under root, skipping excluded dirs and env files."""
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if any(part in EXCLUDED_DIRS for part in path.relative_to(root).parts[:-1]):
            continue
        if path.name in ENV_FILENAMES:
            continue
        if path.suffix in EXTENSIONS:
            yield path


def scan_directory(root):
    """Return (used_vars, files_checked) for the source tree under root."""
    used = set()
    files_checked = 0
    for path in iter_source_files(root):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        files_checked += 1
        used.update(scan_text(text))
    return used, files_checked


def check(root, example_path, ignored):
    """Run one drift check. Returns a dict with sorted lists and a verdict."""
    used, files_checked = scan_directory(root)
    used -= set(ignored)
    try:
        documented = parse_example(example_path.read_text(encoding="utf-8"))
    except OSError:
        documented = set()
    missing = sorted(used - documented)
    extra = sorted(documented - used)
    return {
        "root": str(root),
        "example": str(example_path),
        "files_checked": files_checked,
        "used": sorted(used),
        "documented": sorted(documented),
        "missing": missing,
        "extra": extra,
        "in_sync": not missing and not extra,
    }


def render_text(result):
    """Render a drift check as human-readable text."""
    lines = [
        "Checked: {} file(s)".format(result["files_checked"]),
        "Used in code: {}".format(len(result["used"])),
        "Documented in .env.example: {}".format(len(result["documented"])),
    ]
    if result["missing"]:
        lines.append("Missing from .env.example (used but not documented):")
        lines.extend("  - {}".format(name) for name in result["missing"])
    if result["extra"]:
        lines.append("Extra in .env.example (documented but not used):")
        lines.extend("  - {}".format(name) for name in result["extra"])
    lines.append("Result: {}".format("IN SYNC" if result["in_sync"] else "DRIFT"))
    return "\n".join(lines)


def apply_fix(result, example_path):
    """Append missing variables to .env.example as NAME= lines. Returns names."""
    missing = result["missing"]
    if not missing:
        return []
    with example_path.open("a", encoding="utf-8") as handle:
        if example_path.stat().st_size > 0:
            with example_path.open("rb") as probe:
                probe.seek(-1, 2)
                if probe.read(1) != b"\n":
                    handle.write("\n")
        handle.write("".join("{}=\n".format(name) for name in missing))
    return missing


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="env-example-sync",
        description="Report drift between code's env-var use and .env.example.",
    )
    parser.add_argument("path", nargs="?", default=".",
                        help="project directory to scan (default: current directory)")
    parser.add_argument("--example", default=".env.example",
                        help="path to .env.example (default: .env.example)")
    parser.add_argument("--ignore", default="",
                        help="comma-separated variable names to ignore")
    parser.add_argument("--format", choices=["text", "json"], default="text",
                        help="output format (default: text)")
    parser.add_argument("--fix", action="store_true",
                        help="append missing variables to .env.example as NAME=")
    args = parser.parse_args(argv)

    root = Path(args.path)
    if not root.is_dir():
        parser.error("not a directory: {}".format(root))
    example_path = Path(args.example)
    ignored = [name.strip() for name in args.ignore.split(",") if name.strip()]

    result = check(root, example_path, ignored)

    if args.fix and result["missing"]:
        fixed = apply_fix(result, example_path)
        result = check(root, example_path, ignored)
        if args.format == "text":
            print("Added to {}: {}".format(example_path, ", ".join(fixed)))

    if args.format == "json":
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(render_text(result))
    return 0 if result["in_sync"] else 1


if __name__ == "__main__":
    sys.exit(main())
