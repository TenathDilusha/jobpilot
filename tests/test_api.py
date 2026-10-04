import io

import pytest
from docx import Document
from fastapi.testclient import TestClient

from app import config
from app.llm import LLMError, get_llm
from app.main import app


class FakeLLM:
    def __init__(self, response=None, error=None, chunks=("Focus on ", "TypeScript next.")):
        self.response = response
        self.error = error
        self.chunks = chunks
        self.calls = []

    async def chat_json(self, messages, schema, temperature=0.2, model=None):
        self.calls.append({"messages": messages, "model": model})
        if self.error:
            raise self.error
        return self.response

    async def stream_chat(self, messages, temperature=0.4, model=None):
        self.calls.append({"messages": messages, "model": model})
        if self.error:
            raise self.error
        for chunk in self.chunks:
            yield chunk

    async def status(self, fast_model):
        return {"reachable": True, "model": "fake", "model_available": True,
                "fast_model": fast_model, "fast_model_available": True}


@pytest.fixture
def client():
    yield TestClient(app)
    app.dependency_overrides.clear()


def use_llm(llm):
    app.dependency_overrides[get_llm] = lambda: llm
    return llm


DOCS = {"cv_text": "Python and React", "job_description": "Need React and TypeScript"}


def test_index_served(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "JobPilot" in response.text


def test_health(client):
    use_llm(FakeLLM())
    body = client.get("/api/health").json()
    assert body["ollama"]["fast_model"] == config.OLLAMA_FAST_MODEL


def test_parse_txt_cv(client):
    files = {"file": ("cv.txt", b"Skills: Python, React, Docker", "text/plain")}
    response = client.post("/api/cv/parse", files=files)
    assert response.status_code == 200
    assert set(response.json()["skills"]) == {"Python", "React", "Docker"}


def test_parse_docx_cv(client):
    doc = Document()
    doc.add_paragraph("Projects built with Flutter and Firebase")
    buffer = io.BytesIO()
    doc.save(buffer)
    files = {"file": ("cv.docx", buffer.getvalue(), "application/octet-stream")}
    response = client.post("/api/cv/parse", files=files)
    assert response.status_code == 200
    assert set(response.json()["skills"]) == {"Flutter", "Firebase"}


def test_parse_rejects_unknown_type(client):
    files = {"file": ("cv.png", b"\x89PNG", "image/png")}
    assert client.post("/api/cv/parse", files=files).status_code == 415


def test_match_needs_no_model(client):
    body = client.post("/api/match", json=DOCS).json()
    assert [s["skill"] for s in body["matched"]] == ["React"]
    assert [s["skill"] for s in body["missing"]] == ["TypeScript"]
    assert body["score"] == 50


def test_analyze_grounds_prompt_in_keyword_scan(client):
    llm = use_llm(FakeLLM(response={"summary": "ok", "fit_score": 60}))
    response = client.post("/api/analyze", json=DOCS)
    assert response.status_code == 200
    body = response.json()
    assert [s["skill"] for s in body["keyword_match"]["missing"]] == ["TypeScript"]
    assert body["ai"]["fit_score"] == 60
    prompt = llm.calls[0]["messages"][1]["content"]
    assert "does not mention: TypeScript" in prompt
    assert llm.calls[0]["model"] is None


def test_fast_mode_uses_fast_model(client):
    llm = use_llm(FakeLLM(response={"questions": []}))
    response = client.post("/api/interview/questions", json={**DOCS, "fast": True})
    assert response.status_code == 200
    assert llm.calls[0]["model"] == config.OLLAMA_FAST_MODEL


def test_llm_errors_become_503(client):
    use_llm(FakeLLM(error=LLMError("Ollama is not running")))
    response = client.post("/api/rewrite", json={"text": "Built a website"})
    assert response.status_code == 503
    assert response.json()["detail"] == "Ollama is not running"


def test_chat_streams_reply(client):
    use_llm(FakeLLM())
    response = client.post(
        "/api/chat", json={"messages": [{"role": "user", "content": "What next?"}], "cv_text": "Python"}
    )
    assert response.status_code == 200
    assert response.text == "Focus on TypeScript next."


def test_chat_error_before_first_token_is_503(client):
    use_llm(FakeLLM(error=LLMError("Model 'gemma3:4b' is not installed.")))
    response = client.post("/api/chat", json={"messages": [{"role": "user", "content": "Hi"}]})
    assert response.status_code == 503


def test_job_search_disabled_without_key(client, monkeypatch):
    monkeypatch.setattr(config, "SERPAPI_KEY", "")
    response = client.post("/api/jobs/search", json={"query": "intern"})
    assert response.status_code == 503


FAKE_JOBS = [
    {"title": "iOS Intern", "description": "Swift and iOS", "highlights": ["Git required"]},
    {"title": "Data Intern", "description": "Python, Pandas and SQL", "highlights": ["Git"]},
    {"title": "Backend Intern", "description": "Python and Docker", "highlights": []},
]


@pytest.fixture
def fake_job_search(monkeypatch):
    async def fake_search(query, location, api_key, pages=1):
        return FAKE_JOBS

    monkeypatch.setattr(config, "SERPAPI_KEY", "test")
    monkeypatch.setattr("app.main.search_jobs", fake_search)


def test_job_search_ranks_by_cv_match(client, fake_job_search):
    response = client.post(
        "/api/jobs/search", json={"query": "intern", "cv_text": "Python, Pandas, SQL, Git"}
    )
    jobs = response.json()["jobs"]
    assert [j["title"] for j in jobs] == ["Data Intern", "Backend Intern", "iOS Intern"]
    assert jobs[0]["match"]["score"] == 100
    assert "match" not in FAKE_JOBS[0]


def test_job_search_reports_skill_demand(client, fake_job_search):
    response = client.post("/api/jobs/search", json={"query": "intern", "cv_text": "Python"})
    demand = response.json()["demand"]
    assert demand["postings"] == 3
    top = demand["skills"][:2]
    assert [(s["skill"], s["count"], s["in_cv"]) for s in top] == [
        ("Python", 2, True),
        ("Git", 2, False),
    ]


def test_job_insights_prompt_marks_cv_gaps(client):
    llm = use_llm(FakeLLM(response={"summary": "ok", "learn_next": [], "lead_with": []}))
    response = client.post(
        "/api/jobs/insights",
        json={
            "query": "intern",
            "postings": 3,
            "skills": [{"skill": "Git", "count": 2, "in_cv": False}],
            "cv_text": "Python",
        },
    )
    assert response.status_code == 200
    prompt = llm.calls[0]["messages"][1]["content"]
    assert "Git: 2 of 3 postings (NOT in the student's CV)" in prompt
