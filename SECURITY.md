# Security Policy

This tool runs locally, collects no data, sends nothing anywhere, and needs no API key or secret. It reports environment-variable names only — never their values — and it never reads a real `.env` file.

Its only file-writing action is `--fix`, which appends missing variable names to `.env.example` as `NAME=` lines. It never deletes lines and never writes a value.

If you find a case where it could print a secret value, read a real `.env` file, or delete a documented variable, please open an issue describing the exact commands and repo state. Do not include any real secret in the report.
