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
    ]
    for i, term in enumerate(tech_terms):
        placeholder = f"__TECH{i}__"
        if term in text:
            text = text.replace(term, placeholder)
            protected[placeholder] = term

    # Rule 1: lowercase followed by Uppercase (not after slash or dot)
    # "rapportsPower" → "rapports Power"
    text = re.sub(r"([a-zàâäéèêëïîôùûüÿç])([A-ZÀÂÄÉÈÊËÏÎÔÙÛÜŸÇ])", r"\1 \2", text)

    # Rule 2: digit followed by Uppercase letter
    # "2Systèmes" → "2 Systèmes"
    text = re.sub(r"(\d)([A-ZÀÂÄÉÈÊËÏÎÔÙÛÜŸÇ][a-zàâäéèêëïîôùûüÿç])", r"\1 \2", text)

    # Rule 3: closing paren/bracket followed by lowercase
    # ")approche" → ") approche"
    text = re.sub(r"(\))([a-zàâäéèêëïîôùûüÿçA-Z])", r"\1 \2", text)

    # Rule 4: letter followed by opening paren (but not common patterns like "AS/400(")
    # "AS/400(fichiers" → "AS/400 (fichiers"
    text = re.sub(r"([a-zàâäéèêëïîôùûüÿç0-9])(\()", r"\1 \2", text)

    # Rule 5: period followed by Uppercase (sentence boundary)
    # "production.Note" → "production. Note"
    text = re.sub(r"\.([A-ZÀÂÄÉÈÊËÏÎÔÙÛÜŸÇ])", r". \1", text)

    # Rule 6: semicolon followed by letter with no space
    # "relationnelle;API" → "relationnelle; API"
    text = re.sub(r";([A-Za-zàâäéèêëïîôùûüÿç])", r"; \1", text)

    # Rule 7: colon followed by letter with no space (but not in time like "12:30")
    # ":ETL" → ": ETL" but keep "12:30"
    text = re.sub(r":([A-Za-zàâäéèêëïîôùûüÿç])", r": \1", text)

    # Rule 8: UPPERCASE block (3+ chars) followed by lowercase (2+ chars)
    # "RESTpour" → "REST pour", "IBMpour" → "IBM pour"
    # Requires 3+ uppercase to avoid splitting names like "ELhaf"
    text = re.sub(
        r"([A-ZÀÂÄÉÈÊËÏÎÔÙÛÜŸÇ]{3,})([a-zàâäéèêëïîôùûüÿç]{2,})",
        r"\1 \2",
        text,
    )

    # Rule 9: plus sign glued to words on either side
    # "Boot+base" → "Boot + base", "Boot+ base" → "Boot + base"
    text = re.sub(r"(\w)\+(\w)", r"\1 + \2", text)
    text = re.sub(r"(\w)\+\s", r"\1 + ", text)
    text = re.sub(r"\s\+(\w)", r" + \1", text)

    # Restore protected tech terms
    for placeholder, term in protected.items():
        text = text.replace(placeholder, term)

    # Clean up any double spaces we may have introduced
    text = re.sub(r"  +", " ", text)

    return text


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
            
            # Check next line for end date
            next_stripped = lines[i + 1].strip()
            m2_date = just_date.match(next_stripped)
            m2_with_text = end_date_with_text.match(next_stripped)
            
            if m2_date:
                # Next line is just an end date
                end_date = m2_date.group(1)
                result.append(f"{start_date} – {end_date}")
                result.append(after_dash)
                i += 2
                continue
            elif m2_with_text:
                # Next line is end date + bullet text
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
    # Extract "signature" chars (remove spaces to match content regardless of spacing)
    target_sig = re.sub(r"\s+", "", target_lower)

    if len(target_sig) < 10:
        return None

    best_match = None
    best_score = 0

    for cand in candidate_lines:
        cand_sig = re.sub(r"\s+", "", cand.lower())
        # Check overlap: how many chars of target appear in candidate (order-free)
        if not cand_sig:
            continue
        # Simple ratio: length of shorter / length of longer
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
            # This line looks glued — try to find a better version in pypdf
            match = _find_best_match(stripped, pypdf_lines)
            if match:
                pypdf_score = _line_glue_score(match.strip())
                if pypdf_score < plumber_score:
                    # pypdf's version is less glued — use it
                    result.append(match)
                    continue

        result.append(line)

    return "\n".join(result)


def extract_from_pdf(path: str) -> str:
    plumber_text = ""
    pypdf_text = ""

    # Extract with both
    try:
        plumber_text = _extract_pdf_pdfplumber(path)
    except Exception:
        pass
    try:
        pypdf_text = _extract_pdf_pypdf(path)
    except Exception:
        pass

    # If one failed, use the other
    if not plumber_text.strip() and not pypdf_text.strip():
        return ""
    if not plumber_text.strip():
        text = pypdf_text
    elif not pypdf_text.strip():
        text = plumber_text
    else:
        # Step 1: Fix split date lines on pdfplumber FIRST
        # (before hybrid swap, so dates don't get lost)
        plumber_fixed = _merge_split_date_lines(plumber_text)

        # Step 2: Line-by-line hybrid (pdfplumber base, swap in pypdf where less glued)
        text = _hybrid_line_merge(plumber_fixed, pypdf_text)

    # Step 3: Fix remaining glued words with regex
    text = _fix_glued_words(text)

    return text


def extract_from_docx(path: str) -> str:
    from docx import Document

    doc = Document(path)
    lines = []
    
    # Build a queue of body-level Paragraph objects
    # doc.paragraphs only contains body-level <w:p>, not ones inside tables
    para_queue = list(doc.paragraphs)
    para_idx = 0

    for element in doc.element.body:
        tag = element.tag.split("}")[-1]

        if tag == "p":
            # Match this element to the next body-level paragraph
            if para_idx < len(para_queue) and para_queue[para_idx]._p is element:
                text = para_queue[para_idx].text
                # Clean: replace tab+newline (heading patterns) with space
                text = text.replace("\t\n", " ").replace("\n", " ")
                # Replace non-breaking spaces with regular spaces
                text = text.replace("\xa0", " ")
                lines.append(text)
                para_idx += 1
            else:
                # Fallback: manual extraction
                texts = []
                for node in element.iter():
                    node_tag = node.tag.split("}")[-1]
                    if node_tag == "t" and node.text:
                        texts.append(node.text)
                lines.append("".join(texts))

        elif tag == "tbl":
            # Tables: read row by row, tab-separated
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

    # Apply glue-fix regex for any remaining issues
    text = "\n".join(lines)
    text = _fix_glued_words(text)
    return text


def extract_from_txt(path: str) -> str:
    """Read plain text file."""
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