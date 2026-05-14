#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
import urllib.parse
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"
AUTH_URL = "https://nid.naver.com/oauth2.0/authorize"
TOKEN_URL = "https://nid.naver.com/oauth2.0/token"
CATEGORY_URL = "https://openapi.naver.com/blog/listCategory.json"


def load_dotenv(path: Path = ENV_PATH) -> None:
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
        raise RuntimeError(f"{name} is missing. Add it to {ENV_PATH}.")
    return value


def request_json(url: str, headers: dict[str, str] | None = None) -> dict:
    request = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def print_env_lines(payload: dict) -> None:
    if "access_token" in payload:
        print(f"NAVER_BLOG_ACCESS_TOKEN={payload['access_token']}")
    if "refresh_token" in payload:
        print(f"NAVER_BLOG_REFRESH_TOKEN={payload['refresh_token']}")
    if "expires_in" in payload:
        print(f"# expires_in={payload['expires_in']}")
    if "token_type" in payload:
        print(f"# token_type={payload['token_type']}")


def auth_url(args: argparse.Namespace) -> int:
    client_id = require_env("NAVER_BLOG_CLIENT_ID")
    state = args.state or secrets.token_urlsafe(24)
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": args.redirect_uri,
        "state": state,
    }
    print(f"# state={state}")
    print(f"{AUTH_URL}?{urllib.parse.urlencode(params)}")
    return 0


def exchange(args: argparse.Namespace) -> int:
    client_id = require_env("NAVER_BLOG_CLIENT_ID")
    client_secret = require_env("NAVER_BLOG_CLIENT_SECRET")
    params = {
        "grant_type": "authorization_code",
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": args.redirect_uri,
        "code": args.code,
        "state": args.state,
    }
    payload = request_json(f"{TOKEN_URL}?{urllib.parse.urlencode(params)}")
    print_env_lines(payload)
    return 0


def refresh(args: argparse.Namespace) -> int:
    client_id = require_env("NAVER_BLOG_CLIENT_ID")
    client_secret = require_env("NAVER_BLOG_CLIENT_SECRET")
    refresh_token = args.refresh_token or require_env("NAVER_BLOG_REFRESH_TOKEN")
    params = {
        "grant_type": "refresh_token",
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
    }
    payload = request_json(f"{TOKEN_URL}?{urllib.parse.urlencode(params)}")
    print_env_lines(payload)
    return 0


def categories(args: argparse.Namespace) -> int:
    client_id = require_env("NAVER_BLOG_CLIENT_ID")
    client_secret = require_env("NAVER_BLOG_CLIENT_SECRET")
    access_token = args.access_token or require_env("NAVER_BLOG_ACCESS_TOKEN")
    payload = request_json(
        CATEGORY_URL,
        headers={
            "Authorization": f"Bearer {access_token}",
            "X-Naver-Client-Id": client_id,
            "X-Naver-Client-Secret": client_secret,
        },
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Issue or inspect Naver Blog OAuth values.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    auth_parser = subparsers.add_parser("auth-url", help="Print Naver OAuth authorization URL.")
    auth_parser.add_argument("--redirect-uri", required=True, help="Callback URL registered in Naver Developers.")
    auth_parser.add_argument("--state", help="Optional CSRF state. Random by default.")
    auth_parser.set_defaults(func=auth_url)

    exchange_parser = subparsers.add_parser("exchange", help="Exchange callback code for access/refresh tokens.")
    exchange_parser.add_argument("--redirect-uri", required=True, help="Callback URL registered in Naver Developers.")
    exchange_parser.add_argument("--code", required=True, help="code query parameter returned to callback URL.")
    exchange_parser.add_argument("--state", required=True, help="state query parameter returned to callback URL.")
    exchange_parser.set_defaults(func=exchange)

    refresh_parser = subparsers.add_parser("refresh", help="Refresh access token from refresh token.")
    refresh_parser.add_argument("--refresh-token", help="Refresh token. Defaults to NAVER_BLOG_REFRESH_TOKEN.")
    refresh_parser.set_defaults(func=refresh)

    categories_parser = subparsers.add_parser("categories", help="List Naver Blog categories.")
    categories_parser.add_argument("--access-token", help="Access token. Defaults to NAVER_BLOG_ACCESS_TOKEN.")
    categories_parser.set_defaults(func=categories)

    load_dotenv()
    args = parser.parse_args()
    try:
        return args.func(args)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
