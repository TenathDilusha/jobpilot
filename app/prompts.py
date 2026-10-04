from . import config

SYSTEM_PROMPT = """You are JobPilot, a friendly and honest career coach for Sri Lankan university \
students and fresh graduates who are applying for internships and entry-level jobs.

Rules:
- Ground every claim in the CV and job description you are given. Never invent experience, \
grades, metrics, or skills the student does not have.
- Be specific and practical. Prefer free learning resources and small portfolio projects a \
student can finish in one or two weeks.
- Understand the Sri Lankan context: intern, trainee and associate roles; degree programmes \
such as BSc and HND; GPA and class; A/L results; and that many students write in English as a \
second language. Use clear, simple English.
- Be encouraging but truthful. A weak match should be called a weak match, with a plan to close it."""


def clip(text: str, limit: int = config.MAX_DOC_CHARS) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[:limit] + "\n[...truncated]"


def _skill_names(items: list[dict]) -> str:
    return ", ".join(i["skill"] for i in items) or "none detected"


def _documents(cv_text: str, job_description: str) -> str:
    parts = [f"<cv>\n{clip(cv_text) or 'No CV provided.'}\n</cv>"]
    if job_description.strip():
        parts.append(f"<job_description>\n{clip(job_description)}\n</job_description>")
    return "\n\n".join(parts)


ANALYSIS_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "fit_score": {"type": "integer", "minimum": 0, "maximum": 100},
        "strengths": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"skill": {"type": "string"}, "evidence": {"type": "string"}},
                "required": ["skill", "evidence"],
            },
        },
        "missing_skills": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "skill": {"type": "string"},
                    "importance": {"type": "string", "enum": ["high", "medium", "low"]},
                    "why": {"type": "string"},
                    "how_to_learn": {"type": "string"},
                },
                "required": ["skill", "importance", "why", "how_to_learn"],
            },
        },
        "cv_improvements": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["summary", "fit_score", "strengths", "missing_skills", "cv_improvements"],
}

# Every generated token costs ~0.2 s on a CPU-only laptop, so outputs are kept deliberately short.
BREVITY = "Keep every text field to one short sentence."


def analysis_messages(cv_text: str, job_description: str, keyword_match: dict) -> list[dict]:
    user = f"""{_documents(cv_text, job_description)}

A keyword scan found:
- Skills in both the CV and the job: {_skill_names(keyword_match["matched"])}
- Skills the job asks for that the CV does not mention: {_skill_names(keyword_match["missing"])}

The scan only sees exact keywords. Use it as a starting point, then read both documents \
yourself: a skill may be implied by a project, or the job may need something the scan missed.

Return JSON with:
- summary: 2 sentences on how well this student fits this role.
- fit_score: 0-100, your honest overall fit estimate.
- strengths: up to 4 relevant skills. evidence must be a short phrase copied word for word \
from the CV, not a description you wrote.
- missing_skills: up to 5 gaps, most important first, each with why it matters for this job \
and one concrete way to learn it or prove it with a small project.
- cv_improvements: up to 3 specific edits to make this CV stronger for this job. Only suggest \
rewording, reordering, or adding detail about things the CV already shows. Never suggest \
claiming a skill or experience that is not in the CV, and never invent numbers.

{BREVITY}"""
    return [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user}]


QUESTIONS_SCHEMA = {
    "type": "object",
    "properties": {
        "questions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "question": {"type": "string"},
                    "category": {"type": "string", "enum": ["technical", "project", "behavioral"]},
                    "tip": {"type": "string"},
                },
                "required": ["question", "category", "tip"],
            },
        }
    },
    "required": ["questions"],
}


def questions_messages(cv_text: str, job_description: str) -> list[dict]:
    user = f"""{_documents(cv_text, job_description)}

You are interviewing this student for this role. Return JSON with questions: 5 questions you \
would most likely ask (2 technical about the job's requirements, 2 about specific projects \
named in the CV, 1 behavioral), each with a short tip for answering well.

{BREVITY}"""
    return [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user}]


REWRITE_SCHEMA = {
    "type": "object",
    "properties": {
        "rewritten": {"type": "string"},
        "bullets": {"type": "array", "items": {"type": "string"}},
        "notes": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["rewritten", "bullets", "notes"],
}


def rewrite_messages(text: str, target_role: str, job_description: str) -> list[dict]:
    target = f"The student is applying for: {target_role}.\n" if target_role.strip() else ""
    job = (
        f"<job_description>\n{clip(job_description, 3000)}\n</job_description>\n"
        if job_description.strip()
        else ""
    )
    user = f"""{target}{job}Rewrite this project or experience description for a CV:

<original>
{clip(text, 3000)}
</original>

Return JSON with:
- rewritten: a polished 2-4 sentence description that leads with impact and names the technologies.
- bullets: 3-4 CV bullet points that start with strong action verbs. Where a number would help \
but the original has none, insert a placeholder like [X users] or [Y%] instead of inventing one.
- notes: 2-3 short suggestions about what the student should add (metrics, links, their own role)."""
    user += "\n\nKeep each bullet and note to one sentence."
    return [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user}]


FEEDBACK_SCHEMA = {
    "type": "object",
    "properties": {
        "score": {"type": "integer", "minimum": 1, "maximum": 10},
        "strengths": {"type": "array", "items": {"type": "string"}},
        "improvements": {"type": "array", "items": {"type": "string"}},
        "better_answer": {"type": "string"},
    },
    "required": ["score", "strengths", "improvements", "better_answer"],
}


def feedback_messages(question: str, answer: str, cv_text: str, job_description: str) -> list[dict]:
    user = f"""{_documents(cv_text, job_description)}

You are now the interviewer for this role. The student was asked:
<question>{question}</question>

Their answer:
<answer>{clip(answer, 3000)}</answer>

Return JSON with:
- score: 1-10 for how well this answer would land in a real interview.
- strengths: up to 3 things that worked in the answer.
- improvements: up to 3 specific ways to make it stronger (structure such as STAR, missing \
detail, clarity).
- better_answer: an improved answer of at most 5 sentences, in the student's voice, that only \
uses facts from their CV and their answer."""
    return [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user}]


INSIGHTS_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "learn_next": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "skill": {"type": "string"},
                    "why": {"type": "string"},
                    "first_step": {"type": "string"},
                },
                "required": ["skill", "why", "first_step"],
            },
        },
        "lead_with": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["summary", "learn_next", "lead_with"],
}


def insights_messages(
    query: str, location: str, postings: int, demand: list[dict], cv_text: str
) -> list[dict]:
    def status(item: dict) -> str:
        if item["in_cv"] is None:
            return ""
        return " (in the student's CV)" if item["in_cv"] else " (NOT in the student's CV)"

    lines = "\n".join(
        f"- {d['skill']}: {d['count']} of {postings} postings{status(d)}" for d in demand[:15]
    )
    cv = f"<cv>\n{clip(cv_text, 3000)}\n</cv>\n\n" if cv_text.strip() else ""
    user = f"""{cv}We searched {postings} live job postings for "{query}" in {location}. \
Skills they ask for, most requested first:
{lines}

Return JSON with:
- summary: 2 sentences on what employers in this search want most.
- learn_next: up to 3 skills that are NOT in the student's CV, most requested first. For each, \
why it matters (cite how many postings ask for it) and first_step: one free resource or a small \
project the student could finish in a weekend.
- lead_with: up to 3 in-demand skills the student already has, which they should put at the top \
of their CV. Empty if none.

Only use skills from the list above. {BREVITY}"""
    return [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user}]


def chat_messages(cv_text: str, job_description: str, history: list[dict]) -> list[dict]:
    context = (
        f"{SYSTEM_PROMPT}\n\nThe student's documents are below. Refer to them when answering. "
        "Answer in under 150 words unless the student asks for something longer, such as a "
        "cover letter.\n\n"
        f"{_documents(cv_text, job_description)}"
    )
    return [{"role": "system", "content": context}, *history]
