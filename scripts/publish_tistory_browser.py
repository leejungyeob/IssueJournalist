#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import json
import subprocess
import tempfile
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config" / "tistory-automation.json"
KST = ZoneInfo("Asia/Seoul")
DRAFT_LOG = ROOT / "logs" / "tistory-browser-drafts.jsonl"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def load_env(path: Path = ROOT / ".env") -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def run_osascript(script: str) -> str:
    result = subprocess.run(
        ["osascript"],
        input=script,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout).strip())
    return result.stdout.strip()


def execute_chrome_js(js: str) -> str:
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as file:
        file.write(js)
        js_path = file.name
    try:
        script = f"""
tell application "Google Chrome"
  activate
  set jsCode to read POSIX file "{js_path}"
  set jsResult to execute active tab of front window javascript jsCode
end tell
return jsResult
"""
        return run_osascript(script)
    finally:
        Path(js_path).unlink(missing_ok=True)


def assert_chrome_javascript_enabled() -> None:
    try:
        result = execute_chrome_js("JSON.stringify({ok: true})")
    except RuntimeError as exc:
        message = str(exc)
        if "AppleScript" in message or "자바스크립트 실행 기능이 꺼져" in message:
            raise SystemExit(
                "Chrome Apple Events JavaScript is disabled.\n"
                "Chrome menu에서 보기 > 개발자 > Apple Events의 자바스크립트 허용을 켠 뒤 다시 실행하세요."
            ) from exc
        raise
    if '"ok":true' not in result:
        raise SystemExit(f"Chrome JavaScript check failed: {result}")


def open_editor(blog_host: str) -> None:
    url = f"https://{blog_host.rstrip('/')}/manage/newpost"
    script = f"""
tell application "Google Chrome"
  activate
  if not (exists front window) then make new window
  set URL of active tab of front window to "{url}"
end tell
"""
    run_osascript(script)


def wait_for_editor(timeout: int = 30) -> None:
    deadline = time.time() + timeout
    last = ""
    while time.time() < deadline:
        js = r"""
(() => {
  const text = document.body ? document.body.innerText : "";
  const hasTitle = [...document.querySelectorAll("input, textarea, [contenteditable='true']")]
    .some(el => ((el.getAttribute("placeholder") || el.getAttribute("aria-label") || el.innerText || "")).includes("제목"));
  const hasEditor = !!(window.tinymce && window.tinymce.activeEditor) ||
    [...document.querySelectorAll("iframe")].some(frame => {
      try {
        const body = frame.contentDocument && frame.contentDocument.body;
        return !!body && (body.isContentEditable || body.getAttribute("contenteditable") === "true");
      } catch (_) {
        return false;
      }
    });
  return JSON.stringify({title: document.title, url: location.href, hasTitle, hasEditor, text: text.slice(0, 120)});
})()
"""
        last = execute_chrome_js(js)
        try:
            state = json.loads(last)
        except json.JSONDecodeError:
            state = {}
        if state.get("hasTitle") and state.get("hasEditor"):
            return
        time.sleep(1)
    raise SystemExit(f"Tistory editor did not become ready: {last}")


def post_from_dir(post_dir: Path) -> dict:
    return {
        "post_dir": str(post_dir),
        "title": str(post_dir / "post-title.txt"),
        "tags": str(post_dir / "post-tags.txt"),
        "html": str(post_dir / "tistory-ready.html"),
        "cover": str(post_dir / "cover.png") if (post_dir / "cover.png").exists() else str(post_dir / "cover.svg"),
    }


def load_posts(manifest: Path | None, post_dir: Path | None) -> list[dict]:
    if post_dir:
        return [post_from_dir(post_dir)]
    if not manifest:
        raise SystemExit("Either --manifest or --post-dir is required.")
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    posts = payload.get("posts") or []
    if not posts:
        raise SystemExit(f"No posts found in manifest: {manifest}")
    return posts


def config_blog_host(path: Path) -> str:
    if not path.exists():
        return ""
    config = json.loads(path.read_text(encoding="utf-8"))
    browser_publish = config.get("browser_publish") or {}
    return browser_publish.get("blog_host") or ""


def fill_editor(title: str, html: str, tags: list[str]) -> dict:
    payload = {
        "title": title,
        "html": html,
        "tags": tags,
    }
    encoded = base64.b64encode(json.dumps(payload, ensure_ascii=False).encode("utf-8")).decode("ascii")
    js = f"""
(() => {{
  const bytes = Uint8Array.from(atob("{encoded}"), c => c.charCodeAt(0));
  const payload = JSON.parse(new TextDecoder().decode(bytes));
  const fire = (el, type) => el.dispatchEvent(new Event(type, {{ bubbles: true }}));
  const titleEl = [...document.querySelectorAll("input, textarea, [contenteditable='true']")]
    .find(el => ((el.getAttribute("placeholder") || el.getAttribute("aria-label") || el.innerText || "")).includes("제목"));
  if (!titleEl) throw new Error("title field not found");
  if (titleEl.isContentEditable || titleEl.getAttribute("contenteditable") === "true") {{
    titleEl.focus();
    titleEl.textContent = payload.title;
  }} else {{
    titleEl.focus();
    titleEl.value = payload.title;
  }}
  fire(titleEl, "input");
  fire(titleEl, "change");

  if (window.tinymce && window.tinymce.activeEditor) {{
    window.tinymce.activeEditor.setContent(payload.html);
    window.tinymce.activeEditor.fire("input");
    window.tinymce.activeEditor.fire("change");
    window.tinymce.activeEditor.save();
  }} else {{
    const frame = [...document.querySelectorAll("iframe")].find(frame => {{
      try {{
        const body = frame.contentDocument && frame.contentDocument.body;
        return !!body && (body.isContentEditable || body.getAttribute("contenteditable") === "true");
      }} catch (_) {{
        return false;
      }}
    }});
    if (!frame) throw new Error("editor iframe not found");
    const body = frame.contentDocument.body;
    body.focus();
    body.innerHTML = payload.html;
    fire(body, "input");
    fire(body, "change");
  }}

  const tagInput = [...document.querySelectorAll("input, textarea")]
    .find(el => ((el.getAttribute("placeholder") || el.getAttribute("aria-label") || "")).includes("태그"));
  if (tagInput) {{
    for (const tag of payload.tags) {{
      tagInput.focus();
      tagInput.value = tag;
      fire(tagInput, "input");
      tagInput.dispatchEvent(new KeyboardEvent("keydown", {{ bubbles: true, cancelable: true, key: "Enter", code: "Enter", keyCode: 13, which: 13 }}));
      tagInput.dispatchEvent(new KeyboardEvent("keyup", {{ bubbles: true, cancelable: true, key: "Enter", code: "Enter", keyCode: 13, which: 13 }}));
    }}
  }}

  return JSON.stringify({{
    ok: true,
    title: payload.title,
    tagCount: payload.tags.length,
    url: location.href,
    editorTitle: document.title
  }});
}})()
"""
    return json.loads(execute_chrome_js(js))


def click_draft_save() -> dict:
    js = r"""
(() => {
  const buttons = [...document.querySelectorAll("button, [role='button']")];
  const button = buttons.find(el => (el.innerText || el.textContent || "").trim() === "임시저장");
  if (!button) throw new Error("draft save button not found");
  button.click();
  return JSON.stringify({ok: true, clicked: "draft_save"});
})()
"""
    return json.loads(execute_chrome_js(js))


def append_log(path: Path, entry: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(entry, ensure_ascii=False) + "\n")


def publish_posts(blog_host: str, posts: list[dict], limit: int | None, draft_save: bool, pause_seconds: float) -> None:
    assert_chrome_javascript_enabled()
    selected = posts[:limit] if limit else posts
    for index, post in enumerate(selected, start=1):
        post_dir = Path(post["post_dir"])
        title = read_text(Path(post["title"]))
        html = (Path(post["html"])).read_text(encoding="utf-8")
        tags = [tag.strip().lstrip("#") for tag in read_text(Path(post["tags"])).split(",") if tag.strip()]
        open_editor(blog_host)
        wait_for_editor()
        result = fill_editor(title, html, tags)
        status = "filled"
        if draft_save:
            click_draft_save()
            status = "draft_saved"
            append_log(
                DRAFT_LOG,
                {
                    "created_at": datetime.now(KST).isoformat(timespec="seconds"),
                    "status": status,
                    "title": title,
                    "post_dir": str(post_dir),
                    "url": result.get("url"),
                },
            )
        print(f"OK: {status}: {index}/{len(selected)} {title}")
        if pause_seconds and index < len(selected):
            time.sleep(pause_seconds)


def main() -> int:
    parser = argparse.ArgumentParser(description="Fill Tistory editor from generated draft files using logged-in Chrome.")
    parser.add_argument("--blog-host", help="Tistory blog host, e.g. goods99.tistory.com")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--manifest", type=Path, help="Hourly batch manifest.json")
    parser.add_argument("--post-dir", type=Path, help="Single post directory with post-title/tags/html files")
    parser.add_argument("--limit", type=int, help="Limit number of posts to process")
    parser.add_argument("--draft-save", action="store_true", help="Click Tistory draft save after filling each post")
    parser.add_argument("--pause-seconds", type=float, default=2.0)
    args = parser.parse_args()

    env = load_env()
    blog_host = args.blog_host or env.get("TISTORY_BLOG_HOST") or config_blog_host(args.config)
    if not blog_host:
        raise SystemExit("Missing blog host. Pass --blog-host or set TISTORY_BLOG_HOST in .env.")

    posts = load_posts(args.manifest, args.post_dir)
    publish_posts(blog_host, posts, args.limit, args.draft_save, args.pause_seconds)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
