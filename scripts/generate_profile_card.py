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


def build_smooth_path(points: list[tuple[float, float]]) -> str:
    if not points:
        return ""
    if len(points) == 1:
        x, y = points[0]
        return f"M {x:.1f} {y:.1f}"

    path = [f"M {points[0][0]:.1f} {points[0][1]:.1f}"]
    for index in range(1, len(points) - 1):
        current = points[index]
        nxt = points[index + 1]
        mid_x = (current[0] + nxt[0]) / 2
        mid_y = (current[1] + nxt[1]) / 2
        path.append(f"Q {current[0]:.1f} {current[1]:.1f} {mid_x:.1f} {mid_y:.1f}")
    path.append(
        f"Q {points[-1][0]:.1f} {points[-1][1]:.1f} {points[-1][0]:.1f} {points[-1][1]:.1f}"
    )
    return " ".join(path)


def render_svg(metrics: dict[str, Any], theme: str) -> str:
    palettes = {
        "light": {
            "bg": "#f8fafc",
            "panel": "#ffffff",
            "stroke": "#dbe2f1",
            "muted": "#64748b",
            "soft": "#edf2fb",
            "accent": "#6d5efc",
            "accent_soft": "#8b5cf6",
            "accent_alt": "#22d3ee",
            "ink": "#0f172a",
            "inverse": "#f8fafc",
            "orb_a": "#c4b5fd",
            "orb_b": "#7dd3fc",
            "line": "#94a3b8",
        },
        "dark": {
            "bg": "#08111f",
            "panel": "#0f1728",
            "stroke": "#203049",
            "muted": "#8da0bd",
            "soft": "#13203a",
            "accent": "#8b5cf6",
            "accent_soft": "#a78bfa",
            "accent_alt": "#22d3ee",
            "ink": "#e7eef9",
            "inverse": "#08111f",
            "orb_a": "#6d28d9",
            "orb_b": "#0284c7",
            "line": "#334155",
        },
    }
    c = palettes[theme]

    chart_values = metrics["monthly_contributions"]
    chart_max = max(chart_values) if max(chart_values) > 0 else 1
    chart_left = 688
    chart_width = 430
    chart_top = 174
    chart_base_y = 298
    chart_height = 108
    step = chart_width / (len(chart_values) - 1)
    points: list[tuple[float, float]] = []

    for index, value in enumerate(chart_values):
        normalized = value / chart_max
        x = chart_left + index * step
        y = chart_base_y - normalized * chart_height
        points.append((x, y))

    line_path = build_smooth_path(points)
    area_path = (
        f"{line_path} L {points[-1][0]:.1f} {chart_base_y:.1f} "
        f"L {points[0][0]:.1f} {chart_base_y:.1f} Z"
    )

    peak_index = max(range(len(chart_values)), key=lambda idx: chart_values[idx])
    latest_index = len(chart_values) - 1
    peak_point = points[peak_index]
    latest_point = points[latest_index]

    dot_markup = []
    for index, (x, y) in enumerate(points):
        radius = 5 if index in {peak_index, latest_index} else 3.5
        opacity = 0.96 if chart_values[index] > 0 else 0.34
        delay = round(index * 0.16, 2)
        dot_markup.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{radius}" fill="{c["panel"]}" stroke="{c["accent"]}" stroke-width="1.8" opacity="{opacity}">'
            f'<animate attributeName="opacity" values="{opacity};1;{opacity}" dur="5.4s" begin="{delay}s" repeatCount="indefinite"/></circle>'
        )

    label_markup = []
    for index in [0, 3, 6, 9, 11]:
        x, _ = points[index]
        label_markup.append(
            f'<text x="{x:.1f}" y="334" fill="{c["muted"]}" font-family="Inter, Helvetica Neue, Arial, sans-serif" '
            f'font-size="12" text-anchor="middle" letter-spacing="1.6">{metrics["month_labels"][index]}</text>'
        )

    cadence_summary = f"{metrics['active_months']} active months"
    last_active = svg_escape(metrics["last_active"])
    peak_month = svg_escape(metrics["peak_month"])

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="430" viewBox="0 0 1200 430" role="img" aria-labelledby="title desc">
  <title id="title">Adkid Zephyr profile motion card</title>
  <desc id="desc">Daily-updated AI PM and fintech profile card with a spacious Gemini-inspired layout and normalized activity curve.</desc>
  <defs>
    <linearGradient id="card-bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="{c["bg"]}"/>
      <stop offset="0.55" stop-color="{c["soft"]}"/>
      <stop offset="1" stop-color="{c["bg"]}"/>
    </linearGradient>
    <linearGradient id="area" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="{c["accent_soft"]}" stop-opacity="0.26"/>
      <stop offset="1" stop-color="{c["accent_alt"]}" stop-opacity="0.02"/>
    </linearGradient>
    <linearGradient id="line-gradient" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stop-color="{c["accent_soft"]}"/>
      <stop offset="0.54" stop-color="{c["accent"]}"/>
      <stop offset="1" stop-color="{c["accent_alt"]}"/>
    </linearGradient>
    <filter id="blur-orb" x="-30%" y="-30%" width="160%" height="160%">
      <feGaussianBlur stdDeviation="28"/>
    </filter>
    <style><![CDATA[
      .outline {{
        stroke: {c["stroke"]};
        stroke-width: 1;
        fill: none;
        vector-effect: non-scaling-stroke;
      }}
      .trace {{
        stroke: url(#line-gradient);
        stroke-width: 3;
        fill: none;
        stroke-linecap: round;
        stroke-linejoin: round;
      }}
      .float {{
        animation: float 8s ease-in-out infinite;
      }}
      .pulse {{
        animation: pulse 3.8s ease-in-out infinite;
      }}
      .glow {{
        animation: glow 7.2s ease-in-out infinite;
      }}
      @keyframes float {{
        0%, 100% {{ transform: translateY(0); opacity: 0.14; }}
        50% {{ transform: translateY(-12px); opacity: 0.28; }}
      }}
      @keyframes pulse {{
        0%, 100% {{ opacity: 0.45; transform: scale(1); }}
        50% {{ opacity: 1; transform: scale(1.18); }}
      }}
      @keyframes glow {{
        0%, 100% {{ opacity: 0.18; transform: translateX(0); }}
        50% {{ opacity: 0.32; transform: translateX(18px); }}
      }}
    ]]></style>
  </defs>

  <rect x="10" y="10" width="1180" height="410" rx="30" fill="url(#card-bg)"/>
  <rect x="10" y="10" width="1180" height="410" rx="30" class="outline"/>
  <circle cx="928" cy="154" r="116" fill="{c["orb_a"]}" opacity="0.2" filter="url(#blur-orb)" class="float"/>
  <circle cx="1004" cy="240" r="76" fill="{c["orb_b"]}" opacity="0.13" filter="url(#blur-orb)" class="glow"/>
  <rect x="52" y="54" width="420" height="300" rx="28" fill="{c["panel"]}" opacity="0.86" stroke="{c["stroke"]}" stroke-width="1"/>
  <rect x="650" y="54" width="500" height="300" rx="28" fill="{c["panel"]}" opacity="0.72" stroke="{c["stroke"]}" stroke-width="1"/>

  <g transform="translate(74 76)">
    <text x="0" y="0" fill="{c["muted"]}" font-family="Inter, Helvetica Neue, Arial, sans-serif" font-size="13" letter-spacing="4">CURRENT FOCUS</text>
    <text x="0" y="54" fill="{c["ink"]}" font-family="Inter, Helvetica Neue, Arial, sans-serif" font-size="44" font-weight="600">AI PM</text>
    <text x="0" y="98" fill="{c["ink"]}" font-family="Inter, Helvetica Neue, Arial, sans-serif" font-size="38" font-weight="500">for Fintech</text>
    <text x="0" y="132" fill="{c["muted"]}" font-family="Inter, Helvetica Neue, Arial, sans-serif" font-size="16">Cleaner decision flows, trust-aware experiences, and useful AI interfaces.</text>
    <rect x="0" y="162" width="156" height="78" rx="22" fill="{c["soft"]}" opacity="0.72" stroke="{c["stroke"]}" stroke-width="1"/>
    <text x="20" y="188" fill="{c["muted"]}" font-family="Inter, Helvetica Neue, Arial, sans-serif" font-size="12" letter-spacing="2.2">PUBLIC REPOS</text>
    <text x="20" y="224" fill="{c["ink"]}" font-family="Inter, Helvetica Neue, Arial, sans-serif" font-size="34" font-weight="600">{number_text(metrics["public_repos"])}</text>
    <rect x="176" y="162" width="156" height="78" rx="22" fill="{c["soft"]}" opacity="0.72" stroke="{c["stroke"]}" stroke-width="1"/>
    <text x="196" y="188" fill="{c["muted"]}" font-family="Inter, Helvetica Neue, Arial, sans-serif" font-size="12" letter-spacing="2.2">FOLLOWERS</text>
    <text x="196" y="224" fill="{c["ink"]}" font-family="Inter, Helvetica Neue, Arial, sans-serif" font-size="34" font-weight="600">{number_text(metrics["followers"])}</text>
    <text x="0" y="272" fill="{c["muted"]}" font-family="Inter, Helvetica Neue, Arial, sans-serif" font-size="13" letter-spacing="2">12M CONTRIBUTIONS  {number_text(metrics["total_contributions"])}</text>
    <text x="0" y="298" fill="{c["muted"]}" font-family="Inter, Helvetica Neue, Arial, sans-serif" font-size="13" letter-spacing="2">LAST ACTIVE  {last_active}</text>
    <g transform="translate(0 314)">
      <rect x="0" y="0" width="108" height="32" rx="16" fill="{c["ink"]}"/>
      <text x="27" y="21" fill="{c["inverse"]}" font-family="Inter, Helvetica Neue, Arial, sans-serif" font-size="12" letter-spacing="2">AI PM</text>
      <rect x="120" y="0" width="120" height="32" rx="16" fill="{c["panel"]}" stroke="{c["stroke"]}" stroke-width="1"/>
      <text x="150" y="21" fill="{c["muted"]}" font-family="Inter, Helvetica Neue, Arial, sans-serif" font-size="12" letter-spacing="1.8">FINTECH</text>
    </g>
  </g>

  <g transform="translate(688 78)">
    <text x="0" y="0" fill="{c["muted"]}" font-family="Inter, Helvetica Neue, Arial, sans-serif" font-size="13" letter-spacing="4">ACTIVITY CADENCE</text>
    <text x="0" y="44" fill="{c["ink"]}" font-family="Inter, Helvetica Neue, Arial, sans-serif" font-size="32" font-weight="500">Personal cadence</text>
    <text x="0" y="74" fill="{c["muted"]}" font-family="Inter, Helvetica Neue, Arial, sans-serif" font-size="15">A normalized monthly view, tuned to your own pace.</text>
    <text x="0" y="108" fill="{c["muted"]}" font-family="Inter, Helvetica Neue, Arial, sans-serif" font-size="13" letter-spacing="2">PEAK MONTH  {peak_month}</text>
    <text x="248" y="108" fill="{c["muted"]}" font-family="Inter, Helvetica Neue, Arial, sans-serif" font-size="13" letter-spacing="2">{cadence_summary.upper()}</text>
  </g>

  <g>
    <path d="{area_path}" fill="url(#area)"/>
    <path d="{line_path}" class="trace"/>
    {''.join(dot_markup)}
    {''.join(label_markup)}
    <line x1="{peak_point[0]:.1f}" y1="{peak_point[1]:.1f}" x2="{peak_point[0]:.1f}" y2="320" class="outline" opacity="0.24"/>
    <line x1="{latest_point[0]:.1f}" y1="{latest_point[1]:.1f}" x2="{latest_point[0]:.1f}" y2="320" class="outline" opacity="0.18"/>
    <g transform="translate({peak_point[0] - 38:.1f} {peak_point[1] - 52:.1f})">
      <rect x="0" y="0" width="96" height="32" rx="16" fill="{c["panel"]}" stroke="{c["stroke"]}" stroke-width="1"/>
      <text x="18" y="21" fill="{c["muted"]}" font-family="Inter, Helvetica Neue, Arial, sans-serif" font-size="12" letter-spacing="1.8">PEAK</text>
    </g>
    <g transform="translate({latest_point[0] - 54:.1f} {latest_point[1] + 20:.1f})">
      <rect x="0" y="0" width="132" height="32" rx="16" fill="{c["panel"]}" stroke="{c["stroke"]}" stroke-width="1"/>
      <text x="18" y="21" fill="{c["muted"]}" font-family="Inter, Helvetica Neue, Arial, sans-serif" font-size="12" letter-spacing="1.4">UPDATED {metrics["generated_on"]}</text>
    </g>
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
