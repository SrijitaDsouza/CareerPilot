"""Feature 6: skill / location / experience / requirement match with percentage fit.

The LLM extracts structured requirements from the JD; the percentages themselves are computed
in Python so they are consistent and explainable.
"""
import re
from difflib import SequenceMatcher

from config import FIT_WEIGHTS
from core.utils import profile_brief, to_float

SYSTEM = """You are a meticulous technical recruiter. Extract the job's requirements and judge how
well the candidate's experience matches the responsibilities. Be strict and evidence-based."""

SCHEMA = """{
  "title": "", "company": "", "location": "", "work_mode": "onsite | hybrid | remote | unknown",
  "min_years": null, "max_years": null,
  "must_have_skills": ["8-15 concise skill names, e.g. 'SQL', 'Stakeholder management'"],
  "nice_to_have_skills": [""],
  "education": "", "salary": "",
  "responsibility_alignment": 0,
  "alignment_reasoning": "2-3 lines",
  "education_ok": true,
  "red_flags": ["deal-breakers or concerns"],
  "recommendations": ["how to close the gap or position the application"]
}"""

ALIASES = {
    "js": "javascript", "ts": "typescript", "ml": "machine learning", "dl": "deep learning",
    "k8s": "kubernetes", "gcp": "google cloud", "aws": "amazon web services", "nlp": "natural language processing",
    "power bi": "powerbi", "ms excel": "excel", "advanced excel": "excel", "genai": "generative ai",
    "llm": "large language models", "ci cd": "cicd", "node": "nodejs", "node.js": "nodejs",
    "react.js": "react", "reactjs": "react", "postgres": "postgresql",
}


def _norm(s: str) -> str:
    s = re.sub(r"[^a-z0-9+#. ]", " ", str(s).lower())
    s = re.sub(r"\s+", " ", s).strip()
    return ALIASES.get(s, s)


def _has_skill(skill: str, cand: list[str], resume_norm: str) -> bool:
    s = _norm(skill)
    if not s:
        return False
    if f" {s} " in resume_norm:
        return True
    for c in cand:
        if s == c or (len(s) > 3 and (s in c or c in s)) or SequenceMatcher(None, s, c).ratio() >= 0.85:
            return True
    return False


def _experience_score(years, lo, hi) -> int:
    if years is None or (lo is None and hi is None):
        return 70  # unknown -> neutral
    if lo is not None and years < lo:
        return max(0, round(100 - 25 * (lo - years)))
    if hi is not None and years > hi:
        return 100 if years - hi <= 2 else 75  # mild over-qualification risk
    return 100


def _location_score(job_loc: str, mode: str, profile: dict) -> tuple[int, str]:
    if (mode or "").lower() == "remote":
        return 100, "Remote role"
    jl = _norm(job_loc)
    if not jl:
        return 70, "Job location not stated"
    prefs = [_norm(x) for x in (profile.get("preferred_locations") or [])]
    cur = _norm(profile.get("current_location", ""))
    places = [p for p in prefs + [cur] if p]
    if any(p in jl or jl in p for p in places):
        return 100, "Matches your preferred/current location"
    if "remote" in [_norm(m) for m in profile.get("work_modes", [])] and (mode or "").lower() == "hybrid":
        return 50, "Hybrid role; you prefer remote"
    if profile.get("open_to_relocate"):
        return 70, "Different city; you are open to relocating"
    return 30, "Different city and relocation not indicated"


def compute_fit(llm, profile: dict, resume_text: str, jd_text: str) -> dict:
    jd = llm.ask_json(SYSTEM, f"CANDIDATE:\n{profile_brief(profile)}\n\nJOB DESCRIPTION:\n{jd_text[:12000]}\n\n"
                              f"Return JSON:\n{SCHEMA}")

    cand = [_norm(x) for x in (profile.get("skills", []) + profile.get("tools", []) + profile.get("soft_skills", []))]
    resume_norm = f" {_norm(resume_text)} "

    must = jd.get("must_have_skills") or []
    nice = jd.get("nice_to_have_skills") or []
    must_hit = [s for s in must if _has_skill(s, cand, resume_norm)]
    nice_hit = [s for s in nice if _has_skill(s, cand, resume_norm)]
    must_pct = 100 * len(must_hit) / len(must) if must else 70
    nice_pct = 100 * len(nice_hit) / len(nice) if nice else must_pct
    skill_score = round(0.75 * must_pct + 0.25 * nice_pct)

    years = to_float(profile.get("total_experience_years"))
    exp_score = _experience_score(years, to_float(jd.get("min_years")), to_float(jd.get("max_years")))
    loc_score, loc_note = _location_score(jd.get("location", ""), jd.get("work_mode", ""), profile)

    req_score = int(to_float(jd.get("responsibility_alignment")) or 0)
    if jd.get("education_ok") is False:
        req_score = max(0, req_score - 15)

    overall = round(
        FIT_WEIGHTS["skills"] * skill_score + FIT_WEIGHTS["experience"] * exp_score
        + FIT_WEIGHTS["location"] * loc_score + FIT_WEIGHTS["requirements"] * req_score
    )
    band = "Strong fit" if overall >= 80 else "Good fit" if overall >= 65 else "Partial fit" if overall >= 50 else "Stretch"

    return {
        "jd": jd,
        "overall": overall, "band": band,
        "scores": {"skills": skill_score, "experience": exp_score, "location": loc_score, "requirements": req_score},
        "matched_must": must_hit, "missing_must": [s for s in must if s not in must_hit],
        "matched_nice": nice_hit, "missing_nice": [s for s in nice if s not in nice_hit],
        "location_note": loc_note,
        "experience_note": f"You: {years if years is not None else '?'} yrs | JD: "
                           f"{jd.get('min_years') or '?'}-{jd.get('max_years') or '?'} yrs",
    }
