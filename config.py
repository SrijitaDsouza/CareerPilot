"""Central configuration for CareerPilot."""
import os
import re
from urllib.parse import quote_plus
from dotenv import load_dotenv

load_dotenv()

# Bump this whenever core code changes, so Streamlit rebuilds cached clients.
APP_VERSION = "0.4"

# Gemini through the OpenAI SDK (OpenAI-compatible endpoint)
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
# "gemini-flash-latest" is Google's moving alias for the current Flash model.
# Pin a specific model id in .env if you want stable behaviour.
DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-flash-latest")

# Models tried in order when the primary one is overloaded (503) or rate-limited (429).
# Comma-separated in .env, e.g. GEMINI_FALLBACK_MODELS=gemini-flash-lite-latest,gemini-2.5-flash
FALLBACK_MODELS = [m.strip() for m in os.getenv(
    "GEMINI_FALLBACK_MODELS", "gemini-flash-lite-latest,gemini-2.5-flash").split(",") if m.strip()]

REQUEST_TIMEOUT = float(os.getenv("GEMINI_TIMEOUT", "90"))   # seconds per request
RETRIES_PER_MODEL = int(os.getenv("GEMINI_RETRIES", "3"))    # attempts before switching model

# Job boards Tavily is allowed to search (label -> domains)
JOB_SITES = {
    "LinkedIn": ["linkedin.com"],
    "Naukri": ["naukri.com"],
    "Indeed": ["indeed.com", "in.indeed.com"],
    "Glassdoor": ["glassdoor.co.in", "glassdoor.com"],
    "iimjobs": ["iimjobs.com"],
    "Shine": ["shine.com"],
    "Foundit": ["foundit.in"],
    "Instahyre": ["instahyre.com"],
    "Hirist": ["hirist.tech"],
    "Cutshort": ["cutshort.io"],
    "Wellfound": ["wellfound.com"],
}

# Boards searched by default (each costs one Tavily credit per role)
DEFAULT_SITES = ["LinkedIn", "Naukri", "Indeed", "Glassdoor", "iimjobs", "Shine", "Foundit"]

# Country hint for Tavily ranking ("" to disable). Helps Indian portals surface.
SEARCH_COUNTRY = os.getenv("SEARCH_COUNTRY", "india")

MAX_TARGET_ROLES = 3

# Where chat history is kept: "auto" (local files when you run the app on your own
# computer, browser-session only when it's hosted), "local" or "session".
HISTORY_MODE = os.getenv("HISTORY_MODE", "auto")
HISTORY_DIR = os.getenv("HISTORY_DIR", os.path.join(os.path.dirname(__file__), "history"))


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")


def portal_search_url(site: str, role: str, location: str = "") -> str:
    """Direct search link on each portal, so users can always see the full live list."""
    q, l = quote_plus(role), quote_plus(location or "")
    loc_part = f"-jobs-in-{_slug(location)}" if location else "-jobs"
    urls = {
        "LinkedIn": f"https://www.linkedin.com/jobs/search/?keywords={q}&location={l}",
        "Naukri": f"https://www.naukri.com/{_slug(role)}{loc_part}",
        "Indeed": f"https://in.indeed.com/jobs?q={q}&l={l}",
        "Glassdoor": f"https://www.glassdoor.co.in/Job/jobs.htm?sc.keyword={q}",
        "Foundit": f"https://www.foundit.in/srp/results?query={q}&locations={l}",
        "Shine": f"https://www.shine.com/job-search/{_slug(role)}{loc_part}",
        "iimjobs": "https://www.iimjobs.com/",
        "Instahyre": "https://www.instahyre.com/",
        "Hirist": "https://www.hirist.tech/",
        "Cutshort": "https://cutshort.io/jobs",
        "Wellfound": "https://wellfound.com/jobs",
    }
    return urls.get(site, "")


# Sites that publish salary data
SALARY_SITES = [
    "ambitionbox.com", "glassdoor.co.in", "glassdoor.com", "payscale.com",
    "levels.fyi", "6figr.com", "naukri.com", "indeed.com", "in.indeed.com",
]

# Weights used for the overall fit score (must sum to 1.0)
FIT_WEIGHTS = {"skills": 0.45, "experience": 0.20, "location": 0.15, "requirements": 0.20}


def env_key(name: str) -> str:
    return os.getenv(name, "")
