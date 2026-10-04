import time

import httpx

SERPAPI_URL = "https://serpapi.com/search.json"
# Results are cached so repeated searches (e.g. during a demo) don't spend SerpApi credits.
CACHE_SECONDS = 6 * 60 * 60

_cache: dict[tuple, tuple[float, list[dict]]] = {}


class JobSearchError(RuntimeError):
    pass


async def search_jobs(query: str, location: str, api_key: str, pages: int = 1) -> list[dict]:
    key = (query.strip().lower(), location.strip().lower(), pages)
    cached = _cache.get(key)
    if cached and time.monotonic() - cached[0] < CACHE_SECONDS:
        return cached[1]

    params = {
        "engine": "google_jobs",
        "q": query,
        "location": location,
        "hl": "en",
        "api_key": api_key,
    }
    jobs: list[dict] = []
    for _ in range(pages):
        data = await _fetch(params)
        if data is None:
            break
        jobs.extend(_normalize(job) for job in data.get("jobs_results", []))
        token = data.get("serpapi_pagination", {}).get("next_page_token")
        if not token:
            break
        params = {**params, "next_page_token": token}

    _cache[key] = (time.monotonic(), jobs)
    return jobs


async def _fetch(params: dict) -> dict | None:
    """One SerpApi request. Returns None when Google has no results for the query."""
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(SERPAPI_URL, params=params)
    except httpx.HTTPError as exc:
        raise JobSearchError("Could not reach SerpApi. Check your internet connection.") from exc

    data = response.json() if response.content else {}
    error = data.get("error", "")
    if "hasn't returned any results" in error:
        return None
    if response.status_code != 200 or error:
        raise JobSearchError(f"SerpApi error: {error or response.status_code}")
    return data


def _normalize(job: dict) -> dict:
    extensions = job.get("detected_extensions", {})
    apply_options = job.get("apply_options") or []
    highlights = [
        item for section in job.get("job_highlights", []) for item in section.get("items", [])
    ]
    return {
        "title": job.get("title", ""),
        "company": job.get("company_name", ""),
        "location": job.get("location", ""),
        "via": job.get("via", ""),
        "posted": extensions.get("posted_at", ""),
        "schedule": extensions.get("schedule_type", ""),
        "description": job.get("description", ""),
        "highlights": highlights,
        "link": apply_options[0]["link"] if apply_options else job.get("share_link", ""),
    }


def job_text(job: dict) -> str:
    return "\n".join([job["title"], job["description"], *job.get("highlights", [])])
