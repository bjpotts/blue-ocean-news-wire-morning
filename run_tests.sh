#!/usr/bin/env bash
# Full test suite. No network access: every fetcher is exercised through
# injected data, so this is safe to run offline and on every commit.
#
#   ./run_tests.sh        quiet
#   ./run_tests.sh -v     per-test names
set -euo pipefail
cd "$(dirname "$0")"
exec python3 -W ignore -m unittest discover -s tests -p 'test_*.py' "$@"
