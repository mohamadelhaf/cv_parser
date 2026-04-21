import json
import os
import re
from dataclasses import dataclass, field

from parser_v2 import ParsedCV, Section, ExperienceBlock


# Options: "mistral" or "claude"
AI_PROVIDER = "mistral"

MISTRAL_MODEL = "mistral-medium-2508"
CLAUDE_MODEL  = "claude-sonnet-4-20250514"


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


EXTRACT_SYSTEM_PROMPT = """You are an expert HR analyst. You receive a job offer / job description.

Your ONLY job is to extract the EXPLICIT requirements from the offer. Do NOT invent, infer, or add requirements that are not stated or strongly implied by the text.

Return ONLY valid JSON — no explanation, no markdown, no code fences.

JSON structure:
{
  "job_title": "<the role title>",
  "required_skills": ["<skill1>", "<skill2>", ...],
  "required_experience": {
    "years": "<minimum years if mentioned, else empty string>",
    "domains": ["<domain1>", "<domain2>", ...],
    "specific_tasks": ["<task1>", "<task2>", ...]
  },
  "required_education": ["<degree or certification if mentioned>"],
  "required_languages": ["<language requirements if mentioned>"],
  "tools_and_platforms": ["<specific tool/platform/framework mentioned>"],
  "soft_skills": ["<soft skill if explicitly mentioned>"],
  "nice_to_have": ["<skills mentioned as optional/preferred/bonus>"]
}

━━━ STRICT RULES ━━━

- required_skills: ONLY list technologies, frameworks, methodologies, and technical skills that the offer explicitly names or clearly implies. Examples: "Python", "LangChain", "RAG", "Azure OpenAI".
  → Do NOT add generic skills like "teamwork" or "communication" unless the offer explicitly states them.
  → Do NOT split compound requirements: if the offer says "MCP, frameworks Semantic Kernel / LangChain", list "MCP", "Semantic Kernel", "LangChain" as separate items.

- tools_and_platforms: specific products, platforms, or environments mentioned (e.g. "Copilot Studio", "M365/Graph", "Azure AI Search").

- nice_to_have: skills or qualifications that are mentioned as preferred, bonus, or "nice to have" — NOT as hard requirements.

- If a category has no items, use an empty list [].

━━━ LANGUAGE RULE ━━━
Write everything in the same language as the job offer.
"""


MATCH_SYSTEM_PROMPT = """You are an expert HR/recruitment analyst. You receive:
1. A candidate's CV
2. A STRUCTURED LIST OF REQUIREMENTS extracted from a job offer

Your job is to evaluate the CV STRICTLY against these requirements — nothing else.

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

━━━ CRITICAL MATCHING RULES ━━━

matched_skills — ONLY include a skill if ALL of these are true:
  1. The skill appears in the REQUIREMENTS list (required_skills OR tools_and_platforms)
  2. AND the skill is explicitly present in the CV (word-for-word or near-exact match)
  → NEVER include skills that are only in the CV but not in the requirements.
  → NEVER include skills that are only in the requirements but not in the CV — those go in missing_skills.
  → NEVER infer skills. If the CV says "Python" but the requirement is "FastAPI", do NOT list FastAPI as matched.

missing_skills — ONLY include a skill if ALL of these are true:
  1. The skill appears in the REQUIREMENTS list (required_skills OR tools_and_platforms)
  2. AND the skill is NOT present in the CV in any form
  → Every skill in the requirements list must appear in EITHER matched_skills OR missing_skills — none should be dropped.

CROSS-CHECK: matched_skills + missing_skills should together cover ALL items from required_skills and tools_and_platforms. If a required skill is in neither list, you made an error.

NEVER list the same skill in both matched_skills and missing_skills.

matched_experience — list SPECIFIC job experiences, projects, or missions from the CV that are relevant to the requirements.
  → Be specific: mention company names, project names, or technologies used.
  → Do NOT list generic statements like "experience in Python" — that belongs in matched_skills.
  → Do NOT fabricate experience that is not written in the CV.

experience_gaps — gaps between what the requirements ask and what the CV shows.
  → Do not repeat points already in missing_skills.
  → Maximum 4-5 items.

strengths — what genuinely differentiates this candidate FOR THIS SPECIFIC ROLE.
  → Be specific, reference actual CV content.
  → Do NOT list strengths unrelated to the requirements.
  → Maximum 5-6 items.

risks — honest, fair assessment of real risks for this specific role.
  → Do not repeat missing_skills or experience_gaps.
  → Maximum 4-5 items.

tailoring_suggestions — concrete, actionable advice to improve the CV for this specific offer.
  → Each suggestion must be specific and implementable.
  → Maximum 6 items.

━━━ LANGUAGE RULE ━━━
Write everything in the same language as the requirements (French if French, English if English).
"""


def _call_mistral(prompt: str, system_prompt: str) -> str:
    from mistralai.client import Mistral
    api_key = _get_mistral_key()
    if not api_key:
        raise ValueError("Clé MISTRAL_API_KEY introuvable.")
    client = Mistral(api_key=api_key, timeout_ms=1200000)
    response = client.chat.complete(
        model=MISTRAL_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": prompt},
        ],
        response_format={"type": "json_object"},
        temperature=0.1,
    )
    return response.choices[0].message.content


def _call_claude(prompt: str, system_prompt: str) -> str:
    from anthropic import Anthropic
    api_key = _get_claude_key()
    if not api_key:
        raise ValueError("Clé ANTHROPIC_API_KEY introuvable.")
    client = Anthropic(api_key=api_key)
    message = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=4096,
        system=system_prompt,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text


def _call_ai(prompt: str, system_prompt: str, provider: str = None) -> str:
    p = (provider or AI_PROVIDER).lower()
    if p == "mistral":
        return _call_mistral(prompt, system_prompt)
    elif p == "claude":
        return _call_claude(prompt, system_prompt)
    else:
        raise ValueError(f"Fournisseur IA inconnu: '{p}'. Utilisez 'mistral' ou 'claude'.")


def _parse_json_response(raw: str) -> dict:
    cleaned = raw.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", cleaned)
        if match:
            return json.loads(match.group())
        raise ValueError(f"Impossible de parser le JSON: {raw[:300]}")


def extract_offer_requirements(offer_text: str, provider: str = None) -> dict:
    """Step 1: Extract structured requirements from a job offer."""
    prompt = f"""Extract the requirements from this job offer.

--- JOB OFFER ---
{offer_text}

Return ONLY the JSON object with the structured requirements."""

    raw = _call_ai(prompt, system_prompt=EXTRACT_SYSTEM_PROMPT, provider=provider)
    return _parse_json_response(raw)


def _requirements_to_text(reqs: dict) -> str:
    parts = []

    title = reqs.get("job_title", "")
    if title:
        parts.append(f"JOB TITLE: {title}")

    skills = reqs.get("required_skills", [])
    if skills:
        parts.append(f"REQUIRED SKILLS: {', '.join(skills)}")

    tools = reqs.get("tools_and_platforms", [])
    if tools:
        parts.append(f"REQUIRED TOOLS & PLATFORMS: {', '.join(tools)}")

    exp = reqs.get("required_experience", {})
    if isinstance(exp, dict):
        years = exp.get("years", "")
        if years:
            parts.append(f"REQUIRED EXPERIENCE: {years}")
        domains = exp.get("domains", [])
        if domains:
            parts.append(f"REQUIRED DOMAINS: {', '.join(domains)}")
        tasks = exp.get("specific_tasks", [])
        if tasks:
            parts.append(f"REQUIRED TASKS/RESPONSIBILITIES:")
            for t in tasks:
                parts.append(f"  • {t}")

    edu = reqs.get("required_education", [])
    if edu:
        parts.append(f"REQUIRED EDUCATION: {', '.join(edu)}")

    langs = reqs.get("required_languages", [])
    if langs:
        parts.append(f"REQUIRED LANGUAGES: {', '.join(langs)}")

    soft = reqs.get("soft_skills", [])
    if soft:
        parts.append(f"REQUIRED SOFT SKILLS: {', '.join(soft)}")

    nice = reqs.get("nice_to_have", [])
    if nice:
        parts.append(f"NICE TO HAVE: {', '.join(nice)}")

    return "\n".join(parts)


def _parse_match_response(raw: str, candidate_name: str = "") -> MatchResult:
    try:
        data = _parse_json_response(raw)
    except ValueError:
        return MatchResult(
            candidate_name=candidate_name,
            overall_score=0,
            summary=f"Erreur : impossible d'analyser la réponse. Brut : {raw[:200]}",
        )

    # ── Post-processing: remove duplicates between matched and missing ──
    matched = data.get("matched_skills", [])
    missing = data.get("missing_skills", [])

    matched_norm = {s.lower().strip() for s in matched}

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


def match_cv(
    cv: ParsedCV,
    offer_text: str,
    api_key: str = "",
    model: str = "",
    provider: str = None,
    offer_requirements: dict = None,
) -> MatchResult:
    """Score a single CV against a job offer (two-step).

    If offer_requirements is provided, skip Step 1 (useful for batch ranking).
    """
    # Step 1: Extract requirements (or reuse if already extracted)
    if offer_requirements is None:
        offer_requirements = extract_offer_requirements(offer_text, provider=provider)

    # Step 2: Match CV against requirements
    cv_text = _cv_to_text(cv)
    reqs_text = _requirements_to_text(offer_requirements)

    prompt = f"""Evaluate this CV against the following job requirements.

--- EXTRACTED JOB REQUIREMENTS ---
{reqs_text}

--- CANDIDATE CV ---
{cv_text}

Match the CV STRICTLY against the requirements above. Only consider skills and experience that the requirements actually ask for. Provide your analysis as a JSON object."""

    raw_response = _call_ai(prompt, system_prompt=MATCH_SYSTEM_PROMPT, provider=provider)
    return _parse_match_response(raw_response, candidate_name=cv.profile.name)


def rank_cvs(
    cvs: list[tuple[str, ParsedCV]],
    offer_text: str,
    api_key: str = "",
    model: str = "",
    provider: str = None,
    progress_callback=None,
) -> RankingResult:
    """Rank multiple CVs against one job offer.

    Step 1 runs once; Step 2 runs per CV.
    """
    # Step 1: Extract requirements ONCE for all CVs
    offer_requirements = extract_offer_requirements(offer_text, provider=provider)

    results = []
    total = len(cvs)

    for i, (filename, cv) in enumerate(cvs):
        if progress_callback:
            progress_callback(i, total)
        # Step 2: Match each CV against the same requirements
        result = match_cv(
            cv, offer_text,
            provider=provider,
            offer_requirements=offer_requirements,
        )
        if not result.candidate_name or result.candidate_name == "Inconnu":
            result.candidate_name = cv.profile.name or filename
        results.append(result)

    results.sort(key=lambda r: r.overall_score, reverse=True)
    offer_title = offer_text.strip().split("\n")[0][:100]

    if progress_callback:
        progress_callback(total, total)

    return RankingResult(offer_title=offer_title, ranked_candidates=results)


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

    # Step 1
    print(f"\n🔍 Étape 1 : Extraction des exigences de l'offre...")
    reqs = extract_offer_requirements(offer_text, provider=provider)
    print(f"   ✅ {len(reqs.get('required_skills', []))} compétences requises extraites")
    print(f"   ✅ {len(reqs.get('tools_and_platforms', []))} outils/plateformes extraits")
    if reqs.get("required_skills"):
        print(f"   📋 Compétences : {', '.join(reqs['required_skills'])}")
    if reqs.get("tools_and_platforms"):
        print(f"   🔧 Outils : {', '.join(reqs['tools_and_platforms'])}")

    # Step 2
    print(f"\n🔍 Étape 2 : Matching CV ↔ Exigences...")
    result = match_cv(cv, offer_text, provider=provider, offer_requirements=reqs)

    print(f"\n{'='*60}")
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