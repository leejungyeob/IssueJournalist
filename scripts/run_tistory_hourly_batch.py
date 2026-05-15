#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config" / "tistory-automation.json"
KST = ZoneInfo("Asia/Seoul")
PUBLISHED_LOG = ROOT / "logs" / "tistory-published.jsonl"
ISSUED_LOG = ROOT / "logs" / "tistory-issued.jsonl"


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


def normalized_title(value: str) -> str:
    return re.sub(r"[^0-9a-z가-힣]+", "", (value or "").lower())


def load_history_keys(paths: list[Path]) -> set[str]:
    keys: set[str] = set()
    for path in paths:
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if entry.get("url"):
                keys.add(f"url:{entry['url']}")
            if entry.get("title"):
                keys.add(f"title:{normalized_title(entry['title'])}")
    return keys


def item_keys(item: dict) -> set[str]:
    keys = set()
    if item.get("url"):
        keys.add(f"url:{item['url']}")
    if item.get("title"):
        keys.add(f"title:{normalized_title(item['title'])}")
    return keys


def item_sort_key(item: dict) -> tuple:
    has_rank = 0 if item.get("rank_source") else 1
    rank_position = item.get("rank_position") or 999
    pub_date = item.get("pub_date_kst") or ""
    return (has_rank, rank_position, -float(item.get("score") or 0), pub_date)


def select_items(payload: dict, count: int, history_keys: set[str]) -> tuple[list[dict], int]:
    skipped = 0
    selected = []
    for item in sorted(payload.get("items") or [], key=item_sort_key):
        keys = item_keys(item)
        if keys & history_keys:
            skipped += 1
            continue
        selected.append(item)
        history_keys.update(keys)
        if len(selected) == count:
            break
    return selected, skipped


def append_issued_log(items: list[dict], manifest_path: Path) -> None:
    ISSUED_LOG.parent.mkdir(parents=True, exist_ok=True)
    with ISSUED_LOG.open("a", encoding="utf-8") as file:
        for item in items:
            file.write(
                json.dumps(
                    {
                        "created_at": now_kst().isoformat(timespec="seconds"),
                        "status": "queued",
                        "title": item.get("title", ""),
                        "url": item.get("url", ""),
                        "rank_source": item.get("rank_source", ""),
                        "rank_position": item.get("rank_position"),
                        "manifest": str(manifest_path),
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )


def maybe_browser_publish(config: dict, manifest_path: Path) -> None:
    browser_config = config.get("browser_publish") or {}
    publish_mode = config.get("publish_mode", "manual_copy")
    if not browser_config.get("enabled") and publish_mode == "manual_copy":
        return
    if publish_mode == "browser_publish":
        raise SystemExit("browser_publish is not enabled yet. Use browser_draft first.")
    blog_host = browser_config.get("blog_host")
    args = [
        sys.executable,
        "scripts/publish_tistory_browser.py",
        "--manifest",
        str(manifest_path),
        "--draft-save",
    ]
    if blog_host:
        args.extend(["--blog-host", str(blog_host)])
    run_command(args)


def run_batch(config: dict, output_dir: Path, record_history: bool) -> int:
    output_dir.mkdir(parents=True, exist_ok=True)

    posts_per_run = int(config.get("posts_per_run", 5))
    news_limit = max(int(config.get("news_limit", 80)), int(config.get("nate_rank_limit", 30)) + posts_per_run)
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
            "--nate-rank-limit",
            str(config.get("nate_rank_limit", 30)),
            "--output",
            str(news_json),
        ]
    )

    payload = json.loads(news_json.read_text(encoding="utf-8"))
    selected_items, skipped_history = select_items(payload, posts_per_run, load_history_keys([PUBLISHED_LOG, ISSUED_LOG]))
    if len(selected_items) < posts_per_run:
        print(
            f"ERROR: not enough unissued news items: selected {len(selected_items)} of {posts_per_run}",
            file=sys.stderr,
        )
        return 1

    selected_payload = {
        **payload,
        "selected_count": len(selected_items),
        "skipped_history_count": skipped_history,
        "items": selected_items,
    }
    news_json.write_text(json.dumps(selected_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    for index in range(posts_per_run):
        post_dir = output_dir / f"post-{index + 1:02d}"
        post_dir.mkdir(parents=True, exist_ok=True)
        html_path = post_dir / "tistory-ready.html"
        enriched_path = post_dir / "enriched.json"
        title_path = post_dir / "post-title.txt"
        title_candidates_path = post_dir / "post-title-candidates.txt"
        tags_path = post_dir / "post-tags.txt"
        cover_svg = post_dir / "cover.svg"
        cover_png = post_dir / "cover.png"

        run_command(
            [
                sys.executable,
                "scripts/enrich_tistory_issue.py",
                str(news_json),
                "--index",
                str(index),
                "--output",
                str(enriched_path),
                "--related-limit",
                str(config.get("related_articles_per_post", 5)),
                "--image-limit",
                str(config.get("image_candidates_per_post", 4)),
            ]
        )

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
                "--title-candidates-output",
                str(title_candidates_path),
                "--tags-output",
                str(tags_path),
                "--base-tags",
                base_tags,
                "--enriched",
                str(enriched_path),
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
                "enriched": str(enriched_path),
                "title": str(title_path),
                "title_candidates": str(title_candidates_path),
                "tags": str(tags_path),
                "html": str(html_path),
                "cover": str(cover_png if cover_png.exists() else cover_svg),
                "status": "ready_for_browser_publish",
            }
        )

    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    maybe_browser_publish(config, manifest_path)
    if record_history:
        append_issued_log(selected_items, manifest_path)
    print(f"OK: hourly Tistory batch created: {manifest_path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Create one hourly batch of Tistory issue posts.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--force", action="store_true", help="Run even outside configured active hours.")
    parser.add_argument("--output-dir", type=Path, help="Override output directory.")
    parser.add_argument("--no-record", action="store_true", help="Do not append selected items to local issued history.")
    args = parser.parse_args()

    config = load_config(args.config)
    current = now_kst()
    if not args.force and not within_active_hours(config, current):
        print(f"SKIP: {current.hour:02d}:00 is outside active hours")
        return 0

    output_dir = args.output_dir or output_dir_for(current)
    try:
        return run_batch(config, output_dir, not args.no_record)
    except subprocess.CalledProcessError as exc:
        print(f"ERROR: command failed with exit code {exc.returncode}: {' '.join(exc.cmd)}", file=sys.stderr)
        return exc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
