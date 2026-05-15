#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import json
import re
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


def dismiss_chrome_confirm_dialog(button_label: str = "취소") -> bool:
    script = f"""
tell application "System Events"
  tell process "Google Chrome"
    repeat with dialogWindow in windows
      if (name of dialogWindow contains "내용") and (exists button "{button_label}" of dialogWindow) then
        click button "{button_label}" of dialogWindow
        return "clicked"
      end if
    end repeat
  end tell
end tell
return "none"
"""
    try:
        return run_osascript(script) == "clicked"
    except RuntimeError:
        return False


def click_chrome_accessibility_button(button_label: str) -> bool:
    script = f"""
tell application "System Events"
  tell process "Google Chrome"
    set allItems to entire contents of window 1
    repeat with itemRef in allItems
      try
        if (role of itemRef is "AXButton") and (name of itemRef is "{button_label}") then
          click itemRef
          return "clicked"
        end if
      end try
    end repeat
  end tell
end tell
return "not-found"
"""
    try:
        return run_osascript(script) == "clicked"
    except RuntimeError:
        return False


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
  set currentUrl to URL of active tab of front window
  if currentUrl starts with "{url}" then return "already-open"
  set URL of active tab of front window to "{url}"
  return "opened"
end tell
"""
    run_osascript(script)


def wait_for_editor(timeout: int = 30) -> None:
    deadline = time.time() + timeout
    last = ""
    while time.time() < deadline:
        dismiss_chrome_confirm_dialog("취소")
        js = r"""
(() => {
  const text = document.body ? document.body.innerText : "";
  const hasTitle = !!document.querySelector("#post-title-inp, .textarea_tit");
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
        try:
            last = execute_chrome_js(js)
        except RuntimeError:
            if dismiss_chrome_confirm_dialog("취소"):
                time.sleep(0.5)
                continue
            raise
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


def tistory_body_fragment(html: str) -> str:
    article_match = re.search(r"<article>\s*(.*?)\s*</article>", html, flags=re.DOTALL | re.IGNORECASE)
    fragment = article_match.group(1) if article_match else html
    fragment = re.sub(r"\s*<h1\b[^>]*>.*?</h1>\s*", "\n", fragment, count=1, flags=re.DOTALL | re.IGNORECASE)
    fragment = re.sub(r"\s*<p\b[^>]*class=\"[^\"]*\btags\b[^\"]*\"[^>]*>.*?</p>\s*", "\n", fragment, flags=re.DOTALL | re.IGNORECASE)
    return fragment.strip()


def normalize_image_urls(html: str) -> str:
    return re.sub(
        r"https://thumbnews\.nateimg\.co\.kr/(?:view610|news90|mnews90)///news\.nateimg\.co\.kr/",
        "https://news.nateimg.co.kr/",
        html,
    )


def encoded_payload(payload: dict) -> str:
    return base64.b64encode(json.dumps(payload, ensure_ascii=False).encode("utf-8")).decode("ascii")


def decode_payload_js(encoded: str) -> str:
    return f'JSON.parse(new TextDecoder().decode(Uint8Array.from(atob("{encoded}"), c => c.charCodeAt(0))))'


def close_html_block_dialog_if_open() -> dict:
    js = r"""
(() => {
  const dialogs = [...document.querySelectorAll(".mce-codeblock-dialog-container.ke-dialog-html")];
  let closed = 0;
  for (const dialog of dialogs) {
    if (dialog.getBoundingClientRect().width === 0 || getComputedStyle(dialog).display === "none") continue;
    const cancelButton = [...dialog.querySelectorAll("button")]
      .find(button => (button.innerText || button.textContent || "").trim() === "취소");
    if (cancelButton) {
      cancelButton.click();
      closed += 1;
    }
  }
  return JSON.stringify({ok: true, closed});
})()
"""
    return json.loads(execute_chrome_js(js))


def clear_editor_and_set_title(title: str) -> dict:
    encoded = encoded_payload({"title": title})
    js = f"""
(() => {{
  const payload = {decode_payload_js(encoded)};
  const fire = (el, type) => el.dispatchEvent(new Event(type, {{ bubbles: true }}));
  const titleEl = document.querySelector("#post-title-inp, .textarea_tit");
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

  const frame = [...document.querySelectorAll("iframe")].find(frame => {{
    try {{
      const body = frame.contentDocument && frame.contentDocument.body;
      return !!body && (body.isContentEditable || body.getAttribute("contenteditable") === "true");
    }} catch (_) {{
      return false;
    }}
  }});
  if (frame) {{
    const body = frame.contentDocument.body;
    body.innerHTML = "<p data-ke-size=\\"size16\\"></p>";
    fire(body, "input");
    fire(body, "change");
  }}

  for (const del of [...document.querySelectorAll("a.btn_delete")]) {{
    if ((del.innerText || "").includes("태그 삭제")) del.click();
  }}
  return JSON.stringify({{
    ok: true,
    title: payload.title,
    url: location.href,
    editorTitle: document.title
  }});
}})()
"""
    return json.loads(execute_chrome_js(js))


def open_html_block_dialog() -> None:
    js = r"""
(() => {
  for (const dialog of [...document.querySelectorAll(".mce-codeblock-dialog-container.ke-dialog-html")]) {
    if (dialog.getBoundingClientRect().width === 0 || getComputedStyle(dialog).display === "none") continue;
    const cancelButton = [...dialog.querySelectorAll("button")]
      .find(button => (button.innerText || button.textContent || "").trim() === "취소");
    if (cancelButton) cancelButton.click();
  }
  const more = document.querySelector("#more-plugin-btn-open");
  if (!more) throw new Error("more menu button not found");
  more.click();
  return JSON.stringify({ok: true});
})()
"""
    execute_chrome_js(js)
    deadline = time.time() + 5
    while time.time() < deadline:
        js = r"""
(() => {
  const item = document.querySelector("#plugin-html-block");
  if (!item) return JSON.stringify({ok: false});
  item.click();
  return JSON.stringify({ok: true});
})()
"""
        result = json.loads(execute_chrome_js(js))
        if result.get("ok"):
            return
        time.sleep(0.2)
    raise SystemExit("HTML block menu item not found")


def wait_for_html_block_dialog(timeout: int = 10) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        js = r"""
(() => {
  const dialog = document.querySelector(".mce-codeblock-dialog-container.ke-dialog-html");
  const cm = dialog && [...dialog.querySelectorAll(".CodeMirror")]
    .find(el => el.getBoundingClientRect().width > 0 && el.getBoundingClientRect().height > 0);
  return JSON.stringify({ok: !!cm});
})()
"""
        if json.loads(execute_chrome_js(js)).get("ok"):
            return
        time.sleep(0.2)
    raise SystemExit("HTML block dialog did not open")


def wait_for_html_block_dialog_closed(timeout: int = 5) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        js = r"""
(() => {
  const visible = [...document.querySelectorAll(".mce-codeblock-dialog-container.ke-dialog-html")]
    .some(dialog => dialog.getBoundingClientRect().width > 0 && getComputedStyle(dialog).display !== "none");
  return JSON.stringify({closed: !visible});
})()
"""
        if json.loads(execute_chrome_js(js)).get("closed"):
            return
        time.sleep(0.2)
    raise SystemExit("HTML block dialog did not close")


def insert_html_block(html: str) -> None:
    encoded = encoded_payload({"html": html})
    js = f"""
(() => {{
  const payload = {decode_payload_js(encoded)};
  const dialog = document.querySelector(".mce-codeblock-dialog-container.ke-dialog-html");
  if (!dialog) throw new Error("HTML block dialog not found");
  const cm = [...dialog.querySelectorAll(".CodeMirror")]
    .find(el => el.getBoundingClientRect().width > 0 && el.getBoundingClientRect().height > 0);
  if (!cm) throw new Error("HTML block CodeMirror not found");
  if (cm.CodeMirror) {{
    cm.CodeMirror.setValue(payload.html);
    cm.CodeMirror.focus();
  }} else {{
    cm.dispatchEvent(new MouseEvent("mousedown", {{ bubbles: true }}));
    cm.dispatchEvent(new MouseEvent("mouseup", {{ bubbles: true }}));
    cm.click();
    document.execCommand("selectAll", false, null);
    document.execCommand("insertText", false, payload.html);
  }}
  return JSON.stringify({{ ok: true }});
}})()
"""
    execute_chrome_js(js)
    if not click_chrome_accessibility_button("확인"):
        raise SystemExit("HTML block confirm button not found")
    wait_for_html_block_dialog_closed()


def fill_tags(tags: list[str]) -> dict:
    encoded = encoded_payload({"tags": tags})
    js = f"""
(() => {{
  const payload = {decode_payload_js(encoded)};
  const fire = (el, type) => el.dispatchEvent(new Event(type, {{ bubbles: true }}));
  const tagInput = document.querySelector("#tagText");
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
    tagCount: payload.tags.length
  }});
}})()
"""
    return json.loads(execute_chrome_js(js))


def fill_editor(title: str, html: str, tags: list[str]) -> dict:
    close_html_block_dialog_if_open()
    result = clear_editor_and_set_title(title)
    open_html_block_dialog()
    wait_for_html_block_dialog()
    insert_html_block(html)
    tag_result = fill_tags(tags)
    result.update(tag_result)
    return result


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
        html = normalize_image_urls(tistory_body_fragment((Path(post["html"])).read_text(encoding="utf-8")))
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
