import streamlit as st
import tempfile
import os
import zipfile
import copy

from dotenv import load_dotenv
load_dotenv()

st.set_page_config(page_title="DDC Lab", page_icon="📄", layout="wide")


# ═══════════════════════════════════════════════════════════════════
# Helpers partagés
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
    """Parse un fichier CV (tout format) en objet ParsedCV."""
    ext = os.path.splitext(filename)[1].lower()
    tmp_path = save_temp(file_bytes, ext)

    if ext == ".docx" and is_intm_format(file_bytes):
        from parser_v2 import parse_docx
        return parse_docx(tmp_path), "intm"
    else:
        from parser import parse_file_with_mistral
        return parse_file_with_mistral(tmp_path), "text"


def extract_offer_text(offer_file=None, offer_text_input=""):
    """Récupère le texte de l'offre depuis un fichier ou un champ texte."""
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
# Barre latérale — Sélecteur de mode + Clé API
# ═══════════════════════════════════════════════════════════════════

st.sidebar.title("📄 DDC Lab")

mode = st.sidebar.radio(
    "Mode",
    ["🔄 Convertir CV", "🎯 Matcher CV ↔ Offre", "📊 Classer les CVs"],
    key="app_mode",
)

st.sidebar.divider()

# Clé API (chargée depuis le fichier .env)
api_key = os.environ.get("MISTRAL_API_KEY", "")

if mode in ["🎯 Matcher CV ↔ Offre", "📊 Classer les CVs"]:
    if api_key:
        st.sidebar.success("✅ Clé API chargée")
    else:
        st.sidebar.error("❌ Clé API manquante — ajoutez ANTHROPIC_API_KEY dans votre fichier .env")
    st.sidebar.divider()


# ═══════════════════════════════════════════════════════════════════
# MODE 1 : Convertir CV (flux existant — inchangé)
# ═══════════════════════════════════════════════════════════════════

if mode == "🔄 Convertir CV":
    st.sidebar.markdown("Convertir n'importe quel CV au format INTM")
    st.sidebar.divider()

    uploaded_file = st.sidebar.file_uploader(
        "**Étape 1 :** Téléverser le CV",
        type=["docx", "pdf", "txt"],
        help="DOCX INTM, DOCX classique, PDF ou TXT",
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
                st.sidebar.success("✅ Template INTM détecté")
            else:
                needs_template = True
                st.sidebar.info("ℹ️ DOCX classique — téléversez un template ci-dessous")
        elif ext in (".pdf", ".txt", ".md"):
            needs_template = True
            st.sidebar.info(f"ℹ️ Fichier {ext.upper()} — téléversez un template ci-dessous")

    if needs_template:
        template_file = st.sidebar.file_uploader(
            "**Étape 2 :** Téléverser le template INTM",
            type=["docx"],
            key="template_uploader",
            help="N'importe quel DOCX INTM existant pour le style",
        )
        if template_file:
            st.sidebar.success("✅ Template chargé")
        else:
            st.sidebar.warning("⚠️ Template requis pour générer le fichier")

    if not uploaded_file:
        st.title("📄 DDC Lab — Convertir")
        st.markdown("""
        **Convertir n'importe quel CV en document Word au format INTM.**

        👈 Téléversez un fichier dans la barre latérale pour commencer.

        **Formats supportés :** DOCX INTM, DOCX classique, PDF, TXT
        """)
        st.stop()

    if needs_template and not template_file:
        st.title("📄 DDC Lab — Convertir")
        st.info("👈 Téléversez un template DOCX INTM dans la barre latérale pour continuer.")
        st.markdown("N'importe quel DDC INTM peut servir de template — peu importe à qui il appartient.")
        st.stop()

    # Parsing
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
        st.error(f"❌ Erreur de parsing : {e}")
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
        ["👤 Profil", "📋 Sections", "📥 Générer"]
    )

    with tab_profile:
        st.header("Profil")
        st.caption(
            f"Parsé via {'le parser INTM (basé sur les styles)' if parse_mode == 'intm' else 'le parser texte'}"
        )
        col1, col2 = st.columns(2)
        with col1:
            cv_edit.profile.name = st.text_input("Nom", value=cv_edit.profile.name)
            cv_edit.profile.title = st.text_input("Titre / Rôle", value=cv_edit.profile.title)
        with col2:
            cv_edit.profile.language = st.text_input("Langue", value=cv_edit.profile.language)
            cv_edit.profile.years_experience = st.text_input(
                "Années d'expérience", value=cv_edit.profile.years_experience
            )

    with tab_sections:
        st.header("Sections")
        st.caption(f"{len(cv_edit.sections)} sections")

        sections_to_delete = []

        for i, section in enumerate(cv_edit.sections):
            parts = []
            if section.table_rows:
                parts.append(f"{len(section.table_rows)} lignes")
            if section.bullet_items:
                parts.append(f"{len(section.bullet_items)} puces")
            if section.experience_blocks:
                parts.append(f"{len(section.experience_blocks)} entrées")
            summary = ", ".join(parts) if parts else "vide"

            with st.expander(f"**{section.header}** — {summary}", expanded=False):
                c_h, c_d = st.columns([5, 1])
                with c_h:
                    section.header = st.text_input(
                        "Nom de la section", value=section.header, key=f"h_{i}"
                    )
                with c_d:
                    st.markdown("<br>", unsafe_allow_html=True)
                    if st.button("🗑️ Supprimer", key=f"ds_{i}"):
                        sections_to_delete.append(i)

                if section.table_rows:
                    st.markdown("##### Lignes du tableau")
                    rows_del = []
                    for j, row in enumerate(section.table_rows):
                        c1, c2, c3 = st.columns([3, 5, 1])
                        with c1:
                            row.left = st.text_input(
                                "G", value=row.left, key=f"tl_{i}_{j}", label_visibility="collapsed"
                            )
                        with c2:
                            row.right = st.text_input(
                                "D", value=row.right, key=f"tr_{i}_{j}", label_visibility="collapsed"
                            )
                        with c3:
                            if st.button("✕", key=f"dtr_{i}_{j}"):
                                rows_del.append(j)
                    for j in sorted(rows_del, reverse=True):
                        section.table_rows.pop(j)
                    if st.button("➕ Ajouter une ligne", key=f"atr_{i}"):
                        from parser_v2 import TableRow
                        section.table_rows.append(TableRow(left="", right=""))
                        st.rerun()

                if section.bullet_items:
                    st.markdown("##### Puces")
                    bul_del = []
                    for j, item in enumerate(section.bullet_items):
                        c1, c2 = st.columns([9, 1])
                        with c1:
                            section.bullet_items[j] = st.text_input(
                                "P", value=item, key=f"bl_{i}_{j}", label_visibility="collapsed"
                            )
                        with c2:
                            if st.button("✕", key=f"dbl_{i}_{j}"):
                                bul_del.append(j)
                    for j in sorted(bul_del, reverse=True):
                        section.bullet_items.pop(j)
                    if st.button("➕ Ajouter une puce", key=f"abl_{i}"):
                        section.bullet_items.append("")
                        st.rerun()

                if section.experience_blocks:
                    for k, exp in enumerate(section.experience_blocks):
                        st.divider()
                        c_t, c_de = st.columns([8, 1])
                        with c_t:
                            exp.title_line = st.text_input(
                                "Titre", value=exp.title_line, key=f"et_{i}_{k}"
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
                                f"**{sub_header}**" if sub_header else "**Contenu :**"
                            )
                            items_del = []
                            for ii, item in enumerate(items):
                                c1, c2 = st.columns([9, 1])
                                with c1:
                                    items[ii] = st.text_input(
                                        "E",
                                        value=item,
                                        key=f"ei_{i}_{k}_{s_idx}_{ii}",
                                        label_visibility="collapsed",
                                    )
                                with c2:
                                    if st.button("✕", key=f"dei_{i}_{k}_{s_idx}_{ii}"):
                                        items_del.append(ii)
                            for idx in sorted(items_del, reverse=True):
                                items.pop(idx)
                            if st.button(f"➕ Ajouter un élément", key=f"aei_{i}_{k}_{s_idx}"):
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
                    st.info("Section vide — choisissez un type de contenu :")
                    c1, c2, c3 = st.columns(3)
                    with c1:
                        if st.button("➕ Tableau", key=f"aet_{i}"):
                            from parser_v2 import TableRow
                            section.content_type = "table"
                            section.table_rows.append(TableRow(left="", right=""))
                            st.rerun()
                    with c2:
                        if st.button("➕ Puces", key=f"aeb_{i}"):
                            section.content_type = "bullets"
                            section.bullet_items.append("")
                            st.rerun()
                    with c3:
                        if st.button("➕ Expériences", key=f"aee_{i}"):
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
        st.subheader("➕ Ajouter une nouvelle section")
        c_name, c_type, c_pos = st.columns([3, 2, 2])
        with c_name:
            new_name = st.text_input("Nom de la section", value="", key="new_sec_name")
        with c_type:
            new_type = st.selectbox(
                "Type",
                ["Liste à puces", "Tableau (2 colonnes)", "Expériences"],
                key="new_sec_type",
            )
        with c_pos:
            positions = ["À la fin"] + [
                f"Avant : {s.header}" for s in cv_edit.sections
            ]
            new_pos = st.selectbox("Position", positions, key="new_sec_pos")

        if st.button("➕ Ajouter la section", key="add_new_sec", use_container_width=True):
            if not new_name.strip():
                st.warning("Entrez un nom de section.")
            else:
                from parser_v2 import Section, TableRow, ExperienceBlock

                ns = Section(header=new_name.strip())
                if new_type == "Liste à puces":
                    ns.content_type = "bullets"
                    ns.bullet_items = [""]
                elif new_type == "Tableau (2 colonnes)":
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

                if new_pos == "À la fin":
                    cv_edit.sections.append(ns)
                else:
                    target = new_pos.replace("Avant : ", "")
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
        st.header("Générer le DOCX")

        col1, col2 = st.columns(2)
        with col1:
            st.markdown(f"**Nom :** {cv_edit.profile.name}")
            st.markdown(f"**Titre :** {cv_edit.profile.title}")
        with col2:
            st.markdown(f"**Langue :** {cv_edit.profile.language}")
            st.markdown(f"**Expérience :** {cv_edit.profile.years_experience}")

        st.divider()
        st.markdown(f"**{len(cv_edit.sections)} sections :**")
        for s in cv_edit.sections:
            icon = (
                "📊"
                if "table" in s.content_type
                else "📝" if s.content_type == "bullets" else "💼"
            )
            count = (
                len(s.table_rows) + len(s.bullet_items) + len(s.experience_blocks)
            )
            st.markdown(f"  {icon} **{s.header}** ({count} éléments)")

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
                    st.success("✅ Généré avec succès !")
                    st.download_button(
                        label=f"📥 Télécharger {output_name}",
                        data=docx_bytes,
                        file_name=output_name,
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        use_container_width=True,
                    )
                except Exception as e:
                    st.error(f"❌ Erreur : {e}")
                    st.exception(e)


# ═══════════════════════════════════════════════════════════════════
# Helpers UI partagés pour les résultats de matching
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
        return "Bon"
    elif score >= 50:
        return "Partiel"
    elif score >= 30:
        return "Faible"
    return "Insuffisant"


def _render_score_bar(label: str, score: int):
    """Affiche une barre de progression colorée avec un label."""
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
    """Affiche un MatchResult complet dans l'UI."""
    score = result.overall_score
    emoji = _score_color(score)
    label = _score_label(score)

    with st.expander(
        f"{emoji} **{result.candidate_name}** — {score}/100 ({label})",
        expanded=expanded,
    ):
        # Résumé
        st.markdown(f"*{result.summary}*")
        st.divider()

        # Scores détaillés
        if result.detail_scores:
            st.markdown("**Détail des scores**")
            detail_labels = {
                "skills": "🛠️ Compétences",
                "experience": "💼 Expérience",
                "domain": "🏢 Domaine",
                "education": "🎓 Formation",
                "languages": "🌐 Langues",
            }
            for key, lbl in detail_labels.items():
                val = result.detail_scores.get(key, 0)
                _render_score_bar(lbl, val)
            st.divider()

        # Compétences correspondantes vs manquantes
        col1, col2 = st.columns(2)
        with col1:
            if result.matched_skills:
                st.markdown("**✅ Compétences correspondantes**")
                for s in result.matched_skills:
                    st.markdown(f"- {s}")
        with col2:
            if result.missing_skills:
                st.markdown("**❌ Compétences manquantes**")
                for s in result.missing_skills:
                    st.markdown(f"- {s}")

        # Points forts & Risques
        col3, col4 = st.columns(2)
        with col3:
            if result.strengths:
                st.markdown("**💪 Points forts**")
                for s in result.strengths:
                    st.markdown(f"- {s}")
        with col4:
            if result.risks:
                st.markdown("**⚠️ Risques**")
                for r in result.risks:
                    st.markdown(f"- {r}")

        # Expérience correspondante
        col5, col6 = st.columns(2)
        with col5:
            if result.matched_experience:
                st.markdown("**✅ Expérience pertinente**")
                for e in result.matched_experience:
                    st.markdown(f"- {e}")
        with col6:
            if result.experience_gaps:
                st.markdown("**❌ Lacunes d'expérience**")
                for g in result.experience_gaps:
                    st.markdown(f"- {g}")

        # Suggestions d'adaptation
        if result.tailoring_suggestions:
            st.divider()
            st.markdown("**💡 Suggestions d'adaptation**")
            for i, s in enumerate(result.tailoring_suggestions, 1):
                st.markdown(f"{i}. {s}")


def _render_offer_input(key_prefix: str):
    """Affiche l'entrée de l'offre (téléversement OU copier-coller) et retourne le texte."""
    offer_method = st.radio(
        "Comment fournir l'offre d'emploi :",
        ["📄 Téléverser un fichier", "📝 Coller le texte"],
        horizontal=True,
        key=f"{key_prefix}_offer_method",
    )

    offer_text = ""
    if offer_method == "📄 Téléverser un fichier":
        offer_file = st.file_uploader(
            "Téléverser l'offre d'emploi",
            type=["pdf", "docx", "txt"],
            key=f"{key_prefix}_offer_file",
            help="PDF, DOCX ou TXT",
        )
        if offer_file:
            try:
                offer_text = extract_offer_text(offer_file=offer_file)
                st.success(f"✅ {len(offer_text)} caractères extraits de l'offre")
            except Exception as e:
                st.error(f"❌ Erreur de lecture de l'offre : {e}")
    else:
        offer_text = st.text_area(
            "Collez l'offre d'emploi ici",
            height=250,
            key=f"{key_prefix}_offer_text",
            placeholder="Collez la description complète du poste...",
        )

    return offer_text


# ═══════════════════════════════════════════════════════════════════
# MODE 2 : Matcher un CV ↔ une Offre
# ═══════════════════════════════════════════════════════════════════

if mode == "🎯 Matcher CV ↔ Offre":

    uploaded_cv = st.sidebar.file_uploader(
        "**Téléverser le CV**",
        type=["docx", "pdf", "txt"],
        key="match_cv_upload",
        help="Le CV à comparer avec l'offre",
    )

    if not uploaded_cv:
        st.title("🎯 Matcher CV ↔ Offre")
        st.markdown("""
        **Évaluez la compatibilité d'un CV avec une offre d'emploi.**

        👈 Téléversez un CV dans la barre latérale, puis fournissez l'offre ci-dessous.

        L'IA analysera la compatibilité et vous donnera :
        - Un score global (0–100)
        - Un détail par compétences, expérience, domaine, formation, langues
        - Les compétences correspondantes et manquantes
        - Les points forts, risques et suggestions d'adaptation
        """)
        st.stop()

    # Parsing du CV
    try:
        cv, parse_mode = parse_cv_file(uploaded_cv.getvalue(), uploaded_cv.name)
        st.sidebar.success(f"✅ CV parsé : **{cv.profile.name}**")
    except Exception as e:
        st.error(f"❌ Erreur de parsing du CV : {e}")
        st.exception(e)
        st.stop()

    st.title("🎯 Matcher CV ↔ Offre")
    st.caption(f"CV : **{cv.profile.name}** — {cv.profile.title}")

    # Entrée de l'offre
    st.subheader("Offre d'emploi")
    offer_text = _render_offer_input("match")

    # Lancer le matching
    st.divider()

    if not offer_text:
        st.info("👆 Fournissez une offre d'emploi ci-dessus pour lancer le matching.")
        st.stop()

    if not api_key:
        st.warning("⚠️ Entrez votre clé API Anthropic dans la barre latérale pour lancer le matching.")
        st.stop()

    if st.button("🚀 Lancer le matching", type="primary", use_container_width=True):
        with st.spinner("🔍 Analyse de la compatibilité..."):
            try:
                from matcher import match_cv
                result = match_cv(cv, offer_text, api_key)
                st.session_state.match_result = result
            except Exception as e:
                st.error(f"❌ Erreur de matching : {e}")
                st.exception(e)

    if "match_result" in st.session_state:
        st.divider()
        _render_match_result(st.session_state.match_result, expanded=True)


# ═══════════════════════════════════════════════════════════════════
# MODE 3 : Classer plusieurs CVs face à une offre
# ═══════════════════════════════════════════════════════════════════

if mode == "📊 Classer les CVs":

    uploaded_cvs = st.sidebar.file_uploader(
        "**Téléverser les CVs** (plusieurs)",
        type=["docx", "pdf", "txt"],
        accept_multiple_files=True,
        key="rank_cvs_upload",
        help="Téléversez tous les CVs à comparer",
    )

    if not uploaded_cvs:
        st.title("📊 Classer les CVs")
        st.markdown("""
        **Classez plusieurs CVs face à une seule offre d'emploi.**

        👈 Téléversez plusieurs CVs dans la barre latérale, puis fournissez l'offre ci-dessous.

        Chaque CV sera évalué individuellement, puis classé du meilleur au moins bon.
        """)
        st.stop()

    st.sidebar.success(f"✅ {len(uploaded_cvs)} CV(s) téléversé(s)")

    # Parsing de tous les CVs
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
            st.sidebar.error(f"❌ {fname} : {err}")

    st.title("📊 Classer les CVs")
    st.caption(f"{len(parsed_cvs)} CVs chargés")

    # Entrée de l'offre
    st.subheader("Offre d'emploi")
    offer_text = _render_offer_input("rank")

    st.divider()

    if not offer_text:
        st.info("👆 Fournissez une offre d'emploi ci-dessus pour lancer le classement.")
        st.stop()

    if not api_key:
        st.warning("⚠️ Entrez votre clé API Anthropic dans la barre latérale pour lancer le classement.")
        st.stop()

    if len(parsed_cvs) == 0:
        st.error("Aucun CV n'a pu être parsé. Vérifiez les fichiers et réessayez.")
        st.stop()

    if st.button(
        f"🚀 Classer {len(parsed_cvs)} CVs",
        type="primary",
        use_container_width=True,
    ):
        progress_bar = st.progress(0, text="Démarrage...")
        status_text = st.empty()

        def update_progress(current, total):
            pct = current / total if total > 0 else 0
            progress_bar.progress(pct, text=f"Analyse du CV {current + 1}/{total}...")
            if current < total:
                name = parsed_cvs[current][0] if current < len(parsed_cvs) else ""
                status_text.caption(f"🔍 En cours : {name}")

        try:
            from matcher import rank_cvs
            ranking = rank_cvs(
                parsed_cvs, offer_text, api_key, progress_callback=update_progress
            )
            st.session_state.ranking_result = ranking
            progress_bar.progress(1.0, text="Terminé !")
            status_text.empty()
        except Exception as e:
            st.error(f"❌ Erreur de classement : {e}")
            st.exception(e)

    if "ranking_result" in st.session_state:
        ranking = st.session_state.ranking_result
        st.divider()

        # Tableau récapitulatif
        st.subheader("🏆 Classement")

        for rank, result in enumerate(ranking.ranked_candidates, 1):
            emoji = _score_color(result.overall_score)
            label = _score_label(result.overall_score)

            # Ligne résumée
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

        # Résultats détaillés
        st.divider()
        st.subheader("📋 Résultats détaillés")

        for result in ranking.ranked_candidates:
            _render_match_result(result, expanded=False)