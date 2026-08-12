import glob
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from ..models import Usage, number
from .common import JsonObject, ProviderError, object_value


def parse_copilot_usage(payload: JsonObject) -> Usage:
    snapshots = object_value(payload.get("quota_snapshots"))
    quota = object_value(snapshots.get("premium_interactions"))
    remaining = number(quota.get("percent_remaining"))
    used = number(quota.get("credits_used"))
    entitlement = number(quota.get("entitlement"))
    if used is not None and entitlement:
        percentage = used / entitlement * 100
    elif remaining is not None:
        percentage = 100 - remaining
    else:
        raise ProviderError("GitHub Copilot plan usage is unavailable")
    return Usage(
        percentage=percentage,
        used_amount=used,
        limit_amount=entitlement,
        amount_kind="count",
        unit="AIC",
    )


def find_gh(home: Path) -> Optional[str]:
    candidates = [shutil.which("gh"), "/opt/homebrew/bin/gh", "/usr/local/bin/gh"]
    candidates.extend(
        sorted(
            glob.glob(str(home / "Library" / "Caches" / "copilot-desktop-gh-*" / "gh")),
            reverse=True,
        )
    )
    for candidate in candidates:
        if candidate and os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


def collect_copilot(home: Path) -> Usage:
    gh = find_gh(home)
    if gh is None:
        raise ProviderError("GitHub CLI (gh) was not found")
    result = subprocess.run(
        [gh, "api", "/copilot_internal/user"],
        check=True,
        capture_output=True,
        text=True,
        timeout=15,
    )
    payload = json.loads(result.stdout)
    if not isinstance(payload, dict):
        raise ProviderError("GitHub Copilot returned a non-object response")
    return parse_copilot_usage(payload)
