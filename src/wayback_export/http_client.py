from __future__ import annotations

import hashlib
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Protocol, Tuple


class HttpClient(Protocol):
    def get_text(self, url: str, timeout: int, user_agent: str) -> str:
        ...

    def download_file(
        self, url: str, destination: Path, timeout: int, user_agent: str
    ) -> Tuple[int, str]:
        ...


class UrlLibHttpClient:
    def _request(self, url: str, user_agent: str) -> urllib.request.Request:
        return urllib.request.Request(url, headers={"User-Agent": user_agent})

    def get_text(self, url: str, timeout: int, user_agent: str) -> str:
        request = self._request(url, user_agent)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                charset = response.headers.get_content_charset() or "utf-8"
                payload = response.read()
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Failed to fetch snapshot HTML: {exc}") from exc
        return payload.decode(charset, errors="replace")

    def download_file(
        self, url: str, destination: Path, timeout: int, user_agent: str
    ) -> Tuple[int, str]:
        request = self._request(url, user_agent)
        destination.parent.mkdir(parents=True, exist_ok=True)
        sha256 = hashlib.sha256()
        total = 0
        temp_destination = destination.with_name(f"{destination.name}.part")
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                with temp_destination.open("wb") as out:
                    while True:
                        chunk = response.read(65536)
                        if not chunk:
                            break
                        out.write(chunk)
                        total += len(chunk)
                        sha256.update(chunk)
        except urllib.error.URLError as exc:
            temp_destination.unlink(missing_ok=True)
            raise RuntimeError(f"Download failed for {url}: {exc}") from exc
        os.replace(temp_destination, destination)
        return total, sha256.hexdigest()
