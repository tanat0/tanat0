#!/usr/bin/env python3
"""
GitHub Stats SVG generator — private repo aware, dual-theme.

Outputs two files:
  github-stats-dark.svg   — Linear dark (indigo accent)
  github-stats-light.svg  — GitHub light (blue accent)

Required env:
  GH_PAT        Personal Access Token with `repo` scope
  GH_USER       GitHub username   (default: tanat0)

The profile repo (<username>/<username>) is excluded from all stats.
"""
from __future__ import annotations

import os
import sys
from typing import Dict, List, NamedTuple, Tuple

import requests

GQL_URL  = "https://api.github.com/graphql"
REST_URL = "https://api.github.com"

LANG_COLORS: Dict[str, str] = {
    "Python":     "#3572A5",
    "JavaScript": "#F1E05A",
    "TypeScript": "#3178C6",
    "SQL":        "#E38C00",
    "Shell":      "#89E051",
    "Bash":       "#89E051",
    "Go":         "#00ADD8",
    "Rust":       "#DEA584",
    "Java":       "#B07219",
    "Scala":      "#DC322F",
    "YAML":       "#CB171E",
    "HCL":        "#844FBA",
    "Dockerfile": "#384D54",
    "Makefile":   "#427819",
    "HTML":       "#E34C26",
    "CSS":        "#563D7C",
    "Kotlin":     "#A97BFF",
    "Groovy":     "#E69F56",
}


class Theme(NamedTuple):
    bg:         str
    border:     str
    text:       str
    dim:        str
    accent:     str
    accent_bg:  str
    dot_color:  str
    dot_opacity: str


DARK = Theme(
    bg          = "#0F0F12",
    border      = "#1C1C28",
    text        = "#E2E8F0",
    dim         = "#64748B",
    accent      = "#6366F1",
    accent_bg   = "rgba(99,102,241,0.10)",
    dot_color   = "#27273A",
    dot_opacity = "0.6",
)

LIGHT = Theme(
    bg          = "#FFFFFF",
    border      = "#D0D7DE",
    text        = "#1F2328",
    dim         = "#57606A",
    accent      = "#0969DA",
    accent_bg   = "rgba(9,105,218,0.08)",
    dot_color   = "#C8D2DC",
    dot_opacity = "0.5",
)


# ── API ───────────────────────────────────────────────────────────────────────

def _gql(token: str, query: str, variables: dict | None = None) -> dict:
    r = requests.post(
        GQL_URL,
        json={"query": query, "variables": variables or {}},
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    if "errors" in data:
        raise RuntimeError(f"GraphQL error: {data['errors']}")
    return data["data"]


def _rest(token: str, path: str, params: dict | None = None) -> list | dict:
    r = requests.get(
        f"{REST_URL}{path}",
        headers={"Authorization": f"token {token}",
                 "Accept": "application/vnd.github.v3+json"},
        params=params or {},
        timeout=20,
    )
    r.raise_for_status()
    return r.json()


# ── Data fetching ─────────────────────────────────────────────────────────────

def fetch_commit_stats(token: str, username: str) -> Tuple[int, str]:
    meta = _gql(token, """
        query($login: String!) {
          user(login: $login) {
            createdAt
            contributionsCollection { contributionYears }
          }
        }""", {"login": username})

    years: List[int] = meta["user"]["contributionsCollection"]["contributionYears"]
    member_since: str = meta["user"]["createdAt"][:4]

    year_q = """
        query($login: String!, $from: DateTime!, $to: DateTime!) {
          user(login: $login) {
            contributionsCollection(from: $from, to: $to) {
              totalCommitContributions
              restrictedContributionsCount
            }
          }
        }"""
    total = 0
    for year in years:
        d = _gql(token, year_q, {
            "login": username,
            "from": f"{year}-01-01T00:00:00Z",
            "to":   f"{year}-12-31T23:59:59Z",
        })
        cc = d["user"]["contributionsCollection"]
        total += cc["totalCommitContributions"] + cc["restrictedContributionsCount"]

    return total, member_since


def fetch_repo_and_lang_stats(
    token: str, username: str
) -> Tuple[int, int, Dict[str, int]]:
    skip = f"{username}/{username}"   # exclude profile repo

    # Personal repos (for counts + lang stats)
    personal: list = []
    page = 1
    while True:
        batch = _rest(token, "/user/repos", {
            "affiliation": "owner", "per_page": 100,
            "page": page, "sort": "updated",
        })
        if not isinstance(batch, list) or not batch:
            break
        personal.extend(batch)
        page += 1

    # repo counts: non-fork personal repos only
    owned = [r for r in personal
             if r["full_name"] != skip and not r.get("fork")]
    public  = sum(1 for r in owned if not r["private"])
    private = sum(1 for r in owned if r["private"])

    # language stats: all personal repos incl. forks (homework, study projects)
    lang_repos = [r for r in personal if r["full_name"] != skip]
    print(f"  Repos for lang stats: {len(owned)} owned + {len(lang_repos) - len(owned)} forks")

    languages: Dict[str, int] = {}
    for repo in lang_repos:
        try:
            ld = _rest(token, f"/repos/{repo['full_name']}/languages")
            if isinstance(ld, dict):
                for lang, nb in ld.items():
                    languages[lang] = languages.get(lang, 0) + nb
        except Exception:
            pass

    return public, private, languages


# ── SVG ───────────────────────────────────────────────────────────────────────

def _fmt(n: int) -> str:
    return f"{n:,}".replace(",", " ")   # thin-space thousands separator


def generate_svg(
    languages: Dict[str, int],
    theme: Theme,
) -> str:
    W = 495
    t = theme

    top_langs = sorted(languages.items(), key=lambda x: -x[1])[:6]
    total_bytes = sum(v for _, v in top_langs) or 1

    # ── language bar ────────────────────────────────────────────────────────
    BAR_X0, BAR_Y, BAR_W, BAR_H = 20, 28, 455, 6
    bar_segs, bx = "", BAR_X0
    for i, (lang, nb) in enumerate(top_langs):
        sw    = max(int(nb / total_bytes * BAR_W), 2)
        color = LANG_COLORS.get(lang, t.dim)
        rx    = 3 if i in (0, len(top_langs) - 1) else 0
        bar_segs += (
            f'<rect x="{bx}" y="{BAR_Y}" width="{sw}" height="{BAR_H}" '
            f'rx="{rx}" fill="{color}"/>'
        )
        bx += sw

    # ── legend ───────────────────────────────────────────────────────────────
    legend = ""
    for i, (lang, nb) in enumerate(top_langs):
        pct   = f"{nb / total_bytes * 100:.0f}%"
        color = LANG_COLORS.get(lang, t.dim)
        lx = 20 + (i % 3) * 155
        ly = 44 + (i // 3) * 16
        legend += (
            f'<circle cx="{lx+4}" cy="{ly+4}" r="3.5" fill="{color}"/>'
            f'<text x="{lx+13}" y="{ly+8}" fill="{t.dim}" font-size="10.5" '
            f'font-family="ui-monospace,\'Cascadia Code\',monospace">'
            f'{lang} <tspan fill="{t.text}" font-weight="500">{pct}</tspan></text>'
        )

    rows = (len(top_langs) + 2) // 3
    H = 44 + rows * 16 + 8

    return f"""<svg width="{W}" height="{H}" viewBox="0 0 {W} {H}"
     xmlns="http://www.w3.org/2000/svg">
  <defs>
    <pattern id="dots" x="0" y="0" width="20" height="20" patternUnits="userSpaceOnUse">
      <circle cx="1.5" cy="1.5" r="1" fill="{t.dot_color}" opacity="{t.dot_opacity}"/>
    </pattern>
  </defs>

  <rect width="{W}" height="{H}" rx="8" fill="{t.bg}"/>
  <rect width="{W}" height="{H}" rx="8" fill="url(#dots)"/>
  <rect width="{W}" height="{H}" rx="8" fill="none" stroke="{t.border}" stroke-width="1"/>

  <text x="20" y="16" fill="{t.dim}" font-size="9.5" letter-spacing="1"
        font-family="-apple-system,sans-serif">LANGUAGES</text>
  <text x="475" y="16" fill="{t.dim}" font-size="9" text-anchor="end"
        font-family="-apple-system,sans-serif" opacity="0.6">incl. private repos</text>

  {bar_segs}
  {legend}
</svg>"""


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    token = os.environ.get("GH_PAT") or os.environ.get("GITHUB_TOKEN", "")
    if not token:
        print("ERROR: GH_PAT env var is required", file=sys.stderr)
        sys.exit(1)

    username = os.environ.get("GH_USER", "tanat0")

    print(f"Fetching stats for {username} …")
    public, private, languages = fetch_repo_and_lang_stats(token, username)
    print(f"  Repos:    {public} public + {private} private")
    total_b = sum(languages.values()) or 1
    print(f"  All languages ({len(languages)}):")
    for lang, nb in sorted(languages.items(), key=lambda x: -x[1]):
        print(f"    {lang}: {nb/total_b*100:.2f}%")

    dark_svg  = generate_svg(languages, theme=DARK)
    light_svg = generate_svg(languages, theme=LIGHT)

    for path, content in [
        ("github-stats-dark.svg",  dark_svg),
        ("github-stats-light.svg", light_svg),
    ]:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"Saved → {path}")


if __name__ == "__main__":
    main()
