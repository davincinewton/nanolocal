"""Web tools: web_search and web_fetch."""

import html
import json
import os
import re
from typing import Any
from urllib.parse import urlparse

import httpx

from nanobot.agent.tools.base import Tool

# Shared constants
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_7_2) AppleWebKit/537.36"
MAX_REDIRECTS = 5  # Limit redirects to prevent DoS attacks


def _strip_tags(text: str) -> str:
    """Remove HTML tags and decode entities."""
    text = re.sub(r'<script[\s\S]*?</script>', '', text, flags=re.I)
    text = re.sub(r'<style[\s\S]*?</style>', '', text, flags=re.I)
    text = re.sub(r'<[^>]+>', '', text)
    return html.unescape(text).strip()


def _normalize(text: str) -> str:
    """Normalize whitespace."""
    text = re.sub(r'[ \t]+', ' ', text)
    return re.sub(r'\n{3,}', '\n\n', text).strip()


def _validate_url(url: str) -> tuple[bool, str]:
    """Validate URL: must be http(s) with valid domain."""
    try:
        p = urlparse(url)
        if p.scheme not in ('http', 'https'):
            return False, f"Only http/https allowed, got '{p.scheme or 'none'}'"
        if not p.netloc:
            return False, "Missing domain"
        return True, ""
    except Exception as e:
        return False, str(e)


class WebSearchTool(Tool):
    """Searches the web. Uses DuckDuckGo by default, SearXNG when configured."""
    
    name = "web_search"
    description = "Searches the web for information. Returns titles, URLs, and snippets. Uses DuckDuckGo by default, SearXNG when configured."
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
            "count": {
                "type": "integer",
                "description": "Number of results to return (default 5, max 10)",
                "minimum": 1,
                "maximum": 10
            }
        },
        "required": ["query"]
    }
    
    def __init__(self, searxng_url: str | None = None, max_results: int = 5):
        self.searxng_url = searxng_url.rstrip('/') if searxng_url else None
        self.max_results = max_results

    async def execute(self, query: str, count: int | None = None, **kwargs) -> str:
        try:
            n = min(max(count or self.max_results, 1), 10)
            
            # If SearXNG is configured, use it; otherwise use DuckDuckGo
            if self.searxng_url:
                return await self._search_searxng(query, n)
            else:
                return await self._search_duckduckgo(query, n)
            
        except Exception as e:
            return f"Error: web search failed - {str(e)}"
    
    async def _search_searxng(self, query: str, n: int) -> str:
        """Search using SearXNG instance."""
        try:
            # searxng API参数
            params = {
                "q": query,
                "format": "json",
                "pageno": 1,
            }
            
            async with httpx.AsyncClient() as client:
                r = await client.get(
                    f"{self.searxng_url}/search",
                    params=params,
                    timeout=10.0
                )
                r.raise_for_status()
            
            data = r.json()
            results = data.get("results", [])[:n]
            
            if not results:
                return f"No results for: {query}"
            
            lines = [f"Results for: {query} (via SearXNG)\n"]
            for i, item in enumerate(results, 1):
                title = item.get('title', '')
                url = item.get('url', '')
                content = item.get('content') or item.get('snippet', '')
                
                # 清理可能的HTML标签
                if content:
                    content = re.sub(r'<[^>]+>', '', content).strip()
                
                lines.append(f"{i}. {title}")
                lines.append(f"   {url}")
                if content:
                    lines.append(f"   {content}")
            
            return "\n".join(lines)
            
        except httpx.RequestError as e:
            return f"Error: SearXNG connection failed - {str(e)}"
        except (KeyError, ValueError) as e:
            return f"Error: invalid SearXNG response - {str(e)}"
    
    async def _search_duckduckgo(self, query: str, n: int) -> str:
        """Search using DuckDuckGo."""
        try:
            # DuckDuckGo Instant Answer API
            params = {
                "q": query,
                "format": "json",
                "no_html": 1,
                "kl": "wt-wt",  # Weighted title
                "kp": -1,        # No official source
                "kh": 1,        # Site descriptions
                "k1": -1,        # Safe search
                "ia": "web"        # Web results only
                "duckduckgo_ai": 1,  # Use AI features,
            }
            
            async with httpx.AsyncClient() as client:
                r = await client.get(
                    "https://duckduckgo.com/",
                    params=params,
                    timeout=10.0
                )
                r.raise_for_status()
            
            data = r.json()
            
            # DuckDuckGo has different response format
            results = []
            
            # Check if it's an instant answer
            if "AbstractText" in data:
                instant_answer = data["AbstractText"]
                results.append({
                    "title": "Instant Answer",
                    "url": "",
                    "content": instant_answer
                })
            
            # Process regular results
            for result in data.get("Results", [])[:n]:
                results.append({
                    "title": result.get("Title", ""),
                    "url": result.get("FirstURL", ""),
                    "content": result.get("Text", "") or result.get("Snippet", "")
                })
            
            if not results and not data.get("AbstractText"):
                return f"No results for: {query}"
            
            lines = [f"Results for: {query} (via DuckDuckGo)\n"]
            for i, item in enumerate(results, 1):
                title = item["title"]
                url = item["url"]
                content = item["content"]
                
                lines.append(f"{i}. {title}")
                lines.append(f"   {url}")
                if content:
                    lines.append(f"   {content}")
            
            return "\n".join(lines)
            
        except httpx.RequestError as e:
            return f"Error: DuckDuckGo connection failed - {str(e)}"
        except (KeyError, ValueError) as e:
            return f"Error: invalid DuckDuckGo response - {str(e)}"

class WebFetchTool(Tool):
    """Fetch and extract content from a URL using Readability."""
    
    name = "web_fetch"
    description = "Fetch URL and extract readable content (HTML → markdown/text)."
    parameters = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "URL to fetch"},
            "extractMode": {"type": "string", "enum": ["markdown", "text"], "default": "markdown"},
            "maxChars": {"type": "integer", "minimum": 100}
        },
        "required": ["url"]
    }
    
    def __init__(self, max_chars: int = 50000):
        self.max_chars = max_chars
    
    async def execute(self, url: str, extractMode: str = "markdown", maxChars: int | None = None, **kwargs: Any) -> str:
        from readability import Document

        max_chars = maxChars or self.max_chars

        # Validate URL before fetching
        is_valid, error_msg = _validate_url(url)
        if not is_valid:
            return json.dumps({"error": f"URL validation failed: {error_msg}", "url": url})

        try:
            async with httpx.AsyncClient(
                follow_redirects=True,
                max_redirects=MAX_REDIRECTS,
                timeout=30.0
            ) as client:
                r = await client.get(url, headers={"User-Agent": USER_AGENT})
                r.raise_for_status()
            
            ctype = r.headers.get("content-type", "")
            
            # JSON
            if "application/json" in ctype:
                text, extractor = json.dumps(r.json(), indent=2), "json"
            # HTML
            elif "text/html" in ctype or r.text[:256].lower().startswith(("<!doctype", "<html")):
                doc = Document(r.text)
                content = self._to_markdown(doc.summary()) if extractMode == "markdown" else _strip_tags(doc.summary())
                text = f"# {doc.title()}\n\n{content}" if doc.title() else content
                extractor = "readability"
            else:
                text, extractor = r.text, "raw"
            
            truncated = len(text) > max_chars
            if truncated:
                text = text[:max_chars]
            
            return json.dumps({"url": url, "finalUrl": str(r.url), "status": r.status_code,
                              "extractor": extractor, "truncated": truncated, "length": len(text), "text": text})
        except Exception as e:
            return json.dumps({"error": str(e), "url": url})
    
    def _to_markdown(self, html: str) -> str:
        """Convert HTML to markdown."""
        # Convert links, headings, lists before stripping tags
        text = re.sub(r'<a\s+[^>]*href=["\']([^"\']+)["\'][^>]*>([\s\S]*?)</a>',
                      lambda m: f'[{_strip_tags(m[2])}]({m[1]})', html, flags=re.I)
        text = re.sub(r'<h([1-6])[^>]*>([\s\S]*?)</h\1>',
                      lambda m: f'\n{"#" * int(m[1])} {_strip_tags(m[2])}\n', text, flags=re.I)
        text = re.sub(r'<li[^>]*>([\s\S]*?)</li>', lambda m: f'\n- {_strip_tags(m[1])}', text, flags=re.I)
        text = re.sub(r'</(p|div|section|article)>', '\n\n', text, flags=re.I)
        text = re.sub(r'<(br|hr)\s*/?>', '\n', text, flags=re.I)
        return _normalize(_strip_tags(text))
