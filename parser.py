import json
import os
import re
import sys
import hashlib
from pathlib import Path

# ── Import the exact data structures generator.py uses ──
from parser_v2 import ParsedCV, ProfileData, Section, ExperienceBlock, TableRow


MISTRAL_MODEL = "mistral-small-latest"
CACHE_DIR     = Path(".cache/mistral")


def _get_api_key() -> str:
    # Streamlit Cloud: secrets are injected via st.secrets
    try:
        import streamlit as st
        return st.secrets["MISTRAL_API_KEY"]
    except Exception:
        pass
    # Local: read from environment variable
    return os.environ.get("MISTRAL_API_KEY", "")


def _cache_key(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest()

def _load_cache(key: str):
    f = CACHE_DIR / f"{key}.json"
    if f.exists():
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None

def _save_cache(key: str, data: dict):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    (CACHE_DIR / f"{key}.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


SYSTEM_PROMPT = """You are an expert CV parser. You receive raw text extracted from a PDF or Word CV.
The text may have artifacts: glued words, broken lines, repeated page headers, garbled characters.

Your tasks:
1. Clean the text (fix glued words, remove repeated headers/footers, fix broken lines)
2. Parse into structured JSON

Return ONLY valid JSON — no explanation, no markdown, no code fences.

JSON structure:
{
  "name": "Full name",
  "title": "Professional title/headline",
  "language": "Français or English",
  "years_experience": "e.g. 5 ans or 10+ years",
  "profile": "Summary/profile paragraph",
  "savoir_faire": ["bullet point 1", "bullet point 2"],
  "skills": [
    {"category": "Category name", "details": "comma-separated skills"}
  ],
  "languages": [
    {"language": "French", "level": "Natif"}
  ],
  "education": [
    {"degree": "Degree or Certification name", "institution": "School or Issuer", "year": "2018", "type": "degree or certification"}
  ],
  "experiences": [
    {
      "company": "Company name",
      "role": "Job title",
      "dates": "Start – End",
      "context": "Mission context paragraph (optional)",
      "tasks": ["task 1", "task 2"],
      "tech_stack": ["Python", "SQL"]
    }
  ]
}

Rules:
- name: person's name only, not their title
- savoir_faire: key strengths as short bullet points (3-6 items)
- skills: group by category (Langages, Outils, Méthodes, etc.)
- experiences: most recent first, include ALL experiences found
- dates: keep original format, e.g. "Mars 2022 – Février 2026"
- missing fields: use "" or []
- tasks: include ALL bullet points found for each experience
- education: include EVERYTHING in the formation/education section — university degrees, technical diplomas, bootcamps, AND professional certifications (e.g. ISTQB, COBOL certification, AWS, PMP, etc.). Never drop certifications.
- if a section is called "Formation et Certifications" or "Certifications" or similar, include ALL items in education
"""


def _call_mistral(raw_text: str) -> dict:
    from mistralai.client import Mistral

    # Get API key at call time — works on both local and Streamlit Cloud
    api_key = _get_api_key()
    if not api_key:
        raise ValueError("Clé API Mistral introuvable. Vérifiez MISTRAL_API_KEY dans les secrets Streamlit ou les variables d'environnement.")

    key = _cache_key(raw_text)
    cached = _load_cache(key)
    if cached:
        print("   ✅ Chargé depuis le cache (gratuit)")
        return cached

    print(f"   🤖 Appel Mistral ({MISTRAL_MODEL})...")
    client = Mistral(api_key=api_key)

    max_chars = 14000
    if len(raw_text) > max_chars:
        print(f"   ⚠️  Texte tronqué à {max_chars} caractères")
        raw_text = raw_text[:max_chars]

    response = client.chat.complete(
        model=MISTRAL_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": f"Parse this CV:\n\n{raw_text}"}
        ],
        response_format={"type": "json_object"},
        temperature=0.1,
    )

    content = response.choices[0].message.content.strip()

    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\n?", "", content)
        content = re.sub(r"\n?```$", "", content)

    result = json.loads(content)
    _save_cache(key, result)
    print("   ✅ Analysé et mis en cache")
    return result


def _compute_duration(dates: str) -> str:
    MONTHS = {
        "jan": 1, "janv": 1, "janvier": 1,
        "fev": 2, "fév": 2, "févr": 2, "fevrier": 2, "février": 2,
        "mar": 3, "mars": 3,
        "avr": 4, "avril": 4,
        "mai": 5, "juin": 6,
        "jul": 7, "juil": 7, "juillet": 7,
        "aou": 8, "aoû": 8, "aout": 8, "août": 8,
        "sep": 9, "sept": 9, "septembre": 9,
        "oct": 10, "octobre": 10,
        "nov": 11, "novembre": 11,
        "dec": 12, "déc": 12, "décembre": 12,
    }

    if not dates or not dates.strip():
        return ""

    cleaned = dates.strip()

    if re.match(r"(?i)^(durée|depuis)", cleaned):
        return cleaned

    if re.search(r"(?i)(aujourd|présent|present|en cours|actuel)", cleaned):
        start_part = re.split(r"\s*[-–—]\s*", cleaned)[0].strip()
        return f"Depuis {start_part}"

    parts = re.split(r"\s*[-–—]\s*", cleaned)
    if len(parts) == 2:
        def parse_piece(p):
            p = p.strip()
            m = re.match(r"^(\d{2})/(\d{4})$", p)
            if m:
                return int(m.group(2)), int(m.group(1))
            m = re.match(r"(?i)^([A-Za-zÀ-ÿ]+)\.?\s+(\d{4})$", p)
            if m:
                mo = MONTHS.get(m.group(1).lower().rstrip("."))
                return (int(m.group(2)), mo) if mo else None
            m = re.match(r"^(\d{4})$", p)
            if m:
                return int(m.group(1)), 1
            return None

        start = parse_piece(parts[0])
        end   = parse_piece(parts[1])
        if start and end:
            months = (end[0] - start[0]) * 12 + (end[1] - start[1])
            if months <= 0:
                return f"Durée {cleaned}"
            if months < 12:
                return f"Durée {months} mois"
            y, r = divmod(months, 12)
            if r == 0:
                return f"Durée {y} an" if y == 1 else f"Durée {y} ans"
            return f"Durée {y} an {r} mois" if y == 1 else f"Durée {y} ans {r} mois"

    return f"Durée {cleaned}"


def _json_to_parsed_cv(data: dict) -> ParsedCV:
    cv = ParsedCV()

    # ── Profile ──
    name    = data.get("name", "")
    title   = data.get("title", "")
    lang    = data.get("language", "Français")
    exp_yrs = data.get("years_experience", "")

    if exp_yrs and "expérience" not in exp_yrs.lower():
        exp_yrs_display = f"{exp_yrs} d'expérience professionnelle"
    else:
        exp_yrs_display = exp_yrs

    cv.profile = ProfileData(
        lines=[name, title, lang, exp_yrs_display],
        name=name,
        title=title,
        language=lang,
        years_experience=exp_yrs_display,
    )

    # ── Formation + Certifications ──
    education = data.get("education", [])
    if education:
        section = Section(header="Formation", content_type="table")
        for e in education:
            if isinstance(e, dict):
                year  = e.get("year", "")
                degree = e.get("degree", "")
                inst  = e.get("institution", "")
                etype = e.get("type", "")
                left  = f"{year} : {degree}" if year else degree
                if etype and "certif" in etype.lower() and inst:
                    right = f"{inst} (Certification)"
                else:
                    right = inst
                section.table_rows.append(TableRow(left=left, right=right))
            elif isinstance(e, str):
                section.table_rows.append(TableRow(left=e, right=""))
        cv.sections.append(section)

    # ── Savoir Faire ──
    savoir_faire = data.get("savoir_faire", [])
    profile_text = data.get("profile", "")

    sf_items = []
    if savoir_faire:
        sf_items = [s for s in savoir_faire if s and s.strip()]
    elif profile_text:
        sentences = re.split(r"(?<=[.!])\s+", profile_text.strip())
        sf_items = [s.strip() for s in sentences if len(s.strip()) > 20]

    if sf_items:
        section = Section(header="Savoir Faire", content_type="bullets")
        section.bullet_items = sf_items
        cv.sections.append(section)

    # ── Compétences Techniques ──
    skills = data.get("skills", [])
    if skills:
        section = Section(header="Compétences Techniques", content_type="table")
        for s in skills:
            if isinstance(s, dict):
                section.table_rows.append(TableRow(
                    left=s.get("category", ""),
                    right=s.get("details", "")
                ))
            elif isinstance(s, str):
                section.table_rows.append(TableRow(left="", right=s))
        cv.sections.append(section)

    # ── Langues ──
    languages = data.get("languages", [])
    if languages:
        section = Section(header="Langues", content_type="table")
        for l in languages:
            if isinstance(l, dict):
                section.table_rows.append(TableRow(
                    left=l.get("language", ""),
                    right=l.get("level", "")
                ))
            elif isinstance(l, str):
                section.table_rows.append(TableRow(left=l, right=""))
        cv.sections.append(section)

    # ── Expériences Professionnelles ──
    experiences = data.get("experiences", [])
    if experiences:
        section = Section(
            header="Expériences Professionnelles",
            content_type="experiences"
        )

        for exp_data in experiences:
            if not isinstance(exp_data, dict):
                continue

            company = exp_data.get("company", "")
            role    = exp_data.get("role", "")
            dates   = exp_data.get("dates", "")
            context = exp_data.get("context", "")
            tasks   = exp_data.get("tasks", [])
            stack   = exp_data.get("tech_stack", [])

            duration   = _compute_duration(dates)
            title_line = f"Entreprise {company}\t{duration}" if duration else f"Entreprise {company}"
            poste      = f"Poste {role}" if role else ""

            sub_sections = []

            if context and context.strip():
                sub_sections.append(("Contexte :", [context]))

            if tasks:
                clean_tasks = [t for t in tasks if t and t.strip()]
                if clean_tasks:
                    sub_sections.append(("ROLE :", clean_tasks))

            if stack:
                stack_list  = stack if isinstance(stack, list) else [stack]
                clean_stack = [s for s in stack_list if s and s.strip()]
                if clean_stack:
                    sub_sections.append(("Environnement technique :", clean_stack))

            block = ExperienceBlock(
                title_line=title_line,
                poste=poste,
                sub_sections=sub_sections,
            )
            section.experience_blocks.append(block)

        cv.sections.append(section)

    return cv


def parse_with_mistral(raw_text: str) -> ParsedCV:
    data = _call_mistral(raw_text)
    return _json_to_parsed_cv(data)


def parse_file_with_mistral(file_path: str) -> ParsedCV:
    sys.path.insert(0, str(Path(__file__).parent))
    from extractor import extract_text

    print(f"📄 Extraction : {Path(file_path).name}")
    raw_text = extract_text(file_path)
    print(f"   {len(raw_text)} caractères extraits")
    return parse_with_mistral(raw_text)


if __name__ == "__main__":
    from parser_v2 import print_parsed

    if len(sys.argv) < 2:
        print('Usage: python parser.py "/chemin/vers/cv.pdf"')
        print('Clé API : export MISTRAL_API_KEY="votre-clé"')
        sys.exit(1)

    cv = parse_file_with_mistral(sys.argv[1])
    print_parsed(cv)

    from extractor import extract_text
    raw = extract_text(sys.argv[1])
    cached = _load_cache(_cache_key(raw))
    if cached:
        out = Path(sys.argv[1]).stem + "_mistral.json"
        with open(out, "w", encoding="utf-8") as f:
            json.dump(cached, f, ensure_ascii=False, indent=2)
        print(f"\n💾  JSON sauvegardé → {out}")