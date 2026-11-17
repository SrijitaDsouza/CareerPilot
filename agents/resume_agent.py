"""Feature 4: tailored ATS-friendly resume + cover letter."""
import re

from core.utils import profile_brief

RESUME_SYSTEM = """You are an expert resume writer and ATS specialist.
Rewrite the candidate's resume so it is ATS-friendly and tailored to the target job.
Hard rules:
- Use ONLY facts from the original resume. Never invent employers, titles, dates, degrees,
  certifications, tools or metrics.
- Where a bullet would benefit from a number the resume lacks, insert a placeholder like
  [add metric: % / time saved / revenue] so the candidate fills it in honestly.
- Bullets: start with a strong action verb, show impact, 1-2 lines each, 3-6 per role.
- Mirror the job description's exact keywords where the candidate genuinely has that skill.
- Standard section names only; no tables, columns, icons or graphics."""

RESUME_SCHEMA = """{
  "name": "", "headline": "target title | 2-3 core strengths", "location": "", "phone": "",
  "email": "", "linkedin": "", "portfolio": "",
  "summary": "3-4 lines tailored to the role",
  "skills": [{"category": "", "items": [""]}],
  "experience": [{"title": "", "company": "", "location": "", "dates": "", "bullets": [""]}],
  "projects": [{"name": "", "description": ""}],
  "education": [{"degree": "", "institution": "", "year": ""}],
  "certifications": [""],
  "jd_keywords": ["15-25 important keywords/skills from the job description"],
  "changes_made": ["what you changed and why"],
  "missing_keywords": ["JD keywords the candidate does not show; do NOT add them to the resume"]
}"""

COVER_SYSTEM = """You write concise, specific cover letters that recruiters actually read.
No clichés ('I am writing to express my interest'), no invented facts. Connect 2-3 concrete
achievements from the resume to the job's needs. Plain text, short paragraphs, ready to send."""


def tailor_resume(llm, profile: dict, resume_text: str, jd_text: str = "", target_role: str = "") -> dict:
    target = jd_text.strip() or f"Target role: {target_role or ', '.join(profile.get('target_roles', []))}"
    user = (
        f"ORIGINAL RESUME:\n{resume_text[:20000]}\n\n"
        f"CANDIDATE PROFILE:\n{profile_brief(profile)}\n\n"
        f"TARGET JOB:\n{target[:10000]}\n\nReturn JSON:\n{RESUME_SCHEMA}"
    )
    return llm.ask_json(RESUME_SYSTEM, user, temperature=0.3)


def cover_letter(llm, profile: dict, resume_text: str, jd_text: str, company: str = "",
                 role: str = "", hiring_manager: str = "", tone: str = "Professional",
                 words: int = 280) -> str:
    user = (
        f"CANDIDATE PROFILE:\n{profile_brief(profile)}\n\nRESUME:\n{resume_text[:12000]}\n\n"
        f"JOB DESCRIPTION:\n{(jd_text or 'Not provided')[:8000]}\n\n"
        f"Company: {company or 'from the JD'}\nRole: {role or 'from the JD'}\n"
        f"Addressed to: {hiring_manager or 'Hiring Manager'}\nTone: {tone}\n"
        f"Length: about {words} words. Include a greeting and a sign-off with the candidate's name."
    )
    return llm.ask(COVER_SYSTEM, user, temperature=0.6)


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9+#. ]", " ", s.lower())


def ats_coverage(keywords: list[str], text: str) -> dict:
    """Share of JD keywords that appear in a piece of resume text."""
    body = f" {_norm(text)} "
    found, missing = [], []
    for k in keywords:
        nk = _norm(k).strip()
        if nk and (f" {nk} " in body or (len(nk) > 4 and nk in body)):
            found.append(k)
        else:
            missing.append(k)
    pct = round(100 * len(found) / len(keywords)) if keywords else 0
    return {"pct": pct, "found": found, "missing": missing}
