"""Pre-baked demo content so the full UI can be previewed without spending API credit.
Three personas applying to the SAME backend job: a perfect fit, a partial fit, and no fit.
review/cover are Markdown strings; roles/dashboard/keywords/interview are dicts (the app
json.dumps them so the normal renderers can display them just like a real Claude response).
"""

JD = """Software Engineer - Platform Engineering

We are looking for a talented Software Engineer to join our Platform team. You will design,
build, and maintain scalable backend services and APIs.

Requirements:
- 3+ years building backend services in Python or Go
- Strong experience with REST APIs, microservices, and SQL/NoSQL databases
- Hands-on with AWS (EC2, S3, Lambda), Docker, and Kubernetes
- Familiarity with CI/CD, Git, and automated testing
- Bonus: experience with Kafka, Terraform, and observability tools
"""

# ---------------------------------------------------------------------------
# PERFECT MATCH
# ---------------------------------------------------------------------------
PERFECT_RESUME = """ARJUN SHARMA — Senior Backend Engineer
arjun.sharma@email.com | Bengaluru | github.com/arjuns

SUMMARY
Backend engineer with 5 years building high-throughput, cloud-native services for SaaS products.

EXPERIENCE
Senior Backend Engineer — Razorpay (2021–present)
- Designed Python / FastAPI microservices handling 20M+ API calls/day at p99 < 80ms.
- Containerised services with Docker and deployed on AWS EKS (Kubernetes); cut deploy time 60%.
- Built event-driven pipelines with Kafka; managed infrastructure as code with Terraform.
- Owned CI/CD (GitHub Actions), automated testing, and observability (Prometheus, Grafana).
Backend Engineer — Freshworks (2019–2021)
- Built REST APIs and microservices in Python (Django) over PostgreSQL and MongoDB.

SKILLS
Python, FastAPI, Django, REST APIs, Microservices, PostgreSQL, MongoDB, AWS (EC2/S3/Lambda/EKS),
Docker, Kubernetes, Kafka, Terraform, CI/CD, Git, automated testing

EDUCATION
B.Tech, Computer Science — IIT Roorkee
"""

PERFECT = {
    "label": "Perfect match",
    "badge": "✅",
    "name": "arjun_sharma_resume.pdf",
    "jd": JD,
    "resume": PERFECT_RESUME,
    "review": """## Overall Verdict
A near-ideal candidate for this role — the resume covers virtually every requirement with strong, quantified backend experience.

## Key Strengths
- **Directly relevant stack**: Python, FastAPI, Django, REST APIs, and microservices map 1:1 to the JD.
- **Cloud & DevOps depth**: hands-on AWS (EC2/S3/Lambda/EKS), Docker, Kubernetes, CI/CD, Terraform.
- **Impressive, quantified impact**: "20M+ API calls/day at p99 < 80ms" and "cut deploy time 60%".
- **Bonus tech covered**: Kafka, Terraform, and observability (Prometheus, Grafana).

## Gaps & Weaknesses
- The JD mentions **Go** as an alternative to Python — not on the resume (minor; Python satisfies the core need).
- No explicit mention of **Datadog**, though Prometheus/Grafana cover observability.

## Recommendations to Improve
- Add a one-line note on any Go exposure, even small.
- Lead the summary with the strongest metric for instant ATS impact.
""",
    "roles": {
        "candidate_summary": "Senior backend engineer with deep Python/cloud expertise and proven scale (20M+ calls/day). Strong fit for senior platform and backend roles.",
        "recommended_roles": [
            {"role": "Senior Backend Engineer — Platform", "justification": "Exact match for the JD: Python/FastAPI, microservices, AWS, Kubernetes.", "expected_ctc_inr": "28–38 LPA"},
            {"role": "Staff Software Engineer — Infrastructure", "justification": "Strong IaC (Terraform) and Kubernetes experience supports a step up.", "expected_ctc_inr": "35–48 LPA"},
            {"role": "Backend Tech Lead", "justification": "Quantified ownership and mentoring signals readiness to lead a small team.", "expected_ctc_inr": "32–45 LPA"},
        ],
    },
    "dashboard": {
        "overall_match": 92,
        "subscores": {"keywords": 90, "experience": 95, "education": 88, "skills": 94},
        "years_experience": 5,
        "matched_keywords": ["Python", "FastAPI", "Django", "REST APIs", "Microservices", "PostgreSQL",
                             "MongoDB", "AWS", "Docker", "Kubernetes", "Kafka", "Terraform", "CI/CD", "Git"],
        "missing_keywords": ["Go"],
        "summary": "Excellent fit — covers nearly every requirement with strong, quantified backend experience.",
    },
    "cover": """Dear Hiring Manager,

I'm excited to apply for the Software Engineer role on your Platform team. Over the past five years I've built high-throughput backend services in **Python and FastAPI**, including a microservice handling 20M+ API calls per day at p99 latency under 80ms.

Your requirements read like my day-to-day: I've deployed containerised services on **AWS EKS (Kubernetes)** with **Docker**, managed infrastructure with **Terraform**, built event pipelines on **Kafka**, and owned **CI/CD** and observability end to end. At Razorpay I cut deployment time by 60% while improving reliability.

I'd love to bring this experience to your Platform team and help scale your core services. Thank you for your consideration — I'd welcome the chance to discuss how I can contribute.

Warm regards,
Arjun Sharma
""",
    "keywords": {
        "matched": ["Python", "FastAPI", "Django", "REST APIs", "Microservices", "PostgreSQL", "MongoDB",
                    "AWS", "Docker", "Kubernetes", "Kafka", "Terraform", "CI/CD", "Git", "automated testing"],
        "missing": ["Go"],
    },
    "interview": {
        "questions": [
            {"question": "Walk me through the FastAPI service handling 20M+ calls/day — key architectural decisions?",
             "talking_point": "Cover your async design, connection pooling, caching, and how you hit p99 < 80ms."},
            {"question": "How did you approach the move to AWS EKS / Kubernetes?",
             "talking_point": "Mention the 60% deploy-time cut, rollout strategy, and resource limits/HPA."},
            {"question": "When would you reach for Kafka, and what trade-offs did you manage?",
             "talking_point": "Use a real event-pipeline example and discuss ordering/at-least-once delivery."},
            {"question": "How do you keep Terraform-managed infra safe and reviewable?",
             "talking_point": "Talk about modules, plan reviews in CI, and state management."},
            {"question": "How do you design for observability from day one?",
             "talking_point": "Reference Prometheus/Grafana, key SLOs, and alerting you set up."},
        ],
        "general_tips": [
            "Lead every answer with a quantified outcome.",
            "Be ready to whiteboard the 20M-calls/day architecture.",
            "Have one crisp Go-readiness line ready, since the JD mentions it.",
        ],
    },
}

# ---------------------------------------------------------------------------
# PARTIAL MATCH
# ---------------------------------------------------------------------------
PARTIAL_RESUME = """NEHA VERMA — Software Developer
neha.verma@email.com | Pune

SUMMARY
Full-stack developer with 2 years of experience, strongest on the frontend.

EXPERIENCE
Software Developer — SaaS Startup (2022–present)
- Built React frontends and Node.js / Express REST APIs.
- Wrote Python scripts for data processing; queried MySQL databases.
- Used Git for version control; basic experience with REST APIs and unit testing.

SKILLS
JavaScript, React, Node.js, Python (basic), REST APIs, MySQL, HTML/CSS, Git

EDUCATION
B.E., Information Technology — Pune University
"""

PARTIAL = {
    "label": "Half match",
    "badge": "🟡",
    "name": "neha_verma_resume.pdf",
    "jd": JD,
    "resume": PARTIAL_RESUME,
    "review": """## Overall Verdict
A partial fit. Solid fundamentals and some backend exposure, but missing the cloud, containerisation, and DevOps depth this platform role expects.

## Key Strengths
- Real REST API experience with **Node.js/Express** and some **Python**.
- Comfortable with **SQL (MySQL)** and **Git**, plus unit testing basics.
- Frontend strength (React) shows full-stack versatility.

## Gaps & Weaknesses
- **No cloud experience** — AWS (EC2/S3/Lambda) is a core requirement.
- **No Docker/Kubernetes** and no microservices at scale.
- Missing **CI/CD pipelines**, **Kafka**, and **Terraform**.
- Only ~2 years vs the 3+ requested.

## Recommendations to Improve
- Ship a small **Dockerised** project on **AWS** and add it to the resume.
- Build a microservice + CI/CD pipeline to demonstrate platform readiness.
- Reframe Python work to foreground backend (not just scripting).
""",
    "roles": {
        "candidate_summary": "Early-career full-stack developer, frontend-leaning, with foundational backend and SQL skills. Best suited to junior backend or full-stack roles with room to grow into platform work.",
        "recommended_roles": [
            {"role": "Junior Backend Developer", "justification": "REST API + Python/Node basics fit an entry backend role.", "expected_ctc_inr": "6–10 LPA"},
            {"role": "Full-Stack Developer (Mid)", "justification": "React + Node.js + SQL make full-stack a natural fit.", "expected_ctc_inr": "8–14 LPA"},
            {"role": "Associate Software Engineer — APIs", "justification": "Good launchpad to build cloud/DevOps depth on the job.", "expected_ctc_inr": "7–12 LPA"},
        ],
    },
    "dashboard": {
        "overall_match": 54,
        "subscores": {"keywords": 48, "experience": 55, "education": 80, "skills": 50},
        "years_experience": 2,
        "matched_keywords": ["Python", "JavaScript", "Node.js", "REST APIs", "SQL", "Git"],
        "missing_keywords": ["AWS", "Docker", "Kubernetes", "Microservices", "Kafka", "Terraform", "Go", "CI/CD", "NoSQL"],
        "summary": "Partial fit — solid fundamentals but missing the cloud, containerisation, and DevOps depth this role needs.",
    },
    "cover": """Dear Hiring Manager,

I'm writing to apply for the Software Engineer role on your Platform team. As a full-stack developer with two years' experience, I've built **REST APIs with Node.js and Python** and worked with **SQL** databases and **Git** day to day.

While my cloud and container experience is still growing, I'm a fast learner actively building skills in **Docker** and **AWS**, and I'm genuinely motivated to deepen my backend and platform expertise. I bring strong fundamentals, a full-stack perspective, and a track record of shipping features end to end.

I'd welcome the opportunity to discuss how I can contribute and grow with your team. Thank you for your consideration.

Best regards,
Neha Verma
""",
    "keywords": {
        "matched": ["Python", "JavaScript", "Node.js", "REST APIs", "SQL", "Git"],
        "missing": ["AWS", "Docker", "Kubernetes", "Microservices", "Kafka", "Terraform", "Go", "CI/CD", "automated testing"],
    },
    "interview": {
        "questions": [
            {"question": "Tell me about a REST API you built end to end.",
             "talking_point": "Use your Node.js/Express work; describe endpoints, validation, and error handling."},
            {"question": "How comfortable are you with cloud platforms like AWS?",
             "talking_point": "Be honest about current level and show what you're actively learning."},
            {"question": "What do you understand by microservices vs a monolith?",
             "talking_point": "Show conceptual clarity even without production experience."},
            {"question": "How would you containerise an app you've built?",
             "talking_point": "Walk through a basic Dockerfile and why containers help."},
            {"question": "Describe a bug you debugged in a backend service.",
             "talking_point": "Pick a Python/Node example and emphasise your systematic approach."},
        ],
        "general_tips": [
            "Frame your gaps as active learning, with a concrete example.",
            "Lead with backend work, not frontend, for this role.",
            "Have a small Dockerised/AWS side project ready to mention.",
        ],
    },
}

# ---------------------------------------------------------------------------
# NO MATCH
# ---------------------------------------------------------------------------
NONE_RESUME = """RITU MALHOTRA — Graphic Designer
ritu.malhotra@email.com | Delhi | behance.net/ritum

SUMMARY
Creative graphic designer with 4 years in branding and visual design.

EXPERIENCE
Senior Graphic Designer — Ad Agency (2020–present)
- Designed brand identities, marketing collateral, and social-media creatives.
- Built UI mockups and prototypes in Figma; led photo shoots and retouching.

SKILLS
Adobe Photoshop, Illustrator, InDesign, Figma, Branding, Typography, UI Mockups, Print Design

EDUCATION
Bachelor of Design — NID Ahmedabad
"""

NONE = {
    "label": "No match",
    "badge": "❌",
    "name": "ritu_malhotra_resume.pdf",
    "jd": JD,
    "resume": NONE_RESUME,
    "review": """## Overall Verdict
Not a match for this role. This is a graphic-design profile with no software engineering or backend experience against a backend platform job.

## Key Strengths
- Strong, relevant skills — **for design**: branding, typography, Figma, the Adobe suite.
- Clear creative impact and senior design experience.

## Gaps & Weaknesses
- **No programming experience** (no Python, Go, or any backend language).
- None of the core requirements present: REST APIs, databases, AWS, Docker, Kubernetes, CI/CD.
- The skill set belongs to a different career track entirely.

## Recommendations to Improve
- This role isn't aligned with the profile. Apply to **design / UX roles** instead (see Job Recommendations).
- If a switch to engineering is the goal, start with programming fundamentals and a small project portfolio before targeting platform roles.
""",
    "roles": {
        "candidate_summary": "Experienced graphic designer (branding, Figma, Adobe suite). Not suited to backend engineering; strongest fit is design and UX roles.",
        "recommended_roles": [
            {"role": "Senior Graphic Designer", "justification": "Directly matches 4 years of branding and visual-design experience.", "expected_ctc_inr": "8–14 LPA"},
            {"role": "UI / UX Designer", "justification": "Figma + UI mockup experience transfers well to product design.", "expected_ctc_inr": "10–18 LPA"},
            {"role": "Brand / Visual Designer", "justification": "Strong identity and typography skills fit brand-led teams.", "expected_ctc_inr": "9–15 LPA"},
        ],
    },
    "dashboard": {
        "overall_match": 11,
        "subscores": {"keywords": 6, "experience": 12, "education": 55, "skills": 8},
        "years_experience": 4,
        "matched_keywords": [],
        "missing_keywords": ["Python", "Go", "REST APIs", "Microservices", "SQL", "NoSQL", "AWS",
                             "Docker", "Kubernetes", "CI/CD", "Kafka", "Terraform", "Git"],
        "summary": "Not a match — a design profile with no backend engineering experience for this role.",
    },
    "cover": """Dear Hiring Manager,

I'm writing regarding the Software Engineer role on your Platform team. My background is in **graphic and visual design** — branding, typography, and UI design in Figma and the Adobe suite — rather than software engineering.

While I admire your team's work, I want to be transparent that my experience does not align with the backend requirements of this position (Python/Go, cloud, containers). I'd be glad to be considered for any **design or UX** openings where my skills would add real value.

Thank you for your time and consideration.

Sincerely,
Ritu Malhotra
""",
    "keywords": {
        "matched": [],
        "missing": ["Python", "Go", "REST APIs", "Microservices", "SQL", "NoSQL", "AWS",
                    "Docker", "Kubernetes", "CI/CD", "Kafka", "Terraform", "Git", "automated testing"],
    },
    "interview": {
        "questions": [
            {"question": "This is a backend engineering role — what draws you to it given your design background?",
             "talking_point": "Be honest: if pivoting, share your learning plan; otherwise target design roles."},
            {"question": "Do you have any programming experience?",
             "talking_point": "State your current level plainly; mention any self-study."},
            {"question": "How do you approach learning a brand-new, technical skill?",
             "talking_point": "Use a design example to show learning ability that could transfer."},
        ],
        "general_tips": [
            "This role isn't aligned with your profile — consider design/UX roles instead.",
            "If pivoting to engineering, build fundamentals and a project portfolio first.",
            "Lead with transferable strengths: visual problem-solving and user empathy.",
        ],
    },
}

DEMO = {"perfect": PERFECT, "partial": PARTIAL, "none": NONE}
