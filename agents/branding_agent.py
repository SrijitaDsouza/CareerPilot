"""Feature 8: LinkedIn and job-portal profile optimisation for better recruiter reach."""
from core.utils import profile_brief

SYSTEM = """You are a LinkedIn top-voice career coach and an ex-recruiter who sources candidates daily
on LinkedIn Recruiter, Naukri Resdex, iimjobs and Indeed. You know how recruiter search works:
keyword matching on headline, current title, skills and About; filters on location, notice
period and experience; and how activity and completeness boost visibility.
Rules: write in the candidate's voice; use ONLY facts from their resume (use [placeholders] for
numbers they must add); respect platform limits: LinkedIn headline 220 characters, LinkedIn About
2,600 characters, Naukri resume headline 250 characters. Make text keyword-rich but human, not stuffed."""

SCHEMA = """{
  "profile_strength": 0,
  "strength_note": "one line on where the profiles stand",
  "priority_actions": ["top 5 changes in order of impact"],
  "keywords": ["15-20 search keywords recruiters use for the target roles"],
  "linkedin": {
    "headline_options": [{"style": "keyword-rich | value-led | aspirational", "text": ""}],
    "about": "ready-to-paste About section with a hook, proof points, skills line and call to action",
    "experience_rewrites": [{"title": "", "company": "", "text": "ready-to-paste description"}],
    "top_skills": ["ordered: pin the first 5"],
    "sections_to_add": [{"section": "", "what_to_add": "", "why": ""}],
    "featured_ideas": [""],
    "open_to_work": {"job_titles": [""], "locations": [""], "visibility_advice": ""},
    "custom_url": "suggested linkedin.com/in/... slug",
    "banner_idea": "",
    "recommendations_to_request": [{"from_whom": "", "ask_them_to_mention": ""}],
    "content_plan": [{"week": 1, "post_idea": ""}],
    "settings_tips": [""]
  },
  "naukri": {
    "resume_headline": "",
    "profile_summary": "",
    "key_skills": [""],
    "desired_career_profile": {"roles": [""], "industry": "", "locations": [""], "employment_type": "", "expected_ctc": ""},
    "it_skills_or_tools": [""],
    "visibility_tips": ["e.g. update profile regularly, notice period field, resume file name"]
  },
  "other_portals": [{"portal": "iimjobs | Indeed | Foundit | Instahyre | Glassdoor", "tips": [""]}],
  "mistakes_to_fix": ["problems spotted in the current profile text, if provided"]
}"""


def optimise(llm, profile: dict, resume_text: str, target_roles: list[str],
             current_linkedin: str = "", current_portal: str = "", tone: str = "Professional") -> dict:
    user = (
        f"CANDIDATE PROFILE:\n{profile_brief(profile)}\n\nRESUME:\n{resume_text[:12000]}\n\n"
        f"TARGET ROLES (cover all of them, primary first): {target_roles}\n"
        f"TONE: {tone}\n\n"
        f"CURRENT LINKEDIN PROFILE TEXT:\n{(current_linkedin or 'not provided')[:8000]}\n\n"
        f"CURRENT NAUKRI / PORTAL PROFILE TEXT:\n{(current_portal or 'not provided')[:4000]}\n\n"
        "Give 3 headline options. Give 4-6 sections_to_add (e.g. Featured, Licenses & certifications, "
        "Projects, Volunteering, Services) chosen for THIS candidate. Give a 4-week content_plan.\n\n"
        f"Return JSON:\n{SCHEMA}"
    )
    return llm.ask_json(SYSTEM, user, temperature=0.5)
