import streamlit as st
import tempfile
import os
import zipfile
import copy

st.set_page_config(page_title="DDC Lab", page_icon="📄", layout="wide")


def is_intm_format(file_bytes: bytes) -> bool:
    """
    Détecte si un fichier DOCX est un DDC INTM.
    Critère fiable : présence des styles personnalisés INTM
    ('Profil', 'Titre Référence', 'Profil : Experience')
    qui n'existent que dans les documents INTM.
    Un simple logo dans l'en-tête ne suffit pas — beaucoup de CVs en ont.
    """
    try:
        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name
        with zipfile.ZipFile(tmp_path) as z:
            if "word/styles.xml" not in z.namelist():
                return False
            styles_xml = z.read("word/styles.xml").decode("utf-8")
            # Les styles INTM sont uniques et ne se trouvent pas dans des CVs ordinaires
            intm_styles = ["Titre R&#xE9;f&#xE9;rence", "Titre Référence",
                           "Profil : Experience", "Profil : Exp&#xE9;rience"]
            return any(s in styles_xml for s in intm_styles)
    except Exception:
        return False


def save_temp(file_bytes: bytes, suffix: str) -> str:
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        f.write(file_bytes)
        return f.name


def parse_intm_docx(input_path: str):
    """Parse un DDC INTM existant — utilise le parseur basé sur les styles."""
    from parser_v2 import parse_docx
    return parse_docx(input_path)


def parse_text_input(input_path: str):
    """
    Parse n'importe quel CV (PDF, DOCX, TXT) avec Mistral AI.
    """
    from extractor import extract_text
    from parser import parse_with_mistral
    text = extract_text(input_path)
    return parse_with_mistral(text)


def generate_output(cv, template_path: str) -> bytes:
    from generator import generate_docx
    with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as f:
        output_path = f.name
    generate_docx(cv, output_path, template_path=template_path, ask_user=False)
    with open(output_path, "rb") as f:
        return f.read()


st.sidebar.title("📄 DDC Lab")
st.sidebar.markdown("Convertissez n'importe quel CV au format INTM")
st.sidebar.divider()

uploaded_file = st.sidebar.file_uploader(
    "**Étape 1 :** Importer le CV",
    type=["docx", "pdf", "txt"],
    help="DDC INTM, DOCX classique, PDF ou TXT"
)

is_intm = False
needs_template = False
template_file = None

if uploaded_file:
    ext = os.path.splitext(uploaded_file.name)[1].lower()
    if ext == ".docx":
        is_intm = is_intm_format(uploaded_file.getvalue())
        if is_intm:
            st.sidebar.success("✅ Document INTM détecté")
        else:
            needs_template = True
            st.sidebar.info("ℹ️ DOCX classique — vous pouvez importer un modèle INTM ci-dessous")
    elif ext in (".pdf", ".txt", ".md"):
        needs_template = True
        st.sidebar.info(f"ℹ️ Fichier {ext.upper()} — vous pouvez importer un modèle INTM ci-dessous")

if needs_template:
    template_file = st.sidebar.file_uploader(
        "**Étape 2 (optionnel) :** Importer un modèle INTM",
        type=["docx"],
        key="template_uploader",
        help="Importez un DDC INTM existant pour appliquer le bon style. Si absent, le style par défaut sera utilisé."
    )
    if template_file:
        st.sidebar.success("✅ Modèle chargé")
    else:
        st.sidebar.info("ℹ️ Sans modèle, le style par défaut sera appliqué")


if not uploaded_file:
    st.title("📄 DDC Lab")
    st.markdown("""
    **Convertissez n'importe quel CV en document Word au format INTM.**

    👈 Importez un fichier dans la barre latérale pour commencer.

    **Formats acceptés :** DDC INTM, DOCX classique, PDF, TXT
    """)
    st.stop()


ext = os.path.splitext(uploaded_file.name)[1].lower()
input_path = save_temp(uploaded_file.getvalue(), ext)

# Chemin du modèle : priorité au modèle importé, sinon fallback
if is_intm:
    template_path = input_path
elif template_file:
    template_path = save_temp(template_file.getvalue(), ".docx")
else:
    if ext == ".docx":
        template_path = input_path
    else:
        default_template = os.path.join(os.path.dirname(__file__), "template_default.docx")
        if os.path.exists(default_template):
            template_path = default_template
        else:
            st.warning("⚠️ Aucun modèle INTM trouvé. Importez un modèle pour un rendu correct.")
            st.info("Astuce : enregistrez un DDC INTM sous le nom 'template_default.docx' dans le dossier de l'application pour l'utiliser automatiquement.")
            st.stop()

try:
    with st.spinner("🤖 Analyse du CV avec Mistral AI..." if not is_intm else "📄 Lecture du document INTM..."):
        cv = parse_intm_docx(input_path) if is_intm else parse_text_input(input_path)
    parse_mode = "intm" if is_intm else "mistral"
except Exception as e:
    st.error(f"❌ Erreur lors de l'analyse : {e}")
    st.exception(e)
    st.stop()


file_key = f"{uploaded_file.name}_{uploaded_file.size}"
if st.session_state.get("_file_key") != file_key:
    st.session_state.cv = copy.deepcopy(cv)
    st.session_state._file_key = file_key
    st.session_state._template_path = template_path

cv_edit = st.session_state.cv
template_path = st.session_state._template_path


tab_profile, tab_sections, tab_generate = st.tabs(["👤 Profil", "📋 Sections", "📥 Générer"])


with tab_profile:
    st.header("Profil")
    st.caption(f"Analysé via {'le parseur INTM (styles)' if parse_mode == 'intm' else 'Mistral AI'}")
    col1, col2 = st.columns(2)
    with col1:
        cv_edit.profile.name = st.text_input("Nom", value=cv_edit.profile.name)
        cv_edit.profile.title = st.text_input("Titre / Poste", value=cv_edit.profile.title)
    with col2:
        cv_edit.profile.language = st.text_input("Langue", value=cv_edit.profile.language)
        cv_edit.profile.years_experience = st.text_input(
            "Années d'expérience", value=cv_edit.profile.years_experience
        )


with tab_sections:
    st.header("Sections")
    st.caption(f"{len(cv_edit.sections)} section(s)")

    sections_to_delete = []

    for i, section in enumerate(cv_edit.sections):
        parts = []
        if section.table_rows:
            parts.append(f"{len(section.table_rows)} ligne(s)")
        if section.bullet_items:
            parts.append(f"{len(section.bullet_items)} point(s)")
        if section.experience_blocks:
            parts.append(f"{len(section.experience_blocks)} expérience(s)")
        summary = ", ".join(parts) if parts else "vide"

        with st.expander(f"**{section.header}** — {summary}", expanded=False):

            c_h, c_d = st.columns([5, 1])
            with c_h:
                section.header = st.text_input("Nom de la section", value=section.header, key=f"h_{i}")
            with c_d:
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("🗑️ Supprimer", key=f"ds_{i}"):
                    sections_to_delete.append(i)

            # ── TABLEAU ──
            if section.table_rows:
                st.markdown("##### Lignes du tableau")
                rows_del = []
                for j, row in enumerate(section.table_rows):
                    c1, c2, c3 = st.columns([3, 5, 1])
                    with c1:
                        row.left = st.text_input("G", value=row.left, key=f"tl_{i}_{j}", label_visibility="collapsed")
                    with c2:
                        row.right = st.text_input("D", value=row.right, key=f"tr_{i}_{j}", label_visibility="collapsed")
                    with c3:
                        if st.button("✕", key=f"dtr_{i}_{j}"):
                            rows_del.append(j)
                for j in sorted(rows_del, reverse=True):
                    section.table_rows.pop(j)
                if st.button("➕ Ajouter une ligne", key=f"atr_{i}"):
                    from parser_v2 import TableRow
                    section.table_rows.append(TableRow(left="", right=""))
                    st.rerun()

            # ── POINTS ──
            if section.bullet_items:
                st.markdown("##### Points")
                bul_del = []
                for j, item in enumerate(section.bullet_items):
                    c1, c2 = st.columns([9, 1])
                    with c1:
                        section.bullet_items[j] = st.text_input("P", value=item, key=f"bl_{i}_{j}", label_visibility="collapsed")
                    with c2:
                        if st.button("✕", key=f"dbl_{i}_{j}"):
                            bul_del.append(j)
                for j in sorted(bul_del, reverse=True):
                    section.bullet_items.pop(j)
                if st.button("➕ Ajouter un point", key=f"abl_{i}"):
                    section.bullet_items.append("")
                    st.rerun()

            # ── EXPÉRIENCES ──
            if section.experience_blocks:
                for k, exp in enumerate(section.experience_blocks):
                    st.divider()

                    c_t, c_de = st.columns([8, 1])
                    with c_t:
                        exp.title_line = st.text_input("Titre", value=exp.title_line, key=f"et_{i}_{k}")
                    with c_de:
                        st.markdown("<br>", unsafe_allow_html=True)
                        if st.button("🗑️", key=f"dex_{i}_{k}"):
                            section.experience_blocks.pop(k)
                            st.rerun()

                    if exp.poste:
                        exp.poste = st.text_input("Poste", value=exp.poste, key=f"ep_{i}_{k}")

                    for s_idx, (sub_header, items) in enumerate(exp.sub_sections):
                        st.markdown(f"**{sub_header}**" if sub_header else "**Contenu :**")

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

                        if st.button("➕ Ajouter un élément", key=f"aei_{i}_{k}_{s_idx}"):
                            items.append("")
                            st.rerun()

                    if st.button("➕ Ajouter une sous-section", key=f"ass_{i}_{k}"):
                        exp.sub_sections.append(("ROLE :", [""]))
                        st.rerun()

                st.divider()
                if st.button("➕ Ajouter une expérience", key=f"aex_{i}"):
                    from parser_v2 import ExperienceBlock
                    section.experience_blocks.append(
                        ExperienceBlock(
                            title_line="",
                            poste="",
                            sub_sections=[("ROLE :", [""]), ("Environnement technique :", [""])],
                        )
                    )
                    st.rerun()

            # ── SECTION VIDE ──
            if not section.table_rows and not section.bullet_items and not section.experience_blocks:
                st.info("Section vide — choisissez un type de contenu :")
                c1, c2, c3 = st.columns(3)
                with c1:
                    if st.button("➕ Tableau", key=f"aet_{i}"):
                        from parser_v2 import TableRow
                        section.content_type = "table"
                        section.table_rows.append(TableRow(left="", right=""))
                        st.rerun()
                with c2:
                    if st.button("➕ Points", key=f"aeb_{i}"):
                        section.content_type = "bullets"
                        section.bullet_items.append("")
                        st.rerun()
                with c3:
                    if st.button("➕ Expériences", key=f"aee_{i}"):
                        from parser_v2 import ExperienceBlock
                        section.content_type = "experiences"
                        section.experience_blocks.append(
                            ExperienceBlock(title_line="", poste="",
                                           sub_sections=[("ROLE :", [""]), ("Environnement technique :", [""])])
                        )
                        st.rerun()

    if sections_to_delete:
        for i in sorted(sections_to_delete, reverse=True):
            cv_edit.sections.pop(i)
        st.rerun()

    # ── AJOUTER UNE SECTION ──
    st.divider()
    st.subheader("➕ Ajouter une section")

    c_name, c_type, c_pos = st.columns([3, 2, 2])
    with c_name:
        new_name = st.text_input("Nom de la section", value="", key="new_sec_name")
    with c_type:
        new_type = st.selectbox("Type", ["Liste de points", "Tableau (2 colonnes)", "Expériences"], key="new_sec_type")
    with c_pos:
        positions = ["À la fin"] + [f"Avant : {s.header}" for s in cv_edit.sections]
        new_pos = st.selectbox("Position", positions, key="new_sec_pos")

    if st.button("➕ Ajouter la section", key="add_new_sec", use_container_width=True):
        if not new_name.strip():
            st.warning("Veuillez saisir un nom de section.")
        else:
            from parser_v2 import Section, TableRow, ExperienceBlock
            ns = Section(header=new_name.strip())
            if new_type == "Liste de points":
                ns.content_type = "bullets"
                ns.bullet_items = [""]
            elif new_type == "Tableau (2 colonnes)":
                ns.content_type = "table"
                ns.table_rows = [TableRow(left="", right="")]
            else:
                ns.content_type = "experiences"
                ns.experience_blocks = [
                    ExperienceBlock(title_line="", poste="",
                                   sub_sections=[("ROLE :", [""]), ("Environnement technique :", [""])])
                ]

            if new_pos == "À la fin":
                cv_edit.sections.append(ns)
            else:
                target = new_pos.replace("Avant : ", "")
                idx = next((j for j, s in enumerate(cv_edit.sections) if s.header == target), len(cv_edit.sections))
                cv_edit.sections.insert(idx, ns)
            st.rerun()


with tab_generate:
    st.header("Générer le document")

    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"**Nom :** {cv_edit.profile.name}")
        st.markdown(f"**Titre :** {cv_edit.profile.title}")
    with col2:
        st.markdown(f"**Langue :** {cv_edit.profile.language}")
        st.markdown(f"**Expérience :** {cv_edit.profile.years_experience}")

    st.divider()
    st.markdown(f"**{len(cv_edit.sections)} section(s) :**")
    for s in cv_edit.sections:
        icon = "📊" if "table" in s.content_type else "📝" if s.content_type == "bullets" else "💼"
        count = len(s.table_rows) + len(s.bullet_items) + len(s.experience_blocks)
        st.markdown(f"  {icon} **{s.header}** ({count} élément(s))")

    st.divider()

    base_name = os.path.splitext(uploaded_file.name)[0]
    output_name = st.text_input(
        "📁 Nom du fichier de sortie",
        value=f"INTM_DDC_{cv_edit.profile.name.replace(' ', '_')}",
        help="L'extension .docx sera ajoutée automatiquement",
    )
    if not output_name.strip():
        output_name = f"{base_name}_INTM"
    if not output_name.endswith(".docx"):
        output_name = f"{output_name}.docx"

    if st.button("🚀 Générer le DOCX", type="primary", use_container_width=True):
        with st.spinner("Génération en cours..."):
            try:
                docx_bytes = generate_output(cv_edit, template_path)
                st.success("✅ Document généré avec succès !")
                st.download_button(
                    label=f"📥 Télécharger {output_name}",
                    data=docx_bytes,
                    file_name=output_name,
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    use_container_width=True,
                )
            except Exception as e:
                st.error(f"❌ Erreur lors de la génération : {e}")
                st.exception(e)