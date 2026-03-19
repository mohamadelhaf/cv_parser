import streamlit as st
import tempfile
import os
import zipfile
import copy

st.set_page_config(page_title="DDC Lab", page_icon="📄", layout="wide")

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


def parse_intm_docx(input_path: str):
    from parser_v2 import parse_docx
    return parse_docx(input_path)


def parse_text_input(input_path: str):
    from extractor import extract_text
    from parser import parse_cv, get_savoir_faire
    from adapter import cvdata_to_parsed
    text = extract_text(input_path)
    cv_data = parse_cv(text)
    sf = get_savoir_faire(text)
    return cvdata_to_parsed(cv_data, savoir_faire=sf)


def generate_output(cv, template_path: str) -> bytes:
    from generator import generate_docx
    with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as f:
        output_path = f.name
    generate_docx(cv, output_path, template_path=template_path, ask_user=False)
    with open(output_path, "rb") as f:
        return f.read()


st.sidebar.title("📄 DDC Lab")
st.sidebar.markdown("Convert any CV into INTM format")
st.sidebar.divider()

uploaded_file = st.sidebar.file_uploader(
    "**Step 1:** Upload CV",
    type=["docx", "pdf", "txt"],
    help="INTM DOCX, regular DOCX, PDF, or TXT"
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
        help="Any existing INTM DOCX for styling"
    )
    if template_file:
        st.sidebar.success("✅ Template loaded")
    else:
        st.sidebar.warning("⚠️ Template required to generate output")


if not uploaded_file:
    st.title("📄 DDC Lab")
    st.markdown("""
    **Convert any CV into INTM-formatted Word document.**

    👈 Upload a file in the sidebar to get started.

    **Supported:** INTM DOCX, regular DOCX, PDF, TXT
    """)
    st.stop()

if needs_template and not template_file:
    st.title("📄 DDC Lab")
    st.info("👈 Upload an INTM template DOCX in the sidebar to continue.")
    st.markdown("Any INTM DDC will work as a template — it doesn't matter whose it is.")
    st.stop()


ext = os.path.splitext(uploaded_file.name)[1].lower()
input_path = save_temp(uploaded_file.getvalue(), ext)
template_path = input_path if is_intm else save_temp(template_file.getvalue(), ".docx")

try:
    cv = parse_intm_docx(input_path) if is_intm else parse_text_input(input_path)
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


tab_profile, tab_sections, tab_generate = st.tabs(["👤 Profile", "📋 Sections", "📥 Generate"])


with tab_profile:
    st.header("Profile")
    st.caption(f"Parsed via {'INTM style-based parser' if parse_mode == 'intm' else 'text-based parser'}")
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

            # Header + delete
            c_h, c_d = st.columns([5, 1])
            with c_h:
                section.header = st.text_input("Section name", value=section.header, key=f"h_{i}")
            with c_d:
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("🗑️ Delete", key=f"ds_{i}"):
                    sections_to_delete.append(i)

            # ---- TABLE ----
            if section.table_rows:
                st.markdown("##### Table rows")
                rows_del = []
                for j, row in enumerate(section.table_rows):
                    c1, c2, c3 = st.columns([3, 5, 1])
                    with c1:
                        row.left = st.text_input("L", value=row.left, key=f"tl_{i}_{j}", label_visibility="collapsed")
                    with c2:
                        row.right = st.text_input("R", value=row.right, key=f"tr_{i}_{j}", label_visibility="collapsed")
                    with c3:
                        if st.button("✕", key=f"dtr_{i}_{j}"):
                            rows_del.append(j)
                for j in sorted(rows_del, reverse=True):
                    section.table_rows.pop(j)
                if st.button("➕ Add row", key=f"atr_{i}"):
                    from parser_v2 import TableRow
                    section.table_rows.append(TableRow(left="", right=""))
                    st.rerun()

            # ---- BULLETS ----
            if section.bullet_items:
                st.markdown("##### Bullets")
                bul_del = []
                for j, item in enumerate(section.bullet_items):
                    c1, c2 = st.columns([9, 1])
                    with c1:
                        section.bullet_items[j] = st.text_input("B", value=item, key=f"bl_{i}_{j}", label_visibility="collapsed")
                    with c2:
                        if st.button("✕", key=f"dbl_{i}_{j}"):
                            bul_del.append(j)
                for j in sorted(bul_del, reverse=True):
                    section.bullet_items.pop(j)
                if st.button("➕ Add bullet", key=f"abl_{i}"):
                    section.bullet_items.append("")
                    st.rerun()

            # ---- EXPERIENCES ----
            if section.experience_blocks:
                for k, exp in enumerate(section.experience_blocks):
                    st.divider()

                    # Title + delete experience
                    c_t, c_de = st.columns([8, 1])
                    with c_t:
                        exp.title_line = st.text_input("Title", value=exp.title_line, key=f"et_{i}_{k}")
                    with c_de:
                        st.markdown("<br>", unsafe_allow_html=True)
                        if st.button("🗑️", key=f"dex_{i}_{k}"):
                            section.experience_blocks.pop(k)
                            st.rerun()

                    if exp.poste:
                        exp.poste = st.text_input("Poste", value=exp.poste, key=f"ep_{i}_{k}")

                    # Sub-sections
                    for s_idx, (sub_header, items) in enumerate(exp.sub_sections):
                        st.markdown(f"**{sub_header}**" if sub_header else "**Content:**")

                        items_del = []
                        for ii, item in enumerate(items):
                            c1, c2 = st.columns([9, 1])
                            with c1:
                                items[ii] = st.text_input("I", value=item, key=f"ei_{i}_{k}_{s_idx}_{ii}", label_visibility="collapsed")
                            with c2:
                                if st.button("✕", key=f"dei_{i}_{k}_{s_idx}_{ii}"):
                                    items_del.append(ii)
                        for idx in sorted(items_del, reverse=True):
                            items.pop(idx)

                        if st.button(f"➕ Add item", key=f"aei_{i}_{k}_{s_idx}"):
                            items.append("")
                            st.rerun()

                    # Add sub-section
                    if st.button("➕ Add sub-section", key=f"ass_{i}_{k}"):
                        exp.sub_sections.append(("ROLE :", [""]))
                        st.rerun()

                # Add experience entry
                st.divider()
                if st.button("➕ Add experience entry", key=f"aex_{i}"):
                    from parser_v2 import ExperienceBlock
                    section.experience_blocks.append(
                        ExperienceBlock(
                            title_line="",
                            poste="",
                            sub_sections=[("ROLE :", [""]), ("Environnement technique :", [""])],
                        )
                    )
                    st.rerun()

            # ---- EMPTY SECTION ----
            if not section.table_rows and not section.bullet_items and not section.experience_blocks:
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
                            ExperienceBlock(title_line="", poste="",
                                           sub_sections=[("ROLE :", [""]), ("Environnement technique :", [""])])
                        )
                        st.rerun()

    # Apply deletions
    if sections_to_delete:
        for i in sorted(sections_to_delete, reverse=True):
            cv_edit.sections.pop(i)
        st.rerun()

    # ========== ADD NEW SECTION ==========
    st.divider()
    st.subheader("➕ Add new section")

    c_name, c_type, c_pos = st.columns([3, 2, 2])
    with c_name:
        new_name = st.text_input("Section name", value="", key="new_sec_name")
    with c_type:
        new_type = st.selectbox("Type", ["Bullet list", "Table (2 columns)", "Experiences"], key="new_sec_type")
    with c_pos:
        positions = ["At the end"] + [f"Before: {s.header}" for s in cv_edit.sections]
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
                    ExperienceBlock(title_line="", poste="",
                                   sub_sections=[("ROLE :", [""]), ("Environnement technique :", [""])])
                ]

            if new_pos == "At the end":
                cv_edit.sections.append(ns)
            else:
                target = new_pos.replace("Before: ", "")
                idx = next((j for j, s in enumerate(cv_edit.sections) if s.header == target), len(cv_edit.sections))
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
        icon = "📊" if "table" in s.content_type else "📝" if s.content_type == "bullets" else "💼"
        count = len(s.table_rows) + len(s.bullet_items) + len(s.experience_blocks)
        st.markdown(f"  {icon} **{s.header}** ({count} items)")

    st.divider()

    # Output filename
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