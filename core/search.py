"""Tavily web search wrapper with an in-memory cache."""
from tavily import TavilyClient

from config import SEARCH_COUNTRY


class WebSearch:
    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("Tavily API key is missing")
        self.client = TavilyClient(api_key=api_key)
        self._cache: dict = {}

    def search(self, query: str, domains=None, max_results: int = 8,
               depth: str = "advanced", time_range: str | None = None,
               country: str | None = SEARCH_COUNTRY) -> list[dict]:
        key = (query, tuple(domains or []), max_results, depth, time_range, country)
        if key in self._cache:
            return self._cache[key]
        kwargs = dict(query=query, search_depth=depth, max_results=max_results)
        if domains:
            kwargs["include_domains"] = list(domains)
        if time_range:
            kwargs["time_range"] = time_range
        if country:
            kwargs["country"] = country
        try:
            resp = self.client.search(**kwargs)
        except TypeError:  # older tavily-python without these options
            kwargs.pop("time_range", None)
            kwargs.pop("country", None)
            resp = self.client.search(**kwargs)
        results = [
            {
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "content": r.get("content", ""),
                "score": r.get("score", 0),
            }
            for r in resp.get("results", [])
        ]
        self._cache[key] = results
        return results

    def extract(self, url: str) -> str:
        """Fetch the full text of a page (e.g. a job description)."""
        resp = self.client.extract(urls=[url])
        results = resp.get("results", [])
        return (results[0].get("raw_content") or "") if results else ""
