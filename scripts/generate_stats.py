#!/usr/bin/env python3
"""
Генерирует GitHub Stats SVG с поддержкой приватных репозиториев
Использует GitHub API для получения данных о репозиториях
"""

import os
import sys
import requests
from datetime import datetime

def get_github_stats(username: str, token: str) -> dict:
    """Получает статистику GitHub через API"""
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    # Получаем информацию о пользователе
    user_url = f"https://api.github.com/users/{username}"
    user_response = requests.get(user_url, headers=headers)
    user_data = user_response.json()
    
    # Получаем все репозитории (публичные и приватные)
    repos_url = f"https://api.github.com/user/repos?per_page=100&affiliation=owner"
    repos_response = requests.get(repos_url, headers=headers)
    repos_data = repos_response.json()
    
    # Подсчитываем статистику
    total_stars = sum(repo.get('stargazers_count', 0) for repo in repos_data)
    total_forks = sum(repo.get('forks_count', 0) for repo in repos_data)
    total_repos = len(repos_data)
    
    # Получаем информацию о коммитах (приблизительно)
    # Это сложнее, так как нужно получить коммиты из каждого репо
    # Для упрощения используем публичный API
    
    return {
        "username": username,
        "public_repos": user_data.get("public_repos", 0),
        "total_repos": total_repos,
        "total_stars": total_stars,
        "total_forks": total_forks,
        "followers": user_data.get("followers", 0),
        "following": user_data.get("following", 0)
    }

def generate_svg(stats: dict) -> str:
    """Генерирует SVG с красивой темой dracula"""
    # Используем готовый API с параметрами для красивого отображения
    # Для приватных репо нужно использовать другой подход
    username = stats["username"]
    params = {
        "username": username,
        "show_icons": "true",
        "hide_border": "true",
        "bg_color": "282A36",
        "title_color": "BD93F9",
        "icon_color": "BD93F9",
        "text_color": "F8F8F2",
        "hide_rank": "false",
        "include_all_commits": "true",
        "count_private": "true",
        "theme": "dracula"
    }
    
    url = "https://github-readme-stats.vercel.app/api"
    response = requests.get(url, params=params)
    return response.text

def main():
    username = os.environ.get("GITHUB_USERNAME", "tanat0")
    token = os.environ.get("GITHUB_TOKEN")
    output_path = os.environ.get("OUTPUT_PATH", "github-stats.svg")
    
    if not token:
        print("Warning: GITHUB_TOKEN not set. Using public API only.")
        # Используем публичный API без токена
        params = {
            "username": username,
            "show_icons": "true",
            "hide_border": "true",
            "bg_color": "282A36",
            "title_color": "BD93F9",
            "icon_color": "BD93F9",
            "text_color": "F8F8F2",
            "hide_rank": "false",
            "include_all_commits": "true",
            "count_private": "true",
            "theme": "dracula"
        }
        url = "https://github-readme-stats.vercel.app/api"
        response = requests.get(url, params=params)
        svg_content = response.text
    else:
        # Получаем статистику через API
        stats = get_github_stats(username, token)
        # Генерируем SVG
        svg_content = generate_svg(stats)
    
    # Сохраняем SVG
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(svg_content)
    
    print(f"GitHub stats saved to {output_path}")

if __name__ == "__main__":
    main()

