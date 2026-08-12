from pathlib import Path

from ..models import Usage, number
from ..storage import read_object
from .common import HttpGet, JsonObject, ProviderError, fetch_json, object_value


def parse_codex_usage(payload: JsonObject) -> Usage:
    spend_control = object_value(payload.get("spend_control"))
    individual_limit = object_value(spend_control.get("individual_limit"))
    percentage = number(individual_limit.get("used_percent"))
    if percentage is not None:
        return Usage(
            percentage=percentage,
            used_amount=number(individual_limit.get("used")),
            limit_amount=number(individual_limit.get("limit")),
            amount_kind="count",
            unit="credits",
        )

    rate_limit = object_value(payload.get("rate_limit"))
    percentages = []
    for key in ("primary_window", "secondary_window", "primary", "secondary"):
        window = object_value(rate_limit.get(key))
        used_percent = number(window.get("used_percent"))
        if used_percent is not None:
            percentages.append(used_percent)
    if not percentages:
        raise ProviderError("Codex plan usage is unavailable")
    return Usage(percentage=max(percentages))


def collect_codex(home: Path, http_get: HttpGet = fetch_json) -> Usage:
    auth = read_object(home / ".codex" / "auth.json") or {}
    tokens = object_value(auth.get("tokens"))
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
