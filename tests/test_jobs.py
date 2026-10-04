import asyncio

import pytest

from app import jobs
from app.skills import skill_demand


def raw_job(title):
    return {
        "title": title,
        "company_name": "Acme",
        "description": "Build things",
        "job_highlights": [{"title": "Qualifications", "items": ["React", "TypeScript"]}],
        "detected_extensions": {"posted_at": "2 days ago"},
        "apply_options": [{"title": "LinkedIn", "link": "https://example.com/apply"}],
    }


@pytest.fixture(autouse=True)
def clear_cache():
    jobs._cache.clear()


def test_paginates_normalizes_and_caches(monkeypatch):
    calls = []

    async def fake_fetch(params):
        calls.append(params)
        if "next_page_token" not in params:
            return {"jobs_results": [raw_job("A")], "serpapi_pagination": {"next_page_token": "t"}}
        return {"jobs_results": [raw_job("B")]}

    monkeypatch.setattr(jobs, "_fetch", fake_fetch)
    results = asyncio.run(jobs.search_jobs("intern", "Sri Lanka", "key", pages=3))

    assert [j["title"] for j in results] == ["A", "B"]
    assert results[0]["highlights"] == ["React", "TypeScript"]
    assert results[0]["link"] == "https://example.com/apply"
    assert len(calls) == 2

    asyncio.run(jobs.search_jobs("Intern ", "sri lanka", "key", pages=3))
    assert len(calls) == 2


def test_no_results(monkeypatch):
    async def fake_fetch(params):
        return None

    monkeypatch.setattr(jobs, "_fetch", fake_fetch)
    assert asyncio.run(jobs.search_jobs("zzz", "Sri Lanka", "key")) == []


def test_skill_demand_without_cv():
    demand = skill_demand(["React and Git", "React"])
    assert demand[0] == {
        "skill": "React", "category": "Frontend", "count": 2, "share": 100, "in_cv": None
    }
    assert demand[1]["skill"] == "Git"
