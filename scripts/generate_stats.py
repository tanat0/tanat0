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

    repos: list = []
    page = 1
    while True:
        batch = _rest(token, "/user/repos", {
            "affiliation": "owner", "per_page": 100,
            "page": page, "sort": "updated",
        })
        if not isinstance(batch, list) or not batch:
            break
        repos.extend(batch)
        page += 1

    real = [r for r in repos if r["full_name"] != skip and not r.get("fork")]
    public  = sum(1 for r in real if not r["private"])
    private = sum(1 for r in real if r["private"])

    languages: Dict[str, int] = {}
    for repo in real:
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
    username: str,
    total_commits: int,
    member_since: str,
    public_repos: int,
    private_repos: int,
    languages: Dict[str, int],
    theme: Theme,
) -> str:
    W = 495
    t = theme
    total_repos = public_repos + private_repos

    top_langs = sorted(languages.items(), key=lambda x: -x[1])[:5]
    total_bytes = sum(v for _, v in top_langs) or 1

    # ── language bar ────────────────────────────────────────────────────────
    BAR_X0, BAR_Y, BAR_W, BAR_H = 20, 158, 455, 6
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
        ly = 174 + (i // 3) * 14
        legend += (
            f'<circle cx="{lx+4}" cy="{ly+4}" r="3.5" fill="{color}"/>'
            f'<text x="{lx+13}" y="{ly+8}" fill="{t.dim}" font-size="10.5" '
            f'font-family="ui-monospace,\'Cascadia Code\',monospace">'
            f'{lang} <tspan fill="{t.text}" font-weight="500">{pct}</tspan></text>'
        )

    H = 205 if len(top_langs) > 3 else 192

    return f"""<svg width="{W}" height="{H}" viewBox="0 0 {W} {H}"
     xmlns="http://www.w3.org/2000/svg">
  <defs>
    <pattern id="dots" x="0" y="0" width="20" height="20" patternUnits="userSpaceOnUse">
      <circle cx="1.5" cy="1.5" r="1" fill="{t.dot_color}" opacity="{t.dot_opacity}"/>
    </pattern>
    <linearGradient id="sep" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%"   stop-color="{t.accent}" stop-opacity="0"/>
      <stop offset="30%"  stop-color="{t.accent}" stop-opacity="1"/>
      <stop offset="70%"  stop-color="{t.accent}" stop-opacity="1"/>
      <stop offset="100%" stop-color="{t.accent}" stop-opacity="0"/>
    </linearGradient>
    <linearGradient id="div" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%"   stop-color="{t.border}" stop-opacity="0"/>
      <stop offset="20%"  stop-color="{t.border}" stop-opacity="1"/>
      <stop offset="80%"  stop-color="{t.border}" stop-opacity="1"/>
      <stop offset="100%" stop-color="{t.border}" stop-opacity="0"/>
    </linearGradient>
  </defs>

  <rect width="{W}" height="{H}" rx="8" fill="{t.bg}"/>
  <rect width="{W}" height="{H}" rx="8" fill="url(#dots)"/>
  <rect width="{W}" height="{H}" rx="8" fill="none" stroke="{t.border}" stroke-width="1"/>

  <!-- header -->
  <text x="20" y="30" fill="{t.text}" font-size="15" font-weight="600"
        font-family="-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif"
        >{username}</text>
  <rect x="366" y="15" width="109" height="20" rx="10"
        fill="{t.accent_bg}" stroke="{t.accent}" stroke-width="0.8" stroke-opacity="0.4"/>
  <text x="420" y="29" fill="{t.accent}" font-size="10" font-weight="500"
        text-anchor="middle"
        font-family="-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif"
        >Data Engineer</text>

  <rect x="20" y="42" width="455" height="1" fill="url(#sep)"/>

  <!-- commits -->
  <text x="88" y="80" fill="{t.accent}" font-size="24" font-weight="700"
        font-family="ui-monospace,'Cascadia Code',monospace"
        text-anchor="middle">{_fmt(total_commits)}</text>
  <text x="88" y="97" fill="{t.dim}" font-size="11" text-anchor="middle"
        font-family="-apple-system,sans-serif">commits</text>
  <text x="88" y="111" fill="{t.dim}" font-size="9" text-anchor="middle"
        font-family="-apple-system,sans-serif" opacity="0.65">public + private</text>

  <line x1="188" y1="52" x2="188" y2="120" stroke="{t.border}" stroke-width="1"/>

  <!-- repos -->
  <text x="248" y="80" fill="{t.text}" font-size="24" font-weight="700"
        font-family="ui-monospace,'Cascadia Code',monospace"
        text-anchor="middle">{total_repos}</text>
  <text x="248" y="97" fill="{t.dim}" font-size="11" text-anchor="middle"
        font-family="-apple-system,sans-serif">repositories</text>
  <text x="248" y="111" fill="{t.dim}" font-size="9" text-anchor="middle"
        font-family="-apple-system,sans-serif" opacity="0.65">{public_repos} pub · {private_repos} priv</text>

  <line x1="308" y1="52" x2="308" y2="120" stroke="{t.border}" stroke-width="1"/>

  <!-- member since -->
  <text x="402" y="80" fill="{t.text}" font-size="24" font-weight="700"
        font-family="ui-monospace,'Cascadia Code',monospace"
        text-anchor="middle">{member_since}</text>
  <text x="402" y="97" fill="{t.dim}" font-size="11" text-anchor="middle"
        font-family="-apple-system,sans-serif">member since</text>

  <!-- languages -->
  <rect x="20" y="128" width="455" height="1" fill="url(#div)"/>
  <text x="20" y="145" fill="{t.dim}" font-size="9.5" letter-spacing="1"
        font-family="-apple-system,sans-serif">LANGUAGES</text>
  <text x="475" y="145" fill="{t.dim}" font-size="9" text-anchor="end"
        font-family="-apple-system,sans-serif" opacity="0.6">all repos incl. private</text>

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
    commits, member_since = fetch_commit_stats(token, username)
    print(f"  Commits:  {commits}  (since {member_since})")

    public, private, languages = fetch_repo_and_lang_stats(token, username)
    print(f"  Repos:    {public} public + {private} private (profile repo excluded)")
    total_b = sum(v for _, v in sorted(languages.items(), key=lambda x: -x[1])[:5]) or 1
    for lang, nb in sorted(languages.items(), key=lambda x: -x[1])[:5]:
        print(f"    {lang}: {nb/total_b*100:.1f}%")

    args = (username, commits, member_since, public, private, languages)

    dark_svg  = generate_svg(*args, theme=DARK)
    light_svg = generate_svg(*args, theme=LIGHT)

    for path, content in [
        ("github-stats-dark.svg",  dark_svg),
        ("github-stats-light.svg", light_svg),
    ]:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"Saved → {path}")


if __name__ == "__main__":
    main()
