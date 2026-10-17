"""Source page scraping, link discovery, and throttled downloading with workbook validation."""

from datetime import datetime
import hashlib
from html.parser import HTMLParser
from io import BytesIO
from pathlib import Path
import time
from urllib.parse import urljoin, urlparse

from openpyxl import load_workbook
import requests


class _LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self._href = None
        self._text = None

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            attrs_dict = dict(attrs)
            href = attrs_dict.get("href")
            if href:
                self._href = href
                self._text = []

    def handle_data(self, data):
        if self._text is not None:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self._href is not None:
            text = " ".join("".join(self._text).split())
            self.links.append((text, self._href))
            self._href = None
            self._text = []


def discover_file(html: str, landing_url: str, utility: str, month: str) -> str:
    """Find the unique report link for a utility and month from the landing page HTML."""
    try:
        requested_month = datetime.strptime(month, "%Y-%m")
    except ValueError as exc:
        raise ValueError(
            f"Invalid month format: {month!r}. Expected YYYY-MM."
        ) from exc

    month_label = requested_month.strftime("%B %Y").casefold()
    utility_label = " ".join(utility.split()).casefold()

    parser = _LinkParser()
    parser.feed(html)

    matches = []
    for label, href in parser.links:
        normalized_label = " ".join(label.split()).casefold()

        # Check that both the utility and the month appear in the link label
        if utility_label not in normalized_label:
            continue
        if month_label not in normalized_label:
            continue

        resolved_url = urljoin(landing_url, href)
        if resolved_url not in matches:
            matches.append(resolved_url)

    if not matches:
        raise LookupError(f"No report link found for {utility!r} in month {month}")

    if len(matches) > 1:
        raise LookupError(
            f"Ambiguous report links ({len(matches)} found) for {utility!r} in month {month}"
        )

    return matches[0]


class SourceClient:
    """HTTP client that enforces rate-limiting, User-Agent fallback on 403, and file validation."""

    USER_AGENTS = [
        "python-requests/2.34.2",
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/120.0.6099.119 Mobile/15E148 Safari/604.1",
        "curl/8.5.0",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
    ]

    RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

    def __init__(self, cache_dir: str | Path = "data/cache", min_interval: float = 3.0):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.min_interval = min_interval
        self.session = requests.Session()
        self.last_request_at = 0.0

    def _request(self, url: str) -> requests.Response:
        """Execute a throttled HTTP GET request with retries and 403 User-Agent rotation."""
        last_error = None

        for attempt in range(len(self.USER_AGENTS)):
            user_agent = self.USER_AGENTS[attempt]

            # Enforce at least 3 seconds between requests
            elapsed = time.monotonic() - self.last_request_at
            if elapsed < self.min_interval:
                time.sleep(self.min_interval - elapsed)

            self.last_request_at = time.monotonic()

            try:
                response = self.session.get(
                    url,
                    headers={
                        "User-Agent": user_agent,
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    },
                    timeout=30,
                    allow_redirects=True,
                )
            except requests.RequestException as exc:
                last_error = exc
                continue

            # If 403, retry with the next User-Agent
            if response.status_code == 403:
                last_error = RuntimeError(f"HTTP 403 Forbidden with User-Agent {user_agent!r}")
                continue

            if response.status_code in self.RETRYABLE_STATUS_CODES:
                last_error = RuntimeError(f"Temporary HTTP error: {response.status_code}")
                time.sleep(2 ** attempt)
                continue

            try:
                response.raise_for_status()
            except requests.HTTPError as exc:
                raise RuntimeError(f"HTTP request failed: {response.status_code}") from exc

            return response

        raise RuntimeError(f"Request failed after retries for URL {url}: {last_error}")

    @staticmethod
    def _validate_workbook(content: bytes):
        """Verify the content is a complete, uncorrupted Excel workbook."""
        try:
            workbook = load_workbook(
                BytesIO(content),
                read_only=True,
                data_only=True,
            )
            try:
                if not workbook.sheetnames:
                    raise ValueError("Workbook contains no worksheets.")

                # Iterate through rows to catch truncated/malformed XML inside sheets
                for sheet in workbook.worksheets:
                    for _ in sheet.iter_rows(values_only=True):
                        pass
            finally:
                workbook.close()
        except Exception as exc:
            raise ValueError(f"Downloaded file is not a valid workbook: {exc}") from exc

    def fetch_page(self, url: str) -> str:
        """Fetch the landing page HTML and reject cross-host redirects."""
        response = self._request(url)

        orig_host = (urlparse(url).hostname or "").removeprefix("www.")
        final_host = (urlparse(response.url).hostname or "").removeprefix("www.")

        if orig_host != final_host:
            raise ValueError(
                f"Landing page redirected to another website: {response.url}"
            )

        return response.text

    def download_workbook(self, url: str) -> Path:
        """Download, validate, and cache an Excel workbook."""
        cache_key = hashlib.sha256(url.encode("utf-8")).hexdigest()
        cache_path = self.cache_dir / f"{cache_key}.xlsx"

        # Check existing cached file
        if cache_path.exists():
            try:
                self._validate_workbook(cache_path.read_bytes())
                return cache_path
            except (ValueError, OSError):
                cache_path.unlink(missing_ok=True)

        response = self._request(url)

        orig_host = (urlparse(url).hostname or "").removeprefix("www.")
        final_host = (urlparse(response.url).hostname or "").removeprefix("www.")
        if orig_host != final_host:
            raise ValueError(
                f"Workbook URL redirected to another website: {response.url}"
            )

        content = response.content
        self._validate_workbook(content)

        temp_path = cache_path.with_suffix(".tmp")
        try:
            temp_path.write_bytes(content)
            temp_path.replace(cache_path)
        finally:
            temp_path.unlink(missing_ok=True)

        return cache_path
