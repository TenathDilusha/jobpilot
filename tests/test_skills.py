from pathlib import Path

from app.skills import compare, extract_skills

SAMPLES = Path(__file__).resolve().parent.parent / "samples"


def test_extracts_common_skills():
    text = "Built APIs with Node.js and Express.js, deployed on AWS using Docker. Strong in C++ and C#."
    assert {"Node.js", "Express.js", "AWS", "Docker", "C++", "C#"} <= extract_skills(text)


def test_java_does_not_match_javascript():
    assert extract_skills("JavaScript developer") == {"JavaScript"}


def test_longer_alias_wins():
    assert extract_skills("Mobile apps with React Native") == {"React Native"}


def test_case_sensitive_aliases():
    assert "Go" not in extract_skills("I like to go hiking")
    assert "Go" in extract_skills("Backend services in Go and Python")
    assert "Excel" not in extract_skills("I excel at teamwork")
    assert "Excel" in extract_skills("Advanced Excel and Power BI")


def test_r_and_d_is_not_r_language():
    assert "R" not in extract_skills("Worked in the R&D team")


def test_compare_sample_documents():
    cv = (SAMPLES / "sample_cv.txt").read_text()
    job = (SAMPLES / "sample_job.txt").read_text()
    result = compare(cv, job)

    matched = {s["skill"] for s in result["matched"]}
    missing = {s["skill"] for s in result["missing"]}
    assert {"JavaScript", "React", "Git", "SQL"} <= matched
    assert {"TypeScript", "Node.js", "Docker", "AWS", "PostgreSQL"} <= missing
    assert 0 < result["score"] < 100


def test_compare_without_job_skills():
    assert compare("Python developer", "We value kindness.")["score"] is None
