import re
import sys
from dataclasses import dataclass, field
from typing import Optional


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


# ============================================================================
# Section header patterns — broadened to match many real-world CV formats
# ============================================================================

SECTION_HEADERS = {
    "profil": re.compile(
        r"^(?:profil|profile|r[ée]sum[ée](?:\s+ex[ée]cutif)?|resume|"
        r"à\s+propos|about|"
        r"pr[ée]sentation\s+g[ée]n[ée]rale|pr[ée]sentation|"
        r"synth[èe]se(?:\s+professionn\w*)?|"
        r"r[ée]sum[ée]\s+professionnel)$",
        re.IGNORECASE,
    ),
    "formation": re.compile(
        r"^(?:formation|formations|education|[ée]tudes|etudes|"
        r"dipl[ôo]mes?|diplomes?|parcours\s+acad[ée]mique|"
        r"formations?\s+acad[ée]miques?|cursus|"
        r"certifications?|formations?\s+professionn\w*|"
        r"formations?\s+et\s+certifications?)"
        r"(?:\s+[&et]+\s+certifications?)?$",
        re.IGNORECASE,
    ),
    "experiences": re.compile(
        r"^(?:(?:principales?\s+)?exp[ée]riences?\s+profes+ion\w*|"
        r"professional\s+experience|work\s+experience|"
        r"parcours\s+profes+ion\w*|exp[ée]riences?|"
        r"exp[ée]rience\s+d[ée]taill[ée]e|"
        r"exp[ée]riences?\s+d[ée]taill[ée]es?|"
        r"d[ée]tails?\s+des\s+exp[ée]riences?\s+profes+ion\w*|"
        r"d[ée]tails?\s+des\s+exp[ée]riences?|"
        r"exp[ée]rience\s+profes+ion\w+\s+d[ée]taill[ée]e|"
        r"missions?\s+et\s+projets?|"
        r"experiences?)$",
        re.IGNORECASE,
    ),
    "projets": re.compile(
        r"^(?:projets?\s+s[ée]lectionn[ée]s?|"
        r"projets?\s+(?:universitaires?|personnels?|professionnels?|acad[ée]miques?)|"
        r"projets?|projects?)$",
        re.IGNORECASE,
    ),
    "savoir_faire": re.compile(
        r"^(?:savoir[\s\-]faire)$",
        re.IGNORECASE,
    ),
    "competences": re.compile(
        r"^(?:comp[ée]tences?\s+techniques?|"
        r"comp[ée]tences?\s+fonctionnelles?|"
        r"comp[ée]tences?\s+techniques?\s+et\s+m[ée]thodologiques?|"
        r"comp[ée]tences?\s+(?:techniques?\s+et\s+)?m[ée]thodologiques?|"
        r"comp[ée]tences?\s+m[ée]tiers?|"
        r"comp[ée]tences?\s+cl[ée]s?|"
        r"comp[ée]tences?\s+informatiques?|"
        r"comp[ée]tences?\s+professionn\w*|"
        r"comp[ée]tences?\s+principales?|"
        r"technical\s+skills?|"
        r"comp[ée]tences?|skills?|"
        r"outils?\s+(?:et\s+)?technologies?|"
        r"domaines?\s+(?:de\s+)?comp[ée]tences?|"
        r"domaines?\s+d.intervention|"
        r"points?\s+forts?(?:\s+pour\s+.+)?|"
        r"synth[èe]se\s+des\s+comp[ée]tences?\s+fonctionnelles?|"
        r"domaine\s+de\s+comp[ée]tences?|"
        r"secteurs?\s+d.activit[ée]|"
        r"domaines?\s+d.expertise|"
        r"expertise|"
        r"soft\s*skills?\s*(?:&|et)\s*comp[ée]tences?\s+techniques?)$",
        re.IGNORECASE,
    ),
    "langues": re.compile(
        r"^(?:langues?|languages?|langues?\s+parl[ée]es?|langues?\s+[ée]trang[èe]res?)$",
        re.IGNORECASE,
    ),
    # Sections we want to skip / not parse as content
    "_contact": re.compile(
        r"^(?:contact|coordonn[ée]es?|informations?\s+personnelles?)$",
        re.IGNORECASE,
    ),
}


def _clean(line: str) -> str:
    return re.sub(r"\s+", " ", line.strip())


def _detect_section(line: str) -> Optional[str]:
    cleaned = _clean(line)
    if not cleaned:
        return None
    # Skip lines that are too long to be headers
    if len(cleaned) > 80:
        return None
    
    # IMPORTANT: "Projets :" with a trailing colon inside an experience is a 
    # sub-section header, not a new section. Only treat bare "Projets" (no colon)
    # as a section header.
    original_cleaned = cleaned
    
    # Strip trailing colon, period, or spaces (common in headers)
    cleaned = re.sub(r"[\s:\.]+$", "", cleaned)
    if not cleaned:
        return None
    
    # If the original had a trailing colon AND it matches "projets", skip it —
    # it's a sub-heading like "Projets :" within an experience block
    has_trailing_colon = re.search(r":\s*$", original_cleaned) is not None
    
    for key, pattern in SECTION_HEADERS.items():
        if pattern.match(cleaned):
            # "Projets :" with colon is a sub-section, not a section
            if key == "projets" and has_trailing_colon:
                return None
            # Skip private sections
            if key.startswith("_"):
                return key
            return key
    return None


def split_into_sections(text: str) -> dict[str, list[str]]:
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


# --- Helper patterns ---

# Month abbreviations (French + English + full French months)
_MONTHS_ABBREV = (
    r"(?:Jan|Fev|F[ée]v|Mar|Avr|Mai|Juin|Jul|Juil|Aou|Ao[uû]t|Sep|Oct|Nov|Dec|D[ée]c)"
    r"\w*\.?"
)
_MONTHS_FULL = (
    r"(?:Janvier|F[ée]vrier|Mars|Avril|Mai|Juin|Juillet|Ao[uû]t"
    r"|Septembre|Octobre|Novembre|D[ée]cembre)"
)
_MONTHS_ALL = rf"(?:{_MONTHS_ABBREV}|{_MONTHS_FULL})"

# Date piece: "Sep. 2024", "Septembre 2024", "2024", "01/2025", "09/2022"
_DATE_PIECE = rf"(?:{_MONTHS_ALL}\s*)?\d{{4}}|\d{{2}}/\d{{4}}"
# End date can also be "Present" or "Présent" or "Aujourd'hui" or "aujourd'hui" or "en cours" or "auj"
_DATE_END_PIECE = rf"{_DATE_PIECE}|[Pp]r[ée]sent|[Aa]ujourd.hui|[Ee]n\s+cours|[Aa]uj\.?"

# Matches FULL date ranges on one line
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

# A single date expression: "Month YEAR" or "MM/YYYY"
_DATE_EXPR = rf"(?:{_MONTHS_ALL}\s+\d{{4}}|\d{{2}}/\d{{4}})"
# End date expression: date or "Present", "Aujourd'hui", "en cours", "(En cours)", "ce jour"
_DATE_END_EXPR = rf"(?:{_DATE_EXPR}|\(?[Pp]r[ée]sent\)?|\(?[Aa]ujourd.hui\)?|\(?[Ee]n\s+cours\)?|\(?[Aa]uj\.?\)?|[Cc]e\s+jour)"

# "De MONTH YEAR à MONTH YEAR" — French format
# e.g. "De Mars 2022 à février 2026" or "De 08/2017 à 04/2018"
DE_A_PATTERN = re.compile(
    rf"^[Dd]e(?:puis)?\s+({_DATE_EXPR})\s+(?:[àa]|au)\s+({_DATE_END_EXPR})",
    re.IGNORECASE,
)

# "De MONTH YEAR à MONTH YEAR (duration)" — with optional parenthetical
DE_A_PAREN_PATTERN = re.compile(
    rf"^[Dd]e(?:puis)?\s+({_DATE_EXPR})\s+(?:[àa]|au)\s+({_DATE_END_EXPR})\s*(?:\(.+\))?\s*$",
    re.IGNORECASE,
)

# "Depuis MONTH YEAR" or "Depuis MM/YYYY" (alone on line or with trailing text)
DEPUIS_PATTERN = re.compile(
    rf"^[Dd]epuis\s+({_DATE_EXPR})\s*$",
    re.IGNORECASE,
)

# "COMPANY DE MONTH YEAR A MONTH YEAR" format (all caps)
DE_A_DATE_PATTERN = re.compile(
    rf"^(.+?)\s+DE\s+({_MONTHS_FULL})\s+(\d{{4}})\s+[AÀ]\s+({_MONTHS_FULL})\s*(\d{{4}})\s*$",
    re.IGNORECASE,
)

# "Month YEAR à Month YEAR" inline with company: "Natixis CIB – Analyste Mars 2023 à Mars 2026"
# Also: "COMPANY De/Depuis MM/YYYY – MM/YYYY" or "COMPANY Depuis MM/YYYY (En cours)"
INLINE_DATE_A_PATTERN = re.compile(
    rf"^(.+?)\s+(?:[Dd]e(?:puis)?\s+)?({_DATE_EXPR})\s+(?:[àa]|au|[-–—])\s+({_DATE_END_EXPR})\s*(?:\(.+\))?\s*$",
    re.IGNORECASE,
)

# "Text - Month à Month YEAR" — start date has no year (just month name)
# e.g. "Company - Title - Location - Janvier à Septembre 2024"
INLINE_MONTH_ONLY_PATTERN = re.compile(
    rf"^(.+?)\s+(?:[Dd]e\s+)?({_MONTHS_ALL})\s+(?:[àa]|au)\s+({_MONTHS_ALL}\s+\d{{4}}|{_DATE_END_EXPR})\s*$",
    re.IGNORECASE,
)

# "Month YEAR à Month YEAR [Company]" — dates at START, optional company after
DATE_A_START_PATTERN = re.compile(
    rf"^({_DATE_EXPR})\s+(?:[àa]|au|[-–—])\s+({_DATE_END_EXPR})\s*(.*)$",
    re.IGNORECASE,
)

# "Depuis MM/YYYY – MM/YYYY" — hybrid Depuis with date range
DEPUIS_RANGE_PATTERN = re.compile(
    rf"^[Dd]epuis\s+({_DATE_EXPR})\s*[-–—]\s*({_DATE_END_EXPR})\s*$",
    re.IGNORECASE,
)

# Two dates on separate lines: "03/2024" then "Test Lead 05/2025"
# or: "Depuis" then "06/2025"
DEPUIS_ALONE_PATTERN = re.compile(
    r"^[Dd]epuis\s*$",
    re.IGNORECASE,
)

# Matches bullet prefixes
BULLET_PATTERN = re.compile(r"^\s*[—\-•■▪▸◆➤●★>»→◼✓✔☑o]\s*")

# Matches stack/env lines WITH inline content
STACK_PATTERN = re.compile(
    r"(?i)^(?:stack|environnement\s+technique|technologies?\s+utilis[ée]es?|outils?)\s*:\s*(.+)",
)

# Context technique line (inline): "Contexte technique : ..."
CONTEXT_TECH_PATTERN = re.compile(
    r"(?i)^contexte\s+technique\s*:\s*(.+)",
)

# Outils & Technologies inline: "Outils & Technologies : ..."
OUTILS_TECH_PATTERN = re.compile(
    r"(?i)^outils?\s*(?:&|et)\s*technologies?\s*:\s*(.+)",
)

# --- INTM template patterns ---
INTM_COMPANY_PATTERN = re.compile(
    r"(?i)^entreprise\s+(.+?)(?:\s*dur[ée]e\s+(.+))?$",
)
INTM_POSTE_PATTERN = re.compile(
    r"(?i)^poste\s+(.+)$",
)
INTM_ROLE_PATTERN = re.compile(
    r"(?i)^r[oô]le\s*:\s*$",
)
INTM_ENV_PATTERN = re.compile(
    r"(?i)^(?:environnement\s+technique|stack\s+technique|technologies?)\s*:?\s*$",
)
INTM_PROJECT_PATTERN = re.compile(
    r"(?i)^(?:projet\s+(?:universitaire|personnel|professionnel|client)\s*\d*)\s*(.*)$",
)
INTM_TRAINING_PATTERN = re.compile(
    r"(?i)^formation\s*(\S.+)$",
)

# Sub-section headers within experiences (not section-level)
SUBSECTION_HEADERS = re.compile(
    r"(?i)^(?:contexte|missions?|r[ée]alisations?|activit[ée]s?|t[âa]ches?|responsabilit[ée]s?)\s*:?\s*$",
)


def _is_bullet(line: str) -> bool:
    return bool(BULLET_PATTERN.match(line))


def _strip_bullet(line: str) -> str:
    return BULLET_PATTERN.sub("", line).strip()


def _is_page_marker(line: str) -> bool:
    cleaned = _clean(line)
    # Page numbers: "1/2", "2/2", "Page 3" — but NOT "03/2024" (dates!)
    if re.match(r"^\d{1,2}/\d{1,2}$", cleaned):
        return True
    if re.match(r"(?i)^page\s+\d+", cleaned):
        return True
    if re.match(r"^\d{1,2}\s*/\s*\d{1,2}$", cleaned):
        return True
    # Standalone page number: "1", "2", "3" (only single digits alone on a line)
    if re.match(r"^\d{1}$", cleaned):
        return True
    # "Page : N/M" format
    if re.match(r"(?i)^page\s*:\s*\d+\s*/\s*\d+", cleaned):
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
    result = {"name": "", "headline": "", "contacts": [], "years_exp": ""}

    contact_pattern = re.compile(
        r"(?i)(@|[\+]\d|\d{2}\s\d{2}|linkedin|github|gitlab|§|ð|cid:|"
        r"\d{2}\.\d{2}\.\d{2}|\.com|\.fr)",
    )
    # Pattern for years of experience
    exp_pattern = re.compile(
        r"(?i)(\d+\s*(?:ans?|années?)\s*d.exp[ée]rience|"
        r"\+?\s*\d+\s*ans?\s*d.exp|"
        r"exp[ée]rience\s*:\s*\d+\s*ans?)",
    )
    # Pattern for address lines
    address_pattern = re.compile(
        r"(?i)^\d+\s+(?:rue|avenue|allée|boulevard|chemin|impasse|place|passage)",
    )
    # Pattern for age/personal info lines
    age_pattern = re.compile(
        r"(?i)^\d{2}\s*ans",
    )
    postal_pattern = re.compile(
        r"^\d{5}\s+",
    )
    # Pattern for nationality
    nationality_pattern = re.compile(
        r"(?i)^nationalit[ée]",
    )

    for line in lines:
        cleaned = _clean(line)
        if not cleaned or _is_page_marker(cleaned):
            continue

        # Skip contact/address/age lines
        if contact_pattern.search(cleaned):
            result["contacts"].append(cleaned)
            continue
        if address_pattern.match(cleaned):
            continue
        if age_pattern.match(cleaned):
            continue
        if postal_pattern.match(cleaned):
            continue
        if nationality_pattern.match(cleaned):
            continue

        # Check for years of experience
        exp_match = exp_pattern.search(cleaned)
        if exp_match:
            result["years_exp"] = cleaned
            continue

        # First substantial non-contact line = name
        if not result["name"]:
            # Skip very short lines that are likely icons or symbols
            if len(cleaned) < 3:
                continue
            result["name"] = cleaned
        elif not result["headline"]:
            # Second line = headline/title (if not too long)
            if len(cleaned.split()) <= 12:
                result["headline"] = cleaned
            # If it's longer, it might be part of the profile — stop header parsing
            else:
                break

    return result


# --- B2: Formation parser ---

def parse_formation(lines: list[str]) -> list[Education]:
    education = []
    undated_lines = []

    paren_date_range = re.compile(r"^(.+?)\s*\((\d{4})\s*[-–‑]\s*(\d{4})\)\s*$")
    paren_date_single = re.compile(r"^(.+?)\s*\((\d{4})\)\s*$")

    for line in lines:
        cleaned = _clean(line)
        if not cleaned or _is_page_marker(cleaned):
            continue

        stripped = _strip_bullet(cleaned) if _is_bullet(cleaned) else cleaned

        # Skip sub-headings
        if re.match(r"(?i)^(?:modules?\s*:|diplôme|diplome|mention|formation\s+acad[ée]mique|formations?\s+professionn\w*|certifications?)$", stripped):
            continue

        # Pattern 0: "YYYY/YYYY" or "YYYY/YY" or "YYYY/Y YYY" format at start
        # e.g. "2013/2014 - STERIA Formation HP ALM QC, QTP, ISTQB"
        # e.g. "2004/2 005 – U. de Versailles M2P..." (space in year from PDF)
        # First, clean up spaces within year numbers after slash
        stripped_nospace = re.sub(r"(\d{4}/\d)\s+(\d{2,3})", r"\1\2", stripped)
        slash_year = re.match(r"^(\d{4})/(\d{2,4})\s*[-–—]\s*(.+)$", stripped_nospace)
        if not slash_year:
            slash_year = re.match(r"^(\d{4})/(\d{2,4})\s+(.+)$", stripped_nospace)
        if slash_year:
            year1 = slash_year.group(1)
            year2_raw = slash_year.group(2)
            if len(year2_raw) == 2:
                year2 = year1[:2] + year2_raw
            else:
                year2 = year2_raw
            years = f"{year1}–{year2}"
            rest = slash_year.group(3).strip()
            rest = re.sub(r"^[-–—]\s*", "", rest).strip()
            parts = re.split(r",\s+|\s+[—–]\s+", rest, maxsplit=1)
            degree = parts[0].strip()
            institution = parts[1].strip() if len(parts) > 1 else ""
            education.append(Education(years=years, degree=degree, institution=institution))
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

        # Pattern 1b: Date range at END of line
        end_date_match = DATE_RANGE_END_PATTERN.match(stripped)
        if end_date_match:
            text_part = end_date_match.group(1).strip()
            years = end_date_match.group(2).strip()
            parts = re.split(r",\s+|\s+[—–]\s+", text_part, maxsplit=1)
            degree = parts[0].strip()
            institution = parts[1].strip() if len(parts) > 1 else ""
            education.append(Education(years=years, degree=degree, institution=institution))
            continue

        # Pattern 1c: Date range in parentheses
        paren_range_match = paren_date_range.match(stripped)
        if paren_range_match:
            text_part = paren_range_match.group(1).strip()
            years = f"{paren_range_match.group(2)}–{paren_range_match.group(3)}"
            parts = re.split(r",\s+|\s+[—–]\s+", text_part, maxsplit=1)
            degree = parts[0].strip()
            institution = parts[1].strip() if len(parts) > 1 else ""
            education.append(Education(years=years, degree=degree, institution=institution))
            continue

        # Pattern 1d: Single year in parentheses
        paren_single_match = paren_date_single.match(stripped)
        if paren_single_match:
            text_part = paren_single_match.group(1).strip()
            years = paren_single_match.group(2)
            education.append(Education(years=years, degree=text_part, institution=""))
            continue

        # Pattern 1e: "YYYY-YYYY : Degree" or "YYYY – YYYY : Degree"
        colon_date = re.match(r"^(\d{4})\s*[-–]\s*(\d{4})\s*:?\s+(.+)$", stripped)
        if colon_date:
            years = f"{colon_date.group(1)}–{colon_date.group(2)}"
            rest = colon_date.group(3).strip()
            parts = re.split(r",\s+|\s+[—–]\s+", rest, maxsplit=1)
            degree = parts[0].strip()
            institution = parts[1].strip() if len(parts) > 1 else ""
            education.append(Education(years=years, degree=degree, institution=institution))
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

        # Pattern 4: Fallback — collect undated lines
        if stripped and len(stripped) > 3:
            undated_lines.append(stripped)

    # If we found NO dated entries, use all undated lines
    if not education and undated_lines:
        for line in undated_lines:
            education.append(Education(years="", degree=line, institution=""))

    return education


# --- B3: Experience parser ---

def parse_experiences(lines: list[str]) -> list[Experience]:
    experiences = []
    current: Optional[Experience] = None
    mode = "tasks"  # tasks | stack

    i = 0
    while i < len(lines):
        cleaned = _clean(lines[i])

        if not cleaned or _is_page_marker(cleaned):
            i += 1
            continue

        # --- "COMPANY Depuis DATE (status)" e.g. "UP COOP Depuis 07/2025 (En cours)" ---
        company_depuis = re.match(
            rf"^(.+?)\s+[Dd]epuis\s+({_DATE_EXPR})\s*(?:\(.+\))?\s*$",
            cleaned, re.IGNORECASE
        )
        if company_depuis:
            if current:
                experiences.append(current)
            company = company_depuis.group(1).strip()
            dates = f"Depuis {company_depuis.group(2)}"
            # Look for title on next line
            title = ""
            j = i + 1
            while j < len(lines):
                next_cleaned = _clean(lines[j])
                if next_cleaned and not _is_bullet(next_cleaned) and not _is_page_marker(next_cleaned):
                    if not SUBSECTION_HEADERS.match(next_cleaned) and not re.match(r"(?i)^r[oô]le\s*:", next_cleaned):
                        title = next_cleaned
                        j += 1
                    break
                elif next_cleaned:
                    break
                j += 1
            current = Experience(dates=dates, title=title, company=company)
            mode = "tasks"
            i = j
            continue

        # --- "Depuis DATE – DATE" hybrid e.g. "Depuis 07/2023 – 06/2024" ---
        depuis_range = re.match(
            rf"^[Dd]epuis\s+({_DATE_EXPR})\s*[-–—]\s*({_DATE_EXPR})\s*$",
            cleaned, re.IGNORECASE
        )
        if depuis_range:
            if current:
                experiences.append(current)
            dates = f"{depuis_range.group(1)} – {depuis_range.group(2)}"
            # Look for company/title on next line
            title, company = "", ""
            j = i + 1
            while j < len(lines):
                next_cleaned = _clean(lines[j])
                if next_cleaned and not _is_bullet(next_cleaned) and not _is_page_marker(next_cleaned):
                    if not SUBSECTION_HEADERS.match(next_cleaned):
                        parts = next_cleaned.split(",", 1)
                        title = parts[0].strip()
                        company = parts[1].strip() if len(parts) > 1 else ""
                        j += 1
                    break
                elif next_cleaned:
                    break
                j += 1
            current = Experience(dates=dates, title=title, company=company)
            mode = "tasks"
            i = j
            continue

        # --- "Depuis" alone on a line, next line has MM/YYYY ---
        if DEPUIS_ALONE_PATTERN.match(cleaned):
            # Look ahead: could be "Depuis\nMM/YYYY" or "Depuis\nTitle\nMM/YYYY"
            j = i + 1
            collected_non_date = []
            found_date = None
            while j < len(lines) and j <= i + 4:  # Look up to 4 lines ahead
                next_cleaned = _clean(lines[j])
                if not next_cleaned:
                    j += 1
                    continue
                # Check if it's a date like "06/2025" or "Février 2022"
                date_match = re.match(rf"^({_DATE_PIECE})$", next_cleaned, re.IGNORECASE)
                if date_match:
                    found_date = date_match.group(1)
                    j += 1
                    break
                # Check for "Title MM/YYYY" pattern (e.g. "Test Lead 05/2025")
                title_date = re.match(rf"^(.+?)\s+(\d{{2}}/\d{{4}})\s*$", next_cleaned)
                if title_date:
                    collected_non_date.append(title_date.group(1).strip())
                    found_date = title_date.group(2)
                    j += 1
                    break
                # Check for "Depuis MONTH YEAR COMPANY" (e.g. "Depuis Février 2022 HSBC")
                depuis_with_co = re.match(rf"^({_DATE_EXPR})\s+(.+)$", next_cleaned, re.IGNORECASE)
                if depuis_with_co:
                    found_date = depuis_with_co.group(1)
                    collected_non_date.append(depuis_with_co.group(2).strip())
                    j += 1
                    break
                # Otherwise it's a title/company line between Depuis and the date
                collected_non_date.append(next_cleaned)
                j += 1

            if found_date:
                if current:
                    experiences.append(current)
                dates = f"Depuis {found_date}"
                title = collected_non_date[0] if collected_non_date else ""
                company = collected_non_date[1] if len(collected_non_date) > 1 else ""
                # Look for more title info after the date if we have none
                if not title:
                    while j < len(lines):
                        title_cleaned = _clean(lines[j])
                        if title_cleaned and not _is_bullet(title_cleaned) and not _is_page_marker(title_cleaned):
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
            # No date found — skip "Depuis" as stray
            i += 1
            continue

        # --- "Depuis MONTH YEAR" alone or "Depuis MONTH YEAR COMPANY" ---
        depuis_match = DEPUIS_PATTERN.match(cleaned)
        if not depuis_match:
            # Try: "Depuis MONTH YEAR COMPANY" (company appended)
            depuis_with_company = re.match(
                rf"^[Dd]epuis\s+({_DATE_EXPR}|\d{{2}}/\d{{4}})\s+(.+)$",
                cleaned, re.IGNORECASE
            )
            # Try: "Depuis COMPANY" (no date — date on next line)
            depuis_company_only = None
            if not depuis_with_company:
                depuis_company_only = re.match(
                    r"^[Dd]epuis\s+(.+)$", cleaned, re.IGNORECASE
                )
            if depuis_with_company:
                if current:
                    experiences.append(current)
                dates = f"Depuis {depuis_with_company.group(1)}"
                rest = depuis_with_company.group(2).strip()
                title = ""
                company = rest
                # Look for title/role on next line
                j = i + 1
                while j < len(lines):
                    next_cleaned = _clean(lines[j])
                    if next_cleaned and not _is_bullet(next_cleaned) and not _is_page_marker(next_cleaned):
                        if not SUBSECTION_HEADERS.match(next_cleaned) and not re.match(r"(?i)^r[oô]le\s*:", next_cleaned):
                            # Check if next line is "Month YEAR Title"
                            month_title = re.match(rf"^({_DATE_EXPR})\s+(.+)$", next_cleaned, re.IGNORECASE)
                            if month_title:
                                # This is the end date + title
                                title = month_title.group(2).strip()
                            else:
                                title = next_cleaned
                            j += 1
                        break
                    elif next_cleaned:
                        break
                    j += 1
                current = Experience(dates=dates, title=title, company=company)
                mode = "tasks"
                i = j
                continue
            elif depuis_company_only:
                # "Depuis COMPANY" — look for date on next line
                company_text = depuis_company_only.group(1).strip()
                j = i + 1
                while j < len(lines):
                    next_cleaned = _clean(lines[j])
                    if next_cleaned:
                        # Check for "Month YEAR Title" on next line
                        month_title = re.match(rf"^({_DATE_EXPR})\s+(.+)$", next_cleaned, re.IGNORECASE)
                        month_only = re.match(rf"^({_DATE_EXPR})\s*$", next_cleaned, re.IGNORECASE)
                        date_only = re.match(rf"^(\d{{2}}/\d{{4}})\s*$", next_cleaned, re.IGNORECASE)
                        if month_title:
                            if current:
                                experiences.append(current)
                            dates = f"Depuis {month_title.group(1)}"
                            title = month_title.group(2).strip()
                            current = Experience(dates=dates, title=title, company=company_text)
                            mode = "tasks"
                            i = j + 1
                            break
                        elif month_only or date_only:
                            if current:
                                experiences.append(current)
                            date_str = (month_only or date_only).group(1)
                            dates = f"Depuis {date_str}"
                            current = Experience(dates=dates, title="", company=company_text)
                            mode = "tasks"
                            i = j + 1
                            break
                        else:
                            break
                    j += 1
                else:
                    i += 1
                continue
        if depuis_match:
            if current:
                experiences.append(current)
            dates = f"Depuis {depuis_match.group(1)}"
            # Look for title on next line
            title, company = "", ""
            j = i + 1
            while j < len(lines):
                next_cleaned = _clean(lines[j])
                if next_cleaned and not _is_bullet(next_cleaned) and not _is_page_marker(next_cleaned):
                    if not SUBSECTION_HEADERS.match(next_cleaned):
                        parts = next_cleaned.split(",", 1)
                        title = parts[0].strip()
                        company = parts[1].strip() if len(parts) > 1 else ""
                        j += 1
                    break
                elif next_cleaned:
                    break
                j += 1
            current = Experience(dates=dates, title=title, company=company)
            mode = "tasks"
            i = j
            continue

        # --- "De MONTH YEAR à MONTH YEAR" ---
        de_a_match = DE_A_PATTERN.match(cleaned)
        # Also try: "De MONTH YEAR à MONTH COMPANY\nYEAR" (end year on next line)
        if not de_a_match:
            # Pattern: "De Décembre 2020 à Janvier SOCIETE GENERAL - CFT"
            # where "2022" is on the next line
            split_de_a = re.match(
                rf"^[Dd]e(?:puis)?\s+({_DATE_EXPR})\s+(?:[àa]|au)\s+({_MONTHS_ALL})\s+(.+)$",
                cleaned, re.IGNORECASE
            )
            if split_de_a and i + 1 < len(lines):
                next_cleaned = _clean(lines[i + 1])
                year_match = re.match(r"^(\d{4})\s*$", next_cleaned)
                if year_match:
                    if current:
                        experiences.append(current)
                    start = split_de_a.group(1)
                    end_month = split_de_a.group(2)
                    end_year = year_match.group(1)
                    company_text = split_de_a.group(3).strip()
                    dates = f"{start} – {end_month} {end_year}"
                    # company_text might have "[14 mois]" on following lines too
                    title, company = "", company_text
                    j = i + 2
                    # Skip duration lines like "[14 mois]"
                    while j < len(lines):
                        jcleaned = _clean(lines[j])
                        if jcleaned and re.match(r"^\[?\d+\s*(?:mois|ans?)\]?\s*$", jcleaned, re.IGNORECASE):
                            j += 1
                            continue
                        if jcleaned and not _is_bullet(jcleaned) and not _is_page_marker(jcleaned):
                            if not SUBSECTION_HEADERS.match(jcleaned) and not re.match(r"(?i)^r[oô]le\s*:", jcleaned):
                                title = jcleaned
                                j += 1
                            break
                        elif jcleaned:
                            break
                        j += 1
                    current = Experience(dates=dates, title=title, company=company)
                    mode = "tasks"
                    i = j
                    continue
        if de_a_match:
            if current:
                experiences.append(current)
            dates = f"{de_a_match.group(1)} – {de_a_match.group(2)}"
            # Rest of line after the date pattern might have content
            rest = cleaned[de_a_match.end():].strip()
            # Remove optional parenthetical duration like "(4 ans)"
            rest = re.sub(r"\s*\(\d+\s*(?:ans?|mois)\)\s*$", "", rest).strip()
            title, company = "", ""
            if rest:
                parts = rest.split(",", 1)
                title = parts[0].strip()
                company = parts[1].strip() if len(parts) > 1 else ""
            else:
                # Look for title on next line
                j = i + 1
                while j < len(lines):
                    next_cleaned = _clean(lines[j])
                    if next_cleaned and not _is_bullet(next_cleaned) and not _is_page_marker(next_cleaned):
                        if not SUBSECTION_HEADERS.match(next_cleaned):
                            parts = next_cleaned.split(",", 1)
                            title = parts[0].strip()
                            company = parts[1].strip() if len(parts) > 1 else ""
                            j += 1
                        break
                    elif next_cleaned:
                        break
                    j += 1
                i = j
                current = Experience(dates=dates, title=title, company=company)
                mode = "tasks"
                continue
            current = Experience(dates=dates, title=title, company=company)
            mode = "tasks"
            i += 1
            continue

        # --- "Company/Title Month YEAR à Month YEAR" inline ---
        inline_match = INLINE_DATE_A_PATTERN.match(cleaned)
        if inline_match:
            if current:
                experiences.append(current)
            text_part = inline_match.group(1).strip()
            dates = f"{inline_match.group(2)} – {inline_match.group(3)}"
            # Strip trailing "De" or "de" (French date prefix leaked into text)
            text_part = re.sub(r"\s+[Dd]e\s*$", "", text_part).strip()
            # Try to split text_part into company and title
            # Common patterns: "Company – Title" or "Company - Title"
            dash_split = re.split(r"\s+[–—\-]\s+", text_part, maxsplit=1)
            if len(dash_split) == 2:
                company = dash_split[0].strip()
                title = dash_split[1].strip()
            else:
                title = text_part
                company = ""
            current = Experience(dates=dates, title=title, company=company)
            mode = "tasks"
            i += 1
            continue

        # --- "Text - Month à Month YEAR" (start month without year) ---
        month_only_match = INLINE_MONTH_ONLY_PATTERN.match(cleaned)
        if month_only_match:
            if current:
                experiences.append(current)
            text_part = month_only_match.group(1).strip()
            start_month = month_only_match.group(2)
            end_part = month_only_match.group(3)
            # Extract the year from the end date and apply to start month
            year_match = re.search(r"\d{4}", end_part)
            if year_match:
                dates = f"{start_month} {year_match.group()} – {end_part}"
            else:
                dates = f"{start_month} – {end_part}"
            text_part = re.sub(r"\s+[Dd]e\s*$", "", text_part).strip()
            # Split text_part by dashes: "Company - Title - Location"
            dash_parts = re.split(r"\s+-\s+", text_part)
            if len(dash_parts) >= 2:
                company = dash_parts[0].strip()
                title = dash_parts[1].strip()
            else:
                title = text_part
                company = ""
            current = Experience(dates=dates, title=title, company=company)
            mode = "tasks"
            i += 1
            continue

        # --- "Month YEAR à Month YEAR [Company]" — dates at start ---
        date_start_match = DATE_A_START_PATTERN.match(cleaned)
        if date_start_match:
            if current:
                experiences.append(current)
            dates = f"{date_start_match.group(1)} – {date_start_match.group(2)}"
            rest = date_start_match.group(3).strip() if date_start_match.group(3) else ""
            title, company = "", ""
            if rest:
                company = rest
            else:
                # Look for company/title on next line
                j = i + 1
                while j < len(lines):
                    next_cleaned = _clean(lines[j])
                    if next_cleaned and not _is_bullet(next_cleaned) and not _is_page_marker(next_cleaned):
                        if not SUBSECTION_HEADERS.match(next_cleaned) and not re.match(r"(?i)^r[oô]le\s*:", next_cleaned):
                            company = next_cleaned
                            j += 1
                        break
                    elif next_cleaned:
                        break
                    j += 1
                i = j
                current = Experience(dates=dates, title=title, company=company)
                mode = "tasks"
                continue
            current = Experience(dates=dates, title=title, company=company)
            mode = "tasks"
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

        # --- Format C: date range at END of line ---
        end_date_match = DATE_RANGE_END_PATTERN.match(cleaned)
        if end_date_match:
            if current:
                experiences.append(current)
            text_part = end_date_match.group(1).strip()
            dates = end_date_match.group(2).strip()
            title, company = "", ""
            
            # Check if text_part is a location (e.g. "Nanterre, France |")
            # If so, the real title/company is on the PREVIOUS line
            text_cleaned = re.sub(r"\s*\|\s*$", "", text_part).strip()
            is_location = bool(re.match(
                r"(?i)^[\w\s\-]+,\s*(?:France|Paris|Lyon|Maroc|Tunisie|Belgique|"
                r"UK|Écosse|Espagne|Allemagne|Inde|Lettonie|Liban|Suisse)\s*$",
                text_cleaned
            ))
            
            if is_location and i > 0:
                # Look at previous line for "Title | Company" or "Title – Company"
                prev = _clean(lines[i - 1]) if i > 0 else ""
                if prev and "|" in prev:
                    parts = prev.split("|", 1)
                    title = parts[0].strip()
                    company = parts[1].strip() if len(parts) > 1 else ""
                elif prev:
                    dash_split = re.split(r"\s+[–—\-]\s+", prev, maxsplit=1)
                    if len(dash_split) == 2:
                        title = dash_split[0].strip()
                        company = dash_split[1].strip()
                    else:
                        title = prev
                # Remove the previous line from the last experience's tasks
                # (it was likely appended as a task of the previous experience)
                if experiences and experiences[-1].tasks:
                    last_task = experiences[-1].tasks[-1]
                    if prev and (last_task == prev or last_task.strip() == prev.strip()):
                        experiences[-1].tasks.pop()
            elif text_part:
                # Normal handling: split text_part
                text_part_clean = re.sub(r"\s*\|\s*$", "", text_part).strip()
                dash_split = re.split(r"\s+[–—]\s+", text_part_clean, maxsplit=1)
                if len(dash_split) == 2:
                    company = dash_split[0].strip()
                    title = dash_split[1].strip()
                elif "|" in text_part_clean:
                    parts = text_part_clean.split("|", 1)
                    title = parts[0].strip()
                    company = parts[1].strip() if len(parts) > 1 else ""
                else:
                    parts = text_part_clean.split(",", 1)
                    title = parts[0].strip()
                    company = parts[1].strip() if len(parts) > 1 else ""
            current = Experience(dates=dates, title=title, company=company)
            mode = "tasks"
            i += 1
            continue

        # --- Format D: "COMPANY DE MONTH YEAR A MONTH YEAR" ---
        de_a_company = DE_A_DATE_PATTERN.match(cleaned)
        if de_a_company:
            if current:
                experiences.append(current)
            company = de_a_company.group(1).strip()
            dates = f"{de_a_company.group(2)} {de_a_company.group(3)} – {de_a_company.group(4)} {de_a_company.group(5)}"
            title = ""
            j = i + 1
            while j < len(lines):
                next_cleaned = _clean(lines[j])
                if next_cleaned and not _is_page_marker(next_cleaned):
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

        # --- Format: Multi-line date "MM/YYYY\n[Title [MM/YYYY]]\n[MM/YYYY]" ---
        # Handles: "03/2024\nTest Lead 05/2025" (title+end_date on same line)
        #          "10/2021\nTest Lead\n01/2024" (title then end_date on separate lines)
        #          "04/2020\nChef de Projet Test\n09/2021" (same pattern)
        two_line_start = re.match(r"^(\d{2}/\d{4})\s*$", cleaned)
        if two_line_start:
            start_date = two_line_start.group(1)
            j = i + 1
            # Collect non-empty lines ahead (up to 3)
            ahead = []
            while j < len(lines) and len(ahead) < 3:
                next_cleaned = _clean(lines[j])
                if next_cleaned and not _is_page_marker(next_cleaned):
                    ahead.append((j, next_cleaned))
                j += 1
                if next_cleaned:
                    break
                # skip blank lines

            if ahead:
                first_j, first_text = ahead[0]
                # Case 1: "Title MM/YYYY" on same line
                title_date = re.match(rf"^(.+?)\s+(\d{{2}}/\d{{4}})\s*$", first_text)
                if title_date:
                    if current:
                        experiences.append(current)
                    title = title_date.group(1).strip()
                    end_date = title_date.group(2)
                    dates = f"{start_date} – {end_date}"
                    current = Experience(dates=dates, title=title, company="")
                    mode = "tasks"
                    i = first_j + 1
                    continue

                # Case 2: just "MM/YYYY" (end date immediately)
                just_end = re.match(r"^(\d{2}/\d{4})\s*$", first_text)
                if just_end:
                    if current:
                        experiences.append(current)
                    end_date = just_end.group(1)
                    dates = f"{start_date} – {end_date}"
                    # Title on next line
                    title, company = "", ""
                    k = first_j + 1
                    while k < len(lines):
                        tk = _clean(lines[k])
                        if tk and not _is_bullet(tk) and not _is_page_marker(tk):
                            parts = tk.split(",", 1)
                            title = parts[0].strip()
                            company = parts[1].strip() if len(parts) > 1 else ""
                            k += 1
                            break
                        elif tk:
                            break
                        k += 1
                    current = Experience(dates=dates, title=title, company=company)
                    mode = "tasks"
                    i = k
                    continue

                # Case 3: Title on first line, check for end date on second line
                # Look at next non-empty line after the title
                k = first_j + 1
                while k < len(lines):
                    ktext = _clean(lines[k])
                    if ktext:
                        break
                    k += 1
                if k < len(lines):
                    ktext = _clean(lines[k])
                    end_match = re.match(r"^(\d{2}/\d{4})\s*$", ktext)
                    # Also check "Title MM/YYYY" on the second line
                    title_date2 = re.match(rf"^(.+?)\s+(\d{{2}}/\d{{4}})\s*$", ktext)
                    if end_match:
                        # Pattern: start_date\nTitle\nend_date
                        if current:
                            experiences.append(current)
                        end_date = end_match.group(1)
                        dates = f"{start_date} – {end_date}"
                        current = Experience(dates=dates, title=first_text, company="")
                        mode = "tasks"
                        i = k + 1
                        continue
                    elif title_date2:
                        # Pattern: start_date\nCompany\nTitle end_date  
                        if current:
                            experiences.append(current)
                        title = title_date2.group(1).strip()
                        end_date = title_date2.group(2)
                        dates = f"{start_date} – {end_date}"
                        current = Experience(dates=dates, title=title, company=first_text)
                        mode = "tasks"
                        i = k + 1
                        continue

                # Fallback: start_date alone, next line is title
                if not _is_bullet(first_text):
                    if current:
                        experiences.append(current)
                    dates = f"Depuis {start_date}"
                    current = Experience(dates=dates, title=first_text, company="")
                    mode = "tasks"
                    i = first_j + 1
                    continue
            i += 1
            continue

        # --- Format: "Month YEAR COMPANY\nMonth YEAR TITLE" (date+company then date+title) ---
        # e.g. "Novembre 2021 CNP ASSURANCE\nMars 2023 Tech lead COBOL/MVS"
        # ONLY match if next non-empty line also starts with Month YEAR
        month_year_company = re.match(
            rf"^({_DATE_EXPR})\s+(.+)$", cleaned, re.IGNORECASE
        )
        if month_year_company:
            start_date = month_year_company.group(1)
            rest_text = month_year_company.group(2).strip()
            # Peek at next non-empty line
            j = i + 1
            confirmed = False
            while j < len(lines):
                next_cleaned = _clean(lines[j])
                if next_cleaned:
                    next_month_text = re.match(
                        rf"^({_DATE_EXPR})\s+(.+)$", next_cleaned, re.IGNORECASE
                    )
                    next_month_only = re.match(
                        rf"^({_DATE_EXPR})\s*$", next_cleaned, re.IGNORECASE
                    )
                    if next_month_text:
                        if current:
                            experiences.append(current)
                        end_date = next_month_text.group(1)
                        dates = f"{start_date} – {end_date}"
                        company = rest_text
                        title = next_month_text.group(2).strip()
                        current = Experience(dates=dates, title=title, company=company)
                        mode = "tasks"
                        i = j + 1
                        confirmed = True
                    elif next_month_only:
                        if current:
                            experiences.append(current)
                        end_date = next_month_only.group(1)
                        dates = f"{start_date} – {end_date}"
                        company = rest_text
                        current = Experience(dates=dates, title="", company=company)
                        mode = "tasks"
                        i = j + 1
                        confirmed = True
                    break
                j += 1
            if confirmed:
                continue
            # Not confirmed — fall through to other handlers (don't consume this line)

        # --- Format: "Month YEAR\nMonth YEAR" split date ---
        full_month_alone = re.match(rf"^({_DATE_EXPR})\s*$", cleaned, re.IGNORECASE)
        if full_month_alone:
            start_date = full_month_alone.group(1)
            j = i + 1
            found_end = False
            while j < len(lines):
                next_cleaned = _clean(lines[j])
                if next_cleaned:
                    end_match = re.match(rf"^({_DATE_EXPR})\s*$", next_cleaned, re.IGNORECASE)
                    if end_match:
                        # Two dates = date range, look for title/company after
                        end_date = end_match.group(1)
                        dates = f"{start_date} – {end_date}"
                        title, company = "", ""
                        k = j + 1
                        while k < len(lines):
                            title_cleaned = _clean(lines[k])
                            if title_cleaned and not _is_bullet(title_cleaned) and not _is_page_marker(title_cleaned):
                                if not SUBSECTION_HEADERS.match(title_cleaned):
                                    parts = title_cleaned.split(",", 1)
                                    title = parts[0].strip()
                                    company = parts[1].strip() if len(parts) > 1 else ""
                                    k += 1
                                break
                            elif title_cleaned:
                                break
                            k += 1
                        if current:
                            experiences.append(current)
                        current = Experience(dates=dates, title=title, company=company)
                        mode = "tasks"
                        i = k
                        found_end = True
                        break
                    else:
                        # Not a date — this month+year is the start, next line is company/title
                        dates = f"Depuis {start_date}"
                        parts = next_cleaned.split(",", 1)
                        title = parts[0].strip()
                        company = parts[1].strip() if len(parts) > 1 else ""
                        if current:
                            experiences.append(current)
                        current = Experience(dates=dates, title=title, company=company)
                        mode = "tasks"
                        i = j + 1
                        found_end = True
                        break
                j += 1
            if found_end:
                continue
            # Else fall through
            i += 1
            continue

        # --- Format: PARTIAL date (split across lines) ---
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
            mode = "scan"
            i += 1
            continue

        # --- Format B: INTM "Poste X" ---
        if current:
            poste_match = INTM_POSTE_PATTERN.match(cleaned)
            if poste_match:
                current.title = poste_match.group(1).strip()
                i += 1
                continue

        # --- Sub-section headers (ROLE, Contexte, Missions, etc.) ---
        if current and SUBSECTION_HEADERS.match(cleaned):
            mode = "tasks"
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

        # --- Inline stack patterns ---
        stack_match = STACK_PATTERN.match(cleaned) or STACK_PATTERN.match(cleaned_no_bullet)
        if stack_match and current:
            current.stack.append(stack_match.group(1).strip())
            mode = "stack"
            i += 1
            continue

        # --- "Contexte technique : ..." inline ---
        ctx_match = CONTEXT_TECH_PATTERN.match(cleaned) or CONTEXT_TECH_PATTERN.match(cleaned_no_bullet)
        if ctx_match and current:
            current.stack.append(ctx_match.group(1).strip())
            mode = "stack"
            i += 1
            continue

        # --- "Outils & Technologies : ..." inline ---
        outils_match = OUTILS_TECH_PATTERN.match(cleaned) or OUTILS_TECH_PATTERN.match(cleaned_no_bullet)
        if outils_match and current:
            current.stack.append(outils_match.group(1).strip())
            mode = "stack"
            i += 1
            continue

        # --- Content line (bullet or plain text) ---
        if current:
            item = _strip_bullet(cleaned) if _is_bullet(cleaned) else cleaned
            if item:
                # IMPORTANT: Before appending as a task, check if this line
                # is actually the start of a NEW experience (inline date pattern
                # that wasn't caught by earlier handlers)
                if mode == "tasks" and not _is_bullet(cleaned):
                    # Check for "Company Month YEAR à Month YEAR" pattern
                    inline_check = INLINE_DATE_A_PATTERN.match(item)
                    if inline_check:
                        experiences.append(current)
                        text_part = inline_check.group(1).strip()
                        text_part = re.sub(r"\s+[Dd]e\s*$", "", text_part).strip()
                        dates = f"{inline_check.group(2)} – {inline_check.group(3)}"
                        dash_split = re.split(r"\s+[–—\-]\s+", text_part, maxsplit=1)
                        if len(dash_split) == 2:
                            company = dash_split[0].strip()
                            title = dash_split[1].strip()
                        else:
                            title = text_part
                            company = ""
                        current = Experience(dates=dates, title=title, company=company)
                        mode = "tasks"
                        i += 1
                        continue
                    # Check for "Month YEAR à Month YEAR" at start of non-bullet line
                    de_a_inline = DE_A_PATTERN.match(item)
                    if de_a_inline:
                        experiences.append(current)
                        dates = f"{de_a_inline.group(1)} – {de_a_inline.group(2)}"
                        rest = item[de_a_inline.end():].strip()
                        rest = re.sub(r"\s*\(\d+\s*(?:ans?|mois)\)\s*$", "", rest).strip()
                        title, company = "", ""
                        if rest:
                            parts = rest.split(",", 1)
                            title = parts[0].strip()
                            company = parts[1].strip() if len(parts) > 1 else ""
                        current = Experience(dates=dates, title=title, company=company)
                        mode = "tasks"
                        i += 1
                        continue
                    # Check for "Month YEAR à Month YEAR [Company]" — dates first
                    date_start_check = DATE_A_START_PATTERN.match(item)
                    if date_start_check:
                        experiences.append(current)
                        dates = f"{date_start_check.group(1)} – {date_start_check.group(2)}"
                        rest = date_start_check.group(3).strip() if date_start_check.group(3) else ""
                        current = Experience(dates=dates, title="", company=rest)
                        mode = "tasks"
                        i += 1
                        continue

                if mode == "stack":
                    current.stack.append(item)
                elif mode in ("tasks", "scan"):
                    if mode == "scan" and not current.title:
                        current.title = item
                    else:
                        current.tasks.append(item)
                    mode = "tasks"
        else:
            # No current experience — try to start one from freeform line
            pass

        i += 1

    if current:
        experiences.append(current)

    return experiences


# --- B4: Projects parser ---

def parse_projects(lines: list[str]) -> list[Experience]:
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

        if _is_bullet(cleaned):
            item = _strip_bullet(cleaned)
            if item:
                current.tasks.append(item)
            continue

        if current.tasks:
            current.tasks[-1] += " " + cleaned
        else:
            current.tasks.append(cleaned)

    if current:
        projects.append(current)

    return projects


# --- B5: Technical skills parser ---

def parse_tech_skills(lines: list[str]) -> list[TechSkill]:
    skills = []

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
        "méthode de réalisation de projet", "méthodologie de conception",
        "outils de tests", "outils de business intelligence",
        "logiciel de data mining",
        "outils", "tools",
        "os", "système", "systeme", "systèmes",
        "protocoles", "protocols",
        "soft skills",
        "secteur", "secteurs",
    ]

    for line in lines:
        cleaned = _clean(line)
        if not cleaned or _is_page_marker(cleaned):
            continue

        # Strip bullets
        stripped = _strip_bullet(cleaned) if _is_bullet(cleaned) else cleaned

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
            colon_match = re.match(r"^([^:]{2,40})\s*:\s+(.+)$", stripped)
            if colon_match:
                skills.append(TechSkill(
                    category=colon_match.group(1).strip(),
                    details=colon_match.group(2).strip(),
                ))
                matched = True

        # Pattern 3: Multi-space separated (3+ spaces)
        if not matched:
            parts = re.split(r"\s{3,}", stripped, maxsplit=1)
            if len(parts) == 2 and len(parts[0].split()) <= 5:
                skills.append(TechSkill(
                    category=parts[0].strip(),
                    details=parts[1].strip(),
                ))
                matched = True

        # Pattern 4: Known category keyword at start
        if not matched:
            lower = stripped.lower()
            for keyword in KNOWN_CATEGORIES:
                if lower.startswith(keyword):
                    rest = stripped[len(keyword):].strip()
                    if rest:
                        category = stripped[:len(keyword)].strip()
                        skills.append(TechSkill(category=category, details=rest))
                        matched = True
                        break

        # Fallback: append to last skill's details or create uncategorized
        if not matched:
            if skills:
                skills[-1].details += ", " + stripped
            else:
                skills.append(TechSkill(category="", details=stripped))

    return skills


# --- B6: Languages parser ---

def parse_languages(lines: list[str]) -> dict[str, str]:
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
        colon_match = re.match(r"^([\w\sé]+?)\s*:\s+(.+)$", cleaned)
        if colon_match:
            lang = colon_match.group(1).strip()
            level = colon_match.group(2).strip()
            # Avoid matching non-language lines
            if len(lang.split()) <= 3 and len(lang) < 30:
                languages[lang] = level
            continue

        # "Français Courant"
        words = cleaned.split(None, 1)
        if len(words) == 2 and len(words[0]) < 20:
            languages[words[0]] = words[1]

    return languages


def _parse_intm_blocks(lines: list[str]) -> list[Experience]:
    experiences = []
    current: Optional[Experience] = None
    mode = "scan"

    for line in lines:
        cleaned = _clean(line)
        if not cleaned or _is_page_marker(cleaned):
            continue

        if INTM_ROLE_PATTERN.match(cleaned):
            mode = "tasks"
            continue

        if INTM_ENV_PATTERN.match(cleaned):
            mode = "stack"
            continue

        stack_match = STACK_PATTERN.match(cleaned)
        if stack_match and current:
            current.stack.append(stack_match.group(1).strip())
            mode = "stack"
            continue

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

        if current:
            item = _strip_bullet(cleaned) if _is_bullet(cleaned) else cleaned
            if mode == "stack":
                current.stack.append(item)
            elif mode == "tasks":
                current.tasks.append(item)
            elif mode == "scan":
                if not current.title:
                    current.title = item
                else:
                    current.tasks.append(item)
        else:
            current = Experience(dates="", title=cleaned, company="")
            mode = "scan"

    if current:
        experiences.append(current)

    return experiences


def parse_cv(text: str) -> CVData:
    cv = CVData()

    sections = split_into_sections(text)

    # Parse header
    if "_header" in sections:
        header = parse_header(sections["_header"])
        cv.name = header["name"]
        cv.headline = header["headline"]
        if header.get("years_exp"):
            cv.years_experience = header["years_exp"]

    # Parse profil
    if "profil" in sections:
        profile_lines = [_clean(l) for l in sections["profil"] if _clean(l)]
        cv.profile = " ".join(profile_lines)

    # Parse formation
    if "formation" in sections:
        cv.education = parse_formation(sections["formation"])

    # Parse experiences
    if "experiences" in sections:
        cv.experiences = parse_experiences(sections["experiences"])

    # Parse projects
    if "projets" in sections:
        cv.projects = parse_projects(sections["projets"])

    # Parse savoir faire
    if "savoir_faire" in sections:
        pass  # handled by generator via get_savoir_faire()

    # Parse technical skills
    if "competences" in sections:
        cv.tech_skills = parse_tech_skills(sections["competences"])

    # Parse languages
    if "langues" in sections:
        cv.languages = parse_languages(sections["langues"])

    # --- Handle duplicate sections ---
    for key, lines in sections.items():
        if key.startswith("formation_") and key != "formation":
            # Could be certifications or training — add to education
            extra_edu = parse_formation(lines)
            if extra_edu:
                cv.education.extend(extra_edu)
            else:
                extra = _parse_intm_blocks(lines)
                cv.experiences.extend(extra)
        elif key.startswith("projets_") and key != "projets":
            extra = _parse_intm_blocks(lines)
            cv.projects.extend(extra)
        elif key.startswith("experiences_") and key != "experiences":
            extra = parse_experiences(lines)
            cv.experiences.extend(extra)
        elif key.startswith("competences_") and key != "competences":
            extra = parse_tech_skills(lines)
            cv.tech_skills.extend(extra)

    return cv


def get_savoir_faire(text: str) -> list[str]:
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


def print_cv(cv: CVData):
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
        for t in exp.tasks[:3]:
            print(f"          • {t}")
        if len(exp.tasks) > 3:
            print(f"          ... +{len(exp.tasks)-3} more")
        if exp.stack:
            print(f"          🔧 {', '.join(exp.stack)}")

    print(f"\n🔬 Projects ({len(cv.projects)}):")
    for proj in cv.projects:
        print(f"  [{proj.dates}] {proj.title}")
        for t in proj.tasks[:2]:
            print(f"          • {t}")
        if len(proj.tasks) > 2:
            print(f"          ... +{len(proj.tasks)-2} more")
        if proj.stack:
            print(f"          🔧 {', '.join(proj.stack)}")

    print(f"\n💻 Technical Skills ({len(cv.tech_skills)}):")
    for ts in cv.tech_skills:
        print(f"  [{ts.category}] {ts.details[:80]}")

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