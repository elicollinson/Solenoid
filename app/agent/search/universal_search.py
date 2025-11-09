"""
Provider-agnostic web search tool that wraps Google CSE, SerpAPI, or Brave Search.
"""

from __future__ import annotations

import json
import random
import time
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Iterable, Literal, Mapping, Protocol
from urllib.parse import urlparse

import requests
from agents import function_tool
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


ProviderName = Literal["google_cse", "serpapi_google", "brave"]


class DateRange(BaseModel):
    """Structured representation of a custom time range."""

    start: str = Field(alias="from")
    end: str = Field(alias="to")

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    @field_validator("start", "end")
    @classmethod
    def _validate_iso_date(cls, value: str) -> str:
        try:
            date.fromisoformat(value)
        except ValueError as exc:  # pragma: no cover - defensive guard
            raise ValueError("Expected YYYY-MM-DD formatted date.") from exc
        return value


TimeRange = Literal["any", "past_day", "past_week", "past_month", "past_year"] | DateRange


class UniversalInputs(BaseModel):
    """Provider-agnostic search inputs."""

    query: str = Field(min_length=1)
    limit: int = Field(default=10, ge=1, le=20)
    page: int = Field(default=1, ge=1)
    locale: str = Field(default="en")
    country: str = Field(default="US")
    safe: Literal["off", "moderate", "strict"] = "moderate"
    time_range: TimeRange = "any"
    site: str | None = None
    exclude_sites: list[str] = Field(default_factory=list)
    include_raw_provider_payload: bool = False
    user_agent: str | None = Field(
        default=None,
        description="Optional user agent forwarded to providers that accept it (e.g., Brave).",
    )

    model_config = ConfigDict(extra="forbid")

    @field_validator("query")
    @classmethod
    def _strip_query(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("query must not be empty.")
        return trimmed

    @field_validator("locale")
    @classmethod
    def _validate_locale(cls, value: str) -> str:
        if not value:
            return "en"
        if len(value) == 2 and value.islower():
            return value
        if len(value) == 5 and value[2] == "-" and value[:2].islower() and value[3:].isupper():
            return value
        raise ValueError("locale must match pattern /^[a-z]{2}(-[A-Z]{2})?$/")

    @field_validator("country")
    @classmethod
    def _validate_country(cls, value: str) -> str:
        if len(value) == 2 and value.isupper():
            return value
        raise ValueError("country must be two uppercase letters (ISO 3166-1 alpha-2).")

    @field_validator("exclude_sites")
    @classmethod
    def _clean_exclude_sites(cls, values: Iterable[str]) -> list[str]:
        cleaned = [site.strip() for site in values if site and site.strip()]
        return cleaned[:100]


class NormalizedResult(BaseModel):
    """Single normalized search result row."""

    position: int
    title: str
    url: str
    display_url: str | None = None
    snippet: str | None = None
    favicon: str | None = None
    thumbnail: str | None = None
    published_at: str | None = Field(default=None, description="ISO-8601 timestamp when available.")
    source: str | None = None
    extras: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


class NormalizedOutput(BaseModel):
    """Provider-neutral search response."""

    query: str
    provider: ProviderName
    limit: int
    page: int
    result_count_estimate: int | None = None
    request_parameters_effective: dict[str, Any]
    next_page: int | None = None
    prev_page: int | None = None
    results: list[NormalizedResult]
    raw_provider_payload: dict[str, Any] | None = None

    model_config = ConfigDict(extra="forbid")


class SearchSettings(BaseSettings):
    """Environment-driven configuration."""

    search_provider: ProviderName = Field(alias="SEARCH_PROVIDER")
    google_cse_api_key: str | None = Field(default=None, alias="GOOGLE_CSE_API_KEY")
    google_cse_cx: str | None = Field(default=None, alias="GOOGLE_CSE_CX")
    serpapi_api_key: str | None = Field(default=None, alias="SERPAPI_API_KEY")
    brave_search_api_key: str | None = Field(default=None, alias="BRAVE_SEARCH_API_KEY")
    retry_max_attempts: int = Field(default=3, alias="SEARCH_RETRY_MAX")
    retry_backoff_base: float = Field(default=0.5, alias="SEARCH_RETRY_BACKOFF")
    retry_backoff_jitter: float = Field(default=0.1, alias="SEARCH_RETRY_JITTER")
    connect_timeout: float = Field(default=3.0, alias="SEARCH_CONNECT_TIMEOUT")
    read_timeout: float = Field(default=10.0, alias="SEARCH_READ_TIMEOUT")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    @field_validator("retry_max_attempts")
    @classmethod
    def _validate_retry_max(cls, value: int) -> int:
        if value < 1:
            raise ValueError("SEARCH_RETRY_MAX must be at least 1.")
        return value

    @field_validator(
        "retry_backoff_base",
        "retry_backoff_jitter",
        "connect_timeout",
        "read_timeout",
    )
    @classmethod
    def _validate_positive(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("Value must be greater than zero.")
        return value

    @model_validator(mode="after")
    def _validate_provider(self) -> "SearchSettings":
        match self.search_provider:
            case "google_cse":
                if not self.google_cse_api_key or not self.google_cse_cx:
                    raise ValueError(
                        "Google CSE requires GOOGLE_CSE_API_KEY and GOOGLE_CSE_CX environment variables."
                    )
            case "serpapi_google":
                if not self.serpapi_api_key:
                    raise ValueError("SerpAPI requires SERPAPI_API_KEY environment variable.")
            case "brave":
                if not self.brave_search_api_key:
                    raise ValueError("Brave Search requires BRAVE_SEARCH_API_KEY environment variable.")
        return self


@dataclass(slots=True)
class HttpRequest:
    """Minimal HTTP request payload."""

    method: Literal["GET"]
    url: str
    params: dict[str, Any]
    headers: dict[str, str]


@dataclass(slots=True)
class ProviderExecutionContext:
    """Execution context shared with adapters during parsing."""

    inputs: UniversalInputs
    effective_limit: int
    effective_params: dict[str, Any]
    effective_headers: dict[str, str]
    include_raw: bool


class SearchToolError(RuntimeError):
    """Structured tool error with normalized codes."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        provider: ProviderName,
        status: int | None = None,
        details: dict[str, Any] | None = None,
    ):
        self.code = code
        self.provider = provider
        self.status = status
        self.details = details or {}
        super().__init__(message)

    def format(self) -> str:
        fragments = [f"[{self.provider}] {self.code}"]
        if self.status is not None:
            fragments.append(f"status={self.status}")
        fragments.append(str(self))
        if self.details:
            fragments.append(f"details={json.dumps(self.details, ensure_ascii=False)}")
        return " | ".join(fragments)


class ProviderAdapter(Protocol):
    """Behavior shared by provider-specific adapters."""

    name: ProviderName

    def build_request(self, inputs: UniversalInputs, settings: SearchSettings) -> HttpRequest:
        ...

    def parse_response(
        self, response: requests.Response, context: ProviderExecutionContext
    ) -> NormalizedOutput:
        ...


class BaseAdapter:
    """Common helpers for provider adapters."""

    name: ProviderName

    @staticmethod
    def _hostname(url: str | None) -> str | None:
        if not url:
            return None
        try:
            return urlparse(url).hostname
        except Exception:  # pragma: no cover - defensive
            return None

    @staticmethod
    def _clean_extras(raw: Mapping[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in raw.items() if value not in (None, "", [], {})}


class GoogleCSEAdapter(BaseAdapter):
    name: ProviderName = "google_cse"
    URL = "https://customsearch.googleapis.com/customsearch/v1"

    def __init__(self, api_key: str, cx: str):
        self._api_key = api_key
        self._cx = cx

    def build_request(self, inputs: UniversalInputs, _: SearchSettings) -> HttpRequest:
        limit = min(inputs.limit, 10)
        start = (inputs.page - 1) * limit + 1
        if start + limit - 1 > 100:
            raise SearchToolError(
                code="INVALID_PARAMS",
                message="Google CSE only supports up to 100 results (start + num - 1 must be <= 100).",
                provider=self.name,
            )

        params: dict[str, Any] = {
            "key": self._api_key,
            "cx": self._cx,
            "q": inputs.query,
            "num": limit,
            "start": start,
            "hl": inputs.locale,
            "gl": inputs.country,
            "safe": "off" if inputs.safe == "off" else "active",
        }
        query = params["q"]
        if inputs.site:
            query = f"site:{inputs.site} {query}"
        if inputs.exclude_sites:
            query = f"{query} " + " ".join(f"-site:{site}" for site in inputs.exclude_sites)
        params["q"] = query

        if isinstance(inputs.time_range, str):
            mapping = {
                "past_day": ("d1", True),
                "past_week": ("w1", True),
                "past_month": ("m1", True),
                "past_year": ("y1", True),
            }
            code = mapping.get(inputs.time_range)
            if code:
                params["dateRestrict"] = code[0]
                params["sort"] = "date"
        else:
            # No direct range parameters. Retain original query.
            pass

        return HttpRequest("GET", self.URL, params=params, headers={})

    def parse_response(
        self, response: requests.Response, context: ProviderExecutionContext
    ) -> NormalizedOutput:
        data = _json_or_raise(response, self.name)
        items = data.get("items") or []
        request_info = (data.get("queries") or {}).get("request") or [{}]
        start_index = request_info[0].get("startIndex", 1)

        results: list[NormalizedResult] = []
        for idx, item in enumerate(items):
            title = item.get("title")
            url = item.get("link")
            if not title or not url:
                continue
            pagemap = item.get("pagemap") or {}
            thumbnail = _first_non_empty(
                _extract_from_sequence(pagemap.get("cse_thumbnail"), "src"),
                _extract_from_sequence(pagemap.get("cse_image"), "src"),
            )
            extras = self._clean_extras(
                {
                    "cacheId": item.get("cacheId"),
                    "pagemap": pagemap or None,
                }
            )
            results.append(
                NormalizedResult(
                    position=start_index + idx,
                    title=title,
                    url=url,
                    display_url=item.get("displayLink") or item.get("formattedUrl"),
                    snippet=item.get("snippet"),
                    favicon=None,
                    thumbnail=thumbnail,
                    published_at=None,
                    source=self._hostname(url),
                    extras=extras,
                )
            )

        total_raw = (data.get("searchInformation") or {}).get("totalResults")
        total = _safe_int(total_raw)
        next_page = _page_from_query_block(data, "nextPage") or _next_page_fallback(
            context.inputs.page,
            context.effective_limit,
            len(results),
            total_cap=100,
        )
        prev_page = _page_from_query_block(data, "previousPage") or (
            context.inputs.page - 1 if context.inputs.page > 1 else None
        )

        return NormalizedOutput(
            query=context.inputs.query,
            provider=self.name,
            limit=context.effective_limit,
            page=context.inputs.page,
            result_count_estimate=total,
            request_parameters_effective=_build_effective_request(context),
            next_page=next_page,
            prev_page=prev_page,
            results=results,
            raw_provider_payload=data if context.include_raw else None,
        )


class SerpApiAdapter(BaseAdapter):
    name: ProviderName = "serpapi_google"
    URL = "https://serpapi.com/search.json"

    def __init__(self, api_key: str):
        self._api_key = api_key

    def build_request(self, inputs: UniversalInputs, _: SearchSettings) -> HttpRequest:
        limit = min(inputs.limit, 20)
        start = (inputs.page - 1) * limit

        params: dict[str, Any] = {
            "api_key": self._api_key,
            "engine": "google",
            "q": inputs.query,
            "num": limit,
            "start": start,
            "hl": inputs.locale,
            "gl": inputs.country,
            "safe": "off" if inputs.safe == "off" else "active",
        }

        if inputs.site:
            params["q"] = f"site:{inputs.site} {params['q']}"
        if inputs.exclude_sites:
            params["q"] = f"{params['q']} " + " ".join(f"-site:{site}" for site in inputs.exclude_sites)

        if isinstance(inputs.time_range, str):
            mapping = {
                "past_day": "qdr:d",
                "past_week": "qdr:w",
                "past_month": "qdr:m",
                "past_year": "qdr:y",
            }
            code = mapping.get(inputs.time_range)
            if code:
                params["tbs"] = code
        else:
            params["tbs"] = f"cdr:1,cd_min:{inputs.time_range.start},cd_max:{inputs.time_range.end}"

        return HttpRequest("GET", self.URL, params=params, headers={})

    def parse_response(
        self, response: requests.Response, context: ProviderExecutionContext
    ) -> NormalizedOutput:
        data = _json_or_raise(response, self.name)
        if isinstance(data, dict) and data.get("error"):
            raise SearchToolError(
                code=_infer_error_code(response.status_code, data["error"]),
                message=data["error"],
                provider=self.name,
                status=response.status_code,
            )

        organic_results = data.get("organic_results") or []
        results: list[NormalizedResult] = []
        for idx, item in enumerate(organic_results):
            title = item.get("title")
            url = item.get("link")
            if not title or not url:
                continue
            position = item.get("position") or ((context.inputs.page - 1) * context.effective_limit + idx + 1)
            extras = self._clean_extras(
                {
                    "snippet_highlighted_words": item.get("snippet_highlighted_words"),
                    "cache_id": item.get("cached_page_link"),
                }
            )
            results.append(
                NormalizedResult(
                    position=position,
                    title=title,
                    url=url,
                    display_url=item.get("displayed_link"),
                    snippet=item.get("snippet"),
                    favicon=item.get("favicon"),
                    thumbnail=item.get("thumbnail"),
                    published_at=item.get("date") if _is_isoish(item.get("date")) else None,
                    source=self._hostname(url),
                    extras=extras,
                )
            )

        total = data.get("search_information", {}).get("total_results")
        next_page = (
            context.inputs.page + 1 if len(results) == context.effective_limit else None
        )
        prev_page = context.inputs.page - 1 if context.inputs.page > 1 else None

        return NormalizedOutput(
            query=context.inputs.query,
            provider=self.name,
            limit=context.effective_limit,
            page=context.inputs.page,
            result_count_estimate=total if isinstance(total, int) else None,
            request_parameters_effective=_build_effective_request(context),
            next_page=next_page,
            prev_page=prev_page,
            results=results,
            raw_provider_payload=data if context.include_raw else None,
        )


class BraveAdapter(BaseAdapter):
    name: ProviderName = "brave"
    URL = "https://api.search.brave.com/res/v1/web/search"

    def __init__(self, api_key: str):
        self._api_key = api_key

    def build_request(self, inputs: UniversalInputs, settings: SearchSettings) -> HttpRequest:
        limit = min(inputs.limit, 20)
        locale = (inputs.locale or "en").strip()
        lang_code = locale.split("-")[0] if locale else "en"
        ui_lang = locale if "-" in locale and len(locale) >= 4 else f"{lang_code}-{inputs.country}"

        params: dict[str, Any] = {
            "q": inputs.query,
            "count": limit,
            "offset": inputs.page - 1,
            "country": inputs.country,
            "search_lang": lang_code,
            "safesearch": inputs.safe,
            "ui_lang": ui_lang,
        }

        if inputs.site:
            params["q"] = f"site:{inputs.site} {params['q']}"
        if inputs.exclude_sites:
            params["q"] = f"{params['q']} " + " ".join(f"-site:{site}" for site in inputs.exclude_sites)

        if isinstance(inputs.time_range, str):
            mapping = {
                "past_day": "pd",
                "past_week": "pw",
                "past_month": "pm",
                "past_year": "py",
            }
            code = mapping.get(inputs.time_range)
            if code:
                params["freshness"] = code
        else:
            params["freshness"] = f"{inputs.time_range.start}to{inputs.time_range.end}"

        headers = {
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": self._api_key,
        }
        if inputs.user_agent:
            headers["User-Agent"] = inputs.user_agent
        return HttpRequest("GET", self.URL, params=params, headers=headers)

    def parse_response(
        self, response: requests.Response, context: ProviderExecutionContext
    ) -> NormalizedOutput:
        data = _json_or_raise(response, self.name)
        section = (data.get("web") or {}).get("results") or []
        results: list[NormalizedResult] = []
        for idx, item in enumerate(section):
            title = item.get("title")
            url = item.get("url")
            if not title or not url:
                continue
            meta = item.get("meta_url") or {}
            thumbnail = None
            thumb_data = item.get("thumbnail")
            if isinstance(thumb_data, dict):
                thumbnail = thumb_data.get("src")
            elif isinstance(thumb_data, str):
                thumbnail = thumb_data

            published_at = _normalize_datetime(item)

            results.append(
                NormalizedResult(
                    position=(context.inputs.page - 1) * context.effective_limit + idx + 1,
                    title=title,
                    url=url,
                    display_url=meta.get("hostname"),
                    snippet=item.get("description"),
                    favicon=meta.get("favicon"),
                    thumbnail=thumbnail,
                    published_at=published_at,
                    source=meta.get("hostname") or self._hostname(url),
                    extras=self._clean_extras(
                        {
                            "profile": item.get("profile"),
                            "language": item.get("language"),
                        }
                    ),
                )
            )

        next_page = (
            context.inputs.page + 1 if len(results) == context.effective_limit else None
        )
        prev_page = context.inputs.page - 1 if context.inputs.page > 1 else None

        return NormalizedOutput(
            query=context.inputs.query,
            provider=self.name,
            limit=context.effective_limit,
            page=context.inputs.page,
            result_count_estimate=None,
            request_parameters_effective=_build_effective_request(context),
            next_page=next_page,
            prev_page=prev_page,
            results=results,
            raw_provider_payload=data if context.include_raw else None,
        )


class SearchClient:
    """HTTP executor with retry and timeout policies."""

    RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504, 522, 524}

    def __init__(self, settings: SearchSettings):
        self._settings = settings
        self._session = requests.Session()

    def send(self, adapter: ProviderAdapter, request: HttpRequest) -> requests.Response:
        max_attempts = self._settings.retry_max_attempts
        base_delay = self._settings.retry_backoff_base
        jitter = self._settings.retry_backoff_jitter
        for attempt in range(1, max_attempts + 1):
            try:
                response = self._session.request(
                    method=request.method,
                    url=request.url,
                    params=request.params,
                    headers=request.headers,
                    timeout=(self._settings.connect_timeout, self._settings.read_timeout),
                )
            except requests.RequestException as exc:
                if attempt == max_attempts:
                    raise SearchToolError(
                        code="BACKEND_FAILURE",
                        message=f"HTTP request failed: {exc}",
                        provider=adapter.name,
                    ) from exc
                _sleep_with_jitter(base_delay, jitter, attempt)
                continue

            if (
                response.status_code in self.RETRYABLE_STATUS
                and attempt < max_attempts
            ):
                _sleep_with_jitter(base_delay, jitter, attempt)
                continue

            return response

        raise SearchToolError(
            code="BACKEND_FAILURE",
            message="Exhausted retry attempts without receiving a response.",
            provider=adapter.name,
        )


def _sleep_with_jitter(base_delay: float, jitter: float, attempt_number: int) -> None:
    delay = base_delay * (2 ** (attempt_number - 1))
    total_delay = delay + random.uniform(0, jitter)
    time.sleep(total_delay)


def _json_or_raise(response: requests.Response, provider: ProviderName) -> dict[str, Any]:
    if response.status_code >= 400:
        message = _extract_error_message(response)
        raise SearchToolError(
            code=_map_status_to_code(response.status_code),
            message=message,
            provider=provider,
            status=response.status_code,
        )
    try:
        payload = response.json()
    except ValueError as exc:
        raise SearchToolError(
            code="BACKEND_FAILURE",
            message="Provider returned non-JSON response.",
            provider=provider,
            status=response.status_code,
        ) from exc
    if not isinstance(payload, dict):
        raise SearchToolError(
            code="BACKEND_FAILURE",
            message="Provider returned unexpected payload shape.",
            provider=provider,
            status=response.status_code,
        )
    return payload


def _extract_error_message(response: requests.Response) -> str:
    try:
        data = response.json()
    except ValueError:
        text = response.text.strip()
        return text[:500] if text else f"HTTP {response.status_code}"

    if isinstance(data, dict):
        if "error" in data:
            maybe_dict = data["error"]
            if isinstance(maybe_dict, dict):
                message = maybe_dict.get("message") or maybe_dict.get("status")
                if message:
                    return message
            if isinstance(maybe_dict, str):
                return maybe_dict
        message = data.get("message")
        if message:
            return str(message)
    return f"HTTP {response.status_code}"


def _map_status_to_code(status: int) -> str:
    if status == 429:
        return "RATE_LIMITED"
    if status in (401, 403):
        return "UNAUTHORIZED"
    if status in (400, 404, 422):
        return "INVALID_PARAMS"
    if status >= 500:
        return "BACKEND_FAILURE"
    return "UNKNOWN_ERROR"


def _infer_error_code(status: int, message: str) -> str:
    lowered = message.lower()
    if "rate limit" in lowered or "quota" in lowered:
        return "RATE_LIMITED"
    if "api key" in lowered or "unauthorized" in lowered:
        return "UNAUTHORIZED"
    return _map_status_to_code(status)


def _build_effective_request(context: ProviderExecutionContext) -> dict[str, Any]:
    params = _redact_sensitive(context.effective_params)
    headers = _redact_sensitive(context.effective_headers)
    payload: dict[str, Any] = {"params": params}
    if headers:
        payload["headers"] = headers
    return payload


def _redact_sensitive(values: dict[str, Any]) -> dict[str, Any]:
    sensitive_keys = {"key", "api_key", "cx", "X-Subscription-Token", "x-subscription-token"}
    redacted: dict[str, Any] = {}
    for key, value in values.items():
        if key in sensitive_keys or key.lower() in sensitive_keys:
            redacted[key] = "***REDACTED***"
        else:
            redacted[key] = value
    return redacted


def _next_page_fallback(
    current_page: int, limit: int, result_count: int, *, total_cap: int | None = None
) -> int | None:
    if result_count < limit:
        return None
    if total_cap is not None:
        next_start = current_page * limit + 1
        if next_start > total_cap:
            return None
    return current_page + 1


def _page_from_query_block(data: dict[str, Any], key: str) -> int | None:
    block = (data.get("queries") or {}).get(key)
    if not block:
        return None
    entry = block[0]
    start_index = entry.get("startIndex")
    count = entry.get("count") or entry.get("num")
    if isinstance(start_index, int) and isinstance(count, int) and count > 0:
        return ((start_index - 1) // count) + 1
    return None


def _safe_int(value: Any) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _extract_from_sequence(data: Any, key: str) -> str | None:
    if isinstance(data, list) and data:
        first = data[0]
        if isinstance(first, dict):
            candidate = first.get(key)
            if candidate:
                return str(candidate)
    return None


def _first_non_empty(*values: str | None) -> str | None:
    for value in values:
        if value:
            return value
    return None


def _determine_effective_limit(params: Mapping[str, Any], fallback: int) -> int:
    for key in ("num", "count", "limit"):
        value = params.get(key)
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            try:
                return int(value)
            except ValueError:
                continue
    return fallback


def _is_isoish(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


def _normalize_datetime(item: dict[str, Any]) -> str | None:
    page_fetched = item.get("page_fetched")
    if isinstance(page_fetched, str) and _is_isoish(page_fetched):
        return datetime.fromisoformat(page_fetched.replace("Z", "+00:00")).isoformat()
    page_age = item.get("page_age")
    if isinstance(page_age, (int, float)) and page_age > 0:
        try:
            ts = datetime.utcfromtimestamp(page_age)
            return ts.isoformat() + "Z"
        except (OverflowError, ValueError):
            return None
    return None


def perform_universal_search(
    inputs: UniversalInputs, *, settings: SearchSettings | None = None
) -> dict[str, Any]:
    """Execute a universal web search and return the normalized payload."""
    resolved_settings, adapter, client = _prepare_execution(settings)
    context = ProviderExecutionContext(
        inputs=inputs,
        effective_limit=min(inputs.limit, 10 if adapter.name == "google_cse" else 20),
        effective_params={},
        effective_headers={},
        include_raw=inputs.include_raw_provider_payload,
    )
    try:
        request = adapter.build_request(inputs, resolved_settings)
    except SearchToolError:
        raise
    except Exception as exc:
        raise SearchToolError(
            code="INVALID_PARAMS",
            message=str(exc),
            provider=adapter.name,
        ) from exc

    context.effective_params = dict(request.params)
    context.effective_headers = dict(request.headers)
    context.effective_limit = _determine_effective_limit(
        context.effective_params, context.effective_limit
    )

    response = client.send(adapter, request)
    output = adapter.parse_response(response, context)
    return output.model_dump(mode="json")


def create_universal_search_tool(settings: SearchSettings | None = None):
    """Factory that materializes the universal search tool."""

    @function_tool(name_override="universal_search")
    def universal_search(inputs: UniversalInputs) -> dict[str, Any]:
        try:
            return perform_universal_search(inputs, settings=settings)
        except SearchToolError as exc:
            raise ValueError(exc.format()) from exc
        except RuntimeError as exc:  # pragma: no cover - defensive guard
            raise ValueError(str(exc)) from exc

    return universal_search


def _prepare_execution(
    settings: SearchSettings | None,
) -> tuple[SearchSettings, ProviderAdapter, SearchClient]:
    try:
        resolved_settings = settings or SearchSettings()
    except ValidationError as exc:  # pragma: no cover - configuration guard
        details = _format_validation_errors(exc.errors())
        raise SearchToolError(
            code="CONFIGURATION_ERROR",
            message=f"Universal search configuration invalid: {details}",
            provider="google_cse",
        ) from exc

    adapter: ProviderAdapter
    match resolved_settings.search_provider:
        case "google_cse":
            adapter = GoogleCSEAdapter(
                api_key=resolved_settings.google_cse_api_key or "",
                cx=resolved_settings.google_cse_cx or "",
            )
        case "serpapi_google":
            adapter = SerpApiAdapter(api_key=resolved_settings.serpapi_api_key or "")
        case "brave":
            adapter = BraveAdapter(api_key=resolved_settings.brave_search_api_key or "")
        case _:
            raise SearchToolError(
                code="CONFIGURATION_ERROR",
                message="SEARCH_PROVIDER must be one of google_cse, serpapi_google, brave.",
                provider=resolved_settings.search_provider,
            )

    client = SearchClient(resolved_settings)
    return resolved_settings, adapter, client


def _format_validation_errors(errors: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for error in errors:
        location = ".".join(str(part) for part in error.get("loc", ()))
        message = error.get("msg", "Invalid configuration")
        if location:
            parts.append(f"{location}: {message}")
        else:
            parts.append(str(message))
    return "; ".join(parts) if parts else "unknown configuration error"


__all__ = [
    "create_universal_search_tool",
    "NormalizedOutput",
    "NormalizedResult",
    "perform_universal_search",
    "SearchSettings",
    "UniversalInputs",
]
