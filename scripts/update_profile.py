#!/usr/bin/env python3
"""Regenerate Adkid Zephyr's profile cards from public GitHub data."""

from __future__ import annotations

import html
import json
import os
import re
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path


USERNAME = "Adkid-Zephyr"
ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
START = "<!-- OSS-CONTRIBUTIONS:START -->"
END = "<!-- OSS-CONTRIBUTIONS:END -->"

PROJECTS = {
    "Financial-research-agent-QBT": {
        "file": "financial-research-agent.svg",
        "index": "01",
        "title": "Financial Research Agent",
        "lines": ["Multi-agent futures research", "and report-review pipeline."],
        "tag": "AGENT PIPELINE",
        "accent": "#5EEAD4",
    },
    "OpenManager": {
        "file": "openmanager.svg",
        "index": "02",
        "title": "OpenManager",
        "lines": ["Local-first project workspace", "manager built for OpenClaw."],
        "tag": "LOCAL FIRST",
        "accent": "#60A5FA",
    },
    "anti-defensive-writing": {
        "file": "anti-defensive-writing.svg",
        "index": "03",
        "title": "Anti-defensive Writing",
        "lines": ["Bilingual skill + prompt pack", "for clearer academic writing."],
        "tag": "AI SKILL",
        "accent": "#A78BFA",
    },
    "Monte_Carlo_Princing_Engine": {
        "file": "monte-carlo-engine.svg",
        "index": "04",
        "title": "Monte Carlo Engine",
        "lines": ["Snowball autocallable pricing", "with PV and Delta in under 1s."],
        "tag": "QUANT",
        "accent": "#F472B6",
    },
}

HIGHLIGHTS = {
    "https://github.com/openclaw/openclaw/pull/122684": {
        "eyebrow": "P1 · USER-FACING BUG · SECURITY BOUNDARY",
        "title": "CLI image hydration for agent workspaces",
        "lines": [
            "Fixed an authorization defect that rejected image requests from non-default agents",
            "before they reached the CLI model. Added regression coverage and real-path proof.",
        ],
    }
}


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def github_get(url: str) -> object:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": f"{USERNAME}-profile-readme",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def merged_upstream_prs() -> list[dict[str, object]]:
    query = urllib.parse.quote(f"is:pr is:merged author:{USERNAME}")
    result = github_get(
        f"https://api.github.com/search/issues?q={query}&per_page=100&sort=updated&order=desc"
    )
    if not isinstance(result, dict):
        return []

    contributions: list[dict[str, object]] = []
    repo_cache: dict[str, dict[str, object]] = {}
    for item in result.get("items", []):
        if not isinstance(item, dict) or not isinstance(item.get("repository_url"), str):
            continue
        repo_url = str(item["repository_url"])
        full_name = repo_url.removeprefix("https://api.github.com/repos/")
        if full_name.split("/", 1)[0].casefold() == USERNAME.casefold():
            continue
        if full_name not in repo_cache:
            repo = github_get(repo_url)
            if isinstance(repo, dict):
                repo_cache[full_name] = repo
        if full_name in repo_cache:
            contributions.append({"pr": item, "repo": repo_cache[full_name]})
    return contributions


def public_repositories() -> list[dict[str, object]]:
    result = github_get(
        f"https://api.github.com/users/{USERNAME}/repos?per_page=100&type=owner&sort=updated"
    )
    return [repo for repo in result if isinstance(repo, dict)] if isinstance(result, list) else []


def project_card(repo: dict[str, object], spec: dict[str, object]) -> str:
    accent = esc(spec["accent"])
    language = esc(repo.get("language") or "MULTI")
    stars = int(repo.get("stargazers_count") or 0)
    lines = spec["lines"]
    return f'''<svg width="570" height="220" viewBox="0 0 570 220" fill="none" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="570" y2="220" gradientUnits="userSpaceOnUse"><stop stop-color="#070B13"/><stop offset="1" stop-color="#0D1020"/></linearGradient>
    <radialGradient id="glow" cx="0" cy="0" r="1" gradientUnits="userSpaceOnUse" gradientTransform="translate(510 20) rotate(130) scale(230 180)"><stop stop-color="{accent}" stop-opacity="0.17"/><stop offset="1" stop-color="{accent}" stop-opacity="0"/></radialGradient>
    <pattern id="grid" width="24" height="24" patternUnits="userSpaceOnUse"><path d="M24 0H0V24" fill="none" stroke="#94A3B8" stroke-opacity="0.035"/></pattern>
  </defs>
  <rect x="1" y="1" width="568" height="218" rx="16" fill="url(#bg)"/>
  <rect x="1" y="1" width="568" height="218" rx="16" fill="url(#grid)"/>
  <rect x="1" y="1" width="568" height="218" rx="16" fill="url(#glow)"/>
  <rect x="1" y="1" width="568" height="218" rx="16" stroke="{accent}" stroke-opacity="0.42" stroke-width="2"/>
  <path d="M1 47H569" stroke="#1E293B"/>
  <circle cx="22" cy="24" r="4" fill="{accent}"/><text x="36" y="29" fill="#64748B" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" font-size="12">~/builds/{esc(repo['name'])}</text>
  <text x="525" y="33" fill="{accent}" fill-opacity="0.3" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" font-size="27" font-weight="800">{esc(spec['index'])}</text>
  <text x="24" y="88" fill="#F8FAFC" font-family="Inter, ui-sans-serif, system-ui, sans-serif" font-size="23" font-weight="750">{esc(spec['title'])}</text>
  <text x="24" y="121" fill="#94A3B8" font-family="Inter, ui-sans-serif, system-ui, sans-serif" font-size="14">{esc(lines[0])}</text>
  <text x="24" y="143" fill="#94A3B8" font-family="Inter, ui-sans-serif, system-ui, sans-serif" font-size="14">{esc(lines[1])}</text>
  <rect x="24" y="171" width="112" height="26" rx="13" fill="{accent}" fill-opacity="0.1" stroke="{accent}" stroke-opacity="0.35"/>
  <text x="80" y="188" fill="{accent}" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" font-size="11" font-weight="700" text-anchor="middle">{esc(spec['tag'])}</text>
  <text x="370" y="189" fill="#64748B" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" font-size="12">{language}</text>
  <path d="M451 180.5L455 181.1L457 177L459 181.1L463 180.5L460 183.5L461 188L457 185.8L453 188L454 183.5L451 180.5Z" fill="{accent}"/>
  <text x="469" y="189" fill="#CBD5E1" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" font-size="12">{stars} STARS</text>
</svg>
'''


def contribution_card(contribution: dict[str, object]) -> tuple[str, str]:
    pr = contribution["pr"]
    repo = contribution["repo"]
    assert isinstance(pr, dict) and isinstance(repo, dict)
    full_name = str(repo["full_name"])
    number = int(pr["number"])
    url = str(pr["html_url"])
    highlight = HIGHLIGHTS.get(
        url,
        {
            "eyebrow": "MERGED UPSTREAM",
            "title": str(pr.get("title") or "Accepted contribution"),
            "lines": ["Reviewed and merged into the project's default branch.", "Public proof is linked from this card."],
        },
    )
    filename = f"{full_name.replace('/', '-')}-{number}.svg"
    stars = int(repo.get("stargazers_count") or 0)
    language = str(repo.get("language") or "MULTI")
    lines = highlight["lines"]
    svg = f'''<svg width="1200" height="290" viewBox="0 0 1200 290" fill="none" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1200" y2="290" gradientUnits="userSpaceOnUse"><stop stop-color="#060A12"/><stop offset="0.58" stop-color="#0A1020"/><stop offset="1" stop-color="#150B23"/></linearGradient>
    <linearGradient id="edge" x1="12" y1="0" x2="1178" y2="290" gradientUnits="userSpaceOnUse"><stop stop-color="#5EEAD4"/><stop offset="0.55" stop-color="#60A5FA"/><stop offset="1" stop-color="#F472B6"/></linearGradient>
    <pattern id="grid" width="28" height="28" patternUnits="userSpaceOnUse"><path d="M28 0H0V28" fill="none" stroke="#94A3B8" stroke-opacity="0.04"/></pattern>
  </defs>
  <rect x="1" y="1" width="1198" height="288" rx="17" fill="url(#bg)"/><rect x="1" y="1" width="1198" height="288" rx="17" fill="url(#grid)"/><rect x="1" y="1" width="1198" height="288" rx="17" stroke="url(#edge)" stroke-opacity="0.55" stroke-width="2"/>
  <path d="M1 52H1199" stroke="#263244"/><circle cx="25" cy="26" r="4" fill="#5EEAD4"/><text x="39" y="31" fill="#64748B" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" font-size="13">gh://{esc(full_name)}/pull/{number}</text>
  <rect x="1012" y="14" width="164" height="26" rx="13" fill="#5EEAD4" fill-opacity="0.1" stroke="#5EEAD4" stroke-opacity="0.4"/><circle cx="1032" cy="27" r="4" fill="#5EEAD4"/><text x="1044" y="32" fill="#A7F3D0" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" font-size="12" font-weight="700">MERGED / MAIN</text>
  <text x="34" y="92" fill="#F472B6" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" font-size="13" font-weight="700" letter-spacing="1.2">{esc(highlight['eyebrow'])}</text>
  <text x="34" y="137" fill="#F8FAFC" font-family="Inter, ui-sans-serif, system-ui, sans-serif" font-size="30" font-weight="760">{esc(highlight['title'])}</text>
  <text x="34" y="177" fill="#94A3B8" font-family="Inter, ui-sans-serif, system-ui, sans-serif" font-size="16">{esc(lines[0])}</text><text x="34" y="202" fill="#94A3B8" font-family="Inter, ui-sans-serif, system-ui, sans-serif" font-size="16">{esc(lines[1])}</text>
  <rect x="34" y="231" width="152" height="30" rx="15" fill="#A78BFA" fill-opacity="0.1" stroke="#A78BFA" stroke-opacity="0.38"/><text x="110" y="251" fill="#C4B5FD" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" font-size="12" font-weight="700" text-anchor="middle">PR #{number} · VERIFIED</text>
  <text x="886" y="94" fill="#475569" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" font-size="12">UPSTREAM REPOSITORY</text><text x="886" y="126" fill="#E2E8F0" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" font-size="17" font-weight="700">{esc(full_name)}</text>
  <text x="886" y="171" fill="#64748B" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" font-size="13">★  {stars:,} STARS</text><text x="886" y="201" fill="#64748B" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" font-size="13">◈  {esc(language.upper())}</text><text x="886" y="239" fill="#5EEAD4" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" font-size="13">OPEN PUBLIC PROOF →</text>
</svg>
'''
    return filename, svg


def telemetry(profile: dict[str, object], repos: list[dict[str, object]], contributions: list[dict[str, object]]) -> str:
    owned = [repo for repo in repos if not repo.get("fork")]
    stars = sum(int(repo.get("stargazers_count") or 0) for repo in owned)
    followers = int(profile.get("followers") or 0)
    languages = Counter(str(repo["language"]) for repo in owned if repo.get("language"))
    aliases = {"TypeScript": "TS", "JavaScript": "JS", "Jupyter Notebook": "JUPYTER"}
    runtime = " · ".join(aliases.get(language, language.upper()) for language, _ in languages.most_common(3)) or "MULTI"
    metrics = [
        ("PUBLIC REPOS", len(repos), "#5EEAD4"),
        ("OWNED STARS", stars, "#60A5FA"),
        ("FOLLOWERS", followers, "#A78BFA"),
        ("UPSTREAM MERGES", len(contributions), "#F472B6"),
    ]
    cards = []
    for index, (label, value, color) in enumerate(metrics):
        x = 28 + index * 287
        cards.append(f'''<rect x="{x}" y="77" width="263" height="112" rx="13" fill="#0A0F1B" stroke="{color}" stroke-opacity="0.34"/><text x="{x + 19}" y="108" fill="#64748B" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" font-size="11" letter-spacing="1.1">{label}</text><text x="{x + 19}" y="158" fill="{color}" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" font-size="35" font-weight="800">{value:,}</text><path d="M{x + 188} 153H{x + 205}L{x + 216} 136L{x + 230} 146L{x + 245} 121" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" opacity="0.55"/>''')
    return f'''<svg width="1200" height="250" viewBox="0 0 1200 250" fill="none" xmlns="http://www.w3.org/2000/svg">
  <defs><linearGradient id="bg" x1="0" y1="0" x2="1200" y2="250" gradientUnits="userSpaceOnUse"><stop stop-color="#060A12"/><stop offset="1" stop-color="#0E0B19"/></linearGradient><pattern id="grid" width="25" height="25" patternUnits="userSpaceOnUse"><path d="M25 0H0V25" fill="none" stroke="#94A3B8" stroke-opacity="0.035"/></pattern></defs>
  <rect x="1" y="1" width="1198" height="248" rx="17" fill="url(#bg)"/><rect x="1" y="1" width="1198" height="248" rx="17" fill="url(#grid)"/><rect x="1" y="1" width="1198" height="248" rx="17" stroke="#334155" stroke-width="2"/>
  <circle cx="27" cy="27" r="5" fill="#5EEAD4"/><circle cx="27" cy="27" r="10" fill="#5EEAD4" fill-opacity="0.12"/><text x="47" y="32" fill="#CBD5E1" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" font-size="13" font-weight="700" letter-spacing="1">LIVE TELEMETRY</text><text x="1172" y="32" fill="#475569" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" font-size="12" text-anchor="end">STACK · {esc(runtime)}</text><path d="M1 55H1199" stroke="#1E293B"/>
  {''.join(cards)}
  <text x="28" y="224" fill="#475569" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" font-size="11">SOURCE: GITHUB PUBLIC API</text><text x="1172" y="224" fill="#5EEAD4" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" font-size="11" text-anchor="end">AUTO-SYNC / 24H</text>
</svg>
'''


def main() -> None:
    profile = github_get(f"https://api.github.com/users/{USERNAME}")
    if not isinstance(profile, dict):
        raise RuntimeError("Could not load GitHub profile")
    repos = public_repositories()
    contributions = merged_upstream_prs()

    projects_dir = ROOT / "assets" / "projects"
    contributions_dir = ROOT / "assets" / "contributions"
    projects_dir.mkdir(parents=True, exist_ok=True)
    contributions_dir.mkdir(parents=True, exist_ok=True)

    repo_by_name = {str(repo.get("name")): repo for repo in repos}
    for name, spec in PROJECTS.items():
        repo = repo_by_name.get(name)
        if repo:
            (projects_dir / str(spec["file"])).write_text(project_card(repo, spec), encoding="utf-8")

    cards = []
    for contribution in contributions:
        filename, svg = contribution_card(contribution)
        (contributions_dir / filename).write_text(svg, encoding="utf-8")
        pr = contribution["pr"]
        repo = contribution["repo"]
        assert isinstance(pr, dict) and isinstance(repo, dict)
        cards.append(
            f'<a href="{esc(pr["html_url"])}"><img src="./assets/contributions/{filename}" '
            f'width="100%" alt="Merged contribution to {esc(repo["full_name"])}: PR #{pr["number"]}" /></a>'
        )

    readme = README.read_text(encoding="utf-8")
    replacement = f"{START}\n" + ("\n\n".join(cards) or "_More upstream signal coming soon._") + f"\n{END}"
    updated, count = re.subn(rf"{re.escape(START)}.*?{re.escape(END)}", replacement, readme, flags=re.DOTALL)
    if count != 1:
        raise RuntimeError("README contribution markers are missing or duplicated")
    README.write_text(updated, encoding="utf-8")
    (ROOT / "assets" / "telemetry.svg").write_text(telemetry(profile, repos, contributions), encoding="utf-8")


if __name__ == "__main__":
    main()
