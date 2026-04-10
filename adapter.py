import re
from parser import CVData, Experience, Education, TechSkill
from parser import get_savoir_faire, parse_cv
from parser_v2 import ParsedCV, ProfileData, Section, ExperienceBlock, TableRow


MONTHS_MAP = {
    "jan": 1, "janv": 1, "janvier": 1,
    "fev": 2, "fév": 2, "fevr": 2, "févr": 2, "fevrier": 2, "février": 2,
    "mar": 3, "mars": 3,
    "avr": 4, "avril": 4,
    "mai": 5,
    "juin": 6,
    "jul": 7, "juil": 7, "juillet": 7,
    "aou": 8, "aoû": 8, "aout": 8, "août": 8,
    "sep": 9, "sept": 9, "septembre": 9,
    "oct": 10, "octobre": 10,
    "nov": 11, "novembre": 11,
    "dec": 12, "déc": 12, "decembre": 12, "décembre": 12,
}


def _parse_date_piece(piece: str):
    """Parse 'Month YYYY' or 'MM/YYYY' or 'YYYY' into (year, month)."""
    piece = piece.strip().replace("–", "-").replace("—", "-")

    # "MM/YYYY"
    m = re.match(r"^(\d{2})/(\d{4})$", piece)
    if m:
        return int(m.group(2)), int(m.group(1))

    # "Month YYYY" (abbreviated or full)
    m = re.match(r"(?i)^([A-Za-zÀ-ÿ\.]+)\s+(\d{4})$", piece)
    if m:
        month_str = m.group(1).lower().replace(".", "").strip()
        month = MONTHS_MAP.get(month_str)
        year = int(m.group(2))
        if month:
            return year, month

    # Just "YYYY"
    m = re.match(r"^(\d{4})$", piece)
    if m:
        return int(m.group(1)), 1

    return None


def _compute_duration(dates: str) -> str:
    if not dates or not dates.strip():
        return ""

    cleaned = dates.strip()

    # Already has "Durée"
    if cleaned.lower().startswith("durée"):
        return cleaned

    # Strip "Depuis" prefix — treat as open-ended
    if cleaned.lower().startswith("depuis"):
        rest = re.sub(r"(?i)^depuis\s+", "", cleaned).strip()
        return f"Depuis {rest}"

    # Single year
    if re.fullmatch(r"\d{4}", cleaned):
        return cleaned

    # Split on dash
    parts = re.split(r"\s*[-–—]\s*", cleaned)
    if len(parts) == 2:
        start = _parse_date_piece(parts[0])
        end_str = parts[1].strip().lower()

        # Handle "Présent", "Aujourd'hui", "en cours"
        if any(kw in end_str for kw in ["présent", "present", "aujourd", "en cours", "auj"]):
            if start:
                return f"Depuis {parts[0].strip()}"

        end = _parse_date_piece(parts[1])
        if start and end:
            sy, sm = start
            ey, em = end
            months = (ey - sy) * 12 + (em - sm)
            if months <= 0:
                return f"Durée {cleaned}"
            if months < 12:
                return f"Durée {months} mois"
            years = months // 12
            rem = months % 12
            if rem == 0:
                return "Durée 1 an" if years == 1 else f"Durée {years} ans"
            if years == 1:
                return f"Durée 1 an {rem} mois"
            return f"Durée {years} ans {rem} mois"

    return f"Durée {cleaned}"


def _clean_text(text: str) -> str:
    """Strip trailing pipes, dashes, colons, bullets, duration brackets from text."""
    if not text:
        return ""
    # Strip leading bullet chars
    text = re.sub(r"^[•·▪■▸◆➤●★\-–—]\s*", "", text).strip()
    # Strip trailing pipes and dashes
    text = re.sub(r"\s*[\|]\s*$", "", text).strip()
    text = re.sub(r"\s*-\s*$", "", text).strip()
    # Strip duration parentheticals: "(1 ans et 6 mois)", "(3 ans)", "(8 mois)"
    text = re.sub(r"^\(\d+\s*(?:ans?|années?)?(?:\s+et\s+\d+\s*mois)?\)\s*$", "", text).strip()
    text = re.sub(r"^\(\d+\s*mois\)\s*$", "", text).strip()
    # Strip duration brackets: "[4 mois]", "[13 mois]", "[14 mois]"
    text = re.sub(r"^\[\d+\s*(?:ans?|mois)\]\s*$", "", text).strip()
    return text


def _looks_like_company(text: str) -> bool:
    if not text:
        return False
    # Companies: often ALL CAPS, or end with SA, SAS, SARL, Group, etc.
    # Or contain parenthetical location: "ATOS (Paris)", "OBJECTWARE (France)"
    if re.search(r"\((?:Paris|France|Lyon|Maroc|Belgique|UK|Écosse)\)", text, re.IGNORECASE):
        return True
    if text.isupper() and len(text.split()) <= 5:
        return True
    # Known company suffixes
    if re.search(r"(?i)\b(?:SA|SAS|SARL|GmbH|Ltd|Inc|Group|Groupe|CIB)\b", text):
        return True
    return False


def _looks_like_title(text: str) -> bool:
    if not text:
        return False
    title_keywords = [
        r"(?i)\b(?:consultant|ingénieur|analyste|développeur|chef\s+de\s+projet|"
        r"manager|lead|directeur|responsable|administrateur|coordinat|cheffe?|"
        r"architect|expert|senior|junior|freelance|officer|advisor|recetteur)\b"
    ]
    for pat in title_keywords:
        if re.search(pat, text):
            return True
    return False


def _guess_company_and_title(exp: Experience) -> tuple[str, str]:
    company = _clean_text(exp.company)
    title = _clean_text(exp.title)

    # If title is empty after cleaning (was a duration parenthetical), 
    # look for the real title in the first task
    if not title and exp.tasks:
        for i, task in enumerate(exp.tasks):
            t = _clean_text(task)
            if t and _looks_like_title(t) and len(t.split()) <= 12:
                title = t
                break

    if company and title:
        # Check if they're swapped
        if _looks_like_company(title) and _looks_like_title(company):
            return title, company
        return company, title

    if not company and title:
        # "Company – Title" or "Company - Title" or "Company | Title"
        dash_split = re.split(r"\s+[–—\-|]\s+", title, maxsplit=1)
        if len(dash_split) == 2:
            part1, part2 = dash_split[0].strip(), dash_split[1].strip()
            # Determine which is company and which is title
            if _looks_like_company(part1):
                return part1, part2
            elif _looks_like_company(part2):
                return part2, part1
            else:
                return part1, part2

        # If it looks like a company name, use it as company
        # and try to find the real title in first task
        if _looks_like_company(title):
            job_title = ""
            if exp.tasks:
                for task in exp.tasks:
                    t = _clean_text(task)
                    if t and _looks_like_title(t) and len(t.split()) <= 12:
                        job_title = t
                        break
            return title, job_title

        # If it looks like a title, use it as title and company is unknown
        if _looks_like_title(title):
            # Try to find company in first task
            job_company = ""
            if exp.tasks:
                first = _clean_text(exp.tasks[0])
                if first and _looks_like_company(first):
                    job_company = first
                elif first and not _looks_like_title(first) and len(first.split()) <= 5:
                    job_company = first
            return job_company, title

        # Default: use as company, look for title in tasks
        job_title = ""
        if exp.tasks:
            for task in exp.tasks:
                t = _clean_text(task)
                if t and _looks_like_title(t) and len(t.split()) <= 12:
                    job_title = t
                    break
        return title, job_title

    if company and not title:
        # Try to find title in tasks
        if exp.tasks:
            for task in exp.tasks:
                t = _clean_text(task)
                if t and _looks_like_title(t) and len(t.split()) <= 12:
                    title = t
                    break
        return company, title

    return "", ""


def _experience_to_block(exp: Experience) -> ExperienceBlock:
    company, title = _guess_company_and_title(exp)

    # --- Build the title line: "Entreprise COMPANY\tDurée DURATION" ---
    duration = _compute_duration(exp.dates)

    if company:
        title_line = f"Entreprise {company}"
    else:
        title_line = "Entreprise"

    if duration:
        title_line += f"\t{duration}"

    # --- Poste line ---
    poste = f"Poste {title}" if title else ""

    # --- Sub-sections ---
    sub_sections = []

    # Filter out tasks that were accidentally the job title
    tasks = exp.tasks
    if title and tasks and tasks[0] == title:
        tasks = tasks[1:]

    if tasks:
        sub_sections.append(("ROLE :", tasks))
    if exp.stack:
        sub_sections.append(("Environnement technique :", exp.stack))

    return ExperienceBlock(
        title_line=title_line,
        poste=poste,
        sub_sections=sub_sections,
    )


def cvdata_to_parsed(cv: CVData, savoir_faire: list[str] | None = None) -> ParsedCV:
    result = ParsedCV()

    # --- Profile ---
    result.profile = ProfileData(
        lines=[cv.name, cv.headline, cv.language, cv.years_experience],
        name=cv.name,
        title=cv.headline,
        language=cv.language,
        years_experience=cv.years_experience,
    )

    # --- Formation ---
    if cv.education:
        section = Section(header="Formation", content_type="table")
        for edu in cv.education:
            left = edu.degree
            right = edu.institution
            section.table_rows.append(TableRow(left=left, right=right))
        result.sections.append(section)

    # --- Savoir Faire ---
    # Use explicit savoir_faire items if available, otherwise generate from profile
    sf_items = savoir_faire or []
    if not sf_items and cv.profile:
        # Split the profile paragraph into sentences to use as savoir faire bullets
        # Only if it's substantial enough (more than just a one-liner)
        profile_text = cv.profile.strip()
        if len(profile_text) > 50:
            # Split on sentence boundaries
            sentences = re.split(r"(?<=[.!])\s+", profile_text)
            # Filter out very short fragments
            sf_items = [s.strip() for s in sentences if len(s.strip()) > 20]
    
    if sf_items:
        section = Section(header="Savoir Faire", content_type="bullets")
        section.bullet_items = sf_items
        result.sections.append(section)

    # --- Compétences Techniques ---
    if cv.tech_skills:
        section = Section(header="Compétences Techniques", content_type="table")
        for ts in cv.tech_skills:
            section.table_rows.append(TableRow(left=ts.category, right=ts.details))
        result.sections.append(section)

    # --- Expériences Professionnelles ---
    if cv.experiences:
        section = Section(header="Expériences Professionnelles", content_type="experiences")
        for exp in cv.experiences:
            section.experience_blocks.append(_experience_to_block(exp))
        result.sections.append(section)

    # --- Projets ---
    if cv.projects:
        section = Section(header="Projets", content_type="experiences")
        for proj in cv.projects:
            section.experience_blocks.append(_experience_to_block(proj))
        result.sections.append(section)

    return result