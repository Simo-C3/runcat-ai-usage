import json
import urllib.request
from typing import Any, Callable, Dict


JsonObject = Dict[str, Any]
Headers = Dict[str, str]
HttpGet = Callable[[str, Headers], JsonObject]


class ProviderError(ValueError):
    """Raised when a provider cannot supply a usable usage value."""


def object_value(value: Any) -> JsonObject:
    """Return a JSON object or an empty object for malformed optional data."""
    return value if isinstance(value, dict) else {}


def fetch_json(url: str, headers: Headers) -> JsonObject:
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=15) as response:
        value = json.load(response)
    if not isinstance(value, dict):
        raise ProviderError("{} returned a non-object response".format(url))
    return value
