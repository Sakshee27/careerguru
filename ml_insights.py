"""Local ML engine for CareerGuru — instant, free insights with scikit-learn.

Everything here runs locally in milliseconds with no API calls:
  * instant_match()        — TF-IDF cosine similarity between resume and JD
  * skill_gap()            — taxonomy-based skill extraction + JD gap analysis
  * predict_career_tracks()— nearest-role matching against built-in role profiles
  * resume_quality()       — heuristic resume health score with a checklist
"""
import re

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# ---------------------------------------------------------------------------
# Skill taxonomy — grouped, lowercase. Multi-word skills are matched as phrases.
# ---------------------------------------------------------------------------
SKILL_TAXONOMY = {
    "Languages": [
        "python", "java", "javascript", "typescript", "go", "golang", "c++", "c#",
        "ruby", "php", "swift", "kotlin", "rust", "scala", "r", "matlab", "sql",
        "html", "css", "bash", "shell scripting", "dart", "perl",
    ],
    "Backend & APIs": [
        "node.js", "nodejs", "django", "flask", "fastapi", "spring boot", "spring",
        "express", "rest api", "rest apis", "restful", "graphql", "grpc",
        "microservices", "websockets", "celery", "rabbitmq", "kafka", "redis",
        "elasticsearch", "nginx", "oauth", "jwt",
    ],
    "Frontend": [
        "react", "react.js", "angular", "vue", "vue.js", "next.js", "nextjs",
        "svelte", "redux", "tailwind", "bootstrap", "sass", "webpack", "vite",
        "jquery", "responsive design",
    ],
    "Design": [
        "figma", "sketch", "adobe xd", "photoshop", "illustrator", "canva",
        "wireframes", "wireframing", "prototyping", "prototypes", "mockups",
        "user research", "design systems", "usability", "interaction design",
        "visual design", "ui/ux", "ux design", "ui design",
    ],
    "Mobile": [
        "android", "ios", "react native", "flutter", "swiftui", "jetpack compose",
        "mobile development", "app store", "play store",
    ],
    "Data & ML": [
        "machine learning", "deep learning", "nlp", "computer vision", "pandas",
        "numpy", "scikit-learn", "sklearn", "tensorflow", "pytorch", "keras",
        "xgboost", "data analysis", "data science", "statistics", "etl",
        "data engineering", "spark", "hadoop", "airflow", "power bi", "tableau",
        "data visualization", "a/b testing", "llm", "generative ai", "langchain",
        "hugging face", "opencv", "recommendation systems", "time series",
    ],
    "Databases": [
        "postgresql", "postgres", "mysql", "mongodb", "sqlite", "oracle",
        "dynamodb", "cassandra", "snowflake", "bigquery", "redshift", "neo4j",
        "nosql", "database design",
    ],
    "Cloud & DevOps": [
        "aws", "azure", "gcp", "google cloud", "ec2", "s3", "lambda", "docker",
        "kubernetes", "terraform", "ansible", "jenkins", "ci/cd", "git", "github",
        "gitlab", "linux", "monitoring", "prometheus", "grafana", "serverless",
        "cloudformation", "helm", "devops",
    ],
    "Testing & Quality": [
        "unit testing", "pytest", "jest", "selenium", "cypress", "junit",
        "integration testing", "tdd", "automated testing", "qa", "test automation",
        "load testing", "postman",
    ],
    "Practices & Soft Skills": [
        "agile", "scrum", "kanban", "jira", "project management", "leadership",
        "mentoring", "communication", "stakeholder management", "problem solving",
        "team management", "code review", "documentation", "cross-functional",
        "product management", "customer success", "presentation",
    ],
}

_ALL_SKILLS = sorted(
    {(cat, s) for cat, skills in SKILL_TAXONOMY.items() for s in skills},
    key=lambda x: -len(x[1]),  # longest first so "react.js" wins over "react"
)


# ---------------------------------------------------------------------------
# Built-in role profiles for career-track prediction (nearest-neighbour match)
# ---------------------------------------------------------------------------
ROLE_PROFILES = {
    "Backend Engineer": "python java go backend services rest api microservices sql postgresql redis kafka docker kubernetes aws scalable distributed systems caching authentication server",
    "Frontend Engineer": "javascript typescript react angular vue html css responsive ui components state management redux next.js webpack accessibility design systems user interface",
    "Full-Stack Developer": "javascript python react node.js full stack rest api database frontend backend html css express mongodb postgresql deployment end to end web application",
    "Data Scientist": "python machine learning statistics pandas numpy scikit-learn model training feature engineering regression classification deep learning experiments hypothesis a/b testing insights",
    "Data Engineer": "etl pipelines spark airflow kafka data warehouse snowflake bigquery sql python batch streaming ingestion transformation orchestration data lake schema",
    "ML Engineer": "machine learning deployment tensorflow pytorch mlops model serving inference pipelines feature store monitoring gpu training production llm fine-tuning embeddings",
    "DevOps / SRE": "kubernetes docker terraform ci/cd jenkins aws monitoring prometheus grafana incident reliability automation infrastructure as code linux scaling deployment pipelines",
    "Mobile Developer": "android ios swift kotlin react native flutter mobile app store ui mobile development push notifications offline performance",
    "QA / Test Engineer": "test automation selenium cypress pytest quality assurance regression test plans bug tracking ci integration manual testing api testing coverage",
    "Product Manager": "product roadmap stakeholders requirements user research prioritization metrics kpis agile backlog discovery go-to-market strategy customer feedback analytics",
    "Data / Business Analyst": "sql excel dashboards tableau power bi reporting kpis insights data analysis stakeholder requirements visualization metrics trends business intelligence",
    "UI/UX Designer": "figma wireframes prototypes user research design systems usability accessibility visual design interaction design mockups personas journey mapping",
    "Cloud Architect": "aws azure gcp architecture design cloud migration cost optimization security networking vpc landing zone scalability high availability disaster recovery",
    "Security Engineer": "security vulnerabilities penetration testing owasp encryption authentication compliance siem incident response threat modeling network security audits",
}


_WORD_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9+#./-]*")


def _profile_skill_sets():
    return {name: frozenset(s for v in extract_skills(text).values() for s in v)
            for name, text in ROLE_PROFILES.items()}


def _clean(text):
    return re.sub(r"\s+", " ", (text or "")).strip().lower()


def instant_match(resume_text, jd_text):
    """TF-IDF cosine similarity between resume and JD, scaled to 0-100.

    Raw cosine on short docs is conservative, so apply a gentle curve that
    maps typical good matches (~0.4-0.6 raw) into an intuitive 70-90 band.
    """
    r, j = _clean(resume_text), _clean(jd_text)
    if not r or not j:
        return None
    vec = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), sublinear_tf=True)
    try:
        m = vec.fit_transform([r, j])
    except ValueError:
        return None
    sim = float(cosine_similarity(m[0], m[1])[0][0])
    return round(min(1.0, sim ** 0.45) * 100)


def extract_skills(text):
    """Return {category: [skills found]} using word-boundary phrase matching."""
    t = " " + _clean(text) + " "
    found = {}
    for cat, skill in _ALL_SKILLS:
        pat = r"(?<![a-z0-9+#])" + re.escape(skill) + r"(?![a-z0-9+#])"
        if re.search(pat, t):
            found.setdefault(cat, []).append(skill)
    return found


# Taxonomy skills present in each role profile — used for overlap scoring.
_PROFILE_SKILLS = _profile_skill_sets()


def skill_gap(resume_text, jd_text):
    """Compare JD-required skills vs resume skills.

    Returns {"matched": {...}, "missing": {...}, "extra": {...}, "coverage": pct|None}
    """
    rs = extract_skills(resume_text)
    js = extract_skills(jd_text)
    r_flat = {s for v in rs.values() for s in v}
    matched, missing = {}, {}
    n_match = n_total = 0
    for cat, skills in js.items():
        for s in skills:
            n_total += 1
            if s in r_flat:
                matched.setdefault(cat, []).append(s)
                n_match += 1
            else:
                missing.setdefault(cat, []).append(s)
    j_flat = {s for v in js.values() for s in v}
    extra = {cat: [s for s in v if s not in j_flat] for cat, v in rs.items()}
    extra = {c: v for c, v in extra.items() if v}
    coverage = round(n_match / n_total * 100) if n_total else None
    return {"matched": matched, "missing": missing, "extra": extra,
            "coverage": coverage, "resume_skills": rs}


def predict_career_tracks(resume_text, top_n=3):
    """Rank built-in role profiles against the resume.

    Blends TF-IDF cosine similarity (word-level) with hard skill overlap
    (taxonomy-level) so a sparse resume can't drift to a noisy neighbour,
    and drops tracks whose signal is negligible rather than padding to
    top_n — better one confident track than three guesses.
    """
    r = _clean(resume_text)
    if not r:
        return []
    names = list(ROLE_PROFILES)
    docs = [r] + [ROLE_PROFILES[n] for n in names]
    vec = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), sublinear_tf=True)
    m = vec.fit_transform(docs)
    sims = cosine_similarity(m[0], m[1:])[0]

    rskills = {s for v in extract_skills(resume_text).values() for s in v}
    best_sim = max(float(s) for s in sims) or 1e-9
    scored = []
    for name, sim in zip(names, sims):
        pskills = _PROFILE_SKILLS[name]
        inter = len(rskills & pskills)
        overlap = inter / max(1, min(len(rskills) or 1, len(pskills) or 1))
        blend = 0.55 * (float(sim) / best_sim) + 0.45 * overlap
        scored.append((name, blend, float(sim), overlap))
    scored.sort(key=lambda x: -x[1])

    best_blend = scored[0][1] or 1e-9
    # Confidence of the headline track: absolute similarity + skill evidence.
    conf = min(1.0, best_sim ** (1 / 3) + 0.3 * scored[0][3])
    out = []
    for name, blend, sim, overlap in scored[:top_n]:
        # Skip noise: well below the leader, or no skill evidence at all.
        if blend < 0.3 * best_blend or (sim < 0.02 and overlap == 0):
            continue
        out.append({"role": name, "score": round((blend / best_blend) * conf * 100)})
    return out


_ACTION_VERBS = {
    "achieved", "architected", "automated", "built", "created", "delivered",
    "designed", "developed", "drove", "engineered", "implemented", "improved",
    "increased", "launched", "led", "managed", "mentored", "migrated",
    "optimized", "optimised", "owned", "reduced", "refactored", "scaled",
    "shipped", "spearheaded", "streamlined",
}

_SECTIONS = {
    "experience": r"\b(work\s+)?experience\b|\bemployment\b",
    "education": r"\beducation\b|\bacademic\b|\bb\.?tech\b|\bdegree\b",
    "skills": r"\bskills\b|\btechnologies\b|\btech\s+stack\b",
    "summary": r"\bsummary\b|\bprofile\b|\bobjective\b|\babout\b",
}


def resume_quality(resume_text):
    """Heuristic resume health check. Returns {"score": 0-100, "checks": [...]}."""
    text = resume_text or ""
    low = text.lower()
    words = _WORD_RE.findall(low)
    n_words = len(words)
    checks = []

    def add(label, status, detail):
        checks.append({"label": label, "status": status, "detail": detail})

    # Length
    if 250 <= n_words <= 1100:
        add("Length", "pass", f"{n_words} words — in the ideal 1–2 page range.")
    elif n_words < 250:
        add("Length", "fail", f"Only {n_words} words — too thin; add detail to your experience.")
    else:
        add("Length", "warn", f"{n_words} words — consider trimming to keep it under 2 pages.")

    # Contact info
    has_email = bool(re.search(r"[^@\s]+@[^@\s]+\.[^@\s]+", text))
    has_phone = bool(re.search(r"(\+?\d[\d\s().-]{8,}\d)", text))
    if has_email and has_phone:
        add("Contact info", "pass", "Email and phone number found.")
    elif has_email or has_phone:
        add("Contact info", "warn", "Only one contact method found — add both email and phone.")
    else:
        add("Contact info", "fail", "No email or phone detected — recruiters can't reach you.")

    # Quantified impact
    lines = [l for l in text.splitlines() if len(l.strip()) > 25]
    metric_lines = [l for l in lines if re.search(r"\d+\s*%|\$\s?\d|₹\s?\d|\b\d+[kKxX]\b|\b\d{2,}\b", l)]
    ratio = (len(metric_lines) / len(lines)) if lines else 0
    if ratio >= 0.35:
        add("Quantified impact", "pass", f"{round(ratio*100)}% of bullets carry numbers — strong evidence of impact.")
    elif ratio >= 0.15:
        add("Quantified impact", "warn", f"Only {round(ratio*100)}% of bullets have numbers — add metrics (%, ₹, counts).")
    else:
        add("Quantified impact", "fail", "Almost no quantified results — numbers make achievements credible.")

    # Action verbs
    verbs = sorted({w for w in words if w in _ACTION_VERBS})
    if len(verbs) >= 6:
        add("Action verbs", "pass", f"{len(verbs)} strong verbs ({', '.join(verbs[:5])}…).")
    elif len(verbs) >= 3:
        add("Action verbs", "warn", f"Only {len(verbs)} strong verbs — open more bullets with built / led / shipped.")
    else:
        add("Action verbs", "fail", "Bullets lack strong action verbs — avoid 'responsible for…'.")

    # Sections
    missing_secs = [name for name, pat in _SECTIONS.items() if not re.search(pat, low)]
    if not missing_secs:
        add("Core sections", "pass", "Experience, education, skills and summary all present.")
    elif len(missing_secs) <= 1:
        add("Core sections", "warn", f"Missing a '{missing_secs[0]}' section.")
    else:
        add("Core sections", "fail", "Missing sections: " + ", ".join(missing_secs) + ".")

    # Links / portfolio
    if re.search(r"linkedin\.com|github\.com|gitlab\.com|portfolio|behance|dribbble", low):
        add("Online presence", "pass", "LinkedIn/GitHub/portfolio link found.")
    else:
        add("Online presence", "warn", "No LinkedIn or GitHub link — most recruiters look for one.")

    pts = {"pass": 1.0, "warn": 0.5, "fail": 0.0}
    score = round(sum(pts[c["status"]] for c in checks) / len(checks) * 100)
    return {"score": score, "checks": checks}


def analyze(resume_text, jd_text=""):
    """One-call bundle used by the Instant Insights tab.

    The headline match blends semantic similarity (40%) with hard skill
    coverage (60%) — cosine alone underrates good matches on short documents.
    """
    has_jd = bool((jd_text or "").strip())
    cos = instant_match(resume_text, jd_text) if has_jd else None
    gap = skill_gap(resume_text, jd_text) if has_jd else None
    match = None
    if cos is not None:
        if gap and gap["coverage"] is not None:
            match = round(0.4 * cos + 0.6 * gap["coverage"])
        else:
            match = cos
    return {
        "match": match,
        "gap": gap,
        "tracks": predict_career_tracks(resume_text),
        "quality": resume_quality(resume_text),
        "resume_skills": extract_skills(resume_text),
    }
