"""
CV ↔ Job Offer Matcher
======================
Supports both Mistral and Claude APIs — switch with the AI_PROVIDER setting.

Supports:
  - Single CV scoring against an offer
  - Batch ranking of multiple CVs against one offer
  - Job offer input as text or extracted from PDF/DOCX
"""

import json
import os
import re
from dataclasses import dataclass, field

from parser_v2 import ParsedCV, Section, ExperienceBlock


# ---------------------------------------------------------------------------
# ⚙️  CONFIGURATION — switch provider here
# ---------------------------------------------------------------------------

# Options: "mistral" or "claude"
AI_PROVIDER = "mistral"

MISTRAL_MODEL = "mistral-medium-latest"
CLAUDE_MODEL  = "claude-sonnet-4-20250514"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class MatchResult:
    candidate_name: str = ""
    overall_score: int = 0
    summary: str = ""
    matched_skills: list[str] = field(default_factory=list)
    missing_skills: list[str] = field(default_factory=list)
    matched_experience: list[str] = field(default_factory=list)
    experience_gaps: list[str] = field(default_factory=list)
    strengths: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    tailoring_suggestions: list[str] = field(default_factory=list)
    detail_scores: dict = field(default_factory=dict)


@dataclass
class RankingResult:
    offer_title: str = ""
    ranked_candidates: list[MatchResult] = field(default_factory=list)


# ---------------------------------------------------------------------------
# API key helpers
# ---------------------------------------------------------------------------

def _get_mistral_key() -> str:
    try:
        import streamlit as st
        return st.secrets["MISTRAL_API_KEY"]
    except Exception:
        pass
    return os.environ.get("MISTRAL_API_KEY", "")


def _get_claude_key() -> str:
    try:
        import streamlit as st
        return st.secrets["ANTHROPIC_API_KEY"]
    except Exception:
        pass
    return os.environ.get("ANTHROPIC_API_KEY", "")


# ---------------------------------------------------------------------------
# CV → text
# ---------------------------------------------------------------------------

def _cv_to_text(cv: ParsedCV) -> str:
    parts = []
    p = cv.profile
    parts.append(f"NAME: {p.name}")
    if p.title:            parts.append(f"TITLE: {p.title}")
    if p.language:         parts.append(f"LANGUAGES: {p.language}")
    if p.years_experience: parts.append(f"EXPERIENCE: {p.years_experience}")
    parts.append("")

    for section in cv.sections:
        parts.append(f"=== {section.header.upper()} ===")
        if section.table_rows:
            for row in section.table_rows:
                parts.append(f"  {row.left}: {row.right}" if row.right else f"  {row.left}")
        if section.bullet_items:
            for item in section.bullet_items:
                parts.append(f"  • {item}")
        if section.experience_blocks:
            for exp in section.experience_blocks:
                parts.append(f"  --- {exp.title_line} ---")
                if exp.poste:
                    parts.append(f"  Poste: {exp.poste}")
                for sub_header, items in exp.sub_sections:
                    if sub_header:
                        parts.append(f"  {sub_header}")
                    for item in items:
                        parts.append(f"    • {item}")
        parts.append("")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

MATCH_SYSTEM_PROMPT = """You are an expert HR/recruitment analyst. Your job is to analyze the compatibility between a candidate's CV and a job offer.

You must respond ONLY with a valid JSON object (no markdown, no backticks, no preamble).

The JSON must have this exact structure:
{
  "overall_score": <integer 0-100>,
  "summary": "<3-4 sentence overview: overall fit, strongest asset, main gap, and one concrete recommendation>",
  "detail_scores": {
    "skills": <integer 0-100>,
    "experience": <integer 0-100>,
    "domain": <integer 0-100>,
    "education": <integer 0-100>,
    "languages": <integer 0-100>
  },
  "matched_skills": ["<skill1>", "<skill2>", ...],
  "missing_skills": ["<skill1>", "<skill2>", ...],
  "matched_experience": ["<relevant experience point 1>", ...],
  "experience_gaps": ["<gap1>", ...],
  "strengths": ["<strength1>", "<strength2>", ...],
  "risks": ["<risk1>", "<risk2>", ...],
  "tailoring_suggestions": ["<suggestion1>", "<suggestion2>", ...]
}

━━━ SCORING RULES ━━━

overall_score:
- 85-100: Excellent — candidate meets nearly all requirements including experience threshold
- 70-84: Good — meets most key requirements, minor gaps only
- 50-69: Partial — relevant background but significant gaps (e.g. wrong domain, missing frameworks)
- 30-49: Weak — some transferable skills but major requirements unmet
- 0-29: Poor — profile does not align with the role

detail_scores must be consistent with overall_score:
- If experience is below the required minimum, experience score must be below 60
- If key required frameworks are missing, skills score must reflect that gap
- overall_score must never be higher than the average of detail_scores by more than 5 points

━━━ STRICT CONTENT RULES ━━━

matched_skills — ONLY include a skill if:
  1. It is explicitly written in the CV text (word-for-word or near-exact match)
  2. AND it is relevant to the job offer
  → Never infer or assume a skill from context. If Python is listed but FastAPI is not, do NOT list FastAPI as matched.

missing_skills — ONLY include a skill if:
  1. It is explicitly required or strongly implied by the job offer
  2. AND it is NOT present in the CV
  → Stick to what the offer actually asks for. Do not invent requirements not mentioned in the offer.
  → Keep this list focused: maximum 8-10 items, prioritized by importance to the role.

NEVER list the same skill (or near-identical variants) in both matched_skills and missing_skills.
  → Wrong: matched has "CI/CD", missing has "CI/CD pipelines" — pick one column only.
  → Rule: if the skill is present in the CV in any form, put it in matched_skills. If it is absent entirely, put it in missing_skills.

matched_experience — list actual job experiences, projects, or missions from the CV that are relevant to the offer.
  → Be specific: mention company names, project names, or technologies used.
  → Do not list generic statements like "experience in Python" — that belongs in matched_skills.

experience_gaps — focus only on gaps that matter for THIS specific role.
  → Do not repeat points already covered in missing_skills or risks.
  → Maximum 4-5 items.

strengths — highlight what genuinely differentiates this candidate.
  → Be specific and reference actual content from the CV.
  → Maximum 5-6 items.

risks — be honest but fair. Only flag real risks relevant to this specific role.
  → Do not repeat what is already in missing_skills or experience_gaps.
  → Maximum 4-5 items.

tailoring_suggestions — concrete, actionable advice to improve the CV for this specific offer.
  → Each suggestion must be specific and implementable.
  → Maximum 6 items.

━━━ LANGUAGE RULE ━━━
Write everything in the same language as the job offer (French if French, English if English).
"""


# ---------------------------------------------------------------------------
# API calls
# ---------------------------------------------------------------------------

def _call_mistral(prompt: str) -> str:
    from mistralai.client import Mistral
    api_key = _get_mistral_key()
    if not api_key:
        raise ValueError("Clé MISTRAL_API_KEY introuvable.")
    client = Mistral(api_key=api_key)
    response = client.chat.complete(
        model=MISTRAL_MODEL,
        messages=[
            {"role": "system", "content": MATCH_SYSTEM_PROMPT},
            {"role": "user",   "content": prompt},
        ],
        response_format={"type": "json_object"},
        temperature=0.1,
    )
    return response.choices[0].message.content


def _call_claude(prompt: str) -> str:
    from anthropic import Anthropic
    api_key = _get_claude_key()
    if not api_key:
        raise ValueError("Clé ANTHROPIC_API_KEY introuvable.")
    client = Anthropic(api_key=api_key)
    message = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=4096,
        system=MATCH_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text


def _call_ai(prompt: str, provider: str = None) -> str:
    """Route to the correct AI provider."""
    p = (provider or AI_PROVIDER).lower()
    if p == "mistral":
        return _call_mistral(prompt)
    elif p == "claude":
        return _call_claude(prompt)
    else:
        raise ValueError(f"Fournisseur IA inconnu: '{p}'. Utilisez 'mistral' ou 'claude'.")


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------

def _parse_match_response(raw: str, candidate_name: str = "") -> MatchResult:
    cleaned = raw.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", cleaned)
        if match:
            data = json.loads(match.group())
        else:
            return MatchResult(
                candidate_name=candidate_name,
                overall_score=0,
                summary=f"Erreur : impossible d'analyser la réponse. Brut : {raw[:200]}",
            )

    # ── Post-processing: remove duplicates between matched and missing ──
    matched = data.get("matched_skills", [])
    missing = data.get("missing_skills", [])

    # Normalize for comparison (lowercase, strip)
    matched_norm = {s.lower().strip() for s in matched}

    # Remove from missing anything that's already in matched (exact or substring match)
    def _is_duplicate(skill: str, matched_set: set) -> bool:
        s = skill.lower().strip()
        return s in matched_set or any(s in m or m in s for m in matched_set)

    missing_clean = [s for s in missing if not _is_duplicate(s, matched_norm)]

    return MatchResult(
        candidate_name=candidate_name or data.get("candidate_name", "Inconnu"),
        overall_score=data.get("overall_score", 0),
        summary=data.get("summary", ""),
        matched_skills=matched,
        missing_skills=missing_clean,
        matched_experience=data.get("matched_experience", []),
        experience_gaps=data.get("experience_gaps", []),
        strengths=data.get("strengths", []),
        risks=data.get("risks", []),
        tailoring_suggestions=data.get("tailoring_suggestions", []),
        detail_scores=data.get("detail_scores", {}),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def match_cv(
    cv: ParsedCV,
    offer_text: str,
    api_key: str = "",
    model: str = "",
    provider: str = None,
) -> MatchResult:
    """Score a single CV against a job offer."""
    cv_text = _cv_to_text(cv)
    prompt = f"""Analyze the compatibility between this CV and job offer.

--- CV ---
{cv_text}

--- JOB OFFER ---
{offer_text}

Provide your analysis as a JSON object following the specified format."""

    raw_response = _call_ai(prompt, provider=provider)
    return _parse_match_response(raw_response, candidate_name=cv.profile.name)


def rank_cvs(
    cvs: list[tuple[str, ParsedCV]],
    offer_text: str,
    api_key: str = "",
    model: str = "",
    provider: str = None,
    progress_callback=None,
) -> RankingResult:
    """Rank multiple CVs against one job offer."""
    results = []
    total = len(cvs)

    for i, (filename, cv) in enumerate(cvs):
        if progress_callback:
            progress_callback(i, total)
        result = match_cv(cv, offer_text, provider=provider)
        if not result.candidate_name or result.candidate_name == "Inconnu":
            result.candidate_name = cv.profile.name or filename
        results.append(result)

    results.sort(key=lambda r: r.overall_score, reverse=True)
    offer_title = offer_text.strip().split("\n")[0][:100]

    if progress_callback:
        progress_callback(total, total)

    return RankingResult(offer_title=offer_title, ranked_candidates=results)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Usage: python matcher.py <cv_path> <offer_path_or_text> [mistral|claude]")
        sys.exit(1)

    cv_path     = sys.argv[1]
    offer_input = sys.argv[2]
    provider    = sys.argv[3] if len(sys.argv) > 3 else AI_PROVIDER

    ext = os.path.splitext(cv_path)[1].lower()
    if ext == ".docx":
        import zipfile
        try:
            with zipfile.ZipFile(cv_path) as z:
                styles_xml = z.read("word/styles.xml").decode("utf-8") if "word/styles.xml" in z.namelist() else ""
                is_intm = "Titre R" in styles_xml and "Profil : Exp" in styles_xml
        except Exception:
            is_intm = False
        if is_intm:
            from parser_v2 import parse_docx
            cv = parse_docx(cv_path)
        else:
            from parser import parse_file_with_mistral
            cv = parse_file_with_mistral(cv_path)
    else:
        from parser import parse_file_with_mistral
        cv = parse_file_with_mistral(cv_path)

    if os.path.exists(offer_input):
        from extractor import extract_text
        offer_text = extract_text(offer_input)
    else:
        offer_text = offer_input

    print(f"📄 CV : {cv.profile.name}")
    print(f"🤖 Fournisseur : {provider.upper()}")
    print(f"🔍 Analyse en cours...\n")

    result = match_cv(cv, offer_text, provider=provider)

    print(f"{'='*60}")
    print(f"  RÉSULTAT : {result.candidate_name}")
    print(f"  SCORE GLOBAL : {result.overall_score}/100")
    print(f"{'='*60}")
    print(f"\n  {result.summary}\n")

    if result.detail_scores:
        print("  Scores détaillés :")
        for k, v in result.detail_scores.items():
            bar = "█" * (v // 5) + "░" * (20 - v // 5)
            print(f"    {k:12s} {bar} {v}/100")

    if result.matched_skills:
        print(f"\n  ✅ Compétences correspondantes : {', '.join(result.matched_skills)}")
    if result.missing_skills:
        print(f"  ❌ Compétences manquantes : {', '.join(result.missing_skills)}")
    if result.strengths:
        print(f"\n  💪 Points forts :")
        for s in result.strengths: print(f"    • {s}")
    if result.risks:
        print(f"\n  ⚠️  Risques :")
        for r in result.risks: print(f"    • {r}")
    if result.tailoring_suggestions:
        print(f"\n  💡 Suggestions :")
        for s in result.tailoring_suggestions: print(f"    • {s}")

    print(f"\n{'='*60}")