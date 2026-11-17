"""Feature 7: skills, certifications and roadmap to land the next role."""
from core.utils import profile_brief

SYSTEM = """You are a career advisor who knows which skills and certifications hiring managers
actually value (not just popular ones). Recommend only real, currently offered certifications
from reputable bodies (cloud providers, PMI, Scrum.org, Google, Microsoft, CFA Institute, etc.).
Prioritise by impact on getting shortlisted for the target role."""

SCHEMA = """{
  "readiness": 0,
  "readiness_note": "",
  "skill_gaps": [{"skill": "", "importance": "critical | important | nice", "why": "", "how_to_learn": ""}],
  "certifications": [{"name": "", "provider": "", "level": "", "cost": "free | paid | approx amount",
                      "duration": "", "why": "", "priority": 1}],
  "projects": [{"title": "", "description": "a portfolio project that proves the gap is closed"}],
  "roadmap": [{"phase": "Days 1-30", "focus": "", "actions": [""]}],
  "quick_wins": ["things to do this week, e.g. LinkedIn headline, resume keywords"],
  "positioning": "how to pitch yourself for the target role"
}"""


def advise(llm, search, profile: dict, target_role: str, timeframe: str = "3 months",
           budget: str = "Any", jd_text: str = "") -> dict:
    user = (
        f"CANDIDATE:\n{profile_brief(profile)}\n\nTARGET ROLE: {target_role}\nTIMEFRAME: {timeframe}\n"
        f"CERTIFICATION BUDGET: {budget}\nSAMPLE JD (optional):\n{(jd_text or 'n/a')[:5000]}\n\n"
        f"Return JSON:\n{SCHEMA}"
    )
    plan = llm.ask_json(SYSTEM, user, temperature=0.4)

    # Attach real links for the top certifications via web search
    if search:
        for cert in plan.get("certifications", [])[:5]:
            try:
                res = search.search(f"{cert.get('name')} {cert.get('provider', '')} official certification",
                                    max_results=3, depth="basic")
                if res:
                    cert["url"] = res[0]["url"]
            except Exception:
                continue
    return plan
