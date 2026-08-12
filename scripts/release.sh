#!/usr/bin/env bash
# Release agentversion to PyPI.
#
# Usage:  ./scripts/release.sh   (run from anywhere inside the repo)
#
# Builds the package, validates it, smoke-tests the built wheel (import + CLI)
# in a clean environment, refuses to proceed if the version is unsafe, and only
# then — after a typed confirmation — uploads to PyPI.
#
# Prerequisites: `uv` installed, and ~/.pypirc configured with a PyPI token.
# See RELEASING.md for the one-time setup and the full runbook.
set -euo pipefail

NAME="agentversion"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# --- resolve the package version -------------------------------------------
# Only pyproject.toml carries it; agentversion/__init__.py reads it back from
# installed metadata. SPEC_VERSION (constants.py) is the *wire format* version
# and is independent — do NOT bump it for a normal package release.
VERSION="$(grep -m1 '^version = ' pyproject.toml | sed -E 's/.*"([^"]+)".*/\1/')"
if [[ -z "$VERSION" ]]; then
  echo "ERROR: could not read version from pyproject.toml" >&2; exit 1
fi
echo "==> Releasing $NAME $VERSION"

# --- refuse to clobber an existing release (PyPI is append-only) -----------
HTTP="$(curl -s -o /dev/null -w '%{http_code}' "https://pypi.org/pypi/$NAME/$VERSION/json" || echo 000)"
if [[ "$HTTP" == "200" ]]; then
  echo "ERROR: $NAME $VERSION already exists on PyPI — a version can never be reused." >&2
  echo "       bump the version and try again." >&2
  exit 1
fi

# --- changelog reminder (advisory only) ------------------------------------
if ! grep -q "$VERSION" CHANGELOG.md; then
  echo "WARNING: no '$VERSION' entry found in CHANGELOG.md" >&2
fi

# --- build + validate ------------------------------------------------------
rm -rf dist
uv build
uvx twine check dist/*

# --- smoke-test the built wheel in a throwaway environment -----------------
wheels=(dist/*.whl); WHEEL="${wheels[0]}"
echo "==> Smoke-testing $WHEEL"
uv run --no-project --with "$WHEEL" -- python -c "
import agentversion as m
assert m.__version__ == '$VERSION', f'wheel reports {m.__version__}, expected $VERSION'
print('  import OK | __version__ =', m.__version__, '| SPEC_VERSION =', m.SPEC_VERSION)
"
uv run --no-project --with "$WHEEL" -- agentversion --help >/dev/null
echo "  CLI entry point OK"

# --- confirm, then the one irreversible step -------------------------------
echo
echo "Built and verified $NAME $VERSION."
echo "Uploading to PyPI is PERMANENT — the version can never be replaced or reused."
read -r -p "Type 'yes' to upload: " ANS
[[ "$ANS" == "yes" ]] || { echo "Aborted — nothing uploaded."; exit 1; }

uvx twine upload dist/*

# --- verify it went live (the version endpoint updates fastest) ------------
echo "==> Verifying on PyPI (cache may lag a minute)"
curl -s -o /dev/null -w "  https://pypi.org/pypi/$NAME/$VERSION/json -> HTTP %{http_code}\n" \
  "https://pypi.org/pypi/$NAME/$VERSION/json" || true
echo "Done: https://pypi.org/project/$NAME/$VERSION/"
