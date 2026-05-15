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


def load_config(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def run_command(args: list[str]) -> None:
    subprocess.run(args, cwd=ROOT, check=True)


def now_kst() -> datetime:
    return datetime.now(KST)


def output_dir_for(dt: datetime) -> Path:
    return ROOT / "drafts" / dt.strftime("%Y-%m-%d") / dt.strftime("%H")


def within_active_hours(config: dict, dt: datetime) -> bool:
    return dt.hour in set(config.get("active_hours") or [])


def run_batch(config: dict, output_dir: Path) -> int:
    output_dir.mkdir(parents=True, exist_ok=True)

    posts_per_run = int(config.get("posts_per_run", 5))
    news_limit = max(int(config.get("news_limit", 30)), posts_per_run)
    base_tags = ",".join(config.get("tags") or [])
    news_json = output_dir / "latest-entertainment-news.json"
    manifest = {
        "generated_at": now_kst().isoformat(timespec="seconds"),
        "publish_mode": config.get("publish_mode", "manual_copy"),
        "posts": [],
    }

    run_command(
        [
            sys.executable,
            "scripts/collect_entertainment_news.py",
            "--display",
            str(config.get("news_display_per_query", 40)),
            "--limit",
            str(news_limit),
            "--output",
            str(news_json),
        ]
    )

    for index in range(posts_per_run):
        post_dir = output_dir / f"post-{index + 1:02d}"
        post_dir.mkdir(parents=True, exist_ok=True)
        html_path = post_dir / "tistory-ready.html"
        title_path = post_dir / "post-title.txt"
        tags_path = post_dir / "post-tags.txt"
        cover_svg = post_dir / "cover.svg"
        cover_png = post_dir / "cover.png"

        run_command(
            [
                sys.executable,
                "scripts/render_tistory_issue_post.py",
                str(news_json),
                "--index",
                str(index),
                "--output",
                str(html_path),
                "--title-output",
                str(title_path),
                "--tags-output",
                str(tags_path),
                "--base-tags",
                base_tags,
            ]
        )

        cover_args = [
            sys.executable,
            "scripts/create_cover_image.py",
            str(news_json),
            "--title-file",
            str(title_path),
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
                str(html_path),
                "--title-file",
                str(title_path),
                "--tags-file",
                str(tags_path),
            ]
        )

        manifest["posts"].append(
            {
                "post_dir": str(post_dir),
                "title": str(title_path),
                "tags": str(tags_path),
                "html": str(html_path),
                "cover": str(cover_png if cover_png.exists() else cover_svg),
                "status": "ready_for_browser_publish",
            }
        )

    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"OK: hourly Tistory batch created: {manifest_path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Create one hourly batch of Tistory issue posts.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--force", action="store_true", help="Run even outside configured active hours.")
    parser.add_argument("--output-dir", type=Path, help="Override output directory.")
    args = parser.parse_args()

    config = load_config(args.config)
    current = now_kst()
    if not args.force and not within_active_hours(config, current):
        print(f"SKIP: {current.hour:02d}:00 is outside active hours")
        return 0

    output_dir = args.output_dir or output_dir_for(current)
    try:
        return run_batch(config, output_dir)
    except subprocess.CalledProcessError as exc:
        print(f"ERROR: command failed with exit code {exc.returncode}: {' '.join(exc.cmd)}", file=sys.stderr)
        return exc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
