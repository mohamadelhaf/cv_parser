import sys
import os
import zipfile


def _is_intm_format(path: str) -> bool:
    try:
        with zipfile.ZipFile(path) as z:
            header_rels = [f for f in z.namelist()
                           if "header" in f.lower() and f.endswith(".rels")]
            for rel_file in header_rels:
                content = z.read(rel_file).decode("utf-8")
                if "image" in content.lower():
                    return True
        return False
    except Exception:
        return False


def _ensure_template(args_list, position=3):
    template_path = args_list[position] if len(args_list) > position else None
    if not template_path:
        template_path = input("Template DOCX path: ").strip()
    if not template_path or not os.path.exists(template_path):
        print(f"❌ Template not found: {template_path}")
        print("   For non-INTM input, a template DOCX is required for styling.")
        print('   Usage: python main.py "input.pdf" "output.docx" "template.docx"')
        sys.exit(1)
    return template_path


def _run_intm_pipeline(input_path, output_path, template_override=None):
    from parser_v2 import parse_docx, print_parsed
    from generator import generate_docx

    template_path = template_override or input_path

    print(f"📄 Reading INTM DOCX: {input_path}")
    cv = parse_docx(input_path)
    print_parsed(cv)

    print(f"📝 Generating: {output_path}")
    generate_docx(
        cv,
        output_path,
        template_path=template_path,
        ask_user=True,
    )


def _run_text_pipeline(input_path, output_path, template_path):
    from extractor import extract_text
    from parser import parse_cv, print_cv, get_savoir_faire
    from adapter import cvdata_to_parsed
    from parser_v2 import print_parsed
    from generator import generate_docx

    print(f"📄 Reading: {input_path}")
    text = extract_text(input_path)

    print("🔍 Parsing CV text...")
    cv_data = parse_cv(text)
    savoir_faire = get_savoir_faire(text)
    print_cv(cv_data)

    print("🔄 Converting to INTM structure...")
    cv = cvdata_to_parsed(cv_data, savoir_faire=savoir_faire)
    print_parsed(cv)

    print(f"📝 Generating: {output_path}")
    generate_docx(
        cv,
        output_path,
        template_path=template_path,
        ask_user=True,
    )


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print('  python main.py "intm_ddc.docx" "output.docx"')
        print('  python main.py "regular_cv.docx" "output.docx" "template.docx"')
        print('  python main.py "cv.pdf" "output.docx" "template.docx"')
        print('  python main.py "cv.txt" "output.docx" "template.docx"')
        print()
        print("INTM DOCX files are auto-detected by their header logo.")
        print("All other formats require a template DOCX for styling.")
        sys.exit(1)

    input_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else "output.docx"

    if not os.path.exists(input_path):
        print(f"❌ Input file not found: {input_path}")
        sys.exit(1)

    ext = os.path.splitext(input_path)[1].lower()

    if ext == ".docx":
        if _is_intm_format(input_path):
            print("✅ INTM logo detected in header — using structure-preserving pipeline")
            template_override = sys.argv[3] if len(sys.argv) > 3 else None
            _run_intm_pipeline(input_path, output_path, template_override)
        else:
            print("ℹ️  No INTM logo found — using text-based parsing")
            template_path = _ensure_template(sys.argv, position=3)
            _run_text_pipeline(input_path, output_path, template_path)

    elif ext in (".pdf", ".txt", ".md"):
        template_path = _ensure_template(sys.argv, position=3)
        _run_text_pipeline(input_path, output_path, template_path)

    else:
        print(f"❌ Unsupported format: {ext}")
        print("   Supported: .docx, .pdf, .txt")
        sys.exit(1)


if __name__ == "__main__":
    main()