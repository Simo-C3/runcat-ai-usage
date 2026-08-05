import glob
import json
import os
import shutil
import subprocess
import urllib.request
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from .models import Usage, number
from .storage import read_object


class ProviderError(ValueError):
    pass


def fetch_json(url: str, headers: Dict[str, str]) -> Dict[str, Any]:
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=15) as response:
        value = json.load(response)
    if not isinstance(value, dict):
        raise ProviderError("{} returned a non-object response".format(url))
    return value


def parse_claude_usage(payload: Dict[str, Any]) -> Usage:
    percentages = []
    for key in ("five_hour", "seven_day"):
        window = payload.get(key)
        if isinstance(window, dict):
            utilization = number(window.get("utilization"))
            if utilization is not None:
                percentages.append(utilization)
    if percentages:
        return Usage(percentage=max(percentages))

    extra_usage = payload.get("extra_usage") or {}
    used_minor = number(extra_usage.get("used_credits"))
    limit_minor = number(extra_usage.get("monthly_limit"))
    decimal_places = int(number(extra_usage.get("decimal_places")) or 0)
    currency = str(extra_usage.get("currency") or "")
    if used_minor is not None and limit_minor:
        scale = 10 ** decimal_places
        return Usage(
            percentage=used_minor / limit_minor * 100,
            used_amount=used_minor / scale,
            limit_amount=limit_minor / scale,
            amount_kind="currency",
            currency=currency,
            decimal_places=decimal_places,
        )

    utilization = number(extra_usage.get("utilization"))
    if utilization is None:
        raise ProviderError("Claude plan usage is unavailable")
    return Usage(percentage=utilization)


def parse_codex_usage(payload: Dict[str, Any]) -> Usage:
    individual_limit = ((payload.get("spend_control") or {}).get("individual_limit") or {})
    percentage = number(individual_limit.get("used_percent"))
    if percentage is not None:
        return Usage(
            percentage=percentage,
            used_amount=number(individual_limit.get("used")),
            limit_amount=number(individual_limit.get("limit")),
            amount_kind="count",
            unit="credits",
        )

    rate_limit = payload.get("rate_limit") or {}
    percentages = []
    for key in ("primary_window", "secondary_window", "primary", "secondary"):
        window = rate_limit.get(key)
        if isinstance(window, dict):
            used_percent = number(window.get("used_percent"))
            if used_percent is not None:
                percentages.append(used_percent)
    if not percentages:
        raise ProviderError("Codex plan usage is unavailable")
    return Usage(percentage=max(percentages))


def parse_copilot_usage(payload: Dict[str, Any]) -> Usage:
    quota = (payload.get("quota_snapshots") or {}).get("premium_interactions") or {}
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


def collect_claude(home: Path, http_get: Callable = fetch_json) -> Usage:
    credentials = subprocess.run(
        [
            "/usr/bin/security",
            "find-generic-password",
            "-s",
            "Claude Code-credentials",
            "-w",
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    credential = json.loads(credentials.stdout)
    oauth = credential.get("claudeAiOauth") or credential
    access_token = oauth.get("accessToken") or oauth.get("access_token")
    if not access_token:
        raise ProviderError("Claude OAuth credentials were not found")
    payload = http_get(
        "https://api.anthropic.com/api/oauth/usage",
        {
            "Authorization": "Bearer {}".format(access_token),
            "anthropic-beta": "oauth-2025-04-20",
            "Accept": "application/json",
            "User-Agent": "claude-code",
        },
    )
    return parse_claude_usage(payload)


def collect_codex(home: Path, http_get: Callable = fetch_json) -> Usage:
    auth = read_object(home / ".codex" / "auth.json") or {}
    tokens = auth.get("tokens") or {}
    access_token = tokens.get("access_token")
    account_id = tokens.get("account_id")
    if not access_token or not account_id:
        raise ProviderError("Codex OAuth credentials were not found")
    payload = http_get(
        "https://chatgpt.com/backend-api/wham/usage",
        {
            "Authorization": "Bearer {}".format(access_token),
            "ChatGPT-Account-ID": str(account_id),
            "Accept": "application/json",
            "User-Agent": "codex-cli",
        },
    )
    return parse_codex_usage(payload)


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
