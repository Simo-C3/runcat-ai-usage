import hashlib
import json
import subprocess
from pathlib import Path
from typing import Iterable

from models import Usage, number
from .common import HttpGet, JsonObject, ProviderError, fetch_json, object_value


def _credential_value(values: Iterable[JsonObject], keys: Iterable[str]) -> str:
    for value in values:
        for key in keys:
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate:
                return candidate
    return ""


def _claude_oauth(credential: JsonObject) -> JsonObject:
    oauth = object_value(credential.get("claudeAiOauth")) or credential
    access_token = _credential_value(
        (oauth,), ("accessToken", "access_token")
    )
    if not access_token:
        raise ProviderError("Claude OAuth credentials were not found")
    return oauth


def load_claude_credential(home: Path) -> JsonObject:
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
    return object_value(json.loads(credentials.stdout))


def claude_profile_key(credential: JsonObject) -> str:
    """Return a non-secret key that isolates state for a Claude sign-in."""
    oauth = _claude_oauth(credential)
    account_identifier = _credential_value(
        (oauth, credential),
        (
            "accountUuid",
            "account_uuid",
            "userUuid",
            "user_uuid",
            "email",
        ),
    )
    organization_identifier = _credential_value(
        (oauth, credential),
        (
            "organizationUuid",
            "organization_uuid",
        ),
    )
    credential_identifier = (
        "account={};organization={}".format(
            account_identifier, organization_identifier
        )
        if account_identifier or organization_identifier
        else _credential_value(
            (oauth, credential),
            ("refreshToken", "refresh_token", "accessToken", "access_token"),
        )
    )
    digest = hashlib.sha256(credential_identifier.encode("utf-8")).hexdigest()
    return digest[:16]


def claude_state_key(home: Path) -> str:
    """Return the cache/history key for the active Claude credentials."""
    return "claude-code-{}".format(claude_profile_key(load_claude_credential(home)))


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
    oauth = _claude_oauth(load_claude_credential(home))
    access_token = _credential_value((oauth,), ("accessToken", "access_token"))
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
