#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import json
import mimetypes
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
PUBLISHED_LOG = ROOT / "logs" / "tistory-published.jsonl"


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


def press_chrome_key_code(key_code: int, modifiers: list[str] | None = None, delay_seconds: float = 0.15) -> None:
    using_clause = ""
    if modifiers:
        using_clause = " using {" + ", ".join(f"{modifier} down" for modifier in modifiers) + "}"
    script = f"""
tell application "Google Chrome" to activate
delay {delay_seconds}
tell application "System Events"
  key code {key_code}{using_clause}
end tell
"""
    run_osascript(script)


def get_macos_clipboard() -> str:
    result = subprocess.run(["pbpaste"], text=True, capture_output=True, check=False)
    return result.stdout if result.returncode == 0 else ""


def set_macos_clipboard(text: str) -> None:
    subprocess.run(["pbcopy"], input=text, text=True, check=True)


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
    !!document.querySelector(".html-editor .CodeMirror, .CodeMirror.cm-s-tistory-html") ||
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
  let removed = 0;
  for (const dialog of dialogs) {
    if (dialog.getBoundingClientRect().width === 0 || getComputedStyle(dialog).display === "none") {
      dialog.remove();
      removed += 1;
      continue;
    }
    const cancelButton = [...dialog.querySelectorAll("button")]
      .find(button => (button.innerText || button.textContent || "").trim() === "취소");
    if (cancelButton) {
      cancelButton.click();
      closed += 1;
    }
  }
  return JSON.stringify({ok: true, closed, removed});
})()
"""
    return json.loads(execute_chrome_js(js))


def close_publish_layer_if_open() -> dict:
    js = r"""
(() => {
  const cancelButton = document.querySelector("#unpublish-btn") ||
    [...document.querySelectorAll("button, [role='button']")]
      .find(el => (el.innerText || el.textContent || "").trim() === "취소");
  if (!cancelButton) return JSON.stringify({ok: true, closed: false});
  cancelButton.click();
  return JSON.stringify({ok: true, closed: true});
})()
"""
    state = json.loads(execute_chrome_js(js))
    if state.get("closed"):
        deadline = time.time() + 5
        while time.time() < deadline:
            layer_state = json.loads(execute_chrome_js(r"""
(() => JSON.stringify({open: !!document.querySelector("#unpublish-btn") || !!document.querySelector("input[type='file'][accept*='image']")}))()
"""))
            if not layer_state.get("open"):
                return state
            time.sleep(0.2)
    return state


def is_html_editor_mode() -> bool:
    js = r"""
(() => {
  const cm = [...document.querySelectorAll(".html-editor .CodeMirror, .CodeMirror.cm-s-tistory-html")]
    .find(el => {
      const rect = el.getBoundingClientRect();
      return !el.closest(".mce-codeblock-dialog-container") &&
        rect.width > 100 && rect.height > 20 &&
        getComputedStyle(el).display !== "none" &&
        getComputedStyle(el).visibility !== "hidden";
    });
  if (!cm) return JSON.stringify({ok: false});
  return JSON.stringify({ok: true});
})()
"""
    return bool(json.loads(execute_chrome_js(js)).get("ok"))


def wait_for_html_editor_mode(timeout: int = 10) -> None:
    deadline = time.time() + timeout
    last = {}
    while time.time() < deadline:
        js = r"""
(() => {
  const cm = [...document.querySelectorAll(".html-editor .CodeMirror, .CodeMirror.cm-s-tistory-html")]
    .find(el => {
      const rect = el.getBoundingClientRect();
      return !el.closest(".mce-codeblock-dialog-container") &&
        rect.width > 100 && rect.height > 20 &&
        getComputedStyle(el).display !== "none" &&
        getComputedStyle(el).visibility !== "hidden";
    });
  if (!cm) return JSON.stringify({ok: false, reason: "missing"});
  const rect = cm.getBoundingClientRect();
  return JSON.stringify({ok: true, rect: [Math.round(rect.x), Math.round(rect.y), Math.round(rect.width), Math.round(rect.height)]});
})()
"""
        last = json.loads(execute_chrome_js(js))
        if last.get("ok"):
            return
        time.sleep(0.2)
    raise SystemExit(f"HTML editor mode did not become ready: {last}")


def ensure_html_editor_mode() -> None:
    if is_html_editor_mode():
        return
    close_html_block_dialog_if_open()
    js = r"""
(() => {
  const button = document.querySelector("#editor-mode-layer-btn-open") || document.querySelector("#editor-mode-layer-btn");
  if (!button) throw new Error("editor mode button not found");
  button.click();
  return JSON.stringify({ok: true});
})()
"""
    execute_chrome_js(js)
    time.sleep(0.2)
    press_chrome_key_code(125)  # Down: markdown
    press_chrome_key_code(125)  # Down: HTML
    press_chrome_key_code(36)   # Return
    deadline = time.time() + 5
    while time.time() < deadline:
        if dismiss_chrome_confirm_dialog("확인"):
            break
        if is_html_editor_mode():
            break
        time.sleep(0.2)
    wait_for_html_editor_mode()


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
    const doc = frame.contentDocument;
    const body = frame.contentDocument.body;
    body.focus();
    try {{
      const selection = frame.contentWindow.getSelection();
      const range = doc.createRange();
      range.selectNodeContents(body);
      selection.removeAllRanges();
      selection.addRange(range);
      doc.execCommand("delete", false, null);
    }} catch (_) {{}}
    body.innerHTML = "<p data-ke-size=\\"size16\\"><br></p>";
    fire(body, "input");
    fire(body, "change");
    fire(body, "keyup");
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


def paste_text_to_focused_chrome(text: str) -> None:
    previous_clipboard = get_macos_clipboard()
    try:
        set_macos_clipboard(text)
        press_chrome_key_code(0, ["command"])
        press_chrome_key_code(117)
        press_chrome_key_code(9, ["command"])
        time.sleep(0.6)
    finally:
        set_macos_clipboard(previous_clipboard)


def set_html_mode_content(html: str) -> dict:
    ensure_html_editor_mode()
    js = r"""
(() => {
  const cm = [...document.querySelectorAll(".html-editor .CodeMirror, .CodeMirror.cm-s-tistory-html")]
    .find(el => {
      const rect = el.getBoundingClientRect();
      return !el.closest(".mce-codeblock-dialog-container") &&
        rect.width > 100 && rect.height > 20 &&
        getComputedStyle(el).display !== "none" &&
        getComputedStyle(el).visibility !== "hidden";
    });
  if (!cm) throw new Error("HTML CodeMirror not found");
  cm.scrollIntoView({block: "center"});
  const rect = cm.getBoundingClientRect();
  const x = Math.min(rect.left + 100, rect.right - 10);
  const y = Math.min(rect.top + 40, rect.bottom - 10);
  const target = document.elementFromPoint(x, y) || cm;
  for (const type of ["mousedown", "mouseup", "click"]) {
    target.dispatchEvent(new MouseEvent(type, {bubbles: true, clientX: x, clientY: y}));
  }
  cm.click();
  return JSON.stringify({
    ok: true,
    active: document.activeElement ? document.activeElement.tagName : "",
    rect: [Math.round(rect.x), Math.round(rect.y), Math.round(rect.width), Math.round(rect.height)]
  });
})()
"""
    focus_state = json.loads(execute_chrome_js(js))
    paste_text_to_focused_chrome(html)
    encoded = encoded_payload({"prefix": html[:80], "expected": len(html)})
    verify_js = f"""
(() => {{
  const payload = {decode_payload_js(encoded)};
  const cm = [...document.querySelectorAll(".html-editor .CodeMirror, .CodeMirror.cm-s-tistory-html")]
    .find(el => {{
      const rect = el.getBoundingClientRect();
      return !el.closest(".mce-codeblock-dialog-container") &&
        rect.width > 100 && rect.height > 20 &&
        getComputedStyle(el).display !== "none" &&
        getComputedStyle(el).visibility !== "hidden";
    }});
  const text = cm ? (cm.innerText || cm.textContent || "") : "";
  return JSON.stringify({{
    ok: text.includes(payload.prefix) &&
      text.includes("source-bookmark") &&
      text.length >= Math.floor(payload.expected * 0.8),
    textLength: text.length,
    expectedLength: payload.expected,
    hasSourceBookmark: text.includes("source-bookmark"),
    focusedElement: document.activeElement ? document.activeElement.tagName : "",
    focusState: {json.dumps(focus_state, ensure_ascii=False)}
  }});
}})()
"""
    state = json.loads(execute_chrome_js(verify_js))
    if not state.get("ok"):
        raise SystemExit(f"HTML editor content was not applied: {state}")
    return {"htmlMode": True, "htmlTextLength": state.get("textLength")}


def open_publish_layer() -> dict:
    js = r"""
(() => {
  const existing = document.querySelector("input[type='file'][accept*='image']");
  if (existing) return JSON.stringify({ok: true, alreadyOpen: true});
  const button = document.querySelector("#publish-layer-btn") ||
    [...document.querySelectorAll("button, [role='button']")]
      .find(el => (el.innerText || el.textContent || "").trim() === "완료");
  if (!button) throw new Error("publish layer button not found");
  button.click();
  return JSON.stringify({ok: true, alreadyOpen: false});
})()
"""
    state = json.loads(execute_chrome_js(js))
    deadline = time.time() + 30
    last: dict = {}
    while time.time() < deadline:
        verify_js = r"""
(() => {
  const input = document.querySelector("input[type='file'][accept*='image']");
  const publishButton = document.querySelector("#publish-btn");
  const cancelButton = document.querySelector("#unpublish-btn");
  const deleteButton = document.querySelector(".ico_delete");
  return JSON.stringify({
    ok: !!input || !!publishButton || !!cancelButton,
    hasCoverInput: !!input,
    hasPublishButton: !!publishButton,
    hasDeleteButton: !!deleteButton,
    title: document.title
  });
})()
"""
        last = json.loads(execute_chrome_js(verify_js))
        if last.get("ok"):
            state.update(last)
            return state
        time.sleep(0.2)
    raise SystemExit(f"Publish layer did not open: {last}")


def set_cover_image(cover_path: Path) -> dict:
    if not cover_path.exists():
        return {"coverApplied": False, "coverReason": "missing"}
    open_publish_layer()
    initial_state = json.loads(execute_chrome_js(r"""
(() => {
  const input = document.querySelector("input[type='file'][accept*='image']");
  return JSON.stringify({
    hasInput: !!input,
    hasExistingCover: !!document.querySelector(".ico_delete")
  });
})()
"""))
    if initial_state.get("hasExistingCover") and not initial_state.get("hasInput"):
        return {
            "coverApplied": True,
            "coverFileName": cover_path.name,
            "coverPreviewImageCount": 1,
            "coverAlreadyPresent": True,
        }
    js_prepare = r"""
(() => {
  const deleteButton = document.querySelector(".ico_delete");
  if (deleteButton) deleteButton.click();
  return JSON.stringify({ok: true, deletedExisting: !!deleteButton});
})()
"""
    prepare_state = json.loads(execute_chrome_js(js_prepare))
    if prepare_state.get("deletedExisting"):
        deadline = time.time() + 5
        while time.time() < deadline:
            state = json.loads(execute_chrome_js(r"""
(() => JSON.stringify({ok: !!document.querySelector("input[type='file'][accept*='image']")}))()
"""))
            if state.get("ok"):
                break
            time.sleep(0.2)
    mime_type = mimetypes.guess_type(str(cover_path))[0] or "image/png"
    payload = {
        "name": cover_path.name,
        "mime": mime_type,
        "base64": base64.b64encode(cover_path.read_bytes()).decode("ascii"),
    }
    encoded = encoded_payload(payload)
    js = f"""
(() => {{
  const payload = {decode_payload_js(encoded)};
  const input = [...document.querySelectorAll("input[type='file']")]
    .find(el => (el.accept || "").includes("image"));
  if (!input) throw new Error("cover image input not found");

  const binary = atob(payload.base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);

  const file = new File([bytes], payload.name, {{type: payload.mime, lastModified: Date.now()}});
  const dataTransfer = new DataTransfer();
  dataTransfer.items.add(file);
  input.files = dataTransfer.files;
  input.dispatchEvent(new Event("input", {{bubbles: true}}));
  input.dispatchEvent(new Event("change", {{bubbles: true}}));
  return JSON.stringify({{
    ok: !!(input.files && input.files[0]),
    fileName: input.files && input.files[0] ? input.files[0].name : "",
    fileCount: input.files ? input.files.length : 0
  }});
}})()
"""
    state = json.loads(execute_chrome_js(js))
    if not state.get("ok"):
        raise SystemExit(f"Cover image was not applied: {state}")
    deadline = time.time() + 10
    last: dict = {}
    while time.time() < deadline:
        last = json.loads(execute_chrome_js(r"""
(() => {
  const deleteButton = document.querySelector(".ico_delete");
  const images = [...document.querySelectorAll("img")].map(img => {
    const rect = img.getBoundingClientRect();
    return {
      src: img.src,
      width: Math.round(rect.width),
      height: Math.round(rect.height),
      visible: rect.width > 0 && rect.height > 0 && getComputedStyle(img).display !== "none"
    };
  });
  return JSON.stringify({
    ok: !!deleteButton,
    hasDeleteButton: !!deleteButton,
    previewImageCount: images.filter(img => img.visible).length
  });
})()
"""))
        if last.get("ok"):
            break
        time.sleep(0.3)
    if not last.get("ok"):
        raise SystemExit(f"Cover preview did not appear: {last}")
    return {
        "coverApplied": True,
        "coverFileName": state.get("fileName"),
        "coverPreviewImageCount": last.get("previewImageCount"),
    }


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
    close_publish_layer_if_open()
    close_html_block_dialog_if_open()
    result = clear_editor_and_set_title(title)
    result.update(set_html_mode_content(html))
    tag_result = fill_tags(tags)
    result.update(tag_result)
    return result


def draft_save_state() -> dict:
    js = r"""
(() => {
  const buttons = [...document.querySelectorAll("button, [role='button']")];
  const countButton = buttons.find(el => ((el.innerText || el.textContent || "").trim()).includes("임시저장 개수"));
  const text = document.body ? document.body.innerText : "";
  return JSON.stringify({
    countText: countButton ? (countButton.innerText || countButton.textContent || "").trim() : "",
    bodyTail: text.slice(-300)
  });
})()
"""
    return json.loads(execute_chrome_js(js))


def wait_for_draft_saved(timeout: int = 20) -> dict:
    deadline = time.time() + timeout
    last: dict = {}
    while time.time() < deadline:
        last = draft_save_state()
        count_text = last.get("countText") or ""
        body_tail = last.get("bodyTail") or ""
        if count_text and "0개" not in count_text:
            last["ok"] = True
            return last
        if "저장되었습니다" in body_tail or "임시저장 완료" in body_tail or "자동 저장 완료" in body_tail:
            last["ok"] = True
            return last
        time.sleep(0.5)
    raise SystemExit(f"Draft save did not finish: {last}")


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
    try:
        result = execute_chrome_js(js)
        if result and result != "missing value":
            json.loads(result)
    except (RuntimeError, json.JSONDecodeError):
        click_chrome_accessibility_button("임시저장")
    return wait_for_draft_saved()


def ensure_public_publish_option() -> dict:
    js = r"""
(() => {
  const visible = el => {
    const rect = el.getBoundingClientRect();
    const style = getComputedStyle(el);
    return rect.width > 0 && rect.height > 0 && style.display !== "none" && style.visibility !== "hidden";
  };
  const exactText = el => ((el.innerText || el.textContent || "").trim()).replace(/\s+/g, " ");
  const publicLabel = [...document.querySelectorAll("label, button, [role='button']")]
    .find(el => visible(el) && exactText(el) === "공개");
  if (publicLabel) {
    publicLabel.click();
    return JSON.stringify({ok: true, selected: "공개", clicked: true});
  }
  const publicInput = [...document.querySelectorAll("input[type='radio']")]
    .find(input => {
      const id = input.id ? document.querySelector(`label[for="${CSS.escape(input.id)}"]`) : null;
      const labelText = id ? exactText(id) : "";
      return labelText === "공개" || input.value === "public" || input.value === "20";
    });
  if (publicInput) {
    publicInput.checked = true;
    publicInput.dispatchEvent(new Event("input", {bubbles: true}));
    publicInput.dispatchEvent(new Event("change", {bubbles: true}));
    return JSON.stringify({ok: true, selected: "공개", clicked: false});
  }
  return JSON.stringify({ok: true, selected: "", clicked: false, reason: "public option not found"});
})()
"""
    return json.loads(execute_chrome_js(js))


def click_final_publish_button() -> dict:
    js = r"""
(() => {
  const visible = el => {
    const rect = el.getBoundingClientRect();
    const style = getComputedStyle(el);
    return rect.width > 0 && rect.height > 0 && style.display !== "none" && style.visibility !== "hidden";
  };
  const buttonText = el => ((el.innerText || el.textContent || "").trim()).replace(/\s+/g, " ");
  const button = document.querySelector("#publish-btn") ||
    [...document.querySelectorAll("button, [role='button']")]
      .find(el => visible(el) && ["발행", "공개 발행", "예약 발행"].includes(buttonText(el)));
  if (!button) throw new Error("final publish button not found");
  if (button.disabled || button.getAttribute("aria-disabled") === "true") {
    throw new Error("final publish button is disabled");
  }
  const beforeUrl = location.href;
  button.click();
  return JSON.stringify({ok: true, clicked: buttonText(button) || "publish", beforeUrl});
})()
"""
    try:
        result = execute_chrome_js(js)
        if result and result != "missing value":
            return json.loads(result)
    except (RuntimeError, json.JSONDecodeError):
        for label in ("발행", "공개 발행"):
            if click_chrome_accessibility_button(label):
                return {"ok": True, "clicked": label, "beforeUrl": ""}
        raise
    return {"ok": True, "clicked": "publish", "beforeUrl": ""}


def wait_for_publish_complete(before_url: str = "", timeout: int = 60) -> dict:
    deadline = time.time() + timeout
    last: dict = {}
    while time.time() < deadline:
        dismiss_chrome_confirm_dialog("확인")
        try:
            last = json.loads(execute_chrome_js(r"""
(() => {
  const text = document.body ? document.body.innerText : "";
  const url = location.href;
  const canonical = document.querySelector("link[rel='canonical']")?.href || "";
  const hasEditor = !!document.querySelector("#post-title-inp, .textarea_tit, #publish-layer-btn");
  const publishDoneText = /발행되었습니다|게시되었습니다|글이 등록되었습니다|등록되었습니다/.test(text);
  const movedToPublicPost = !/\/manage\/newpost|\/manage\/post/.test(url) && !/\/manage($|\/)/.test(url);
  return JSON.stringify({
    ok: publishDoneText || movedToPublicPost,
    url,
    canonical,
    title: document.title,
    hasEditor,
    publishDoneText,
    movedToPublicPost,
    bodyTail: text.slice(-300)
  });
})()
"""))
        except RuntimeError:
            if dismiss_chrome_confirm_dialog("확인"):
                time.sleep(0.8)
                continue
            raise
        current_url = last.get("url") or ""
        if last.get("ok") and (not before_url or current_url != before_url or last.get("publishDoneText")):
            last["ok"] = True
            return last
        time.sleep(1)
    raise SystemExit(f"Publish did not finish: {last}")


def click_publish() -> dict:
    open_publish_layer()
    visibility = ensure_public_publish_option()
    click_state = click_final_publish_button()
    complete = wait_for_publish_complete(click_state.get("beforeUrl", ""))
    return {
        "published": True,
        "publishClicked": click_state.get("clicked", ""),
        "publishVisibility": visibility.get("selected", ""),
        "publishedUrl": complete.get("canonical") or complete.get("url", ""),
        "publishState": complete,
    }


def append_log(path: Path, entry: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(entry, ensure_ascii=False) + "\n")


def publish_posts(
    blog_host: str,
    posts: list[dict],
    limit: int | None,
    draft_save: bool,
    prepare_publish: bool,
    publish: bool,
    pause_seconds: float,
) -> None:
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
        if prepare_publish or publish:
            result.update(set_cover_image(Path(post["cover"])))
            if publish and not result.get("coverApplied"):
                raise SystemExit(f"Cover image was not applied before publish: {post.get('cover')}")
            status = "publish_ready"
        if publish:
            result.update(click_publish())
            status = "published"
            append_log(
                PUBLISHED_LOG,
                {
                    "created_at": datetime.now(KST).isoformat(timespec="seconds"),
                    "status": status,
                    "title": title,
                    "url": post.get("source_url", ""),
                    "source_title": post.get("source_title", ""),
                    "source_url": post.get("source_url", ""),
                    "source_domain": post.get("source_domain", ""),
                    "rank_source": post.get("rank_source", ""),
                    "rank_position": post.get("rank_position"),
                    "post_dir": str(post_dir),
                    "published_url": result.get("publishedUrl", ""),
                    "cover_applied": result.get("coverApplied", False),
                },
            )
        if draft_save:
            click_draft_save()
            status = "draft_saved"
            append_log(
                DRAFT_LOG,
                {
                    "created_at": datetime.now(KST).isoformat(timespec="seconds"),
                    "status": status,
                    "title": title,
                    "source_title": post.get("source_title", ""),
                    "source_url": post.get("source_url", ""),
                    "post_dir": str(post_dir),
                    "url": result.get("url"),
                    "cover_applied": result.get("coverApplied", False),
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
    parser.add_argument("--prepare-publish", action="store_true", help="Open publish settings and apply cover image, but do not click final publish")
    parser.add_argument("--publish", action="store_true", help="Click final Tistory publish after filling each post")
    parser.add_argument("--pause-seconds", type=float, default=2.0)
    args = parser.parse_args()

    if args.publish and args.draft_save:
        raise SystemExit("--publish and --draft-save cannot be used together.")

    env = load_env()
    blog_host = args.blog_host or env.get("TISTORY_BLOG_HOST") or config_blog_host(args.config)
    if not blog_host:
        raise SystemExit("Missing blog host. Pass --blog-host or set TISTORY_BLOG_HOST in .env.")

    posts = load_posts(args.manifest, args.post_dir)
    publish_posts(blog_host, posts, args.limit, args.draft_save, args.prepare_publish, args.publish, args.pause_seconds)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
