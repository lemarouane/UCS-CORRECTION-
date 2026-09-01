"""
Application Streamlit - Correction automatique des longueurs UCS.

Flux (cahier des charges, section 5 et 11) :
Accueil -> Importer UCS -> Calculer -> Previsualiser -> Valider ->
Exporter UCS corrige / rapport / lettre.
"""

import io
import os 
from datetime import datetime
import base64
import streamlit as st

from config import (
    MODEL_VERSION,
    ROUNDING_STEP_MM,
    GAUSSIAN_PARAMS,
    LOG_COEFF_A,
    LOG_COEFF_B,
    PROJECT_TITLE,
    PROJECT_SUBTITLE,
    PROJECT_TYPE,
    PROJECT_AUTHOR,
    PROJECT_INSTITUTION,
    PROJECT_ACADEMIC_YEAR,
    PROJECT_SUPERVISOR_ACADEMIC,
    PROJECT_SUPERVISOR_INDUSTRY,
)
from processor import process_ucs_file
from ucs_exporter import export_corrected_ucs
from report_exporter import export_report_excel, export_report_csv
from letter_generator import generate_adjustment_letter
from change_summary import build_change_summary
from ucs_parser import UCSStructureError


st.set_page_config(page_title=PROJECT_TITLE, page_icon="🔧", layout="wide")

LOGO_FST = "logos/fst.png"
LOGO_LEAR = "logos/lear.png"

CUSTOM_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Merriweather:wght@700&family=Inter:wght@400;500;600;700&display=swap');

html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

.logo-caption {
    text-align: center;
    color: #94a3b8;
    font-size: 0.78rem;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    margin-bottom: 0.4rem;
}
.logo-sep {
    text-align: center;
    padding-top: 1.4rem;
    color: #cbd5e1;
    font-size: 1.3rem;
    font-weight: 300;
}

.hero {
    background: linear-gradient(160deg, #0b1f3a 0%, #10315c 50%, #14497f 100%);
    padding: 3rem 3rem 2.6rem 3rem;
    border-radius: 18px;
    color: #f1f5f9;
    margin-top: 1rem;
    margin-bottom: 1.4rem;
    position: relative;
    overflow: hidden;
}
.hero::after {
    content: "";
    position: absolute;
    right: -60px; top: -60px;
    width: 280px; height: 280px;
    background: radial-gradient(circle, rgba(255,255,255,0.10) 0%, rgba(255,255,255,0) 70%);
    border-radius: 50%;
}
.hero::before {
    content: "";
    position: absolute;
    left: -40px; bottom: -80px;
    width: 220px; height: 220px;
    background: radial-gradient(circle, rgba(147,197,253,0.10) 0%, rgba(255,255,255,0) 70%);
    border-radius: 50%;
}
.hero .eyebrow {
    text-transform: uppercase;
    letter-spacing: 0.12em;
    font-size: 0.78rem;
    color: #93c5fd;
    font-weight: 600;
    margin-bottom: 0.6rem;
}
.hero h1 {
    font-family: 'Merriweather', serif;
    font-size: 2.35rem;
    line-height: 1.25;
    margin: 0 0 0.9rem 0;
}
.hero p.subtitle {
    font-size: 1.05rem;
    color: #cbd5e1;
    max-width: 700px;
    margin-bottom: 1.2rem;
}
.hero .badge {
    display: inline-block;
    background: rgba(255,255,255,0.10);
    border: 1px solid rgba(255,255,255,0.22);
    padding: 0.3rem 0.85rem;
    border-radius: 999px;
    font-size: 0.82rem;
    margin-right: 0.5rem;
    margin-bottom: 0.3rem;
}

.highlight-bar {
    display: flex;
    gap: 1rem;
    margin-bottom: 1.8rem;
}
.highlight-item {
    flex: 1;
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    padding: 1rem 1.2rem;
    text-align: center;
}
.highlight-item .num {
    font-family: 'Merriweather', serif;
    font-size: 1.5rem;
    color: #14497f;
    font-weight: 700;
}
.highlight-item .label {
    font-size: 0.78rem;
    color: #64748b;
    margin-top: 0.15rem;
}

.section-title {
    font-family: 'Merriweather', serif;
    font-size: 1.35rem;
    color: #0f172a;
    margin-top: 0.4rem;
    margin-bottom: 0.9rem;
    border-left: 4px solid #14497f;
    padding-left: 0.7rem;
}

.feature-card {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    padding: 1.3rem 1.4rem;
    height: 100%;
    transition: box-shadow 0.15s ease;
}
.feature-card:hover { box-shadow: 0 4px 14px rgba(15, 23, 42, 0.08); }
.feature-card .icon { font-size: 1.5rem; margin-bottom: 0.4rem; }
.feature-card h4 { margin: 0 0 0.35rem 0; font-size: 1.02rem; color: #0f172a; }
.feature-card p { color: #475569; font-size: 0.9rem; margin-bottom: 0; line-height: 1.45; }

.step-row {
    display: flex;
    align-items: flex-start;
    gap: 0.9rem;
    margin-bottom: 1.1rem;
}
.step-number {
    flex-shrink: 0;
    width: 34px; height: 34px;
    border-radius: 50%;
    background: #14497f;
    color: white;
    display: flex; align-items: center; justify-content: center;
    font-weight: 600; font-size: 0.95rem;
}
.step-text h5 { margin: 0 0 0.15rem 0; font-size: 0.96rem; color: #0f172a; }
.step-text p { margin: 0; font-size: 0.87rem; color: #64748b; }

.info-card {
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    padding: 1.1rem 1.3rem;
}
.info-card .label {
    font-size: 0.75rem;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: #64748b;
    margin-bottom: 0.15rem;
}
.info-card .value {
    font-size: 0.95rem;
    color: #0f172a;
    font-weight: 600;
    margin-bottom: 0.7rem;
}

.formula-box {
    background: #0b1f3a;
    color: #e2e8f0;
    border-radius: 10px;
    padding: 1rem 1.2rem;
    font-family: 'Courier New', monospace;
    font-size: 0.88rem;
    overflow-x: auto;
}

.tech-chip {
    display: inline-block;
    background: #eef2ff;
    color: #3730a3;
    border: 1px solid #c7d2fe;
    padding: 0.28rem 0.75rem;
    border-radius: 999px;
    font-size: 0.8rem;
    margin-right: 0.4rem;
    margin-bottom: 0.4rem;
}

.footer-note {
    text-align: center;
    color: #94a3b8;
    font-size: 0.8rem;
    margin-top: 2rem;
    padding-top: 1.2rem;
    border-top: 1px solid #e2e8f0;
}



.logo-frame {
    display: flex;
    align-items: center;
    justify-content: center;
    height: 90px;
}
.logo-frame img {
    margin-top: -5em;
    max-height: 180px;
    max-width: 200%;
    width: auto;
    height: auto;
    object-fit: contain;
}
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

if "page" not in st.session_state:
    st.session_state.page = "home"
if "results" not in st.session_state:
    st.session_state.results = None
if "source_bytes" not in st.session_state:
    st.session_state.source_bytes = None
if "source_name" not in st.session_state:
    st.session_state.source_name = None
if "validated" not in st.session_state:
    st.session_state.validated = False


def _image_to_base64(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def render_logo_bar():
    if not (os.path.exists(LOGO_FST) or os.path.exists(LOGO_LEAR)):
        return

    st.markdown(
        '<div class="logo-caption">Projet realise en partenariat entre</div>',
        unsafe_allow_html=True,
    )

    c_fst, c_sep, c_lear = st.columns([1, 0.25, 1])

    with c_fst:
        if os.path.exists(LOGO_FST):
            b64 = _image_to_base64(LOGO_FST)
            st.markdown(
                f'<div class="logo-frame"><img src="data:image/png;base64,{b64}"></div>',
                unsafe_allow_html=True,
            )
    with c_sep:
        st.markdown('<div class="logo-sep">×</div>', unsafe_allow_html=True)
    with c_lear:
        if os.path.exists(LOGO_LEAR):
            b64 = _image_to_base64(LOGO_LEAR)
            st.markdown(
                f'<div class="logo-frame"><img src="data:image/png;base64,{b64}"></div>',
                unsafe_allow_html=True,
            )

def render_home():
    render_logo_bar()

    st.markdown(
        f"""
        <div class="hero">
            <div class="eyebrow">{PROJECT_TYPE} - Annee universitaire {PROJECT_ACADEMIC_YEAR}</div>
            <h1>{PROJECT_TITLE}</h1>
            <p class="subtitle">{PROJECT_SUBTITLE}</p>
            <span class="badge">👤 Realise par {PROJECT_AUTHOR}</span>
            <span class="badge">🏫 {PROJECT_INSTITUTION}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        f"""
        <div class="highlight-bar">
            <div class="highlight-item"><div class="num">2</div><div class="label">Feuilles UCS supportees<br>(Wires / Tubes)</div></div>
            <div class="highlight-item"><div class="num">{ROUNDING_STEP_MM} mm</div><div class="label">Pas d'arrondi metier</div></div>
            <div class="highlight-item"><div class="num">100%</div><div class="label">Fichier source jamais modifie</div></div>
            <div class="highlight-item"><div class="num">{MODEL_VERSION}</div><div class="label">Version du modele actif</div></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    left, right = st.columns([2, 1])

    with left:
        st.markdown('<div class="section-title">Contexte et problematique</div>', unsafe_allow_html=True)
        st.write(
            "Dans un dossier de cablage automobile, les longueurs de fils et de "
            "tubes definies en CAO doivent frequemment etre ajustees pour "
            "correspondre a la realite du process de fabrication (routage "
            "physique, tolerances, connectique). Cet ajustement etait realise "
            "manuellement, faisceau par faisceau, ce qui est chronophage et "
            "source d'erreurs difficiles a tracer."
        )
        st.write(
            "Ce PFE propose d'automatiser ce calcul a partir d'un modele "
            "empirique construit sur des donnees reelles (longueur d'origine "
            "en entree, variation de longueur en sortie), tout en garantissant "
            "que chaque decision reste tracable, verifiable et modifiable "
            "par le metier."
        )

        st.markdown('<div class="section-title">Objectifs du projet</div>', unsafe_allow_html=True)
        st.markdown(
            "- Lire et interpreter automatiquement la structure d'un fichier UCS (Wires / Tubes)\n"
            "- Predire la variation de longueur a partir d'un modele mathematique versionne\n"
            "- Arrondir la correction au pas metier (5 mm) et produire une nouvelle longueur\n"
            "- Ne jamais modifier le fichier source : toute correction est ecrite dans une copie\n"
            "- Fournir un rapport de controle tracable (statuts, avertissements, erreurs)\n"
            "- Generer une demande d'ajustement pretes a etre transmise au metier"
        )

        st.markdown('<div class="section-title">Modele mathematique utilise</div>', unsafe_allow_html=True)
        st.markdown(
            f"""<div class="formula-box">
            Delta(L) = {LOG_COEFF_A} . ln(L) + {LOG_COEFF_B}
            &nbsp;+&nbsp; Sum<sub>i=1..5</sub> a<sub>i</sub> . exp( -(L - C<sub>i</sub>)^2 / (2.sigma<sub>i</sub>^2) )
            <br><br>
            Delta_arrondi = 5 x round( Delta(L) / 5 )  &nbsp;→&nbsp; New_Length = L + Delta_arrondi
            </div>""",
            unsafe_allow_html=True,
        )
        st.caption(
            f"Version actuelle du modele : {MODEL_VERSION}. Les parametres complets sont "
            "consultables dans la barre laterale une fois dans l'outil."
        )

        st.markdown('<div class="section-title">Technologies utilisees</div>', unsafe_allow_html=True)
        st.markdown(
            "".join(
                f'<span class="tech-chip">{tech}</span>'
                for tech in ["Python", "Streamlit", "pandas", "openpyxl", "python-docx", "pytest"]
            ),
            unsafe_allow_html=True,
        )

    with right:
        st.markdown('<div class="section-title">Fiche projet</div>', unsafe_allow_html=True)
        st.markdown(
            f"""
            <div class="info-card">
                <div class="label">Etudiant(e)</div>
                <div class="value">{PROJECT_AUTHOR}</div>
                <div class="label">Etablissement</div>
                <div class="value">{PROJECT_INSTITUTION}</div>
                <div class="label">Encadrant academique</div>
                <div class="value">{PROJECT_SUPERVISOR_ACADEMIC}</div>
                <div class="label">Encadrant industriel</div>
                <div class="value">{PROJECT_SUPERVISOR_INDUSTRY}</div>
                <div class="label">Annee universitaire</div>
                <div class="value">{PROJECT_ACADEMIC_YEAR}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.write("")
    st.markdown('<div class="section-title">Fonctionnalites principales</div>', unsafe_allow_html=True)
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown(
            """<div class="feature-card">
            <div class="icon">📥</div>
            <h4>Import et detection automatique</h4>
            <p>Detection automatique des feuilles Wires/Tubes et de leurs colonnes
            Name/Length, quelle que soit leur position dans le classeur, sans
            jamais alterer le fichier source.</p>
            </div>""",
            unsafe_allow_html=True,
        )
    with col2:
        st.markdown(
            """<div class="feature-card">
            <div class="icon">🧮</div>
            <h4>Modele mathematique versionne</h4>
            <p>Calcul du delta de longueur puis arrondi au pas metier de 5 mm,
            selon une formule centralisee, testee et facilement remplacable.</p>
            </div>""",
            unsafe_allow_html=True,
        )
    with col3:
        st.markdown(
            """<div class="feature-card">
            <div class="icon">📋</div>
            <h4>Rapport et tracabilite</h4>
            <p>Tableau de controle exportable (Excel/CSV), resume des
            modifications, et generation d'une demande d'ajustement (.docx).</p>
            </div>""",
            unsafe_allow_html=True,
        )

    st.write("")
    st.markdown('<div class="section-title">Comment ca marche</div>', unsafe_allow_html=True)

    steps = [
        ("Importer", "Deposer un fichier UCS (.xlsx) contenant les feuilles Wires et/ou Tubes."),
        ("Calculer", "L'application detecte les colonnes, applique le modele et arrondit chaque delta."),
        ("Verifier", "Le tableau de controle liste chaque element avec son statut (OK / avertissement / erreur)."),
        ("Valider et exporter", "Une fois valide, telechargez l'UCS corrige, le rapport et la demande d'ajustement."),
    ]
    for i, (title, desc) in enumerate(steps, start=1):
        st.markdown(
            f"""<div class="step-row">
                <div class="step-number">{i}</div>
                <div class="step-text"><h5>{title}</h5><p>{desc}</p></div>
            </div>""",
            unsafe_allow_html=True,
        )

    st.write("")
    st.divider()
    if st.button("Acceder a l'outil ➜", type="primary"):
        st.session_state.page = "app"
        st.rerun()

    st.markdown(
        f'<div class="footer-note">{PROJECT_TITLE} — {PROJECT_TYPE} {PROJECT_ACADEMIC_YEAR} — {PROJECT_AUTHOR}</div>',
        unsafe_allow_html=True,
    )


def render_tool():
    if st.button("⬅ Retour a l'accueil"):
        st.session_state.page = "home"
        st.rerun()

    st.title(PROJECT_TITLE)
    st.caption(f"Version du modele : {MODEL_VERSION} - pas d'arrondi : {ROUNDING_STEP_MM} mm")

    with st.sidebar:
        st.header("Modele")
        st.write(f"**Version :** {MODEL_VERSION}")
        st.write(f"**Composante log :** {LOG_COEFF_A} . ln(L) + {LOG_COEFF_B}")
        with st.expander("Parametres gaussiens (ai, Ci, sigma_i)"):
            for i, (a, c, s) in enumerate(GAUSSIAN_PARAMS, start=1):
                st.write(f"i={i} : a={a}, C={c}, sigma={s}")
        st.divider()
        st.caption(
            "Le fichier source n'est jamais modifie : toute correction est "
            "produite dans un nouveau fichier."
        )

    uploaded_file = st.file_uploader("Importer un UCS (.xlsx)", type=["xlsx"])

    if uploaded_file is not None:
        file_bytes = uploaded_file.getvalue()

        if st.session_state.source_name != uploaded_file.name:
            st.session_state.results = None
            st.session_state.validated = False

        st.session_state.source_bytes = file_bytes
        st.session_state.source_name = uploaded_file.name

        if st.button("Calculer", type="primary"):
            try:
                result = process_ucs_file(io.BytesIO(file_bytes))
                st.session_state.results = result
                st.session_state.validated = False
            except UCSStructureError as exc:
                st.session_state.results = None
                st.error(str(exc))

    result = st.session_state.results

    if result is not None:
        if result.skipped_sheets:
            st.warning(
                "Feuilles non detectees / ignorees (structure Name/Length non "
                f"trouvee) : {', '.join(result.skipped_sheets)}"
            )

        for sheet_name, layout in result.layouts.items():
            st.caption(
                f"Feuille **{sheet_name}** : colonnes detectees - "
                f"Name = « {layout.name_header} » (col {layout.name_col_index}), "
                f"Length = « {layout.length_header} » (col {layout.length_col_index}), "
                f"en-tete ligne {layout.header_row_index}."
            )

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Elements traites", len(result.results_df))
        col2.metric("OK", result.n_ok)
        col3.metric("Avertissements", result.n_warnings)
        col4.metric("Erreurs", result.n_errors)

        st.subheader("Tableau de controle")

        show_only_issues = st.checkbox("Afficher uniquement les avertissements / erreurs")
        display_df = result.results_df
        if show_only_issues:
            display_df = display_df[display_df["Statut"] != "OK"]

        st.dataframe(display_df, use_container_width=True, hide_index=True)

        st.subheader("Validation")
        st.session_state.validated = st.checkbox(
            "Je valide ce tableau de controle et souhaite generer les fichiers de sortie",
            value=st.session_state.validated,
        )

        if st.session_state.validated:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            base_name = st.session_state.source_name.rsplit(".", 1)[0]

            st.subheader("Resume des modifications")

            summary = build_change_summary(result.results_df)
            s = summary["stats"]

            sum_col1, sum_col2, sum_col3, sum_col4 = st.columns(4)
            sum_col1.metric("Elements modifies", s["n_modified"])
            sum_col2.metric("Longueurs augmentees", s["n_increased"])
            sum_col3.metric("Longueurs diminuees", s["n_decreased"])
            sum_col4.metric("Ecart moyen (mm)", s["mean_delta_abs"])

            st.caption(
                f"Inchanges : {s['n_unchanged']} - "
                f"Plus grande augmentation : {s['max_increase']:+} mm - "
                f"Plus grande diminution : {s['max_decrease']:+} mm"
            )

            with st.expander("Repartition par feuille"):
                st.dataframe(summary["per_sheet"], use_container_width=True, hide_index=True)

            st.write("**Detail des elements modifies** (tries par ampleur du changement)")
            if len(summary["changes_df"]) > 0:
                st.dataframe(summary["changes_df"], use_container_width=True, hide_index=True)
            else:
                st.info("Aucun element modifie (tous les deltas arrondis sont a 0).")

            st.subheader("Exports")

            export_col1, export_col2, export_col3 = st.columns(3)

            with export_col1:
                corrected_ucs_bytes = export_corrected_ucs(
                    io.BytesIO(st.session_state.source_bytes),
                    result.results_df,
                    result.layouts,
                )
                st.download_button(
                    "Telecharger UCS corrige (.xlsx)",
                    data=corrected_ucs_bytes,
                    file_name=f"{base_name}_corrected_{timestamp}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )

            with export_col2:
                report_xlsx = export_report_excel(result.results_df)
                st.download_button(
                    "Telecharger rapport (.xlsx)",
                    data=report_xlsx,
                    file_name=f"{base_name}_rapport_{timestamp}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
                report_csv = export_report_csv(result.results_df)
                st.download_button(
                    "Telecharger rapport (.csv)",
                    data=report_csv,
                    file_name=f"{base_name}_rapport_{timestamp}.csv",
                    mime="text/csv",
                )

            with export_col3:
                project_name = st.text_input("Nom du projet / faisceau (pour la lettre)", value=base_name)
                letter_bytes = generate_adjustment_letter(result.results_df, project_name=project_name)
                st.download_button(
                    "Generer la demande d'ajustement (.docx)",
                    data=letter_bytes,
                    file_name=f"{base_name}_demande_ajustement_{timestamp}.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
    else:
        st.info("Importez un fichier UCS (.xlsx) puis cliquez sur « Calculer » pour demarrer.")


if st.session_state.page == "home":
    render_home()
else:
    render_tool()