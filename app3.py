from dotenv import load_dotenv
load_dotenv(override=True)

import os
import re
import json
import html
import time
import base64
import datetime

import streamlit as st
import PyPDF2

# When deployed (e.g. Streamlit Community Cloud), secrets come from st.secrets
# rather than a .env file — mirror them into the environment so os.getenv works.
try:
    for _k in ("GOOGLE_API_KEY", "DATABASE_URL"):
        if not os.getenv(_k) and _k in st.secrets:
            os.environ[_k] = str(st.secrets[_k])
except Exception:
    pass

from demo_data import DEMO
import db

try:
    import altair as alt
    import pandas as pd
    HAVE_CHARTS = True
except Exception:
    HAVE_CHARTS = False


def _load_logo():
    try:
        path = os.path.join(os.path.dirname(__file__), "logo.svg")
        with open(path, "r", encoding="utf-8") as f:
            svg = f.read()
        return svg
    except Exception:
        return "🎓"


LOGO_SVG = _load_logo()
from google import genai
from google.genai import types
gemini_client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
GEMINI_MODEL = "gemini-2.5-flash"


@st.cache_resource
def _ensure_db():
    """Create the users table once per app process."""
    try:
        db.init_db()
        return True
    except Exception:  # noqa: BLE001 — app still usable without auth
        return False


_DB_READY = _ensure_db()


# ----------------------------------------------------------------------------
# Core logic
# ----------------------------------------------------------------------------
# Primary model first, then fallbacks if it's overloaded/unavailable.
GEMINI_FALLBACKS = ["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-flash-latest"]


def get_claude_response(prompt, pdf_text, job_description, max_tokens=4000):
    """Run an analysis via Google Gemini (free tier), retrying on overload."""
    contents = f"{prompt}\n\nJob Description:\n{job_description}\n\nResume Content:\n{pdf_text}"
    cfg = types.GenerateContentConfig(
        system_instruction="You are an expert ATS (Applicant Tracking System) and career advisor.",
        max_output_tokens=max_tokens,
        thinking_config=types.ThinkingConfig(thinking_budget=0),
    )
    models = [GEMINI_MODEL] + [m for m in GEMINI_FALLBACKS if m != GEMINI_MODEL]
    last_err = None
    for model in models:
        for attempt in range(3):
            try:
                resp = gemini_client.models.generate_content(model=model, contents=contents, config=cfg)
                if resp.text:
                    return resp.text
                last_err = RuntimeError("Empty response from model.")
                break  # empty -> try next model, don't retry same
            except Exception as e:  # noqa: BLE001
                last_err = e
                msg = str(e)
                # Retry only transient overload/unavailable; otherwise move to next model.
                if ("503" in msg or "UNAVAILABLE" in msg or "overloaded" in msg.lower()
                        or "high demand" in msg.lower() or "429" in msg):
                    time.sleep(1.5 * (attempt + 1))
                    continue
                break  # non-transient (e.g. 403) -> next model
    raise RuntimeError(
        "Gemini is temporarily overloaded across models. Please click Generate again in a few seconds. "
        f"(last error: {last_err})"
    )


def extract_pdf_text(uploaded_file):
    if uploaded_file is None:
        raise FileNotFoundError("No file uploaded")
    try:
        uploaded_file.seek(0)
    except Exception:
        pass
    reader = PyPDF2.PdfReader(uploaded_file)
    if len(reader.pages) == 0:
        raise RuntimeError("PDF contains no pages")
    texts = [p.extract_text() for p in reader.pages if p.extract_text()]
    full_text = "\n".join(texts).strip()
    if not full_text:
        raise RuntimeError("No extractable text found in PDF. If it's a scanned image, OCR it first.")
    return full_text


def try_parse_json(text):
    cleaned = re.sub(r"```$", "", re.sub(r"^```(?:json)?", "", text.strip()).strip()).strip()
    s, e = cleaned.find("{"), cleaned.rfind("}")
    if s != -1 and e != -1 and e > s:
        cleaned = cleaned[s:e + 1]
    try:
        return json.loads(cleaned)
    except Exception:
        return None


def score_color(v):
    return "#10B981" if v >= 75 else "#F59E0B" if v >= 50 else "#EF4444"


# ----------------------------------------------------------------------------
# Prompts / tools
# ----------------------------------------------------------------------------
PROMPTS = {
    "review": "You are an experienced Technical HR Manager. Review the resume against the job description. "
              "Use Markdown with: ## Overall Verdict, ## Key Strengths, ## Gaps & Weaknesses, ## Recommendations to Improve. Be specific.",
    "roles": 'You are a career advisor. Return ONLY valid JSON: {"candidate_summary":"...","recommended_roles":'
             '[{"role":"...","justification":"...","expected_ctc_inr":"6-8 LPA"}]}. 3-5 roles, India salary ranges.',
    "dashboard": 'ATS scanner. Return ONLY valid JSON: {"overall_match":<0-100>,"subscores":{"keywords":<0-100>,'
                 '"experience":<0-100>,"education":<0-100>,"skills":<0-100>},"years_experience":<number>,'
                 '"matched_keywords":[up to 15],"missing_keywords":[up to 15],"summary":"1-2 sentences"}. Short keywords.',
    "cover": "Write a tailored, in-depth cover letter (450-600 words, first person, confident). "
             "Greeting 'Dear Hiring Manager,' if no name. Use 4-5 substantial paragraphs: a strong hook, "
             "2-3 body paragraphs with specific achievements and quantified impact mapped to the job's key "
             "requirements, a paragraph on culture/motivation fit, and a confident closing with a call to action. "
             "Return ONLY the letter in Markdown.",
    "interview": 'Interview coach. Return ONLY valid JSON: {"questions":[{"question":"...","talking_point":'
                 '"point from THIS resume"}],"general_tips":[...]}. 6-8 questions, technical + behavioral.',
}
SPINNERS = {"review": "Reviewing your resume…", "roles": "Finding roles that fit…",
            "dashboard": "Scoring your ATS match…", "cover": "Drafting your cover letter…",
            "interview": "Preparing interview questions…"}
MAXTOK = {"cover": 2400}

TOOLS = [
    ("review", "fact_check", "Resume Review", "A candid, recruiter-style read on your fit — strengths, gaps, and how to fix them."),
    ("roles", "work", "Job Recommendations", "The roles that suit your profile best, each with an expected salary range."),
    ("dashboard", "dashboard", "Match Dashboard", "An ATS score with sub-scores, a coverage chart, and matched vs. missing keywords."),
    ("cover", "edit_document", "Cover Letter", "A tailored, ready-to-send cover letter from your resume and the job post."),
    ("interview", "mic", "Interview Prep", "Likely interview questions plus the exact points from your resume to bring up."),
]
TOOL_BY_KEY = {t[0]: t for t in TOOLS}


# ----------------------------------------------------------------------------
# Page config + styling
# ----------------------------------------------------------------------------
st.set_page_config(page_title="CareerGuru", page_icon="🎓", layout="wide")

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Sora:wght@500;600;700;800&family=Manrope:wght@400;500;600;700&display=swap');
    @import url('https://fonts.googleapis.com/css2?family=Material+Symbols+Rounded:opsz,wght,FILL,GRAD@24,400,0,0');
    .mi{ font-family:'Material Symbols Rounded'; font-size:1.05rem; vertical-align:-3px; color:#10B981; }

    /* Tab/page title — prominent header above results */
    .page-title{ font-family:'Sora',sans-serif; font-weight:800; font-size:1.9rem; letter-spacing:-0.02em;
        color:#0F172A; display:flex; align-items:center; gap:11px; margin:0.2rem 0; }
    .page-title .mi{ font-size:1.7rem; vertical-align:0; color:#10B981; }

    /* Resume Review report — styled section cards instead of raw markdown */
    [class*="st-key-rc_"] [data-testid="stVerticalBlockBorderWrapper"], [class*="st-key-rc_"]{
        background:#FFFFFF !important; border:1px solid #E7E9EF !important; border-radius:14px !important;
        box-shadow:0 6px 18px rgba(17,24,39,0.05) !important; padding:1.1rem 1.3rem !important; margin-bottom:0.4rem; }
    .report-h{ font-family:'Sora',sans-serif; font-weight:700; font-size:1.02rem; letter-spacing:0.01em;
        color:#0F172A; display:flex; align-items:center; gap:9px; margin:0 0 0.55rem; padding-bottom:0.55rem;
        border-bottom:1px solid #EEF1F5; }
    .report-h .mi{ font-size:1.15rem; color:#10B981; }
    [class*="st-key-rc_"] p{ color:#374151; font-size:0.95rem; line-height:1.6; margin:0.2rem 0; }
    [class*="st-key-rc_"] li{ color:#374151; font-size:0.95rem; line-height:1.55; }
    [class*="st-key-rc_"] li::marker{ color:#10B981; }
    [class*="st-key-rc_"] strong{ color:#0F172A; }
    /* Color-tint the Gaps and Recommendations section headers */
    .st-key-rc_gapsweaknesses .report-h .mi{ color:#F59E0B; }
    .st-key-rc_recommendationstoimprove .report-h .mi{ color:#7C3AED; }
    .st-key-rc_keywordcoverage .report-h .mi{ color:#7C3AED; }
    /* Equal-height side-by-side cards — target the keyed inner block directly */
    .st-key-rc_scorebreakdown, .st-key-rc_keywordcoverage{
        min-height:340px !important; justify-content:center !important; }
    /* Center the donut horizontally in its card */
    .st-key-rc_keywordcoverage [data-testid="stVegaLiteChart"]{ display:flex; justify-content:center; }
    /* Matched / Missing sub-labels inside the keyword card */
    .kw-sub{ display:flex; align-items:center; gap:6px; font-family:'Sora',sans-serif; font-weight:700;
        font-size:0.82rem; text-transform:uppercase; letter-spacing:0.06em; margin:0.7rem 0 0.4rem; }
    .kw-sub .mi{ font-size:1rem; }
    .kw-sub-ok{ color:#047857; } .kw-sub-ok .mi{ color:#10B981; }
    .kw-sub-miss{ color:#B91C1C; } .kw-sub-miss .mi{ color:#EF4444; }
    .st-key-rc_keywords{ padding-bottom:1.8rem !important; }
    /* Cover letter — larger, letter-like reading size */
    .st-key-rc_coverletter{ padding:1.8rem 2.2rem !important; }
    .st-key-rc_coverletter p, .st-key-rc_coverletter li{ font-size:1.05rem !important; line-height:1.8 !important; color:#1F2937 !important; }
    .st-key-rc_coverletter h1, .st-key-rc_coverletter h2, .st-key-rc_coverletter h3{ font-size:1.25rem !important; }
    .bigic{ font-family:'Material Symbols Rounded'; font-size:54px; color:#10B981; line-height:1; }
    html, body, [class*="css"], .stApp, .stMarkdown, p, span, div, label, input, textarea { font-family:'Manrope',sans-serif; }
    h1,h2,h3,h4,.guru-title { font-family:'Sora',sans-serif !important; letter-spacing:-0.01em; color:#111827; }

    .stApp { background:
        radial-gradient(1200px 600px at 6% -12%, rgba(16,185,129,0.18), transparent 60%),
        radial-gradient(1000px 600px at 104% 112%, rgba(124,58,237,0.16), transparent 55%),
        radial-gradient(900px 500px at 95% -10%, rgba(56,189,248,0.10), transparent 60%),
        #F6F8FB; background-attachment:fixed; }
    [data-testid="stHeader"]{ background:transparent; }
    [data-testid="stHeaderActionElements"]{display:none;} #MainMenu,footer{visibility:hidden;}
    [data-testid="stToolbar"]{right:1rem;}
    [data-testid="stStatusWidget"]{display:none;}
    .block-container{ padding-top:3.2rem; padding-left:clamp(1.5rem,6vw,7rem); padding-right:clamp(1.5rem,6vw,7rem); max-width:100%; animation:cgfade 0.22s ease; }
    @keyframes cgfade{ from{opacity:0.55;} to{opacity:1;} }
    @keyframes fadeUp{ from{opacity:0; transform:translateY(10px);} to{opacity:1; transform:none;} }
    @keyframes shine{ to{ background-position:200% center; } }
    @keyframes floaty{ 0%,100%{ transform:translateY(0);} 50%{ transform:translateY(-3px);} }
    @keyframes growx{ from{ width:0; } }

    /* Top bar */
    /* Hide Streamlit's Deploy button */
    [data-testid="stAppDeployButton"]{ display:none !important; }

    /* Back-to-home arrow — nudged into the left gutter, aligned with the brand */
    [data-testid="stMainBlockContainer"], .block-container{ position:relative !important; overflow:visible !important; }
    .st-key-back_home{ margin-left:-3rem !important; }
    /* Pull the brand back so the arrow column doesn't shove it right */
    .topbar-ws{ margin-left:-3rem !important; }
    .st-key-back_home button{ border-radius:50% !important; width:44px !important; height:44px !important; min-width:44px !important;
        padding:0 !important; background:#FFFFFF !important; border:1px solid #E2E6EE !important;
        color:#334155 !important; box-shadow:0 4px 12px rgba(17,24,39,0.07) !important; }
    .st-key-back_home button:hover{ border-color:#10B981 !important; color:#059669 !important;
        transform:translateX(-2px); box-shadow:0 8px 18px rgba(16,185,129,0.18) !important; }
    .st-key-back_home button p{ display:none !important; }

    /* Sign in button (landing, top-right) — boxed, pushed up & right */
    /* Let clicks pass through the transparent Streamlit header bar to the Sign in button under it */
    [data-testid="stHeader"]{ pointer-events:none !important; }
    [data-testid="stHeader"] *{ pointer-events:auto !important; }
    .st-key-signin_btn{ position:absolute !important; top:1.5rem !important; right:1.5rem !important;
        z-index:1000000 !important; margin:0 !important; width:auto !important; pointer-events:auto !important; }
    .st-key-signin_btn button{ border-radius:6px !important; font-weight:600 !important;
        width:auto !important; padding:0.4rem 1rem !important; }
    /* Signed-in user chip — same top-right spot as the Sign in button */
    .st-key-userchip{ position:absolute !important; top:1.5rem !important; right:1.5rem !important;
        left:auto !important; width:auto !important; z-index:1000000 !important; margin:0 !important;
        pointer-events:auto !important; }
    .st-key-userchip [data-testid="stPopover"],
    .st-key-userchip [data-testid="stPopover"] > div{ width:auto !important; }
    .st-key-userchip > div > [data-testid="stPopover"] button{ border-radius:6px !important; font-weight:600 !important;
        width:auto !important; padding:0.4rem 1rem !important; background:#FFFFFF !important;
        border:1px solid #E2E6EE !important; color:#1F2937 !important; box-shadow:0 4px 12px rgba(17,24,39,0.07) !important; }
    /* Account menu (inside the popover) */
    .acct-head{ display:flex; align-items:center; gap:11px; margin-bottom:0.6rem; }
    .acct-avatar{ width:42px; height:42px; border-radius:50%; flex:0 0 auto; display:flex; align-items:center; justify-content:center;
        font-family:'Sora',sans-serif; font-weight:800; font-size:1.1rem; color:#fff;
        background:linear-gradient(135deg,#10B981,#7C3AED); }
    .acct-name{ font-family:'Sora',sans-serif; font-weight:700; font-size:1rem; color:#0F172A; }
    .acct-email{ font-size:0.82rem; color:#6B7280; }
    .acct-row{ display:flex; align-items:center; gap:7px; font-size:0.85rem; color:#6B7280; margin:0.1rem 0; }
    .acct-row .mi{ font-size:1rem; color:#94A3B8; }

    .topbar{ display:flex; align-items:center; gap:12px; margin-bottom:1.2rem; }
    .topbar .logo{ width:44px; height:44px; flex:0 0 auto; animation:floaty 4.5s ease-in-out infinite; }
    .topbar .logo svg{ width:100%; height:100%; display:block; }
    .brand{ font-family:'Sora',sans-serif; font-weight:800; font-size:1.6rem; line-height:1.5;
        display:inline-block; padding:0 6px 0.12em 0;
        background:linear-gradient(90deg,#10B981,#34D399 40%,#7C3AED 110%); background-size:200% auto;
        -webkit-background-clip:text; -webkit-text-fill-color:transparent; background-clip:text;
        animation:shine 7s linear infinite; }
    .ai-pill{ font-size:0.68rem; font-weight:700; letter-spacing:0.08em; color:#fff;
        background:linear-gradient(90deg,#10B981,#34D399); padding:3px 10px; border-radius:99px; box-shadow:0 4px 10px rgba(16,185,129,0.3); }
    .spacer{ flex:1; }

    .section-label{ font-family:'Sora',sans-serif; font-weight:700; font-size:0.76rem; text-transform:uppercase;
        letter-spacing:0.13em; color:#059669; margin:0.2rem 0 0.5rem 0; }

    [data-testid="stVerticalBlockBorderWrapper"]{ background:#FFFFFF;
        border:1px solid #E7E9EF !important; border-radius:16px; box-shadow:0 8px 24px rgba(17,24,39,0.06); }

    .stTextArea textarea{ background:#F9FAFB; border:1px solid #E5E7EB; border-radius:12px; color:#111827; font-size:0.95rem; }
    .stTextArea textarea:focus{ border-color:#10B981; box-shadow:0 0 0 3px rgba(16,185,129,0.15); background:#fff; }
    .stTextArea textarea::placeholder{ color:#9CA3AF; }
    [data-testid="stFileUploaderDropzone"]{ background:#F4FBF8; border:2px dashed rgba(16,185,129,0.5);
        border-radius:16px; min-height:180px; display:flex; flex-direction:column; align-items:center; justify-content:center;
        gap:8px; transition:all 0.18s ease; }
    [data-testid="stFileUploaderDropzone"]:hover{ background:#ECF9F3; border-color:#10B981; transform:translateY(-2px);
        box-shadow:0 12px 28px rgba(16,185,129,0.14); }
    [data-testid="stFileUploaderDropzone"]::before{ content:"cloud_upload"; font-family:'Material Symbols Rounded';
        font-size:2.8rem; color:#10B981; line-height:1; }
    [data-testid="stFileUploaderDropzone"] button{ border-radius:10px !important; font-weight:600 !important; }
    .opt{ color:#9CA3AF; font-weight:500; text-transform:none; letter-spacing:0; }

    /* Distinct upload card background */
    .st-key-uploadcard [data-testid="stVerticalBlockBorderWrapper"], .st-key-uploadcard{
        background:linear-gradient(180deg,#E2E6F7 0%, #D2D8F0 100%) !important;
        border:1px solid rgba(124,58,237,0.32) !important;
        box-shadow:none !important; }

    /* Right-column extras under the preview */
    .art-extra{ margin-top:1.6rem; animation:fadeUp 0.6s ease both; }
    .rating{ color:#F59E0B; font-size:1.05rem; font-weight:700; letter-spacing:2px; }
    .rating span{ color:#6B7280; font-weight:600; font-size:0.85rem; letter-spacing:0; margin-left:8px; }
    .art-list{ margin-top:1rem; }
    .art-list > div{ display:flex; align-items:center; gap:9px; color:#374151; font-size:0.95rem; padding:6px 0; }
    .art-list .mi{ color:#10B981; }
    .quote-card{ margin-top:1.4rem; background:#fff; border:1px solid #E7E9EF; border-radius:16px; padding:1.2rem 1.35rem; box-shadow:0 8px 24px rgba(17,24,39,0.06); }
    .quote-card .q{ color:#374151; font-size:0.96rem; line-height:1.6; font-style:italic; }
    .quote-card .q-by{ color:#059669; font-weight:700; font-size:0.85rem; margin-top:0.7rem; }

    .stButton > button{ border-radius:12px; font-family:'Sora',sans-serif; font-weight:600; font-size:0.9rem;
        padding:0.55rem 0.6rem; border:1px solid #E5E7EB; background:#FFFFFF; color:#374151; transition:all 0.15s ease; box-shadow:0 1px 2px rgba(17,24,39,0.04); }
    .stButton > button:hover{ border-color:#10B981; color:#047857; transform:translateY(-1px); box-shadow:0 8px 20px rgba(16,185,129,0.16); }
    .stButton button[kind="primary"]{ background:linear-gradient(90deg,#10B981,#059669); color:#fff; border:none; box-shadow:0 6px 16px rgba(16,185,129,0.3); }
    .stButton button[kind="primary"]:hover{ background:linear-gradient(90deg,#34D399,#10B981); color:#fff; transform:translateY(-1px); }
    .stDownloadButton > button{ border-radius:10px; font-weight:600; background:#fff; border:1px solid rgba(124,58,237,0.4); color:#7C3AED; }
    .stDownloadButton > button:hover{ border-color:#7C3AED; color:#6D28D9; background:#F5F3FF; }

    /* Collapse / expand arrow buttons */
    .st-key-collapse_btn button, .st-key-expand_btn button{
        background:transparent !important; border:none !important; box-shadow:none !important;
        color:#10B981 !important; padding:0.1rem 0.25rem !important; min-height:0 !important; transition:transform 0.12s ease, color 0.12s ease; }
    .st-key-collapse_btn button:hover, .st-key-expand_btn button:hover{
        background:transparent !important; color:#7C3AED !important; transform:scale(1.18); }
    .st-key-collapse_btn [data-testid="stIconMaterial"], .st-key-expand_btn [data-testid="stIconMaterial"]{ font-size:1.7rem !important; }

    /* Segmented control (tools) — centered, no background band */
    [data-testid="stButtonGroup"]{ width:fit-content !important; max-width:100%; margin:0 auto !important;
        flex-wrap:nowrap !important; overflow-x:auto; justify-content:center !important;
        background:transparent !important; border:none !important; box-shadow:none !important;
        padding:0 0 3px !important; }
    [data-testid="stButtonGroup"] > div{ flex-wrap:nowrap !important; gap:14px !important; }
    [data-testid="stButtonGroup"] button{ flex:0 0 auto !important; padding-left:1.4rem !important; padding-right:1.4rem !important; }
    [data-testid="stButtonGroup"]::-webkit-scrollbar{ height:6px; }
    [data-testid="stButtonGroup"]::-webkit-scrollbar-thumb{ background:rgba(17,24,39,0.15); border-radius:99px; }
    .st-key-toolbar{ background:transparent; border:none; padding:0; margin:1.6rem 0 0.6rem;
        display:flex !important; justify-content:center !important; width:100% !important; }

    /* Resume / Job Description workspace card — dark gradient panel */
    .st-key-wscard, .st-key-wscard [data-testid="stVerticalBlockBorderWrapper"]{
        position:relative; overflow:hidden;
        background:linear-gradient(135deg,#0B1020 0%,#191235 55%,#2C1A55 100%) !important;
        border:1px solid rgba(124,58,237,0.30) !important; border-radius:18px !important;
        box-shadow:0 24px 60px rgba(11,16,32,0.35) !important; padding:1.5rem 1.6rem !important; }
    .st-key-wscard::after{ content:""; position:absolute; right:-120px; top:-90px; width:360px; height:360px; z-index:0;
        border-radius:50%; background:radial-gradient(circle, rgba(124,58,237,0.40), transparent 70%); pointer-events:none; }
    .st-key-wscard [data-testid="stHorizontalBlock"]{ position:relative; z-index:1; }
    .st-key-wscard .section-label{ color:#34D399 !important; }
    .st-key-wscard .pill-ok{ background:rgba(16,185,129,0.18) !important; color:#6EE7B7 !important;
        border:1px solid rgba(16,185,129,0.45) !important; }
    /* JD textarea — solid white field with black text for readability */
    .st-key-wscard textarea{ background:#FFFFFF !important;
        border:1px solid rgba(255,255,255,0.25) !important; color:#111827 !important; }
    .st-key-wscard textarea::placeholder{ color:#6B7280 !important; }
    .st-key-wscard textarea:focus{ border-color:#34D399 !important;
        box-shadow:0 0 0 3px rgba(16,185,129,0.25) !important; background:#FFFFFF !important; }
    /* Change-resume expander — white box, dark text */
    .st-key-wscard [data-testid="stExpander"] summary{ background:transparent !important; color:#111827 !important; }
    .st-key-wscard [data-testid="stExpander"] summary svg,
    .st-key-wscard [data-testid="stExpander"] summary p{ color:#111827 !important; fill:#111827 !important; }
    /* Start-over button on dark */
    .st-key-wscard .stButton > button{ background:rgba(255,255,255,0.06) !important;
        border:1px solid rgba(255,255,255,0.18) !important; color:#E5E7EB !important; }
    .st-key-wscard .stButton > button:hover{ border-color:#34D399 !important; color:#fff !important;
        background:rgba(16,185,129,0.14) !important; }
    .st-key-toolbar [data-testid="stElementContainer"]{ width:100% !important; }

    /* Empty state */
    .empty{ text-align:center; padding:44px 18px 8px 18px; animation:fadeUp 0.4s ease both; }
    .empty .bigic{ display:inline-block; animation:floaty 4s ease-in-out infinite; }
    .empty-t{ font-family:'Sora',sans-serif; font-weight:700; color:#111827; font-size:1.18rem; margin-top:0.5rem; }
    .empty-d{ color:#6B7280; font-size:0.92rem; max-width:470px; margin:0.4rem auto 0.2rem auto; line-height:1.55; }

    .demo-banner{ background:linear-gradient(90deg,rgba(16,185,129,0.12),rgba(124,58,237,0.10));
        border:1px solid rgba(16,185,129,0.30); border-radius:12px; padding:0.7rem 1rem; color:#374151; font-size:0.9rem; margin-bottom:0.7rem; animation:fadeUp 0.35s ease both; }
    .demo-banner b{ color:#111827; }

    .sub-row{ display:flex; align-items:center; gap:12px; margin:0.45rem 0; }
    .sub-name{ width:120px; color:#374151; font-size:0.9rem; }
    .sub-track{ flex:1; height:10px; background:#EDEFF3; border-radius:99px; overflow:hidden; }
    .sub-fill{ height:100%; border-radius:99px; animation:growx 0.8s ease; }
    .sub-val{ width:44px; text-align:right; color:#111827; font-weight:700; font-size:0.9rem; }

    .pill{ display:inline-block; padding:0.18rem 0.7rem; border-radius:99px; font-size:0.78rem; font-weight:600; margin:0.15rem 0.25rem 0.15rem 0; }
    .pill-ok{ background:rgba(16,185,129,0.12); color:#047857; border:1px solid rgba(16,185,129,0.3); }
    .pill-warn{ background:rgba(245,158,11,0.12); color:#B45309; border:1px solid rgba(245,158,11,0.3); }
    .chip{ display:inline-block; padding:0.22rem 0.7rem; border-radius:8px; font-size:0.8rem; font-weight:600; margin:0.18rem 0.3rem 0.18rem 0; }
    .chip-ok{ background:rgba(16,185,129,0.12); color:#047857; border:1px solid rgba(16,185,129,0.28); }
    .chip-miss{ background:rgba(239,68,68,0.10); color:#B91C1C; border:1px solid rgba(239,68,68,0.28); }

    .role-card{ background:#fff; border:1px solid #E7E9EF; border-left:3px solid #10B981; border-radius:12px; padding:0.9rem 1.1rem; margin-bottom:0.7rem; box-shadow:0 4px 14px rgba(17,24,39,0.05); animation:fadeUp 0.4s ease both; transition:transform 0.15s, box-shadow 0.15s; }
    .role-card:hover{ transform:translateY(-2px); box-shadow:0 10px 24px rgba(16,185,129,0.14); }
    .role-title{ font-family:'Sora',sans-serif; font-weight:700; font-size:1.05rem; color:#111827; }
    .role-ctc{ float:right; color:#059669; font-weight:700; font-size:0.95rem; }
    .role-why{ color:#4B5563; font-size:0.92rem; margin-top:0.25rem; }

    .resume-box{ background:#FFFFFF; border:1px solid #E7E9EF; border-radius:12px; padding:1rem 1.2rem;
        max-height:430px; overflow:auto; white-space:pre-wrap; font-size:0.88rem; line-height:1.6; color:#374151; animation:fadeUp 0.4s ease both; }
    mark.kw{ background:rgba(16,185,129,0.22); color:#065F46; padding:0 2px; border-radius:3px; font-weight:600; }

    .iq{ background:#fff; border:1px solid #E7E9EF; border-left:3px solid #7C3AED; border-radius:12px; padding:0.9rem 1.1rem; margin-bottom:0.7rem; box-shadow:0 4px 14px rgba(17,24,39,0.05); animation:fadeUp 0.4s ease both; transition:transform 0.15s, box-shadow 0.15s; }
    .iq:hover{ transform:translateY(-2px); box-shadow:0 10px 24px rgba(124,58,237,0.14); }
    .iq-q{ font-family:'Sora',sans-serif; font-weight:600; color:#111827; }
    .iq-a{ color:#4B5563; font-size:0.92rem; margin-top:0.3rem; } .iq-a b{ color:#7C3AED; }

    /* KPI cards */
    .kpi{ background:#FFFFFF; border:1px solid #E7E9EF; border-radius:16px; padding:1rem 1.1rem; text-align:center;
        box-shadow:0 6px 18px rgba(17,24,39,0.06); animation:fadeUp 0.45s ease both; transition:transform 0.15s, box-shadow 0.15s; }
    .kpi:hover{ transform:translateY(-3px); box-shadow:0 14px 30px rgba(16,185,129,0.14); }
    .kpi-n{ font-family:'Sora',sans-serif; font-weight:800; font-size:2rem; line-height:1; }
    .kpi-l{ color:#6B7280; font-size:0.74rem; margin-top:0.45rem; text-transform:uppercase; letter-spacing:0.09em; font-weight:600; }
    .kpi-ic{ font-family:'Material Symbols Rounded'; font-size:1.05rem; vertical-align:-3px; margin-right:5px; }

    [data-testid="stAlert"]{ border-radius:12px; }

    /* Landing hero */
    .hero-top{ height:1.4rem; }
    .eyebrow{ color:#7C3AED; font-weight:700; letter-spacing:0.16em; font-size:0.8rem; text-transform:uppercase; margin-bottom:1.1rem; animation:fadeUp 0.4s ease both; }
    .h1{ font-family:'Sora',sans-serif; font-weight:800; font-size:3.5rem; line-height:1.12; color:#111827; margin-bottom:1.4rem; animation:fadeUp 0.45s ease both; }
    .h1 .accent{ background:linear-gradient(90deg,#10B981,#34D399); -webkit-background-clip:text; -webkit-text-fill-color:transparent; background-clip:text; }
    .lede{ color:#4B5563; font-size:1.08rem; max-width:560px; line-height:1.7; margin-bottom:2rem; animation:fadeUp 0.5s ease both; }
    .privacy{ color:#6B7280; font-size:0.82rem; margin-top:0.9rem; } .privacy .mi{ color:#6B7280; font-size:0.95rem; }
    .or{ text-align:center; color:#9CA3AF; font-size:0.8rem; margin:1.3rem 0 0.8rem 0; }

    /* Landing preview art */
    .pv-wrap{ position:relative; height:430px; animation:fadeUp 0.6s ease both; }
    .pv-card{ position:absolute; background:#fff; border:1px solid #E7E9EF; border-radius:18px; box-shadow:0 24px 60px rgba(17,24,39,0.12); }
    .pv-float{ left:0; top:34px; width:236px; padding:18px 18px 20px; z-index:2; animation:floaty 5s ease-in-out infinite; }
    .pv-back{ right:0; top:0; width:330px; padding:18px; z-index:1; }
    .pv-title{ font-family:'Sora',sans-serif; font-weight:700; color:#111827; font-size:0.95rem; text-align:center; }
    .pv-gauge{ text-align:center; margin-top:6px; }
    .pv-score{ font-family:'Sora',sans-serif; font-weight:800; font-size:1.9rem; color:#111827; text-align:center; margin-top:-10px; }
    .pv-score span{ color:#9CA3AF; font-size:0.9rem; font-weight:600; }
    .pv-sub{ text-align:center; color:#10B981; font-size:0.78rem; font-weight:600; margin-bottom:12px; }
    .pv-row{ display:flex; align-items:center; gap:8px; padding:6px 0; border-top:1px solid #F1F2F6; }
    .pv-dot{ width:18px; height:18px; border-radius:50%; display:flex; align-items:center; justify-content:center; font-size:11px; font-weight:800; }
    .pv-row-l{ color:#374151; font-size:0.82rem; }
    .pv-back-h{ font-family:'Sora',sans-serif; font-weight:700; color:#111827; font-size:0.82rem; letter-spacing:0.06em; margin-bottom:14px; display:flex; align-items:center; }
    .pv-badge{ background:rgba(16,185,129,0.14); color:#047857; font-size:0.68rem; padding:2px 7px; border-radius:99px; font-weight:700; }
    .pv-bar{ height:9px; background:#EDEFF3; border-radius:6px; margin:11px 0; }
    .pv-bar.w80{ width:80%; } .pv-bar.w60{ width:60%; } .pv-bar.w90{ width:90%; } .pv-bar.w50{ width:50%; }

    /* Landing sections */
    .lp-section{ margin-top:4.5rem; }
    .lp-eyebrow{ text-align:center; color:#7C3AED; font-weight:700; letter-spacing:0.15em; font-size:0.76rem; text-transform:uppercase; }
    .lp-h2{ text-align:center; font-family:'Sora',sans-serif; font-weight:800; font-size:2.2rem; color:#111827; margin:0.5rem 0 0.7rem; }
    .lp-sub{ text-align:center; color:#4B5563; font-size:1.02rem; max-width:700px; margin:0 auto 2.2rem; line-height:1.65; }

    .statbox{ text-align:center; padding:0.6rem 0; }
    .statbox .n{ font-family:'Sora',sans-serif; font-weight:800; font-size:2rem; line-height:1;
        background:linear-gradient(90deg,#10B981,#7C3AED); -webkit-background-clip:text; -webkit-text-fill-color:transparent; background-clip:text; }
    .statbox .l{ color:#6B7280; font-size:0.85rem; margin-top:0.35rem; }

    .val-card{ background:#fff; border:1px solid #E7E9EF; border-radius:18px; padding:1.6rem 1.7rem; box-shadow:0 10px 30px rgba(17,24,39,0.06); }
    .val-h{ font-family:'Sora',sans-serif; font-weight:800; font-size:1.9rem; color:#111827; line-height:1.2; margin-bottom:0.8rem; }
    .val-p{ color:#4B5563; font-size:1.02rem; line-height:1.7; margin-bottom:0.6rem; }
    .val-row{ display:flex; align-items:flex-start; gap:10px; padding:9px 0; }
    .val-ic{ font-family:'Material Symbols Rounded'; color:#10B981; font-size:1.25rem; flex:0 0 auto; }
    .val-t{ color:#111827; font-weight:600; font-size:0.95rem; }
    .val-d{ color:#6B7280; font-size:0.87rem; }

    .tgrid{ display:flex; flex-wrap:wrap; justify-content:center; gap:1.3rem; }
    .tcard{ flex:0 1 calc(33.333% - 0.9rem); min-width:260px;
        background:#fff; border:1px solid #E7E9EF; border-radius:16px; padding:1.3rem 1.35rem; min-height:188px;
        box-shadow:0 6px 18px rgba(17,24,39,0.05); transition:transform 0.15s, box-shadow 0.15s, border-color 0.15s; }
    .tcard:hover{ transform:translateY(-4px); box-shadow:0 16px 32px rgba(16,185,129,0.16); border-color:rgba(16,185,129,0.45); }
    .tcard .ic{ width:46px; height:46px; border-radius:13px; background:rgba(16,185,129,0.12); color:#059669;
        display:flex; align-items:center; justify-content:center; font-family:'Material Symbols Rounded'; font-size:1.5rem; }
    .tcard .t{ font-family:'Sora',sans-serif; font-weight:700; color:#111827; font-size:1.06rem; margin-top:0.8rem; }
    .tcard .d{ color:#6B7280; font-size:0.9rem; margin-top:0.35rem; line-height:1.55; }

    .step{ text-align:center; padding:0.5rem; }
    .step .num{ width:46px; height:46px; border-radius:50%; margin:0 auto 0.7rem; color:#fff; font-family:'Sora',sans-serif; font-weight:800;
        display:flex; align-items:center; justify-content:center; font-size:1.2rem;
        background:linear-gradient(135deg,#10B981,#34D399); box-shadow:0 8px 18px rgba(16,185,129,0.32); }
    .step .t{ font-family:'Sora',sans-serif; font-weight:700; color:#111827; }
    .step .d{ color:#6B7280; font-size:0.9rem; margin-top:0.25rem; line-height:1.5; }

    /* FAQ expanders */
    [data-testid="stExpander"]{ border:1px solid #E7E9EF !important; border-radius:14px !important; background:#fff; margin-bottom:0.6rem; box-shadow:0 3px 10px rgba(17,24,39,0.04); }
    [data-testid="stExpander"] summary{ font-family:'Sora',sans-serif; font-weight:600; color:#111827; }

    .footer-cg{ text-align:center; color:#9CA3AF; font-size:0.85rem; margin-top:4.5rem; padding-top:1.6rem; border-top:1px solid #E7E9EF; }
    .footer-cg b{ color:#059669; }

    /* Dark gradient panels */
    .dark-panel{ position:relative; overflow:hidden; margin-top:3.2rem;
        background:linear-gradient(135deg,#0B1020 0%,#191235 55%,#2C1A55 100%);
        border-radius:26px; padding:2.8rem 2.6rem; color:#E5E7EB;
        box-shadow:0 24px 60px rgba(17,24,39,0.28); animation:fadeUp 0.5s ease both; }
    .dark-panel::before{ content:""; position:absolute; right:-130px; top:-90px; width:400px; height:400px; border-radius:50%;
        background:radial-gradient(circle, rgba(124,58,237,0.45), transparent 70%); }
    .dark-panel::after{ content:""; position:absolute; left:-90px; bottom:-110px; width:320px; height:320px; border-radius:50%;
        background:radial-gradient(circle, rgba(16,185,129,0.22), transparent 70%); }
    .dp-eyebrow{ color:#A78BFA; font-weight:700; letter-spacing:0.15em; font-size:0.76rem; text-transform:uppercase; position:relative; z-index:1; }
    .dp-h2{ font-family:'Sora',sans-serif; font-weight:800; font-size:2.1rem; color:#fff; line-height:1.18; margin:0.5rem 0 0.7rem; text-align:center; position:relative; z-index:1; }
    .dp-sub{ color:#C7CBD6; font-size:1.0rem; line-height:1.65; text-align:center; max-width:680px; margin:0 auto; position:relative; z-index:1; }
    .dp-grid{ display:grid; grid-template-columns:1fr 1fr; gap:2.2rem; align-items:center; position:relative; z-index:1; }
    .dp-card{ background:#fff; border-radius:16px; padding:1.4rem 1.6rem; box-shadow:0 18px 44px rgba(0,0,0,0.3); }
    .dp-steps{ display:grid; grid-template-columns:repeat(3,1fr); gap:1.6rem; margin-top:1.8rem; position:relative; z-index:1; }
    .dp-step{ text-align:center; }
    .dp-step .num{ width:48px; height:48px; border-radius:50%; margin:0 auto 0.7rem; color:#fff; font-family:'Sora',sans-serif; font-weight:800;
        display:flex; align-items:center; justify-content:center; font-size:1.25rem;
        background:linear-gradient(135deg,#10B981,#34D399); box-shadow:0 8px 20px rgba(16,185,129,0.4); }
    .dp-step .t{ font-family:'Sora',sans-serif; font-weight:700; color:#fff; }
    .dp-step .d{ color:#C7CBD6; font-size:0.9rem; margin-top:0.25rem; line-height:1.5; }
    .faq-wrap{ max-width:780px; margin:1.6rem auto 0; position:relative; z-index:1; }
    .faq-item{ background:rgba(255,255,255,0.06); border:1px solid rgba(255,255,255,0.12); border-radius:12px; padding:0.9rem 1.15rem; margin-bottom:0.7rem; transition:background 0.15s; }
    .faq-item[open]{ background:rgba(255,255,255,0.09); }
    .faq-item summary{ cursor:pointer; color:#fff; font-family:'Sora',sans-serif; font-weight:600; font-size:0.98rem; list-style:none; display:flex; align-items:center; justify-content:space-between; }
    .faq-item summary::-webkit-details-marker{ display:none; }
    .faq-item summary::after{ content:"+"; color:#A78BFA; font-size:1.3rem; font-weight:700; }
    .faq-item[open] summary::after{ content:"−"; }
    .faq-a{ color:#C7CBD6; font-size:0.92rem; margin-top:0.7rem; line-height:1.65; }
    @media (max-width:820px){ .dp-grid{ grid-template-columns:1fr; } .dp-steps{ grid-template-columns:1fr; } }

    /* Fluid, zoom-out responsive scaling */
    .h1{ font-size:clamp(2.1rem, 4.6vw, 3.6rem) !important; }
    .lede{ font-size:clamp(0.96rem, 1.35vw, 1.1rem) !important; }
    .lp-h2, .dp-h2, .val-h{ font-size:clamp(1.6rem, 3.1vw, 2.25rem) !important; }
    .lp-sub, .dp-sub{ font-size:clamp(0.92rem, 1.25vw, 1.03rem) !important; }
    .dark-panel{ padding:clamp(1.6rem, 3vw, 2.8rem) clamp(1.4rem, 3vw, 2.6rem); }
    .pv-wrap{ width:100%; max-width:560px; margin:0 auto; }
    @media (max-width:1100px){ .pv-back{ width:62%; } .pv-float{ width:48%; min-width:200px; } }
    @media (max-width:820px){ .pv-wrap{ height:380px; } }
    @media (max-width:680px){ .pv-wrap{ display:none; } }
    </style>
    """,
    unsafe_allow_html=True,
)


# ----------------------------------------------------------------------------
# State helpers
# ----------------------------------------------------------------------------
def set_result(kind, text, pdf):
    st.session_state[f"res_{kind}"] = {"text": text, "pdf": pdf}


def clear_results():
    for k, *_ in TOOLS:
        st.session_state.pop(f"res_{k}", None)
    st.session_state.pop("demo_active", None)
    st.session_state.pop("demo_name", None)


def set_collapsed(value):
    st.session_state["collapsed"] = value


def load_demo(persona):
    d = DEMO[persona]
    st.session_state["_pending_jd"] = d["jd"]  # applied next run, before the JD widget is created
    st.session_state["demo_active"] = d["label"]
    st.session_state["demo_name"] = d["name"]
    set_result("review", d["review"], d["resume"])
    set_result("roles", json.dumps(d["roles"]), d["resume"])
    set_result("dashboard", json.dumps(d["dashboard"]), d["resume"])
    set_result("cover", d["cover"], d["resume"])
    set_result("interview", json.dumps(d["interview"]), d["resume"])


def run_analysis(kind):
    """Real Claude call. Returns True on success."""
    jd = st.session_state.get("jd_text", "")
    cv = st.session_state.get("_resume_file")
    if cv is None:
        st.warning("⚠️ Please upload your resume first.")
        return False
    if not jd.strip() and kind != "roles":
        st.warning("⚠️ Please paste a job description first.")
        return False
    with st.spinner(SPINNERS[kind]):
        try:
            pdf_text = extract_pdf_text(cv)
            resp = get_claude_response(PROMPTS[kind], pdf_text, jd, max_tokens=MAXTOK.get(kind, 4000))
            set_result(kind, resp, pdf_text)
            st.session_state.pop("demo_active", None)
            return True
        except Exception as e:
            st.error(f"Error: {e}")
            return False


# ----------------------------------------------------------------------------
# Renderers
# ----------------------------------------------------------------------------
_VERDICT_ICONS = {
    "overall verdict": "verified",
    "key strengths": "trending_up",
    "gaps & weaknesses": "warning",
    "gaps and weaknesses": "warning",
    "recommendations to improve": "lightbulb",
    "recommendations": "lightbulb",
}


def _split_md_sections(text):
    """Split '## Header' markdown into (header, body) pairs."""
    parts = re.split(r"^\s*#{2,3}\s+", text, flags=re.M)
    out = []
    for chunk in parts[1:]:
        head, _, body = chunk.partition("\n")
        out.append((head.strip(), body.strip()))
    return out


def render_review(text, pdf_text):
    sections = _split_md_sections(text)
    if not sections:
        st.markdown(text)
        return
    for head, body in sections:
        icon = _VERDICT_ICONS.get(head.lower().strip(), "chevron_right")
        with st.container(border=True, key=f"rc_{re.sub(r'[^a-z]', '', head.lower())}"):
            st.markdown(
                f'<div class="report-h"><span class="mi">{icon}</span>{html.escape(head)}</div>',
                unsafe_allow_html=True)
            if body:
                st.markdown(body)


def render_roles(text, pdf_text):
    data = try_parse_json(text)
    if not data:
        st.markdown(text); return
    if data.get("candidate_summary"):
        st.markdown('<div class="section-label">Candidate Summary</div>', unsafe_allow_html=True)
        st.write(data["candidate_summary"])
    if data.get("recommended_roles"):
        st.markdown('<div class="section-label">Recommended Roles</div>', unsafe_allow_html=True)
        for r in data["recommended_roles"]:
            st.markdown(
                f'<div class="role-card"><span class="role-ctc">{r.get("expected_ctc_inr","")}</span>'
                f'<div class="role-title">{r.get("role","")}</div>'
                f'<div class="role-why">{r.get("justification","")}</div></div>', unsafe_allow_html=True)


def _sub_bars_html(order, scores):
    out = []
    for name, v in zip(order, scores):
        out.append(
            f'<div class="sub-row"><div class="sub-name">{name}</div>'
            f'<div class="sub-track"><div class="sub-fill" style="width:{v}%;background:{score_color(v)};"></div></div>'
            f'<div class="sub-val">{v}%</div></div>')
    st.markdown("".join(out), unsafe_allow_html=True)


def render_dashboard(text, pdf_text):
    data = try_parse_json(text)
    if not data:
        st.markdown(text); return
    overall = int(data.get("overall_match", 0))
    matched = data.get("matched_keywords", []) or []
    missing = data.get("missing_keywords", []) or []
    subs = data.get("subscores", {}) or {}
    yrs = data.get("years_experience", "—")

    # ---- KPI cards ----
    kpis = [
        ("trophy", "Overall Match", f"{overall}%", score_color(overall)),
        ("check_circle", "Matched", str(len(matched)), "#10B981"),
        ("cancel", "Missing", str(len(missing)), "#EF4444"),
        ("work_history", "Experience", f"{yrs} yrs", "#7C3AED"),
    ]
    cols = st.columns(4)
    for col, (ic, label, val, color) in zip(cols, kpis):
        col.markdown(
            f'<div class="kpi"><div class="kpi-n" style="color:{color};">{val}</div>'
            f'<div class="kpi-l"><span class="kpi-ic" style="color:{color};">{ic}</span>{label}</div></div>',
            unsafe_allow_html=True)

    if data.get("summary"):
        st.write("")
        with st.container(border=True, key="rc_dashsummary"):
            st.markdown('<div class="report-h"><span class="mi">summarize</span>Summary</div>', unsafe_allow_html=True)
            st.write(data["summary"])

    st.write("")
    a, b = st.columns([1.25, 1], gap="small")

    # ---- Score breakdown (Altair bars w/ data labels) ----
    order = ["Keywords", "Experience", "Education", "Skills"]
    keys = ["keywords", "experience", "education", "skills"]
    scores = [int(subs.get(k, 0)) for k in keys]
    with a:
      with st.container(border=True, key="rc_scorebreakdown"):
        st.markdown('<div class="report-h"><span class="mi">bar_chart</span>Score Breakdown</div>', unsafe_allow_html=True)
        if HAVE_CHARTS:
            try:
                df = pd.DataFrame({"Category": order, "Score": scores, "Max": [100] * 4,
                                   "Color": [score_color(s) for s in scores]})
                ybase = alt.Y("Category:N", sort=order,
                              axis=alt.Axis(title=None, domain=False, ticks=False, labelColor="#374151", labelFontSize=13))
                track = alt.Chart(df).mark_bar(height=20, cornerRadius=10, color="#EDEFF3").encode(
                    y=ybase, x=alt.X("Max:Q", scale=alt.Scale(domain=[0, 100]), axis=None))
                bar = alt.Chart(df).mark_bar(height=20, cornerRadius=10).encode(
                    y=ybase, x=alt.X("Score:Q", scale=alt.Scale(domain=[0, 100]), axis=None),
                    color=alt.Color("Color:N", scale=None),
                    tooltip=[alt.Tooltip("Category:N"), alt.Tooltip("Score:Q")])
                lbl = alt.Chart(df).mark_text(align="right", dx=-8, fontSize=12, fontWeight="bold", color="#FFFFFF").encode(
                    y=ybase, x=alt.X("Score:Q"), text=alt.Text("Score:Q", format=".0f"))
                chart = (track + bar + lbl).properties(height=200).configure_view(stroke=None).configure(background="transparent")
                st.altair_chart(chart, use_container_width=True)
            except Exception:
                _sub_bars_html(order, scores)
        else:
            _sub_bars_html(order, scores)

    # ---- Keyword coverage donut (Altair w/ labels + center %) ----
    m, n = len(matched), len(missing)
    total = m + n
    with b:
      with st.container(border=True, key="rc_keywordcoverage"):
        st.markdown('<div class="report-h"><span class="mi">donut_small</span>Keyword Coverage</div>', unsafe_allow_html=True)
        if HAVE_CHARTS and total:
            try:
                cov = pd.DataFrame({"Status": ["Matched", "Missing"], "Count": [m, n]})
                pct = round(m / total * 100)
                donut = alt.Chart(cov).mark_arc(innerRadius=58, outerRadius=92, cornerRadius=4,
                                                stroke="#FFFFFF", strokeWidth=2).encode(
                    theta=alt.Theta("Count:Q", stack=True),
                    color=alt.Color("Status:N", scale=alt.Scale(domain=["Matched", "Missing"], range=["#10B981", "#EF4444"]),
                                    legend=alt.Legend(orient="bottom", title=None, labelColor="#374151", labelFontSize=12)),
                    tooltip=["Status", "Count"])
                arc_lbl = alt.Chart(cov[cov["Count"] > 0]).mark_text(radius=75, fontSize=13, fontWeight="bold", color="white").encode(
                    theta=alt.Theta("Count:Q", stack=True), text=alt.Text("Count:Q"))
                c1 = alt.Chart(pd.DataFrame({"t": [f"{pct}%"]})).mark_text(
                    fontSize=30, fontWeight="bold", color="#059669", dy=-6).encode(text="t:N")
                c2 = alt.Chart(pd.DataFrame({"t": ["covered"]})).mark_text(
                    fontSize=11, color="#6B7280", dy=18).encode(text="t:N")
                chart = (donut + arc_lbl + c1 + c2).properties(width=240, height=240).configure_view(stroke=None).configure(background="transparent")
                st.altair_chart(chart)
            except Exception:
                st.write(f"Matched {m} · Missing {n}")
        else:
            st.write(f"Matched {m} · Missing {n}")

    st.write("")
    if matched or missing:
        with st.container(border=True, key="rc_keywords"):
            st.markdown('<div class="report-h"><span class="mi">label</span>Keyword Breakdown</div>', unsafe_allow_html=True)
            if matched:
                st.markdown('<div class="kw-sub kw-sub-ok"><span class="mi">check_circle</span>Matched</div>', unsafe_allow_html=True)
                st.markdown("".join(f'<span class="chip chip-ok">{html.escape(str(x))}</span>' for x in matched), unsafe_allow_html=True)
            if missing:
                st.markdown('<div class="kw-sub kw-sub-miss"><span class="mi">cancel</span>Missing</div>', unsafe_allow_html=True)
                st.markdown("".join(f'<span class="chip chip-miss">{html.escape(str(x))}</span>' for x in missing), unsafe_allow_html=True)

    # Inline-highlighted resume (merged from the old Keyword Highlighter)
    if pdf_text and matched:
        st.write("")
        with st.container(border=True, key="rc_resumehighlight"):
            st.markdown('<div class="report-h"><span class="mi">highlight</span>Resume — matched keywords highlighted</div>', unsafe_allow_html=True)
            safe = html.escape(pdf_text)
            for kw in sorted({str(k) for k in matched if str(k).strip()}, key=len, reverse=True):
                pat = re.compile(r"(?<!\w)(" + re.escape(html.escape(kw)) + r")(?!\w)", flags=re.IGNORECASE)
                safe = pat.sub(r'<mark class="kw">\1</mark>', safe)
            st.markdown(f'<div class="resume-box">{safe}</div>', unsafe_allow_html=True)


def render_cover(text, pdf_text):
    with st.container(border=True, key="rc_coverletter"):
        st.markdown(text)


def render_interview(text, pdf_text):
    data = try_parse_json(text)
    if not data:
        st.markdown(text); return
    if data.get("questions"):
        st.markdown('<div class="section-label">Likely Questions & Your Angle</div>', unsafe_allow_html=True)
        for i, q in enumerate(data["questions"], 1):
            st.markdown(
                f'<div class="iq"><div class="iq-q">Q{i}. {html.escape(str(q.get("question","")))}</div>'
                f'<div class="iq-a"><b>Your angle:</b> {html.escape(str(q.get("talking_point","")))}</div></div>', unsafe_allow_html=True)
    if data.get("general_tips"):
        st.markdown('<div class="section-label">Prep Tips</div>', unsafe_allow_html=True)
        for t in data["general_tips"]:
            st.markdown(f"- {t}")


RENDERERS = {"review": render_review, "roles": render_roles, "dashboard": render_dashboard,
             "cover": render_cover, "interview": render_interview}


# Apply any pending JD (from dummy-data load) BEFORE the JD widget is created
if "_pending_jd" in st.session_state:
    st.session_state["jd_text"] = st.session_state.pop("_pending_jd")


# ----------------------------------------------------------------------------
# Top bar
# ----------------------------------------------------------------------------
def start_over():
    """Go back to the landing page: fresh uploader + cleared results/demo."""
    st.session_state["up_nonce"] = st.session_state.get("up_nonce", 0) + 1
    st.session_state.pop("_resume_file", None)
    clear_results()


@st.dialog("Welcome to CareerGuru")
def _signin_dialog():
    st.caption("Save your analyses, track applications, and pick up where you left off.")
    tab_in, tab_up = st.tabs(["Sign in", "Create account"])

    with tab_in:
        email = st.text_input("Email", placeholder="you@email.com", key="login_email")
        pw = st.text_input("Password", type="password", placeholder="••••••••", key="login_pw")
        if st.button("Sign in", type="primary", use_container_width=True, key="login_submit"):
            ok, res = db.verify_user(email, pw)
            if ok:
                st.session_state["user"] = res
                st.rerun()
            else:
                st.error(res)

    with tab_up:
        name = st.text_input("Full name", placeholder="Jane Doe", key="signup_name")
        email2 = st.text_input("Email", placeholder="you@email.com", key="signup_email")
        pw2 = st.text_input("Password", type="password", placeholder="At least 6 characters", key="signup_pw")
        if st.button("Create account", type="primary", use_container_width=True, key="signup_submit"):
            ok, res = db.create_user(email2, pw2, name)
            if ok:
                st.session_state["user"] = res
                st.success("Account created! You're signed in.")
                st.rerun()
            else:
                st.error(res)


def _sign_out():
    st.session_state.pop("user", None)


_on_workspace = (st.session_state.get("_resume_file") is not None) or bool(st.session_state.get("demo_name"))
if _on_workspace:
    _c1, _c2 = st.columns([1, 20], vertical_alignment="center")
    with _c1:
        st.button("", icon=":material/arrow_back:", key="back_home", on_click=start_over, help="Back to home")
    with _c2:
        st.markdown('<div class="topbar topbar-ws"><span class="brand">CareerGuru</span></div>', unsafe_allow_html=True)
else:
    _tb, _si = st.columns([5, 1], vertical_alignment="center")
    with _tb:
        st.markdown('<div class="topbar"><span class="brand">CareerGuru</span></div>', unsafe_allow_html=True)
    with _si:
        _user = st.session_state.get("user")
        if _user:
            _label = (_user.get("full_name") or _user.get("email", "")).split("@")[0]
            _name = _user.get("full_name") or _label
            _initial = (_name[:1] or "?").upper()
            _email = _user.get("email", "")
            _created = _user.get("created_at")
            _since = _created.strftime("%b %Y") if hasattr(_created, "strftime") else "—"
            with st.container(key="userchip"):
                with st.popover(f"👤 {_label}", use_container_width=False):
                    st.markdown(
                        f'<div class="acct-head">'
                        f'<div class="acct-avatar">{html.escape(_initial)}</div>'
                        f'<div class="acct-meta"><div class="acct-name">{html.escape(_name)}</div>'
                        f'<div class="acct-email">{html.escape(_email)}</div></div></div>',
                        unsafe_allow_html=True)
                    st.markdown(
                        f'<div class="acct-row"><span class="mi">calendar_month</span>Member since {_since}</div>',
                        unsafe_allow_html=True)
                    st.divider()
                    st.button("Sign out", icon=":material/logout:", key="signout_btn",
                              on_click=_sign_out, use_container_width=True)
        else:
            if st.button("Sign in", icon=":material/login:", key="signin_btn", type="primary"):
                _signin_dialog()


# ----------------------------------------------------------------------------
# Tab body renderer
# ----------------------------------------------------------------------------
def tab_body(kind):
    _, ic, title, desc = TOOL_BY_KEY[kind]
    res = st.session_state.get(f"res_{kind}")
    has_real_cv = st.session_state.get("_resume_file") is not None

    if not res:
        st.markdown(
            f'<div class="empty"><span class="bigic">{ic}</span>'
            f'<div class="empty-t">{title}</div><div class="empty-d">{desc}</div></div>', unsafe_allow_html=True)
        c = st.columns([1, 1, 1])
        with c[1]:
            if st.button("Generate", icon=":material/play_arrow:", key=f"gen_{kind}", type="primary", use_container_width=True):
                if run_analysis(kind):
                    st.rerun()
        return

    if has_real_cv:
        top = st.columns([3, 1])
        top[0].markdown(f'<div class="page-title"><span class="mi">{ic}</span>{html.escape(title)}</div>', unsafe_allow_html=True)
        with top[1]:
            if st.button("Regenerate", icon=":material/refresh:", key=f"regen_{kind}", use_container_width=True):
                if run_analysis(kind):
                    st.rerun()
    else:
        st.markdown(f'<div class="page-title"><span class="mi">{ic}</span>{html.escape(title)}</div>', unsafe_allow_html=True)
    st.markdown("---")
    RENDERERS[kind](res["text"], res["pdf"])


def render_tools():
    keys = [t[0] for t in TOOLS]
    with st.container(key="toolbar"):
        sel = st.segmented_control(
            "Tools", options=keys,
            format_func=lambda k: f":material/{TOOL_BY_KEY[k][1]}: {TOOL_BY_KEY[k][2]}",
            selection_mode="single", default=keys[0], required=True, key="active_tool",
            label_visibility="collapsed",
        )
    if not sel:
        sel = keys[0]
    st.write("")
    tab_body(sel)


# ----------------------------------------------------------------------------
# LANDING PAGE — upload-first, like a real product hero
# ----------------------------------------------------------------------------
def landing_preview_html():
    rows = [("ATS Parse Rate", "check", "#10B981"), ("Quantifying Impact", "check", "#10B981"),
            ("Keyword Match", "check", "#10B981"), ("Formatting", "warn", "#F59E0B"),
            ("Missing Skills", "cross", "#EF4444")]
    icon = {"check": "✓", "warn": "!", "cross": "✕"}
    row_html = "".join(
        f'<div class="pv-row"><span class="pv-dot" style="background:{c}1A;color:{c};">{icon[t]}</span>'
        f'<span class="pv-row-l">{name}</span></div>' for name, t, c in rows)
    return f"""
    <div class="pv-wrap">
      <div class="pv-card pv-float">
        <div class="pv-title">Resume Score</div>
        <div class="pv-gauge">
          <svg viewBox="0 0 120 70" width="150">
            <path d="M10 65 A50 50 0 0 1 110 65" fill="none" stroke="#EDEFF3" stroke-width="11" stroke-linecap="round"/>
            <path d="M10 65 A50 50 0 0 1 102 38" fill="none" stroke="#10B981" stroke-width="11" stroke-linecap="round"/>
          </svg>
        </div>
        <div class="pv-score">92<span>/100</span></div>
        <div class="pv-sub">Great — interview ready</div>
        <div class="pv-rows">{row_html}</div>
      </div>
      <div class="pv-card pv-back">
        <div class="pv-back-h">CONTENT &nbsp;<span class="pv-badge">90%</span></div>
        <div class="pv-bar"></div><div class="pv-bar w80"></div><div class="pv-bar w60"></div>
        <div class="pv-bar w90"></div><div class="pv-bar w50"></div>
      </div>
    </div>
    """


def render_landing():
    ukey = f"resume_pdf_{st.session_state.get('up_nonce', 0)}"
    st.markdown('<div class="hero-top"></div>', unsafe_allow_html=True)
    hero, art = st.columns([1.05, 0.95], gap="large")
    with hero:
        st.markdown('<div class="eyebrow">AI RESUME COACH</div>', unsafe_allow_html=True)
        st.markdown('<div class="h1">Know your fit.<br>Fix the gaps. <span class="accent">Get hired.</span></div>', unsafe_allow_html=True)
        st.markdown('<div class="lede">CareerGuru scores your resume against any job, shows exactly what\'s '
                    'missing, and even drafts your cover letter and interview prep — all in seconds.</div>', unsafe_allow_html=True)
        with st.container(border=True, key="uploadcard"):
            st.markdown('<div class="section-label"><span class="mi">upload_file</span> Step 1 · Upload your resume</div>', unsafe_allow_html=True)
            f = st.file_uploader("Upload your resume (PDF)", type=["pdf"], label_visibility="collapsed", key=ukey)
            if f is not None:
                st.session_state["_resume_file"] = f
                st.session_state.pop("demo_active", None)
                st.session_state.pop("demo_name", None)
                st.rerun()
            st.markdown('<div class="privacy"><span class="mi">lock</span> PDF only · processed securely, never shared</div>', unsafe_allow_html=True)
            st.write("")
            st.markdown('<div class="section-label"><span class="mi">work</span> Step 2 · Paste the job description <span class="opt">(optional)</span></div>', unsafe_allow_html=True)
            st.text_area("Job Description", key="jd_text", height=130, label_visibility="collapsed",
                         placeholder="Paste the job you're targeting for the most accurate match…")
            st.markdown('<div class="or">— or just preview with a sample —</div>', unsafe_allow_html=True)
            s = st.columns(3)
            s[0].button("Strong · 92%", icon=":material/check_circle:", use_container_width=True, on_click=load_demo, args=("perfect",))
            s[1].button("Partial · 54%", icon=":material/contrast:", use_container_width=True, on_click=load_demo, args=("partial",))
            s[2].button("Weak · 11%", icon=":material/cancel:", use_container_width=True, on_click=load_demo, args=("none",))
    with art:
        st.write("")
        st.markdown(landing_preview_html(), unsafe_allow_html=True)
        st.markdown(
            '<div class="art-extra">'
            '<div class="rating">★★★★★ <span>Loved by job seekers</span></div>'
            '<div class="art-list">'
            '<div><span class="mi">check_circle</span> Instantly checks ATS-readiness</div>'
            '<div><span class="mi">check_circle</span> Tailors to the exact job you want</div>'
            '<div><span class="mi">check_circle</span> Drafts your cover letter &amp; interview prep</div>'
            '</div>'
            '<div class="quote-card"><div class="q">"I went from zero callbacks to three interviews in a week — '
            'CareerGuru showed me exactly what my resume was missing."</div>'
            '<div class="q-by">— Priya · Software Engineer</div></div>'
            '</div>', unsafe_allow_html=True)

    # ---- Stats strip ----
    st.markdown('<div class="lp-section"></div>', unsafe_allow_html=True)
    cs = st.columns(4)
    for col, (n, l) in zip(cs, [("5", "AI tools"), ("Claude", "Opus model"), ("Seconds", "to results"), ("ATS", "optimised")]):
        col.markdown(f'<div class="statbox"><div class="n">{n}</div><div class="l">{l}</div></div>', unsafe_allow_html=True)

    # ---- Value section (dark panel) ----
    rows = [("psychology", "Understands the job", "Scores your true fit against any job description — not generic rules."),
            ("key", "Finds missing keywords", "Shows the ATS keywords you have, and the ones you should add."),
            ("auto_awesome", "Writes for you", "Generates a tailored cover letter in your voice."),
            ("forum", "Preps your interview", "Likely questions plus talking points from your own resume.")]
    val_rows = "".join(
        f'<div class="val-row"><span class="val-ic">{ic}</span><div><div class="val-t">{t}</div>'
        f'<div class="val-d">{d}</div></div></div>' for ic, t, d in rows)
    st.markdown(
        f'<div class="dark-panel"><div class="dp-grid">'
        f'<div><div class="dp-eyebrow">More than a spell-check</div>'
        f'<div class="dp-h2" style="text-align:left;">A coach that reads your resume like a recruiter</div>'
        f'<div class="dp-sub" style="text-align:left;margin:0;max-width:none;">Most checkers stop at typos and '
        f'formatting. CareerGuru understands the role you\'re targeting — it scores how well you match, surfaces the '
        f'exact skills and keywords you\'re missing, and tells you how to fix them. Powered by Anthropic\'s Claude, it '
        f'goes further and drafts a tailored cover letter and your interview prep.</div></div>'
        f'<div class="dp-card">{val_rows}</div></div></div>', unsafe_allow_html=True)

    # ---- Tools grid (light) ----
    st.markdown('<div class="lp-section"></div>', unsafe_allow_html=True)
    st.markdown('<div class="lp-eyebrow">Everything in one place</div>', unsafe_allow_html=True)
    st.markdown('<div class="lp-h2">Five tools, one upload</div>', unsafe_allow_html=True)
    st.markdown('<div class="lp-sub">From a quick health check to a ready-to-send cover letter — CareerGuru covers your whole job search.</div>', unsafe_allow_html=True)
    cards = "".join(
        f'<div class="tcard"><div class="ic">{ic}</div><div class="t">{title}</div>'
        f'<div class="d">{desc}</div></div>' for key, ic, title, desc in TOOLS)
    st.markdown(f'<div class="tgrid">{cards}</div>', unsafe_allow_html=True)

    # ---- How it works (dark panel) ----
    steps = [("1", "Upload your resume", "Drop in a PDF — we read it instantly."),
             ("2", "Add the job", "Paste the job description you're targeting."),
             ("3", "Get your analysis", "Score, gaps, cover letter and interview prep — in seconds.")]
    steps_html = "".join(
        f'<div class="dp-step"><div class="num">{n}</div><div class="t">{t}</div><div class="d">{d}</div></div>'
        for n, t, d in steps)
    st.markdown(
        f'<div class="dark-panel"><div class="dp-eyebrow" style="text-align:center;">Dead simple</div>'
        f'<div class="dp-h2">How it works</div>'
        f'<div class="dp-sub">Three steps from upload to a recruiter-ready resume.</div>'
        f'<div class="dp-steps">{steps_html}</div></div>', unsafe_allow_html=True)

    # ---- FAQ (dark panel) ----
    faqs = [
        ("Is CareerGuru free to use?",
         "You can preview every tool with built-in sample data for free. Running an analysis on your own resume uses "
         "Anthropic's Claude API, which requires an API key with credits."),
        ("Is my resume data safe?",
         "Your resume is used only to generate your analysis. It isn't sold or shared, and nothing is stored beyond your session."),
        ("What file types are supported?",
         "PDF resumes. We extract the text directly — if your PDF is a scanned image, run it through an OCR tool first."),
        ("Does it work for any job?",
         "Yes. Paste any job description and CareerGuru scores your fit against that specific role and its keywords."),
        ("Which AI powers CareerGuru?",
         "Anthropic's Claude (Opus). It reads and evaluates your resume, and writes your cover letter and interview prep."),
    ]
    faq_html = "".join(
        f'<details class="faq-item"><summary>{html.escape(q)}</summary><div class="faq-a">{html.escape(a)}</div></details>'
        for q, a in faqs)
    st.markdown(
        f'<div class="dark-panel"><div class="dp-eyebrow" style="text-align:center;">Good to know</div>'
        f'<div class="dp-h2">Frequently asked questions</div>'
        f'<div class="faq-wrap">{faq_html}</div></div>', unsafe_allow_html=True)


# ----------------------------------------------------------------------------
# WORKSPACE — inputs summary + tools (shown after a resume is provided)
# ----------------------------------------------------------------------------
def render_workspace():
    ukey = f"resume_pdf_{st.session_state.get('up_nonce', 0)}"
    name = (st.session_state["_resume_file"].name if st.session_state.get("_resume_file")
            else f'{st.session_state.get("demo_name", "sample.pdf")} (sample)')

    with st.container(border=True, key="wscard"):
        a, b = st.columns([1, 1.5], gap="large")
        with a:
            st.markdown('<div class="section-label"><span class="mi">description</span> Resume</div>', unsafe_allow_html=True)
            st.markdown(f'<span class="pill pill-ok">✓ {name}</span>', unsafe_allow_html=True)
            st.write("")
            with st.expander("Change resume"):
                f = st.file_uploader("Upload another (PDF)", type=["pdf"], label_visibility="collapsed", key=ukey)
                if f is not None:
                    st.session_state["_resume_file"] = f
                    st.session_state.pop("demo_active", None)
                    st.session_state.pop("demo_name", None)
            st.button("Start over", icon=":material/restart_alt:", key="start_over", on_click=start_over)
        with b:
            st.markdown('<div class="section-label"><span class="mi">work</span> Job Description</div>', unsafe_allow_html=True)
            st.text_area("Job Description", key="jd_text", height=120, label_visibility="collapsed",
                         placeholder="Paste the job description for the most accurate match...")

    if st.session_state.get("demo_active"):
        st.markdown(
            f'<div class="demo-banner"><span class="mi">science</span> Showing <b>sample data — '
            f'{st.session_state["demo_active"]}</b> (no API used). Upload your own resume + click '
            f'<b>Generate</b> for a real analysis.</div>', unsafe_allow_html=True)

    st.write("")
    render_tools()


# ----------------------------------------------------------------------------
# Router: upload-first gate
# ----------------------------------------------------------------------------
has_resume = (st.session_state.get("_resume_file") is not None) or bool(st.session_state.get("demo_name"))
if has_resume:
    render_workspace()
else:
    render_landing()
