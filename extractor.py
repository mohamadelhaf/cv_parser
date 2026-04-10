import os
import re
import sys



def _extract_pdf_pypdf(path: str) -> str:
    from pypdf import PdfReader

    reader = PdfReader(path)
    pages = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            pages.append(text)
    return "\n".join(pages)


def _extract_pdf_pdfplumber(path: str) -> str:
    import pdfplumber

    pages = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                pages.append(text)
    return "\n".join(pages)


def _fix_glued_words(text: str) -> str:
    # Protect known tech terms from being split
    protected = {}
    tech_terms = [
        "JavaScript", "TypeScript", "Node.js", "Vue.js", "Express.js",
        "GitHub", "GitLab", "MongoDB", "PostgreSQL", "MySQL", "PhpMyAdmin",
        "PowerQuery", "PowerPoint", "Power BI", "OpenCV", "OpenStack",
        "TensorFlow", "PyTorch", "HuggingFace", "BitsAndBytes",
        "ShellExecute", "FindWindow", "AutoSys", "DataStage",
        "Spring Boot", "SpringBoot", "IntelliJ", "macOS", "DevOps",
        "scikit-learn", "NumPy", "FastAPI", "LabelImg",
        "BackOffice", "FrontOffice", "SharePoint",
        "PaaS", "SaaS", "IaaS",
    ]
    for i, term in enumerate(tech_terms):
        placeholder = f"__TECH{i}__"
        if term in text:
            text = text.replace(term, placeholder)
            protected[placeholder] = term

    # Rule 1: lowercase followed by Uppercase (not after slash or dot)
    text = re.sub(r"([a-zàâäéèêëïîôùûüÿç])([A-ZÀÂÄÉÈÊËÏÎÔÙÛÜŸÇ])", r"\1 \2", text)

    # Rule 2: digit followed by Uppercase letter
    text = re.sub(r"(\d)([A-ZÀÂÄÉÈÊËÏÎÔÙÛÜŸÇ][a-zàâäéèêëïîôùûüÿç])", r"\1 \2", text)

    # Rule 3: closing paren/bracket followed by letter
    text = re.sub(r"(\))([a-zàâäéèêëïîôùûüÿçA-Z])", r"\1 \2", text)

    # Rule 4: letter/digit followed by opening paren
    text = re.sub(r"([a-zàâäéèêëïîôùûüÿç0-9])(\()", r"\1 \2", text)

    # Rule 5: period followed by Uppercase (sentence boundary)
    text = re.sub(r"\.([A-ZÀÂÄÉÈÊËÏÎÔÙÛÜŸÇ])", r". \1", text)

    # Rule 6: semicolon followed by letter with no space
    text = re.sub(r";([A-Za-zàâäéèêëïîôùûüÿç])", r"; \1", text)

    # Rule 7: colon followed by letter with no space (but not in time like "12:30")
    text = re.sub(r":([A-Za-zàâäéèêëïîôùûüÿç])", r": \1", text)

    # Rule 8: UPPERCASE block (3+ chars) followed by lowercase (2+ chars)
    text = re.sub(
        r"([A-ZÀÂÄÉÈÊËÏÎÔÙÛÜŸÇ]{3,})([a-zàâäéèêëïîôùûüÿç]{2,})",
        r"\1 \2",
        text,
    )

    # Rule 9: plus sign glued to words on either side
    text = re.sub(r"(\w)\+(\w)", r"\1 + \2", text)
    text = re.sub(r"(\w)\+\s", r"\1 + ", text)
    text = re.sub(r"\s\+(\w)", r" + \1", text)

    # Restore protected tech terms
    for placeholder, term in protected.items():
        text = text.replace(placeholder, term)

    # Clean up any double spaces we may have introduced
    text = re.sub(r"  +", " ", text)

    return text


def _fix_triple_chars(text: str) -> str:
    lines = text.split("\n")
    result = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            result.append(line)
            continue

        # Check if the line has triple-char pattern
        words = stripped.split()
        triple_words = 0
        total_words = 0
        for w in words:
            if len(w) < 3:
                continue
            total_words += 1
            if len(w) % 3 == 0:
                is_triple = True
                for j in range(0, len(w), 3):
                    if j + 2 < len(w) and w[j] == w[j+1] == w[j+2]:
                        pass
                    else:
                        is_triple = False
                        break
                if is_triple:
                    triple_words += 1

        if total_words > 0 and triple_words / total_words > 0.4:
            new_words = []
            for w in words:
                if len(w) >= 3 and len(w) % 3 == 0:
                    collapsed = ""
                    is_triple = True
                    for j in range(0, len(w), 3):
                        if j + 2 < len(w) and w[j] == w[j+1] == w[j+2]:
                            collapsed += w[j]
                        else:
                            is_triple = False
                            break
                    if is_triple:
                        new_words.append(collapsed)
                    else:
                        new_words.append(w)
                else:
                    new_words.append(w)
            result.append(" ".join(new_words))
        else:
            result.append(line)

    return "\n".join(result)


def _strip_hellowork_header(text: str) -> str:
    lines = text.split("\n")
    result = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("CV envoyé par Hellowork"):
            continue
        result.append(line)
    return "\n".join(result)


def _strip_repeated_page_headers(text: str) -> str:
    lines = text.split("\n")
    if len(lines) < 20:
        return text

    from collections import Counter
    short_lines = Counter()
    for line in lines:
        stripped = line.strip()
        if stripped and len(stripped) < 60 and len(stripped.split()) <= 8:
            short_lines[stripped] += 1

    # Lines that appear 3+ times are likely page headers
    repeated = {line for line, count in short_lines.items() if count >= 3}

    if not repeated:
        return text

    seen = set()
    result = []
    for line in lines:
        stripped = line.strip()
        if stripped in repeated:
            if stripped not in seen:
                seen.add(stripped)
                result.append(line)
            # else skip
        else:
            result.append(line)

    return "\n".join(result)


def _strip_cv_page_header(text: str) -> str:
    lines = text.split("\n")
    if len(lines) < 10:
        return text

    # Find lines that start with "CV " and appear more than once
    from collections import Counter
    cv_lines = Counter()
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("CV ") and len(stripped) < 80:
            cv_lines[stripped] += 1

    repeated_cv = {line for line, count in cv_lines.items() if count >= 2}
    if not repeated_cv:
        return text

    seen = set()
    result = []
    for line in lines:
        stripped = line.strip()
        if stripped in repeated_cv:
            if stripped not in seen:
                seen.add(stripped)
                # Don't keep the "CV Name Title" line at all — it's just a header
                pass
            # skip all occurrences
        else:
            result.append(line)

    return "\n".join(result)


def _merge_split_date_lines(text: str) -> str:
    _MONTH = r"(?:Jan|Fev|F[ée]v|Mar|Avr|Mai|Juin|Jul|Juil|Aou|Ao[uû]t|Sep|Oct|Nov|Dec|D[ée]c)\w*\.?"

    # Pattern: "Month YYYY – <text>" where text is NOT another date
    partial_with_text = re.compile(
        rf"^((?:{_MONTH}\s+)?\d{{4}})\s*[–—\-]\s+(?!(?:{_MONTH}\s+)?\d{{4}})(.+)$",
        re.IGNORECASE,
    )
    # Pattern: "Month YYYY — <bullet text>" (end date stuck to bullet)
    end_date_with_text = re.compile(
        rf"^((?:{_MONTH}\s+)?\d{{4}})\s*[–—\-]\s*(.+)$",
        re.IGNORECASE,
    )
    # Pattern: just "Month YYYY" alone
    just_date = re.compile(
        rf"^((?:{_MONTH}\s+)?\d{{4}})\s*$",
        re.IGNORECASE,
    )

    lines = text.split("\n")
    result = []
    i = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        m1 = partial_with_text.match(stripped)
        if m1 and i + 1 < len(lines):
            start_date = m1.group(1)
            after_dash = m1.group(2)

            next_stripped = lines[i + 1].strip()
            m2_date = just_date.match(next_stripped)
            m2_with_text = end_date_with_text.match(next_stripped)

            if m2_date:
                end_date = m2_date.group(1)
                result.append(f"{start_date} – {end_date}")
                result.append(after_dash)
                i += 2
                continue
            elif m2_with_text:
                end_date = m2_with_text.group(1)
                bullet_text = m2_with_text.group(2).strip()
                result.append(f"{start_date} – {end_date}")
                result.append(after_dash)
                if bullet_text:
                    result.append(bullet_text)
                i += 2
                continue

        result.append(line)
        i += 1

    return "\n".join(result)


def _longest_word_len(line: str) -> int:
    words = line.split()
    return max((len(w) for w in words), default=0)


def _line_glue_score(line: str) -> float:
    longest = _longest_word_len(line)
    if longest > 30:
        return longest
    return 0


def _find_best_match(target_line: str, candidate_lines: list[str]) -> str | None:
    target_lower = target_line.lower()
    target_sig = re.sub(r"\s+", "", target_lower)

    if len(target_sig) < 10:
        return None

    best_match = None
    best_score = 0

    for cand in candidate_lines:
        cand_sig = re.sub(r"\s+", "", cand.lower())
        if not cand_sig:
            continue
        if target_sig in cand_sig or cand_sig in target_sig:
            score = min(len(target_sig), len(cand_sig)) / max(len(target_sig), len(cand_sig))
            if score > best_score and score > 0.6:
                best_score = score
                best_match = cand

    return best_match


def _hybrid_line_merge(plumber_text: str, pypdf_text: str) -> str:
    plumber_lines = plumber_text.split("\n")
    pypdf_lines = pypdf_text.split("\n")

    result = []
    for line in plumber_lines:
        stripped = line.strip()
        if not stripped:
            result.append(line)
            continue

        plumber_score = _line_glue_score(stripped)

        if plumber_score > 25:
            match = _find_best_match(stripped, pypdf_lines)
            if match:
                pypdf_score = _line_glue_score(match.strip())
                if pypdf_score < plumber_score:
                    result.append(match)
                    continue

        result.append(line)

    return "\n".join(result)


def _merge_broken_headers(text: str) -> str:
    # Known section header fragments that might get split
    # Format: (first_line_regex, second_line_regex) → these get merged
    splits = [
        # Single letter + rest: "C\nompétences", "E\nXPERIENCES", "F\nOR MATIONS"
        # The second line might have spaces (broken words) so we allow spaces
        (re.compile(r"^[A-ZÉÈÊËÀÂÄÎÏÔÙÛÜŸÇ]$"), re.compile(r"^[a-zéèêëàâäîïôùûüÿçA-ZÉÈÊËÀÂÄÎÏÔÙÛÜŸÇ\s]{3,}$")),
        # "EXPÉRIENCES" + "PROFESSIONNELLES"
        (re.compile(r"(?i)^EXP[ÉE]RIENCES?$"), re.compile(r"(?i)^PROFES+ION\w+$")),
        # "COMPÉTENCES" + "TECHNIQUES" / "FONCTIONNELLES" / "INFORMATIQUES"
        (re.compile(r"(?i)^COMP[ÉE]TENCES?$"), re.compile(r"(?i)^(?:TECHNIQUES?|FONCTIONNELLES?|INFORMATIQUES?|M[ÉE]THODOLOGIQUES?|CL[ÉE]S?|PROFES+IONNELLES?)$")),
        # "EXPÉRIENCE" + "PROFESSIONNELLE"
        (re.compile(r"(?i)^EXP[ÉE]RIENCE$"), re.compile(r"(?i)^PROFES+IONNELLE$")),
        # "FORMATION" + various continuations
        (re.compile(r"(?i)^FORMATIONS?$"), re.compile(r"(?i)^(?:ACAD[ÉE]MIQUES?|PROFES+IONNELLES?|ET\s+CERTIFICATIONS?)$")),
    ]

    lines = text.split("\n")
    result = []
    i = 0
    while i < len(lines):
        if i + 1 < len(lines):
            stripped = lines[i].strip()
            next_stripped = lines[i + 1].strip()
            merged = False
            for first_pat, second_pat in splits:
                if first_pat.match(stripped) and second_pat.match(next_stripped):
                    if len(stripped) == 1:
                        # Single letter merge: "F" + "OR MATIONS" -> "FORMATIONS"
                        # Remove internal spaces from the second part since it's a broken word
                        merged_text = stripped + next_stripped.replace(" ", "")
                    else:
                        merged_text = stripped + " " + next_stripped
                    result.append(merged_text)
                    i += 2
                    merged = True
                    break
            if merged:
                continue
        result.append(lines[i])
        i += 1
    return "\n".join(result)


def _merge_broken_date_ranges(text: str) -> str:
    lines = text.split("\n")
    result = []
    i = 0
    date_piece = re.compile(r"\d{2}/\d{4}")

    while i < len(lines):
        stripped = lines[i].rstrip()
        # Check if line ends with "MM/YYYY-" or "MM/YYYY –" pattern
        if re.search(r"\d{2}/\d{4}\s*[-–—]\s*$", stripped) and i + 1 < len(lines):
            next_stripped = lines[i + 1].strip()
            # Check if next line starts with a date
            if date_piece.match(next_stripped):
                # Merge: "12/2022-\n12/2025" → "12/2022- 12/2025"
                result.append(stripped + " " + next_stripped)
                i += 2
                continue
        result.append(lines[i])
        i += 1
    return "\n".join(result)


def _strip_private_use_chars(text: str) -> str:
    result = []
    for ch in text:
        cp = ord(ch)
        if 0xE000 <= cp <= 0xF8FF:
            # Map common Symbol font PUA chars to their intended meanings
            if cp in (0xF0A7, 0xF0B7, 0xF0B0):
                result.append("•")  # bullet
            elif cp == 0xF0D8:
                result.append("")   # arrow — just strip
            else:
                result.append(" ")  # replace unknown PUA with space
        elif cp == 0xFFFD:
            result.append("")       # replacement character — strip
        else:
            result.append(ch)
    return "".join(result)


def extract_from_pdf(path: str) -> str:
    plumber_text = ""
    pypdf_text = ""

    try:
        plumber_text = _extract_pdf_pdfplumber(path)
    except Exception:
        pass
    try:
        pypdf_text = _extract_pdf_pypdf(path)
    except Exception:
        pass

    if not plumber_text.strip() and not pypdf_text.strip():
        return ""
    if not plumber_text.strip():
        text = pypdf_text
    elif not pypdf_text.strip():
        text = plumber_text
    else:
        plumber_fixed = _merge_split_date_lines(plumber_text)
        text = _hybrid_line_merge(plumber_fixed, pypdf_text)

    # Post-processing pipeline
    text = _fix_triple_chars(text)
    text = _strip_hellowork_header(text)
    text = _strip_cv_page_header(text)
    text = _strip_repeated_page_headers(text)
    text = _merge_broken_headers(text)
    text = _merge_broken_date_ranges(text)
    text = _strip_private_use_chars(text)
    text = _fix_glued_words(text)

    return text


def extract_from_docx(path: str) -> str:
    from docx import Document

    doc = Document(path)
    lines = []

    para_queue = list(doc.paragraphs)
    para_idx = 0

    for element in doc.element.body:
        tag = element.tag.split("}")[-1]

        if tag == "p":
            if para_idx < len(para_queue) and para_queue[para_idx]._p is element:
                text = para_queue[para_idx].text
                text = text.replace("\t\n", " ").replace("\n", " ")
                text = text.replace("\xa0", " ")
                lines.append(text)
                para_idx += 1
            else:
                texts = []
                for node in element.iter():
                    node_tag = node.tag.split("}")[-1]
                    if node_tag == "t" and node.text:
                        texts.append(node.text)
                lines.append("".join(texts))

        elif tag == "tbl":
            for tr in element.iter():
                tr_tag = tr.tag.split("}")[-1]
                if tr_tag == "tr":
                    cells = []
                    for tc in tr.iter():
                        tc_tag = tc.tag.split("}")[-1]
                        if tc_tag == "tc":
                            cell_texts = []
                            for node in tc.iter():
                                node_tag = node.tag.split("}")[-1]
                                if node_tag == "t" and node.text:
                                    cell_texts.append(node.text)
                            cells.append(" ".join(cell_texts).strip())
                    if any(cells):
                        lines.append("\t".join(cells))

    text = "\n".join(lines)
    text = _fix_glued_words(text)
    return text


def extract_from_txt(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def extract_text(path: str) -> str:
    if not os.path.exists(path):
        raise FileNotFoundError(f"File not found: {path}")

    ext = os.path.splitext(path)[1].lower()

    extractors = {
        ".pdf": extract_from_pdf,
        ".docx": extract_from_docx,
        ".txt": extract_from_txt,
        ".md": extract_from_txt,
    }

    if ext not in extractors:
        supported = ", ".join(extractors.keys())
        raise ValueError(f"Unsupported format: {ext}. Supported: {supported}")

    text = extractors[ext](path)

    if not text.strip():
        print(f"⚠️  Warning: No text extracted from {path}")

    return text


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python extractor.py <file_path>")
        sys.exit(1)

    path = sys.argv[1]
    text = extract_text(path)
    print(f"📄 Extracted {len(text)} characters from {path}")
    print("=" * 60)
    print(text)
    print("=" * 60)