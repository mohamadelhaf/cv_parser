import streamlit as st
import tempfile
import os
import zipfile
import copy

from dotenv import load_dotenv
load_dotenv()

st.set_page_config(page_title="DDC Lab", page_icon="📄", layout="wide")


# ═══════════════════════════════════════════════════════════════════
# Shared helpers
# ═══════════════════════════════════════════════════════════════════

def is_intm_format(file_bytes: bytes) -> bool:
    try:
        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name
        with zipfile.ZipFile(tmp_path) as z:
            header_rels = [f for f in z.namelist()
                           if "header" in f.lower() and f.endswith(".rels")]
            for rel_file in header_rels:
                content = z.read(rel_file).decode("utf-8")
                if "image" in content.lower():
                    return True
        return False
    except Exception:
        return False


def save_temp(file_bytes: bytes, suffix: str) -> str:
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        f.write(file_bytes)
        return f.name


def parse_cv_file(file_bytes: bytes, filename: str):
    """Parse a CV file (any format) into a ParsedCV object."""
    ext = os.path.splitext(filename)[1].lower()
    tmp_path = save_temp(file_bytes, ext)

    if ext == ".docx" and is_intm_format(file_bytes):
        from parser_v2 import parse_docx
        return parse_docx(tmp_path), "intm"
    else:
        from parser import parse_file_with_mistral
        return parse_file_with_mistral(tmp_path), "text"


def extract_offer_text(offer_file=None, offer_text_input=""):
    """Get offer text from file or text input."""
    if offer_file is not None:
        ext = os.path.splitext(offer_file.name)[1].lower()
        tmp_path = save_temp(offer_file.getvalue(), ext)
        from extractor import extract_text
        return extract_text(tmp_path)
    return offer_text_input.strip()


def generate_output(cv, template_path: str) -> bytes:
    from generator import generate_docx
    with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as f:
        output_path = f.name
    generate_docx(cv, output_path, template_path=template_path, ask_user=False)
    with open(output_path, "rb") as f:
        return f.read()


# ═══════════════════════════════════════════════════════════════════
# Sidebar — Mode selector + API key
# ═══════════════════════════════════════════════════════════════════

st.sidebar.title("📄 DDC Lab")

mode = st.sidebar.radio(
    "Mode",
    ["🔄 Convert CV", "🎯 Match CV ↔ Offer", "📊 Rank CVs"],
    key="app_mode",
)

st.sidebar.divider()

# API key (loaded from .env file)
api_key = os.environ.get("MISTRAL_API_KEY", "")

if mode in ["🎯 Match CV ↔ Offer", "📊 Rank CVs"]:
    if api_key:
        st.sidebar.success("✅ API key loaded")
    else:
        st.sidebar.error("❌ API key missing — add ANTHROPIC_API_KEY to your .env file")
    st.sidebar.divider()


# ═══════════════════════════════════════════════════════════════════
# MODE 1: Convert CV (existing flow — unchanged)
# ═══════════════════════════════════════════════════════════════════

if mode == "🔄 Convert CV":
    st.sidebar.markdown("Convert any CV into INTM format")
    st.sidebar.divider()

    uploaded_file = st.sidebar.file_uploader(
        "**Step 1:** Upload CV",
        type=["docx", "pdf", "txt"],
        help="INTM DOCX, regular DOCX, PDF, or TXT",
        key="convert_cv_upload",
    )

    is_intm = False
    needs_template = False
    template_file = None

    if uploaded_file:
        ext = os.path.splitext(uploaded_file.name)[1].lower()
        if ext == ".docx":
            is_intm = is_intm_format(uploaded_file.getvalue())
            if is_intm:
                st.sidebar.success("✅ INTM template detected")
            else:
                needs_template = True
                st.sidebar.info("ℹ️ Regular DOCX — upload a template below")
        elif ext in (".pdf", ".txt", ".md"):
            needs_template = True
            st.sidebar.info(f"ℹ️ {ext.upper()} file — upload a template below")

    if needs_template:
        template_file = st.sidebar.file_uploader(
            "**Step 2:** Upload INTM Template",
            type=["docx"],
            key="template_uploader",
            help="Any existing INTM DOCX for styling",
        )
        if template_file:
            st.sidebar.success("✅ Template loaded")
        else:
            st.sidebar.warning("⚠️ Template required to generate output")

    if not uploaded_file:
        st.title("📄 DDC Lab — Convert")
        st.markdown("""
        **Convert any CV into INTM-formatted Word document.**

        👈 Upload a file in the sidebar to get started.

        **Supported:** INTM DOCX, regular DOCX, PDF, TXT
        """)
        st.stop()

    if needs_template and not template_file:
        st.title("📄 DDC Lab — Convert")
        st.info("👈 Upload an INTM template DOCX in the sidebar to continue.")
        st.markdown("Any INTM DDC will work as a template — it doesn't matter whose it is.")
        st.stop()

    # Parse
    ext = os.path.splitext(uploaded_file.name)[1].lower()
    input_path = save_temp(uploaded_file.getvalue(), ext)
    template_path = input_path if is_intm else save_temp(template_file.getvalue(), ".docx")

    try:
        if is_intm:
            from parser_v2 import parse_docx as _parse_docx
            cv = _parse_docx(input_path)
        else:
            from parser import parse_file_with_mistral
            cv = parse_file_with_mistral(input_path)
        parse_mode = "intm" if is_intm else "text"
    except Exception as e:
        st.error(f"❌ Error parsing: {e}")
        st.exception(e)
        st.stop()

    file_key = f"{uploaded_file.name}_{uploaded_file.size}"
    if st.session_state.get("_file_key") != file_key:
        st.session_state.cv = copy.deepcopy(cv)
        st.session_state._file_key = file_key
        st.session_state._template_path = template_path

    cv_edit = st.session_state.cv
    template_path = st.session_state._template_path

    tab_profile, tab_sections, tab_generate = st.tabs(
        ["👤 Profile", "📋 Sections", "📥 Generate"]
    )

    with tab_profile:
        st.header("Profile")
        st.caption(
            f"Parsed via {'INTM style-based parser' if parse_mode == 'intm' else 'text-based parser'}"
        )
        col1, col2 = st.columns(2)
        with col1:
            cv_edit.profile.name = st.text_input("Name", value=cv_edit.profile.name)
            cv_edit.profile.title = st.text_input("Title / Role", value=cv_edit.profile.title)
        with col2:
            cv_edit.profile.language = st.text_input("Language", value=cv_edit.profile.language)
            cv_edit.profile.years_experience = st.text_input(
                "Years of experience", value=cv_edit.profile.years_experience
            )

    with tab_sections:
        st.header("Sections")
        st.caption(f"{len(cv_edit.sections)} sections")

        sections_to_delete = []

        for i, section in enumerate(cv_edit.sections):
            parts = []
            if section.table_rows:
                parts.append(f"{len(section.table_rows)} rows")
            if section.bullet_items:
                parts.append(f"{len(section.bullet_items)} bullets")
            if section.experience_blocks:
                parts.append(f"{len(section.experience_blocks)} entries")
            summary = ", ".join(parts) if parts else "empty"

            with st.expander(f"**{section.header}** — {summary}", expanded=False):
                c_h, c_d = st.columns([5, 1])
                with c_h:
                    section.header = st.text_input(
                        "Section name", value=section.header, key=f"h_{i}"
                    )
                with c_d:
                    st.markdown("<br>", unsafe_allow_html=True)
                    if st.button("🗑️ Delete", key=f"ds_{i}"):
                        sections_to_delete.append(i)

                if section.table_rows:
                    st.markdown("##### Table rows")
                    rows_del = []
                    for j, row in enumerate(section.table_rows):
                        c1, c2, c3 = st.columns([3, 5, 1])
                        with c1:
                            row.left = st.text_input(
                                "L", value=row.left, key=f"tl_{i}_{j}", label_visibility="collapsed"
                            )
                        with c2:
                            row.right = st.text_input(
                                "R", value=row.right, key=f"tr_{i}_{j}", label_visibility="collapsed"
                            )
                        with c3:
                            if st.button("✕", key=f"dtr_{i}_{j}"):
                                rows_del.append(j)
                    for j in sorted(rows_del, reverse=True):
                        section.table_rows.pop(j)
                    if st.button("➕ Add row", key=f"atr_{i}"):
                        from parser_v2 import TableRow
                        section.table_rows.append(TableRow(left="", right=""))
                        st.rerun()

                if section.bullet_items:
                    st.markdown("##### Bullets")
                    bul_del = []
                    for j, item in enumerate(section.bullet_items):
                        c1, c2 = st.columns([9, 1])
                        with c1:
                            section.bullet_items[j] = st.text_input(
                                "B", value=item, key=f"bl_{i}_{j}", label_visibility="collapsed"
                            )
                        with c2:
                            if st.button("✕", key=f"dbl_{i}_{j}"):
                                bul_del.append(j)
                    for j in sorted(bul_del, reverse=True):
                        section.bullet_items.pop(j)
                    if st.button("➕ Add bullet", key=f"abl_{i}"):
                        section.bullet_items.append("")
                        st.rerun()

                if section.experience_blocks:
                    for k, exp in enumerate(section.experience_blocks):
                        st.divider()
                        c_t, c_de = st.columns([8, 1])
                        with c_t:
                            exp.title_line = st.text_input(
                                "Title", value=exp.title_line, key=f"et_{i}_{k}"
                            )
                        with c_de:
                            st.markdown("<br>", unsafe_allow_html=True)
                            if st.button("🗑️", key=f"dex_{i}_{k}"):
                                section.experience_blocks.pop(k)
                                st.rerun()

                        if exp.poste:
                            exp.poste = st.text_input(
                                "Poste", value=exp.poste, key=f"ep_{i}_{k}"
                            )

                        for s_idx, (sub_header, items) in enumerate(exp.sub_sections):
                            st.markdown(
                                f"**{sub_header}**" if sub_header else "**Content:**"
                            )
                            items_del = []
                            for ii, item in enumerate(items):
                                c1, c2 = st.columns([9, 1])
                                with c1:
                                    items[ii] = st.text_input(
                                        "I",
                                        value=item,
                                        key=f"ei_{i}_{k}_{s_idx}_{ii}",
                                        label_visibility="collapsed",
                                    )
                                with c2:
                                    if st.button("✕", key=f"dei_{i}_{k}_{s_idx}_{ii}"):
                                        items_del.append(ii)
                            for idx in sorted(items_del, reverse=True):
                                items.pop(idx)
                            if st.button(f"➕ Add item", key=f"aei_{i}_{k}_{s_idx}"):
                                items.append("")
                                st.rerun()

                        if st.button("➕ Add sub-section", key=f"ass_{i}_{k}"):
                            exp.sub_sections.append(("ROLE :", [""]))
                            st.rerun()

                    st.divider()
                    if st.button("➕ Add experience entry", key=f"aex_{i}"):
                        from parser_v2 import ExperienceBlock
                        section.experience_blocks.append(
                            ExperienceBlock(
                                title_line="",
                                poste="",
                                sub_sections=[
                                    ("ROLE :", [""]),
                                    ("Environnement technique :", [""]),
                                ],
                            )
                        )
                        st.rerun()

                if (
                    not section.table_rows
                    and not section.bullet_items
                    and not section.experience_blocks
                ):
                    st.info("Empty section — choose content type:")
                    c1, c2, c3 = st.columns(3)
                    with c1:
                        if st.button("➕ Table", key=f"aet_{i}"):
                            from parser_v2 import TableRow
                            section.content_type = "table"
                            section.table_rows.append(TableRow(left="", right=""))
                            st.rerun()
                    with c2:
                        if st.button("➕ Bullets", key=f"aeb_{i}"):
                            section.content_type = "bullets"
                            section.bullet_items.append("")
                            st.rerun()
                    with c3:
                        if st.button("➕ Experiences", key=f"aee_{i}"):
                            from parser_v2 import ExperienceBlock
                            section.content_type = "experiences"
                            section.experience_blocks.append(
                                ExperienceBlock(
                                    title_line="",
                                    poste="",
                                    sub_sections=[
                                        ("ROLE :", [""]),
                                        ("Environnement technique :", [""]),
                                    ],
                                )
                            )
                            st.rerun()

        if sections_to_delete:
            for i in sorted(sections_to_delete, reverse=True):
                cv_edit.sections.pop(i)
            st.rerun()

        st.divider()
        st.subheader("➕ Add new section")
        c_name, c_type, c_pos = st.columns([3, 2, 2])
        with c_name:
            new_name = st.text_input("Section name", value="", key="new_sec_name")
        with c_type:
            new_type = st.selectbox(
                "Type",
                ["Bullet list", "Table (2 columns)", "Experiences"],
                key="new_sec_type",
            )
        with c_pos:
            positions = ["At the end"] + [
                f"Before: {s.header}" for s in cv_edit.sections
            ]
            new_pos = st.selectbox("Position", positions, key="new_sec_pos")

        if st.button("➕ Add section", key="add_new_sec", use_container_width=True):
            if not new_name.strip():
                st.warning("Enter a section name.")
            else:
                from parser_v2 import Section, TableRow, ExperienceBlock

                ns = Section(header=new_name.strip())
                if new_type == "Bullet list":
                    ns.content_type = "bullets"
                    ns.bullet_items = [""]
                elif new_type == "Table (2 columns)":
                    ns.content_type = "table"
                    ns.table_rows = [TableRow(left="", right="")]
                else:
                    ns.content_type = "experiences"
                    ns.experience_blocks = [
                        ExperienceBlock(
                            title_line="",
                            poste="",
                            sub_sections=[
                                ("ROLE :", [""]),
                                ("Environnement technique :", [""]),
                            ],
                        )
                    ]

                if new_pos == "At the end":
                    cv_edit.sections.append(ns)
                else:
                    target = new_pos.replace("Before: ", "")
                    idx = next(
                        (
                            j
                            for j, s in enumerate(cv_edit.sections)
                            if s.header == target
                        ),
                        len(cv_edit.sections),
                    )
                    cv_edit.sections.insert(idx, ns)
                st.rerun()

    with tab_generate:
        st.header("Generate DOCX")

        col1, col2 = st.columns(2)
        with col1:
            st.markdown(f"**Name:** {cv_edit.profile.name}")
            st.markdown(f"**Title:** {cv_edit.profile.title}")
        with col2:
            st.markdown(f"**Language:** {cv_edit.profile.language}")
            st.markdown(f"**Experience:** {cv_edit.profile.years_experience}")

        st.divider()
        st.markdown(f"**{len(cv_edit.sections)} sections:**")
        for s in cv_edit.sections:
            icon = (
                "📊"
                if "table" in s.content_type
                else "📝" if s.content_type == "bullets" else "💼"
            )
            count = (
                len(s.table_rows) + len(s.bullet_items) + len(s.experience_blocks)
            )
            st.markdown(f"  {icon} **{s.header}** ({count} items)")

        st.divider()

        base_name = os.path.splitext(uploaded_file.name)[0]
        output_name = st.text_input(
            "📁 Output file name",
            value=f"INTM_DDC_{cv_edit.profile.name.replace(' ', '_')}",
            help="The .docx extension will be added automatically",
        )
        if not output_name.strip():
            output_name = f"{base_name}_INTM"
        if not output_name.endswith(".docx"):
            output_name = f"{output_name}.docx"

        if st.button("🚀 Generate DOCX", type="primary", use_container_width=True):
            with st.spinner("Generating..."):
                try:
                    docx_bytes = generate_output(cv_edit, template_path)
                    st.success("✅ Generated!")
                    st.download_button(
                        label=f"📥 Download {output_name}",
                        data=docx_bytes,
                        file_name=output_name,
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        use_container_width=True,
                    )
                except Exception as e:
                    st.error(f"❌ Error: {e}")
                    st.exception(e)


# ═══════════════════════════════════════════════════════════════════
# Shared UI helpers for match results
# ═══════════════════════════════════════════════════════════════════

def _score_color(score: int) -> str:
    if score >= 85:
        return "🟢"
    elif score >= 70:
        return "🔵"
    elif score >= 50:
        return "🟡"
    elif score >= 30:
        return "🟠"
    return "🔴"


def _score_label(score: int) -> str:
    if score >= 85:
        return "Excellent"
    elif score >= 70:
        return "Good"
    elif score >= 50:
        return "Partial"
    elif score >= 30:
        return "Weak"
    return "Poor"


def _render_score_bar(label: str, score: int):
    """Render a colored progress bar with label."""
    color = (
        "#1D9E75" if score >= 85
        else "#378ADD" if score >= 70
        else "#EF9F27" if score >= 50
        else "#D85A30" if score >= 30
        else "#E24B4A"
    )
    st.markdown(
        f"""
        <div style="margin-bottom: 8px;">
            <div style="display: flex; justify-content: space-between; margin-bottom: 2px;">
                <span style="font-size: 13px; font-weight: 500;">{label}</span>
                <span style="font-size: 13px; font-weight: 600;">{score}/100</span>
            </div>
            <div style="background: #e0e0e0; border-radius: 6px; height: 10px; overflow: hidden;">
                <div style="background: {color}; width: {score}%; height: 100%; border-radius: 6px;
                            transition: width 0.5s ease;"></div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_match_result(result, expanded=True):
    """Render a full MatchResult in the UI."""
    score = result.overall_score
    emoji = _score_color(score)
    label = _score_label(score)

    with st.expander(
        f"{emoji} **{result.candidate_name}** — {score}/100 ({label})",
        expanded=expanded,
    ):
        # Summary
        st.markdown(f"*{result.summary}*")
        st.divider()

        # Detail scores
        if result.detail_scores:
            st.markdown("**Score breakdown**")
            detail_labels = {
                "skills": "🛠️ Skills",
                "experience": "💼 Experience",
                "domain": "🏢 Domain",
                "education": "🎓 Education",
                "languages": "🌐 Languages",
            }
            for key, lbl in detail_labels.items():
                val = result.detail_scores.get(key, 0)
                _render_score_bar(lbl, val)
            st.divider()

        # Matched vs Missing skills
        col1, col2 = st.columns(2)
        with col1:
            if result.matched_skills:
                st.markdown("**✅ Matched skills**")
                for s in result.matched_skills:
                    st.markdown(f"- {s}")
        with col2:
            if result.missing_skills:
                st.markdown("**❌ Missing skills**")
                for s in result.missing_skills:
                    st.markdown(f"- {s}")

        # Strengths & Risks
        col3, col4 = st.columns(2)
        with col3:
            if result.strengths:
                st.markdown("**💪 Strengths**")
                for s in result.strengths:
                    st.markdown(f"- {s}")
        with col4:
            if result.risks:
                st.markdown("**⚠️ Risks**")
                for r in result.risks:
                    st.markdown(f"- {r}")

        # Experience match
        col5, col6 = st.columns(2)
        with col5:
            if result.matched_experience:
                st.markdown("**✅ Relevant experience**")
                for e in result.matched_experience:
                    st.markdown(f"- {e}")
        with col6:
            if result.experience_gaps:
                st.markdown("**❌ Experience gaps**")
                for g in result.experience_gaps:
                    st.markdown(f"- {g}")

        # Tailoring suggestions
        if result.tailoring_suggestions:
            st.divider()
            st.markdown("**💡 Tailoring suggestions**")
            for i, s in enumerate(result.tailoring_suggestions, 1):
                st.markdown(f"{i}. {s}")


def _render_offer_input(key_prefix: str):
    """Render offer input (file upload OR text paste) and return offer text."""
    offer_method = st.radio(
        "How to provide the job offer:",
        ["📄 Upload file", "📝 Paste text"],
        horizontal=True,
        key=f"{key_prefix}_offer_method",
    )

    offer_text = ""
    if offer_method == "📄 Upload file":
        offer_file = st.file_uploader(
            "Upload job offer",
            type=["pdf", "docx", "txt"],
            key=f"{key_prefix}_offer_file",
            help="PDF, DOCX, or TXT",
        )
        if offer_file:
            try:
                offer_text = extract_offer_text(offer_file=offer_file)
                st.success(f"✅ Extracted {len(offer_text)} characters from offer")
            except Exception as e:
                st.error(f"❌ Error reading offer: {e}")
    else:
        offer_text = st.text_area(
            "Paste the job offer here",
            height=250,
            key=f"{key_prefix}_offer_text",
            placeholder="Paste the full job description...",
        )

    return offer_text


# ═══════════════════════════════════════════════════════════════════
# MODE 2: Match single CV ↔ Offer
# ═══════════════════════════════════════════════════════════════════

if mode == "🎯 Match CV ↔ Offer":

    uploaded_cv = st.sidebar.file_uploader(
        "**Upload CV**",
        type=["docx", "pdf", "txt"],
        key="match_cv_upload",
        help="The CV to match against the offer",
    )

    if not uploaded_cv:
        st.title("🎯 Match CV ↔ Offer")
        st.markdown("""
        **Score how well a CV matches a job offer.**

        👈 Upload a CV in the sidebar, then provide the job offer below.

        The AI will analyze compatibility and give you:
        - Overall score (0–100)
        - Detailed breakdown by skills, experience, domain, education, languages
        - Matched & missing skills
        - Strengths, risks, and tailoring suggestions
        """)
        st.stop()

    # Parse CV
    try:
        cv, parse_mode = parse_cv_file(uploaded_cv.getvalue(), uploaded_cv.name)
        st.sidebar.success(f"✅ CV parsed: **{cv.profile.name}**")
    except Exception as e:
        st.error(f"❌ Error parsing CV: {e}")
        st.exception(e)
        st.stop()

    st.title("🎯 Match CV ↔ Offer")
    st.caption(f"CV: **{cv.profile.name}** — {cv.profile.title}")

    # Offer input
    st.subheader("Job Offer")
    offer_text = _render_offer_input("match")

    # Run matching
    st.divider()

    if not offer_text:
        st.info("👆 Provide a job offer above to start matching.")
        st.stop()

    if not api_key:
        st.warning("⚠️ Enter your Anthropic API key in the sidebar to run the match.")
        st.stop()

    if st.button("🚀 Run Match", type="primary", use_container_width=True):
        with st.spinner("🔍 Analyzing compatibility..."):
            try:
                from matcher import match_cv
                result = match_cv(cv, offer_text, api_key)
                st.session_state.match_result = result
            except Exception as e:
                st.error(f"❌ Matching error: {e}")
                st.exception(e)

    if "match_result" in st.session_state:
        st.divider()
        _render_match_result(st.session_state.match_result, expanded=True)


# ═══════════════════════════════════════════════════════════════════
# MODE 3: Rank multiple CVs against one offer
# ═══════════════════════════════════════════════════════════════════

if mode == "📊 Rank CVs":

    uploaded_cvs = st.sidebar.file_uploader(
        "**Upload CVs** (multiple)",
        type=["docx", "pdf", "txt"],
        accept_multiple_files=True,
        key="rank_cvs_upload",
        help="Upload all CVs to compare",
    )

    if not uploaded_cvs:
        st.title("📊 Rank CVs")
        st.markdown("""
        **Rank multiple CVs against a single job offer.**

        👈 Upload multiple CVs in the sidebar, then provide the job offer below.

        Each CV will be scored individually, then ranked from best to worst match.
        """)
        st.stop()

    st.sidebar.success(f"✅ {len(uploaded_cvs)} CV(s) uploaded")

    # Parse all CVs
    parsed_cvs = []
    parse_errors = []
    for f in uploaded_cvs:
        try:
            cv, _ = parse_cv_file(f.getvalue(), f.name)
            name = cv.profile.name or os.path.splitext(f.name)[0]
            parsed_cvs.append((name, cv))
            st.sidebar.caption(f"  ✓ {name}")
        except Exception as e:
            parse_errors.append((f.name, str(e)))
            st.sidebar.caption(f"  ✕ {f.name}")

    if parse_errors:
        for fname, err in parse_errors:
            st.sidebar.error(f"❌ {fname}: {err}")

    st.title("📊 Rank CVs")
    st.caption(f"{len(parsed_cvs)} CVs loaded")

    # Offer input
    st.subheader("Job Offer")
    offer_text = _render_offer_input("rank")

    st.divider()

    if not offer_text:
        st.info("👆 Provide a job offer above to start ranking.")
        st.stop()

    if not api_key:
        st.warning("⚠️ Enter your Anthropic API key in the sidebar to run ranking.")
        st.stop()

    if len(parsed_cvs) == 0:
        st.error("No CVs were successfully parsed. Check the files and try again.")
        st.stop()

    if st.button(
        f"🚀 Rank {len(parsed_cvs)} CVs",
        type="primary",
        use_container_width=True,
    ):
        progress_bar = st.progress(0, text="Starting...")
        status_text = st.empty()

        def update_progress(current, total):
            pct = current / total if total > 0 else 0
            progress_bar.progress(pct, text=f"Analyzing CV {current + 1}/{total}...")
            if current < total:
                name = parsed_cvs[current][0] if current < len(parsed_cvs) else ""
                status_text.caption(f"🔍 Matching: {name}")

        try:
            from matcher import rank_cvs
            ranking = rank_cvs(
                parsed_cvs, offer_text, api_key, progress_callback=update_progress
            )
            st.session_state.ranking_result = ranking
            progress_bar.progress(1.0, text="Done!")
            status_text.empty()
        except Exception as e:
            st.error(f"❌ Ranking error: {e}")
            st.exception(e)

    if "ranking_result" in st.session_state:
        ranking = st.session_state.ranking_result
        st.divider()

        # Summary table
        st.subheader("🏆 Ranking")

        for rank, result in enumerate(ranking.ranked_candidates, 1):
            emoji = _score_color(result.overall_score)
            label = _score_label(result.overall_score)

            # Quick summary row
            col_rank, col_name, col_score, col_label = st.columns([0.5, 4, 1.5, 1.5])
            with col_rank:
                if rank == 1:
                    st.markdown(f"### 🥇")
                elif rank == 2:
                    st.markdown(f"### 🥈")
                elif rank == 3:
                    st.markdown(f"### 🥉")
                else:
                    st.markdown(f"### #{rank}")
            with col_name:
                st.markdown(f"### {result.candidate_name}")
                st.caption(result.summary[:120] + "..." if len(result.summary) > 120 else result.summary)
            with col_score:
                st.markdown(f"### {emoji} {result.overall_score}/100")
            with col_label:
                st.markdown(f"### {label}")

        # Detailed results
        st.divider()
        st.subheader("📋 Detailed Results")

        for result in ranking.ranked_candidates:
            _render_match_result(result, expanded=False)