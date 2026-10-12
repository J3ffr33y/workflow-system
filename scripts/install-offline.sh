#!/usr/bin/env bash
# Installs locked dependencies from the `ci/dev-deps` branch bundle.
# Only for sandboxes that reach GitHub but not PyPI/npm; see
# .github/workflows/dev-deps-bundle.yml. Normal machines: `uv sync` and `pnpm install`.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BUNDLE="${BUNDLE_DIR:-$ROOT/../deps/bundle}"
if [ ! -d "$BUNDLE" ]; then
  git clone -q --depth 1 --branch ci/dev-deps "$(git -C "$ROOT" remote get-url origin)" "$BUNDLE"
fi
cd "$ROOT/backend"
uv venv -q --python 3.13 .venv
uv pip install -q --python .venv/bin/python --no-index --find-links "$BUNDLE/wheelhouse" -r "$BUNDLE/requirements.txt"
cd "$ROOT/frontend"
rm -rf node_modules
cat "$BUNDLE"/node_modules.tgz.part-* | tar -xzf -
echo "Offline dependencies installed."
