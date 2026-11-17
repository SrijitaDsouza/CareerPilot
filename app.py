"""CareerPilot: AI job assistant (Streamlit UI).

Run:  streamlit run app.py
"""
import json
import os
import re
import sys
import uuid
from datetime import datetime

import openai
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# Make sure the app's own folder is importable, wherever the app is launched from
APP_DIR = os.path.dirname(os.path.abspath(__file__))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

if not os.path.isdir(os.path.join(APP_DIR, "agents")) or not os.path.isdir(os.path.join(APP_DIR, "core")):
    st.error("Setup problem: the `agents` and `core` folders must sit in the same folder as app.py. "
             f"Files found next to app.py: {sorted(os.listdir(APP_DIR))}")
    st.stop()

from agents import (branding_agent, career_agent, fit_agent, interview_agent, job_search_agent,
                    profile_agent, resume_agent, salary_agent)
from config import (APP_VERSION, DEFAULT_MODEL, DEFAULT_SITES, HISTORY_DIR, HISTORY_MODE, JOB_SITES,
                    MAX_TARGET_ROLES, portal_search_url)
from core.docx_builder import build_cover_letter_docx, build_resume_docx
from core.history import KINDS, FileHistory, SessionHistory
from core.llm import LLM, LLMUnavailable
from core.resume_parser import extract_text
from core.search import WebSearch
from core.utils import resume_json_to_text, to_float

st.set_page_config(page_title="CareerPilot · AI Job Assistant", page_icon="🧭", layout="wide")

# ------------------------------------------------------------------ state
DEFAULTS = {
    "profile": None, "resume_text": "", "jobs": None, "salary": None, "tailored": None,
    "cover": "", "fit": None, "career": None, "guide": "", "jd_text": "", "branding": None,
    "iv": None, "iv_counter": 0, "profile_ver": 0, "profile_hist_id": None, "flash": "",
}
for k, v in DEFAULTS.items():
    st.session_state.setdefault(k, v)
st.session_state.setdefault("session_history", [])
ss = st.session_state


def server_secret(name: str) -> str:
    try:
        if name in st.secrets:
            return st.secrets[name]
    except Exception:
        pass
    return os.getenv(name, "")


@st.cache_resource(show_spinner=False)
def get_llm(key: str, model: str, version: str = APP_VERSION) -> LLM:
    # `version` is part of the cache key: bumping APP_VERSION forces a fresh client
    return LLM(key, model)


@st.cache_resource(show_spinner=False)
def get_search(key: str, version: str = APP_VERSION) -> WebSearch:
    return WebSearch(key)


# ------------------------------------------------------------------ history
def running_locally() -> bool:
    try:
        host = (st.context.headers.get("host") or "").lower()
    except Exception:
        host = ""
    return any(h in host for h in ("localhost", "127.0.0.1", "[::1]"))


def get_history():
    mode = HISTORY_MODE
    if mode == "auto":
        mode = "local" if running_locally() else "session"
    if mode == "local":
        try:
            return FileHistory(HISTORY_DIR)
        except OSError:
            pass
    return SessionHistory(ss.session_history)


history = get_history()


def save(kind: str, title: str, data, entry_id: str | None = None):
    try:
        return history.save(kind, title, data, entry_id)
    except Exception as e:
        st.caption(f"Couldn't save this to history: {e}")


def restore(entry: dict):
    """Callback: load a history entry back into the app."""
    k, d = entry["kind"], entry["data"]
    if k == "profile":
        ss.profile, ss.resume_text = d["profile"], d.get("resume_text", "")
        ss.profile_ver += 1
        ss.profile_hist_id = entry["id"]
    elif k == "jobs":
        ss.jobs = d
    elif k == "salary":
        ss.salary = d
    elif k == "resume":
        ss.tailored = d
    elif k == "cover":
        ss.cover = d.get("text", "")
    elif k == "guide":
        ss.guide = d.get("text", "")
    elif k == "interview":
        ss.iv = d
    elif k == "fit":
        ss.fit, ss.jd_text = d.get("fit"), d.get("jd_text", "")
    elif k == "career":
        ss.career = d
    elif k == "branding":
        ss.branding = d
    ss.flash = f"Loaded {KINDS.get(k, k)}: {entry['title']}. Open its tab to see it."


def delete_entry(entry_id: str):
    history.delete(entry_id)


# ------------------------------------------------------------------ sidebar
with st.sidebar:
    st.title("🧭 CareerPilot")
    st.caption("Your AI job-search co-pilot")

    srv_gemini, srv_tavily = server_secret("GEMINI_API_KEY"), server_secret("TAVILY_API_KEY")
    with st.expander("API keys", expanded=not (srv_gemini and srv_tavily)):
        user_gemini = st.text_input("Gemini API key", type="password",
                                    help="Get one free at aistudio.google.com" +
                                         (" · leave blank to use the app's key" if srv_gemini else ""))
        user_tavily = st.text_input("Tavily API key", type="password",
                                    help="Get one at tavily.com" +
                                         (" · leave blank to use the app's key" if srv_tavily else ""))
        model = st.text_input("Gemini model", value=DEFAULT_MODEL)
    gemini_key, tavily_key = user_gemini or srv_gemini, user_tavily or srv_tavily

    llm = search = None
    try:
        llm = get_llm(gemini_key, model) if gemini_key else None
    except Exception as e:
        st.error(f"Gemini setup failed: {e}")
    try:
        search = get_search(tavily_key) if tavily_key else None
    except Exception as e:
        st.error(f"Tavily setup failed: {e}")

    st.write("Gemini:", "✅ connected" if llm else "⚠️ add a key")
    st.write("Web search:", "✅ connected" if search else "⚠️ add a key")
    if llm and st.button("Test Gemini models", width="stretch"):
        with st.spinner("Checking each model…"):
            for m in llm.models:
                status = llm.ping(m)
                st.write(("✅ " if status == "ok" else "❌ ") + f"`{m}` {'' if status == 'ok' else status}")

    if ss.profile:
        st.divider()
        st.markdown(f"**{ss.profile.get('name') or 'Candidate'}**  \n"
                    f"{ss.profile.get('current_title', '')} · {ss.profile.get('total_experience_years', '?')} yrs")
        st.caption("Targets: " + ", ".join(ss.profile.get("target_roles", [])))

    recent = history.list()[:5]
    if recent:
        st.divider()
        st.markdown("**Recent**")
        for e in recent:
            st.button(f"{KINDS.get(e['kind'], '').split(' ')[0]} {e['title'][:34]}", key=f"rec_{e['id']}",
                      on_click=restore, args=(e,), width="stretch")

    st.divider()
    if st.button("Start fresh", width="stretch", help="Clears the current screen. Your history is kept."):
        for k, v in DEFAULTS.items():
            ss[k] = v
        st.rerun()
    st.caption(f"CareerPilot v{APP_VERSION}")

if ss.flash:
    st.toast(ss.flash, icon="🕘")
    ss.flash = ""


# ------------------------------------------------------------------ helpers
def need(llm_needed=True, search_needed=False, profile_needed=True) -> bool:
    if llm_needed and not llm:
        st.info("Add your Gemini API key in the sidebar to continue.")
        return False
    if search_needed and not search:
        st.info("Add your Tavily API key in the sidebar to search the web.")
        return False
    if profile_needed and not ss.profile:
        st.info("Build your profile in the **Profile** tab first, or open a saved one from **History**.")
        return False
    return True


def run(label: str, fn, *args, **kwargs):
    """Run an agent call with a spinner and a readable error."""
    try:
        with st.spinner(label):
            result = fn(*args, **kwargs)
        if llm and llm.last_model_used != llm.model:
            st.caption(f"The main model was busy, so this used {llm.last_model_used}.")
        return result
    except LLMUnavailable as e:
        st.warning(f"⏳ {e}")
    except openai.APIStatusError as e:
        if e.status_code in (429, 503):
            st.warning("⏳ Gemini is overloaded right now. Please try again in a minute or two.")
        else:
            st.error(f"Gemini returned an error ({e.status_code}): {e}")
    except Exception as e:
        st.error(f"Something went wrong: {e}")
    return None


def target_roles() -> list[str]:
    p = ss.profile or {}
    roles = [r for r in (p.get("target_roles") or []) if r][:MAX_TARGET_ROLES]
    return roles or [p.get("current_title") or "Professional"]


def role_picker(label: str, key: str, extra=()) -> str:
    opts = list(dict.fromkeys(target_roles() + [x for x in extra if x])) + ["Other…"]
    choice = st.selectbox(label, opts, key=key)
    if choice == "Other…":
        return st.text_input("Type the role", key=f"{key}_custom").strip()
    return choice


def default_location() -> str:
    p = ss.profile or {}
    return (p.get("preferred_locations") or [p.get("current_location") or "India"])[0]


def first_number(text) -> float | None:
    m = re.search(r"\d+(?:\.\d+)?", str(text or ""))
    return float(m.group()) if m else None


def copy_block(text: str, limit: int | None = None):
    """Text with a built-in copy button, plus a character count against a platform limit."""
    st.code(text or "", language=None, wrap_lines=True)
    if limit:
        n = len(text or "")
        (st.caption if n <= limit else st.warning)(f"{n} / {limit} characters")


def set_target_job(job: dict):
    """Callback: use a job from search results as the target job."""
    text = ""
    if search and job.get("url"):
        try:
            text = search.extract(job["url"])[:12000]
        except Exception:
            text = ""
    if len(text) < 300:
        text = (f"{job.get('title', '')} at {job.get('company', '')}\nLocation: {job.get('location', '')}\n"
                f"Experience: {job.get('experience', '')}\n{job.get('summary', '')}")
    ss.jd_text = f"{text}\n\nSource: {job.get('url', '')}"
    ss.fit = None
    ss.flash = "Job set as your target. The Resume, Fit score and Interview tabs will use it."


# ------------------------------------------------------------------ target job (shared)
st.header("Find, fit and land your next role")
with st.expander("🎯 Target job description: used for resume tailoring, fit score and interview prep",
                 expanded=False):
    c1, c2 = st.columns([4, 1])
    jd_url = c1.text_input("Job posting URL (optional)", placeholder="https://www.naukri.com/job-listings-...")
    if c2.button("Fetch JD", width="stretch", disabled=not (search and jd_url)):
        fetched = run("Fetching job description…", search.extract, jd_url)
        if fetched:
            ss.jd_text = fetched[:12000]
        else:
            st.warning("Couldn't read that page (some sites block bots). Paste the JD below instead.")
    st.text_area("Job description", key="jd_text", height=200,
                 placeholder="Paste the full job description, or click 'Use as target job' on any search result.")

tabs = st.tabs(["1 · Profile", "2 · Jobs", "3 · Salary", "4 · Resume & cover letter", "5 · Interview prep",
                "6 · Fit score", "7 · Career advisor", "8 · LinkedIn & portals", "🕘 History"])

# ================================================================== 1. PROFILE
with tabs[0]:
    st.subheader("Tell us about you")
    left, right = st.columns([1, 1])
    with left:
        up = st.file_uploader("Upload resume (PDF, DOCX or TXT)", type=["pdf", "docx", "txt"])
        pasted = st.text_area("…or paste your resume text", height=160)
    with right:
        st.markdown("**Roles you're aiming for** (up to 3, most important first)")
        r1, r2, r3 = st.columns(3)
        tr = [r1.text_input("Role 1", placeholder="e.g. Product Manager", label_visibility="collapsed"),
              r2.text_input("Role 2", placeholder="Role 2 (optional)", label_visibility="collapsed"),
              r3.text_input("Role 3", placeholder="Role 3 (optional)", label_visibility="collapsed")]
        industries = st.text_input("Preferred industries", placeholder="e.g. Fintech, SaaS, BFSI")
        locations = st.text_input("Preferred locations", placeholder="e.g. Mumbai, Pune, Remote")
        c1, c2, c3 = st.columns(3)
        current_ctc = c1.text_input("Current CTC", placeholder="18 LPA")
        expected_ctc = c2.text_input("Expected CTC", placeholder="25 LPA")
        notice = c3.selectbox("Notice period", ["Immediate", "15 days", "30 days", "60 days", "90 days"])
        work_modes = st.multiselect("Work mode", ["Onsite", "Hybrid", "Remote"], default=["Hybrid", "Remote"])
        relocate = st.checkbox("Open to relocating", value=True)
        goals = st.text_area("Career goals or anything else", height=70,
                             placeholder="e.g. Want to move from services to a product company; interested in AI roles.")

    if st.button("Analyse my profile", type="primary", disabled=not llm):
        try:
            text = extract_text(up) if up else pasted.strip()
        except Exception as e:
            st.error(str(e))
            text = ""
        if len(text) < 100:
            st.warning("Upload a resume or paste at least a few lines of it.")
        else:
            prefs = {
                "target_roles": [x.strip() for x in tr if x.strip()][:MAX_TARGET_ROLES],
                "target_industries": [x.strip() for x in industries.split(",") if x.strip()],
                "preferred_locations": [x.strip() for x in locations.split(",") if x.strip()],
                "current_ctc": current_ctc, "expected_ctc": expected_ctc, "notice_period": notice,
                "work_modes": work_modes, "open_to_relocate": relocate, "career_goals": goals,
            }
            prof = run("Reading your resume…", profile_agent.build_profile, llm, text, prefs)
            if prof:
                for k in ("preferred_locations", "current_ctc", "expected_ctc", "work_modes", "notice_period"):
                    if prefs.get(k):
                        prof[k] = prefs[k]
                prof["open_to_relocate"] = relocate
                ss.profile, ss.resume_text = prof, text
                ss.jobs = ss.salary = ss.tailored = ss.fit = ss.career = ss.branding = None
                ss.profile_ver += 1
                e = save("profile", f"{prof.get('name') or 'Profile'} · {', '.join(prof.get('target_roles', []))}",
                         {"profile": prof, "resume_text": text})
                ss.profile_hist_id = e["id"] if e else None

    p = ss.profile
    if p:
        st.divider()
        st.markdown(f"### {p.get('name') or 'Your profile'}")
        st.write(p.get("summary", ""))
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Experience", f"{p.get('total_experience_years', '?')} yrs")
        m2.metric("Level", p.get("seniority", "?"))
        m3.metric("Current role", (p.get("current_title") or "?")[:24])
        m4.metric("Location", (p.get("current_location") or "?")[:24])

        options = list(dict.fromkeys((p.get("target_roles") or []) +
                                     [r.get("role") for r in p.get("suggested_roles", []) if r.get("role")]))
        chosen = st.multiselect("Your target roles (up to 3). Every tab uses these. Pick from suggestions or type your own.",
                                options, default=(p.get("target_roles") or [])[:MAX_TARGET_ROLES],
                                max_selections=MAX_TARGET_ROLES, accept_new_options=True,
                                key=f"tr_select_{ss.profile_ver}")
        if chosen and chosen != p.get("target_roles"):
            p["target_roles"] = chosen
            save("profile", f"{p.get('name') or 'Profile'} · {', '.join(chosen)}",
                 {"profile": p, "resume_text": ss.resume_text}, ss.profile_hist_id)

        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Skills**")
            st.write(", ".join(p.get("skills", []) + p.get("tools", [])) or "—")
            st.markdown("**Strengths**")
            for s in p.get("strengths", []):
                st.markdown(f"- {s}")
        with c2:
            st.markdown("**Gaps to address**")
            for s in p.get("gaps", []):
                st.markdown(f"- {s}")
        st.markdown("**Roles that suit you**")
        icon = {"direct": "🎯", "aspirational": "🚀", "pivot": "🔀"}
        for r in p.get("suggested_roles", []):
            st.markdown(f"{icon.get(r.get('type'), '•')} **{r.get('role')}** ({r.get('type')}): {r.get('rationale')}")
        with st.expander("Full profile data"):
            st.json(p)

# ================================================================== 2. JOBS
with tabs[1]:
    st.subheader("Matching openings from job boards")
    if need(search_needed=True):
        p = ss.profile
        roles = st.multiselect("Roles to search", target_roles(), default=target_roles(),
                               max_selections=MAX_TARGET_ROLES, accept_new_options=True,
                               key=f"job_roles_{ss.profile_ver}_{'|'.join(target_roles())}")
        c1, c2, c3 = st.columns([2, 1, 1])
        loc = c1.text_input("Location", value=default_location())
        fresh_label = c2.selectbox("Posted within", ["Past week", "Past month", "Any time"], index=1)
        n = c3.slider("Max results", 5, 30, 15)
        sites = st.multiselect("Job boards", list(JOB_SITES), default=DEFAULT_SITES)
        c1, c2 = st.columns(2)
        aspir = c1.toggle("Also search one next-level role", value=True)
        deep = c2.toggle("Deep search with AI agent (more queries, slower)", value=False)
        n_searches = (len(roles) + (1 if aspir else 0)) * len(sites)
        st.caption(f"About {n_searches} web searches (Tavily credits) per run.")

        if st.button("Find jobs", type="primary", disabled=not (roles and sites)):
            tr_map = {"Past week": "week", "Past month": "month", "Any time": None}
            res = run("Searching each job board… this can take a minute", job_search_agent.find_jobs,
                      llm, search, p, roles, loc, sites, tr_map[fresh_label], aspir, n, 5, deep)
            if res:
                ss.jobs = res
                save("jobs", f"{', '.join(res['roles'])} · {loc}", res)

        J = ss.jobs
        if J:
            counts = J.get("site_counts", {})
            st.markdown("**Results found per portal:** " + " · ".join(
                f"{s} {c}" if c else f"{s} 0 ⚠️" for s, c in counts.items()))
            if any(c == 0 for c in counts.values()):
                with st.expander("Why do some portals return few or no results?"):
                    st.markdown(
                        "None of these portals offer a public job-search API, and their terms don't allow "
                        "automated scraping, so CareerPilot reads them through a web search index (Tavily). "
                        "How much of each portal is in that index varies: LinkedIn job pages are public and "
                        "widely indexed, while Naukri, Indeed and Glassdoor load listings with JavaScript, "
                        "block crawlers on many pages, or require login, so fewer of their openings are "
                        "visible. Use the direct links below to see each portal's full live list.")
            with st.expander("Search directly on each portal", expanded=False):
                for role in J.get("roles", []):
                    links = [f"[{s}]({portal_search_url(s, role, J.get('location', loc))})" for s in counts]
                    st.markdown(f"**{role}:** " + " · ".join(links))

            plan = J.get("plan", {})
            if plan.get("role_advice"):
                with st.expander("Roles you should be targeting"):
                    for r in plan["role_advice"]:
                        st.markdown(f"- **{r.get('role')}** ({r.get('category')}): {r.get('why')}")

            jobs = J.get("jobs", [])
            if not jobs:
                st.warning("No openings found. Try 'Any time', a broader location or more job boards.")
            else:
                f1, f2 = st.columns(2)
                srcs = sorted({j.get("source") or "Other" for j in jobs})
                pick_src = f1.multiselect("Filter by portal", srcs, default=srcs)
                rls = sorted({j.get("role") or "Other" for j in jobs})
                pick_role = f2.multiselect("Filter by role", rls, default=rls)
                shown = [j for j in jobs if (j.get("source") or "Other") in pick_src
                         and (j.get("role") or "Other") in pick_role]
                openings = [j for j in shown if j.get("kind") != "listing"]
                listings = [j for j in shown if j.get("kind") == "listing"]

                for i, j in enumerate(openings):
                    with st.container(border=True):
                        a, b = st.columns([5, 1])
                        a.markdown(f"**[{j.get('title', 'Role')}]({j.get('url')})**  \n"
                                   f"{j.get('company') or 'Company not listed'} · {j.get('location') or '—'} · "
                                   f"{j.get('source', '')}")
                        b.metric("Est. fit", f"{j.get('est_fit', '?')}%")
                        details = " · ".join(x for x in [
                            f"For: {j['role']}" if j.get("role") else "",
                            f"Exp: {j['experience']}" if j.get("experience") else "",
                            f"Salary: {j['salary']}" if j.get("salary") else "",
                            f"Posted: {j['posted']}" if j.get("posted") else "",
                        ] if x)
                        if details:
                            st.caption(details)
                        st.write(j.get("match_reason", ""))
                        st.button("Use as target job", key=f"tgt_{i}", on_click=set_target_job, args=(j,))
                if listings:
                    st.markdown("**More openings on job-board search pages**")
                    for j in listings:
                        st.markdown(f"- [{j.get('title')}]({j.get('url')}) ({j.get('source', '')})")
                st.caption("Estimated fit is a quick read from the listing. Use the Fit score tab for a detailed match.")

# ================================================================== 3. SALARY
def show_salary(s: dict, p: dict):
    unit = f"{s.get('currency', '')} {s.get('unit', '')}".strip()
    mk = s.get("market", {})
    m1, m2, m3, m4 = st.columns(4)
    m1.metric(f"Low ({unit})", mk.get("low") or "—")
    m2.metric(f"Median ({unit})", mk.get("median") or "—")
    m3.metric(f"High ({unit})", mk.get("high") or "—")
    m4.metric("Confidence", (s.get("confidence") or "?").capitalize())
    pts = [d for d in s.get("data_points", []) if to_float(d.get("min")) is not None]
    if pts:
        fig = go.Figure()
        for d in pts:
            lo = to_float(d["min"])
            hi = to_float(d.get("max")) or lo
            fig.add_trace(go.Scatter(x=[lo, hi], y=[d.get("source", "")] * 2, mode="lines+markers",
                                     line=dict(width=8), showlegend=False, hovertext=d.get("note", "")))
        exp = first_number(p.get("expected_ctc"))
        if exp:
            fig.add_vline(x=exp, line_dash="dash", annotation_text="Your expected CTC")
        fig.update_layout(height=60 + 40 * len(pts), margin=dict(l=10, r=10, t=30, b=10),
                          xaxis_title=unit, title="Ranges by source")
        st.plotly_chart(fig, width="stretch")
    st.markdown(f"**Your expectation vs market:** {s.get('expected_ctc_assessment', '—')}")
    if s.get("hike_guidance"):
        st.markdown(f"**Typical switch hike:** {s['hike_guidance']}")
    st.markdown("**Negotiation tips**")
    for t in s.get("negotiation_tips", []):
        st.markdown(f"- {t}")
    if s.get("data_points"):
        with st.expander("Data sources"):
            st.dataframe(pd.DataFrame(s["data_points"]), width="stretch",
                         column_config={"url": st.column_config.LinkColumn("url")})
    st.caption(f"{s.get('caveats', '')} Figures are compiled from public web data and are estimates.")


with tabs[2]:
    st.subheader("Salary benchmark")
    if need(search_needed=True):
        p = ss.profile
        sal_roles = st.multiselect("Roles to compare (up to 3)", target_roles(), default=target_roles(),
                                   max_selections=MAX_TARGET_ROLES, accept_new_options=True,
                                   key=f"sal_roles_{ss.profile_ver}_{'|'.join(target_roles())}")
        c1, c2 = st.columns(2)
        yrs = c1.number_input("Years of experience", 0.0, 45.0,
                              float(to_float(p.get("total_experience_years")) or 0), 0.5)
        loc = c2.text_input("Location", value=default_location(), key="sal_loc")
        if st.button("Benchmark salary", type="primary", disabled=not sal_roles):
            results = {}
            for role in sal_roles:
                r = run(f"Collecting salary data for {role}…", salary_agent.benchmark, llm, search, role, yrs, loc,
                        p.get("current_ctc", ""), p.get("expected_ctc", ""), ", ".join(p.get("industries", [])[:2]))
                if r:
                    results[role] = r
            if results:
                ss.salary = {"location": loc, "years": yrs, "results": results}
                save("salary", f"{', '.join(results)} · {loc} · {yrs:g} yrs", ss.salary)

        S = ss.salary
        if S and S.get("results"):
            res = S["results"]
            st.caption(f"{S.get('location')} · {S.get('years', 0):g} years of experience")
            if len(res) > 1:
                rows = [{"Role": r, "Low": v.get("market", {}).get("low"), "Median": v.get("market", {}).get("median"),
                         "High": v.get("market", {}).get("high"),
                         "Unit": f"{v.get('currency', '')} {v.get('unit', '')}", "Confidence": v.get("confidence")}
                        for r, v in res.items()]
                st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
                fig = go.Figure()
                for lvl in ("Low", "Median", "High"):
                    fig.add_trace(go.Bar(name=lvl, x=[r["Role"] for r in rows],
                                         y=[to_float(r[lvl]) or 0 for r in rows]))
                fig.update_layout(barmode="group", height=320, margin=dict(l=10, r=10, t=30, b=10),
                                  title="Market pay by role", yaxis_title=rows[0]["Unit"])
                st.plotly_chart(fig, width="stretch")
            for role_tab, (role, s) in zip(st.tabs(list(res)), res.items()):
                with role_tab:
                    show_salary(s, p)

# ================================================================== 4. RESUME & COVER LETTER
with tabs[3]:
    st.subheader("Tailored resume and cover letter")
    if need():
        p = ss.profile
        if not ss.jd_text.strip():
            st.caption("Tip: add a target job description at the top of the page for the best tailoring.")
        target_role = role_picker("Tailor for role (used if no JD is given)", "res_role")

        if st.button("Tailor my resume", type="primary"):
            r = run("Rewriting your resume…", resume_agent.tailor_resume,
                    llm, p, ss.resume_text, ss.jd_text, target_role)
            if r:
                ss.tailored = r
                save("resume", f"Resume for {target_role}" + (" (from JD)" if ss.jd_text.strip() else ""), r)
        r = ss.tailored
        if r:
            kws = r.get("jd_keywords", [])
            if kws:
                before = resume_agent.ats_coverage(kws, ss.resume_text)
                after = resume_agent.ats_coverage(kws, resume_json_to_text(r))
                c1, c2 = st.columns(2)
                c1.metric("Keyword match: original", f"{before['pct']}%")
                c2.metric("Keyword match: tailored", f"{after['pct']}%", delta=f"{after['pct'] - before['pct']}%")
                if r.get("missing_keywords"):
                    st.warning("Not in your resume (add only if true): " + ", ".join(r["missing_keywords"]))
            with st.container(border=True):
                st.markdown(f"## {r.get('name', '')}\n{r.get('headline', '')}")
                st.markdown(f"**Summary**  \n{r.get('summary', '')}")
                for g in r.get("skills", []):
                    st.markdown(f"**{g.get('category')}:** {', '.join(g.get('items', []))}")
                for e in r.get("experience", []):
                    st.markdown(f"**{e.get('title')}**, {e.get('company')} ({e.get('dates', '')})")
                    for b in e.get("bullets", []):
                        st.markdown(f"- {b}")
            st.info("Replace every [add metric…] placeholder with your real numbers before sending.")
            with st.expander("What changed"):
                for c in r.get("changes_made", []):
                    st.markdown(f"- {c}")
            fname = (r.get("name") or "resume").replace(" ", "_")
            st.download_button("Download resume (.docx)", build_resume_docx(r), f"{fname}_Resume.docx",
                               mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document")

        st.divider()
        st.markdown("#### Cover letter")
        c1, c2, c3 = st.columns(3)
        company = c1.text_input("Company")
        manager = c2.text_input("Hiring manager (optional)")
        tone = c3.selectbox("Tone", ["Professional", "Warm", "Confident", "Concise"])
        if st.button("Write cover letter"):
            text = run("Writing…", resume_agent.cover_letter, llm, p, ss.resume_text, ss.jd_text,
                       company, target_role, manager, tone)
            if text:
                ss.cover = text
                save("cover", f"Cover letter · {target_role}" + (f" @ {company}" if company else ""), {"text": text})
        if ss.cover:
            edited = st.text_area("Edit before downloading", ss.cover, height=320)
            st.download_button("Download cover letter (.docx)", build_cover_letter_docx(edited),
                               "Cover_Letter.docx",
                               mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document")

# ================================================================== 5. INTERVIEW PREP
with tabs[4]:
    st.subheader("Interview preparation")
    if need():
        p = ss.profile
        c1, c2 = st.columns(2)
        with c1:
            iv_role = role_picker("Role", "iv_role")
        iv_company = c2.text_input("Company (optional)", key="iv_company")

        if st.button("Create my prep guide"):
            g = run("Researching and preparing…", interview_agent.prep_guide,
                    llm, search, p, iv_role, iv_company, ss.jd_text)
            if g:
                ss.guide = g
                save("guide", f"Prep guide · {iv_role}" + (f" @ {iv_company}" if iv_company else ""), {"text": g})
        if ss.guide:
            with st.expander("Your prep guide", expanded=True):
                st.markdown(ss.guide)

        st.divider()
        st.markdown("#### Mock interview")
        c1, c2, c3 = st.columns(3)
        iv_type = c1.selectbox("Round", ["Mixed", "HR / Behavioural", "Technical", "Hiring manager",
                                         "Case / Problem-solving"])
        diff = c2.selectbox("Difficulty", ["Easy", "Medium", "Hard"], index=1)
        nq = c3.slider("Questions", 3, 12, 6)
        if st.button("Start mock interview", type="primary"):
            qs = run("Preparing questions…", interview_agent.generate_questions,
                     llm, p, iv_role, ss.jd_text, iv_type, diff, nq, iv_company)
            if qs:
                ss.iv_counter += 1
                ss.iv = {"id": f"{ss.iv_counter}_{uuid.uuid4().hex[:4]}", "hist_id": uuid.uuid4().hex[:12],
                         "role": iv_role, "round": iv_type, "company": iv_company,
                         "questions": qs, "idx": 0, "history": [], "report": ""}
                st.rerun()

        iv = ss.iv
        if iv:
            def save_iv():
                done = len(iv["history"])
                save("interview", f"Mock interview · {iv['role']} · {iv.get('round', '')} "
                                  f"({done}/{len(iv['questions'])} answered)", iv, iv.get("hist_id"))

            for h in iv["history"]:
                with st.chat_message("assistant", avatar="🧑‍💼"):
                    st.markdown(h["q"]["question"])
                with st.chat_message("user"):
                    st.markdown(h["a"])
                with st.chat_message("assistant", avatar="📝"):
                    ev = h["eval"]
                    st.markdown(f"**{ev.get('score', '?')}/10** · {ev.get('verdict', '')}")
                    with st.expander("Feedback and a stronger answer"):
                        st.markdown("**What worked:**\n" + "\n".join(f"- {x}" for x in ev.get("strengths", [])))
                        st.markdown("**Improve:**\n" + "\n".join(f"- {x}" for x in ev.get("improvements", [])))
                        st.markdown(f"**Stronger answer:**\n\n{ev.get('better_answer', '')}")
                        if ev.get("follow_up"):
                            st.markdown(f"**Possible follow-up:** {ev['follow_up']}")

            if iv["idx"] < len(iv["questions"]):
                q = iv["questions"][iv["idx"]]
                with st.chat_message("assistant", avatar="🧑‍💼"):
                    st.markdown(f"**Question {iv['idx'] + 1} of {len(iv['questions'])}** · {q.get('category', '')}\n\n"
                                f"{q.get('question')}")
                    with st.expander("Hint"):
                        st.write(q.get("hint", ""))
                ans = st.text_area("Your answer", key=f"ans_{iv['id']}_{iv['idx']}", height=170,
                                   placeholder="Answer as you would in the interview.")
                b1, b2 = st.columns([1, 5])
                if b1.button("Submit answer", type="primary", disabled=not ans.strip()):
                    ev = run("Evaluating…", interview_agent.evaluate_answer, llm, q, ans, iv["role"], p)
                    if ev:
                        iv["history"].append({"q": q, "a": ans, "eval": ev})
                        iv["idx"] += 1
                        save_iv()
                        st.rerun()
                if b2.button("Skip question"):
                    iv["idx"] += 1
                    st.rerun()
            else:
                scores = [to_float(h["eval"].get("score")) or 0 for h in iv["history"]]
                if scores:
                    st.success(f"Interview complete. Average score: {sum(scores) / len(scores):.1f}/10")
                    if not iv["report"] and st.button("Get my readiness report", type="primary"):
                        iv["report"] = run("Writing report…", interview_agent.final_report,
                                           llm, iv["role"], iv["history"]) or ""
                        save_iv()
                        st.rerun()
                    if iv["report"]:
                        st.markdown(iv["report"])

# ================================================================== 6. FIT SCORE
with tabs[5]:
    st.subheader("How well do you fit this job?")
    if need():
        if not ss.jd_text.strip():
            st.info("Add a target job description at the top of the page (or pick one from the Jobs tab).")
        elif st.button("Calculate fit", type="primary"):
            f = run("Comparing you with the job…", fit_agent.compute_fit,
                    llm, ss.profile, ss.resume_text, ss.jd_text)
            if f:
                ss.fit = f
                jd = f["jd"]
                save("fit", f"{jd.get('title') or 'Job'}" + (f" @ {jd['company']}" if jd.get("company") else "")
                     + f" · {f['overall']}%", {"fit": f, "jd_text": ss.jd_text[:12000]})
        f = ss.fit
        if f:
            jd = f["jd"]
            st.markdown(f"**{jd.get('title', 'Role')}** {('at ' + jd['company']) if jd.get('company') else ''}")
            c1, c2 = st.columns([1, 2])
            with c1:
                gauge = go.Figure(go.Indicator(
                    mode="gauge+number", value=f["overall"], number={"suffix": "%"},
                    title={"text": f["band"]},
                    gauge={"axis": {"range": [0, 100]}, "bar": {"color": "#2B59C3"},
                           "steps": [{"range": [0, 50], "color": "#F3E1E1"},
                                     {"range": [50, 65], "color": "#F6EDD9"},
                                     {"range": [65, 80], "color": "#E3EEDF"},
                                     {"range": [80, 100], "color": "#D2E7CF"}]},
                ))
                gauge.update_layout(height=260, margin=dict(l=20, r=20, t=50, b=10))
                st.plotly_chart(gauge, width="stretch")
            with c2:
                sc = f["scores"]
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Skills", f"{sc['skills']}%")
                m2.metric("Experience", f"{sc['experience']}%")
                m3.metric("Location", f"{sc['location']}%")
                m4.metric("Requirements", f"{sc['requirements']}%")
                st.caption(f"{f['experience_note']} · {f['location_note']}")
                st.write(jd.get("alignment_reasoning", ""))
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("**✅ Must-haves you have**")
                st.write(", ".join(f["matched_must"]) or "—")
                st.markdown("**✅ Nice-to-haves you have**")
                st.write(", ".join(f["matched_nice"]) or "—")
            with c2:
                st.markdown("**❌ Missing must-haves**")
                st.write(", ".join(f["missing_must"]) or "None 🎉")
                st.markdown("**➖ Missing nice-to-haves**")
                st.write(", ".join(f["missing_nice"]) or "None")
            if jd.get("red_flags"):
                st.warning("Watch out: " + "; ".join(jd["red_flags"]))
            st.markdown("**How to improve your chances**")
            for rec in jd.get("recommendations", []):
                st.markdown(f"- {rec}")

# ================================================================== 7. CAREER ADVISOR
with tabs[6]:
    st.subheader("Skills and certifications for your next role")
    if need():
        p = ss.profile
        aspirational = [r.get("role") for r in p.get("suggested_roles", []) if r.get("type") != "direct"]
        c1, c2, c3 = st.columns([2, 1, 1])
        with c1:
            tgt = role_picker("Next role you want", "car_role", extra=aspirational)
        tf = c2.selectbox("Timeframe", ["1 month", "3 months", "6 months", "12 months"], index=1)
        budget = c3.selectbox("Certification budget", ["Free only", "Under ₹25k", "Any"], index=2)
        if st.button("Build my plan", type="primary"):
            c = run("Building your plan…", career_agent.advise, llm, search, p, tgt, tf, budget, ss.jd_text)
            if c:
                c["target_role"] = tgt
                ss.career = c
                save("career", f"Plan for {tgt} · {tf}", c)
        c = ss.career
        if c:
            if c.get("target_role"):
                st.caption(f"Plan for: {c['target_role']}")
            st.metric("Readiness for the target role", f"{c.get('readiness', '?')}%")
            st.write(c.get("readiness_note", ""))
            if c.get("skill_gaps"):
                st.markdown("**Skill gaps**")
                st.dataframe(pd.DataFrame(c["skill_gaps"]), width="stretch", hide_index=True)
            if c.get("certifications"):
                st.markdown("**Recommended certifications**")
                df = pd.DataFrame(sorted(c["certifications"], key=lambda x: x.get("priority", 99)))
                st.dataframe(df, width="stretch", hide_index=True,
                             column_config={"url": st.column_config.LinkColumn("link")})
            if c.get("roadmap"):
                st.markdown("**Roadmap**")
                for ph in c["roadmap"]:
                    with st.expander(f"{ph.get('phase')}: {ph.get('focus')}"):
                        for a in ph.get("actions", []):
                            st.markdown(f"- {a}")
            if c.get("projects"):
                st.markdown("**Portfolio projects that prove it**")
                for pr in c["projects"]:
                    st.markdown(f"- **{pr.get('title')}**: {pr.get('description')}")
            if c.get("quick_wins"):
                st.markdown("**Quick wins this week**")
                for q in c["quick_wins"]:
                    st.markdown(f"- {q}")
            if c.get("positioning"):
                st.info(c["positioning"])

# ================================================================== 8. LINKEDIN & PORTALS
with tabs[7]:
    st.subheader("Upgrade your LinkedIn and job-portal profiles")
    if need():
        p = ss.profile
        st.caption("Optimising for: " + ", ".join(target_roles()) + ". Change these in the Profile tab.")
        c1, c2 = st.columns(2)
        with c1:
            li_pdf = st.file_uploader("Your current LinkedIn profile as PDF (optional)", type=["pdf"],
                                      help="On LinkedIn, open your profile, click More (or Resources), then Save to PDF.")
            li_text = st.text_area("…or paste your current headline, About and experience", height=140)
        with c2:
            portal_text = st.text_area("Your current Naukri / portal profile (optional)", height=120,
                                       placeholder="Paste your resume headline, profile summary and key skills.")
            br_tone = st.selectbox("Writing tone", ["Professional", "Warm and approachable", "Bold and confident",
                                                    "Technical and precise"])
        if st.button("Optimise my profiles", type="primary"):
            current_li = li_text
            if li_pdf:
                try:
                    current_li = extract_text(li_pdf) + "\n" + li_text
                except Exception as e:
                    st.warning(f"Couldn't read that PDF ({e}). Continuing without it.")
            b = run("Reviewing your profiles…", branding_agent.optimise, llm, p, ss.resume_text, target_roles(),
                    current_li, portal_text, br_tone)
            if b:
                ss.branding = b
                save("branding", f"LinkedIn & portals · {', '.join(target_roles())}", b)

        b = ss.branding
        if b:
            c1, c2 = st.columns([1, 3])
            c1.metric("Profile strength", f"{b.get('profile_strength', '?')}/100")
            with c2:
                st.write(b.get("strength_note", ""))
                st.markdown("**Do these first**")
                for i, a in enumerate(b.get("priority_actions", []), 1):
                    st.markdown(f"{i}. {a}")
            if b.get("keywords"):
                st.markdown("**Keywords recruiters search for:** " + ", ".join(b["keywords"]))
            if b.get("mistakes_to_fix"):
                st.warning("Fix in your current profile: " + "; ".join(b["mistakes_to_fix"]))

            t_li, t_nk, t_ot = st.tabs(["LinkedIn", "Naukri", "Other portals"])
            li = b.get("linkedin", {})
            with t_li:
                st.markdown("##### Headline options")
                for h in li.get("headline_options", []):
                    st.caption(h.get("style", ""))
                    copy_block(h.get("text", ""), 220)
                st.markdown("##### About section")
                copy_block(li.get("about", ""), 2600)
                if li.get("experience_rewrites"):
                    st.markdown("##### Experience descriptions")
                    for e in li["experience_rewrites"]:
                        st.markdown(f"**{e.get('title')}**, {e.get('company')}")
                        copy_block(e.get("text", ""))
                if li.get("top_skills"):
                    st.markdown("##### Skills (pin the first five)")
                    st.write(", ".join(li["top_skills"]))
                if li.get("sections_to_add"):
                    st.markdown("##### Sections to add or strengthen")
                    st.dataframe(pd.DataFrame(li["sections_to_add"]), width="stretch", hide_index=True)
                otw = li.get("open_to_work", {})
                if otw:
                    st.markdown("##### Open to work settings")
                    st.markdown(f"- Job titles: {', '.join(otw.get('job_titles', []))}\n"
                                f"- Locations: {', '.join(otw.get('locations', []))}\n"
                                f"- Visibility: {otw.get('visibility_advice', '')}")
                c1, c2 = st.columns(2)
                with c1:
                    if li.get("custom_url"):
                        st.markdown(f"**Custom URL:** `{li['custom_url']}`")
                    if li.get("banner_idea"):
                        st.markdown(f"**Banner idea:** {li['banner_idea']}")
                    if li.get("featured_ideas"):
                        st.markdown("**Featured section ideas**")
                        for x in li["featured_ideas"]:
                            st.markdown(f"- {x}")
                with c2:
                    if li.get("recommendations_to_request"):
                        st.markdown("**Recommendations to request**")
                        for x in li["recommendations_to_request"]:
                            st.markdown(f"- {x.get('from_whom')}: ask them to mention {x.get('ask_them_to_mention')}")
                    if li.get("settings_tips"):
                        st.markdown("**Settings to check**")
                        for x in li["settings_tips"]:
                            st.markdown(f"- {x}")
                if li.get("content_plan"):
                    st.markdown("##### 4-week posting plan")
                    for x in li["content_plan"]:
                        st.markdown(f"- Week {x.get('week')}: {x.get('post_idea')}")
            nk = b.get("naukri", {})
            with t_nk:
                st.markdown("##### Resume headline")
                copy_block(nk.get("resume_headline", ""), 250)
                st.markdown("##### Profile summary")
                copy_block(nk.get("profile_summary", ""))
                if nk.get("key_skills"):
                    st.markdown("##### Key skills")
                    copy_block(", ".join(nk["key_skills"]))
                dcp = nk.get("desired_career_profile", {})
                if dcp:
                    st.markdown("##### Desired career profile")
                    st.markdown("\n".join(f"- **{k.replace('_', ' ').capitalize()}:** "
                                          f"{', '.join(v) if isinstance(v, list) else v}" for k, v in dcp.items() if v))
                if nk.get("it_skills_or_tools"):
                    st.markdown("**IT skills / tools section:** " + ", ".join(nk["it_skills_or_tools"]))
                if nk.get("visibility_tips"):
                    st.markdown("##### Get seen by more recruiters")
                    for x in nk["visibility_tips"]:
                        st.markdown(f"- {x}")
            with t_ot:
                for o in b.get("other_portals", []):
                    st.markdown(f"**{o.get('portal')}**")
                    for x in o.get("tips", []):
                        st.markdown(f"- {x}")

# ================================================================== HISTORY
def preview(e: dict) -> str:
    d, k = e.get("data", {}), e.get("kind")
    try:
        if k == "profile":
            pr = d["profile"]
            return f"{pr.get('current_title', '')} · {pr.get('total_experience_years', '?')} yrs · targets: {', '.join(pr.get('target_roles', []))}"
        if k == "jobs":
            return f"{len(d.get('jobs', []))} jobs from {d.get('searched', 0)} results · " + \
                   ", ".join(f"{s} {c}" for s, c in d.get("site_counts", {}).items())
        if k == "salary":
            return " · ".join(f"{r}: median {v.get('market', {}).get('median', '?')} {v.get('unit', '')}"
                              for r, v in d.get("results", {}).items())
        if k == "fit":
            return f"Overall {d['fit']['overall']}% ({d['fit']['band']})"
        if k == "interview":
            sc = [to_float(h["eval"].get("score")) or 0 for h in d.get("history", [])]
            return f"{len(sc)} answers · avg {sum(sc) / len(sc):.1f}/10" if sc else "Not answered yet"
        if k == "career":
            return f"Readiness {d.get('readiness', '?')}% · {len(d.get('certifications', []))} certifications"
        if k == "branding":
            return f"Profile strength {d.get('profile_strength', '?')}/100"
        if k in ("cover", "guide"):
            return (d.get("text", "")[:160] + "…")
        if k == "resume":
            return d.get("headline", "")
    except Exception:
        pass
    return ""


with tabs[8]:
    st.subheader("Your history")
    if history.mode == "local":
        st.caption(f"Everything you generate is saved automatically on this computer, in `{HISTORY_DIR}`.")
    else:
        st.caption("This app is running on a server, so history is kept only while this browser tab is open. "
                   "Download a backup to keep it on your computer, and load it next time.")

    c1, c2 = st.columns(2)
    with c1:
        st.download_button("Download history backup (.json)", history.export_bytes(),
                           f"careerpilot_history_{datetime.now():%Y%m%d}.json", mime="application/json",
                           width="stretch")
    with c2:
        backup = st.file_uploader("Load a history backup", type=["json"], label_visibility="collapsed")
        if backup and st.button("Load backup", width="stretch"):
            try:
                n_loaded = history.import_bytes(backup.getvalue())
                st.success(f"Loaded {n_loaded} items.")
            except Exception as e:
                st.error(f"That file isn't a CareerPilot backup ({e}).")

    entries = history.list()
    if not entries:
        st.info("Nothing saved yet. Results from every tab will appear here.")
    else:
        f1, f2 = st.columns([1, 2])
        kinds = sorted({e["kind"] for e in entries}, key=list(KINDS).index)
        pick = f1.multiselect("Show", kinds, default=kinds, format_func=lambda k: KINDS.get(k, k))
        q = f2.text_input("Search history", placeholder="e.g. Product Manager, Mumbai").lower()
        shown = [e for e in entries if e["kind"] in pick and (not q or q in e["title"].lower())]
        st.caption(f"{len(shown)} of {len(entries)} items")
        for e in shown:
            when = e.get("ts", "").replace("T", " ")[:16]
            with st.container(border=True):
                a, b1, b2, b3 = st.columns([6, 1, 1, 1])
                a.markdown(f"**{KINDS.get(e['kind'], e['kind'])}** · {e['title']}  \n"
                           f"<small>{when} · {preview(e)}</small>", unsafe_allow_html=True)
                b1.button("Open", key=f"open_{e['id']}", on_click=restore, args=(e,), width="stretch")
                b2.download_button("Save", json.dumps(e, ensure_ascii=False, indent=1).encode("utf-8"),
                                   f"{e['kind']}_{e['id']}.json", mime="application/json",
                                   key=f"dl_{e['id']}", width="stretch")
                b3.button("Delete", key=f"del_{e['id']}", on_click=delete_entry, args=(e["id"],), width="stretch")
        with st.expander("Delete all history"):
            if st.checkbox("Yes, permanently delete everything in my history"):
                if st.button("Delete all", type="primary"):
                    history.clear()
                    st.rerun()
