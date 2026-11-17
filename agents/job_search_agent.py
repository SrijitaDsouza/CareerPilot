"""Feature 2: search job boards for up to 3 target roles and suggest roles to pursue.

Why per-portal searches: when many domains are searched in one query, the search engine
ranks by relevance and LinkedIn (huge, well-indexed) fills almost every slot. Searching each
portal separately guarantees every board gets its own share of results.

Flow: plan roles -> parallel search (role x portal) -> optional AI agent for extra queries
-> rank and extract openings, keeping a mix of sources.
"""
import json
from concurrent.futures import ThreadPoolExecutor

from config import JOB_SITES
from core.utils import profile_brief

PLAN_SYSTEM = """You are a career strategist. Advise which job titles this candidate should pursue.
Use real titles recruiters post on Indian and global job boards."""

AGENT_SYSTEM = """You are a job-search agent. Use the search_jobs tool to find extra CURRENT openings
that the first pass may have missed: try synonyms of the titles, seniority variants and nearby
cities. Run 3-6 searches, then reply 'DONE'."""

RANK_SYSTEM = """You are an expert recruiter. From raw search results grouped by job portal, pick
the openings that best fit the candidate. Use ONLY information present in the results; leave a
field "" if not stated. Never invent salaries, companies or URLs.
Keep a MIX of sources: do not drop results from Naukri, Indeed, Glassdoor, iimjobs, Shine etc.
just because LinkedIn has more. A page listing many openings for a search (e.g. '250 Data
Analyst jobs in Mumbai') is kind 'listing'; a single job ad is kind 'opening'."""


def _tool_schema(sites: list[str]) -> list:
    return [{
        "type": "function",
        "function": {
            "name": "search_jobs",
            "description": "Search one job portal for openings. Returns titles and URLs.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "e.g. 'Senior Data Analyst jobs Bengaluru'"},
                    "site": {"type": "string", "enum": sites},
                },
                "required": ["query", "site"],
            },
        },
    }]


def plan_roles(llm, profile: dict, roles: list[str], location: str, include_aspirational: bool) -> dict:
    user = (
        f"CANDIDATE:\n{profile_brief(profile)}\n\nTHEIR TARGET ROLES: {roles}\nLOCATION: {location}\n\n"
        'Return JSON: {"aspirational_roles": ["1-2 next-level titles"], '
        '"synonyms": {"<target role>": ["1-2 alternative titles recruiters use"]}, '
        '"role_advice": [{"role": "", "category": "direct|aspirational|pivot", "why": ""}]}'
        + ("" if include_aspirational else "\nLeave aspirational_roles empty.")
    )
    return llm.ask_json(PLAN_SYSTEM, user)


def find_jobs(llm, search, profile: dict, roles: list[str], location: str, sites: list[str],
              time_range: str | None = "month", include_aspirational: bool = True,
              max_jobs: int = 15, per_site: int = 5, deep_agent: bool = False) -> dict:
    roles = [r for r in roles if r][:3]
    plan = plan_roles(llm, profile, roles, location, include_aspirational)
    search_roles = roles + ((plan.get("aspirational_roles") or [])[:1] if include_aspirational else [])

    def one_search(role: str, site: str):
        q = f"{role} jobs {location}".strip()
        domains = JOB_SITES[site]
        res = search.search(q, domains=domains, max_results=per_site, depth="basic", time_range=time_range)
        undated = False
        if not res and time_range:  # many portals don't expose post dates -> retry without the filter
            res = search.search(q, domains=domains, max_results=per_site, depth="basic")
            undated = True
        return [{**r, "site": site, "role": role, "date_unverified": undated} for r in res]

    tasks = [(r, s) for r in search_roles for s in sites if s in JOB_SITES]
    collected: list[dict] = []
    errors = 0
    with ThreadPoolExecutor(max_workers=8) as pool:
        for fut in [pool.submit(one_search, r, s) for r, s in tasks]:
            try:
                collected.extend(fut.result())
            except Exception:
                errors += 1

    if deep_agent:
        def search_jobs(query: str, site: str):
            if site not in JOB_SITES:
                return {"error": "unknown site"}
            res = search.search(query, domains=JOB_SITES[site], max_results=per_site, depth="basic")
            collected.extend({**r, "site": site, "role": query, "date_unverified": False} for r in res)
            return [{"title": r["title"], "url": r["url"]} for r in res]
        try:
            llm.run_agent(AGENT_SYSTEM,
                          f"CANDIDATE:\n{profile_brief(profile, 1500)}\nROLES: {search_roles}\n"
                          f"SYNONYMS: {json.dumps(plan.get('synonyms', {}))}\nLOCATION: {location}\nSITES: {sites}",
                          _tool_schema(sites), {"search_jobs": search_jobs}, max_steps=6)
        except Exception:
            pass

    # de-duplicate and count per portal
    seen, unique = set(), []
    for r in collected:
        if r["url"] and r["url"] not in seen:
            seen.add(r["url"])
            unique.append(r)
    site_counts = {s: 0 for s in sites}
    for r in unique:
        site_counts[r["site"]] = site_counts.get(r["site"], 0) + 1

    # cap each portal so the ranker sees a balanced pool
    pool_by_site: dict[str, list] = {}
    for r in unique:
        if len(pool_by_site.setdefault(r["site"], [])) < 8:
            pool_by_site[r["site"]].append({"title": r["title"], "url": r["url"], "role_searched": r["role"],
                                             "content": r["content"][:500]})

    if not unique:
        return {"plan": plan, "jobs": [], "site_counts": site_counts, "searched": 0,
                "roles": search_roles, "errors": errors, "location": location}

    user = (
        f"CANDIDATE:\n{profile_brief(profile)}\n\nTARGET ROLES: {search_roles}\nLOCATION: {location}\n\n"
        f"RESULTS BY PORTAL:\n{json.dumps(pool_by_site, ensure_ascii=False)}\n\n"
        f"Return up to {max_jobs} items, best fit first, as JSON: "
        '{"jobs": [{"title": "", "company": "", "location": "", "experience": "", "salary": "", '
        '"url": "", "source": "portal name", "kind": "opening|listing", "role": "which target role it matches", '
        '"posted": "", "category": "direct|aspirational|pivot", "est_fit": 0, '
        '"match_reason": "one line", "summary": "2-3 lines on the role"}]}'
    )
    ranked = llm.ask_json(RANK_SYSTEM, user)
    return {"plan": plan, "jobs": ranked.get("jobs", []), "site_counts": site_counts,
            "searched": len(unique), "roles": search_roles, "errors": errors, "location": location}
