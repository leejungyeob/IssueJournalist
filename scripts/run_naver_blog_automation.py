#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config" / "naver-blog-automation.json"

REQUIRED_CONFIG_KEYS = {
    "mode",
    "image_mode",
    "publish_mode",
    "posts_per_run",
    "images_per_post",
    "dedupe_images",
    "log_sources",
}

PIPELINE_SCRIPTS = [
    "scripts/collect_entertainment_news.py",
    "scripts/enrich_entertainment_issue.py",
    "scripts/render_naver_blog_post.py",
    "scripts/create_naver_blog_images.py",
    "scripts/validate_naver_blog_post.py",
    "scripts/publish_naver_blog.py",
]

NEWS_ENV = [
    "NAVER_CLIENT_ID",
    "NAVER_CLIENT_SECRET",
]

PUBLISH_ENV = [
    "NAVER_BLOG_CLIENT_ID",
    "NAVER_BLOG_CLIENT_SECRET",
    "NAVER_BLOG_ACCESS_TOKEN",
    "NAVER_BLOG_REFRESH_TOKEN",
    "NAVER_BLOG_CATEGORY_ID",
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


def load_config(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RuntimeError(f"config not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"invalid config JSON: {path}: {exc}") from exc


def missing_config_keys(config: dict) -> list[str]:
    return sorted(key for key in REQUIRED_CONFIG_KEYS if key not in config)


def missing_env(names: list[str]) -> list[str]:
    return [name for name in names if not os.environ.get(name, "").strip()]


def missing_scripts() -> list[str]:
    return [script for script in PIPELINE_SCRIPTS if not (ROOT / script).exists()]


def preflight(config: dict) -> int:
    errors: list[str] = []

    missing_keys = missing_config_keys(config)
    if missing_keys:
        errors.append(f"missing config keys: {', '.join(missing_keys)}")

    mode = config.get("mode")
    image_mode = config.get("image_mode")
    publish_mode = config.get("publish_mode")
    if mode != "full_auto":
        errors.append(f"mode must be full_auto for this automation, got {mode!r}")
    if image_mode != "aggressive":
        errors.append(f"image_mode must be aggressive for full automation, got {image_mode!r}")
    if publish_mode not in {"auto_publish", "dry_run"}:
        errors.append(f"publish_mode must be auto_publish or dry_run, got {publish_mode!r}")

    missing_news_env = missing_env(NEWS_ENV)
    if missing_news_env:
        errors.append(f"missing news API env: {', '.join(missing_news_env)}")

    if publish_mode == "auto_publish":
        missing_publish_env = missing_env(PUBLISH_ENV)
        if missing_publish_env:
            errors.append(f"missing Naver Blog publish env: {', '.join(missing_publish_env)}")

    not_built = missing_scripts()
    if not_built:
        errors.append("pipeline scripts not built yet: " + ", ".join(not_built))

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print("OK: Naver Blog full-auto preflight passed")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the fully automated Naver Blog entertainment pipeline.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="Automation config path.")
    parser.add_argument("--preflight", action="store_true", help="Only check config, env, and required scripts.")
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    config = load_config(args.config)

    if args.preflight:
        return preflight(config)

    status = preflight(config)
    if status != 0:
        return status

    print("Full pipeline execution will be enabled after the remaining Naver Blog scripts are implemented.")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
