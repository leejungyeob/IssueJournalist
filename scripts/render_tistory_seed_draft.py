#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
KST = ZoneInfo("Asia/Seoul")


def escape(value: str) -> str:
    return html.escape(value or "", quote=True)


def format_date(value: str) -> str:
    try:
        return datetime.fromisoformat(value).astimezone(KST).strftime("%Y.%m.%d %H:%M")
    except Exception:
        return value


def render_issue(index: int, item: dict) -> str:
    title = escape(item.get("title", ""))
    description = escape(item.get("description", ""))
    url = escape(item.get("url", ""))
    domain = escape(item.get("domain", "원문"))
    pub_date = escape(format_date(item.get("pub_date_kst", "")))

    return f"""
      <section class="news-issue">
        <h2>{index}. {title}</h2>
        <p class="meta">보도 시각: {pub_date} | 출처: <a href="{url}" target="_blank" rel="noopener noreferrer">{domain}</a></p>
        <p>{description}</p>
        <div class="source-bookmark">
          <a href="{url}" target="_blank" rel="noopener noreferrer">원문 기사: {title}</a>
          <span>{domain}</span>
          <p>{title}</p>
        </div>
      </section>
""".rstrip()


def render_html(payload: dict) -> str:
    now = datetime.now(KST)
    date_label = now.strftime("%Y년 %m월 %d일")
    date_label_compact = now.strftime("%Y년 %-m월 %-d일") if hasattr(now, "strftime") else date_label
    items = payload.get("items", [])
    lead_terms = []
    for item in items[:3]:
        terms = item.get("attention_terms") or []
        lead_term = terms[0] if terms else item.get("title", "")
        if lead_term:
            lead_terms.append(escape(lead_term))
    lead_entities = "·".join(lead_terms)
    description = (
        f"{date_label_compact} 연예뉴스 주요 이슈를 한눈에 정리했습니다."
        + (f" {lead_entities} 등 오늘 나온 소식을 확인해보세요." if lead_entities else "")
    )
    issue_links = "\n".join(
        f'          <li><a href="#issue-{index}">{escape(item.get("title", ""))}</a></li>'
        for index, item in enumerate(items, start=1)
    )
    issue_sections = "\n".join(
        render_issue(index, item).replace('class="news-issue"', f'class="news-issue" id="issue-{index}"')
        for index, item in enumerate(items, start=1)
    )

    return f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{date_label} 연예 뉴스 핵심 이슈 정리</title>
  <meta name="description" content="{description}">
  <meta property="og:title" content="{date_label} 연예 뉴스 핵심 이슈 정리">
  <meta property="og:description" content="{description}">
  <style>
    body {{
      color: #222;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      line-height: 1.75;
      margin: 0;
      padding: 32px 20px;
    }}
    article {{
      margin: 0 auto;
      max-width: 760px;
    }}
    h1, h2 {{
      line-height: 1.35;
    }}
    h1 {{
      font-size: 28px;
      margin: 0 0 18px;
    }}
    h2 {{
      font-size: 21px;
      margin-top: 34px;
    }}
    a {{
      color: #1d4ed8;
    }}
    .lead {{
      background: #f7f7f7;
      border-left: 4px solid #222;
      padding: 14px 16px;
    }}
    .meta {{
      color: #555;
      font-size: 14px;
    }}
    .source-list {{
      padding-left: 20px;
    }}
    .source-bookmark {{
      border: 1px solid #ddd;
      border-radius: 8px;
      margin: 18px 0 4px;
      padding: 14px 16px;
    }}
    .source-bookmark a {{
      display: inline-block;
      font-weight: 700;
      margin-bottom: 4px;
      text-decoration: none;
    }}
    .source-bookmark span {{
      color: #666;
      display: block;
      font-size: 13px;
    }}
    .source-bookmark p {{
      margin: 8px 0 0;
    }}
  </style>
</head>
<body>
  <article>
    <h1>{date_label} 연예 뉴스 핵심 이슈 정리</h1>
    <p class="lead">{description}</p>

    <section>
      <h2>한눈에 보는 주요 이슈</h2>
      <ul class="source-list">
{issue_links}
      </ul>
    </section>

{issue_sections}

    <section>
      <h2>마무리</h2>
      <p>오늘 연예계는 컴백, 방송 활동, 드라마, 배우 관련 소식이 고르게 이어졌습니다. 각 이슈의 자세한 내용은 항목마다 남긴 원문 기사에서 확인할 수 있습니다.</p>
    </section>
  </article>
</body>
</html>
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Render a Tistory-friendly seed HTML draft from collected news JSON.")
    parser.add_argument("input", type=Path, help="Collected news JSON path.")
    parser.add_argument("--output", type=Path, help="HTML output path.")
    args = parser.parse_args()

    payload = json.loads(args.input.read_text(encoding="utf-8"))
    rendered = render_html(payload)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
        print(args.output)
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
