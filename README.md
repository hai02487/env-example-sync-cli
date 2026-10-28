# env-example-sync-cli

Scan code for environment variables, compare with `.env.example`, and fail CI when they drift.

[![CI](https://github.com/hai02487/env-example-sync-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/hai02487/env-example-sync-cli/actions/workflows/ci.yml) [![Licence: MIT](https://img.shields.io/badge/Licence-MIT-yellow.svg)](LICENSE)

## What it does

Every project has a moment where someone adds `os.environ["NEW_KEY"]` to code
and forgets `.env.example`, and the next developer's setup breaks silently.
`env-example-sync` catches that before it ships:

- **Missing** — used in code, but not documented in `.env.example`.
- **Extra** — documented in `.env.example`, but no longer used in code.
- **Exit code 1 on drift, 0 when in sync** — so it works as a CI gate.
- **`--fix`** appends missing variables to `.env.example` as `NAME=` — no value
  is ever invented, and extra variables are never deleted automatically.

It scans Python, JavaScript/TypeScript, Go, PHP, and shell files, and skips
`node_modules`, `.git`, virtualenvs, and `.env*` files themselves.

## What it does NOT do

- It does not read, print, or upload any real secret value. It only ever
  reports variable **names**.
- It does not load a real `.env` file, and it never touches one.
- It does not delete variables from `.env.example` — removing a documented
  variable is a human decision, not an automated one.
- It does not parse code as an AST. It matches text patterns, so a variable
  named only in a comment still counts as used. That is deliberate: it errs
  toward keeping a variable documented rather than deleting it.
- Shell scripts only match uppercase names (`$HOME` counts, `$home` does not),
  because lowercase shell words are locals by convention, not env vars.
- It sends nothing anywhere. Everything runs locally, Python standard
  library only.

## Install

No install step and no dependencies — Python 3.10+ is enough:

```sh
git clone https://github.com/hai02487/env-example-sync-cli.git
cd env-example-sync-cli
python3 src/env_example_sync.py --help
```

## Usage

From your project root, where `.env.example` lives:

```sh
python3 src/env_example_sync.py .
```

Real output on the bundled sample project (see `examples/sample-project`,
where `TIMEOUT` is used but undocumented and `OLD_VAR` is documented but
unused):

```text
Checked: 1 file(s)
Used in code: 3
Documented in .env.example: 3
Missing from .env.example (used but not documented):
  - TIMEOUT
Extra in .env.example (documented but not used):
  - OLD_VAR
Result: DRIFT
```

That run exits with code 1 — exactly what a CI gate wants.

Other useful forms:

```sh
# Machine-readable output for another tool to consume
python3 src/env_example_sync.py . --format json

# Ignore variables that are set by the platform, not by the project
python3 src/env_example_sync.py . --ignore PATH,HOME

# Append only the missing variables (as NAME=), then re-check
python3 src/env_example_sync.py . --fix

# Scan a different project, with its example file elsewhere
python3 src/env_example_sync.py /path/to/project --example /path/to/project/.env.example
```

## Examples

**Example 1 — a clean project passes.** A project whose code uses `API_KEY`
and whose `.env.example` lists exactly `API_KEY` prints `Result: IN SYNC`
and exits 0.

**Example 2 — the CI gate.** Add this to a workflow and a pull request that
adds a new env var without documenting it fails the build until
`.env.example` is updated (or `--fix` is run and the result committed):

```yaml
- run: python3 src/env_example_sync.py .
```

**Example 3 — the `--fix` edge case.** If a project has both a missing and
an extra variable, `--fix` appends the missing one but the run still exits
1, because the extra variable still needs a human decision. Nothing is
silently deleted.

## How it is tested

Standard library `unittest` only — 15 tests covering example parsing,
every language pattern, missing/extra classification, exit codes, JSON
output, `--fix`, `--ignore`, and excluded directories:

```sh
python3 tests/test_env_example_sync.py
```

All 15 pass on the files in this repo. The README's sample output above is
the tool's real output on `examples/sample-project`, not a mock.

## Related tools (and how this one differs)

Similar drift checkers exist, mostly for JavaScript projects: `dotenv-audit`
(Node, scans JS/TS and can auto-fill `.env.example` with generated
placeholder values) and `dotdrift` (Node, compares `.env` with
`.env.example`). This tool is the Python-stdlib alternative: it needs no
Node or npm, covers Python, JS/TS, Go, PHP, and shell in one pass, never
reads a real `.env` file, and `--fix` appends empty `NAME=` lines only —
it never invents a placeholder value that could be mistaken for a real one.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Small, focused improvements are
welcome; never weaken the safety rules (no secret values, no automatic
deletion, no invented values).

## Licence

MIT — see [LICENSE](LICENSE). This is original work, written for this repo;
the drift-checking idea is a common developer workflow, not copied code.
