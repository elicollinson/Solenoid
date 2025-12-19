"""
Simplified web search tool using Brave Search.
"""

import os
import json
import yaml
import requests
from typing import Any
from google.adk.tools.function_tool import FunctionTool

def _load_api_key() -> str | None:
    """Loads Brave Search API key from env vars or app_settings.yaml."""
    # 1. Try environment variable
    api_key = os.environ.get("BRAVE_SEARCH_API_KEY")
    if api_key:
        return api_key

    # 2. Try app_settings.yaml
    try:
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))
        config_path = os.path.join(project_root, "app_settings.yaml")
        if os.path.exists(config_path):
            with open(config_path, "r") as f:
                settings = yaml.safe_load(f)
                # Check search section
                search_settings = settings.get("search", {})
                return search_settings.get("brave_search_api_key")
    except Exception:
        pass
    
    return None

def universal_search(query: str) -> str:
    """
    Performs a web search using Brave Search.

    Args:
        query: The search query string.

    Returns:
        A text summary of the search results (titles, links, and snippets).
    """
    api_key = _load_api_key()
    if not api_key:
        return "Error: BRAVE_SEARCH_API_KEY not found in environment variables or app_settings.yaml."

    url = "https://api.search.brave.com/res/v1/web/search"
    headers = {
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
        "X-Subscription-Token": api_key
    }
    params = {
        "q": query,
        "count": 10
    }

    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        results = data.get("web", {}).get("results", [])
        if not results:
            return "No results found."

        summary = []
        for i, result in enumerate(results, 1):
            title = result.get("title", "No Title")
            link = result.get("url", result.get("link", ""))
            description = result.get("description", result.get("snippet", ""))
            
            summary.append(f"{i}. {title}")
            summary.append(f"   Link: {link}")
            summary.append(f"   Snippet: {description}")
            summary.append("")
        
        return "\n".join(summary)

    except Exception as e:
        return f"Error performing search: {str(e)}"

def create_universal_search_tool():
    """Factory to create the search tool."""
    return FunctionTool(func=universal_search)
