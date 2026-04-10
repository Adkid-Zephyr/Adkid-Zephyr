#!/usr/bin/env python3

from __future__ import annotations

import json
import os
import re
import subprocess
from collections import OrderedDict
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


GRAPHQL_QUERY = """
query($login: String!) {
  user(login: $login) {
    followers {
      totalCount
    }
    repositories(privacy: PUBLIC, ownerAffiliations: OWNER) {
      totalCount
    }
    contributionsCollection {
      contributionCalendar {
        totalContributions
        weeks {
          contributionDays {
            date
            contributionCount
          }
        }
      }
    }
  }
}
"""


def api_request(url: str, *, token: str | None = None, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "adkid-profile-card-generator",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    body = None
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = Request(url, data=body, headers=headers)

    try:
        with urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except URLError as error:
        return json.loads(curl_fetch(url, token=token, payload=payload, accept=headers["Accept"], cause=error))


def fetch_text(url: str, *, token: str | None = None, accept: str = "text/html") -> str:
    headers = {
        "Accept": accept,
        "User-Agent": "adkid-profile-card-generator",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    request = Request(url, headers=headers)
    try:
        with urlopen(request, timeout=20) as response:
            return response.read().decode("utf-8")
    except URLError as error:
        return curl_fetch(url, token=token, accept=accept, cause=error)


def curl_fetch(
    url: str,
    *,
    token: str | None = None,
    payload: dict[str, Any] | None = None,
    accept: str = "application/json",
    cause: Exception | None = None,
) -> str:
    command = [
        "curl",
        "-fsSL",
        "--connect-timeout",
        "10",
        "--max-time",
        "20",
        "-H",
        f"Accept: {accept}",
        "-H",
        "User-Agent: adkid-profile-card-generator",
    ]
    if token:
        command.extend(["-H", f"Authorization: Bearer {token}"])
    if payload is not None:
        command.extend(["-H", "Content-Type: application/json", "-d", json.dumps(payload)])
    command.append(url)

    result = subprocess.run(command, check=False, capture_output=True, text=True)
    if result.returncode != 0:
        detail = result.stderr.strip() or str(cause or "curl request failed")
        raise URLError(detail)
    return result.stdout


def fetch_profile(username: str, token: str | None) -> dict[str, Any]:
    user_data = api_request(f"https://api.github.com/users/{username}", token=token)

    try:
        graph = api_request(
            "https://api.github.com/graphql",
            token=token,
            payload={"query": GRAPHQL_QUERY, "variables": {"login": username}},
        )
    except (HTTPError, URLError):
        graph = {"data": {"user": None}}

    if graph.get("errors"):
        graph = {"data": {"user": None}}

    event_items = api_request(
        f"https://api.github.com/users/{username}/events/public?per_page=100",
        token=token,
    )

    user_graph = graph.get("data", {}).get("user") or {}
    calendar = user_graph.get("contributionsCollection", {}).get("contributionCalendar", {})
    weeks = calendar.get("weeks") or []

    if not weeks:
        weeks = scrape_public_contributions(username)
    if not weeks and not token:
        weeks = build_preview_weeks()

    total_contributions = int(calendar.get("totalContributions") or 0)
    if not total_contributions and weeks:
        total_contributions = sum(
            int(item.get("contributionCount", 0))
            for week in weeks
            for item in week.get("contributionDays", [])
        )

    return {
        "followers": int(user_graph.get("followers", {}).get("totalCount") or user_data.get("followers") or 0),
        "public_repos": int(user_graph.get("repositories", {}).get("totalCount") or user_data.get("public_repos") or 0),
        "total_contributions": total_contributions,
        "weeks": weeks,
        "events": event_items if isinstance(event_items, list) else [],
    }


def scrape_public_contributions(username: str) -> list[dict[str, Any]]:
    today = datetime.now(UTC).date()
    start = today - timedelta(days=365)
    try:
        html = fetch_text(
            f"https://github.com/users/{username}/contributions?from={start.isoformat()}&to={today.isoformat()}",
            accept="text/html",
        )
    except (HTTPError, URLError):
        return []

    matches = re.findall(r'data-date="(\d{4}-\d{2}-\d{2})" data-level="\d" data-count="(\d+)"', html)
    if not matches:
        return []

    weeks: list[dict[str, Any]] = []
    current_week: list[dict[str, Any]] = []
    for raw_date, raw_count in matches:
        current_week.append({"date": raw_date, "contributionCount": int(raw_count)})
        if len(current_week) == 7:
            weeks.append({"contributionDays": current_week})
            current_week = []

    if current_week:
        weeks.append({"contributionDays": current_week})

    return weeks


def build_preview_weeks() -> list[dict[str, Any]]:
    today = datetime.now(UTC).date()
    monthly_seed = [0, 1, 2, 1, 0, 3, 2, 4, 1, 2, 3, 2]
    items: list[tuple[date, int]] = []

    for offset, seed in enumerate(monthly_seed):
        anchor = date(today.year, today.month, 1)
        for _ in range(11 - offset):
            previous_last = anchor - timedelta(days=1)
            anchor = date(previous_last.year, previous_last.month, 1)
        for step in range(seed):
            items.append((anchor + timedelta(days=min(step * 4, 24)), 1))

    items.sort(key=lambda pair: pair[0])
    weeks: list[dict[str, Any]] = []
    current_week: list[dict[str, Any]] = []
    for day, count in items:
        current_week.append({"date": day.isoformat(), "contributionCount": count})
        if len(current_week) == 7:
            weeks.append({"contributionDays": current_week})
            current_week = []

    if current_week:
        weeks.append({"contributionDays": current_week})

    return weeks


def build_metrics(profile: dict[str, Any]) -> dict[str, Any]:
    today = datetime.now(UTC).date()
    month_buckets: "OrderedDict[str, int]" = OrderedDict()
    month_cursor = date(today.year, today.month, 1)

    for _ in range(12):
        key = month_cursor.strftime("%Y-%m")
        month_buckets[key] = 0
        previous_last = month_cursor - timedelta(days=1)
        month_cursor = date(previous_last.year, previous_last.month, 1)

    month_buckets = OrderedDict(reversed(list(month_buckets.items())))

    all_days: list[tuple[date, int]] = []
    for week in profile["weeks"]:
        for item in week.get("contributionDays", []):
            day = datetime.strptime(item["date"], "%Y-%m-%d").date()
            count = int(item.get("contributionCount", 0))
            all_days.append((day, count))
            bucket = day.strftime("%Y-%m")
            if bucket in month_buckets:
                month_buckets[bucket] += count

    recent_events_30d = 0
    cutoff = datetime.now(UTC) - timedelta(days=30)
    for event in profile["events"]:
        try:
            created = datetime.strptime(event["created_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
        except (KeyError, ValueError):
            continue
        if created >= cutoff:
            recent_events_30d += 1

    active_days = [day for day, count in all_days if count > 0]
    last_active = max(active_days).strftime("%Y.%m.%d") if active_days else "No public log yet"

    max_month = max(month_buckets.items(), key=lambda item: item[1], default=("", 0))
    peak_month = (
        datetime.strptime(max_month[0], "%Y-%m").strftime("%b %Y").upper()
        if max_month[0]
        else "N/A"
    )
    active_months = sum(1 for value in month_buckets.values() if value > 0)

    return {
        "followers": profile["followers"],
        "public_repos": profile["public_repos"],
        "total_contributions": profile["total_contributions"],
        "recent_events_30d": recent_events_30d,
        "last_active": last_active,
        "active_months": active_months,
        "peak_month": peak_month,
        "monthly_contributions": list(month_buckets.values()),
        "month_labels": [datetime.strptime(key, "%Y-%m").strftime("%b").upper() for key in month_buckets],
        "generated_on": datetime.now(UTC).strftime("%Y.%m.%d"),
    }


def number_text(value: int) -> str:
    return f"{value:,}"


def svg_escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def render_svg(metrics: dict[str, Any], theme: str) -> str:
    palettes = {
        "light": {
            "bg": "#F5F0E7",
            "panel": "#FBF8F1",
            "stroke": "#161616",
            "muted": "#6B6257",
            "soft": "#D4C8B5",
            "accent": "#887A67",
            "ink": "#121212",
            "inverse": "#FBF8F1",
            "bar": "#171717",
            "bar_soft": "#C5B59A",
        },
        "dark": {
            "bg": "#111111",
            "panel": "#171717",
            "stroke": "#E8DECF",
            "muted": "#C0B5A4",
            "soft": "#5C554D",
            "accent": "#D6C5A0",
            "ink": "#F5EFE5",
            "inverse": "#111111",
            "bar": "#F1E7D8",
            "bar_soft": "#6B6257",
        },
    }
    c = palettes[theme]

    chart_values = metrics["monthly_contributions"]
    chart_max = max(chart_values) if max(chart_values) > 0 else 1
    bar_width = 34
    bar_gap = 16
    chart_left = 706
    base_y = 302
    usable_height = 126
    bars = []
    labels = []

    for index, value in enumerate(chart_values):
        normalized = value / chart_max
        height = 12 if value == 0 else int(usable_height * (0.28 + normalized * 0.72))
        x = chart_left + index * (bar_width + bar_gap)
        y = base_y - height
        opacity = 0.24 if value == 0 else 0.92
        delay = round(index * 0.18, 2)
        bars.append(
            f'<rect x="{x}" y="{y}" width="{bar_width}" height="{height}" rx="17" '
            f'fill="{c["bar"]}" opacity="{opacity}">'
            f'<animate attributeName="opacity" values="{opacity};1;{opacity}" dur="5.6s" '
            f'begin="{delay}s" repeatCount="indefinite"/></rect>'
        )
        labels.append(
            f'<text x="{x + bar_width / 2}" y="330" fill="{c["muted"]}" '
            f'font-family="Helvetica Neue, Arial, sans-serif" font-size="12" text-anchor="middle" '
            f'letter-spacing="1.4">{metrics["month_labels"][index]}</text>'
        )

    line_points = []
    for index, value in enumerate(chart_values):
        normalized = value / chart_max
        y = 286 - normalized * 96
        x = chart_left + index * (bar_width + bar_gap) + bar_width / 2
        line_points.append(f"{x},{y}")

    chart_polyline = " ".join(line_points)
    last_x = chart_left + (len(chart_values) - 1) * (bar_width + bar_gap) + bar_width / 2
    last_y = 286 - (chart_values[-1] / chart_max) * 96

    stats = [
        ("PUBLIC REPOS", number_text(metrics["public_repos"])),
        ("FOLLOWERS", number_text(metrics["followers"])),
        ("12M CONTRIBUTIONS", number_text(metrics["total_contributions"])),
        ("PEAK MONTH", svg_escape(metrics["peak_month"])),
    ]

    stat_blocks = []
    stat_positions = [(74, 176), (320, 176), (74, 254), (320, 254)]
    for (label, value), (x, y) in zip(stats, stat_positions):
        stat_blocks.append(
            f'<g transform="translate({x} {y})">'
            f'<rect x="0" y="0" width="214" height="64" rx="18" fill="{c["panel"]}" stroke="{c["soft"]}" stroke-width="1.1"/>'
            f'<text x="18" y="24" fill="{c["muted"]}" font-family="Helvetica Neue, Arial, sans-serif" font-size="12" letter-spacing="2.4">{label}</text>'
            f'<text x="18" y="49" fill="{c["ink"]}" font-family="Georgia, Times New Roman, serif" font-size="26">{value}</text>'
            f'</g>'
        )

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="430" viewBox="0 0 1200 430" role="img" aria-labelledby="title desc">
  <title id="title">Adkid Zephyr profile motion card</title>
  <desc id="desc">Daily-updated AI PM and fintech profile card with GitHub profile metrics and a normalized monthly rhythm chart.</desc>
  <defs>
    <style><![CDATA[
      .outline {{
        stroke: {c["stroke"]};
        stroke-width: 1.15;
        fill: none;
        vector-effect: non-scaling-stroke;
      }}
      .scan {{
        animation: scan 8s ease-in-out infinite;
      }}
      .pulse {{
        animation: pulse 3.8s ease-in-out infinite;
      }}
      @keyframes scan {{
        0%, 100% {{ transform: translateX(0); opacity: 0.06; }}
        50% {{ transform: translateX(34px); opacity: 0.18; }}
      }}
      @keyframes pulse {{
        0%, 100% {{ opacity: 0.45; transform: scale(1); }}
        50% {{ opacity: 1; transform: scale(1.18); }}
      }}
    ]]></style>
  </defs>

  <rect x="10" y="10" width="1180" height="410" rx="28" fill="{c["bg"]}"/>
  <rect x="10" y="10" width="1180" height="410" rx="28" class="outline"/>
  <rect x="34" y="34" width="1132" height="362" rx="22" fill="{c["panel"]}" stroke="{c["soft"]}" stroke-width="1.1"/>

  <line x1="590" y1="76" x2="590" y2="350" class="outline" opacity="0.22"/>
  <line x1="74" y1="84" x2="522" y2="84" class="outline" opacity="0.64"/>
  <line x1="706" y1="84" x2="1086" y2="84" class="outline" opacity="0.54"/>
  <rect x="864" y="110" width="170" height="170" rx="85" fill="{c["bar"]}" opacity="0.04" class="scan"/>

  <g transform="translate(74 76)">
    <text x="0" y="0" fill="{c["muted"]}" font-family="Helvetica Neue, Arial, sans-serif" font-size="14" letter-spacing="4">CURRENT MOTION</text>
    <text x="0" y="64" fill="{c["ink"]}" font-family="Georgia, Times New Roman, serif" font-size="48">AI PM / Fintech</text>
    <text x="0" y="100" fill="{c["muted"]}" font-family="Helvetica Neue, Arial, sans-serif" font-size="18">Minimal signal, daily updated, calibrated to your own pace.</text>
  </g>

  {''.join(stat_blocks)}

  <g transform="translate(706 76)">
    <text x="0" y="0" fill="{c["muted"]}" font-family="Helvetica Neue, Arial, sans-serif" font-size="14" letter-spacing="4">RHYTHM LEDGER</text>
    <text x="0" y="44" fill="{c["ink"]}" font-family="Georgia, Times New Roman, serif" font-size="36">Relative monthly rhythm</text>
    <text x="0" y="74" fill="{c["muted"]}" font-family="Helvetica Neue, Arial, sans-serif" font-size="16">Normalized to your strongest month so sparse activity still reads as design, not absence.</text>
    <text x="0" y="108" fill="{c["muted"]}" font-family="Helvetica Neue, Arial, sans-serif" font-size="14" letter-spacing="2.6">ACTIVE MONTHS</text>
    <text x="0" y="138" fill="{c["ink"]}" font-family="Georgia, Times New Roman, serif" font-size="28">{metrics["active_months"]} / 12</text>
    <text x="166" y="108" fill="{c["muted"]}" font-family="Helvetica Neue, Arial, sans-serif" font-size="14" letter-spacing="2.6">LAST ACTIVE</text>
    <text x="166" y="138" fill="{c["ink"]}" font-family="Georgia, Times New Roman, serif" font-size="28">{svg_escape(metrics["last_active"])}</text>
    <text x="0" y="370" fill="{c["muted"]}" font-family="Helvetica Neue, Arial, sans-serif" font-size="13" letter-spacing="2.4">UPDATED {metrics["generated_on"]}</text>
    <text x="230" y="370" fill="{c["muted"]}" font-family="Helvetica Neue, Arial, sans-serif" font-size="13" letter-spacing="2.4">PUBLIC EVENTS / 30D {metrics["recent_events_30d"]}</text>
  </g>

  <g opacity="0.92">
    <polyline points="{chart_polyline}" fill="none" stroke="{c["bar_soft"]}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>
    {''.join(bars)}
    {''.join(labels)}
    <circle cx="{last_x}" cy="{last_y}" r="6" fill="{c["accent"]}" class="pulse"/>
    <line x1="{last_x}" y1="{last_y}" x2="{last_x}" y2="314" class="outline" opacity="0.18"/>
  </g>

  <g transform="translate(74 344)">
    <rect x="0" y="0" width="112" height="32" rx="16" fill="{c["ink"]}"/>
    <text x="28" y="21" fill="{c["inverse"]}" font-family="Helvetica Neue, Arial, sans-serif" font-size="13" letter-spacing="2">AI PM</text>
    <rect x="126" y="0" width="118" height="32" rx="16" fill="none" stroke="{c["stroke"]}" stroke-width="1.1"/>
    <text x="153" y="21" fill="{c["ink"]}" font-family="Helvetica Neue, Arial, sans-serif" font-size="13" letter-spacing="2">FINTECH</text>
    <rect x="258" y="0" width="180" height="32" rx="16" fill="none" stroke="{c["soft"]}" stroke-width="1.1"/>
    <text x="286" y="21" fill="{c["muted"]}" font-family="Helvetica Neue, Arial, sans-serif" font-size="13" letter-spacing="1.5">PRODUCT SYSTEMS</text>
  </g>
</svg>
"""


def main() -> None:
    username = os.getenv("PROFILE_USERNAME", "Adkid-Zephyr")
    token = os.getenv("GITHUB_TOKEN")
    output_dir = Path(os.getenv("PROFILE_DIST", "dist"))
    output_dir.mkdir(parents=True, exist_ok=True)

    profile = fetch_profile(username, token)
    metrics = build_metrics(profile)

    (output_dir / "profile-motion-card.svg").write_text(render_svg(metrics, "light"), encoding="utf-8")
    (output_dir / "profile-motion-card-dark.svg").write_text(render_svg(metrics, "dark"), encoding="utf-8")


if __name__ == "__main__":
    main()
