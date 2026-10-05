import re

from .skills import extract_skills

_QUOTES = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-"})


def _plain(text: str) -> str:
    return re.sub(r"\s+", " ", text.translate(_QUOTES)).strip().lower()


def quoted_from(evidence: str, cv_text: str) -> bool:
    quote = _plain(evidence).strip(" \"'.")
    return len(quote) >= 3 and quote in _plain(cv_text)


def verify_analysis(ai: dict, cv_text: str) -> dict:
    """Drop model output that the CV cannot back up.

    Small models ignore "never invent" instructions often enough that the prompt alone
    is not a guarantee, so strengths must quote the CV and CV edits must not name
    skills the CV lacks.
    """
    cv_skills = extract_skills(cv_text)
    return {
        **ai,
        "strengths": [s for s in ai.get("strengths", []) if quoted_from(s["evidence"], cv_text)],
        "cv_improvements": [
            tip for tip in ai.get("cv_improvements", []) if not extract_skills(tip) - cv_skills
        ],
    }


def verify_rewrite(result: dict, original: str) -> dict:
    """Drop CV bullets that name skills the original description never mentions."""
    known = extract_skills(original)
    return {
        **result,
        "bullets": [b for b in result.get("bullets", []) if not extract_skills(b) - known],
    }
