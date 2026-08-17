#!/usr/bin/env python3
"""Regenerate public profile metrics and authored upstream-merge cards."""

from __future__ import annotations

import html
import json
import os
import re
import urllib.parse
import urllib.request
from pathlib import Path


USERNAME = "Adkid-Zephyr"
ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
MATRIX_CARD = ROOT / "assets" / "matrix-card.svg"
CONTRIBUTIONS_DIR = ROOT / "assets" / "contributions"
START = "<!-- OSS-CONTRIBUTIONS:START -->"
END = "<!-- OSS-CONTRIBUTIONS:END -->"

HIGHLIGHTS = {
    "https://github.com/openclaw/openclaw/pull/122684": {
        "badge": "P1 · MERGED CODE",
        "status": "MERGED / UPSTREAM MAIN",
        "title": "CLI image hydration for agent workspaces",
        "contribution": "Authored fix · regression coverage · upstream main",
        "attribution": "PR by Adkid-Zephyr · verified authored commit",
        "alt": (
            "Merged code contribution by Adkid-Zephyr to openclaw/openclaw: "
            "P1 PR #122684 with an authored commit merged into upstream main"
        ),
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


def public_repositories() -> list[dict[str, object]]:
    repositories: list[dict[str, object]] = []
    page = 1
    while True:
        result = github_get(
            f"https://api.github.com/users/{USERNAME}/repos"
            f"?per_page=100&type=owner&sort=updated&page={page}"
        )
        if not isinstance(result, list):
            break
        batch = [repo for repo in result if isinstance(repo, dict)]
        repositories.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return repositories


def merged_upstream_prs() -> list[dict[str, object]]:
    # This authored-and-merged PR query is the sole source of UPSTREAM MERGES.
    query = urllib.parse.quote(f"is:pr is:merged author:{USERNAME}")
    result = github_get(
        f"https://api.github.com/search/issues?q={query}"
        "&per_page=100&sort=updated&order=desc"
    )
    if not isinstance(result, dict):
        return []

    repo_cache: dict[str, dict[str, object]] = {}
    contributions: list[dict[str, object]] = []
    for item in result.get("items", []):
        if not isinstance(item, dict) or not isinstance(item.get("repository_url"), str):
            continue
        repo_url = str(item["repository_url"])
        full_name = repo_url.removeprefix("https://api.github.com/repos/")
        if full_name.split("/", 1)[0].casefold() == USERNAME.casefold():
            continue
        if full_name not in repo_cache:
            repository = github_get(repo_url)
            if isinstance(repository, dict):
                repo_cache[full_name] = repository
        if full_name in repo_cache:
            contributions.append({"pr": item, "repo": repo_cache[full_name]})

    contributions.sort(
        key=lambda item: (
            str(item["pr"].get("closed_at") or ""),
            str(item["repo"].get("full_name") or ""),
            int(item["pr"].get("number") or 0),
        ),
        reverse=True,
    )
    return contributions


def replace_svg_text(svg: str, element_id: str, value: int) -> str:
    pattern = rf'(<text id="{re.escape(element_id)}"[^>]*>)[^<]*(</text>)'
    updated, replacements = re.subn(pattern, rf"\g<1>{value:,}\g<2>", svg)
    if replacements != 1:
        raise RuntimeError(f"Expected one {element_id} element, found {replacements}")
    return updated


def update_matrix_card(
    repositories: list[dict[str, object]], contributions: list[dict[str, object]]
) -> None:
    original = [repo for repo in repositories if not repo.get("fork")]
    stars = sum(int(repo.get("stargazers_count") or 0) for repo in original)
    svg = MATRIX_CARD.read_text(encoding="utf-8")
    svg = replace_svg_text(svg, "original-repos-value", len(original))
    svg = replace_svg_text(svg, "stars-earned-value", stars)
    svg = replace_svg_text(svg, "upstream-merges-value", len(contributions))
    MATRIX_CARD.write_text(svg, encoding="utf-8")


def contribution_card(contribution: dict[str, object]) -> tuple[str, str, str]:
    pr = contribution["pr"]
    repo = contribution["repo"]
    assert isinstance(pr, dict) and isinstance(repo, dict)

    full_name = str(repo["full_name"])
    number = int(pr["number"])
    url = str(pr["html_url"])
    highlight = HIGHLIGHTS.get(
        url,
        {
            "badge": "MERGED CODE",
            "status": "MERGED / UPSTREAM",
            "title": str(pr.get("title") or "Accepted contribution"),
            "contribution": "Authored change · reviewed · merged upstream",
            "attribution": f"PR by {USERNAME} · public proof linked",
            "alt": (
                f"Merged code contribution by {USERNAME} to {full_name}: "
                f"upstream PR #{number}"
            ),
        },
    )
    filename = f"{full_name.replace('/', '-')}-{number}.svg"
    svg = f'''<svg width="1200" height="210" viewBox="0 0 1200 210" fill="none" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1200" y2="210" gradientUnits="userSpaceOnUse"><stop stop-color="#020604"/><stop offset="0.62" stop-color="#06130B"/><stop offset="1" stop-color="#020604"/></linearGradient>
    <pattern id="scanlines" width="4" height="4" patternUnits="userSpaceOnUse"><path d="M0 3.5H4" stroke="#89FFB6" stroke-opacity="0.035"/></pattern>
  </defs>
  <rect x="1" y="1" width="1198" height="208" rx="14" fill="url(#bg)" stroke="#00FF66" stroke-opacity="0.34" stroke-width="2"/>
  <path d="M28 43H1172" stroke="#113821"/><circle cx="30" cy="22" r="4" fill="#00FF66"/>
  <text x="44" y="27" fill="#73FFAA" font-family="ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace" font-size="12">gh://{esc(full_name)}/pull/{number}</text>
  <rect x="986" y="10" width="186" height="25" rx="12.5" fill="#00FF66" fill-opacity="0.08" stroke="#00FF66" stroke-opacity="0.38"/>
  <text x="1079" y="27" fill="#73FFAA" font-family="ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace" font-size="11" font-weight="700" text-anchor="middle">{esc(highlight['badge'])}</text>
  <text x="30" y="76" fill="#00FF66" font-family="ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace" font-size="12" font-weight="700" letter-spacing="1">{esc(highlight['status'])}</text>
  <text x="30" y="111" fill="#E8FFF0" font-family="ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace" font-size="25" font-weight="750">{esc(highlight['title'])}</text>
  <text x="30" y="146" fill="#88A993" font-family="ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace" font-size="14">{esc(highlight['contribution'])}</text>
  <text x="30" y="177" fill="#4F8A64" font-family="ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace" font-size="12">{esc(highlight['attribution'])}</text>
  <path d="M820 61V184" stroke="#00FF66" stroke-opacity="0.2"/>
  <text x="850" y="78" fill="#3D8157" font-family="ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace" font-size="10">REPOSITORY</text>
  <text x="850" y="101" fill="#B8F7CD" font-family="ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace" font-size="14" font-weight="700">{esc(full_name)}</text>
  <text x="850" y="132" fill="#3D8157" font-family="ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace" font-size="10">PUBLIC PROOF</text>
  <text x="850" y="155" fill="#E8FFF0" font-family="ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace" font-size="13">PR #{number}</text>
  <text x="850" y="181" fill="#00FF66" font-family="ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace" font-size="11" font-weight="700">AUTHORED CODE ✓</text>
  <rect x="1" y="1" width="1198" height="208" rx="14" fill="url(#scanlines)"/>
</svg>
'''
    return filename, svg, str(highlight["alt"])


def update_generated_contributions(contributions: list[dict[str, object]]) -> None:
    CONTRIBUTIONS_DIR.mkdir(parents=True, exist_ok=True)
    cards: list[str] = []
    for contribution in contributions:
        filename, svg, alt = contribution_card(contribution)
        (CONTRIBUTIONS_DIR / filename).write_text(svg, encoding="utf-8")
        pr = contribution["pr"]
        assert isinstance(pr, dict)
        cards.append(
            f'<a href="{esc(pr["html_url"])}"><img '
            f'src="./assets/contributions/{esc(filename)}" width="100%" '
            f'alt="{esc(alt)}" /></a>'
        )

    readme = README.read_text(encoding="utf-8")
    replacement = f"{START}\n" + ("\n\n".join(cards) or "_No authored upstream merges yet._") + f"\n{END}"
    updated, replacements = re.subn(
        rf"{re.escape(START)}.*?{re.escape(END)}",
        replacement,
        readme,
        flags=re.DOTALL,
    )
    if replacements != 1:
        raise RuntimeError("README contribution markers are missing or duplicated")
    README.write_text(updated, encoding="utf-8")


def main() -> None:
    repositories = public_repositories()
    contributions = merged_upstream_prs()
    update_matrix_card(repositories, contributions)
    update_generated_contributions(contributions)


if __name__ == "__main__":
    main()
