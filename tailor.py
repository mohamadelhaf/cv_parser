"""
tailor.py — Adapter un ParsedCV pour mieux correspondre à une offre d'emploi.

Règles :
- JAMAIS inventer de compétences, expériences ou formations.
- UNIQUEMENT reformuler, réorganiser et mettre en valeur le contenu existant.
- Utiliser le vocabulaire de l'offre quand c'est honnête.
- Réordonner les bullet points pour mettre les plus pertinents en premier.
- Adapter le titre du profil si c'est honnête.
"""

import os
import re
import json

from parser_v2 import (
    ParsedCV, ProfileData, Section, ExperienceBlock, TableRow,
)


# ---------------------------------------------------------------------------
# CV → texte lisible pour le prompt
# ---------------------------------------------------------------------------

def _cv_to_text(cv: ParsedCV) -> str:
    """Sérialise un ParsedCV en texte lisible pour le LLM."""
    lines = []
    p = cv.profile
    lines.append(f"NOM: {p.name}")
    lines.append(f"TITRE: {p.title}")
    lines.append(f"LANGUE: {p.language}")
    lines.append(f"EXPÉRIENCE: {p.years_experience}")
    lines.append("")

    for section in cv.sections:
        lines.append(f"=== SECTION: {section.header} (type: {section.content_type}) ===")

        if section.table_rows:
            for row in section.table_rows:
                lines.append(f"  [{row.left}] | [{row.right}]")

        if section.bullet_items:
            for item in section.bullet_items:
                lines.append(f"  • {item}")

        if section.experience_blocks:
            for exp in section.experience_blocks:
                lines.append(f"  --- {exp.title_line} ---")
                if exp.poste:
                    lines.append(f"  Poste: {exp.poste}")
                for sub_header, items in exp.sub_sections:
                    lines.append(f"    [{sub_header}]")
                    for item in items:
                        lines.append(f"      • {item}")

        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

TAILOR_SYSTEM_PROMPT = """Tu es un expert en rédaction de CV et en recrutement IT.
Ta mission : adapter un CV existant pour maximiser sa compatibilité avec une offre d'emploi donnée.

RÈGLES ABSOLUES — À RESPECTER IMPÉRATIVEMENT :

1. NE JAMAIS MENTIR : tu ne peux PAS ajouter de compétences, expériences, formations ou certifications que le candidat n'a pas dans son CV original.
2. Tu peux UNIQUEMENT reformuler, réorganiser et mettre en valeur le contenu EXISTANT.
3. Utilise le vocabulaire et les mots-clés de l'offre quand c'est honnête (synonymes, reformulations).
4. Réordonne les bullet points pour mettre en premier les plus pertinents pour l'offre.
5. ORDRE DES SECTIONS OBLIGATOIRE (format INTM) : Formation → Savoir Faire → Compétences Techniques → Expériences Professionnelles → Projets (et autres). NE CHANGE JAMAIS cet ordre.
6. Adapte le titre du profil pour mieux correspondre au poste visé, SEULEMENT si c'est honnête.
7. Reformule les descriptions d'expériences pour utiliser les termes de l'offre quand le candidat a réellement fait ces tâches.
8. Conserve TOUTES les expériences et sections — ne supprime rien.
9. Conserve les dates, noms d'entreprises, durées et faits factuels tels quels.
10. Conserve le nom, la langue et les années d'expérience tels quels.

RÈGLES DE STRUCTURE — TRÈS IMPORTANT :

11. TITLE_LINE : Le champ title_line DOIT contenir un caractère TAB (\\t) entre l'entreprise et la durée. Format exact : "Entreprise NOM\\tDurée X ans Y mois : AAAA – AAAA". Le \\t est OBLIGATOIRE.
12. SOUS-SECTIONS D'EXPÉRIENCE : Conserve EXACTEMENT la même structure de sous-sections que l'original. Si l'original a "Contexte" puis "Activités :" puis "Environnement Technique :", tu DOIS garder ces mêmes sous-sections avec ces mêmes noms. Ne fusionne PAS tout dans "ROLE :".
13. SAVOIR FAIRE : Si le Savoir Faire original est structuré avec des catégories et des sous-éléments, conserve cette structure. Ne l'aplatis PAS en une liste plate.
14. ENVIRONNEMENT TECHNIQUE : Conserve le format original des items d'environnement technique (ex: "Business Intelligence: Power BI (DAX, PowerQuery)"). Ne les reformule PAS.
15. TABLES : Pour les sections de type "table", conserve la même structure gauche/droite. Tu peux réordonner les lignes mais pas changer le format.

Tu dois retourner UNIQUEMENT un objet JSON valide (pas de texte avant ou après, pas de markdown, pas de backticks).
"""

TAILOR_JSON_SCHEMA = """{
  "profile": {
    "name": "INCHANGÉ",
    "title": "Adapté si pertinent",
    "language": "INCHANGÉE",
    "years_experience": "INCHANGÉES"
  },
  "sections": [
    {
      "header": "Formation",
      "content_type": "table",
      "table_rows": [{"left": "2019", "right": "Master 2 – Nom du diplôme"}],
      "bullet_items": [],
      "experience_blocks": []
    },
    {
      "header": "Savoir Faire",
      "content_type": "bullets",
      "table_rows": [],
      "bullet_items": ["Catégorie ou item — GARDER LA STRUCTURE ORIGINALE"],
      "experience_blocks": []
    },
    {
      "header": "Compétences Techniques",
      "content_type": "table",
      "table_rows": [{"left": "Catégorie", "right": "outils, séparés par virgule"}],
      "bullet_items": [],
      "experience_blocks": []
    },
    {
      "header": "Expériences Professionnelles",
      "content_type": "experiences",
      "table_rows": [],
      "bullet_items": [],
      "experience_blocks": [
        {
          "title_line": "Entreprise NOM_ENTREPRISE\\tDurée X ans Y mois : AAAA – AAAA",
          "poste": "Poste TITRE",
          "sub_sections": [
            ["Contexte", ["Texte de contexte original conservé"]],
            ["Activités :", ["tâche reformulée 1", "tâche reformulée 2"]],
            ["Environnement Technique :", ["Business Intelligence: Power BI (DAX)", "Data: Excel"]]
          ]
        }
      ]
    }
  ]
}

IMPORTANT sur title_line : le caractère \\t (tabulation) est OBLIGATOIRE entre entreprise et durée.
IMPORTANT sur sub_sections : CONSERVER les mêmes noms de sous-sections que dans le CV original (Contexte, Activités, ROLE, Environnement Technique, etc.).
"""


# ---------------------------------------------------------------------------
# Parsing de la réponse JSON
# ---------------------------------------------------------------------------

def _parse_json_response(text: str) -> dict:
    """Extrait et parse le JSON de la réponse du LLM."""
    text = text.strip()
    # Supprimer les éventuels code fences markdown
    text = re.sub(r"^```(?:json)?\s*\n?", "", text)
    text = re.sub(r"\n?```\s*$", "", text)
    text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Tenter d'extraire le premier objet JSON
        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            return json.loads(match.group())
        raise


def _fix_title_line(raw: str) -> str:
    """Post-process a title_line to ensure proper INTM format.
    
    The LLM often fails to produce a real \\t character in JSON.
    This function normalizes various formats into:
      "Entreprise NAME\\tDurée X ans Y mois : AAAA – AAAA"
    """
    if not raw or not raw.strip():
        return raw
    
    line = raw.strip()
    
    # If it already has a tab and starts with "Entreprise", it's fine
    if "\t" in line and line.startswith("Entreprise "):
        return line
    
    # Try to separate company name from duration info
    # Patterns the LLM might produce:
    #   "SNCF 42 mois : 2022 – 2026"
    #   "Entreprise SNCF Durée 3 ans 6 mois : 2022 – 2026"
    #   "SNCF\t42 mois (2022 – 2026)"
    #   "Entreprise SNCF\tDurée 3 ans : 2022 – 2026"
    #   "SNCF    Durée 42 mois : 2022 - 2026"
    
    # Strip "Entreprise " prefix if present
    if re.match(r"(?i)^entreprise\s+", line):
        line = re.sub(r"(?i)^entreprise\s+", "", line).strip()
    
    # Replace existing tab with space for uniform processing
    line = line.replace("\t", " ")
    
    # Try to find the split point between company name and duration
    # Pattern: "NAME ... Durée X" or "NAME ... X mois/ans" or "NAME ... (YYYY"
    
    # Match "Durée" keyword
    m = re.search(r"\s+(Durée\s+.*)$", line, re.IGNORECASE)
    if m:
        company = line[:m.start()].strip()
        duration = m.group(1).strip()
        return f"Entreprise {company}\t{duration}"
    
    # Match "X mois" or "X ans" pattern (duration without "Durée" prefix)
    m = re.search(r"\s+(\d+\s+(?:mois|ans?|année)\S*(?:\s*:?\s*\(?\d{4}.*)?)$", line, re.IGNORECASE)
    if m:
        company = line[:m.start()].strip()
        duration_part = m.group(1).strip()
        # Clean up: remove parentheses around dates
        duration_part = duration_part.replace("(", ": ").replace(")", "").strip()
        duration_part = re.sub(r"\s*:\s*:\s*", " : ", duration_part)
        return f"Entreprise {company}\tDurée {duration_part}"
    
    # Match "Depuis" pattern
    m = re.search(r"\s+(Depuis\s+.*)$", line, re.IGNORECASE)
    if m:
        company = line[:m.start()].strip()
        duration = m.group(1).strip()
        return f"Entreprise {company}\t{duration}"
    
    # Fallback: if there's already a tab-like separation, use it
    if "  " in line:
        parts = re.split(r"\s{2,}", line, maxsplit=1)
        if len(parts) == 2:
            return f"Entreprise {parts[0].strip()}\t{parts[1].strip()}"
    
    # Last resort: return as-is with Entreprise prefix
    return f"Entreprise {line}"


def _dict_to_parsed_cv(data: dict) -> ParsedCV:
    """Convertit le dict JSON en objet ParsedCV."""
    profile_data = data.get("profile", {})
    profile = ProfileData(
        lines=[
            profile_data.get("name", ""),
            profile_data.get("title", ""),
            profile_data.get("language", ""),
            profile_data.get("years_experience", ""),
        ],
        name=profile_data.get("name", ""),
        title=profile_data.get("title", ""),
        language=profile_data.get("language", ""),
        years_experience=profile_data.get("years_experience", ""),
    )

    sections = []
    for sec_data in data.get("sections", []):
        section = Section(
            header=sec_data.get("header", ""),
            content_type=sec_data.get("content_type", ""),
        )

        # Table rows
        for row_data in sec_data.get("table_rows", []) or []:
            if isinstance(row_data, dict):
                section.table_rows.append(
                    TableRow(
                        left=row_data.get("left", ""),
                        right=row_data.get("right", ""),
                    )
                )

        # Bullet items
        for item in sec_data.get("bullet_items", []) or []:
            if isinstance(item, str) and item.strip():
                section.bullet_items.append(item)

        # Experience blocks
        for exp_data in sec_data.get("experience_blocks", []) or []:
            if not isinstance(exp_data, dict):
                continue

            sub_sections = []
            for sub in exp_data.get("sub_sections", []) or []:
                if isinstance(sub, (list, tuple)) and len(sub) == 2:
                    header = str(sub[0]) if sub[0] else ""
                    items = sub[1] if isinstance(sub[1], list) else [str(sub[1])]
                    sub_sections.append((header, items))
                elif isinstance(sub, dict):
                    header = sub.get("header", sub.get("name", ""))
                    items = sub.get("items", sub.get("content", []))
                    if isinstance(items, str):
                        items = [items]
                    sub_sections.append((header, items))

            section.experience_blocks.append(
                ExperienceBlock(
                    title_line=_fix_title_line(exp_data.get("title_line", "")),
                    poste=exp_data.get("poste", ""),
                    sub_sections=sub_sections,
                )
            )

        sections.append(section)

    return ParsedCV(profile=profile, sections=sections)


# ---------------------------------------------------------------------------
# Fonction principale
# ---------------------------------------------------------------------------

def tailor_cv(
    cv: ParsedCV,
    offer_text: str,
    api_key: str,
    match_summary: str = "",
) -> ParsedCV:
    """
    Adapte un CV pour mieux correspondre à une offre d'emploi via l'API Mistral.

    Args:
        cv: Le ParsedCV original
        offer_text: Le texte de l'offre d'emploi
        api_key: Clé API Mistral
        match_summary: Résumé optionnel du matching pour contexte

    Returns:
        Un nouveau ParsedCV avec le contenu adapté
    """
    from mistralai.client import Mistral

    if not api_key:
        raise ValueError("Clé API Mistral introuvable.")

    cv_text = _cv_to_text(cv)

    # Construire le prompt utilisateur
    user_prompt = f"""Voici le CV actuel du candidat :

{cv_text}

---

Voici l'offre d'emploi cible :

{offer_text}
"""

    if match_summary:
        user_prompt += f"""
---

Résultat du matching (pour contexte) :

{match_summary}
"""

    user_prompt += f"""
---

Adapte le CV pour maximiser la compatibilité avec cette offre.
Retourne UNIQUEMENT un objet JSON valide avec cette structure :

{TAILOR_JSON_SCHEMA}

RAPPELS CRITIQUES :
- NE MENS PAS — n'invente aucune compétence ou expérience
- Conserve les dates, entreprises et faits factuels tels quels
- Reformule et réorganise UNIQUEMENT le contenu existant
- sub_sections est une liste de paires [header, [items]], PAS un dict
- ORDRE SECTIONS : Formation → Savoir Faire → Compétences Techniques → Expériences → Projets
- title_line DOIT avoir un \\t (TAB) entre entreprise et durée : "Entreprise NOM\\tDurée X ans : AAAA – AAAA"
- CONSERVE les noms de sous-sections originaux (Contexte, Activités, ROLE, Environnement Technique) — ne les fusionne PAS
- CONSERVE la structure du Savoir Faire (catégories + sous-éléments si présents)
- CONSERVE le format de l'environnement technique tel quel
"""

    client = Mistral(api_key=api_key)

    response = client.chat.complete(
        model="mistral-large-latest",
        messages=[
            {"role": "system", "content": TAILOR_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.3,
        response_format={"type": "json_object"},
    )

    raw_text = response.choices[0].message.content
    data = _parse_json_response(raw_text)
    tailored_cv = _dict_to_parsed_cv(data)

    return tailored_cv