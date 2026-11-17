"""Feature 3: salary benchmarking from salary sites and live job postings."""
import json

from config import SALARY_SITES, JOB_SITES

SYSTEM = """You are a compensation analyst. Build a salary benchmark ONLY from the numbers present in
the search results. Convert every figure to one consistent currency and unit (for India: INR in LPA,
i.e. lakhs per annum; elsewhere use the local currency per year in thousands and say so).
If a source gives monthly pay, annualise it. Never invent a number; if data is thin, say so
and lower the confidence."""

SCHEMA = """{
  "currency": "INR", "unit": "LPA",
  "market": {"low": 0, "median": 0, "high": 0},
  "data_points": [{"source": "", "url": "", "type": "reported | posted",
                   "min": 0, "max": 0, "note": "e.g. 4-6 yrs, Bengaluru"}],
  "posted_range": {"min": 0, "max": 0},
  "expected_ctc_assessment": "how the candidate's expected CTC compares to market",
  "hike_guidance": "typical hike % for a switch at this level",
  "negotiation_tips": [""],
  "confidence": "low | medium | high",
  "caveats": ""
}"""


def benchmark(llm, search, role: str, years: float, location: str,
              current_ctc: str = "", expected_ctc: str = "", industry: str = "") -> dict:
    yrs = f"{years:g} years" if years else ""
    job_domains = [d for v in JOB_SITES.values() for d in v]
    queries = [
        (f"{role} salary {yrs} experience {location}", SALARY_SITES),
        (f"{role} salary {location} {industry}".strip(), SALARY_SITES),
        (f"{role} average salary {yrs} India LPA" if "india" in location.lower() or not location
         else f"{role} average salary {yrs} {location}", None),
        (f"{role} jobs {location} {yrs} salary", job_domains),
    ]
    results = []
    for q, domains in queries:
        try:
            results.extend(search.search(q, domains=domains, max_results=8))
        except Exception:
            continue

    seen, unique = set(), []
    for r in results:
        if r["url"] not in seen:
            seen.add(r["url"])
            unique.append({"title": r["title"], "url": r["url"], "content": r["content"][:800]})

    user = (
        f"ROLE: {role}\nEXPERIENCE: {yrs}\nLOCATION: {location}\nINDUSTRY: {industry}\n"
        f"CANDIDATE CURRENT CTC: {current_ctc or 'not given'}\n"
        f"CANDIDATE EXPECTED CTC: {expected_ctc or 'not given'}\n\n"
        f"SEARCH RESULTS:\n{json.dumps(unique[:30], ensure_ascii=False)}\n\n"
        f"Return JSON:\n{SCHEMA}"
    )
    out = llm.ask_json(SYSTEM, user)
    out["sources_checked"] = len(unique)
    return out
