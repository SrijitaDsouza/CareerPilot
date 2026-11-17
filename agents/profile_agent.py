"""Feature 1: understand the resume, experience, expectations and target roles."""
import json

SYSTEM = """You are a senior career counsellor and technical recruiter with deep knowledge of the
Indian and global job markets. Build a structured candidate profile from a resume and the
candidate's stated preferences.
Rules: be factual. Never invent employers, dates, numbers, certifications or skills that the
resume does not support. You MAY infer seniority, functional areas and suitable roles."""

SCHEMA = """{
  "name": "", "email": "", "phone": "", "linkedin": "",
  "current_title": "", "current_company": "",
  "total_experience_years": 0,
  "seniority": "Entry | Mid | Senior | Lead | Manager | Director | Executive",
  "current_location": "", "preferred_locations": [], "open_to_relocate": true,
  "work_modes": [], "current_ctc": "", "expected_ctc": "", "notice_period": "",
  "skills": ["hard/technical skills"], "tools": ["software, platforms"],
  "soft_skills": [], "industries": [], "functional_areas": [],
  "education": [{"degree": "", "institution": "", "year": ""}],
  "certifications": [],
  "experience": [{"title": "", "company": "", "location": "", "start": "", "end": "", "highlights": []}],
  "achievements": ["quantified wins from the resume"],
  "target_roles": [], "target_industries": [],
  "suggested_roles": [{"role": "", "type": "direct | aspirational | pivot", "rationale": ""}],
  "strengths": [], "gaps": ["gaps vs. their targets"],
  "summary": "3-4 sentence recruiter-style summary"
}"""


def build_profile(llm, resume_text: str, prefs: dict) -> dict:
    user = (
        f"RESUME:\n{resume_text[:25000]}\n\n"
        f"CANDIDATE PREFERENCES (take precedence over the resume where they conflict):\n"
        f"{json.dumps(prefs, indent=2, ensure_ascii=False)}\n\n"
        f"target_roles: use the candidate's stated roles (max 3). If they gave fewer than 3, "
        f"add the best-fitting roles to make 2-3 in total, primary role first.\n"
        f"Give 5-8 suggested_roles mixing direct matches, a natural next step up (aspirational), "
        f"and at most one or two realistic pivots.\n\n"
        f"Return JSON with exactly this shape:\n{SCHEMA}"
    )
    profile = llm.ask_json(SYSTEM, user)
    profile["target_roles"] = (profile.get("target_roles") or [])[:3]
    profile["preferences"] = prefs
    return profile
