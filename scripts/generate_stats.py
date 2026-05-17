#!/usr/bin/env python3
"""
GitHub Stats SVG generator — private repo aware.

Reads ALL repos (public + private) via PAT, queries the contribution calendar
via GraphQL (includes private commits), and generates a self-contained SVG.

Required env:
  GH_PAT      Personal Access Token with `repo` scope
  GH_USER     GitHub username          (default: tanat0)
  OUTPUT_PATH Output SVG file path     (default: github-stats.svg)
"""
from __future__ import annotations

import os
import sys
from typing import Dict, List, Tuple

import requests

GQL_URL = "https://api.github.com/graphql"
REST_URL = "https://api.github.com"

# Standard GitHub language colours
LANG_COLORS: Dict[str, str] = {
    "Python":     "#3572A5",
    "JavaScript": "#F1E05A",
    "TypeScript": "#3178C6",
    "SQL":        "#e38c00",
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
    "Groovy":     "#E69F56",
    "Kotlin":     "#A97BFF",
}


# ── API helpers ───────────────────────────────────────────────────────────────

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
        headers={"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"},
        params=params or {},
        timeout=20,
    )
    r.raise_for_status()
    return r.json()


# ── Data fetching ─────────────────────────────────────────────────────────────

def fetch_commit_stats(token: str, username: str) -> Tuple[int, str]:
    """
    Total commit count (public + private) across all contribution years.
    Uses `totalCommitContributions + restrictedContributionsCount` per year
    — the same method as github-readme-stats with count_private=true.
    Returns (total_commits, member_since_year).
    """
    # Step 1: get the list of contribution years and profile creation date
    years_q = """
    query($login: String!) {
      user(login: $login) {
        createdAt
        contributionsCollection { contributionYears }
      }
    }"""
    meta = _gql(token, years_q, {"login": username})
    years: List[int] = meta["user"]["contributionsCollection"]["contributionYears"]
    member_since: str = meta["user"]["createdAt"][:4]

    # Step 2: sum commits across every year
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


def fetch_repo_and_lang_stats(token: str) -> Tuple[int, int, Dict[str, int]]:
    """
    Returns (public_count, private_count, {lang: bytes}) across all owned repos.
    Forks are excluded from language counts (they inflate numbers).
    """
    repos = []
    page = 1
    while True:
        batch = _rest(token, "/user/repos", {
            "affiliation": "owner",
            "per_page": 100,
            "page": page,
            "sort": "updated",
        })
        if not isinstance(batch, list) or not batch:
            break
        repos.extend(batch)
        page += 1

    public  = sum(1 for r in repos if not r["private"])
    private = sum(1 for r in repos if r["private"])

    languages: Dict[str, int] = {}
    for repo in repos:
        if repo.get("fork"):
            continue
        try:
            lang_data = _rest(token, f"/repos/{repo['full_name']}/languages")
            if isinstance(lang_data, dict):
                for lang, nbytes in lang_data.items():
                    languages[lang] = languages.get(lang, 0) + nbytes
        except Exception:
            pass   # skip repos where languages endpoint fails

    return public, private, languages


# ── SVG generation ───────────────────────────────────────────────────────────

def _fmt(n: int) -> str:
    """Format large numbers with thin-space thousands separator."""
    return f"{n:,}".replace(",", " ")


def generate_svg(
    username: str,
    total_commits: int,
    member_since: str,
    public_repos: int,
    private_repos: int,
    languages: Dict[str, int],
) -> str:
    W, H = 495, 195

    BG      = "#161B22"
    BORDER  = "#30363D"
    TEXT    = "#E6EDF3"
    DIM     = "#8B949E"
    ACCENT  = "#58A6FF"

    total_repos = public_repos + private_repos

    # ── Language bar ────────────────────────────────────────────────────────
    top_langs = sorted(languages.items(), key=lambda x: -x[1])[:6]
    total_bytes = sum(v for _, v in top_langs) or 1

    BAR_X0, BAR_Y, BAR_W, BAR_H = 20, 154, 455, 8
    bar_segments = ""
    x = BAR_X0
    for i, (lang, nbytes) in enumerate(top_langs):
        pct = nbytes / total_bytes
        seg_w = max(int(pct * BAR_W), 2)
        color = LANG_COLORS.get(lang, "#8B949E")
        # Round first and last corners
        if i == 0:
            bar_segments += f'<rect x="{x}" y="{BAR_Y}" width="{seg_w}" height="{BAR_H}" rx="4" ry="4" fill="{color}"/>'
        elif i == len(top_langs) - 1:
            bar_segments += f'<rect x="{x}" y="{BAR_Y}" width="{seg_w}" height="{BAR_H}" rx="4" ry="4" fill="{color}"/>'
        else:
            bar_segments += f'<rect x="{x}" y="{BAR_Y}" width="{seg_w}" height="{BAR_H}" fill="{color}"/>'
        x += seg_w

    # ── Language legend (two rows of 3) ─────────────────────────────────────
    legend = ""
    for i, (lang, nbytes) in enumerate(top_langs):
        pct_str = f"{nbytes / total_bytes * 100:.1f}%"
        color = LANG_COLORS.get(lang, "#8B949E")
        col = i % 3
        row = i // 3
        lx = 20 + col * 155
        ly = 176 + row * 14
        legend += (
            f'<circle cx="{lx + 5}" cy="{ly + 4}" r="4" fill="{color}"/>'
            f'<text x="{lx + 14}" y="{ly + 8}" fill="{DIM}" '
            f'font-size="11" font-family="monospace">{lang} {pct_str}</text>'
        )

    # Total SVG height: add second legend row if 4-6 langs
    actual_h = H + (14 if len(top_langs) > 3 else 0)

    return f"""<svg width="{W}" height="{actual_h}" viewBox="0 0 {W} {actual_h}"
     xmlns="http://www.w3.org/2000/svg">

  <rect width="{W}" height="{actual_h}" rx="6" fill="{BG}" stroke="{BORDER}" stroke-width="1"/>

  <!-- Title -->
  <text x="20" y="30" fill="{TEXT}"
        font-size="14" font-weight="600"
        font-family="-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif">
    GitHub Activity — {username}
  </text>
  <line x1="20" y1="40" x2="475" y2="40" stroke="{BORDER}" stroke-width="1"/>

  <!-- Commits -->
  <text x="20" y="65" fill="{DIM}" font-size="12"
        font-family="-apple-system,sans-serif">Total commits (public + private)</text>
  <text x="475" y="65" fill="{ACCENT}" font-size="16" font-weight="700"
        font-family="monospace" text-anchor="end">{_fmt(total_commits)}</text>

  <!-- Repos -->
  <text x="20" y="93" fill="{DIM}" font-size="12"
        font-family="-apple-system,sans-serif">Repositories</text>
  <text x="475" y="93" fill="{TEXT}" font-size="16" font-weight="700"
        font-family="monospace" text-anchor="end">{total_repos}</text>
  <text x="475" y="107" fill="{DIM}" font-size="10"
        font-family="monospace" text-anchor="end">{public_repos} public · {private_repos} private</text>

  <!-- Member since -->
  <text x="20" y="126" fill="{DIM}" font-size="12"
        font-family="-apple-system,sans-serif">On GitHub since</text>
  <text x="475" y="126" fill="{TEXT}" font-size="13"
        font-family="monospace" text-anchor="end">{member_since}</text>

  <!-- Languages divider + label -->
  <line x1="20" y1="137" x2="475" y2="137" stroke="{BORDER}" stroke-width="1"/>
  <text x="20" y="150" fill="{DIM}" font-size="11"
        font-family="-apple-system,sans-serif">Languages · all repos incl. private</text>

  <!-- Language bar -->
  {bar_segments}

  <!-- Language legend -->
  {legend}

</svg>"""


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    token = os.environ.get("GH_PAT") or os.environ.get("GITHUB_TOKEN", "")
    if not token:
        print("ERROR: GH_PAT (or GITHUB_TOKEN) env var is required", file=sys.stderr)
        sys.exit(1)

    username    = os.environ.get("GH_USER", "tanat0")
    output_path = os.environ.get("OUTPUT_PATH", "github-stats.svg")

    print(f"Fetching stats for {username} …")

    commits, member_since = fetch_commit_stats(token, username)
    print(f"  Commits: {commits}  (member since {member_since})")

    public, private, languages = fetch_repo_and_lang_stats(token)
    print(f"  Repos: {public} public + {private} private")
    top = sorted(languages.items(), key=lambda x: -x[1])[:6]
    total_b = sum(v for _, v in top) or 1
    for lang, nb in top:
        print(f"    {lang}: {nb/total_b*100:.1f}%")

    svg = generate_svg(username, commits, member_since, public, private, languages)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(svg)
    print(f"Saved → {output_path}")


if __name__ == "__main__":
    main()
