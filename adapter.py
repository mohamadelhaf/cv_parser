from parser import CVData, Experience, Education, TechSkill
from parser import get_savoir_faire, parse_cv
from parser_v2 import ParsedCV, ProfileData, Section, ExperienceBlock, TableRow


def _experience_to_block(exp: Experience) -> ExperienceBlock:
    # Build the title line like "Entreprise Company\tDurée X"
    if exp.company:
        title_line = f"Entreprise {exp.company}\t{exp.dates}" if exp.dates else f"Entreprise {exp.company}"
    elif exp.title:
        title_line = f"{exp.title}\t{exp.dates}" if exp.dates else exp.title
    else:
        title_line = exp.dates or ""

    # Poste
    poste = f"Poste {exp.title}" if exp.title and exp.company else ""

    # Sub-sections
    sub_sections = []
    if exp.tasks:
        sub_sections.append(("ROLE :", exp.tasks))
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
    if savoir_faire:
        section = Section(header="Savoir Faire", content_type="bullets")
        section.bullet_items = savoir_faire
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