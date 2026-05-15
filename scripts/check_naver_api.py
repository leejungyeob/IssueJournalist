#!/usr/bin/env python3
from __future__ import annotations

import html
import json
import os
import re
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"
CERT_PATHS = [
    Path("/etc/ssl/cert.pem"),
    Path("/opt/homebrew/etc/openssl@3/cert.pem"),
]


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("\"'")
        if key and key not in os.environ:
            os.environ[key] = value


def require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is missing. Fill it in {ENV_PATH}.")
    return value


def clean_news_text(text: str) -> str:
    text = html.unescape(text)
    text = re.sub(r"</?b>", "", text)
    return re.sub(r"\s+", " ", text).strip()


def ssl_context() -> ssl.SSLContext:
    for path in CERT_PATHS:
        if path.exists():
            return ssl.create_default_context(cafile=str(path))
    return ssl.create_default_context()


def main() -> int:
    load_dotenv(ENV_PATH)

    client_id = require_env("NAVER_CLIENT_ID")
    client_secret = require_env("NAVER_CLIENT_SECRET")

    params = urllib.parse.urlencode(
        {
            "query": "연예",
            "display": 3,
            "start": 1,
            "sort": "date",
        }
    )
    url = f"https://openapi.naver.com/v1/search/news.json?{params}"

    request = urllib.request.Request(url)
    request.add_header("X-Naver-Client-Id", client_id)
    request.add_header("X-Naver-Client-Secret", client_secret)

    try:
        with urllib.request.urlopen(request, timeout=10, context=ssl_context()) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        print(f"Naver API request failed: HTTP {exc.code}", file=sys.stderr)
        print(body, file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Naver API request failed: {exc}", file=sys.stderr)
        return 1

    items = payload.get("items", [])
    print(f"Naver API connection OK. Received {len(items)} news items.")
    for index, item in enumerate(items, start=1):
        title = clean_news_text(item.get("title", ""))
        publisher_date = item.get("pubDate", "")
        link = item.get("originallink") or item.get("link", "")
        print(f"{index}. {title}")
        print(f"   pubDate: {publisher_date}")
        print(f"   link: {link}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
