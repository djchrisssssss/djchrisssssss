#!/usr/bin/env python3

from __future__ import annotations

import datetime as dt
import html
import json
import os
import ssl
import urllib.error
import urllib.request
from pathlib import Path

import certifi


API_ROOT = "https://api.github.com"
USERNAME = os.getenv("PROFILE_USERNAME", "djchrisssssss")
TOKEN = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN") or ""
ROOT = Path(__file__).resolve().parent.parent
ASSETS_DIR = ROOT / "assets"
SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())

THEMES = {
    "dark": {
        "bg": "#1a1b27",
        "card": "#1f2335",
        "stroke": "#2f334d",
        "text": "#c0caf5",
        "muted": "#8f9bcc",
        "accent": "#7aa2f7",
        "accent_2": "#bb9af7",
        "accent_3": "#73daca",
        "accent_4": "#f7768e",
    },
    "light": {
        "bg": "#f7f9fc",
        "card": "#ffffff",
        "stroke": "#d8deeb",
        "text": "#24283b",
        "muted": "#5a6178",
        "accent": "#3451b2",
        "accent_2": "#7c3aed",
        "accent_3": "#0f9d58",
        "accent_4": "#d93025",
    },
}

LANGUAGE_COLORS = [
    "#7aa2f7",
    "#bb9af7",
    "#73daca",
    "#e0af68",
    "#f7768e",
    "#7dcfff",
]


def request_json(url: str):
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": f"{USERNAME}-profile-stats-generator",
    }
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"

    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30, context=SSL_CONTEXT) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        details = error.read().decode("utf-8", "replace")
        raise RuntimeError(f"GitHub API request failed for {url}: {error.code} {details}") from error


def fetch_profile(username: str) -> dict:
    return request_json(f"{API_ROOT}/users/{username}")


def fetch_repositories(username: str) -> list[dict]:
    repositories: list[dict] = []
    page = 1

    while True:
        batch = request_json(
            f"{API_ROOT}/users/{username}/repos?per_page=100&type=owner&sort=updated&page={page}"
        )
        if not batch:
            break
        repositories.extend(batch)
        page += 1

    return repositories


def aggregate_languages(repositories: list[dict]) -> dict[str, int]:
    totals: dict[str, int] = {}

    for repository in repositories:
        if repository.get("fork"):
            continue
        data = request_json(repository["languages_url"])
        for language, byte_count in data.items():
            totals[language] = totals.get(language, 0) + int(byte_count)

    return dict(sorted(totals.items(), key=lambda item: item[1], reverse=True))


def format_number(value: int) -> str:
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if value >= 1_000:
        return f"{value / 1_000:.1f}K"
    return str(value)


def escape(text: str) -> str:
    return html.escape(text, quote=True)


def render_stats_card(theme_name: str, profile: dict, repositories: list[dict]) -> str:
    theme = THEMES[theme_name]
    owned_repositories = [repo for repo in repositories if not repo.get("fork")]
    total_stars = sum(int(repo.get("stargazers_count", 0)) for repo in owned_repositories)
    total_forks = sum(int(repo.get("forks_count", 0)) for repo in owned_repositories)
    last_refresh = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    stats = [
        ("Public repos", int(profile.get("public_repos", 0))),
        ("Followers", int(profile.get("followers", 0))),
        ("Following", int(profile.get("following", 0))),
        ("Total stars", total_stars),
    ]

    boxes = []
    box_positions = [(24, 72), (258, 72), (24, 128), (258, 128)]
    for (label, value), (x, y) in zip(stats, box_positions):
        boxes.append(
            f"""
  <g transform="translate({x} {y})">
    <rect width="213" height="48" rx="14" fill="{theme["card"]}" stroke="{theme["stroke"]}"/>
    <text x="16" y="20" fill="{theme["muted"]}" font-size="12" font-weight="600">{escape(label)}</text>
    <text x="16" y="36" fill="{theme["text"]}" font-size="22" font-weight="700">{escape(format_number(value))}</text>
  </g>"""
        )

    description = (
        f"{USERNAME} profile summary with {profile.get('public_repos', 0)} public repositories, "
        f"{profile.get('followers', 0)} followers, {profile.get('following', 0)} following, "
        f"{total_stars} total stars, and {total_forks} forks."
    )

    return f"""<svg width="495" height="210" viewBox="0 0 495 210" fill="none" xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="stats-title-{theme_name} stats-desc-{theme_name}">
  <title id="stats-title-{theme_name}">GitHub Stats</title>
  <desc id="stats-desc-{theme_name}">{escape(description)}</desc>
  <rect width="495" height="210" rx="20" fill="{theme["bg"]}"/>
  <rect x="0.5" y="0.5" width="494" height="209" rx="19.5" stroke="{theme["stroke"]}"/>
  <text x="24" y="36" fill="{theme["text"]}" font-size="22" font-weight="700">GitHub Stats</text>
  <text x="24" y="56" fill="{theme["muted"]}" font-size="12">Generated from the GitHub API</text>
  <text x="471" y="36" text-anchor="end" fill="{theme["accent"]}" font-size="14" font-weight="700">@{escape(USERNAME)}</text>
  {''.join(boxes)}
  <text x="24" y="198" fill="{theme["muted"]}" font-size="12">Forks across owned repos: {escape(format_number(total_forks))}</text>
  <text x="471" y="198" text-anchor="end" fill="{theme["muted"]}" font-size="12">Updated {escape(last_refresh)}</text>
</svg>
"""


def render_languages_card(theme_name: str, repositories: list[dict], language_totals: dict[str, int]) -> str:
    theme = THEMES[theme_name]
    owned_repositories = [repo for repo in repositories if not repo.get("fork")]
    total_bytes = sum(language_totals.values())
    top_languages = list(language_totals.items())[:6]

    rows = []
    start_y = 76
    row_gap = 19
    bar_x = 158
    bar_width = 250

    for index, (language, byte_count) in enumerate(top_languages):
        y = start_y + index * row_gap
        percentage = (byte_count / total_bytes * 100) if total_bytes else 0
        fill_width = max(8, round(bar_width * (percentage / 100))) if percentage else 0
        color = LANGUAGE_COLORS[index % len(LANGUAGE_COLORS)]
        rows.append(
            f"""
  <rect x="{bar_x}" y="{y - 10}" width="{bar_width}" height="8" rx="4" fill="{theme["card"]}" stroke="{theme["stroke"]}"/>
  <rect x="{bar_x}" y="{y - 10}" width="{fill_width}" height="8" rx="4" fill="{color}"/>
  <text x="24" y="{y}" fill="{theme["text"]}" font-size="13" font-weight="600">{escape(language)}</text>
  <text x="471" y="{y}" text-anchor="end" fill="{theme["muted"]}" font-size="12">{percentage:.1f}%</text>
"""
        )

    if not rows:
        rows.append(
            f'<text x="24" y="92" fill="{theme["muted"]}" font-size="13">No public language data available yet.</text>'
        )

    description = "Top languages by byte size across public, non-fork repositories."

    return f"""<svg width="495" height="210" viewBox="0 0 495 210" fill="none" xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="langs-title-{theme_name} langs-desc-{theme_name}">
  <title id="langs-title-{theme_name}">Top Languages</title>
  <desc id="langs-desc-{theme_name}">{escape(description)}</desc>
  <rect width="495" height="210" rx="20" fill="{theme["bg"]}"/>
  <rect x="0.5" y="0.5" width="494" height="209" rx="19.5" stroke="{theme["stroke"]}"/>
  <text x="24" y="36" fill="{theme["text"]}" font-size="22" font-weight="700">Top Languages</text>
  <text x="24" y="56" fill="{theme["muted"]}" font-size="12">Public, non-fork repositories only</text>
  <text x="471" y="36" text-anchor="end" fill="{theme["accent_2"]}" font-size="14" font-weight="700">{escape(str(len(owned_repositories)))} repos</text>
  {''.join(rows)}
  <text x="24" y="198" fill="{theme["muted"]}" font-size="12">Measured by GitHub language bytes</text>
  <text x="471" y="198" text-anchor="end" fill="{theme["muted"]}" font-size="12">{escape(format_number(total_bytes))} bytes</text>
</svg>
"""


def main() -> None:
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)

    profile = fetch_profile(USERNAME)
    repositories = fetch_repositories(USERNAME)
    language_totals = aggregate_languages(repositories)

    (ASSETS_DIR / "github-stats-dark.svg").write_text(
        render_stats_card("dark", profile, repositories),
        encoding="utf-8",
    )
    (ASSETS_DIR / "github-stats-light.svg").write_text(
        render_stats_card("light", profile, repositories),
        encoding="utf-8",
    )
    (ASSETS_DIR / "top-langs-dark.svg").write_text(
        render_languages_card("dark", repositories, language_totals),
        encoding="utf-8",
    )
    (ASSETS_DIR / "top-langs-light.svg").write_text(
        render_languages_card("light", repositories, language_totals),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
