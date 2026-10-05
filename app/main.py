from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import config, prompts
from .cv_parser import UnsupportedFileError, extract_text
from .guard import verify_analysis, verify_rewrite
from .jobs import JobSearchError, job_text, search_jobs
from .llm import LLMError, OllamaClient, get_llm
from .skills import compare, extract_skills, skill_demand

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

app = FastAPI(title="JobPilot: Career Assistant for Sri Lankan Students")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class ModelChoice(BaseModel):
    fast: bool = False

    @property
    def model(self) -> str | None:
        return config.OLLAMA_FAST_MODEL if self.fast else None


class DocumentsRequest(ModelChoice):
    cv_text: str = Field(min_length=1)
    job_description: str = Field(min_length=1)


class RewriteRequest(ModelChoice):
    text: str = Field(min_length=1)
    target_role: str = ""
    job_description: str = ""


class FeedbackRequest(ModelChoice):
    question: str = Field(min_length=1)
    answer: str = Field(min_length=1)
    cv_text: str = ""
    job_description: str = ""


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(ModelChoice):
    messages: list[ChatMessage] = Field(min_length=1)
    cv_text: str = ""
    job_description: str = ""


class JobSearchRequest(BaseModel):
    query: str = Field(min_length=1)
    location: str = "Sri Lanka"
    cv_text: str = ""


class DemandItem(BaseModel):
    skill: str
    count: int
    in_cv: bool | None = None


class InsightsRequest(ModelChoice):
    query: str = Field(min_length=1)
    location: str = "Sri Lanka"
    postings: int = Field(gt=0)
    skills: list[DemandItem] = Field(min_length=1)
    cv_text: str = ""


@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
async def health(llm: OllamaClient = Depends(get_llm)):
    return {
        "ollama": await llm.status(config.OLLAMA_FAST_MODEL),
        "job_search": bool(config.SERPAPI_KEY),
    }


@app.post("/api/cv/parse")
async def parse_cv(file: UploadFile = File(...)):
    data = await file.read(config.MAX_UPLOAD_BYTES + 1)
    if len(data) > config.MAX_UPLOAD_BYTES:
        raise HTTPException(413, "File is larger than 5 MB.")
    try:
        text = extract_text(file.filename or "", data)
    except UnsupportedFileError as exc:
        raise HTTPException(415, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(422, "Could not read this file. Try exporting it as PDF or DOCX.") from exc
    if not text:
        raise HTTPException(
            422, "No text found. Scanned/image-only PDFs are not supported; paste the text instead."
        )
    return {"text": text, "skills": sorted(extract_skills(text))}


@app.post("/api/match")
async def match(req: DocumentsRequest):
    return compare(req.cv_text, req.job_description)


@app.post("/api/analyze")
async def analyze(req: DocumentsRequest, llm: OllamaClient = Depends(get_llm)):
    keyword_match = compare(req.cv_text, req.job_description)
    messages = prompts.analysis_messages(req.cv_text, req.job_description, keyword_match)
    schema = prompts.analysis_schema(require_strengths=bool(keyword_match["matched"]))
    ai = await _run_json(llm, messages, schema, req.model)
    return {"keyword_match": keyword_match, "ai": verify_analysis(ai, req.cv_text)}


@app.post("/api/interview/questions")
async def interview_questions(req: DocumentsRequest, llm: OllamaClient = Depends(get_llm)):
    messages = prompts.questions_messages(req.cv_text, req.job_description)
    return await _run_json(llm, messages, prompts.QUESTIONS_SCHEMA, req.model, temperature=0.5)


@app.post("/api/interview/feedback")
async def interview_feedback(req: FeedbackRequest, llm: OllamaClient = Depends(get_llm)):
    messages = prompts.feedback_messages(req.question, req.answer, req.cv_text, req.job_description)
    return await _run_json(llm, messages, prompts.FEEDBACK_SCHEMA, req.model)


@app.post("/api/rewrite")
async def rewrite(req: RewriteRequest, llm: OllamaClient = Depends(get_llm)):
    messages = prompts.rewrite_messages(req.text, req.target_role, req.job_description)
    result = await _run_json(llm, messages, prompts.REWRITE_SCHEMA, req.model, temperature=0.5)
    return verify_rewrite(result, req.text)


@app.post("/api/chat")
async def chat(req: ChatRequest, llm: OllamaClient = Depends(get_llm)):
    history = [m.model_dump() for m in req.messages[-10:]]
    messages = prompts.chat_messages(req.cv_text, req.job_description, history)
    stream = llm.stream_chat(messages, model=req.model)

    # Wait for the first token so a missing model or stopped Ollama becomes a proper HTTP error.
    try:
        first = await anext(stream, "")
    except LLMError as exc:
        raise HTTPException(503, str(exc)) from exc

    async def body():
        yield first
        try:
            async for chunk in stream:
                yield chunk
        except LLMError as exc:
            yield f"\n\n[Stopped: {exc}]"

    return StreamingResponse(body(), media_type="text/plain; charset=utf-8")


@app.post("/api/jobs/search")
async def jobs_search(req: JobSearchRequest):
    if not config.SERPAPI_KEY:
        raise HTTPException(
            503, "Live job search is off. Add SERPAPI_KEY to your .env file to enable it."
        )
    try:
        jobs = await search_jobs(
            req.query, req.location, config.SERPAPI_KEY, pages=config.JOB_SEARCH_PAGES
        )
    except JobSearchError as exc:
        raise HTTPException(502, str(exc)) from exc

    texts = [job_text(job) for job in jobs]
    demand = skill_demand(texts, req.cv_text)[:15] if jobs else []

    if req.cv_text.strip():
        jobs = [dict(job) for job in jobs]
        for job, text in zip(jobs, texts):
            match = compare(req.cv_text, text)
            job["match"] = {"score": match["score"], "missing": match["missing"][:6]}
        jobs.sort(key=lambda j: j["match"]["score"] or 0, reverse=True)
    return {"jobs": jobs, "demand": {"postings": len(jobs), "skills": demand}}


@app.post("/api/jobs/insights")
async def jobs_insights(req: InsightsRequest, llm: OllamaClient = Depends(get_llm)):
    demand = [s.model_dump() for s in req.skills]
    messages = prompts.insights_messages(
        req.query, req.location, req.postings, demand, req.cv_text
    )
    return await _run_json(llm, messages, prompts.INSIGHTS_SCHEMA, req.model)


async def _run_json(
    llm: OllamaClient,
    messages: list[dict],
    schema: dict,
    model: str | None,
    temperature: float = 0.2,
):
    try:
        return await llm.chat_json(messages, schema, temperature=temperature, model=model)
    except LLMError as exc:
        raise HTTPException(503, str(exc)) from exc
