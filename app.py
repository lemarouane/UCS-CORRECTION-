"""
Application Streamlit - Correction automatique des longueurs UCS.

Interface "console metier" avec navigation laterale (cf. maquette) :

Accueil (vitrine) -> Tableau de bord
                      |- Correction
                      |    |- Correction des longueurs (import / calcul / validation)
                      |    '- Regles d'arrondi (parametrage du modele, sauvegarde -> applique)
                      |- Historique (calculs de la session en cours)
                      '- Rapports
                           |- Rapports (detail d'un calcul)
                           '- Exportations (telechargements)

Aucune base de donnees : tout est conserve dans st.session_state, donc
tout est perdu au rafraichissement complet de la page (comportement voulu).
"""

import io
import os
import uuid
import base64
from datetime import datetime

import pandas as pd
import plotly.graph_objects as go
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
from ucs_exporter import export_corrected_ucs, DEFAULT_LENGTH_COLUMN, CONTINUOUS_LENGTH_COLUMN
from report_exporter import export_report_excel, export_report_csv
from letter_generator import generate_adjustment_letter
from change_summary import build_change_summary
from ucs_parser import UCSStructureError


st.set_page_config(page_title=PROJECT_TITLE, page_icon="🔧", layout="wide")

LOGO_FST = "logos/fst.png"
LOGO_LEAR = "logos/lear.png"

# Logo affiche en haut de la barre laterale (centre, grand, fond transparent).
# Le premier fichier existant de la liste est utilise.
LOGO_LEAR_NAVBAR_CANDIDATES = ["logos/lear_logo.png", LOGO_LEAR]

# Textes de la marque dans la barre laterale
BRAND_NAME = "WireCorrect"
BRAND_TAGLINE = "Automatisation des corrections de longueurs UCS"

# Icones = noms d'icones "Material Symbols" (rendues nativement par Streamlit
# via le parametre icon=":material/xxx:" des st.button). Aucune emoji.
NAV_ITEMS = [
    {"key": "dashboard", "label": "Tableau de bord", "icon": "space_dashboard", "group": None},
    {"key": "correction", "label": "Correction des longueurs", "icon": "straighten", "group": "CORRECTION"},
    {"key": "rules", "label": "Regles d'arrondi", "icon": "tune", "group": "CORRECTION"},
    {"key": "historique", "label": "Historique", "icon": "history", "group": "SUIVI"},
    {"key": "rapports", "label": "Rapports de calcul", "icon": "fact_check", "group": "RAPPORTS"},
    {"key": "exportations", "label": "Exportations", "icon": "file_download", "group": "RAPPORTS"},
]

PAGE_META = {
    "dashboard": ("Tableau de bord", ["Accueil", "Tableau de bord"]),
    "correction": ("Correction des longueurs", ["Accueil", "Correction", "Correction des longueurs"]),
    "rules": ("Regles d'arrondi", ["Accueil", "Correction", "Regles d'arrondi"]),
    "historique": ("Historique", ["Accueil", "Historique"]),
    "rapports": ("Rapports de calcul", ["Accueil", "Rapports", "Rapports de calcul"]),
    "exportations": ("Exportations", ["Accueil", "Rapports", "Exportations"]),
}

# Palette partagee entre le CSS et les graphiques Plotly, pour rester coherent
# avec l'identite visuelle de l'appli.
CHART_COLORS = {
    "ok": "#15803d",
    "warn": "#b45309",
    "err": "#b91c1c",
    "primary": "#14497f",
    "primary_light": "#3b82f6",
    "accent": "#6366f1",
    "muted": "#94a3b8",
    "increase": "#b45309",
    "decrease": "#0369a1",
    "unchanged": "#94a3b8",
}

# --------------------------------------------------------------------------
# CSS
# --------------------------------------------------------------------------

CUSTOM_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Merriweather:wght@700&family=Inter:wght@400;500;600;700&display=swap');

html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

/* ---------- Sidebar ---------- */
section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0b1f3a 0%, #10315c 60%, #0d2748 100%);
}
section[data-testid="stSidebar"] * { color: #e2e8f0; }
section[data-testid="stSidebar"] .block-container { padding-top: 1.2rem; padding-bottom: 1.2rem; }

/* Marque : logo centre (grand, sans fond) + nom + sous-titre */
.sidebar-brand {
    display: flex;
    flex-direction: column;
    align-items: center;
    text-align: center;
    gap: 0.35rem;
    padding: 0.6rem 0.4rem 1.3rem 0.4rem;
    border-bottom: 1px solid rgba(255,255,255,0.12);
    margin-bottom: 0.9rem;
}
.sidebar-brand img.brand-logo {
    width: 170px;
    max-width: 85%;
    height: auto;
    background: transparent;
    padding: 0;
    border: none;
    border-radius: 0;
    margin-bottom: 0.5rem;
    filter: drop-shadow(0 6px 16px rgba(0,0,0,0.35));
}
.sidebar-brand .brand-title {
    font-family: 'Merriweather', serif;
    font-size: 1.55rem;
    font-weight: 700;
    color: #ffffff;
    letter-spacing: 0.02em;
    line-height: 1.1;
}
.sidebar-brand .brand-subtitle {
    font-size: 0.74rem;
    color: #93c5fd;
    letter-spacing: 0.03em;
    line-height: 1.4;
    max-width: 200px;
}

.sidebar-group-label {
    font-size: 0.66rem;
    letter-spacing: 0.12em;
    color: #5b7395;
    text-transform: uppercase;
    margin: 1.1rem 0 0.35rem 0.15rem;
    font-weight: 700;
}

section[data-testid="stSidebar"] div[data-testid="stButton"] {
    margin-bottom: 0.18rem;
}
section[data-testid="stSidebar"] div[data-testid="stButton"] button {
    background: transparent;
    border: 1px solid transparent;
    color: #cbd5e1;
    font-weight: 500;
    font-size: 0.87rem;
    line-height: 1.2;
    padding: 0.55rem 0.8rem;
    border-radius: 9px;
    width: 100%;
    min-height: 2.5rem;
    display: flex !important;
    justify-content: flex-start !important;
    align-items: center !important;
    text-align: left !important;
}
/* ---- Alignement des icones : colonne d'icone de largeur fixe + texte aligne a gauche ---- */
section[data-testid="stSidebar"] div[data-testid="stButton"] button > div {
    display: flex !important;
    flex-direction: row !important;
    justify-content: flex-start !important;
    align-items: center !important;
    gap: 0.75rem !important;
    width: 100% !important;
    margin: 0 !important;
}
section[data-testid="stSidebar"] div[data-testid="stButton"] button span[data-testid="stIconMaterial"],
section[data-testid="stSidebar"] div[data-testid="stButton"] button [data-testid="stIconMaterial"] {
    flex: 0 0 1.5rem !important;
    width: 1.5rem !important;
    min-width: 1.5rem !important;
    margin: 0 !important;
    font-size: 1.3rem !important;
    text-align: center !important;
    display: inline-flex !important;
    justify-content: center !important;
    align-items: center !important;
}
section[data-testid="stSidebar"] div[data-testid="stButton"] button [data-testid="stMarkdownContainer"] {
    flex: 1 1 auto !important;
    text-align: left !important;
    margin: 0 !important;
}
section[data-testid="stSidebar"] div[data-testid="stButton"] button p {
    margin: 0 !important;
    font-size: 0.87rem;
    text-align: left !important;
}
section[data-testid="stSidebar"] div[data-testid="stButton"] button:hover {
    background: rgba(255,255,255,0.08);
    border: 1px solid rgba(255,255,255,0.14);
    color: #ffffff;
}
section[data-testid="stSidebar"] div[data-testid="stButton"] button[kind="primary"] {
    background: rgba(59,130,246,0.16);
    color: #ffffff !important;
    border: 1px solid rgba(59,130,246,0.5);
    border-left: 3px solid #3b82f6;
    font-weight: 600;
    box-shadow: none;
}
section[data-testid="stSidebar"] div[data-testid="stButton"] button[kind="primary"] * { color: #ffffff !important; }

.sidebar-footer {
    margin-top: 1.6rem;
    padding-top: 1rem;
    border-top: 1px solid rgba(255,255,255,0.12);
    display: flex;
    flex-direction: column;
    align-items: center;
    text-align: center;
    gap: 0.55rem;
}
.sidebar-footer .footer-text {
    font-size: 0.7rem;
    color: #7c93b3;
    line-height: 1.5;
}

/* ---------- Top bar ---------- */
.app-topbar {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding-bottom: 0.6rem;
    margin-bottom: 0.6rem;
    border-bottom: 1px solid #e2e8f0;
}
.app-breadcrumb { color: #64748b; font-size: 0.85rem; }
.app-breadcrumb b { color: #14497f; }
.app-page-title { font-family: 'Merriweather', serif; font-size: 1.9rem; color: #0f172a; margin: 0.15rem 0 0.2rem 0; }
.app-badge-live {
    display: inline-block;
    background: #eef2ff; color: #3730a3; border: 1px solid #c7d2fe;
    padding: 0.25rem 0.7rem; border-radius: 999px; font-size: 0.75rem; font-weight: 600;
}

/* ---------- Generic cards ---------- */
.kpi-row { display: flex; gap: 1rem; margin-bottom: 1.4rem; flex-wrap: wrap; }
.kpi-card {
    flex: 1; min-width: 170px;
    background: #ffffff; border: 1px solid #e2e8f0; border-radius: 12px;
    padding: 1.1rem 1.3rem;
}
.kpi-card .kpi-label { font-size: 0.78rem; color: #64748b; text-transform: uppercase; letter-spacing: 0.05em; }
.kpi-card .kpi-value { font-family: 'Merriweather', serif; font-size: 1.7rem; color: #14497f; font-weight: 700; margin-top: 0.15rem; }
.kpi-card.warn .kpi-value { color: #b45309; }
.kpi-card.err .kpi-value { color: #b91c1c; }
.kpi-card.ok .kpi-value { color: #15803d; }

.section-title {
    font-family: 'Merriweather', serif;
    font-size: 1.25rem;
    color: #0f172a;
    margin-top: 0.4rem;
    margin-bottom: 0.9rem;
    border-left: 4px solid #14497f;
    padding-left: 0.7rem;
}

.chart-card {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    padding: 0.9rem 1rem 0.4rem 1rem;
    margin-bottom: 1rem;
}
.chart-card .chart-card-title {
    font-size: 0.82rem;
    font-weight: 700;
    color: #334155;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    margin-bottom: 0.2rem;
}

.info-card {
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    padding: 1.1rem 1.3rem;
}
.info-card .label { font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.06em; color: #64748b; margin-bottom: 0.15rem; }
.info-card .value { font-size: 0.95rem; color: #0f172a; font-weight: 600; margin-bottom: 0.7rem; }

.formula-box {
    background: #0b1f3a; color: #e2e8f0; border-radius: 10px;
    padding: 1rem 1.2rem; font-family: 'Courier New', monospace; font-size: 0.88rem; overflow-x: auto;
}

.tag-pill {
    display: inline-block; background: #eef2ff; color: #3730a3; border: 1px solid #c7d2fe;
    padding: 0.22rem 0.65rem; border-radius: 999px; font-size: 0.75rem; margin-right: 0.35rem; margin-bottom: 0.3rem;
}
.tag-pill.custom { background: #fff7ed; color: #9a3412; border-color: #fed7aa; }

.footer-note { text-align: center; color: #94a3b8; font-size: 0.8rem; margin-top: 2rem; padding-top: 1.2rem; border-top: 1px solid #e2e8f0; }

.logo-caption { text-align: center; color: #94a3b8; font-size: 0.78rem; letter-spacing: 0.1em; text-transform: uppercase; margin-bottom: 0.4rem; }
.logo-sep { text-align: center; padding-top: 1.4rem; color: #cbd5e1; font-size: 1.3rem; font-weight: 300; }
.hero {
    background: linear-gradient(160deg, #0b1f3a 0%, #10315c 50%, #14497f 100%);
    padding: 3rem 3rem 2.6rem 3rem; border-radius: 18px; color: #f1f5f9;
    margin-top: 1rem; margin-bottom: 1.4rem; position: relative; overflow: hidden;
}
.hero .eyebrow { text-transform: uppercase; letter-spacing: 0.12em; font-size: 0.78rem; color: #93c5fd; font-weight: 600; margin-bottom: 0.6rem; }
.hero h1 { font-family: 'Merriweather', serif; font-size: 2.35rem; line-height: 1.25; margin: 0 0 0.9rem 0; }
.hero p.subtitle { font-size: 1.05rem; color: #cbd5e1; max-width: 700px; margin-bottom: 1.2rem; }
.hero .badge { display: inline-block; background: rgba(255,255,255,0.10); border: 1px solid rgba(255,255,255,0.22); padding: 0.3rem 0.85rem; border-radius: 999px; font-size: 0.82rem; margin-right: 0.5rem; margin-bottom: 0.3rem; }
.highlight-bar { display: flex; gap: 1rem; margin-bottom: 1.8rem; }
.highlight-item { flex: 1; background: #ffffff; border: 1px solid #e2e8f0; border-radius: 12px; padding: 1rem 1.2rem; text-align: center; }
.highlight-item .num { font-family: 'Merriweather', serif; font-size: 1.5rem; color: #14497f; font-weight: 700; }
.highlight-item .label { font-size: 0.78rem; color: #64748b; margin-top: 0.15rem; }
.feature-card { background: #ffffff; border: 1px solid #e2e8f0; border-radius: 12px; padding: 1.3rem 1.4rem; height: 100%; }
.feature-card .icon { font-size: 1.5rem; margin-bottom: 0.4rem; }
.feature-card h4 { margin: 0 0 0.35rem 0; font-size: 1.02rem; color: #0f172a; }
.feature-card p { color: #475569; font-size: 0.9rem; margin-bottom: 0; line-height: 1.45; }
.step-row { display: flex; align-items: flex-start; gap: 0.9rem; margin-bottom: 1.1rem; }
.step-number { flex-shrink: 0; width: 34px; height: 34px; border-radius: 50%; background: #14497f; color: white; display: flex; align-items: center; justify-content: center; font-weight: 600; font-size: 0.95rem; }
.step-text h5 { margin: 0 0 0.15rem 0; font-size: 0.96rem; color: #0f172a; }
.step-text p { margin: 0; font-size: 0.87rem; color: #64748b; }
.tech-chip { display: inline-block; background: #eef2ff; color: #3730a3; border: 1px solid #c7d2fe; padding: 0.28rem 0.75rem; border-radius: 999px; font-size: 0.8rem; margin-right: 0.4rem; margin-bottom: 0.4rem; }
.logo-frame { display: flex; align-items: center; justify-content: center; height: 90px; }
.logo-frame img { margin-top: -5em; max-height: 180px; max-width: 200%; width: auto; height: auto; object-fit: contain; }
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


# --------------------------------------------------------------------------
# Session state
# --------------------------------------------------------------------------

def init_state():
    defaults = {
        "page": "home",
        "rules": {
            "rounding_step": ROUNDING_STEP_MM,
            "log_a": LOG_COEFF_A,
            "log_b": LOG_COEFF_B,
            "gaussian_params": [list(p) for p in GAUSSIAN_PARAMS],
        },
        "results": None,          # ProcessingResult courant
        "source_bytes": None,
        "source_name": None,
        "validated": False,
        "recorded_current": False,
        "historique": [],         # liste d'entrees de calcul (session uniquement)
        "selected_history_id": None,
        "export_length_choice": "arrondi",
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


init_state()


def rules_are_custom():
    r = st.session_state.rules
    if r["rounding_step"] != ROUNDING_STEP_MM:
        return True
    if abs(r["log_a"] - LOG_COEFF_A) > 1e-9 or abs(r["log_b"] - LOG_COEFF_B) > 1e-9:
        return True
    default = [list(p) for p in GAUSSIAN_PARAMS]
    if len(r["gaussian_params"]) != len(default):
        return True
    for a, b in zip(r["gaussian_params"], default):
        if any(abs(x - y) > 1e-9 for x, y in zip(a, b)):
            return True
    return False


def active_model_label():
    return f"{MODEL_VERSION} (personnalise)" if rules_are_custom() else MODEL_VERSION


def run_calculation(file_bytes):
    """Lance le calcul avec les regles actives et stocke le resultat courant."""
    r = st.session_state.rules
    gaussian_tuples = [tuple(p) for p in r["gaussian_params"]]
    result = process_ucs_file(
        io.BytesIO(file_bytes),
        rounding_step=r["rounding_step"],
        log_a=r["log_a"],
        log_b=r["log_b"],
        gaussian_params=gaussian_tuples,
        model_version_label=active_model_label(),
    )
    st.session_state.results = result
    st.session_state.validated = False
    st.session_state.recorded_current = False


def record_history_entry():
    """Enregistre le calcul courant (une seule fois) dans l'historique de session."""
    if st.session_state.recorded_current or st.session_state.results is None:
        return
    result = st.session_state.results
    entry = {
        "id": str(uuid.uuid4()),
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "filename": st.session_state.source_name,
        "n_total": len(result.results_df),
        "n_ok": result.n_ok,
        "n_warnings": result.n_warnings,
        "n_errors": result.n_errors,
        "model_version": active_model_label(),
        "rounding_step": st.session_state.rules["rounding_step"],
        "results_df": result.results_df.copy(),
        "layouts": result.layouts,
        "skipped_sheets": result.skipped_sheets,
        "source_bytes": st.session_state.source_bytes,
    }
    st.session_state.historique.insert(0, entry)
    st.session_state.recorded_current = True
    st.session_state.selected_history_id = entry["id"]


def get_history_entry(entry_id):
    for entry in st.session_state.historique:
        if entry["id"] == entry_id:
            return entry
    return None


def _image_to_base64(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def _navbar_logo_path():
    for p in LOGO_LEAR_NAVBAR_CANDIDATES:
        if os.path.exists(p):
            return p
    return None


@st.cache_data(show_spinner=False)
def _transparent_logo_b64(path, mtime):
    """Retourne le logo en base64 PNG avec un fond transparent.

    - Si le PNG a deja de la transparence (canal alpha reel), il est utilise tel quel.
    - Sinon, les pixels blancs / quasi blancs (fond) sont rendus transparents,
      avec un degrade doux sur les bords pour eviter un liseré blanc.
    Si Pillow n'est pas disponible, le fichier d'origine est utilise sans changement.
    `mtime` ne sert qu'a invalider le cache quand le fichier change.
    """
    try:
        from PIL import Image
    except ImportError:
        return _image_to_base64(path)

    img = Image.open(path).convert("RGBA")
    pixels = list(img.getdata())

    already_transparent = any(a < 250 for (_, _, _, a) in pixels)
    if not already_transparent:
        hard, soft = 245, 215   # >= hard : transparent ; entre soft et hard : degrade
        new_pixels = []
        for r, g, b, a in pixels:
            m = min(r, g, b)
            if m >= hard:
                new_pixels.append((r, g, b, 0))
            elif m > soft:
                alpha = int(255 * (hard - m) / (hard - soft))
                new_pixels.append((r, g, b, alpha))
            else:
                new_pixels.append((r, g, b, a))
        img.putdata(new_pixels)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")


# --------------------------------------------------------------------------
# Graphiques (Plotly) - helpers partages entre les pages
# --------------------------------------------------------------------------

def _plotly_layout_defaults(fig, height, title=None, show_legend=True):
    fig.update_layout(
        height=height,
        margin=dict(t=34 if title else 8, b=8, l=8, r=8),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, sans-serif", size=12, color="#334155"),
        showlegend=show_legend,
        legend=dict(orientation="h", yanchor="bottom", y=-0.22, xanchor="center", x=0.5, font=dict(size=11)),
        title=dict(text=title or "", font=dict(size=13, color="#0f172a", family="Inter")),
    )
    return fig


def make_status_donut(n_ok, n_warnings, n_errors, height=250, title=None):
    """Donut OK / Avertissements / Erreurs."""
    labels, values, colors = [], [], []
    for label, value, color in [
        ("OK", n_ok, CHART_COLORS["ok"]),
        ("Avertissements", n_warnings, CHART_COLORS["warn"]),
        ("Erreurs", n_errors, CHART_COLORS["err"]),
    ]:
        if value > 0:
            labels.append(label)
            values.append(value)
            colors.append(color)
    if not values:
        labels, values, colors = ["Aucune donnee"], [1], [CHART_COLORS["muted"]]

    fig = go.Figure(
        data=[
            go.Pie(
                labels=labels,
                values=values,
                hole=0.64,
                marker=dict(colors=colors, line=dict(color="#ffffff", width=2)),
                textinfo="value",
                textfont=dict(size=13, color="#ffffff"),
                sort=False,
            )
        ]
    )
    total = sum(values)
    fig.add_annotation(text=f"<b>{total}</b><br><span style='font-size:10px'>elements</span>", showarrow=False, font=dict(size=16, color="#0f172a"))
    return _plotly_layout_defaults(fig, height, title)


def make_bar_chart(categories, values, color=CHART_COLORS["primary"], height=250, title=None, horizontal=False):
    fig = go.Figure()
    if horizontal:
        fig.add_bar(x=values, y=categories, orientation="h", marker_color=color, marker_line_width=0)
        fig.update_yaxes(showgrid=False)
        fig.update_xaxes(showgrid=True, gridcolor="#e2e8f0", zeroline=False)
    else:
        fig.add_bar(x=categories, y=values, marker_color=color, marker_line_width=0)
        fig.update_xaxes(showgrid=False)
        fig.update_yaxes(showgrid=True, gridcolor="#e2e8f0", zeroline=False)
    return _plotly_layout_defaults(fig, height, title, show_legend=False)


def make_grouped_bar_chart(categories, series, height=280, title=None):
    """series: dict {nom_serie: (valeurs, couleur)}"""
    fig = go.Figure()
    for name, (values, color) in series.items():
        fig.add_trace(go.Bar(name=name, x=categories, y=values, marker_color=color, marker_line_width=0))
    fig.update_layout(barmode="group")
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(showgrid=True, gridcolor="#e2e8f0", zeroline=False)
    return _plotly_layout_defaults(fig, height, title, show_legend=True)


def _with_alpha(color, alpha=0.08):
    """Convertit une couleur hex ou rgb en rgba avec transparence."""
    if color.startswith("#") and len(color) == 7:
        r = int(color[1:3], 16)
        g = int(color[3:5], 16)
        b = int(color[5:7], 16)
        return f"rgba({r}, {g}, {b}, {alpha})"
    if color.startswith("rgb"):
        inner = color.replace("rgb", "").replace("(", "").replace(")", "")
        parts = [p.strip() for p in inner.split(",")]
        if len(parts) == 3:
            return f"rgba({parts[0]}, {parts[1]}, {parts[2]}, {alpha})"
    return color


def make_trend_chart(x_labels, series, height=260, title=None):
    """series: dict {nom_serie: (valeurs, couleur)}"""
    fig = go.Figure()
    for name, (values, color) in series.items():
        fig.add_trace(
            go.Scatter(
                x=x_labels,
                y=values,
                mode="lines+markers",
                name=name,
                line=dict(width=2.5, color=color),
                marker=dict(size=6),
                fill="tozeroy",
                fillcolor=_with_alpha(color, 0.08),
            )
        )
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(showgrid=True, gridcolor="#e2e8f0", zeroline=False)
    return _plotly_layout_defaults(fig, height, title, show_legend=True)


def make_histogram(values, color=CHART_COLORS["primary"], height=260, title=None, nbins=20):
    fig = go.Figure()
    fig.add_trace(go.Histogram(x=values, marker_color=color, nbinsx=nbins, marker_line_width=0))
    fig.update_xaxes(showgrid=False, title_text="Delta arrondi (mm)")
    fig.update_yaxes(showgrid=True, gridcolor="#e2e8f0", zeroline=False, title_text="Nombre d'elements")
    return _plotly_layout_defaults(fig, height, title, show_legend=False)


def chart_card_open(title):
    st.markdown(f'<div class="chart-card"><div class="chart-card-title">{title}</div>', unsafe_allow_html=True)


def chart_card_close():
    st.markdown("</div>", unsafe_allow_html=True)


# --------------------------------------------------------------------------
# Sidebar navigation
# --------------------------------------------------------------------------

def render_sidebar():
    with st.sidebar:
        logo_path = _navbar_logo_path()
        if logo_path:
            b64 = _transparent_logo_b64(logo_path, os.path.getmtime(logo_path))
            logo_html = f'<img class="brand-logo" src="data:image/png;base64,{b64}" alt="LEAR">'
        else:
            logo_html = ""
        st.markdown(
            f"""
            <div class="sidebar-brand">
                {logo_html}
                <div class="brand-title">{BRAND_NAME}</div>
                <div class="brand-subtitle">{BRAND_TAGLINE}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        current_page = st.session_state.page
        last_group = None
        for item in NAV_ITEMS:
            if item["group"] != last_group:
                if item["group"] is not None:
                    st.markdown(f'<div class="sidebar-group-label">{item["group"]}</div>', unsafe_allow_html=True)
                last_group = item["group"]
            is_active = current_page == item["key"]
            if st.button(
                item["label"],
                key=f"nav_{item['key']}",
                use_container_width=True,
                type="primary" if is_active else "secondary",
                icon=f":material/{item['icon']}:",
            ):
                st.session_state.page = item["key"]
                st.rerun()

        st.markdown(
            f"""
            <div class="sidebar-footer">
                <div class="footer-text">{PROJECT_TITLE}<br>Version {MODEL_VERSION} &middot; {PROJECT_ACADEMIC_YEAR}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_topbar(page_key):
    title, crumbs = PAGE_META[page_key]
    crumb_html = " &nbsp;›&nbsp; ".join(
        f"<b>{c}</b>" if i == len(crumbs) - 1 else c for i, c in enumerate(crumbs)
    )
    live_badge = '<span class="app-badge-live">🟢 Session active</span>'
    st.markdown(
        f"""
        <div class="app-topbar">
            <div>
                <div class="app-breadcrumb">{crumb_html}</div>
                <div class="app-page-title">{title}</div>
            </div>
            <div>{live_badge}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# --------------------------------------------------------------------------
# Page: vitrine / accueil
# --------------------------------------------------------------------------

def render_logo_bar():
    if not (os.path.exists(LOGO_FST) or os.path.exists(LOGO_LEAR)):
        return
    st.markdown('<div class="logo-caption">Projet realise en partenariat entre</div>', unsafe_allow_html=True)
    c_fst, c_sep, c_lear = st.columns([1, 0.25, 1])
    with c_fst:
        if os.path.exists(LOGO_FST):
            b64 = _image_to_base64(LOGO_FST)
            st.markdown(f'<div class="logo-frame"><img src="data:image/png;base64,{b64}"></div>', unsafe_allow_html=True)
    with c_sep:
        st.markdown('<div class="logo-sep">×</div>', unsafe_allow_html=True)
    with c_lear:
        if os.path.exists(LOGO_LEAR):
            b64 = _image_to_base64(LOGO_LEAR)
            st.markdown(f'<div class="logo-frame"><img src="data:image/png;base64,{b64}"></div>', unsafe_allow_html=True)


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
            <div class="highlight-item"><div class="num">{ROUNDING_STEP_MM} mm</div><div class="label">Pas d'arrondi par defaut</div></div>
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
            "empirique construit sur des donnees reelles, tout en garantissant "
            "que chaque decision reste tracable, verifiable et modifiable "
            "par le metier — y compris le pas d'arrondi et les coefficients "
            "du modele, ajustables depuis l'outil."
        )

        st.markdown('<div class="section-title">Modele mathematique utilise</div>', unsafe_allow_html=True)
        st.markdown(
            f"""<div class="formula-box">
            Delta(L) = {LOG_COEFF_A} . ln(L) + {LOG_COEFF_B}
            &nbsp;+&nbsp; Sum<sub>i=1..5</sub> a<sub>i</sub> . exp( -(L - C<sub>i</sub>)^2 / (2.sigma<sub>i</sub>^2) )
            <br><br>
            Delta_arrondi = pas x round( Delta(L) / pas )  &nbsp;→&nbsp; New_Length = L + Delta_arrondi
            </div>""",
            unsafe_allow_html=True,
        )
        st.caption(
            f"Version actuelle du modele : {MODEL_VERSION}. Les coefficients sont modifiables "
            "et sauvegardables depuis la page « Regles d'arrondi » une fois dans l'outil."
        )

        st.markdown('<div class="section-title">Technologies utilisees</div>', unsafe_allow_html=True)
        st.markdown(
            "".join(f'<span class="tech-chip">{t}</span>' for t in ["Python", "Streamlit", "pandas", "openpyxl", "python-docx", "plotly", "pytest"]),
            unsafe_allow_html=True,
        )

    with right:
        st.markdown('<div class="section-title">Fiche projet</div>', unsafe_allow_html=True)
        st.markdown(
            f"""
            <div class="info-card">
                <div class="label">Etudiant(e)</div><div class="value">{PROJECT_AUTHOR}</div>
                <div class="label">Etablissement</div><div class="value">{PROJECT_INSTITUTION}</div>
                <div class="label">Encadrant academique</div><div class="value">{PROJECT_SUPERVISOR_ACADEMIC}</div>
                <div class="label">Encadrant industriel</div><div class="value">{PROJECT_SUPERVISOR_INDUSTRY}</div>
                <div class="label">Annee universitaire</div><div class="value">{PROJECT_ACADEMIC_YEAR}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.write("")
    st.markdown('<div class="section-title">Fonctionnalites principales</div>', unsafe_allow_html=True)
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown(
            """<div class="feature-card"><div class="icon">📥</div><h4>Import et detection automatique</h4>
            <p>Detection automatique des feuilles Wires/Tubes et de leurs colonnes Name/Length,
            sans jamais alterer le fichier source.</p></div>""",
            unsafe_allow_html=True,
        )
    with col2:
        st.markdown(
            """<div class="feature-card"><div class="icon">⚙️</div><h4>Regles metier modifiables</h4>
            <p>Pas d'arrondi et coefficients du modele ajustables et sauvegardables,
            puis appliques automatiquement a chaque nouveau calcul.</p></div>""",
            unsafe_allow_html=True,
        )
    with col3:
        st.markdown(
            """<div class="feature-card"><div class="icon">📋</div><h4>Historique et tracabilite</h4>
            <p>Chaque calcul est trace en session, avec rapport exportable
            (Excel/CSV) et demande d'ajustement (.docx).</p></div>""",
            unsafe_allow_html=True,
        )

    st.write("")
    st.markdown('<div class="section-title">Comment ca marche</div>', unsafe_allow_html=True)
    steps = [
        ("Importer", "Deposer un fichier UCS (.xlsx) contenant les feuilles Wires et/ou Tubes."),
        ("Calculer", "L'application detecte les colonnes, applique les regles actives et arrondit chaque delta."),
        ("Verifier", "Le tableau de controle liste chaque element avec son statut (OK / avertissement / erreur)."),
        ("Valider et exporter", "Une fois valide, le calcul est trace dans l'historique et les fichiers sont prets a exporter."),
    ]
    for i, (title, desc) in enumerate(steps, start=1):
        st.markdown(
            f"""<div class="step-row"><div class="step-number">{i}</div>
                <div class="step-text"><h5>{title}</h5><p>{desc}</p></div></div>""",
            unsafe_allow_html=True,
        )

    st.write("")
    st.divider()
    if st.button("Acceder a l'outil ➜", type="primary"):
        st.session_state.page = "dashboard"
        st.rerun()

    st.markdown(
        f'<div class="footer-note">{PROJECT_TITLE} — {PROJECT_TYPE} {PROJECT_ACADEMIC_YEAR} — {PROJECT_AUTHOR}</div>',
        unsafe_allow_html=True,
    )


# --------------------------------------------------------------------------
# Page: Tableau de bord
# --------------------------------------------------------------------------

def render_dashboard():
    render_topbar("dashboard")

    historique = st.session_state.historique
    n_calculs = len(historique)
    n_elements = sum(h["n_total"] for h in historique)
    n_errors = sum(h["n_errors"] for h in historique)
    n_warnings = sum(h["n_warnings"] for h in historique)
    n_ok = sum(h["n_ok"] for h in historique)

    st.markdown(
        f"""
        <div class="kpi-row">
            <div class="kpi-card"><div class="kpi-label">Calculs (session)</div><div class="kpi-value">{n_calculs}</div></div>
            <div class="kpi-card"><div class="kpi-label">Elements traites</div><div class="kpi-value">{n_elements}</div></div>
            <div class="kpi-card warn"><div class="kpi-label">Avertissements cumules</div><div class="kpi-value">{n_warnings}</div></div>
            <div class="kpi-card err"><div class="kpi-label">Erreurs cumulees</div><div class="kpi-value">{n_errors}</div></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if historique:
        chart_col1, chart_col2, chart_col3 = st.columns([1, 1.3, 1.3])
        with chart_col1:
            chart_card_open("Repartition globale des statuts")
            st.plotly_chart(make_status_donut(n_ok, n_warnings, n_errors, height=240), use_container_width=True, config={"displayModeBar": False})
            chart_card_close()
        with chart_col2:
            chart_card_open("Elements traites par calcul")
            recent = list(reversed(historique[:8]))
            labels = [f'{h["timestamp"][11:16]}' for h in recent]
            st.plotly_chart(
                make_bar_chart(labels, [h["n_total"] for h in recent], color=CHART_COLORS["primary"], height=240),
                use_container_width=True,
                config={"displayModeBar": False},
            )
            chart_card_close()
        with chart_col3:
            chart_card_open("Tendance avertissements / erreurs")
            recent = list(reversed(historique[:8]))
            labels = [f'{h["timestamp"][11:16]}' for h in recent]
            st.plotly_chart(
                make_trend_chart(
                    labels,
                    {
                        "Avertissements": ([h["n_warnings"] for h in recent], CHART_COLORS["warn"]),
                        "Erreurs": ([h["n_errors"] for h in recent], CHART_COLORS["err"]),
                    },
                    height=240,
                ),
                use_container_width=True,
                config={"displayModeBar": False},
            )
            chart_card_close()

    left, right = st.columns([1.6, 1])

    with left:
        st.markdown('<div class="section-title">Derniers calculs</div>', unsafe_allow_html=True)
        if not historique:
            st.info("Aucun calcul effectue pour l'instant dans cette session. Commencez par « Correction des longueurs ».")
        else:
            apercu = pd.DataFrame(
                [
                    {
                        "Date/heure": h["timestamp"],
                        "Fichier": h["filename"],
                        "Elements": h["n_total"],
                        "OK": h["n_ok"],
                        "Avertissements": h["n_warnings"],
                        "Erreurs": h["n_errors"],
                        "Modele": h["model_version"],
                    }
                    for h in historique[:8]
                ]
            )
            st.dataframe(apercu, use_container_width=True, hide_index=True)
            if len(historique) > 8:
                st.caption(f"+ {len(historique) - 8} autre(s) calcul(s) — voir « Historique ».")

        st.markdown('<div class="section-title">Acces rapide</div>', unsafe_allow_html=True)
        qc1, qc2, qc3, qc4 = st.columns(4)
        with qc1:
            if st.button("Nouveau calcul", use_container_width=True, icon=":material/straighten:"):
                st.session_state.page = "correction"
                st.rerun()
        with qc2:
            if st.button("Regles", use_container_width=True, icon=":material/tune:"):
                st.session_state.page = "rules"
                st.rerun()
        with qc3:
            if st.button("Historique", use_container_width=True, icon=":material/history:"):
                st.session_state.page = "historique"
                st.rerun()
        with qc4:
            if st.button("Exporter", use_container_width=True, icon=":material/file_download:"):
                st.session_state.page = "exportations"
                st.rerun()

    with right:
        st.markdown('<div class="section-title">Regles actives</div>', unsafe_allow_html=True)
        r = st.session_state.rules
        custom = rules_are_custom()
        st.markdown(
            f"""
            <div class="info-card">
                <div class="label">Version du modele</div>
                <div class="value">{active_model_label()}</div>
                <div class="label">Pas d'arrondi</div>
                <div class="value">{r['rounding_step']} mm</div>
                <div class="label">Composante log</div>
                <div class="value">a = {r['log_a']} &nbsp;|&nbsp; b = {r['log_b']}</div>
                <div class="label">Statut</div>
                <div class="value">{'🟠 Personnalise (non defaut)' if custom else '🟢 Valeurs par defaut du cahier des charges'}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button("Modifier les regles ➜", use_container_width=True):
            st.session_state.page = "rules"
            st.rerun()

        if st.session_state.results is not None:
            st.markdown('<div class="section-title">Calcul en cours</div>', unsafe_allow_html=True)
            res = st.session_state.results
            st.markdown(
                f"""
                <div class="info-card">
                    <div class="label">Fichier</div><div class="value">{st.session_state.source_name}</div>
                    <div class="label">Elements</div><div class="value">{len(res.results_df)}</div>
                    <div class="label">Valide</div><div class="value">{'Oui' if st.session_state.validated else 'Non — a valider'}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )


# --------------------------------------------------------------------------
# Page: Correction des longueurs
# --------------------------------------------------------------------------

# Renommage des colonnes techniques -> libelles clairs pour l'affichage du
# tableau de controle (les noms de colonnes internes ne changent pas, seul
# l'affichage est adapte).
DISPLAY_COLUMN_LABELS = {
    "New Length (mm)": "Nouvelle longueur — delta arrondi (mm)",
    "New Length - delta continu (mm)": "Nouvelle longueur — delta continu (mm)",
    "Delta predit continu (mm)": "Delta predit continu (mm)",
    "Delta arrondi (mm)": "Delta arrondi (mm)",
}


def _display_results_df(df):
    """Copie d'affichage du tableau de controle : renomme les colonnes de
    longueur pour bien distinguer la version arrondie de la version en
    delta continu, et ajoute une colonne d'ecart entre les deux methodes."""
    display_df = df.copy()
    if "New Length (mm)" in display_df.columns and "New Length - delta continu (mm)" in display_df.columns:
        display_df["Ecart arrondi vs continu (mm)"] = (
            display_df["New Length (mm)"] - display_df["New Length - delta continu (mm)"]
        ).round(3)
    display_df = display_df.rename(columns=DISPLAY_COLUMN_LABELS)
    return display_df


def render_correction():
    render_topbar("correction")

    r = st.session_state.rules
    st.caption(
        f"Regles actives : pas d'arrondi = {r['rounding_step']} mm &middot; "
        f"modele = {active_model_label()}. "
        "Modifiable depuis « Regles d'arrondi »."
    )

    uploaded_file = st.file_uploader("Importer un UCS (.xlsx)", type=["xlsx"])

    if uploaded_file is not None:
        file_bytes = uploaded_file.getvalue()

        if st.session_state.source_name != uploaded_file.name:
            st.session_state.results = None
            st.session_state.validated = False
            st.session_state.recorded_current = False

        st.session_state.source_bytes = file_bytes
        st.session_state.source_name = uploaded_file.name

        if st.button("Calculer", type="primary"):
            try:
                run_calculation(file_bytes)
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

        chart_col1, chart_col2 = st.columns([1, 1.6])
        with chart_col1:
            chart_card_open("Repartition des statuts")
            st.plotly_chart(
                make_status_donut(result.n_ok, result.n_warnings, result.n_errors, height=230),
                use_container_width=True,
                config={"displayModeBar": False},
            )
            chart_card_close()
        with chart_col2:
            chart_card_open("Statuts par feuille")
            per_sheet_status = (
                result.results_df.groupby(["Feuille", "Statut"]).size().unstack(fill_value=0)
            )
            sheets = list(per_sheet_status.index)
            series = {}
            for status_name, color_key in [("OK", "ok"), ("AVERTISSEMENT", "warn"), ("ERREUR", "err")]:
                if status_name in per_sheet_status.columns:
                    series[status_name.capitalize()] = (per_sheet_status[status_name].tolist(), CHART_COLORS[color_key])
            if series:
                st.plotly_chart(make_grouped_bar_chart(sheets, series, height=230), use_container_width=True, config={"displayModeBar": False})
            chart_card_close()

        st.subheader("Tableau de controle")
        st.caption(
            "Les deux methodes de calcul de la nouvelle longueur sont affichees cote a cote : "
            "la version arrondie au pas metier (utilisee par defaut) et la version basee sur le "
            "delta continu predit par le modele (avant arrondi)."
        )
        show_only_issues = st.checkbox("Afficher uniquement les avertissements / erreurs")
        display_df = result.results_df
        if show_only_issues:
            display_df = display_df[display_df["Statut"] != "OK"]
        st.dataframe(_display_results_df(display_df), use_container_width=True, hide_index=True)

        st.subheader("Validation")
        st.session_state.validated = st.checkbox(
            "Je valide ce tableau de controle et souhaite conserver ce calcul",
            value=st.session_state.validated,
        )

        if st.session_state.validated:
            record_history_entry()

            summary = build_change_summary(result.results_df)
            s = summary["stats"]

            st.subheader("Resume des modifications")
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

            chg_col1, chg_col2 = st.columns([1, 1.6])
            with chg_col1:
                chart_card_open("Repartition des modifications")
                st.plotly_chart(
                    _modification_donut(s),
                    use_container_width=True,
                    config={"displayModeBar": False},
                )
                chart_card_close()
            with chg_col2:
                chart_card_open("Distribution des deltas arrondis (mm)")
                delta_values = result.results_df["Delta arrondi (mm)"].dropna().tolist()
                if delta_values:
                    st.plotly_chart(make_histogram(delta_values, color=CHART_COLORS["primary_light"], height=230), use_container_width=True, config={"displayModeBar": False})
                else:
                    st.info("Aucune valeur de delta disponible.")
                chart_card_close()

            with st.expander("Repartition par feuille"):
                st.dataframe(summary["per_sheet"], use_container_width=True, hide_index=True)
            st.write("**Detail des elements modifies** (tries par ampleur du changement)")
            if len(summary["changes_df"]) > 0:
                st.dataframe(summary["changes_df"], use_container_width=True, hide_index=True)
            else:
                st.info("Aucun element modifie (tous les deltas arrondis sont a 0).")

            st.success(
                "Ce calcul a ete ajoute a l'historique de la session. "
                "Rendez-vous dans **Rapports ➜ Exportations** pour telecharger les fichiers."
            )
            ec1, ec2 = st.columns(2)
            with ec1:
                if st.button("📤 Aller aux exportations", type="primary"):
                    st.session_state.page = "exportations"
                    st.rerun()
            with ec2:
                if st.button("🕒 Voir l'historique"):
                    st.session_state.page = "historique"
                    st.rerun()
    else:
        st.info("Importez un fichier UCS (.xlsx) puis cliquez sur « Calculer » pour demarrer.")


def _modification_donut(stats, height=230):
    labels, values, colors = [], [], []
    for label, value, color_key in [
        ("Augmentees", stats["n_increased"], "increase"),
        ("Diminuees", stats["n_decreased"], "decrease"),
        ("Inchangees", stats["n_unchanged"], "unchanged"),
    ]:
        if value > 0:
            labels.append(label)
            values.append(value)
            colors.append(CHART_COLORS[color_key])
    if not values:
        labels, values, colors = ["Aucune donnee"], [1], [CHART_COLORS["muted"]]
    fig = go.Figure(
        data=[
            go.Pie(
                labels=labels,
                values=values,
                hole=0.6,
                marker=dict(colors=colors, line=dict(color="#ffffff", width=2)),
                textinfo="value",
                textfont=dict(size=13, color="#ffffff"),
                sort=False,
            )
        ]
    )
    return _plotly_layout_defaults(fig, height, None)


# --------------------------------------------------------------------------
# Page: Regles d'arrondi
# --------------------------------------------------------------------------

def render_rules():
    render_topbar("rules")

    st.write(
        "Ces regles pilotent le modele de prediction et l'arrondi metier. "
        "Une fois sauvegardees, elles sont appliquees automatiquement a **tout "
        "nouveau calcul** lance depuis « Correction des longueurs » — les "
        "calculs deja realises et conserves dans l'historique ne sont pas recalcules."
    )

    if rules_are_custom():
        st.markdown('<span class="tag-pill custom">🟠 Regles personnalisees actives</span>', unsafe_allow_html=True)
    else:
        st.markdown('<span class="tag-pill">🟢 Valeurs par defaut du cahier des charges</span>', unsafe_allow_html=True)

    r = st.session_state.rules

    with st.form("rules_form"):
        st.markdown('<div class="section-title">Pas d\'arrondi metier</div>', unsafe_allow_html=True)
        rounding_step = st.number_input(
            "Pas d'arrondi (mm)",
            min_value=1,
            max_value=50,
            value=int(r["rounding_step"]),
            step=1,
            help="Delta_arrondi = pas x round(Delta / pas)",
        )

        st.markdown('<div class="section-title">Composante logarithmique</div>', unsafe_allow_html=True)
        lc1, lc2 = st.columns(2)
        with lc1:
            log_a = st.number_input("Coefficient a (Delta = a.ln(L) + b + ...)", value=float(r["log_a"]), format="%.6f")
        with lc2:
            log_b = st.number_input("Coefficient b", value=float(r["log_b"]), format="%.6f")

        st.markdown('<div class="section-title">Corrections gaussiennes (a_i, C_i, sigma_i)</div>', unsafe_allow_html=True)
        gaussian_df = pd.DataFrame(r["gaussian_params"], columns=["a_i", "C_i", "sigma_i"])
        edited_gaussian_df = st.data_editor(
            gaussian_df,
            use_container_width=True,
            num_rows="fixed",
            key="gaussian_editor",
        )

        col_save, col_reset = st.columns([1, 1])
        submitted = col_save.form_submit_button("💾 Sauvegarder et appliquer", type="primary", use_container_width=True)
        reset = col_reset.form_submit_button("↩️ Reinitialiser aux valeurs par defaut", use_container_width=True)

    if submitted:
        st.session_state.rules = {
            "rounding_step": int(rounding_step),
            "log_a": float(log_a),
            "log_b": float(log_b),
            "gaussian_params": edited_gaussian_df.values.tolist(),
        }
        st.success("Regles sauvegardees. Elles seront appliquees au prochain calcul.")
        st.rerun()

    if reset:
        st.session_state.rules = {
            "rounding_step": ROUNDING_STEP_MM,
            "log_a": LOG_COEFF_A,
            "log_b": LOG_COEFF_B,
            "gaussian_params": [list(p) for p in GAUSSIAN_PARAMS],
        }
        st.success("Regles reinitialisees aux valeurs par defaut du cahier des charges.")
        st.rerun()

    st.markdown('<div class="section-title">Formule appliquee</div>', unsafe_allow_html=True)
    st.markdown(
        f"""<div class="formula-box">
        Delta(L) = {r['log_a']} . ln(L) + {r['log_b']}
        &nbsp;+&nbsp; Sum<sub>i=1..{len(r['gaussian_params'])}</sub> a<sub>i</sub> . exp( -(L - C<sub>i</sub>)^2 / (2.sigma<sub>i</sub>^2) )
        <br><br>
        Delta_arrondi = {r['rounding_step']} x round( Delta(L) / {r['rounding_step']} )
        </div>""",
        unsafe_allow_html=True,
    )


# --------------------------------------------------------------------------
# Page: Historique
# --------------------------------------------------------------------------

def render_historique():
    render_topbar("historique")

    st.info(
        "L'historique est conserve uniquement pour la duree de la session en cours : "
        "il n'y a pas de base de donnees, et tout est efface au rafraichissement complet de la page."
    )

    historique = st.session_state.historique
    if not historique:
        st.warning("Aucun calcul valide pour l'instant dans cette session.")
        if st.button("📐 Aller a « Correction des longueurs »", type="primary"):
            st.session_state.page = "correction"
            st.rerun()
        return

    top_col1, top_col2 = st.columns([3, 1])
    with top_col1:
        st.caption(f"{len(historique)} calcul(s) enregistre(s) dans cette session.")
    with top_col2:
        if st.button("🗑️ Vider l'historique", use_container_width=True):
            st.session_state.historique = []
            st.session_state.selected_history_id = None
            st.rerun()

    if len(historique) > 1:
        chronological = list(reversed(historique))
        labels = [f'{h["timestamp"][5:16]}' for h in chronological]
        chart_col1, chart_col2 = st.columns([1.6, 1])
        with chart_col1:
            chart_card_open("Evolution des avertissements / erreurs par calcul")
            st.plotly_chart(
                make_trend_chart(
                    labels,
                    {
                        "Avertissements": ([h["n_warnings"] for h in chronological], CHART_COLORS["warn"]),
                        "Erreurs": ([h["n_errors"] for h in chronological], CHART_COLORS["err"]),
                    },
                    height=240,
                ),
                use_container_width=True,
                config={"displayModeBar": False},
            )
            chart_card_close()
        with chart_col2:
            chart_card_open("Repartition cumulee")
            st.plotly_chart(
                make_status_donut(
                    sum(h["n_ok"] for h in historique),
                    sum(h["n_warnings"] for h in historique),
                    sum(h["n_errors"] for h in historique),
                    height=240,
                ),
                use_container_width=True,
                config={"displayModeBar": False},
            )
            chart_card_close()

    table = pd.DataFrame(
        [
            {
                "Date/heure": h["timestamp"],
                "Fichier": h["filename"],
                "Elements": h["n_total"],
                "OK": h["n_ok"],
                "Avertissements": h["n_warnings"],
                "Erreurs": h["n_errors"],
                "Pas d'arrondi (mm)": h["rounding_step"],
                "Modele": h["model_version"],
            }
            for h in historique
        ]
    )
    st.dataframe(table, use_container_width=True, hide_index=True)

    st.markdown('<div class="section-title">Detail d\'un calcul</div>', unsafe_allow_html=True)
    options = {f'{h["timestamp"]} — {h["filename"]}': h["id"] for h in historique}
    label = st.selectbox("Choisir un calcul", list(options.keys()))
    entry = get_history_entry(options[label])
    if entry:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Elements", entry["n_total"])
        c2.metric("OK", entry["n_ok"])
        c3.metric("Avertissements", entry["n_warnings"])
        c4.metric("Erreurs", entry["n_errors"])
        show_issues_only = st.checkbox("Afficher uniquement les avertissements / erreurs", key="hist_issues_only")
        df = entry["results_df"]
        if show_issues_only:
            df = df[df["Statut"] != "OK"]
        st.dataframe(_display_results_df(df), use_container_width=True, hide_index=True)

        rc1, rc2 = st.columns(2)
        with rc1:
            if st.button("📋 Ouvrir dans Rapports", use_container_width=True):
                st.session_state.selected_history_id = entry["id"]
                st.session_state.page = "rapports"
                st.rerun()
        with rc2:
            if st.button("📤 Exporter ce calcul", use_container_width=True):
                st.session_state.selected_history_id = entry["id"]
                st.session_state.page = "exportations"
                st.rerun()


# --------------------------------------------------------------------------
# Page: Rapports
# --------------------------------------------------------------------------

def render_rapports():
    render_topbar("rapports")

    historique = st.session_state.historique
    if not historique:
        st.warning("Aucun rapport disponible : effectuez d'abord un calcul valide.")
        if st.button("📐 Aller a « Correction des longueurs »", type="primary"):
            st.session_state.page = "correction"
            st.rerun()
        return

    options = {f'{h["timestamp"]} — {h["filename"]}': h["id"] for h in historique}
    default_id = st.session_state.selected_history_id or historique[0]["id"]
    default_label = next((k for k, v in options.items() if v == default_id), list(options.keys())[0])
    label = st.selectbox("Rapport a afficher", list(options.keys()), index=list(options.keys()).index(default_label))
    entry = get_history_entry(options[label])
    st.session_state.selected_history_id = entry["id"]

    st.markdown('<div class="section-title">Synthese</div>', unsafe_allow_html=True)
    st.markdown(
        f"""
        <div class="kpi-row">
            <div class="kpi-card"><div class="kpi-label">Fichier source</div><div class="kpi-value" style="font-size:1.1rem;">{entry['filename']}</div></div>
            <div class="kpi-card ok"><div class="kpi-label">OK</div><div class="kpi-value">{entry['n_ok']}</div></div>
            <div class="kpi-card warn"><div class="kpi-label">Avertissements</div><div class="kpi-value">{entry['n_warnings']}</div></div>
            <div class="kpi-card err"><div class="kpi-label">Erreurs</div><div class="kpi-value">{entry['n_errors']}</div></div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.caption(
        f"Calcule le {entry['timestamp']} &middot; modele {entry['model_version']} "
        f"&middot; pas d'arrondi {entry['rounding_step']} mm."
    )

    if entry["skipped_sheets"]:
        st.warning(f"Feuilles ignorees lors de ce calcul : {', '.join(entry['skipped_sheets'])}")

    df = entry["results_df"]

    st.markdown('<div class="section-title">Repartition des statuts</div>', unsafe_allow_html=True)
    donut_col, hist_col = st.columns([1, 1.4])
    with donut_col:
        chart_card_open("Statuts")
        st.plotly_chart(
            make_status_donut(entry["n_ok"], entry["n_warnings"], entry["n_errors"], height=250),
            use_container_width=True,
            config={"displayModeBar": False},
        )
        chart_card_close()
    with hist_col:
        chart_card_open("Distribution des deltas arrondis (mm)")
        delta_values = df["Delta arrondi (mm)"].dropna().tolist()
        if delta_values:
            st.plotly_chart(make_histogram(delta_values, color=CHART_COLORS["primary_light"], height=250), use_container_width=True, config={"displayModeBar": False})
        else:
            st.info("Aucune valeur de delta disponible pour ce calcul.")
        chart_card_close()

    st.markdown('<div class="section-title">Resume des modifications</div>', unsafe_allow_html=True)
    summary = build_change_summary(df)
    s = summary["stats"]
    sum_col1, sum_col2, sum_col3, sum_col4 = st.columns(4)
    sum_col1.metric("Elements modifies", s["n_modified"])
    sum_col2.metric("Longueurs augmentees", s["n_increased"])
    sum_col3.metric("Longueurs diminuees", s["n_decreased"])
    sum_col4.metric("Ecart moyen (mm)", s["mean_delta_abs"])

    mod_col1, mod_col2 = st.columns([1, 1.4])
    with mod_col1:
        chart_card_open("Augmentees / diminuees / inchangees")
        st.plotly_chart(_modification_donut(s, height=230), use_container_width=True, config={"displayModeBar": False})
        chart_card_close()
    with mod_col2:
        chart_card_open("Elements par feuille et par statut")
        per_sheet_status = df.groupby(["Feuille", "Statut"]).size().unstack(fill_value=0)
        sheets = list(per_sheet_status.index)
        series = {}
        for status_name, color_key in [("OK", "ok"), ("AVERTISSEMENT", "warn"), ("ERREUR", "err")]:
            if status_name in per_sheet_status.columns:
                series[status_name.capitalize()] = (per_sheet_status[status_name].tolist(), CHART_COLORS[color_key])
        if series:
            st.plotly_chart(make_grouped_bar_chart(sheets, series, height=230), use_container_width=True, config={"displayModeBar": False})
        chart_card_close()

    with st.expander("Repartition par feuille"):
        st.dataframe(summary["per_sheet"], use_container_width=True, hide_index=True)

    st.markdown('<div class="section-title">Tableau de controle complet</div>', unsafe_allow_html=True)
    show_issues_only = st.checkbox("Afficher uniquement les avertissements / erreurs", key="rapport_issues_only")
    display_df = df if not show_issues_only else df[df["Statut"] != "OK"]
    st.dataframe(_display_results_df(display_df), use_container_width=True, hide_index=True)

    if st.button("📤 Exporter ce rapport", type="primary"):
        st.session_state.selected_history_id = entry["id"]
        st.session_state.page = "exportations"
        st.rerun()


# --------------------------------------------------------------------------
# Page: Exportations
# --------------------------------------------------------------------------

def render_exportations():
    render_topbar("exportations")

    historique = st.session_state.historique
    if not historique:
        st.warning("Aucun calcul disponible a exporter : effectuez d'abord un calcul valide.")
        if st.button("📐 Aller a « Correction des longueurs »", type="primary"):
            st.session_state.page = "correction"
            st.rerun()
        return

    options = {f'{h["timestamp"]} — {h["filename"]}': h["id"] for h in historique}
    default_id = st.session_state.selected_history_id or historique[0]["id"]
    default_label = next((k for k, v in options.items() if v == default_id), list(options.keys())[0])
    label = st.selectbox("Calcul a exporter", list(options.keys()), index=list(options.keys()).index(default_label))
    entry = get_history_entry(options[label])

    base_name = entry["filename"].rsplit(".", 1)[0] if entry["filename"] else "ucs"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    st.markdown('<div class="section-title">Fichiers disponibles</div>', unsafe_allow_html=True)
    export_col1, export_col2, export_col3 = st.columns(3)

    with export_col1:
        st.markdown("**UCS corrige**")
        st.caption("Copie du fichier source avec les nouvelles longueurs (fichier d'origine jamais modifie).")

        length_choice_label = st.radio(
            "Longueur a ecrire dans le fichier corrige",
            options=["arrondi", "continu"],
            format_func=lambda v: (
                "Delta arrondi au pas metier (recommande)" if v == "arrondi"
                else "Delta continu (valeur brute predite par le modele, non arrondie)"
            ),
            index=0 if st.session_state.export_length_choice == "arrondi" else 1,
            key="export_length_radio",
        )
        st.session_state.export_length_choice = length_choice_label
        selected_length_column = (
            DEFAULT_LENGTH_COLUMN if length_choice_label == "arrondi" else CONTINUOUS_LENGTH_COLUMN
        )
        suffix = "arrondi" if length_choice_label == "arrondi" else "continu"

        if entry["source_bytes"] is not None:
            corrected_ucs_bytes = export_corrected_ucs(
                io.BytesIO(entry["source_bytes"]),
                entry["results_df"],
                entry["layouts"],
                length_column=selected_length_column,
            )
            st.download_button(
                f"⬇️ Telecharger UCS corrige — {suffix} (.xlsx)",
                data=corrected_ucs_bytes,
                file_name=f"{base_name}_corrected_{suffix}_{timestamp}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
        else:
            st.caption("Fichier source non disponible pour ce calcul.")

    with export_col2:
        st.markdown("**Rapport de calcul**")
        st.caption("Tableau de controle complet (deltas arrondi et continu inclus), au format tableur.")
        report_xlsx = export_report_excel(entry["results_df"])
        st.download_button(
            "⬇️ Rapport (.xlsx)",
            data=report_xlsx,
            file_name=f"{base_name}_rapport_{timestamp}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
        report_csv = export_report_csv(entry["results_df"])
        st.download_button(
            "⬇️ Rapport (.csv)",
            data=report_csv,
            file_name=f"{base_name}_rapport_{timestamp}.csv",
            mime="text/csv",
            use_container_width=True,
        )

    with export_col3:
        st.markdown("**Demande d'ajustement**")
        project_name = st.text_input("Nom du projet / faisceau", value=base_name, key="export_project_name")
        letter_bytes = generate_adjustment_letter(entry["results_df"], project_name=project_name)
        st.download_button(
            "⬇️ Demande d'ajustement (.docx)",
            data=letter_bytes,
            file_name=f"{base_name}_demande_ajustement_{timestamp}.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            use_container_width=True,
        )

    st.markdown('<div class="section-title">Recapitulatif du calcul selectionne</div>', unsafe_allow_html=True)
    st.markdown(
        f"""
        <div class="info-card">
            <div class="label">Fichier source</div><div class="value">{entry['filename']}</div>
            <div class="label">Date du calcul</div><div class="value">{entry['timestamp']}</div>
            <div class="label">Modele / pas d'arrondi</div><div class="value">{entry['model_version']} &middot; {entry['rounding_step']} mm</div>
            <div class="label">Elements (OK / Avert. / Erreurs)</div><div class="value">{entry['n_ok']} / {entry['n_warnings']} / {entry['n_errors']}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# --------------------------------------------------------------------------
# Dispatch
# --------------------------------------------------------------------------

if st.session_state.page == "home":
    render_home()
else:
    render_sidebar()
    dispatch = {
        "dashboard": render_dashboard,
        "correction": render_correction,
        "rules": render_rules,
        "historique": render_historique,
        "rapports": render_rapports,
        "exportations": render_exportations,
    }
    dispatch.get(st.session_state.page, render_dashboard)()
