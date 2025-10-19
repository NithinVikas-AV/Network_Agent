# report_generate.py
import os
import json
from datetime import datetime, timezone
from typing import Dict, Any, List

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib import colors

# Firestore client (import after we set GRPC env vars)
from google.cloud import firestore

# LLM interface used in your project
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage

from dotenv import load_dotenv
load_dotenv(override=True)

# --- Configuration (adjust environment variables or pass in) ---
PROJECT_ID = os.getenv("PROJECT_ID")
COLLECTION_NAME = os.getenv("COLLECTION_NAME")
DOCUMENT_NAME = os.getenv("DOCUMENT_NAME")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# sanity checks
if not COLLECTION_NAME or not DOCUMENT_NAME:
    raise RuntimeError("Please set COLLECTION_NAME and DOCUMENT_NAME environment variables (or add them to .env).")

# --- Initialize firestore and LLM ---
db = firestore.Client(project=PROJECT_ID)

llm = ChatGoogleGenerativeAI(
    model="gemini-2.0-flash",
    google_api_key=GEMINI_API_KEY,
    temperature=0.2
)

# -------------------------
# Helpers
# -------------------------
def fetch_session(session_doc_name: str = DOCUMENT_NAME, collection: str = COLLECTION_NAME) -> Dict[str, Any]:
    doc_ref = db.collection(collection).document(session_doc_name)
    snapshot = doc_ref.get()
    if not snapshot.exists:
        raise RuntimeError(f"No session document found at {collection}/{session_doc_name}")
    return snapshot.to_dict()


def build_prompt_from_session(session_data: Dict[str, Any]) -> str:
    """
    Simpler, robust prompt builder that avoids format-string brace issues.
    We pass a short excerpt of the chat history to the LLM and ask for a compact JSON report.
    """

    messages = session_data.get("messages", [])
    recon = session_data.get("recon", {})  # optional
    attacks = session_data.get("attacks", {})  # optional
    timestamp = session_data.get("session_start", session_data.get("created_at", datetime.now(timezone.utc).isoformat()))

    # short excerpt of recent messages (to avoid token limits)
    def shortlist_msgs(msgs, limit_chars=4000):
        s = []
        c = 0
        for m in reversed(msgs):
            text = m.get("content", "") if isinstance(m, dict) else str(m)
            c += len(text)
            if c > limit_chars:
                break
            s.append({"role": m.get("role", "user"), "content": text})
        return list(reversed(s))

    short_messages = shortlist_msgs(messages)
    short_messages_json = json.dumps(short_messages, ensure_ascii=False)

    # Use .format and escape any literal braces by doubling them.
    prompt_template = """
You are a senior cybersecurity analyst. Produce a compact security assessment report for a single session.

Context:
- Session timestamp: {timestamp}
- Recon summary (raw): {recon}
- Attack results (raw): {attacks}
- Chat & tool transcript (most recent messages): {short_messages}

Task:
1) Produce a JSON object with the following keys:
  - title (string)
  - generated_at (ISO timestamp)
  - executive_summary (string, 2-4 short paragraphs)
  - timeline (list of {{ "time": "<ISO>", "actor": "red|blue|system", "action": "short string" }})
  - findings (list of objects with fields: id (short unique), title, description, evidence (short), severity (one of: Critical, High, Medium, Low, Info), confidence (0-100))
  - risk_matrix (list of {{ "severity": "...", "count": n }})
  - recommended_actions (list of {{ "finding_id": "...", "action": "suggested remediation", "priority":"P1/P2/P3" }})
  - raw_appendix (string: short log excerpt or note where to find full logs)

2) Return *only* valid JSON in your response (no extra commentary). Keep text concise but informative.
3) If a value is unknown, place a sensible placeholder and explain uncertainties in the executive_summary.

Important: be conservative with severity (prefer higher severity when unsure).
"""

    prompt = prompt_template.format(
        timestamp=timestamp,
        recon=json.dumps(recon, ensure_ascii=False) if recon else "None",
        attacks=json.dumps(attacks, ensure_ascii=False) if attacks else "None",
        short_messages=short_messages_json,
    )

    return prompt


def ask_llm_for_structured_report(prompt: str) -> Dict[str, Any]:
    human = HumanMessage(content=prompt)
    llm_text = None
    try:
        resp = llm.generate([human])
        if hasattr(resp, "generations"):
            gen = resp.generations[0][0]
            llm_text = gen.text if hasattr(gen, "text") else str(gen)
        elif isinstance(resp, dict) and "output_text" in resp:
            llm_text = resp["output_text"]
    except Exception:
        try:
            out = llm.predict(human.content)
            llm_text = out
        except Exception:
            try:
                out = llm(human)
                if isinstance(out, str):
                    llm_text = out
                elif hasattr(out, "content"):
                    llm_text = out.content
            except Exception as e:
                raise RuntimeError("LLM invocation failed. Adapt ask_llm_for_structured_report to your LLM client.") from e

    if not llm_text:
        raise RuntimeError("LLM returned no text.")

    json_text = extract_json_block(llm_text)
    if not json_text:
        json_text = llm_text

    try:
        parsed = json.loads(json_text)
    except Exception as e:
        try:
            parsed = json.loads(json_text.replace("'", '"'))
        except Exception:
            raise RuntimeError(f"Failed to parse JSON from model output. Raw output:\n{llm_text}") from e

    return parsed


def extract_json_block(text: str) -> str:
    """Return the first {...} json substring found, else empty string."""
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]
    return ""


# -------------------------
# PDF Rendering
# -------------------------
def render_pdf_from_report(report: Dict[str, Any], output_path: str):
    doc = SimpleDocTemplate(output_path, pagesize=A4, topMargin=20 * mm, bottomMargin=20 * mm, leftMargin=16 * mm, rightMargin=16 * mm)
    styles = getSampleStyleSheet()
    normal = styles["Normal"]
    small = ParagraphStyle("small", parent=normal, fontSize=9, leading=11)

    story = []

    title_text = report.get("title", "Security Assessment Report")
    story.append(Paragraph(f"<b>{title_text}</b>", styles["Title"]))
    story.append(Spacer(1, 6))

    gen_at = report.get("generated_at", datetime.now(timezone.utc).isoformat())
    story.append(Paragraph(f"<i>Generated at: {gen_at}</i>", small))
    story.append(Spacer(1, 12))

    story.append(Paragraph("Executive Summary", styles["Heading2"]))
    executive = report.get("executive_summary", "")
    story.append(Paragraph(executive.replace("\n", "<br/>"), normal))
    story.append(Spacer(1, 12))

    timeline = report.get("timeline", [])
    if timeline:
        story.append(Paragraph("Timeline", styles["Heading2"]))
        table_data = [["Time", "Actor", "Action"]]
        for ev in timeline:
            table_data.append([ev.get("time", ""), ev.get("actor", ""), ev.get("action", "")])
        t = Table(table_data, hAlign="LEFT", colWidths=[90 * mm, 25 * mm, None])
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey), ("GRID", (0, 0), (-1, -1), 0.4, colors.grey)]))
        story.append(t)
        story.append(Spacer(1, 12))

    findings: List[Dict[str, Any]] = report.get("findings", [])
    if findings:
        story.append(Paragraph("Findings", styles["Heading2"]))
        for f in findings:
            fid = f.get("id", "")
            title = f.get("title", "(no title)")
            sev = f.get("severity", "Info")
            conf = f.get("confidence", "")
            story.append(Paragraph(f"<b>{fid} - {title}</b>  <i>Severity: {sev} Confidence: {conf}</i>", normal))
            story.append(Paragraph(f.get("description", ""), small))
            evidence = f.get("evidence", "")
            if evidence:
                story.append(Paragraph(f"<b>Evidence:</b> {evidence}", small))
            story.append(Spacer(1, 8))
        story.append(Spacer(1, 12))

    risk_matrix = report.get("risk_matrix", [])
    if risk_matrix:
        story.append(Paragraph("Risk Matrix", styles["Heading2"]))
        table_data = [["Severity", "Count"]]
        for r in risk_matrix:
            table_data.append([r.get("severity", ""), str(r.get("count", ""))])
        t2 = Table(table_data, hAlign="LEFT", colWidths=[60 * mm, 20 * mm])
        t2.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey), ("GRID", (0, 0), (-1, -1), 0.4, colors.grey)]))
        story.append(t2)
        story.append(Spacer(1, 12))

    recs = report.get("recommended_actions", [])
    if recs:
        story.append(Paragraph("Recommended Actions", styles["Heading2"]))
        for r in recs:
            fid = r.get("finding_id", "")
            action = r.get("action", "")
            priority = r.get("priority", "P3")
            story.append(Paragraph(f"<b>For {fid} ({priority})</b>: {action}", normal))
            story.append(Spacer(1, 6))
        story.append(Spacer(1, 12))

    raw = report.get("raw_appendix", "")
    if raw:
        story.append(PageBreak())
        story.append(Paragraph("Appendix — Raw Logs / Notes", styles["Heading2"]))
        story.append(Paragraph(raw.replace("\n", "<br/>"), small))

    doc.build(story)


# -------------------------
# Public: generate report by session document
# -------------------------
def generate_report_for_session(session_doc_name: str = DOCUMENT_NAME, output_dir: str = "/tmp") -> str:
    session = fetch_session(session_doc_name)
    prompt = build_prompt_from_session(session)
    parsed = ask_llm_for_structured_report(prompt)

    parsed.setdefault("title", f"Security Assessment Report — session {session_doc_name}")
    parsed.setdefault("generated_at", datetime.now(timezone.utc).isoformat())
    output_path = os.path.join(output_dir, f"report_{session_doc_name}_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}.pdf")

    render_pdf_from_report(parsed, output_path)
    return output_path


if __name__ == "__main__":
    out = generate_report_for_session(DOCUMENT_NAME, output_dir=".")
    print("Report generated at:", out)