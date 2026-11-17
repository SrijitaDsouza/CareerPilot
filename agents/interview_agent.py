"""Feature 5: interview preparation guide + interactive mock interview with scoring."""
import json

from core.utils import profile_brief

COACH_SYSTEM = """You are a senior interviewer and interview coach who has hired for this kind of role
many times. You are direct, specific and encouraging. You coach with the STAR method
(Situation, Task, Action, Result) for behavioural answers and structured thinking for
technical and case answers."""


def prep_guide(llm, search, profile: dict, role: str, company: str = "", jd_text: str = "") -> str:
    research, sources = "", []
    if company and search:
        for q in (f"{company} {role} interview questions process", f"{company} company news"):
            try:
                for r in search.search(q, max_results=5, depth="basic"):
                    research += f"- {r['title']}: {r['content'][:400]}\n"
                    sources.append(r["url"])
            except Exception:
                continue
    user = (
        f"CANDIDATE:\n{profile_brief(profile)}\n\nROLE: {role}\nCOMPANY: {company or 'not specified'}\n"
        f"JOB DESCRIPTION:\n{(jd_text or 'not provided')[:6000]}\n\n"
        f"WEB RESEARCH (may be incomplete):\n{research or 'none'}\n\n"
        "Write a markdown interview prep guide with these sections:\n"
        "## Likely interview process\n## What they will assess\n"
        "## Your strongest stories to prepare (map the candidate's real experience to likely questions)\n"
        "## Topics to revise (technical / domain)\n## Weak spots and how to handle them\n"
        "## Smart questions to ask the interviewer\n## Day-before checklist\n"
        "Keep it specific to this candidate and role. Mark anything from web research as 'reported'."
    )
    guide = llm.ask(COACH_SYSTEM, user, temperature=0.5)
    if sources:
        guide += "\n\n**Sources:**\n" + "\n".join(f"- {u}" for u in dict.fromkeys(sources))
    return guide


def generate_questions(llm, profile: dict, role: str, jd_text: str = "", interview_type: str = "Mixed",
                       difficulty: str = "Medium", n: int = 6, company: str = "") -> list[dict]:
    user = (
        f"CANDIDATE:\n{profile_brief(profile)}\n\nROLE: {role}\nCOMPANY: {company or 'n/a'}\n"
        f"JD:\n{(jd_text or 'n/a')[:6000]}\n\nInterview round: {interview_type}\nDifficulty: {difficulty}\n\n"
        f"Write {n} realistic interview questions in the order an interviewer would ask them. "
        "Tie several to the candidate's actual resume. "
        'Return JSON: {"questions": [{"question": "", "category": "Behavioural|Technical|Situational|Role-specific|HR", '
        '"assesses": "what the interviewer is looking for", "hint": "short tip"}]}'
    )
    return llm.ask_json(COACH_SYSTEM, user, temperature=0.6).get("questions", [])


def evaluate_answer(llm, question: dict, answer: str, role: str, profile: dict) -> dict:
    user = (
        f"ROLE: {role}\nCANDIDATE BACKGROUND:\n{profile_brief(profile, 1500)}\n\n"
        f"QUESTION: {question.get('question')}\nIT ASSESSES: {question.get('assesses')}\n\n"
        f"CANDIDATE'S ANSWER:\n{answer}\n\n"
        "Evaluate like a real interviewer. Return JSON: "
        '{"score": 0-10, "verdict": "one line", "strengths": [""], "improvements": [""], '
        '"better_answer": "an improved answer in the candidate\'s voice, using only facts they could plausibly have; '
        'use [placeholders] for numbers you do not know", "follow_up": "a follow-up the interviewer may ask"}'
    )
    return llm.ask_json(COACH_SYSTEM, user, temperature=0.3)


def final_report(llm, role: str, history: list[dict]) -> str:
    compact = [{"q": h["q"]["question"], "a": h["a"][:1200], "score": h["eval"].get("score")} for h in history]
    user = (
        f"ROLE: {role}\nMOCK INTERVIEW TRANSCRIPT:\n{json.dumps(compact, ensure_ascii=False)}\n\n"
        "Write a short markdown report: overall readiness (score out of 100 and a hiring verdict: "
        "Strong hire / Hire / Borderline / Not yet), top 3 strengths, top 3 things to fix, and a "
        "focused 7-day practice plan."
    )
    return llm.ask(COACH_SYSTEM, user, temperature=0.4)
