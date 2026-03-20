"""
Step 2: CV Parser (rule-based)
Detects sections in raw CV text, then parses each into structured data.

Usage:
    from parser import parse_cv
    cv = parse_cv(raw_text)
    print(cv.name, cv.education, cv.experiences, ...)
"""

import re
import sys
from dataclasses import dataclass, field
from typing import Optional


# ===========================================================================
# Data structures
# ===========================================================================

@dataclass
class Education:
    years: str          # e.g. "2023–2025"
    degree: str         # e.g. "Master 2 Systèmes distribués & Data Science"
    institution: str    # e.g. "Université Paris-Est Créteil (UPEC)"


@dataclass
class Experience:
    dates: str          # e.g. "Sep. 2024 – Sep. 2025"
    title: str          # e.g. "Alternant Data Engineer"
    company: str        # e.g. "Pompac Développement, Melun, France"
    tasks: list[str] = field(default_factory=list)    # ROLE bullets
    stack: list[str] = field(default_factory=list)    # ENV TECHNIQUE bullets


@dataclass
class TechSkill:
    category: str       # e.g. "Langages"
    details: str        # e.g. "Python, Java, C++, Kotlin"


@dataclass
class CVData:
    name: str = ""
    headline: str = ""                                  # e.g. "Ingénieur Data & IA"
    language: str = ""                                  # e.g. "Anglais C1 (TOEIC 925)"
    years_experience: str = ""                          # e.g. "+ 2 ans d'expérience"
    profile: str = ""                                   # Profil paragraph
    education: list[Education] = field(default_factory=list)
    experiences: list[Experience] = field(default_factory=list)
    projects: list[Experience] = field(default_factory=list)  # Same structure as experiences
    tech_skills: list[TechSkill] = field(default_factory=list)
    languages: dict[str, str] = field(default_factory=dict)   # {"Français": "Courant", ...}


# ===========================================================================
# Part A: Section detection
# ===========================================================================

# Each pattern matches common French & English section headers
SECTION_HEADERS = {
    "profil": re.compile(
        r"^(?:profil|profile|résumé|resume|à\s+propos|about|objectif|objective|summary)$",
        re.IGNORECASE,
    ),
    "formation": re.compile(
        r"^(?:formation|formations|education|études|etudes|diplômes|diplomes|parcours\s+acad[ée]mique)(?:\s+[&et]+\s+certifications?)?$",
        re.IGNORECASE,
    ),
    "experiences": re.compile(
        r"^(?:exp[ée]riences?\s+professionn\w*|professional\s+experience|work\s+experience|parcours\s+professionn\w*|exp[ée]riences?)$",
        re.IGNORECASE,
    ),
    "projets": re.compile(
        r"^(?:projets?\s+s[ée]lectionn[ée]s?|projets?\s+(?:universitaires?|personnels?|professionnels?|acad[ée]miques?)|projets?|projects?|r[ée]alisations?)$",
        re.IGNORECASE,
    ),
    "savoir_faire": re.compile(
        r"^(?:savoir[\s\-]faire)$",
        re.IGNORECASE,
    ),
    "competences": re.compile(
        r"^(?:comp[ée]tences?\s+techniques?|comp[ée]tences?\s+fonctionnelles?|technical\s+skills?|comp[ée]tences?|skills?|outils?\s+(?:et\s+)?technologies?)$",
        re.IGNORECASE,
    ),
    "langues": re.compile(
        r"^(?:langues?|languages?|langues?\s+parl[ée]es?)$",
        re.IGNORECASE,
    ),
}


def _clean(line: str) -> str:
    """Strip whitespace and normalize spaces."""
    return re.sub(r"\s+", " ", line.strip())


def _detect_section(line: str) -> Optional[str]:
    """
    Check if a line is a section header.
    Returns the section key (e.g. "formation") or None.
    """
    cleaned = _clean(line)
    if not cleaned:
        return None
    # Skip lines that are too long to be headers
    if len(cleaned) > 60:
        return None
    for key, pattern in SECTION_HEADERS.items():
        if pattern.match(cleaned):
            return key
    return None


def split_into_sections(text: str) -> dict[str, list[str]]:
    """
    Split raw CV text into named sections.
    
    Handles duplicate section names (e.g. two "Formation" sections,
    two "Projets" sections) by numbering them: formation, formation_2, etc.
    
    Returns a dict like:
        {
            "_header": [...],
            "formation": [...],        # first Formation = education
            "formation_2": [...],       # second FORMATIONS = training entries
            "experiences": [...],
            "projets": [...],
            "projets_2": [...],
            ...
        }
    """
    lines = text.split("\n")
    sections: dict[str, list[str]] = {}
    
    current_section = "_header"
    current_lines: list[str] = []

    for line in lines:
        detected = _detect_section(line)
        if detected:
            # Save previous section
            sections[current_section] = current_lines
            
            # Handle duplicate keys: add _2, _3, etc.
            key = detected
            suffix = 2
            while key in sections:
                key = f"{detected}_{suffix}"
                suffix += 1
            
            current_section = key
            current_lines = []
        else:
            current_lines.append(line)

    # Save the last section
    sections[current_section] = current_lines

    return sections


# ===========================================================================
# Part B: Section parsers
# ===========================================================================

# --- Helper patterns ---

# Month abbreviations (French + common short forms)
_MONTHS = (
    r"(?:Jan|Fev|F[ée]v|Mar|Avr|Mai|Juin|Jul|Juil|Aou|Ao[uû]t|Sep|Oct|Nov|Dec|D[ée]c)"
    r"\w*\.?"
)

# Date piece: "Sep. 2024", "2024", "01/2025", "09/2022"
_DATE_PIECE = rf"(?:{_MONTHS}\s*)?\d{{4}}|\d{{2}}/\d{{4}}"
# End date can also be "Present" or "Présent"
_DATE_END_PIECE = rf"{_DATE_PIECE}|[Pp]r[ée]sent"

# Matches FULL date ranges on one line: "2023–2025", "Sep. 2024 – Sep. 2025", "01/2024 – 12/2024", "01/2025 – Present"
DATE_RANGE_PATTERN = re.compile(
    rf"^((?:{_DATE_PIECE})\s*[-–—]\s*(?:{_DATE_END_PIECE}))",
    re.IGNORECASE,
)

# Matches date range at END of a line: "some text 01/2024 – 12/2024"
DATE_RANGE_END_PATTERN = re.compile(
    rf"^(.+?)\s+((?:{_DATE_PIECE})\s*[-–—]\s*(?:{_DATE_END_PIECE}))\s*$",
    re.IGNORECASE,
)

# Matches PARTIAL date: "Sep. 2024 –" (start date + dash, end date on next line)
PARTIAL_DATE_PATTERN = re.compile(
    rf"^((?:{_DATE_PIECE}))\s*[-–—]\s*$",
    re.IGNORECASE,
)

# Matches END of a split date: "Sep. 2025" or just "2025" (alone on a line)
DATE_END_PATTERN = re.compile(
    rf"^((?:{_DATE_PIECE}))\s*$",
    re.IGNORECASE,
)

# Matches a single year at start: "2025 Projet..." or "2025Projet..." (PDF glue)
YEAR_PATTERN = re.compile(r"^(\d{4})\s*(\S.+)")

# Matches "COMPANY DE MONTH YEAR A MONTH YEAR" format
# e.g. "BNP PARIBAS DE NOVEMBRE 2024 A JANVIER 2026"
_FULL_MONTHS = (
    r"(?:JANVIER|FEVRIER|FÉVRIER|MARS|AVRIL|MAI|JUIN|JUILLET|AOUT|AOÛT"
    r"|SEPTEMBRE|OCTOBRE|NOVEMBRE|DECEMBRE|DÉCEMBRE"
    r"|Janvier|Fevrier|Février|Mars|Avril|Mai|Juin|Juillet|Aout|Août"
    r"|Septembre|Octobre|Novembre|Decembre|Décembre)"
)
DE_A_DATE_PATTERN = re.compile(
    rf"^(.+?)\s+DE\s+({_FULL_MONTHS})\s+(\d{{4}})\s+A\s+({_FULL_MONTHS})\s*(\d{{4}})\s*$",
    re.IGNORECASE,
)

# Matches bullet prefixes
BULLET_PATTERN = re.compile(r"^\s*[—\-•■▪▸◆➤●★>»→]\s*")

# Matches stack/env lines WITH inline content: "Stack : Excel, VBA, ..."
STACK_PATTERN = re.compile(
    r"(?i)^(?:stack|environnement\s+technique|technologies?\s+utilis[ée]es?|outils?)\s*:\s*(.+)",
)

# --- INTM template patterns ---
# "Entreprise Group Vital Durée 6 mois" or "Entreprise Group VitalDurée 6 mois" (glued)
INTM_COMPANY_PATTERN = re.compile(
    r"(?i)^entreprise\s+(.+?)(?:\s*dur[ée]e\s+(.+))?$",
)
# "Poste Data Engineer"
INTM_POSTE_PATTERN = re.compile(
    r"(?i)^poste\s+(.+)$",
)
# "ROLE :" or "ROLE:" 
INTM_ROLE_PATTERN = re.compile(
    r"(?i)^r[oô]le\s*:\s*$",
)
# "Environnement technique :" or "Environnement technique" (with or without colon)
INTM_ENV_PATTERN = re.compile(
    r"(?i)^(?:environnement\s+technique|stack\s+technique|technologies?)\s*:?\s*$",
)
# "Projet Universitaire 1 DevOps..." or "Projet Personnel IA..."
INTM_PROJECT_PATTERN = re.compile(
    r"(?i)^(?:projet\s+(?:universitaire|personnel|professionnel|client)\s*\d*)\s*(.*)$",
)
# "Formation X - Y" or "FormationX - Y" (glued, no space after Formation)
# Must have content after "Formation" to distinguish from the section header
INTM_TRAINING_PATTERN = re.compile(
    r"(?i)^formation\s*(\S.+)$",
)


def _is_bullet(line: str) -> bool:
    return bool(BULLET_PATTERN.match(line))


def _strip_bullet(line: str) -> str:
    return BULLET_PATTERN.sub("", line).strip()


def _is_page_marker(line: str) -> bool:
    """Detect page markers, PDF headers/footers, and repeated name lines."""
    cleaned = _clean(line)
    # Page numbers: "1/2", "2/2", "Page 3"
    if re.match(r"^\d+/\d+$", cleaned) or re.match(r"(?i)^page\s+\d+", cleaned):
        return True
    # Common PDF header/footer: address lines
    if re.match(r"^\d+\s+rue\s+", cleaned, re.IGNORECASE):
        return True
    # Phone header/footer
    if re.match(r"^T[ée]l\.?\s*:?\s*\+?\d", cleaned, re.IGNORECASE):
        return True
    return False


# --- B1: Header parser ---

def parse_header(lines: list[str]) -> dict:
    """
    Extract name, headline from lines before the first section.
    Skips contact info (email, phone, linkedin, github).
    """
    result = {"name": "", "headline": "", "contacts": []}
    
    contact_pattern = re.compile(
        r"(?i)(@|[\+]\d|\d{2}\s\d{2}|linkedin|github|gitlab|§|ð|cid:)",
    )
    
    for line in lines:
        cleaned = _clean(line)
        if not cleaned or _is_page_marker(cleaned):
            continue
        if contact_pattern.search(cleaned):
            result["contacts"].append(cleaned)
            continue
        if not result["name"]:
            result["name"] = cleaned
        elif not result["headline"] and len(cleaned.split()) <= 8:
            result["headline"] = cleaned
    
    return result


# --- B2: Formation parser ---

def parse_formation(lines: list[str]) -> list[Education]:
    """
    Parse education entries.
    Handles multiple date formats and bullet-prefixed entries.
    Falls back to treating unrecognized lines as simple entries.
    """
    education = []
    undated_lines = []
    
    # Pattern for dates in parentheses at end: "Degree, University (1996-2000)" or "Certification (2018)"
    paren_date_range = re.compile(r"^(.+?)\s*\((\d{4})\s*[-–‑]\s*(\d{4})\)\s*$")
    paren_date_single = re.compile(r"^(.+?)\s*\((\d{4})\)\s*$")
    
    for line in lines:
        cleaned = _clean(line)
        if not cleaned or _is_page_marker(cleaned):
            continue
        
        # Strip bullet characters
        stripped = _strip_bullet(cleaned) if _is_bullet(cleaned) else cleaned
        
        # Skip sub-headings and continuation lines
        if re.match(r"(?i)^(?:modules?\s*:|diplôme|diplome|mention|formation\s+acad[ée]mique|formations?\s+professionn\w*|certifications?)$", stripped):
            continue
        
        # Pattern 1: Date range at start: "2023-2025 Degree, Institution"
        date_match = DATE_RANGE_PATTERN.match(stripped)
        if date_match:
            years = date_match.group(1).strip()
            rest = stripped[date_match.end():].strip()
            parts = re.split(r",\s+|\s+[—–]\s+", rest, maxsplit=1)
            degree = parts[0].strip()
            institution = parts[1].strip() if len(parts) > 1 else ""
            education.append(Education(years=years, degree=degree, institution=institution))
            continue
        
        # Pattern 1b: Date range at END of line: "Degree, Institution 09/2022 – 07/2024"
        end_date_match = DATE_RANGE_END_PATTERN.match(stripped)
        if end_date_match:
            text_part = end_date_match.group(1).strip()
            years = end_date_match.group(2).strip()
            parts = re.split(r",\s+|\s+[—–]\s+", text_part, maxsplit=1)
            degree = parts[0].strip()
            institution = parts[1].strip() if len(parts) > 1 else ""
            education.append(Education(years=years, degree=degree, institution=institution))
            continue
        
        # Pattern 1c: Date range in parentheses: "Degree, University (1996-2000)"
        paren_range_match = paren_date_range.match(stripped)
        if paren_range_match:
            text_part = paren_range_match.group(1).strip()
            years = f"{paren_range_match.group(2)}–{paren_range_match.group(3)}"
            parts = re.split(r",\s+|\s+[—–]\s+", text_part, maxsplit=1)
            degree = parts[0].strip()
            institution = parts[1].strip() if len(parts) > 1 else ""
            education.append(Education(years=years, degree=degree, institution=institution))
            continue
        
        # Pattern 1d: Single year in parentheses: "Certification (2018)"
        paren_single_match = paren_date_single.match(stripped)
        if paren_single_match:
            text_part = paren_single_match.group(1).strip()
            years = paren_single_match.group(2)
            education.append(Education(years=years, degree=text_part, institution=""))
            continue
        
        # Pattern 2: Tab-separated (from DOCX tables)
        if "\t" in line:
            parts = line.split("\t", 1)
            education.append(Education(
                years="",
                degree=parts[0].strip(),
                institution=parts[1].strip() if len(parts) > 1 else "",
            ))
            continue
        
        # Pattern 3: Single year at start: "2025 Degree..."
        year_match = YEAR_PATTERN.match(stripped)
        if year_match:
            years = year_match.group(1)
            rest = year_match.group(2).strip()
            parts = re.split(r",\s+|\s+[—–]\s+", rest, maxsplit=1)
            degree = parts[0].strip()
            institution = parts[1].strip() if len(parts) > 1 else ""
            education.append(Education(years=years, degree=degree, institution=institution))
            continue
        
        # Pattern 4: Fallback — collect undated lines for possible second pass
        if stripped and len(stripped) > 3:
            undated_lines.append(stripped)
    
    # If we found NO dated entries, use all undated lines as simple entries
    # (handles CVs like Masso's where formations are just bullet lists)
    if not education and undated_lines:
        for line in undated_lines:
            education.append(Education(years="", degree=line, institution=""))
    
    return education


# --- B3: Experience parser ---

def parse_experiences(lines: list[str]) -> list[Experience]:
    """
    Parse professional experience entries.
    
    Handles TWO formats:
    
    A) Regular CV (date-based):
        "Sep. 2024 – Sep. 2025 Alternant Data Engineer, Company"
        "— bullet task"
        "Stack : tech1, tech2"
    
    B) INTM template (Entreprise/Poste/ROLE):
        "Entreprise Group Vital Durée 6 mois"
        "Poste Data Engineer"
        "ROLE :"
        "task item (no bullet prefix)"
        "Environnement technique :"
        "stack item"
    """
    experiences = []
    current: Optional[Experience] = None
    mode = "tasks"  # tasks | stack
    
    i = 0
    while i < len(lines):
        cleaned = _clean(lines[i])
        
        if not cleaned or _is_page_marker(cleaned):
            i += 1
            continue
        
        # --- Format A: FULL date range on one line ---
        date_match = DATE_RANGE_PATTERN.match(cleaned)
        if date_match:
            if current:
                experiences.append(current)
            dates = date_match.group(1).strip()
            rest = cleaned[date_match.end():].strip()
            title, company = "", ""
            if rest:
                parts = rest.split(",", 1)
                title = parts[0].strip()
                company = parts[1].strip() if len(parts) > 1 else ""
            current = Experience(dates=dates, title=title, company=company)
            mode = "tasks"
            i += 1
            continue
        
        # --- Format C: date range at END of line: "Title 01/2024 – 12/2024" ---
        end_date_match = DATE_RANGE_END_PATTERN.match(cleaned)
        if end_date_match:
            if current:
                experiences.append(current)
            text_part = end_date_match.group(1).strip()
            dates = end_date_match.group(2).strip()
            title, company = "", ""
            if text_part:
                parts = text_part.split(",", 1)
                title = parts[0].strip()
                company = parts[1].strip() if len(parts) > 1 else ""
            current = Experience(dates=dates, title=title, company=company)
            mode = "tasks"
            i += 1
            continue
        
        # --- Format D: "COMPANY DE MONTH YEAR A MONTH YEAR" ---
        de_a_match = DE_A_DATE_PATTERN.match(cleaned)
        if de_a_match:
            if current:
                experiences.append(current)
            company = de_a_match.group(1).strip()
            dates = f"{de_a_match.group(2)} {de_a_match.group(3)} – {de_a_match.group(4)} {de_a_match.group(5)}"
            # Next line is usually the job title
            title = ""
            j = i + 1
            while j < len(lines):
                next_cleaned = _clean(lines[j])
                if next_cleaned and not _is_page_marker(next_cleaned):
                    # Check if it's not a bullet — it's the title
                    if not BULLET_PATTERN.match(next_cleaned) and not next_cleaned.startswith("CONTEXTE") and not next_cleaned.startswith("ACTIVITES"):
                        title = next_cleaned
                        i = j + 1
                    else:
                        i = j
                    break
                j += 1
            else:
                i += 1
            current = Experience(dates=dates, title=title, company=company)
            mode = "tasks"
            continue
        
        # --- Format A: PARTIAL date (split across lines) ---
        partial_match = PARTIAL_DATE_PATTERN.match(cleaned)
        if partial_match:
            start_date = partial_match.group(1).strip()
            end_date = ""
            j = i + 1
            while j < len(lines):
                next_cleaned = _clean(lines[j])
                if next_cleaned:
                    end_match = DATE_END_PATTERN.match(next_cleaned)
                    if end_match:
                        end_date = end_match.group(1).strip()
                        j += 1
                    break
                j += 1
            dates = f"{start_date} – {end_date}" if end_date else f"{start_date} –"
            if current:
                experiences.append(current)
            title, company = "", ""
            while j < len(lines):
                title_cleaned = _clean(lines[j])
                if title_cleaned and not _is_bullet(title_cleaned):
                    parts = title_cleaned.split(",", 1)
                    title = parts[0].strip()
                    company = parts[1].strip() if len(parts) > 1 else ""
                    j += 1
                    break
                elif title_cleaned:
                    break
                j += 1
            current = Experience(dates=dates, title=title, company=company)
            mode = "tasks"
            i = j
            continue
        
        # --- Format B: INTM "Entreprise X Durée Y" ---
        intm_match = INTM_COMPANY_PATTERN.match(cleaned)
        if intm_match:
            if current:
                experiences.append(current)
            company = intm_match.group(1).strip()
            duration = intm_match.group(2).strip() if intm_match.group(2) else ""
            current = Experience(dates=duration, title="", company=company)
            mode = "scan"  # waiting for Poste or ROLE
            i += 1
            continue
        
        # --- Format B: INTM "Poste X" ---
        if current:
            poste_match = INTM_POSTE_PATTERN.match(cleaned)
            if poste_match:
                current.title = poste_match.group(1).strip()
                i += 1
                continue
        
        # --- Both formats: "ROLE :" header ---
        if current and INTM_ROLE_PATTERN.match(cleaned):
            mode = "tasks"
            i += 1
            continue
        
        # --- Both formats: "Environnement technique :" header ---
        cleaned_no_bullet = _strip_bullet(cleaned) if _is_bullet(cleaned) else cleaned
        if current and INTM_ENV_PATTERN.match(cleaned_no_bullet):
            mode = "stack"
            i += 1
            continue
        
        # --- Both formats: Inline "Stack : content" or "● Environnement Technique : content" ---
        stack_match = STACK_PATTERN.match(cleaned) or STACK_PATTERN.match(cleaned_no_bullet)
        if stack_match and current:
            current.stack.append(stack_match.group(1).strip())
            mode = "stack"
            i += 1
            continue
        
        # --- Content line (bullet or plain text) ---
        if current:
            item = _strip_bullet(cleaned) if _is_bullet(cleaned) else cleaned
            if item:
                if mode == "stack":
                    current.stack.append(item)
                elif mode in ("tasks", "scan"):
                    # In "scan" mode (after Entreprise, before ROLE), 
                    # skip the Poste line if we haven't found it yet
                    if mode == "scan" and not current.title:
                        # This line might be the title
                        current.title = item
                    else:
                        current.tasks.append(item)
                    mode = "tasks"
        else:
            # No current experience — try to start one from freeform line
            # (handles cases where the format doesn't start with a clear marker)
            pass
        
        i += 1
    
    if current:
        experiences.append(current)
    
    return experiences


# --- B4: Projects parser ---

def parse_projects(lines: list[str]) -> list[Experience]:
    """
    Parse project entries. Year at start, then bullet items.
    """
    projects = []
    current: Optional[Experience] = None
    
    for line in lines:
        cleaned = _clean(line)
        
        if not cleaned or _is_page_marker(cleaned):
            continue
        
        # New project: year at start
        year_match = YEAR_PATTERN.match(cleaned)
        if year_match:
            if current:
                projects.append(current)
            current = Experience(
                dates=year_match.group(1),
                title=year_match.group(2).strip(),
                company="",
            )
            continue
        
        if not current:
            continue
        
        # Bullet line
        if _is_bullet(cleaned):
            item = _strip_bullet(cleaned)
            if item:
                current.tasks.append(item)
            continue
        
        # Continuation
        if current.tasks:
            current.tasks[-1] += " " + cleaned
        else:
            current.tasks.append(cleaned)
    
    if current:
        projects.append(current)
    
    return projects


# --- B5: Technical skills parser ---

def parse_tech_skills(lines: list[str]) -> list[TechSkill]:
    """
    Parse technical skills: "Category  Details" (tab, colon, multi-space,
    or known-keyword separated).
    
    Handles PDF output where category and details are single-space separated:
        "Langages Python, Java, C++, Kotlin"
    by detecting known category keywords at the start of the line.
    """
    skills = []
    
    # Known category keywords (French + English, case-insensitive)
    # Order matters: longer phrases first to avoid partial matches
    KNOWN_CATEGORIES = [
        "bases de données", "base de données",
        "systèmes d'exploitation", "systemes d'exploitation",
        "cloud/devops", "cloud / devops", "cloud devops",
        "data viz", "data visualization",
        "ia/ml", "ia / ml", "ia ml", "ai/ml",
        "langages", "languages", "langages de programmation",
        "programmation", "programming",
        "back-end", "backend", "back end",
        "front-end", "frontend", "front end",
        "frameworks", "framework",
        "infrastructures", "infrastructure",
        "bureautique", "office",
        "méthodes", "methodes", "methods", "méthodologies",
        "outils", "tools",
        "os", "système", "systeme",
    ]
    
    for line in lines:
        cleaned = _clean(line)
        if not cleaned or _is_page_marker(cleaned):
            continue
        
        matched = False
        
        # Pattern 1: Tab-separated (from DOCX)
        if "\t" in line:
            parts = line.split("\t", 1)
            cat = parts[0].strip()
            details = parts[1].strip() if len(parts) > 1 else ""
            if cat:
                skills.append(TechSkill(category=cat, details=details))
            matched = True
        
        # Pattern 2: "Category : details"
        if not matched:
            colon_match = re.match(r"^([^:]{2,30})\s*:\s+(.+)$", cleaned)
            if colon_match:
                skills.append(TechSkill(
                    category=colon_match.group(1).strip(),
                    details=colon_match.group(2).strip(),
                ))
                matched = True
        
        # Pattern 3: Multi-space separated (3+ spaces)
        if not matched:
            parts = re.split(r"\s{3,}", cleaned, maxsplit=1)
            if len(parts) == 2 and len(parts[0].split()) <= 4:
                skills.append(TechSkill(
                    category=parts[0].strip(),
                    details=parts[1].strip(),
                ))
                matched = True
        
        # Pattern 4: Known category keyword at start (for single-space PDF text)
        if not matched:
            lower = cleaned.lower()
            for keyword in KNOWN_CATEGORIES:
                if lower.startswith(keyword):
                    # Check that the keyword is followed by a space and more text
                    rest = cleaned[len(keyword):].strip()
                    if rest:
                        # Reconstruct original-case category from the line
                        category = cleaned[:len(keyword)].strip()
                        skills.append(TechSkill(category=category, details=rest))
                        matched = True
                        break
        
        # Fallback: append to last skill's details
        if not matched:
            if skills:
                skills[-1].details += ", " + cleaned
            else:
                skills.append(TechSkill(category="", details=cleaned))
    
    return skills


# --- B6: Languages parser ---

def parse_languages(lines: list[str]) -> dict[str, str]:
    """
    Parse language entries into {"Français": "Courant", "Anglais": "C1 (TOEIC 925)"}.
    """
    languages = {}
    
    for line in lines:
        cleaned = _clean(line)
        if not cleaned or _is_page_marker(cleaned):
            continue
        
        # Tab-separated
        if "\t" in line:
            parts = line.split("\t", 1)
            if len(parts) == 2:
                languages[parts[0].strip()] = parts[1].strip()
            continue
        
        # Multi-space separated
        parts = re.split(r"\s{3,}", cleaned, maxsplit=1)
        if len(parts) == 2:
            languages[parts[0].strip()] = parts[1].strip()
            continue
        
        # "Language : Level"
        colon_match = re.match(r"^(\w+)\s*:\s+(.+)$", cleaned)
        if colon_match:
            languages[colon_match.group(1).strip()] = colon_match.group(2).strip()
            continue
        
        # "Français Courant"
        words = cleaned.split(None, 1)
        if len(words) == 2:
            languages[words[0]] = words[1]
    
    return languages


# ===========================================================================
# Part C: Main parser
# ===========================================================================

def _parse_intm_blocks(lines: list[str]) -> list[Experience]:
    """
    Parse INTM-format blocks that use ROLE:/Environnement technique: structure.
    Used for duplicate formation/projets sections (formation_2, projets_2, etc.)
    which are actually training or project entries, not education.
    
    Each block starts with a title line (project name, training name, etc.)
    followed by ROLE:/Environnement technique: sections.
    """
    experiences = []
    current: Optional[Experience] = None
    mode = "scan"
    
    for line in lines:
        cleaned = _clean(line)
        if not cleaned or _is_page_marker(cleaned):
            continue
        
        # ROLE : header
        if INTM_ROLE_PATTERN.match(cleaned):
            mode = "tasks"
            continue
        
        # Environnement technique : header
        if INTM_ENV_PATTERN.match(cleaned):
            mode = "stack"
            continue
        
        # Inline stack
        stack_match = STACK_PATTERN.match(cleaned)
        if stack_match and current:
            current.stack.append(stack_match.group(1).strip())
            mode = "stack"
            continue
        
        # Project/training title line (starts a new block)
        # Heuristic: if we're in "scan" mode and this isn't a bullet,
        # and we don't have a current block (or current already has tasks), 
        # it's a new entry title
        project_match = INTM_PROJECT_PATTERN.match(cleaned)
        training_match = INTM_TRAINING_PATTERN.match(cleaned)
        
        if project_match or training_match:
            if current:
                experiences.append(current)
            title = (project_match.group(0) if project_match else 
                     training_match.group(0) if training_match else cleaned)
            current = Experience(dates="", title=title, company="")
            mode = "scan"
            continue
        
        # Content line
        if current:
            item = _strip_bullet(cleaned) if _is_bullet(cleaned) else cleaned
            if mode == "stack":
                current.stack.append(item)
            elif mode == "tasks":
                current.tasks.append(item)
            elif mode == "scan":
                # First non-header line without a current block = new entry
                if not current.title:
                    current.title = item
                else:
                    current.tasks.append(item)
        else:
            # No current entry — start one
            current = Experience(dates="", title=cleaned, company="")
            mode = "scan"
    
    if current:
        experiences.append(current)
    
    return experiences


def parse_cv(text: str) -> CVData:
    """
    Parse raw CV text into structured CVData.
    
    Handles both regular CVs and INTM-formatted templates.
    Duplicate sections (formation_2, projets_2, etc.) are parsed
    as additional experience/project entries.
    """
    cv = CVData()
    
    # Split into sections
    sections = split_into_sections(text)
    
    # Parse header
    if "_header" in sections:
        header = parse_header(sections["_header"])
        cv.name = header["name"]
        cv.headline = header["headline"]
    
    # Parse profil
    if "profil" in sections:
        profile_lines = [_clean(l) for l in sections["profil"] if _clean(l)]
        cv.profile = " ".join(profile_lines)
    
    # Parse formation (first occurrence = education)
    if "formation" in sections:
        cv.education = parse_formation(sections["formation"])
    
    # Parse experiences
    if "experiences" in sections:
        cv.experiences = parse_experiences(sections["experiences"])
    
    # Parse projects (first occurrence)
    if "projets" in sections:
        cv.projects = parse_projects(sections["projets"])
    
    # Parse savoir faire (separate from competences)
    if "savoir_faire" in sections:
        savoir_lines = [_clean(l) for l in sections["savoir_faire"] if _clean(l)]
        # Store as skills list in profile or a dedicated field
        # For now, append to tech_skills with empty category as bullet items
        pass  # savoir_faire is handled by generator directly from sections
    
    # Parse technical skills
    if "competences" in sections:
        cv.tech_skills = parse_tech_skills(sections["competences"])
    
    # Parse languages
    if "langues" in sections:
        cv.languages = parse_languages(sections["langues"])
    
    # --- Handle duplicate sections ---
    # formation_2, formation_3, etc. = training entries → add to experiences
    # projets_2, projets_3, etc. = more projects → add to projects
    for key, lines in sections.items():
        if key.startswith("formation_") and key != "formation":
            extra = _parse_intm_blocks(lines)
            cv.experiences.extend(extra)
        elif key.startswith("projets_") and key != "projets":
            extra = _parse_intm_blocks(lines)
            cv.projects.extend(extra)
        elif key.startswith("experiences_") and key != "experiences":
            extra = parse_experiences(lines)
            cv.experiences.extend(extra)
    
    return cv


def get_savoir_faire(text: str) -> list[str]:
    """
    Extract savoir-faire items from CV text.
    Returns a list of skill strings, or empty list if not found.
    Useful for the INTM template which has a separate Savoir Faire section.
    """
    sections = split_into_sections(text)
    if "savoir_faire" not in sections:
        return []
    items = []
    for line in sections["savoir_faire"]:
        cleaned = _clean(line)
        if cleaned and not _is_page_marker(cleaned):
            if _is_bullet(cleaned):
                cleaned = _strip_bullet(cleaned)
            items.append(cleaned)
    return items


# ===========================================================================
# CLI: pretty-print parsed CV
# ===========================================================================

def print_cv(cv: CVData):
    """Pretty-print parsed CV data for debugging."""
    print(f"\n{'='*60}")
    print(f"  Name:       {cv.name}")
    print(f"  Headline:   {cv.headline}")
    print(f"  Language:   {cv.language}")
    print(f"  Experience: {cv.years_experience}")
    if cv.profile:
        print(f"  Profile:    {cv.profile[:100]}...")
    
    print(f"\n📚 Formation ({len(cv.education)}):")
    for e in cv.education:
        print(f"  [{e.years}] {e.degree}")
        if e.institution:
            print(f"          └─ {e.institution}")
    
    print(f"\n💼 Experiences ({len(cv.experiences)}):")
    for exp in cv.experiences:
        print(f"  [{exp.dates}] {exp.title}")
        if exp.company:
            print(f"          └─ {exp.company}")
        for t in exp.tasks:
            print(f"          • {t}")
        if exp.stack:
            print(f"          🔧 {', '.join(exp.stack)}")
    
    print(f"\n🔬 Projects ({len(cv.projects)}):")
    for proj in cv.projects:
        print(f"  [{proj.dates}] {proj.title}")
        for t in proj.tasks:
            print(f"          • {t}")
        if proj.stack:
            print(f"          🔧 {', '.join(proj.stack)}")
    
    print(f"\n💻 Technical Skills ({len(cv.tech_skills)}):")
    for ts in cv.tech_skills:
        print(f"  [{ts.category}] {ts.details}")
    
    print(f"\n🌍 Languages ({len(cv.languages)}):")
    for lang, level in cv.languages.items():
        print(f"  {lang}: {level}")
    
    print(f"\n{'='*60}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python parser.py <raw_text_file>")
        sys.exit(1)
    
    with open(sys.argv[1], "r") as f:
        text = f.read()
    
    cv = parse_cv(text)
    print_cv(cv)