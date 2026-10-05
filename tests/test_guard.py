from app.guard import quoted_from, verify_analysis, verify_rewrite
from app.prompts import analysis_schema

CV = """Tools: Git, GitHub, Figma, Linux
Campus Event Hub (React, Firebase)
Made a website for our university club where members can register for events."""


def test_quoted_from_ignores_case_quotes_and_spacing():
    assert quoted_from("“tools: Git,  GitHub”", CV)
    assert not quoted_from("Maintained a website using Git", CV)
    assert not quoted_from('""', CV)


def test_verify_analysis_drops_unbacked_claims():
    ai = {
        "summary": "ok",
        "fit_score": 60,
        "strengths": [
            {"skill": "Git", "evidence": "Tools: Git, GitHub, Figma, Linux"},
            {"skill": "Git", "evidence": "Maintained a website for our club using Git"},
        ],
        "missing_skills": [],
        "cv_improvements": [
            "Put Campus Event Hub first, since it is a React web app.",
            "Add 'Developed REST APIs with Node.js' to the club project.",
        ],
    }
    checked = verify_analysis(ai, CV)
    assert [s["evidence"] for s in checked["strengths"]] == ["Tools: Git, GitHub, Figma, Linux"]
    assert checked["cv_improvements"] == ["Put Campus Event Hub first, since it is a React web app."]


def test_verify_rewrite_drops_bullets_with_new_skills():
    result = {
        "rewritten": "Built a club website.",
        "bullets": [
            "Developed a React and Firebase app for event registration.",
            "Implemented RESTful APIs following Agile principles.",
        ],
        "notes": [],
    }
    checked = verify_rewrite(result, "Made a club website with React and Firebase.")
    assert checked["bullets"] == ["Developed a React and Firebase app for event registration."]


def test_analysis_schema_requires_strengths_only_when_skills_match():
    assert analysis_schema(True)["properties"]["strengths"]["minItems"] == 1
    assert "minItems" not in analysis_schema(False)["properties"]["strengths"]
