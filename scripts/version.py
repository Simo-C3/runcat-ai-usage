#!/usr/bin/env python3
"""Keep package, tag, and Homebrew Formula versions consistent."""

import argparse
import re
import sys
from pathlib import Path


SEMVER_PATTERN = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
ROOT = Path(__file__).resolve().parent.parent
INIT_PATH = ROOT / "src" / "runcat_ai_usage" / "__init__.py"
PYPROJECT_PATH = ROOT / "pyproject.toml"
FORMULA_PATH = ROOT / "Formula" / "runcat-ai-usage.rb"


class VersionError(ValueError):
    pass


def require_semver(value: str) -> str:
    if not SEMVER_PATTERN.fullmatch(value):
        raise VersionError(
            "version must use stable SemVer MAJOR.MINOR.PATCH: {}".format(value)
        )
    return value


def replace_one(path: Path, pattern: str, replacement: str) -> None:
    content = path.read_text(encoding="utf-8")
    updated, count = re.subn(pattern, replacement, content, count=1, flags=re.MULTILINE)
    if count != 1:
        raise VersionError("expected one version field in {}".format(path))
    path.write_text(updated, encoding="utf-8")


def capture_one(path: Path, pattern: str) -> str:
    content = path.read_text(encoding="utf-8")
    matches = re.findall(pattern, content, flags=re.MULTILINE)
    if len(matches) != 1:
        raise VersionError("expected one version field in {}".format(path))
    return str(matches[0])


def package_versions() -> tuple:
    return (
        capture_one(INIT_PATH, r'^__version__ = "([^"]+)"$'),
        capture_one(PYPROJECT_PATH, r'^version = "([^"]+)"$'),
    )


def package_version() -> str:
    init_version, project_version = package_versions()
    if init_version != project_version:
        raise VersionError(
            "package version mismatch: __init__={} pyproject={}".format(
                init_version, project_version
            )
        )
    return require_semver(init_version)


def formula_version() -> str:
    return require_semver(capture_one(FORMULA_PATH, r'^  version "([^"]+)"$'))


def set_package_version(version: str) -> None:
    require_semver(version)
    replace_one(
        INIT_PATH,
        r'^__version__ = "[^"]+"$',
        '__version__ = "{}"'.format(version),
    )
    replace_one(PYPROJECT_PATH, r'^version = "[^"]+"$', 'version = "{}"'.format(version))


def update_formula(version: str, url: str, sha256: str) -> None:
    require_semver(version)
    if not re.fullmatch(r"[0-9a-f]{64}", sha256):
        raise VersionError("sha256 must contain 64 lowercase hexadecimal characters")
    current = formula_version()
    if version_tuple(version) < version_tuple(current):
        raise VersionError(
            "refusing to downgrade Formula from {} to {}".format(current, version)
        )
    replace_one(FORMULA_PATH, r'^  url "[^"]+"$', '  url "{}"'.format(url))
    replace_one(FORMULA_PATH, r'^  version "[^"]+"$', '  version "{}"'.format(version))
    replace_one(FORMULA_PATH, r'^  sha256 "[^"]+"$', '  sha256 "{}"'.format(sha256))
    replace_one(
        FORMULA_PATH,
        r'assert_match "runcat-ai-usage [^"]+",',
        'assert_match "runcat-ai-usage {}",'.format(version),
    )


def version_tuple(value: str) -> tuple:
    return tuple(int(part) for part in require_semver(value).split("."))


def command_check() -> None:
    current = package_version()
    formula = formula_version()
    if version_tuple(formula) > version_tuple(current):
        raise VersionError(
            "Formula version {} is newer than package version {}".format(formula, current)
        )
    print(current)


def command_check_tag(tag: str) -> None:
    expected = "v{}".format(package_version())
    if tag != expected:
        raise VersionError("tag {} does not match package version {}".format(tag, expected))
    print(tag[1:])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("check", help="validate package and Formula versions")

    check_tag = subparsers.add_parser("check-tag", help="validate a release tag")
    check_tag.add_argument("tag")

    set_version = subparsers.add_parser("set", help="set the package version")
    set_version.add_argument("version")

    update = subparsers.add_parser(
        "update-formula",
        help="update the Formula for a published release artifact",
    )
    update.add_argument("version")
    update.add_argument("url")
    update.add_argument("sha256")
    return parser


def main(argv=None) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        if arguments.command == "check":
            command_check()
        elif arguments.command == "check-tag":
            command_check_tag(arguments.tag)
        elif arguments.command == "set":
            set_package_version(arguments.version)
        elif arguments.command == "update-formula":
            update_formula(arguments.version, arguments.url, arguments.sha256)
    except VersionError as error:
        print("version error: {}".format(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
