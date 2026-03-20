
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Education:
    years: str
    degree: str
    institution: str


@dataclass
class Experience:
    dates: str
    title: str
    company: str
    tasks: list[str] = field(default_factory=list)
    stack: list[str] = field(default_factory=list)


@dataclass
class TechSkill:
    category: str
    details: str


@dataclass
class CVData:
    name: str = ""
    headline: str = ""
    language: str = ""
    years_experience: str = ""
    profile: str = ""
    education: list[Education] = field(default_factory=list)
    experiences: list[Experience] = field(default_factory=list)
    projects: list[Experience] = field(default_factory=list)
    tech_skills: list[TechSkill] = field(default_factory=list)
    languages: dict[str, str] = field(default_factory=dict)


def _strip_accents(text: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(c)
    )


def _normalize_header_key(text: str) -> str:
    text = _strip_accents(text or "")
    text = re.sub(r"[\u200b\u200c\u200d\ufeff]", "", text)
    text = text.lower()
    text = re.sub(r"[^\w\s/&-]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _clean(line: str) -> str:
    line = (line or "").replace("\x0c", " ").replace("\uf0b7", "•").replace("￾", "")
    line = line.replace("’", "'").replace("–", "–").replace("—", "—")
    return re.sub(r"\s+", " ", line.strip())


SECTION_HEADERS = {
    "profil": re.compile(
        r"^(?:profil|profile|resume|summary|about|a propos|objectif|objective)$",
        re.IGNORECASE,
    ),
    "formation": re.compile(
        r"^(?:formation|formations|education|educations|etudes|diplomes|parcours academique|academic background|academic training|certifications?)$",
        re.IGNORECASE,
    ),
    "experiences": re.compile(
        r"^(?:experience|experiences|experience professionnelle|experiences professionnelles|professional experience|professional experiences|work experience|employment history|career history|parcours professionnel|parcours professionnels|debut de carriere)$",
        re.IGNORECASE,
    ),
    "projets": re.compile(
        r"^(?:projet|projets|projects|selected projects|projets selectionnes|realisations|other activities|academic projects)$",
        re.IGNORECASE,
    ),
    "savoir_faire": re.compile(
        r"^(?:savoir faire|core competencies|functional skills|competences fonctionnelles)$",
        re.IGNORECASE,
    ),
    "competences": re.compile(
        r"^(?:competences|competences techniques|competences fonctionnelles|technical skills|skills|tools and technologies|outils et technologies|it skills|hard skills)$",
        re.IGNORECASE,
    ),
    "langues": re.compile(
        r"^(?:langues|languages|spoken languages)$",
        re.IGNORECASE,
    ),
}


def _detect_section(line: str) -> Optional[str]:
    cleaned = _clean(line)
    if not cleaned:
        return None
    key = _normalize_header_key(cleaned)
    if len(key) > 80:
        return None
    for sec, pattern in SECTION_HEADERS.items():
        if pattern.match(key):
            return sec
    return None


def split_into_sections(text: str) -> dict[str, list[str]]:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")
    sections: dict[str, list[str]] = {}
    current_section = "_header"
    current_lines: list[str] = []

    for line in lines:
        detected = _detect_section(line)
        if detected:
            sections[current_section] = current_lines
            key = detected
            suffix = 2
            while key in sections:
                key = f"{detected}_{suffix}"
                suffix += 1
            current_section = key
            current_lines = []
        else:
            current_lines.append(line)

    sections[current_section] = current_lines
    return sections


_MONTHS = (
    r"(?:Jan|Fev|F[ée]v|Mar|Apr|Avr|May|Mai|Jun|Juin|Jul|Juil|Aug|Aou|Ao[uû]t|"
    r"Sep|Sept|Oct|Nov|Dec|D[ée]c|January|February|March|April|May|June|July|"
    r"August|September|October|November|December|Janvier|Fevrier|Février|Mars|"
    r"Avril|Juillet|Aout|Août|Septembre|Octobre|Novembre|Decembre|Décembre)"
    r"\.?"
)
_DATE_PIECE = rf"(?:{_MONTHS}\s+)?\d{{4}}|\d{{2}}/\d{{4}}|\d{{4}}/\d{{2}}|\d{{4}}"
_DATE_END_PIECE = rf"(?:{_DATE_PIECE}|[Pp]r[ée]sent|Present|Current|Aujourd'hui|Now|En cours)"
DATE_RANGE_RE = rf"(?:{_DATE_PIECE})\s*[-–—]\s*(?:{_DATE_END_PIECE})"

DATE_RANGE_PATTERN = re.compile(rf"^({DATE_RANGE_RE})", re.IGNORECASE)
DATE_RANGE_END_PATTERN = re.compile(rf"^(.+?)\s+({DATE_RANGE_RE})\s*$", re.IGNORECASE)
PARTIAL_DATE_PATTERN = re.compile(rf"^(({_DATE_PIECE}))\s*[-–—]\s*$", re.IGNORECASE)
DATE_END_PATTERN = re.compile(rf"^(({_DATE_PIECE}|Present|Current|[Pp]r[ée]sent|Aujourd'hui|En cours))\s*$", re.IGNORECASE)
YEAR_PATTERN = re.compile(r"^(\d{4})\s*[:\-–—]?\s*(\S.+)$")
YEAR_RANGE_INLINE_PATTERN = re.compile(r"^(\d{4}\s*[-–—]\s*\d{4})\s*[:\-–—]\s*(.+)$")
PIPE_EXPERIENCE_PATTERN = re.compile(
    rf"^(?P<dates>{DATE_RANGE_RE})\s*\|\s*(?P<company>[^|]+?)\s*\|\s*(?P<title>.+)$",
    re.IGNORECASE,
)
PIPE_THREE_PARTS_PATTERN = re.compile(r"^(?P<a>[^|]+?)\s*\|\s*(?P<b>[^|]+?)\s*\|\s*(?P<c>.+)$")
_FULL_MONTHS = (
    r"(?:JANVIER|FEVRIER|FÉVRIER|MARS|AVRIL|MAI|JUIN|JUILLET|AOUT|AOÛT|SEPTEMBRE|"
    r"OCTOBRE|NOVEMBRE|DECEMBRE|DÉCEMBRE|Janvier|Fevrier|Février|Mars|Avril|Mai|"
    r"Juin|Juillet|Aout|Août|Septembre|Octobre|Novembre|Decembre|Décembre|"
    r"January|February|March|April|May|June|July|August|September|October|November|December)"
)
DE_A_DATE_PATTERN = re.compile(
    rf"^(?P<company>.+?)\s+DE\s+(?P<m1>{_FULL_MONTHS})\s+(?P<y1>\d{{4}})\s+A\s+(?P<m2>{_FULL_MONTHS})\s*(?P<y2>\d{{4}}|Present|Current|[Pp]r[ée]sent)\s*$",
    re.IGNORECASE,
)
COMPACT_CAREER_PATTERN = re.compile(
    rf"^(?P<dates>\d{{4}}(?:\s*[-–—]\s*\d{{4}})?)\s*:\s*(?P<company>[^—|]+?)\s*[—-]\s*(?P<title>.+)$",
    re.IGNORECASE,
)
TITLE_DATE_LINE_PATTERN = re.compile(rf"^(?P<title>.+?)\s+(?P<dates>{DATE_RANGE_RE})\s*$", re.IGNORECASE)

BULLET_PATTERN = re.compile(r"^\s*[—\-•■▪▸◆➤●★>»→➢◼]\s*")
STACK_PATTERN = re.compile(
    r"(?i)^(?:stack|environnement\s+technique|environnement|technologies?\s+utilis[ée]es?|outils?|tools?|technical environment)\s*:\s*(.+)"
)
STACK_HEADER_PATTERN = re.compile(
    r"(?i)^(?:stack|environnement\s+technique|environnement|technologies?|tools?|technical environment)\s*:?\s*$"
)
ROLE_HEADER_PATTERN = re.compile(
    r"(?i)^(?:r[oô]le|responsabilites?|responsibilities|activites?|missions?|tasks?|main tasks)\s*:?\s*$"
)
CONTEXT_HEADER_PATTERN = re.compile(
    r"(?i)^(?:contexte|context)\s*:?\s*$"
)
LOCATION_LINE_PATTERN = re.compile(
    r"^(?:[A-Z][A-Za-zÀ-ÿ' -]+)(?:,\s*[A-Z][A-Za-zÀ-ÿ' -]+)?$"
)
CONTACT_PATTERN = re.compile(r"(?i)(@|linkedin|github|gitlab|https?://|\+?\d[\d\s().-]{6,})")
LANG_LINE_PATTERN = re.compile(
    r"(?i)\b(?:anglais|english|french|francais|français|arabic|arabe|spanish|espagnol|german|allemand)\b"
)
YEARS_EXP_PATTERN = re.compile(
    r"(?i)(?:\+?\s*\d+\s*(?:ans|years?)\s+d[' ]experience(?:\s+professionnelle)?|plus de \d+\s+ans d[' ]experience)"
)

_TOOL_KEYWORDS = [
    "excel", "word", "powerpoint", "outlook", "teams", "sharepoint", "jira", "confluence",
    "trello", "notion", "ms project", "project", "power bi", "tableau", "qlik", "sap",
    "salesforce", "servicenow", "oracle", "crm", "matomo", "figma", "canva", "adobe",
    "python", "sql", "mysql", "postgresql", "mongodb", "pl/sql", "bash", "powershell",
    "java", "javascript", "php", "git", "github", "gitlab", "jenkins", "ansible", "terraform",
    "docker", "kubernetes", "aws", "azure", "gcp", "linux", "windows", "vmware", "prometheus",
    "grafana", "pack office", "office", "agile", "scrum", "safe", "itil", "axway", "putty"
]
_TOOL_REGEX = re.compile(
    r"(?i)\b(" + "|".join(re.escape(k) for k in sorted(_TOOL_KEYWORDS, key=len, reverse=True)) + r")\b"
)

UNIVERSITY_TERMS = re.compile(
    r"(?i)\b(universit|university|ecole|school|college|institut|institute|mba|master|licence|license|bachelor|doctorat|phd|msc|bba|bts|dut|rncp)\b"
)
CERT_TERMS = re.compile(
    r"(?i)\b(certif|formation|training|bootcamp|itil|safe|prince2|pmp|scrum)\b"
)
PROJECT_TITLE_PATTERN = re.compile(
    r"(?i)^(?:projet|project|projet personnel|projet universitaire|academic project|personal project)\b"
)


def _is_bullet(line: str) -> bool:
    return bool(BULLET_PATTERN.match(line))


def _strip_bullet(line: str) -> str:
    return BULLET_PATTERN.sub("", line).strip()


def _is_page_marker(line: str) -> bool:
    cleaned = _clean(line)
    if not cleaned:
        return True
    if re.match(r"^\d+/\d+$", cleaned) or re.match(r"(?i)^page\s+\d+", cleaned):
        return True
    if re.match(r"^\d+\s+rue\s+", cleaned, re.IGNORECASE):
        return True
    if re.match(r"^T[ée]l\.?\s*:?\s*\+?\d", cleaned, re.IGNORECASE):
        return True
    return False


def _looks_like_city_or_location(line: str) -> bool:
    if not line:
        return False
    if CONTACT_PATTERN.search(line):
        return False
    low = _normalize_header_key(line)
    city_words = [
        "paris", "france", "ile de france", "lyon", "nantes", "pantin", "courbevoie",
        "nanterre", "beirut", "lebanon", "noisy le grand"
    ]
    return any(w in low for w in city_words)


def _dedupe_keep_order(items: list[str]) -> list[str]:
    seen = set()
    out = []
    for item in items:
        key = _normalize_header_key(item)
        if key and key not in seen:
            seen.add(key)
            out.append(item.strip())
    return out


def parse_header(lines: list[str]) -> dict:
    result = {"name": "", "headline": "", "language": "", "years_experience": "", "contacts": []}
    clean_lines = []
    for raw in lines:
        cleaned = _clean(raw)
        if not cleaned or _is_page_marker(cleaned):
            continue
        if _detect_section(cleaned):
            break
        clean_lines.append(cleaned)

    for line in clean_lines:
        if CONTACT_PATTERN.search(line):
            result["contacts"].append(line)
            continue
        if not result["years_experience"]:
            m = YEARS_EXP_PATTERN.search(line)
            if m:
                result["years_experience"] = m.group(0).strip()
                continue
        if not result["language"] and LANG_LINE_PATTERN.search(line):
            result["language"] = line
            continue
        if not result["name"]:
            result["name"] = line
            continue
        if not result["headline"] and not _looks_like_city_or_location(line):
            # Keep long headlines if they are not obviously profile text
            if len(line.split()) <= 16:
                result["headline"] = line
                continue

    return result


def _split_degree_and_institution(text: str) -> tuple[str, str]:
    if "|" in text:
        parts = [p.strip() for p in text.split("|") if p.strip()]
        if len(parts) >= 3:
            if UNIVERSITY_TERMS.search(parts[1]) and not UNIVERSITY_TERMS.search(parts[0]):
                return parts[0], " | ".join(parts[1:])
            if UNIVERSITY_TERMS.search(parts[0]):
                return parts[-1], " | ".join(parts[:-1])
            return parts[0], " | ".join(parts[1:])
        if len(parts) == 2:
            if UNIVERSITY_TERMS.search(parts[0]) and not UNIVERSITY_TERMS.search(parts[1]):
                return parts[1], parts[0]
            return parts[0], parts[1]

    pieces = re.split(r"\s+[|—–-]\s+|,\s+", text, maxsplit=1)
    if len(pieces) == 2:
        a, b = pieces[0].strip(), pieces[1].strip()
        if UNIVERSITY_TERMS.search(a) and not UNIVERSITY_TERMS.search(b):
            return b, a
        return a, b
    return text.strip(), ""


def _education_priority(entry: Education) -> tuple[int, str]:
    text = " ".join([entry.degree, entry.institution])
    if UNIVERSITY_TERMS.search(text) and not CERT_TERMS.search(text):
        return (0, text.lower())
    if CERT_TERMS.search(text):
        return (1, text.lower())
    return (2, text.lower())


def parse_formation(lines: list[str]) -> list[Education]:
    items: list[Education] = []
    pending_lines: list[str] = []

    def flush_pending():
        nonlocal pending_lines
        if not pending_lines:
            return
        text = " ".join(pending_lines).strip(" |")
        if text:
            degree, institution = _split_degree_and_institution(text)
            items.append(Education(years="", degree=degree, institution=institution))
        pending_lines = []

    paren_date_range = re.compile(r"^(.+?)\s*\((\d{4})\s*[-–‑]\s*(\d{4})\)\s*$")
    paren_date_single = re.compile(r"^(.+?)\s*\((\d{4})\)\s*$")

    for line in lines:
        cleaned = _clean(line)
        if not cleaned or _is_page_marker(cleaned):
            flush_pending()
            continue
        stripped = _strip_bullet(cleaned) if _is_bullet(cleaned) else cleaned

        if _detect_section(stripped):
            flush_pending()
            continue

        if "\t" in line:
            flush_pending()
            parts = [p.strip() for p in line.split("\t") if p.strip()]
            if parts:
                years = parts[0] if re.search(r"\d{4}", parts[0]) else ""
                text = " | ".join(parts[1:] if years else parts)
                degree, institution = _split_degree_and_institution(text)
                items.append(Education(years=years, degree=degree, institution=institution))
            continue

        m = PIPE_EXPERIENCE_PATTERN.match(stripped)
        if m:
            # not formation
            flush_pending()
            continue

        date_match = DATE_RANGE_PATTERN.match(stripped)
        if date_match:
            flush_pending()
            years = date_match.group(1).strip()
            rest = stripped[date_match.end():].strip(" |,-")
            degree, institution = _split_degree_and_institution(rest)
            items.append(Education(years=years, degree=degree, institution=institution))
            continue

        end_date_match = DATE_RANGE_END_PATTERN.match(stripped)
        if end_date_match:
            flush_pending()
            text_part = end_date_match.group(1).strip(" |,-")
            years = end_date_match.group(2).strip()
            degree, institution = _split_degree_and_institution(text_part)
            items.append(Education(years=years, degree=degree, institution=institution))
            continue

        paren_range_match = paren_date_range.match(stripped)
        if paren_range_match:
            flush_pending()
            text_part = paren_range_match.group(1).strip()
            years = f"{paren_range_match.group(2)}–{paren_range_match.group(3)}"
            degree, institution = _split_degree_and_institution(text_part)
            items.append(Education(years=years, degree=degree, institution=institution))
            continue

        paren_single_match = paren_date_single.match(stripped)
        if paren_single_match:
            flush_pending()
            text_part = paren_single_match.group(1).strip()
            years = paren_single_match.group(2)
            degree, institution = _split_degree_and_institution(text_part)
            items.append(Education(years=years, degree=degree, institution=institution))
            continue

        year_match = YEAR_PATTERN.match(stripped)
        if year_match:
            flush_pending()
            years = year_match.group(1)
            rest = year_match.group(2).strip()
            degree, institution = _split_degree_and_institution(rest)
            items.append(Education(years=years, degree=degree, institution=institution))
            continue

        # Multi-line formations like:
        # University
        # Master ...
        if pending_lines and UNIVERSITY_TERMS.search(" ".join(pending_lines)) and not UNIVERSITY_TERMS.search(stripped):
            pending_lines.append(stripped)
            flush_pending()
            continue

        if UNIVERSITY_TERMS.search(stripped) or CERT_TERMS.search(stripped) or "|" in stripped:
            flush_pending()
            pending_lines.append(stripped)
            continue

        pending_lines.append(stripped)

    flush_pending()
    items = [i for i in items if i.degree or i.institution]
    items.sort(key=_education_priority)
    return items


def _append_text_item(bucket: list[str], text: str) -> None:
    text = text.strip()
    if not text:
        return
    if not bucket:
        bucket.append(text)
        return
    if bucket[-1].endswith((".", ";", ":", "?", "!")) or len(bucket[-1]) > 220:
        bucket.append(text)
    else:
        bucket[-1] += " " + text


def _split_title_location(text: str) -> tuple[str, str]:
    text = text.strip()
    if " — " in text:
        left, right = text.rsplit(" — ", 1)
        if LOCATION_LINE_PATTERN.match(right) or len(right.split()) <= 4:
            return left.strip(), right.strip()
    if ", " in text:
        left, right = text.rsplit(", ", 1)
        if LOCATION_LINE_PATTERN.match(right) or len(right.split()) <= 4:
            return left.strip(), right.strip()
    return text, ""


def _infer_stack_from_text(text: str) -> list[str]:
    found = []
    for m in _TOOL_REGEX.finditer(text or ""):
        tool = m.group(1)
        # normalize some variants
        low = tool.lower()
        if low == "sharepoint":
            tool = "SharePoint"
        elif low == "power bi":
            tool = "Power BI"
        elif low == "ms project":
            tool = "MS Project"
        elif low == "agile":
            tool = "Agile"
        elif low == "scrum":
            tool = "Scrum"
        found.append(tool)
    return _dedupe_keep_order(found)


def _make_experience(dates: str = "", title: str = "", company: str = "") -> Experience:
    return Experience(dates=dates.strip(), title=title.strip(), company=company.strip())


def parse_experiences(lines: list[str]) -> list[Experience]:
    experiences: list[Experience] = []
    current: Optional[Experience] = None
    mode = "tasks"
    i = 0

    while i < len(lines):
        raw = lines[i]
        cleaned = _clean(raw)
        if not cleaned or _is_page_marker(cleaned):
            i += 1
            continue

        stripped = _strip_bullet(cleaned) if _is_bullet(cleaned) else cleaned

        # Skip duplicated section headers inside PDFs
        if _detect_section(stripped) in {"experiences", "profil"}:
            i += 1
            continue

        # New block: DATE | COMPANY | TITLE
        m = PIPE_EXPERIENCE_PATTERN.match(stripped)
        if m:
            if current:
                if not current.stack:
                    current.stack = _infer_stack_from_text(" ".join(current.tasks))
                experiences.append(current)
            title, location = _split_title_location(m.group("title"))
            company = m.group("company").strip()
            if location and location not in company:
                company = f"{company}, {location}"
            current = _make_experience(m.group("dates"), title, company)
            mode = "tasks"
            i += 1
            continue

        # Compact early career: 2019-2020 : CGI - title
        m = COMPACT_CAREER_PATTERN.match(stripped)
        if m:
            if current:
                if not current.stack:
                    current.stack = _infer_stack_from_text(" ".join(current.tasks))
                experiences.append(current)
            title, location = _split_title_location(m.group("title"))
            company = m.group("company").strip()
            if location and location not in company:
                company = f"{company}, {location}"
            current = _make_experience(m.group("dates"), title, company)
            mode = "tasks"
            i += 1
            continue

        # COMPANY DE MONTH YEAR A MONTH YEAR
        m = DE_A_DATE_PATTERN.match(stripped)
        if m:
            if current:
                if not current.stack:
                    current.stack = _infer_stack_from_text(" ".join(current.tasks))
                experiences.append(current)
            dates = f"{m.group('m1')} {m.group('y1')} – {m.group('m2')} {m.group('y2')}"
            current = _make_experience(dates, "", m.group("company"))
            mode = "tasks"
            # next non-empty line is often title
            j = i + 1
            while j < len(lines):
                nxt = _clean(lines[j])
                if not nxt or _is_page_marker(nxt):
                    j += 1
                    continue
                nstr = _strip_bullet(nxt) if _is_bullet(nxt) else nxt
                if ROLE_HEADER_PATTERN.match(nstr) or CONTEXT_HEADER_PATTERN.match(nstr) or STACK_HEADER_PATTERN.match(nstr):
                    break
                if not DATE_RANGE_PATTERN.match(nstr) and not PIPE_EXPERIENCE_PATTERN.match(nstr):
                    current.title = nstr
                    i = j
                break
            i += 1
            continue

        # Freeform line starting with date
        date_match = DATE_RANGE_PATTERN.match(stripped)
        if date_match:
            if current:
                if not current.stack:
                    current.stack = _infer_stack_from_text(" ".join(current.tasks))
                experiences.append(current)
            dates = date_match.group(1)
            rest = stripped[date_match.end():].strip(" |-")
            company, title = "", ""
            if "|" in rest:
                parts = [p.strip() for p in rest.split("|") if p.strip()]
                if len(parts) >= 2:
                    company = parts[0]
                    title = " | ".join(parts[1:])
                elif parts:
                    title = parts[0]
            else:
                parts = rest.split(",", 1)
                title = parts[0].strip() if parts else ""
                company = parts[1].strip() if len(parts) > 1 else ""
            title, location = _split_title_location(title)
            if location and location not in company:
                company = f"{company}, {location}".strip(", ")
            current = _make_experience(dates, title, company)
            mode = "tasks"
            i += 1
            continue

        # English/French 2-line style:
        # Company Location
        # Title 01/2025 – Present
        if current is None or (current and current.tasks):
            if i + 1 < len(lines):
                nxt = _clean(lines[i + 1])
                nstr = _strip_bullet(nxt) if _is_bullet(nxt) else nxt
                m2 = TITLE_DATE_LINE_PATTERN.match(nstr)
                if m2 and not CONTACT_PATTERN.search(stripped) and not _detect_section(stripped):
                    if current:
                        if not current.stack:
                            current.stack = _infer_stack_from_text(" ".join(current.tasks))
                        experiences.append(current)
                    current = _make_experience(m2.group("dates"), m2.group("title"), stripped)
                    mode = "tasks"
                    i += 2
                    continue

        if current:
            if ROLE_HEADER_PATTERN.match(stripped):
                mode = "tasks"
                i += 1
                continue
            if CONTEXT_HEADER_PATTERN.match(stripped):
                mode = "tasks"
                i += 1
                continue
            if STACK_HEADER_PATTERN.match(stripped):
                mode = "stack"
                i += 1
                continue

            sm = STACK_PATTERN.match(stripped)
            if sm:
                current.stack.extend([s.strip() for s in re.split(r"\s*,\s*|\s*\|\s*", sm.group(1)) if s.strip()])
                mode = "stack"
                i += 1
                continue

            item = _strip_bullet(cleaned) if _is_bullet(cleaned) else stripped
            if mode == "stack":
                current.stack.extend([s.strip() for s in re.split(r"\s*,\s*|\s*\|\s*", item) if s.strip()])
            else:
                _append_text_item(current.tasks, item)
        i += 1

    if current:
        if not current.stack:
            current.stack = _infer_stack_from_text(" ".join(current.tasks))
        experiences.append(current)

    for exp in experiences:
        exp.stack = _dedupe_keep_order([s for s in exp.stack if s])
    return experiences


def parse_projects(lines: list[str]) -> list[Experience]:
    projects: list[Experience] = []
    current: Optional[Experience] = None

    for line in lines:
        cleaned = _clean(line)
        if not cleaned or _is_page_marker(cleaned):
            continue
        stripped = _strip_bullet(cleaned) if _is_bullet(cleaned) else cleaned

        m = PIPE_EXPERIENCE_PATTERN.match(stripped)
        if m:
            if current:
                if not current.stack:
                    current.stack = _infer_stack_from_text(" ".join(current.tasks))
                projects.append(current)
            current = _make_experience(m.group("dates"), m.group("title"), m.group("company"))
            continue

        m = YEAR_RANGE_INLINE_PATTERN.match(stripped)
        if m:
            if current:
                if not current.stack:
                    current.stack = _infer_stack_from_text(" ".join(current.tasks))
                projects.append(current)
            current = _make_experience(m.group(1), m.group(2), "")
            continue

        m = YEAR_PATTERN.match(stripped)
        if m and PROJECT_TITLE_PATTERN.search(m.group(2)):
            if current:
                if not current.stack:
                    current.stack = _infer_stack_from_text(" ".join(current.tasks))
                projects.append(current)
            current = _make_experience(m.group(1), m.group(2), "")
            continue

        if PROJECT_TITLE_PATTERN.match(stripped):
            if current:
                if not current.stack:
                    current.stack = _infer_stack_from_text(" ".join(current.tasks))
                projects.append(current)
            current = _make_experience("", stripped, "")
            continue

        if current:
            if STACK_HEADER_PATTERN.match(stripped):
                continue
            sm = STACK_PATTERN.match(stripped)
            if sm:
                current.stack.extend([s.strip() for s in re.split(r"\s*,\s*|\s*\|\s*", sm.group(1)) if s.strip()])
            else:
                _append_text_item(current.tasks, stripped)

    if current:
        if not current.stack:
            current.stack = _infer_stack_from_text(" ".join(current.tasks))
        projects.append(current)
    return projects


def parse_tech_skills(lines: list[str]) -> list[TechSkill]:
    skills: list[TechSkill] = []
    current_category = ""

    KNOWN_CATEGORIES = [
        "outils", "tools", "methodes", "méthodes", "langages", "languages",
        "frameworks", "cloud", "ci/cd", "monitoring", "reseaux", "réseaux",
        "systemes", "systèmes", "bases de donnees", "bases de données",
        "base de donnees", "base de données", "bureautique", "infrastructures",
        "technical", "soft skills", "technical skills"
    ]

    def commit(category: str, details: str):
        details = details.strip(" ,")
        if not category and not details:
            return
        if skills and skills[-1].category == category:
            skills[-1].details = (skills[-1].details + ", " + details).strip(" ,")
            return
        skills.append(TechSkill(category=category.strip(), details=details))

    i = 0
    while i < len(lines):
        cleaned = _clean(lines[i])
        if not cleaned or _is_page_marker(cleaned):
            i += 1
            continue
        stripped = _strip_bullet(cleaned) if _is_bullet(cleaned) else cleaned

        if "\t" in lines[i]:
            parts = [p.strip() for p in lines[i].split("\t") if p.strip()]
            if len(parts) >= 2:
                commit(parts[0], " ".join(parts[1:]))
            i += 1
            continue

        colon_match = re.match(r"^([^:]{2,40})\s*:\s+(.+)$", stripped)
        if colon_match:
            current_category = colon_match.group(1).strip()
            commit(current_category, colon_match.group(2).strip())
            i += 1
            continue

        lower = _normalize_header_key(stripped)
        if lower in [_normalize_header_key(x) for x in KNOWN_CATEGORIES]:
            current_category = stripped
            # category on one line, details on next lines
            details_parts = []
            j = i + 1
            while j < len(lines):
                nxt = _clean(lines[j])
                if not nxt or _is_page_marker(nxt):
                    break
                nstr = _strip_bullet(nxt) if _is_bullet(nxt) else nxt
                nlow = _normalize_header_key(nstr)
                if re.match(r"^([^:]{2,40})\s*:\s+(.+)$", nstr) or nlow in [_normalize_header_key(x) for x in KNOWN_CATEGORIES]:
                    break
                if _detect_section(nstr):
                    break
                details_parts.append(nstr)
                j += 1
            commit(current_category, " ".join(details_parts))
            i = j
            continue

        parts = re.split(r"\s{3,}", stripped, maxsplit=1)
        if len(parts) == 2 and len(parts[0].split()) <= 5:
            current_category = parts[0].strip()
            commit(current_category, parts[1].strip())
            i += 1
            continue

        if skills and current_category:
            skills[-1].details = (skills[-1].details + ", " + stripped).strip(" ,")
        else:
            commit("", stripped)
        i += 1

    return skills


def parse_languages(lines: list[str]) -> dict[str, str]:
    languages: dict[str, str] = {}

    def add_pair(lang: str, level: str):
        lang = lang.strip(" :|-")
        level = level.strip(" :|-")
        if lang:
            languages[lang] = level

    for line in lines:
        cleaned = _clean(line)
        if not cleaned or _is_page_marker(cleaned):
            continue

        for piece in re.split(r"\s+\|\s+|(?<=Native)\s+|(?<=Fluent)\s+", cleaned):
            piece = piece.strip()
            if not piece:
                continue

            if "\t" in piece:
                parts = piece.split("\t", 1)
                if len(parts) == 2:
                    add_pair(parts[0], parts[1])
                    continue

            colon_match = re.match(r"^([A-Za-zÀ-ÿ]+)\s*:\s*(.+)$", piece)
            if colon_match:
                add_pair(colon_match.group(1), colon_match.group(2))
                continue

            dash_match = re.match(r"^([A-Za-zÀ-ÿ]+)\s*[—-]\s*(.+)$", piece)
            if dash_match:
                add_pair(dash_match.group(1), dash_match.group(2))
                continue

            words = piece.split(None, 1)
            if len(words) == 2 and LANG_LINE_PATTERN.search(words[0]):
                add_pair(words[0], words[1])

    return languages


def _parse_intm_blocks(lines: list[str]) -> list[Experience]:
    return parse_experiences(lines)


def _choose_header_language(cv: CVData) -> str:
    if cv.language:
        return cv.language
    for preferred in ("Anglais", "English"):
        for lang, level in cv.languages.items():
            if preferred.lower() in lang.lower():
                return f"{lang} {level}".strip()
    if cv.languages:
        lang, level = next(iter(cv.languages.items()))
        return f"{lang} {level}".strip()
    return ""


def _build_savoir_faire_from_experiences(experiences: list[Experience]) -> list[str]:
    if not experiences:
        return []
    buckets = []
    seen = set()

    patterns = [
        ("Pilotage / coordination", re.compile(r"(?i)\b(pilotage|coordination|copil|comit[eé]|reporting|roadmap)\b")),
        ("Communication / rédaction", re.compile(r"(?i)\b(comptes?-rendus?|r[eé]daction|communication|animation|soutien|interface)\b")),
        ("Gestion de projet", re.compile(r"(?i)\b(projet|project management|gestion des risques|planning|priorit[ée]s|delivery)\b")),
        ("Management / transverse", re.compile(r"(?i)\b(manag|equipes?|parties prenantes|stakeholders?)\b")),
        ("Automatisation / industrialisation", re.compile(r"(?i)\b(automati|ci/cd|terraform|ansible|devops|scripts?)\b")),
        ("Cloud / infrastructure", re.compile(r"(?i)\b(cloud|aws|azure|kubernetes|docker|linux|infrastructure)\b")),
        ("Data / reporting", re.compile(r"(?i)\b(sql|power bi|tableau|excel|analyse de donn[ée]es|data)\b")),
    ]

    joined = " ".join(" ".join(exp.tasks) for exp in experiences)
    for label, pat in patterns:
        if pat.search(joined) and label.lower() not in seen:
            seen.add(label.lower())
            buckets.append(label)

    if not buckets:
        for exp in experiences:
            if exp.tasks:
                sentence = exp.tasks[0]
                if len(sentence) > 140:
                    sentence = sentence[:140].rstrip() + "..."
                buckets.append(sentence)
            if len(buckets) >= 6:
                break

    return buckets[:8]


def get_savoir_faire(text: str) -> list[str]:
    sections = split_into_sections(text)
    if "savoir_faire" in sections:
        items = []
        for line in sections["savoir_faire"]:
            cleaned = _clean(line)
            if cleaned and not _is_page_marker(cleaned):
                if _is_bullet(cleaned):
                    cleaned = _strip_bullet(cleaned)
                items.append(cleaned)
        return _dedupe_keep_order(items)

    cv = parse_cv(text)
    return _build_savoir_faire_from_experiences(cv.experiences)


def parse_cv(text: str) -> CVData:
    cv = CVData()
    sections = split_into_sections(text)

    if "_header" in sections:
        header = parse_header(sections["_header"])
        cv.name = header["name"]
        cv.headline = header["headline"]
        cv.language = header["language"]
        cv.years_experience = header["years_experience"]

    if "profil" in sections:
        profile_lines = [_clean(l) for l in sections["profil"] if _clean(l)]
        cv.profile = " ".join(profile_lines)

    if "formation" in sections:
        cv.education.extend(parse_formation(sections["formation"]))

    # certifications/extra formations often appear as duplicate formation sections
    for key, lines in sections.items():
        if key.startswith("formation_"):
            cv.education.extend(parse_formation(lines))

    if "experiences" in sections:
        cv.experiences = parse_experiences(sections["experiences"])

    for key, lines in sections.items():
        if key.startswith("experiences_") and key != "experiences":
            cv.experiences.extend(parse_experiences(lines))

    if "projets" in sections:
        cv.projects.extend(parse_projects(sections["projets"]))

    for key, lines in sections.items():
        if key.startswith("projets_") and key != "projets":
            cv.projects.extend(parse_projects(lines))

    if "competences" in sections:
        cv.tech_skills = parse_tech_skills(sections["competences"])

    if "langues" in sections:
        cv.languages = parse_languages(sections["langues"])

    # fallback: extract languages from skills blocks
    if not cv.languages and cv.tech_skills:
        for skill in cv.tech_skills:
            if "lang" in _normalize_header_key(skill.category):
                cv.languages.update(parse_languages([skill.details]))

    cv.language = _choose_header_language(cv)

    # dedupe/sort formation: universities first
    deduped_edu = []
    seen_edu = set()
    for edu in sorted(cv.education, key=_education_priority):
        key = (_normalize_header_key(edu.years), _normalize_header_key(edu.degree), _normalize_header_key(edu.institution))
        if key not in seen_edu:
            seen_edu.add(key)
            deduped_edu.append(edu)
    cv.education = deduped_edu

    return cv


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
        for t in exp.tasks:
            print(f"          • {t}")
        if exp.stack:
            print(f"          🔧 {', '.join(exp.stack)}")

    print(f"\n🔬 Projects ({len(cv.projects)}):")
    for proj in cv.projects:
        print(f"  [{proj.dates}] {proj.title}")
        if proj.company:
            print(f"          └─ {proj.company}")
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

    with open(sys.argv[1], "r", encoding="utf-8") as f:
        text = f.read()

    cv = parse_cv(text)
    print_cv(cv)
