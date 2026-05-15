#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config" / "tistory-automation.json"
KST = ZoneInfo("Asia/Seoul")

REQUIRED_SCRIPTS = [
    "scripts/collect_entertainment_news.py",
    "scripts/render_tistory_seed_draft.py",
    "scripts/create_cover_image.py",
    "scripts/check_tistory_ready_html.py",
    "scripts/run_tistory_hourly_batch.py",
    "scripts/publish_tistory_browser.py",
]

def load_config(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RuntimeError(f"config not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"invalid config JSON: {path}: {exc}") from exc


def missing_scripts() -> list[str]:
    return [script for script in REQUIRED_SCRIPTS if not (ROOT / script).exists()]


def preflight(config: dict) -> int:
    errors: list[str] = []

    if config.get("target") != "tistory":
        errors.append(f"target must be tistory, got {config.get('target')!r}")
    if config.get("publish_mode") not in {"manual_copy", "browser_draft", "browser_publish"}:
        errors.append(f"unsupported publish_mode: {config.get('publish_mode')!r}")
    if config.get("publish_mode") == "browser_publish":
        browser_publish = config.get("browser_publish") or {}
        if not browser_publish.get("enabled"):
            errors.append("browser_publish.enabled must be true when publish_mode is browser_publish")
        if not browser_publish.get("blog_host"):
            errors.append("browser_publish.blog_host is required for browser_publish mode")
        if not shutil.which("osascript"):
            errors.append("osascript is required for Chrome browser publishing")

    scripts_missing = missing_scripts()
    if scripts_missing:
        errors.append("pipeline scripts missing: " + ", ".join(scripts_missing))

    tags = config.get("tags") or []
    if len(tags) != 10:
        errors.append(f"Tistory tags must be exactly 10, got {len(tags)}")

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print("OK: Tistory pipeline preflight passed")
    return 0


def run_command(args: list[str]) -> None:
    subprocess.run(args, cwd=ROOT, check=True)


def title_for_today() -> str:
    now = datetime.now(KST)
    return f"{now.year}년 {now.month}월 {now.day}일 연예 뉴스 핵심 이슈 정리"


def output_dir_for_today() -> Path:
    return ROOT / "drafts" / datetime.now(KST).strftime("%Y-%m-%d")


def run_pipeline(config: dict) -> int:
    output_dir = output_dir_for_today()
    output_dir.mkdir(parents=True, exist_ok=True)

    news_json = output_dir / "latest-entertainment-news.json"
    seed_html = output_dir / "seed.html"
    ready_html = output_dir / "tistory-ready.html"
    title_file = output_dir / "post-title.txt"
    tags_file = output_dir / "post-tags.txt"
    cover_svg = output_dir / "cover.svg"
    cover_png = output_dir / "cover.png"

    title_file.write_text(title_for_today() + "\n", encoding="utf-8")
    tags_file.write_text(",".join(config["tags"]) + "\n", encoding="utf-8")

    run_command(
        [
            sys.executable,
            "scripts/collect_entertainment_news.py",
            "--display",
            str(config.get("news_display_per_query", 40)),
            "--limit",
            str(config.get("news_limit", 12)),
            "--output",
            str(news_json),
        ]
    )
    run_command([sys.executable, "scripts/render_tistory_seed_draft.py", str(news_json), "--output", str(seed_html)])

    ready_html.write_text(seed_html.read_text(encoding="utf-8"), encoding="utf-8")

    cover_args = [
        sys.executable,
        "scripts/create_cover_image.py",
        str(news_json),
        "--title-file",
        str(title_file),
        "--svg-output",
        str(cover_svg),
    ]
    if shutil.which("rsvg-convert"):
        cover_args.extend(["--png-output", str(cover_png)])
    run_command(cover_args)

    run_command(
        [
            sys.executable,
            "scripts/check_tistory_ready_html.py",
            str(ready_html),
            "--title-file",
            str(title_file),
            "--tags-file",
            str(tags_file),
        ]
    )

    print("OK: Tistory draft artifacts created")
    print(f"title: {title_file}")
    print(f"tags: {tags_file}")
    print(f"html: {ready_html}")
    print(f"cover: {cover_png if cover_png.exists() else cover_svg}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Tistory entertainment-news draft pipeline.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="Tistory automation config path.")
    parser.add_argument("--preflight", action="store_true", help="Only check config, env, and required scripts.")
    args = parser.parse_args()

    try:
        config = load_config(args.config)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    status = preflight(config)
    if status != 0 or args.preflight:
        return status

    try:
        return run_pipeline(config)
    except subprocess.CalledProcessError as exc:
        print(f"ERROR: command failed with exit code {exc.returncode}: {' '.join(exc.cmd)}", file=sys.stderr)
        return exc.returncode
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
