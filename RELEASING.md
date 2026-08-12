# Releasing

Stable releases use annotated SemVer tags in the form `vMAJOR.MINOR.PATCH`.

## Create a release

Start from a clean, up-to-date `main` branch:

```sh
./scripts/release.sh NEXT_VERSION --push
```

Replace `NEXT_VERSION` with the next stable version, for example `0.3.2`.

The script:

1. Validates stable SemVer and a clean `main` branch.
2. Updates `pyproject.toml` and `src/runcat_ai_usage.py`.
3. Runs the unit tests.
4. Creates a version commit when needed.
5. Creates an annotated `vMAJOR.MINOR.PATCH` tag and pushes the branch and tag.

Omit `--push` to inspect the tag locally before pushing it.
The script rejects version downgrades, duplicate tags, dirty worktrees, and a
local `main` that differs from `origin/main`.

## Release pipeline

The `Release` GitHub Actions workflow runs for each `vX.Y.Z` tag. It:

1. Rejects a tag that does not match the package version.
2. Runs unit, shell, and Homebrew Formula checks.
3. Builds a versioned source archive with a SHA-256 checksum.
4. Creates a GitHub Release with generated release notes.
5. Updates the Formula on `main` to the immutable release asset.
6. Installs and tests that Formula before pushing the update.

The release workflow is safe to re-run: it replaces the release asset and
skips the Formula commit when the published values already match.

Do not move or reuse a published release tag. Create a new patch release for
corrections.
