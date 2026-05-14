#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


KST = ZoneInfo("Asia/Seoul")
WIDTH = 1080
HEIGHT = 1080


def escape(value: str) -> str:
    return html.escape(value or "", quote=True)


def display_len(value: str) -> int:
    length = 0
    for char in value:
        if char.isspace():
            length += 1
        elif ord(char) < 128:
            length += 1
        else:
            length += 2
    return length


def wrap_text(value: str, width: int, max_lines: int) -> list[str]:
    value = " ".join((value or "").split())
    if not value:
        return []

    lines: list[str] = []
    current = ""
    tokens = value.split(" ")
    truncated = False
    for token_index, token in enumerate(tokens):
        candidate = token if not current else f"{current} {token}"
        if display_len(candidate) <= width:
            current = candidate
            continue

        if current:
            lines.append(current)
        current = token
        if len(lines) == max_lines:
            truncated = token_index < len(tokens) - 1
            break

    if current and len(lines) < max_lines:
        lines.append(current)

    if truncated and len(lines) == max_lines and display_len(lines[-1]) > width - 2:
        while lines[-1] and display_len(lines[-1] + "...") > width:
            lines[-1] = lines[-1][:-1]
        lines[-1] = lines[-1].rstrip() + "..."

    return lines[:max_lines]


def date_label(payload: dict) -> str:
    generated_at = payload.get("generated_at", "")
    try:
        dt = datetime.fromisoformat(generated_at).astimezone(KST)
    except Exception:
        dt = datetime.now(KST)
    return dt.strftime("%Y.%m.%d")


def load_title(title: str | None, title_file: Path | None) -> str:
    if title:
        return title.strip()
    if title_file and title_file.exists():
        return title_file.read_text(encoding="utf-8").strip()
    return "오늘의 연예 뉴스 요약"


def cover_headline(title: str) -> str:
    headline = re.sub(r"^\s*오늘의\s*연예\s*뉴스\s*[:：]\s*", "", title).strip()
    return headline or title


def svg_text(lines: list[str], x: int, y: int, size: int, weight: int, fill: str, line_gap: int) -> str:
    output = []
    for index, line in enumerate(lines):
        output.append(
            f'<text x="{x}" y="{y + index * line_gap}" '
            f'font-size="{size}" font-weight="{weight}" fill="{fill}">{escape(line)}</text>'
        )
    return "\n".join(output)


def render_chip(index: int, item: dict, x: int, y: int, width: int, accent: str) -> str:
    title = item.get("title", "")
    domain = item.get("domain", "")
    title_lines = wrap_text(title, 18, 2)
    issue_text = svg_text(title_lines, x + 24, y + 64, 25, 800, "#111827", 31)
    return f"""
    <g>
      <rect x="{x}" y="{y}" width="{width}" height="138" rx="20" fill="#ffffff" stroke="#dbe3ef"/>
      <rect x="{x}" y="{y}" width="{width}" height="8" rx="4" fill="{accent}"/>
      <text x="{x + 24}" y="{y + 36}" font-size="18" font-weight="900" fill="{accent}">ISSUE {index}</text>
      {issue_text}
      <text x="{x + 24}" y="{y + 118}" font-size="16" font-weight="700" fill="#6b7280">{escape(domain)}</text>
    </g>
""".rstrip()


def render_svg(payload: dict, title: str) -> str:
    items = payload.get("items", [])[:5]
    date = date_label(payload)
    title_lines = wrap_text(cover_headline(title), 18, 3)
    accents = ["#e51b3e", "#2563eb", "#12a272"]

    chip_markup = []
    chip_positions = [
        (96, 720, 270),
        (405, 720, 270),
        (714, 720, 270),
    ]
    for index, item in enumerate(items[:3], start=1):
        x, y, w = chip_positions[index - 1]
        chip_markup.append(render_chip(index, item, x, y, w, accents[index - 1]))

    if len(title_lines) == 1:
        title_y = 384
        title_size = 72
        title_gap = 84
    elif len(title_lines) == 2:
        title_y = 340
        title_size = 70
        title_gap = 82
    else:
        title_y = 314
        title_size = 62
        title_gap = 72
    title_svg = svg_text(title_lines, 540, title_y, title_size, 950, "#10131c", title_gap).replace("<text ", '<text text-anchor="middle" ')

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#f8fafc"/>
      <stop offset="0.56" stop-color="#f4f7ff"/>
      <stop offset="1" stop-color="#fff4f4"/>
    </linearGradient>
    <filter id="softShadow" x="-10%" y="-10%" width="120%" height="130%">
      <feDropShadow dx="0" dy="14" stdDeviation="18" flood-color="#1f2933" flood-opacity="0.12"/>
    </filter>
  </defs>
  <rect width="{WIDTH}" height="{HEIGHT}" fill="url(#bg)"/>
  <rect x="54" y="54" width="972" height="972" rx="42" fill="#ffffff" fill-opacity="0.84" filter="url(#softShadow)"/>
  <rect x="90" y="96" width="174" height="42" rx="21" fill="#10131c"/>
  <text x="177" y="125" font-family="Pretendard, Apple SD Gothic Neo, sans-serif" text-anchor="middle" font-size="22" font-weight="900" fill="#ffffff">TODAY NEWS</text>
  <rect x="804" y="96" width="190" height="42" rx="21" fill="#e51b3e"/>
  <text x="899" y="125" font-family="Pretendard, Apple SD Gothic Neo, sans-serif" text-anchor="middle" font-size="22" font-weight="900" fill="#ffffff">{date}</text>

  <text x="540" y="246" font-family="Pretendard, Apple SD Gothic Neo, sans-serif" text-anchor="middle" font-size="38" font-weight="900" fill="#e51b3e">오늘의 연예 뉴스</text>
  <text x="540" y="586" font-family="Pretendard, Apple SD Gothic Neo, sans-serif" text-anchor="middle" font-size="34" font-weight="850" fill="#4b5563">관심 이슈 핵심 요약</text>

  <g font-family="Pretendard, Apple SD Gothic Neo, sans-serif">
    {title_svg}
    {"".join(chip_markup)}
  </g>
</svg>
"""


def write_cover(payload: dict, title: str, svg_output: Path, png_output: Path | None) -> None:
    svg_output.parent.mkdir(parents=True, exist_ok=True)
    svg_output.write_text(render_svg(payload, title), encoding="utf-8")

    if png_output is None:
        return

    converter = shutil.which("rsvg-convert")
    if converter is None:
        raise RuntimeError("rsvg-convert is required to create PNG output.")

    png_output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [converter, "-w", str(WIDTH), "-h", str(HEIGHT), str(svg_output), "-o", str(png_output)],
        check=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a Tistory cover image from collected news JSON.")
    parser.add_argument("input", type=Path, help="Collected news JSON path.")
    parser.add_argument("--title", help="Cover title. Overrides --title-file.")
    parser.add_argument("--title-file", type=Path, help="Read cover title from a text file.")
    parser.add_argument("--svg-output", type=Path, required=True, help="SVG output path.")
    parser.add_argument("--png-output", type=Path, help="PNG output path.")
    args = parser.parse_args()

    payload = json.loads(args.input.read_text(encoding="utf-8"))
    title = load_title(args.title, args.title_file)
    write_cover(payload, title, args.svg_output, args.png_output)

    if args.png_output:
        print(args.png_output)
    else:
        print(args.svg_output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
