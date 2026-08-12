"""Create the two lightweight reading-statistics blocks used on the home page."""

from __future__ import annotations

import argparse
import calendar
import os
import re
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from html import escape
from pathlib import Path
from typing import Any, Mapping

SHANGHAI = timezone(timedelta(hours=8))
OUT_FOLDER = Path("OUT_FOLDER")


def _day(value: object) -> date:
    if isinstance(value, datetime):
        return value.astimezone(SHANGHAI).date() if value.tzinfo else value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str) and len(value) == 10 and value[4] == "-":
        return date.fromisoformat(value)
    timestamp = int(float(value))
    if abs(timestamp) >= 10**12:
        timestamp //= 1000
    return datetime.fromtimestamp(timestamp, SHANGHAI).date()


def collect_daily_read_times(api: Any, year: int) -> dict[date, int]:
    payload = api.request(
        "/readdata/detail",
        mode="annually",
        baseTime=int(datetime(year, 1, 1, tzinfo=SHANGHAI).timestamp()),
    )
    result: dict[date, int] = defaultdict(int)
    source = payload.get("dailyReadTimes")
    if not source:
        source = payload.get("readTimes") or {}
        # Annual ``readTimes`` can be monthly.  Re-read each month so the
        # heatmap never treats monthly buckets as individual days.
        if isinstance(source, Mapping) and len(source) <= 12:
            source = {}
            final_month = datetime.now(SHANGHAI).month if year == datetime.now(SHANGHAI).year else 12
            for month in range(1, final_month + 1):
                monthly = api.request(
                    "/readdata/detail",
                    mode="monthly",
                    baseTime=int(datetime(year, month, 1, tzinfo=SHANGHAI).timestamp()),
                )
                monthly_source = monthly.get("dailyReadTimes") or monthly.get("readTimes") or {}
                if isinstance(monthly_source, Mapping):
                    source = {**source, **monthly_source}
    items = source.items() if isinstance(source, Mapping) else []
    for raw_day, raw_seconds in items:
        try:
            current = _day(raw_day)
            seconds = max(int(float(raw_seconds or 0)), 0)
        except (TypeError, ValueError, OverflowError, OSError):
            continue
        if current.year == year:
            result[current] += seconds
    result.setdefault(date(year, 1, 1), 0)
    return dict(sorted(result.items()))


def _svg_header(width: int, height: int, title: str) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
        f'height="{height}" viewBox="0 0 {width} {height}" role="img">'
        f'<title>{escape(title)}</title>'
    )


def render_heatmap(values: Mapping[date, int], year: int) -> str:
    cell, gap = 14, 3
    left, top = 46, 38
    width, height = 650, 190
    max_value = max(values.values() or [1])
    svg = [_svg_header(width, height, f"微信读书 · {year}")]
    svg.append('<rect width="100%" height="100%" fill="white" rx="12"/>')
    svg.append(f'<text x="{left}" y="22" font-size="16" font-weight="600">微信读书 · {year}</text>')
    first = date(year, 1, 1)
    start = first - timedelta(days=(first.weekday() + 1) % 7)
    for index in range(53 * 7):
        current = start + timedelta(days=index)
        if current.year != year:
            continue
        column, row = (current - start).days // 7, (current - start).days % 7
        value = values.get(current, 0)
        level = 0 if not value else min(4, 1 + int(value / max_value * 3.99))
        colors = ["#ebedf0", "#ace7ae", "#69c16e", "#3aaf55", "#216e39"]
        x, y = left + column * (cell + gap), top + row * (cell + gap)
        svg.append(f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" rx="3" fill="{colors[level]}"/>')
    for month in range(1, 13):
        month_day = date(year, month, 1)
        column = (month_day - start).days // 7
        svg.append(f'<text x="{left + column * (cell + gap)}" y="{top - 8}" font-size="10">{month}月</text>')
    svg.append('</svg>')
    return "".join(svg)


def render_reading_time(values: Mapping[date, int], year: int) -> str:
    width, height = 650, 240
    rows: dict[str, int] = defaultdict(int)
    for current, seconds in values.items():
        monday = current - timedelta(days=current.weekday())
        rows[monday.strftime("%m/%d")] += seconds
    rows = dict(list(sorted(rows.items()))[-12:])
    max_hours = max([seconds / 3600 for seconds in rows.values()] or [1])
    svg = [_svg_header(width, height, "阅读时长")]
    svg.append('<rect width="100%" height="100%" fill="white" rx="12"/>')
    svg.append('<text x="34" y="28" font-size="18" font-weight="600">阅读时长</text>')
    base_y = 195
    chart_h = 140
    bar_w = 34
    step = 48
    for index, (label, seconds) in enumerate(rows.items()):
        hours = seconds / 3600
        bar_h = max(2, int(chart_h * hours / max_hours)) if seconds else 2
        x = 42 + index * step
        y = base_y - bar_h
        svg.append(f'<rect x="{x}" y="{y}" width="{bar_w}" height="{bar_h}" rx="4" fill="#e86f63"/>')
        svg.append(f'<text x="{x + bar_w / 2}" y="{base_y + 18}" text-anchor="middle" font-size="10">{escape(label)}</text>')
        svg.append(f'<text x="{x + bar_w / 2}" y="{y - 5}" text-anchor="middle" font-size="10">{hours:.2f}</text>')
    svg.append(f'<text x="{width / 2}" y="225" text-anchor="middle" font-size="11">{year}年每周阅读时长（小时）</text>')
    svg.append('</svg>')
    return "".join(svg)


def _notion_id(value: str) -> str:
    match = re.search(r"([a-f0-9]{32}|[a-f0-9-]{36})", value or "", re.I)
    if not match:
        raise ValueError("NOTION_PAGE 不是有效的 Notion 页面链接或 ID")
    return match.group(1)


def _text(value: str) -> list[dict[str, Any]]:
    return [{"type": "text", "text": {"content": value}}]


def update_notion(values: Mapping[date, int], year: int, heatmap_url: str, chart_url: str) -> None:
    from notion_client import Client

    token = os.getenv("NOTION_TOKEN", "").strip()
    parent_id = _notion_id(os.getenv("NOTION_PAGE", ""))
    notion = Client(auth=token, notion_version="2026-03-11")
    children = notion.blocks.children.list(block_id=parent_id).get("results", [])
    images = {
        (item.get("image") or {}).get("external", {}).get("url"): item
        for item in children
        if item.get("type") == "image"
    }
    for url, block in ((heatmap_url, images.get(heatmap_url)), (chart_url, images.get(chart_url))):
        if block:
            notion.blocks.update(block_id=block["id"], image={"type": "external", "external": {"url": url}})
    missing = []
    if not any("weread-" in str(url) and str(year) in str(url) for url in images):
        missing.extend([
            {"object": "block", "type": "heading_2", "heading_2": {"rich_text": _text("年度阅读")}},
            {"object": "block", "type": "image", "image": {"type": "external", "external": {"url": heatmap_url}}},
        ])
    if not any("reading-time-" in str(url) and str(year) in str(url) for url in images):
        missing.extend([
            {"object": "block", "type": "heading_2", "heading_2": {"rich_text": _text("阅读时长")}},
            {"object": "block", "type": "image", "image": {"type": "external", "external": {"url": chart_url}}},
        ])
    if missing:
        notion.blocks.children.append(block_id=parent_id, children=missing)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="同步年度阅读和阅读时长统计")
    parser.add_argument("--year", type=int, default=datetime.now(SHANGHAI).year)
    parser.add_argument("--skip-notion", action="store_true")
    args = parser.parse_args(argv)
    from .cli import WeReadGatewayClient

    api = WeReadGatewayClient(os.getenv("WEREAD_API_KEY"))
    values = collect_daily_read_times(api, args.year)
    OUT_FOLDER.mkdir(exist_ok=True)
    heatmap = OUT_FOLDER / f"weread-{args.year}.svg"
    chart = OUT_FOLDER / f"reading-time-{args.year}.svg"
    heatmap.write_text(render_heatmap(values, args.year), encoding="utf-8")
    chart.write_text(render_reading_time(values, args.year), encoding="utf-8")
    if not args.skip_notion:
        repo = os.getenv("GITHUB_REPOSITORY", "ryocobb/weread2notion")
        ref = os.getenv("GITHUB_REF_NAME", "main")
        base = f"https://raw.githubusercontent.com/{repo}/{ref}/OUT_FOLDER"
        update_notion(values, args.year, f"{base}/{heatmap.name}", f"{base}/{chart.name}")
    print(f"统计完成：{heatmap}，{chart}")
