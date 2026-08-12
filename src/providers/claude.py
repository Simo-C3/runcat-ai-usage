import json
import subprocess
from pathlib import Path

from models import Usage, number
from .common import HttpGet, JsonObject, ProviderError, fetch_json, object_value


def parse_claude_usage(payload: JsonObject) -> Usage:
    percentages = []
    for key in ("five_hour", "seven_day"):
        window = object_value(payload.get(key))
        utilization = number(window.get("utilization"))
        if utilization is not None:
            percentages.append(utilization)
    if percentages:
        return Usage(percentage=max(percentages))

    extra_usage = object_value(payload.get("extra_usage"))
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


def collect_claude(home: Path, http_get: HttpGet = fetch_json) -> Usage:
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
    credential = object_value(json.loads(credentials.stdout))
    oauth = object_value(credential.get("claudeAiOauth")) or credential
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
