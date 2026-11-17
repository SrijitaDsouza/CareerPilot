"""Build ATS-friendly Word files: single column, standard headings, no tables/images."""
import io

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt, Inches


def _base_doc() -> Document:
    doc = Document()
    for s in doc.sections:
        s.top_margin = s.bottom_margin = Inches(0.6)
        s.left_margin = s.right_margin = Inches(0.75)
    normal = doc.styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = Pt(10.5)
    normal.paragraph_format.space_after = Pt(2)
    return doc


def _heading(doc, text):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(8)
    p.paragraph_format.space_after = Pt(3)
    run = p.add_run(text.upper())
    run.bold = True
    run.font.size = Pt(11.5)


def _bullet(doc, text):
    p = doc.add_paragraph(text, style="List Bullet")
    p.paragraph_format.space_after = Pt(1)


def _to_bytes(doc) -> bytes:
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def build_resume_docx(r: dict) -> bytes:
    doc = _base_doc()

    name = doc.add_paragraph()
    name.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = name.add_run(r.get("name", ""))
    run.bold = True
    run.font.size = Pt(18)

    if r.get("headline"):
        hp = doc.add_paragraph(r["headline"])
        hp.alignment = WD_ALIGN_PARAGRAPH.CENTER

    contact = [r.get(k) for k in ("location", "phone", "email", "linkedin", "portfolio") if r.get(k)]
    if contact:
        cp = doc.add_paragraph(" | ".join(contact))
        cp.alignment = WD_ALIGN_PARAGRAPH.CENTER

    if r.get("summary"):
        _heading(doc, "Professional Summary")
        doc.add_paragraph(r["summary"])

    if r.get("skills"):
        _heading(doc, "Skills")
        for g in r["skills"]:
            p = doc.add_paragraph()
            p.add_run(f"{g.get('category', 'Skills')}: ").bold = True
            p.add_run(", ".join(g.get("items", [])))

    if r.get("experience"):
        _heading(doc, "Professional Experience")
        for e in r["experience"]:
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(4)
            p.add_run(e.get("title", "")).bold = True
            p.add_run(f", {e.get('company', '')}")
            meta = " | ".join(x for x in (e.get("location"), e.get("dates")) if x)
            if meta:
                p.add_run(f"  ({meta})")
            for b in e.get("bullets", []):
                _bullet(doc, b)

    if r.get("projects"):
        _heading(doc, "Projects")
        for pr in r["projects"]:
            p = doc.add_paragraph()
            p.add_run(pr.get("name", "")).bold = True
            if pr.get("description"):
                p.add_run(f": {pr['description']}")

    if r.get("education"):
        _heading(doc, "Education")
        for ed in r["education"]:
            line = ", ".join(x for x in (ed.get("degree"), ed.get("institution"), ed.get("year")) if x)
            doc.add_paragraph(line)

    if r.get("certifications"):
        _heading(doc, "Certifications")
        for c in r["certifications"]:
            _bullet(doc, c)

    return _to_bytes(doc)


def build_cover_letter_docx(text: str) -> bytes:
    doc = _base_doc()
    doc.styles["Normal"].font.size = Pt(11)
    for para in text.split("\n\n"):
        p = doc.add_paragraph(para.strip())
        p.paragraph_format.space_after = Pt(10)
    return _to_bytes(doc)
