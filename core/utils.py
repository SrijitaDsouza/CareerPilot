"""Shared helpers."""
import json


def profile_brief(p: dict, max_chars: int = 4000) -> str:
    """Compact text view of a profile, to keep prompts small."""
    if not p:
        return ""
    keys = [
        "name", "current_title", "current_company", "total_experience_years", "seniority",
        "current_location", "preferred_locations", "open_to_relocate", "work_modes",
        "current_ctc", "expected_ctc", "notice_period", "skills", "tools", "industries",
        "functional_areas", "education", "certifications", "target_roles", "target_industries",
        "achievements", "summary",
    ]
    lines = []
    for k in keys:
        v = p.get(k)
        if v in (None, "", [], {}):
            continue
        lines.append(f"{k}: {v if isinstance(v, (str, int, float)) else json.dumps(v, ensure_ascii=False)}")
    for e in (p.get("experience") or [])[:6]:
        hl = "; ".join((e.get("highlights") or [])[:3])
        lines.append(f"role: {e.get('title')} @ {e.get('company')} ({e.get('start')} to {e.get('end')}): {hl}")
    return "\n".join(lines)[:max_chars]


def resume_json_to_text(r: dict) -> str:
    """Flatten a generated resume dict into plain text (for ATS keyword checks)."""
    out = [r.get("name", ""), r.get("headline", ""), r.get("summary", "")]
    for g in r.get("skills", []):
        out.append(f"{g.get('category', '')}: {', '.join(g.get('items', []))}")
    for e in r.get("experience", []):
        out.append(f"{e.get('title', '')} {e.get('company', '')}")
        out.extend(e.get("bullets", []))
    for p in r.get("projects", []):
        out.append(f"{p.get('name', '')} {p.get('description', '')}")
    for ed in r.get("education", []):
        out.append(f"{ed.get('degree', '')} {ed.get('institution', '')}")
    out.extend(r.get("certifications", []))
    return "\n".join(x for x in out if x)


def to_float(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None
