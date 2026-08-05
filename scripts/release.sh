#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"

usage() {
    echo "Usage: $0 MAJOR.MINOR.PATCH [--push]" >&2
    exit 2
}

[ "$#" -ge 1 ] && [ "$#" -le 2 ] || usage
VERSION=$1
PUSH=false
if [ "$#" -eq 2 ]; then
    [ "$2" = "--push" ] || usage
    PUSH=true
fi

python3 scripts/version.py check >/dev/null
python3 - "$VERSION" <<'PY'
import re
import sys

if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", sys.argv[1]):
    raise SystemExit("version must use stable SemVer MAJOR.MINOR.PATCH")
PY

if [ "$(git branch --show-current)" != "main" ]; then
    echo "Release tags must be created from main." >&2
    exit 1
fi
if [ -n "$(git status --porcelain)" ]; then
    echo "The working tree must be clean." >&2
    exit 1
fi

TAG="v$VERSION"
if git rev-parse -q --verify "refs/tags/$TAG" >/dev/null; then
    echo "$TAG already exists." >&2
    exit 1
fi
if [ "$PUSH" = true ]; then
    git fetch origin main --tags
    if [ "$(git rev-parse HEAD)" != "$(git rev-parse origin/main)" ]; then
        echo "Local main must exactly match origin/main before a release." >&2
        exit 1
    fi
    if git ls-remote --exit-code --tags origin "refs/tags/$TAG" >/dev/null 2>&1; then
        echo "$TAG already exists on origin." >&2
        exit 1
    fi
fi

CURRENT=$(python3 scripts/version.py check)
if [ "$CURRENT" != "$VERSION" ]; then
    python3 - "$CURRENT" "$VERSION" <<'PY'
import sys

current = tuple(int(part) for part in sys.argv[1].split("."))
requested = tuple(int(part) for part in sys.argv[2].split("."))
if requested <= current:
    raise SystemExit("the new version must be greater than {}".format(sys.argv[1]))
PY
    python3 scripts/version.py set "$VERSION"
    python3 scripts/version.py check-tag "$TAG" >/dev/null
    if ! PYTHONPATH=src python3 -m unittest discover -s tests -q; then
        git restore -- pyproject.toml src/runcat_ai_usage/__init__.py
        exit 1
    fi
    git add pyproject.toml src/runcat_ai_usage/__init__.py
    git commit -m "chore(release): $TAG を準備する"
else
    python3 scripts/version.py check-tag "$TAG" >/dev/null
    PYTHONPATH=src python3 -m unittest discover -s tests -q
fi

git tag -a "$TAG" -m "Release $TAG"

if [ "$PUSH" = true ]; then
    git push --atomic origin main "$TAG"
    echo "Pushed $TAG. GitHub Actions will publish the release."
else
    echo "Created $TAG locally."
    echo "Push it with: git push origin main $TAG"
fi
