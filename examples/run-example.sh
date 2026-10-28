#!/bin/sh
# Run the drift check on the bundled sample project.
# Expected result: DRIFT -- TIMEOUT is used but not documented, and
# OLD_VAR is documented but not used. The exit code is therefore 1,
# which is the correct CI behaviour for a drifted project.
cd "$(dirname "$0")/.." || exit 1
python3 src/env_example_sync.py examples/sample-project \
  --example examples/sample-project/.env.example || true
