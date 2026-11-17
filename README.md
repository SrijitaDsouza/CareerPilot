# 🧭 CareerPilot: AI Job Assistant

An AI job-search co-pilot built with **Python + Streamlit**, **Gemini (via the OpenAI SDK)** and **Tavily** web search.

| # | Feature | Where |
|---|---------|-------|
| 1 | Understands the resume, experience, expectations and target roles | `agents/profile_agent.py` |
| 2 | Searches Naukri, LinkedIn, Indeed, Glassdoor, iimjobs, Shine, Foundit, Instahyre and more; suggests direct, aspirational and pivot roles | `agents/job_search_agent.py` |
| 3 | Salary benchmarking from salary sites and live postings, compared with your expected CTC | `agents/salary_agent.py` |
| 4 | Tailored ATS-friendly resume (.docx) with keyword-match score, plus cover letter | `agents/resume_agent.py` |
| 5 | Interview prep guide (with company research) and a scored mock interview | `agents/interview_agent.py` |
| 6 | Skill / experience / location / requirement match with % fit | `agents/fit_agent.py` |
| 7 | Skill gaps, certifications (with links), roadmap and portfolio projects | `agents/career_agent.py` |
| 8 | LinkedIn and Naukri profile makeover: headlines, About, sections to add, skills, posting plan | `agents/branding_agent.py` |
| 🕘 | History of everything you generate, saved on your computer, with backup and restore | `core/history.py` |

Up to **3 target roles** are supported: set them in the Profile tab and every tab uses them.

---

## Quick start

```bash
# 1. Python 3.10+
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# 2. Install
pip install -r requirements.txt

# 3. Keys
cp .env.example .env               # then edit .env
#   GEMINI_API_KEY  -> https://aistudio.google.com/apikey
#   TAVILY_API_KEY  -> https://app.tavily.com

# 4. Run
streamlit run app.py
```

Open http://localhost:8501, upload a resume in **Profile**, then work through the tabs.

---

## How it works

```
app.py                     Streamlit UI (7 tabs + shared "Target job" panel)
config.py                  Model, job-board domains, salary sites, fit weights
core/
  llm.py                   Gemini via OpenAI SDK: ask(), ask_json(), run_agent() tool-calling loop
  search.py                Tavily search + page extraction (with cache)
  resume_parser.py         PDF / DOCX / TXT -> text
  docx_builder.py          ATS-safe Word output (single column, standard headings)
  utils.py                 Profile summariser, helpers
agents/                    One module per feature (see table above)
```

**Gemini through the OpenAI SDK**

```python
from openai import OpenAI
client = OpenAI(api_key=GEMINI_API_KEY,
                base_url="https://generativelanguage.googleapis.com/v1beta/openai/")
```

The default model is `gemini-flash-latest` (Google's moving alias for the current Flash model). Set `GEMINI_MODEL` in `.env` to pin a version, or use a Pro model for higher-quality resume writing.

**The agent.** The job search uses real function calling: Gemini decides which queries to run and calls a `search_jobs` tool (Tavily, restricted to job-board domains) several times, then a ranking step turns raw results into structured openings. If tool calling fails, it falls back to a planned set of queries, so the feature always works.

**Trustworthy numbers.**
- Fit percentages are computed in Python from extracted requirements (weights in `config.FIT_WEIGHTS`), so they're consistent and explainable. The LLM only judges responsibility alignment.
- Salary figures must come from search results; each data point keeps its source URL, and a confidence level is shown.
- The resume writer is instructed never to invent facts. Where a metric is missing it inserts `[add metric…]` placeholders for the candidate to fill in honestly.

---

## Job portals: what to expect

Each portal is searched separately (role × portal) so LinkedIn can't crowd out the others; the Jobs tab shows how many results came from each portal. None of these portals offers a public job-search API and their terms prohibit scraping, so results come from Tavily's web index. LinkedIn job pages are widely indexed; Naukri, Indeed and Glassdoor expose fewer pages to crawlers, so they can return fewer results. The Jobs tab always gives direct search links for every portal. A run costs about (roles × portals) Tavily credits.

## History

- **Running on your own computer** (`localhost`): every result is saved automatically as JSON files in `history/` inside the project folder.
- **Hosted publicly**: history stays in the visitor's browser session only (one visitor's resume is never written to a shared server). Visitors use **Download history backup** to keep it on their computer and **Load a backup** next time.
- Override with `HISTORY_MODE=local` or `HISTORY_MODE=session` in `.env`.

## Deploy publicly (Streamlit Community Cloud, free)

1. Push this folder to a GitHub repo (`.env` is git-ignored).
2. Go to https://share.streamlit.io → **New app** → pick the repo, main file `app.py`.
3. In **App settings → Secrets**, paste the contents of `.streamlit/secrets.toml.example` with your keys.

**Keys and cost.** If you set server keys, every visitor uses your quota. Visitors can paste their own Gemini/Tavily keys in the sidebar (bring-your-own-key), which overrides yours. For a public launch, either leave server keys unset (BYOK only) or add rate limiting first (see roadmap).

Other hosts: Render, Railway, Hugging Face Spaces (Streamlit SDK) or Google Cloud Run all work with `streamlit run app.py --server.port $PORT`.

---

## Important notes for a public app

- **Job boards' terms.** The app does not scrape LinkedIn, Naukri etc. It uses Tavily's search index and links users to the original postings. Don't add direct scrapers without checking each site's terms; for scale, consider official partner APIs or licensed job-data providers.
- **Privacy.** Resumes live only in the user's Streamlit session memory and aren't saved. If you add a database, add a privacy policy and consent (India's DPDP Act applies to personal data such as resumes).
- **Accuracy.** Salary and fit outputs are estimates; the UI says so. Keep those disclaimers.

---

## Roadmap: suggested next steps

1. **Rate limiting and usage caps** per session/IP before opening to the public.
2. **User accounts + database** (Supabase/Postgres) to save profiles, resumes, applications and interview history.
3. **Application tracker**: saved jobs, status pipeline, follow-up reminders.
4. **Job alerts**: scheduled searches that email new matches daily/weekly.
5. **Voice mock interviews**: speech-to-text answers, spoken questions.
6. **Resume templates**: more ATS-safe layouts and PDF export.
7. **Batch fit scoring**: score every search result against the full JD automatically.
8. **Move to FastAPI + React** when you need a custom UI, mobile app or many concurrent users; the `agents/` and `core/` modules are UI-independent and can be reused as-is.
