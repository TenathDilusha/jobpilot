"""Deterministic skill extraction.

The keyword scan gives a reproducible baseline that the model's analysis is grounded in,
so a small local model cannot claim a skill the CV never mentions.
Aliases starting with "=" are matched case-sensitively (e.g. "Go" vs the verb "go").
"""

import re

SKILL_TAXONOMY: dict[str, dict[str, list[str]]] = {
    "Languages": {
        "Python": ["python"],
        "Java": ["java"],
        "JavaScript": ["javascript", "ecmascript", "=JS"],
        "TypeScript": ["typescript"],
        "C++": ["c++", "cpp"],
        "C#": ["c#", "csharp"],
        "Go": ["golang", "=Go"],
        "Kotlin": ["kotlin"],
        "Swift": ["swift"],
        "PHP": ["php"],
        "Ruby": ["ruby"],
        "Dart": ["dart"],
        "Rust": ["rust"],
        "R": ["r programming", "rstudio"],
        "SQL": ["sql"],
        "Bash": ["bash", "shell scripting"],
        "MATLAB": ["matlab"],
    },
    "Frontend": {
        "React": ["react", "react.js", "reactjs"],
        "Angular": ["angular", "angularjs"],
        "Vue.js": ["vue", "vue.js", "vuejs"],
        "Next.js": ["next.js", "nextjs"],
        "HTML": ["html", "html5"],
        "CSS": ["css", "css3"],
        "Tailwind CSS": ["tailwind", "tailwindcss"],
        "Bootstrap": ["bootstrap"],
        "Redux": ["redux"],
    },
    "Backend": {
        "Node.js": ["node.js", "nodejs", "node"],
        "Express.js": ["express.js", "expressjs"],
        "Django": ["django"],
        "Flask": ["flask"],
        "FastAPI": ["fastapi"],
        "Spring Boot": ["spring boot", "springboot", "spring framework", "spring mvc"],
        "Laravel": ["laravel"],
        ".NET": [".net", "asp.net", "dotnet"],
        "REST APIs": ["rest api", "rest apis", "restful", "restful apis"],
        "GraphQL": ["graphql"],
        "Microservices": ["microservice", "microservices"],
    },
    "Mobile": {
        "Flutter": ["flutter"],
        "React Native": ["react native"],
        "Android": ["android"],
        "iOS": ["ios"],
    },
    "Data & AI": {
        "Machine Learning": ["machine learning", "ml"],
        "Deep Learning": ["deep learning"],
        "NLP": ["nlp", "natural language processing"],
        "Computer Vision": ["computer vision", "opencv"],
        "TensorFlow": ["tensorflow", "keras"],
        "PyTorch": ["pytorch"],
        "scikit-learn": ["scikit-learn", "sklearn"],
        "Pandas": ["pandas"],
        "NumPy": ["numpy"],
        "Data Analysis": ["data analysis", "data analytics"],
        "Power BI": ["power bi", "powerbi"],
        "Tableau": ["tableau"],
        "Excel": ["ms excel", "microsoft excel", "=Excel"],
        "Statistics": [
            "statistical analysis",
            "statistical modelling",
            "statistical modeling",
            "applied statistics",
            "probability and statistics",
        ],
        "LLMs": ["llm", "llms", "large language model", "large language models"],
        "Generative AI": ["generative ai", "genai", "gen ai"],
    },
    "Databases": {
        "MySQL": ["mysql"],
        "PostgreSQL": ["postgresql", "postgres"],
        "MongoDB": ["mongodb", "mongo"],
        "Firebase": ["firebase", "firestore"],
        "Redis": ["redis"],
        "Oracle DB": ["oracle database", "oracle db", "pl/sql"],
        "SQL Server": ["sql server", "mssql"],
        "SQLite": ["sqlite"],
    },
    "Cloud & DevOps": {
        "AWS": ["aws", "amazon web services"],
        "Azure": ["azure", "microsoft azure"],
        "Google Cloud": ["gcp", "google cloud"],
        "Docker": ["docker"],
        "Kubernetes": ["kubernetes", "k8s"],
        "CI/CD": ["ci/cd", "cicd", "continuous integration", "continuous delivery"],
        "GitHub Actions": ["github actions"],
        "Jenkins": ["jenkins"],
        "Linux": ["linux", "ubuntu"],
        "Terraform": ["terraform"],
        "Git": ["git", "github", "gitlab", "bitbucket", "version control"],
    },
    "Testing & QA": {
        "Unit Testing": ["unit testing", "unit tests", "unit test"],
        "Test Automation": ["test automation", "automation testing", "automated testing"],
        "Manual Testing": ["manual testing"],
        "Selenium": ["selenium"],
        "Cypress": ["cypress"],
        "Jest": ["jest"],
        "JUnit": ["junit"],
        "Postman": ["postman"],
    },
    "Design": {
        "Figma": ["figma"],
        "UI/UX Design": ["ui/ux", "ux design", "ui design", "user experience", "user interface design"],
        "Adobe XD": ["adobe xd"],
    },
    "Practices": {
        "Agile": ["agile"],
        "Scrum": ["scrum"],
        "Jira": ["jira"],
        "OOP": ["oop", "object-oriented", "object oriented"],
        "Data Structures & Algorithms": ["data structures", "algorithms", "dsa"],
        "System Design": ["system design"],
    },
    "Security & Networking": {
        "Cybersecurity": ["cybersecurity", "cyber security", "information security"],
        "Networking": ["computer networks", "networking", "tcp/ip"],
    },
    "Soft Skills": {
        "Communication": ["communication skills", "verbal communication", "written communication"],
        "Teamwork": ["teamwork", "team player", "collaboration"],
        "Problem Solving": ["problem solving", "problem-solving"],
        "Leadership": ["leadership"],
        "Time Management": ["time management"],
    },
}

SKILL_CATEGORY = {
    skill: category for category, skills in SKILL_TAXONOMY.items() for skill in skills
}


def _compile_patterns() -> list[tuple[str, re.Pattern]]:
    entries = []
    for skills in SKILL_TAXONOMY.values():
        for skill, aliases in skills.items():
            for alias in aliases:
                case_sensitive = alias.startswith("=")
                alias = alias.lstrip("=")
                body = r"\s+".join(re.escape(part) for part in alias.split())
                pattern = rf"(?<![\w+#.&/-]){body}(?![\w+#&])"
                flags = 0 if case_sensitive else re.IGNORECASE
                entries.append((len(alias), skill, re.compile(pattern, flags)))
    # Longest aliases first, so "react native" is consumed before "react" can match it.
    entries.sort(key=lambda e: e[0], reverse=True)
    return [(skill, pattern) for _, skill, pattern in entries]


_PATTERNS = _compile_patterns()


def extract_skills(text: str) -> set[str]:
    found: set[str] = set()
    remaining = text
    for skill, pattern in _PATTERNS:
        if pattern.search(remaining):
            found.add(skill)
            remaining = pattern.sub(lambda m: " " * len(m.group(0)), remaining)
    return found


def compare(cv_text: str, job_text: str) -> dict:
    cv_skills = extract_skills(cv_text)
    job_skills = extract_skills(job_text)
    matched = cv_skills & job_skills
    missing = job_skills - cv_skills
    score = round(100 * len(matched) / len(job_skills)) if job_skills else None
    return {
        "score": score,
        "matched": _sorted(matched),
        "missing": _sorted(missing),
        "extra": _sorted(cv_skills - job_skills),
        "job_skills": _sorted(job_skills),
        "cv_skills": _sorted(cv_skills),
    }


def skill_demand(job_texts: list[str], cv_text: str = "") -> list[dict]:
    """How many postings ask for each skill, most requested first."""
    counts: dict[str, int] = {}
    for text in job_texts:
        for skill in extract_skills(text):
            counts[skill] = counts.get(skill, 0) + 1
    cv_skills = extract_skills(cv_text) if cv_text.strip() else None
    order = list(SKILL_CATEGORY)
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], order.index(kv[0])))
    return [
        {
            "skill": skill,
            "category": SKILL_CATEGORY[skill],
            "count": count,
            "share": round(100 * count / len(job_texts)),
            "in_cv": None if cv_skills is None else skill in cv_skills,
        }
        for skill, count in ranked
    ]


def _sorted(skills: set[str]) -> list[dict]:
    order = list(SKILL_CATEGORY)
    return [
        {"skill": s, "category": SKILL_CATEGORY[s]}
        for s in sorted(skills, key=order.index)
    ]
