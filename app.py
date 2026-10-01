"""
Application Streamlit - Wire Correct : automatisation des corrections de longueur UCS.

Interface "console metier" avec navigation laterale :

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

Logo : deposer le nouveau logo dans logos/wire_correct.png
(si le fichier est absent, un logo SVG de secours est affiche).
"""

import io
import os
import uuid
import base64
from datetime import datetime

import numpy as np
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


st.set_page_config(page_title="Wire Correct", page_icon="🔧", layout="wide")

LOGO_APP = "logos/wire_correct.png"   # <-- nouveau logo (centre en haut de page)
LOGO_FST = "logos/fst.png"
LOGO_LEAR = "logos/lear_logo.png"

APP_NAME = "WIRE CORRECT"
APP_TAGLINE = "Automatisation des corrections de longueur UCS"
LEAR_TAGLINE = "Making Every Drive Better"

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
    "dashboard": ("Tableau de bord", ["Accueil", "Tableau de bord"], "space_dashboard"),
    "correction": ("Correction des longueurs", ["Accueil", "Correction", "Correction des longueurs"], "straighten"),
    "rules": ("Regles d'arrondi", ["Accueil", "Correction", "Regles d'arrondi"], "tune"),
    "historique": ("Historique", ["Accueil", "Historique"], "history"),
    "rapports": ("Rapports de calcul", ["Accueil", "Rapports", "Rapports de calcul"], "fact_check"),
    "exportations": ("Exportations", ["Accueil", "Rapports", "Exportations"], "file_download"),
}

# Palette partagee entre le CSS et les graphiques Plotly.
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
    "lear_red": "#c8102e",
}

# --------------------------------------------------------------------------
# CSS
# --------------------------------------------------------------------------

CUSTOM_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Merriweather:wght@700&family=Inter:wght@400;500;600;700&display=swap');
@import url('https://fonts.googleapis.com/css2?family=Material+Symbols+Rounded:opsz,wght,FILL,GRAD@24,400,1,0&display=swap');

html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

.material-symbols-rounded {
    font-family: 'Material Symbols Rounded' !important;
    font-weight: normal;
    font-style: normal;
    font-size: 1.3rem;
    line-height: 1;
    display: inline-block;
    vertical-align: middle;
    letter-spacing: normal;
    text-transform: none;
    white-space: nowrap;
    -webkit-font-smoothing: antialiased;
    font-variation-settings: 'FILL' 1, 'wght' 400, 'GRAD' 0, 'opsz' 24;
}

/* ---------- Header centre (logo + nom + sous-titre) ---------- */
.app-header {
    display: flex;
    flex-direction: column;
    align-items: center;
    text-align: center;
    padding: 0.2rem 0 1rem 0;
    margin-bottom: 1rem;
    border-bottom: 1px solid #e2e8f0;
}
.app-header .app-logo { height: 76px; width: auto; max-width: 240px; object-fit: contain; margin-bottom: 0.45rem; }
.app-header .app-logo-svg { height: 76px; width: 76px; margin-bottom: 0.45rem; }
.app-header .app-name {
    font-family: 'Merriweather', serif;
    font-size: 1.85rem;
    letter-spacing: 0.16em;
    color: #0b1f3a;
    margin: 0;
    line-height: 1.2;
}
.app-header .app-name-bar { width: 56px; height: 3px; background: #c8102e; border-radius: 2px; margin: 0.5rem auto 0.5rem auto; }
.app-header .app-sub { font-size: 0.95rem; color: #64748b; letter-spacing: 0.03em; }

/* ---------- Sidebar ---------- */
section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0b1f3a 0%, #10315c 60%, #0d2748 100%);
}
section[data-testid="stSidebar"] * { color: #e2e8f0; }
section[data-testid="stSidebar"] .block-container { padding-top: 1.2rem; padding-bottom: 1.2rem; }

.sidebar-brand {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    padding: 0.2rem 0.2rem 1.1rem 0.2rem;
    border-bottom: 1px solid rgba(255,255,255,0.12);
    margin-bottom: 0.9rem;
}
.sidebar-brand img { height: 34px; width: auto; border-radius: 6px; background: white; padding: 2px; }
.sidebar-brand .brand-text b { font-size: 1.05rem; color: #ffffff; display:block; letter-spacing: 0.08em; }
.sidebar-brand .brand-text span { font-size: 0.72rem; color: #93c5fd; letter-spacing: 0.04em; }

.sidebar-group-label {
    font-size: 0.66rem;
    letter-spacing: 0.12em;
    color: #5b7395;
    text-transform: uppercase;
    margin: 1.1rem 0 0.35rem 0.15rem;
    font-weight: 700;
}

section[data-testid="stSidebar"] div[data-testid="stButton"] { margin-bottom: 0.18rem; }
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
    padding-top: 0.9rem;
    display: flex;
    flex-direction: column;
    align-items: center;
    text-align: center;
    gap: 0.4rem;
}
.sidebar-footer .side-redline { width: 100%; height: 2px; background: #e4002b; border-radius: 2px; margin-bottom: 0.5rem; }
.sidebar-footer .footer-logo { height: 28px; width: auto; background: #ffffff; border-radius: 6px; padding: 5px 10px; }
.sidebar-footer .footer-company { font-size: 0.78rem; font-weight: 700; letter-spacing: 0.1em; color: #ffffff; }
.sidebar-footer .footer-text { font-size: 0.7rem; color: #7c93b3; line-height: 1.5; }

/* ---------- Top bar ---------- */
.app-topbar {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding-bottom: 0.6rem;
    margin-bottom: 0.9rem;
    border-bottom: 1px solid #e2e8f0;
}
.app-breadcrumb { color: #64748b; font-size: 0.85rem; }
.app-breadcrumb b { color: #14497f; }
.app-page-title {
    font-family: 'Merriweather', serif; font-size: 1.7rem; color: #0f172a; margin: 0.15rem 0 0.2rem 0;
    display: flex; align-items: center; gap: 0.6rem;
}
.app-page-title .title-icon {
    width: 42px; height: 42px; border-radius: 12px; background: #eaf2fb; color: #14497f;
    display: inline-flex; align-items: center; justify-content: center;
}
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
    display: flex; align-items: center; gap: 0.9rem;
    box-shadow: 0 1px 2px rgba(15,23,42,0.04);
}
.kpi-card .kpi-icon {
    flex-shrink: 0; width: 46px; height: 46px; border-radius: 12px;
    display: flex; align-items: center; justify-content: center;
    background: #eaf2fb; color: #14497f;
}
.kpi-card.warn .kpi-icon { background: #fef3c7; color: #b45309; }
.kpi-card.err .kpi-icon { background: #fee2e2; color: #b91c1c; }
.kpi-card.ok .kpi-icon { background: #dcfce7; color: #15803d; }
.kpi-card .kpi-label { font-size: 0.74rem; color: #64748b; text-transform: uppercase; letter-spacing: 0.05em; }
.kpi-card .kpi-value { font-family: 'Merriweather', serif; font-size: 1.6rem; color: #14497f; font-weight: 700; margin-top: 0.1rem; }
.kpi-card.warn .kpi-value { color: #b45309; }
.kpi-card.err .kpi-value { color: #b91c1c; }
.kpi-card.ok .kpi-value { color: #15803d; }

.section-title {
    font-family: 'Merriweather', serif;
    font-size: 1.2rem;
    color: #0f172a;
    margin-top: 0.4rem;
    margin-bottom: 0.9rem;
    border-left: 4px solid #14497f;
    padding-left: 0.7rem;
    display: flex; align-items: center; gap: 0.5rem;
}
.section-title .material-symbols-rounded { color: #14497f; font-size: 1.35rem; }

.chart-card {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    padding: 0.9rem 1rem 0.4rem 1rem;
    margin-bottom: 1rem;
    box-shadow: 0 1px 2px rgba(15,23,42,0.04);
}
.chart-card .chart-card-title {
    font-size: 0.8rem;
    font-weight: 700;
    color: #334155;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    margin-bottom: 0.2rem;
    display: flex; align-items: center; gap: 0.4rem;
}
.chart-card .chart-card-title .material-symbols-rounded { font-size: 1.1rem; color: #14497f; }

.info-card {
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    padding: 1.1rem 1.3rem;
}
.info-card .label { font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.06em; color: #64748b; margin-bottom: 0.15rem; }
.info-card .value { font-size: 0.95rem; color: #0f172a; font-weight: 600; margin-bottom: 0.7rem; }

.empty-state {
    background: #f8fafc; border: 2px dashed #cbd5e1; border-radius: 14px;
    padding: 2rem 1.5rem; text-align: center; color: #64748b; margin-bottom: 1rem;
}
.empty-state .material-symbols-rounded { font-size: 3rem; color: #94a3b8; }
.empty-state h4 { margin: 0.4rem 0 0.2rem 0; color: #334155; }
.empty-state p { margin: 0; font-size: 0.9rem; }

.formula-box {
    background: #0b1f3a; color: #e2e8f0; border-radius: 10px;
    padding: 1rem 1.2rem; font-family: 'Courier New', monospace; font-size: 0.88rem; overflow-x: auto;
}

.tag-pill {
    display: inline-block; background: #eef2ff; color: #3730a3; border: 1px solid #c7d2fe;
    padding: 0.22rem 0.65rem; border-radius: 999px; font-size: 0.75rem; margin-right: 0.35rem; margin-bottom: 0.3rem;
}
.tag-pill.custom { background: #fff7ed; color: #9a3412; border-color: #fed7aa; }

/* ---------- Footer principal : ligne rouge + LEAR Corporation + slogan ---------- */
.app-footer { margin-top: 2.5rem; text-align: center; }
.app-footer .footer-redline { height: 3px; width: 100%; background: #e4002b; border-radius: 2px; margin-bottom: 1rem; }
.app-footer .footer-company { font-family: 'Merriweather', serif; font-size: 1.05rem; letter-spacing: 0.18em; color: #0f172a; text-transform: uppercase; }
.app-footer .footer-tagline { font-size: 0.85rem; color: #c8102e; font-style: italic; margin-top: 0.15rem; font-weight: 600; letter-spacing: 0.04em; }
.app-footer .footer-meta { font-size: 0.74rem; color: #94a3b8; margin-top: 0.6rem; }

.logo-caption { text-align: center; color: #94a3b8; font-size: 0.78rem; letter-spacing: 0.1em; text-transform: uppercase; margin-bottom: 0.4rem; }
.logo-sep { text-align: center; padding-top: 1.4rem; color: #cbd5e1; font-size: 1.3rem; font-weight: 300; }
.hero {
    background: linear-gradient(160deg, #0b1f3a 0%, #10315c 50%, #14497f 100%);
    padding: 3rem 3rem 2.6rem 3rem; border-radius: 18px; color: #f1f5f9;
    margin-top: 1rem; margin-bottom: 1.4rem; position: relative; overflow: hidden;
}
.hero::after {
    content: ""; position: absolute; right: -60px; top: -60px; width: 260px; height: 260px;
    border-radius: 50%; background: radial-gradient(circle, rgba(228,0,43,0.35) 0%, rgba(228,0,43,0) 70%);
}
.hero::before {
    content: ""; position: absolute; right: 80px; bottom: -90px; width: 240px; height: 240px;
    border-radius: 50%; background: radial-gradient(circle, rgba(59,130,246,0.35) 0%, rgba(59,130,246,0) 70%);
}
.hero .eyebrow { text-transform: uppercase; letter-spacing: 0.12em; font-size: 0.78rem; color: #93c5fd; font-weight: 600; margin-bottom: 0.6rem; }
.hero h1 { font-family: 'Merriweather', serif; font-size: 2.35rem; line-height: 1.25; margin: 0 0 0.9rem 0; position: relative; z-index: 1; }
.hero p.subtitle { font-size: 1.05rem; color: #cbd5e1; max-width: 700px; margin-bottom: 1.2rem; position: relative; z-index: 1; }
.hero .badge { display: inline-flex; align-items: center; gap: 0.35rem; background: rgba(255,255,255,0.10); border: 1px solid rgba(255,255,255,0.22); padding: 0.3rem 0.85rem; border-radius: 999px; font-size: 0.82rem; margin-right: 0.5rem; margin-bottom: 0.3rem; position: relative; z-index: 1; }
.hero .badge .material-symbols-rounded { font-size: 1rem; }
.highlight-bar { display: flex; gap: 1rem; margin-bottom: 1.8rem; }
.highlight-item { flex: 1; background: #ffffff; border: 1px solid #e2e8f0; border-radius: 12px; padding: 1rem 1.2rem; text-align: center; box-shadow: 0 1px 2px rgba(15,23,42,0.04); }
.highlight-item .hl-icon { color: #3b82f6; }
.highlight-item .num { font-family: 'Merriweather', serif; font-size: 1.5rem; color: #14497f; font-weight: 700; }
.highlight-item .label { font-size: 0.78rem; color: #64748b; margin-top: 0.15rem; }
.feature-card { background: #ffffff; border: 1px solid #e2e8f0; border-radius: 12px; padding: 1.3rem 1.4rem; height: 100%; box-shadow: 0 1px 2px rgba(15,23,42,0.04); }
.feature-card .icon {
    width: 48px; height: 48px; border-radius: 14px; background: linear-gradient(135deg, #14497f, #3b82f6);
    color: #ffffff; display: flex; align-items: center; justify-content: center; margin-bottom: 0.7rem;
}
.feature-card .icon .material-symbols-rounded { font-size: 1.6rem; }
.feature-card h4 { margin: 0 0 0.35rem 0; font-size: 1.02rem; color: #0f172a; }
.feature-card p { color: #475569; font-size: 0.9rem; margin-bottom: 0; line-height: 1.45; }
.step-row { display: flex; align-items: flex-start; gap: 0.9rem; margin-bottom: 1.1rem; }
.step-number { flex-shrink: 0; width: 38px; height: 38px; border-radius: 50%; background: #14497f; color: white; display: flex; align-items: center; justify-content: center; }
.step-number .material-symbols-rounded { font-size: 1.2rem; }
.step-text h5 { margin: 0 0 0.15rem 0; font-size: 0.96rem; color: #0f172a; }
.step-text p { margin: 0; font-size: 0.87rem; color: #64748b; }
.tech-chip { display: inline-block; background: #eef2ff; color: #3730a3; border: 1px solid #c7d2fe; padding: 0.28rem 0.75rem; border-radius: 999px; font-size: 0.8rem; margin-right: 0.4rem; margin-bottom: 0.4rem; }
.logo-frame { display: flex; align-items: center; justify-content: center; height: 90px; }
.logo-frame img { margin-top: -5em; max-height: 180px; max-width: 200%; width: auto; height: auto; object-fit: contain; }

/* ---------- Pipeline (accueil) ---------- */
.pipeline { display: flex; align-items: center; justify-content: center; gap: 0.6rem; flex-wrap: wrap; margin: 0.4rem 0 1.6rem 0; }
.pipe-node {
    display: flex; flex-direction: column; align-items: center; gap: 0.25rem;
    background: #ffffff; border: 1px solid #e2e8f0; border-radius: 12px; padding: 0.8rem 1.1rem; min-width: 120px;
    box-shadow: 0 1px 2px rgba(15,23,42,0.04);
}
.pipe-node .material-symbols-rounded { color: #14497f; font-size: 1.7rem; }
.pipe-node span.t { font-size: 0.8rem; font-weight: 600; color: #334155; }
.pipe-arrow { color: #c8102e; }
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


# --------------------------------------------------------------------------
# Helpers HTML (icones, titres, KPI)
# --------------------------------------------------------------------------

def mi(name):
    """Icone Material Symbols inline (HTML)."""
    return f'<span class="material-symbols-rounded">{name}</span>'


def section_title(text, icon=None):
    icon_html = mi(icon) if icon else ""
    st.markdown(f'<div class="section-title">{icon_html}{text}</div>', unsafe_allow_html=True)


def kpi_card_html(label, value, icon, variant="", value_style=""):
    style = f' style="{value_style}"' if value_style else ""
    return (
        f'<div class="kpi-card {variant}"><div class="kpi-icon">{mi(icon)}</div>'
        f'<div><div class="kpi-label">{label}</div><div class="kpi-value"{style}>{value}</div></div></div>'
    )


def empty_state(icon, title, text):
    st.markdown(
        f'<div class="empty-state">{mi(icon)}<h4>{title}</h4><p>{text}</p></div>',
        unsafe_allow_html=True,
    )


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


@st.cache_data(show_spinner=False)
def _image_to_base64(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


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


def make_gauge(value_pct, height=240, title=None):
    """Jauge du taux d'elements OK (0-100 %)."""
    color = CHART_COLORS["ok"] if value_pct >= 90 else CHART_COLORS["warn"] if value_pct >= 70 else CHART_COLORS["err"]
    fig = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=value_pct,
            number=dict(suffix=" %", font=dict(size=30, color="#0f172a", family="Inter")),
            gauge=dict(
                axis=dict(range=[0, 100], tickwidth=1, tickcolor="#cbd5e1"),
                bar=dict(color=color, thickness=0.28),
                bgcolor="#f1f5f9",
                borderwidth=0,
                steps=[
                    dict(range=[0, 70], color="#fee2e2"),
                    dict(range=[70, 90], color="#fef3c7"),
                    dict(range=[90, 100], color="#dcfce7"),
                ],
            ),
        )
    )
    return _plotly_layout_defaults(fig, height, title, show_legend=False)


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


def make_delta_scatter(df, height=260):
    """Delta (continu et arrondi) en fonction de la longueur d'origine.

    La longueur d'origine est reconstruite : New Length (mm) - Delta arrondi (mm).
    Retourne None si les colonnes necessaires sont absentes.
    """
    needed = ["New Length (mm)", "Delta arrondi (mm)"]
    if not all(c in df.columns for c in needed):
        return None
    new_len = pd.to_numeric(df["New Length (mm)"], errors="coerce")
    d_round = pd.to_numeric(df["Delta arrondi (mm)"], errors="coerce")
    length = new_len - d_round
    fig = go.Figure()
    if "Delta predit continu (mm)" in df.columns:
        d_cont = pd.to_numeric(df["Delta predit continu (mm)"], errors="coerce")
        fig.add_trace(
            go.Scatter(
                x=length, y=d_cont, mode="markers", name="Delta continu",
                marker=dict(size=6, color=_with_alpha(CHART_COLORS["accent"], 0.55)),
            )
        )
    fig.add_trace(
        go.Scatter(
            x=length, y=d_round, mode="markers", name="Delta arrondi",
            marker=dict(size=6, color=_with_alpha(CHART_COLORS["primary_light"], 0.75), symbol="diamond"),
        )
    )
    fig.update_xaxes(showgrid=False, title_text="Longueur d'origine (mm)")
    fig.update_yaxes(showgrid=True, gridcolor="#e2e8f0", zeroline=True, zerolinecolor="#94a3b8", title_text="Delta (mm)")
    return _plotly_layout_defaults(fig, height, None, show_legend=True)


def model_delta(lengths, rules):
    """Delta continu predit par le modele pour un tableau de longueurs."""
    lengths = np.asarray(lengths, dtype=float)
    delta = rules["log_a"] * np.log(lengths) + rules["log_b"]
    for a_i, c_i, s_i in rules["gaussian_params"]:
        s_i = s_i if abs(s_i) > 1e-12 else 1e-12
        delta = delta + a_i * np.exp(-((lengths - c_i) ** 2) / (2.0 * s_i ** 2))
    return delta


def make_model_curve(rules, l_min, l_max, height=300):
    """Courbe du modele (continu) + version arrondie au pas metier."""
    lengths = np.linspace(max(l_min, 1), max(l_max, l_min + 1), 600)
    cont = model_delta(lengths, rules)
    step = max(rules["rounding_step"], 1)
    rounded = step * np.round(cont / step)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=lengths, y=cont, mode="lines", name="Delta continu",
                             line=dict(width=2.5, color=CHART_COLORS["primary_light"])))
    fig.add_trace(go.Scatter(x=lengths, y=rounded, mode="lines", name=f"Delta arrondi (pas {step} mm)",
                             line=dict(width=2, color=CHART_COLORS["lear_red"], shape="hv")))
    fig.update_xaxes(showgrid=False, title_text="Longueur L (mm)")
    fig.update_yaxes(showgrid=True, gridcolor="#e2e8f0", zeroline=True, zerolinecolor="#94a3b8", title_text="Delta (mm)")
    return _plotly_layout_defaults(fig, height, None, show_legend=True)


def chart_card_open(title, icon="insights"):
    st.markdown(
        f'<div class="chart-card"><div class="chart-card-title">{mi(icon)}{title}</div>',
        unsafe_allow_html=True,
    )


def chart_card_close():
    st.markdown("</div>", unsafe_allow_html=True)


# --------------------------------------------------------------------------
# Header (logo centre + nom + sous-titre) et footer (ligne rouge + LEAR)
# --------------------------------------------------------------------------

FALLBACK_LOGO_SVG = """
<svg class="app-logo-svg" viewBox="0 0 80 80" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="wcg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#14497f"/><stop offset="1" stop-color="#3b82f6"/>
    </linearGradient>
  </defs>
  <rect x="4" y="4" width="72" height="72" rx="18" fill="url(#wcg)"/>
  <path d="M14 48 C 26 20, 34 60, 46 32 S 62 40, 68 24" fill="none" stroke="#ffffff" stroke-width="5" stroke-linecap="round"/>
  <circle cx="14" cy="48" r="4.5" fill="#e4002b"/>
  <circle cx="68" cy="24" r="4.5" fill="#e4002b"/>
</svg>
"""


def render_app_header():
    """Logo centre en haut + 'WIRE CORRECT' + sous-titre, sur toutes les pages."""
    if os.path.exists(LOGO_APP):
        logo_html = f'<img class="app-logo" src="data:image/png;base64,{_image_to_base64(LOGO_APP)}">'
    else:
        logo_html = FALLBACK_LOGO_SVG
    st.markdown(
        f"""
        <div class="app-header">
            {logo_html}
            <div class="app-name">{APP_NAME}</div>
            <div class="app-name-bar"></div>
            <div class="app-sub">{APP_TAGLINE}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_footer():
    """Ligne rouge horizontale, puis LEAR Corporation et le slogan."""
    st.markdown(
        f"""
        <div class="app-footer">
            <div class="footer-redline"></div>
            <div class="footer-company">LEAR Corporation</div>
            <div class="footer-tagline">{LEAR_TAGLINE}</div>
            <div class="footer-meta">{PROJECT_TITLE} &middot; {PROJECT_TYPE} {PROJECT_ACADEMIC_YEAR} &middot; {PROJECT_AUTHOR}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# --------------------------------------------------------------------------
# Sidebar navigation
# --------------------------------------------------------------------------

def render_sidebar():
    with st.sidebar:
        if os.path.exists(LOGO_APP):
            logo_html = f'<img src="data:image/png;base64,{_image_to_base64(LOGO_APP)}">'
        elif os.path.exists(LOGO_LEAR):
            logo_html = f'<img src="data:image/png;base64,{_image_to_base64(LOGO_LEAR)}">'
        else:
            logo_html = ""
        st.markdown(
            f"""
            <div class="sidebar-brand">
                {logo_html}
                <div class="brand-text"><b>WIRE CORRECT</b><span>CORRECTION UCS</span></div>
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

        lear_logo_html = ""
        if os.path.exists(LOGO_LEAR):
            lear_logo_html = f'<img src="data:image/png;base64,{_image_to_base64(LOGO_LEAR)}" class="footer-logo">'
        st.markdown(
            f"""
            <div class="sidebar-footer">
                <div class="side-redline"></div>
                {lear_logo_html}
                <div class="footer-company">LEAR CORPORATION</div>
                <div class="footer-text">{LEAR_TAGLINE}<br>Version {MODEL_VERSION} &middot; {PROJECT_ACADEMIC_YEAR}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_topbar(page_key):
    title, crumbs, icon = PAGE_META[page_key]
    crumb_html = " &nbsp;›&nbsp; ".join(
        f"<b>{c}</b>" if i == len(crumbs) - 1 else c for i, c in enumerate(crumbs)
    )
    live_badge = f'<span class="app-badge-live">{mi("circle")} Session active</span>'
    st.markdown(
        f"""
        <div class="app-topbar">
            <div>
                <div class="app-breadcrumb">{crumb_html}</div>
                <div class="app-page-title"><span class="title-icon">{mi(icon)}</span>{title}</div>
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
            <span class="badge">{mi("person")} Realise par {PROJECT_AUTHOR}</span>
            <span class="badge">{mi("school")} {PROJECT_INSTITUTION}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        f"""
        <div class="highlight-bar">
            <div class="highlight-item"><div class="hl-icon">{mi("table_chart")}</div><div class="num">2</div><div class="label">Feuilles UCS supportees<br>(Wires / Tubes)</div></div>
            <div class="highlight-item"><div class="hl-icon">{mi("straighten")}</div><div class="num">{ROUNDING_STEP_MM} mm</div><div class="label">Pas d'arrondi par defaut</div></div>
            <div class="highlight-item"><div class="hl-icon">{mi("verified_user")}</div><div class="num">100%</div><div class="label">Fichier source jamais modifie</div></div>
            <div class="highlight-item"><div class="hl-icon">{mi("model_training")}</div><div class="num">{MODEL_VERSION}</div><div class="label">Version du modele actif</div></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Pipeline visuel
    st.markdown(
        f"""
        <div class="pipeline">
            <div class="pipe-node">{mi("upload_file")}<span class="t">Import UCS</span></div>
            <span class="pipe-arrow">{mi("arrow_forward")}</span>
            <div class="pipe-node">{mi("calculate")}<span class="t">Modele + arrondi</span></div>
            <span class="pipe-arrow">{mi("arrow_forward")}</span>
            <div class="pipe-node">{mi("fact_check")}<span class="t">Controle</span></div>
            <span class="pipe-arrow">{mi("arrow_forward")}</span>
            <div class="pipe-node">{mi("task_alt")}<span class="t">Validation</span></div>
            <span class="pipe-arrow">{mi("arrow_forward")}</span>
            <div class="pipe-node">{mi("download")}<span class="t">Export</span></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    left, right = st.columns([2, 1])
    with left:
        section_title("Contexte et problematique", "article")
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

        section_title("Modele mathematique utilise", "function")
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

        section_title("Courbe du modele (valeurs par defaut)", "show_chart")
        default_rules = {
            "rounding_step": ROUNDING_STEP_MM,
            "log_a": LOG_COEFF_A,
            "log_b": LOG_COEFF_B,
            "gaussian_params": [list(p) for p in GAUSSIAN_PARAMS],
        }
        chart_card_open("Delta predit en fonction de la longueur", "show_chart")
        st.plotly_chart(make_model_curve(default_rules, 50, 3000, height=280), use_container_width=True, config={"displayModeBar": False})
        chart_card_close()

        section_title("Technologies utilisees", "build")
        st.markdown(
            "".join(f'<span class="tech-chip">{t}</span>' for t in ["Python", "Streamlit", "pandas", "openpyxl", "python-docx", "plotly", "pytest"]),
            unsafe_allow_html=True,
        )

    with right:
        section_title("Fiche projet", "badge")
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
    section_title("Fonctionnalites principales", "star")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown(
            f"""<div class="feature-card"><div class="icon">{mi("upload_file")}</div><h4>Import et detection automatique</h4>
            <p>Detection automatique des feuilles Wires/Tubes et de leurs colonnes Name/Length,
            sans jamais alterer le fichier source.</p></div>""",
            unsafe_allow_html=True,
        )
    with col2:
        st.markdown(
            f"""<div class="feature-card"><div class="icon">{mi("tune")}</div><h4>Regles metier modifiables</h4>
            <p>Pas d'arrondi et coefficients du modele ajustables et sauvegardables,
            puis appliques automatiquement a chaque nouveau calcul.</p></div>""",
            unsafe_allow_html=True,
        )
    with col3:
        st.markdown(
            f"""<div class="feature-card"><div class="icon">{mi("history")}</div><h4>Historique et tracabilite</h4>
            <p>Chaque calcul est trace en session, avec rapport exportable
            (Excel/CSV) et demande d'ajustement (.docx).</p></div>""",
            unsafe_allow_html=True,
        )

    st.write("")
    section_title("Comment ca marche", "help")
    steps = [
        ("Importer", "Deposer un fichier UCS (.xlsx) contenant les feuilles Wires et/ou Tubes.", "upload_file"),
        ("Calculer", "L'application detecte les colonnes, applique les regles actives et arrondit chaque delta.", "calculate"),
        ("Verifier", "Le tableau de controle liste chaque element avec son statut (OK / avertissement / erreur).", "fact_check"),
        ("Valider et exporter", "Une fois valide, le calcul est trace dans l'historique et les fichiers sont prets a exporter.", "task_alt"),
    ]
    for i, (title, desc, icon) in enumerate(steps, start=1):
        st.markdown(
            f"""<div class="step-row"><div class="step-number">{mi(icon)}</div>
                <div class="step-text"><h5>{i}. {title}</h5><p>{desc}</p></div></div>""",
            unsafe_allow_html=True,
        )

    st.write("")
    st.divider()
    if st.button("Acceder a l'outil", type="primary", icon=":material/arrow_forward:"):
        st.session_state.page = "dashboard"
        st.rerun()


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
    ok_rate = round(100 * n_ok / n_elements, 1) if n_elements else 0

    st.markdown(
        f"""
        <div class="kpi-row">
            {kpi_card_html("Calculs (session)", n_calculs, "calculate")}
            {kpi_card_html("Elements traites", n_elements, "cable", "ok")}
            {kpi_card_html("Avertissements cumules", n_warnings, "warning", "warn")}
            {kpi_card_html("Erreurs cumulees", n_errors, "error", "err")}
        </div>
        """,
        unsafe_allow_html=True,
    )

    if historique:
        chart_col1, chart_col2, chart_col3, chart_col4 = st.columns([1, 1, 1.2, 1.3])
        recent = list(reversed(historique[:8]))
        labels = [f'{h["timestamp"][11:16]}' for h in recent]
        with chart_col1:
            chart_card_open("Statuts", "donut_large")
            st.plotly_chart(make_status_donut(n_ok, n_warnings, n_errors, height=230), use_container_width=True, config={"displayModeBar": False})
            chart_card_close()
        with chart_col2:
            chart_card_open("Taux d'elements OK", "speed")
            st.plotly_chart(make_gauge(ok_rate, height=230), use_container_width=True, config={"displayModeBar": False})
            chart_card_close()
        with chart_col3:
            chart_card_open("Elements par calcul", "bar_chart")
            st.plotly_chart(
                make_bar_chart(labels, [h["n_total"] for h in recent], color=CHART_COLORS["primary"], height=230),
                use_container_width=True,
                config={"displayModeBar": False},
            )
            chart_card_close()
        with chart_col4:
            chart_card_open("Tendance avertissements / erreurs", "trending_up")
            st.plotly_chart(
                make_trend_chart(
                    labels,
                    {
                        "Avertissements": ([h["n_warnings"] for h in recent], CHART_COLORS["warn"]),
                        "Erreurs": ([h["n_errors"] for h in recent], CHART_COLORS["err"]),
                    },
                    height=230,
                ),
                use_container_width=True,
                config={"displayModeBar": False},
            )
            chart_card_close()
    else:
        empty_state(
            "monitoring",
            "Aucune statistique pour l'instant",
            "Les graphiques apparaitront apres votre premier calcul valide.",
        )

    left, right = st.columns([1.6, 1])

    with left:
        section_title("Derniers calculs", "schedule")
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

        section_title("Acces rapide", "bolt")
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
        section_title("Regles actives", "rule")
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
        if st.button("Modifier les regles", use_container_width=True, icon=":material/tune:"):
            st.session_state.page = "rules"
            st.rerun()

        if st.session_state.results is not None:
            section_title("Calcul en cours", "pending_actions")
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

        if st.button("Calculer", type="primary", icon=":material/play_arrow:"):
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

        n_total = len(result.results_df)
        ok_rate = round(100 * result.n_ok / n_total, 1) if n_total else 0

        st.markdown(
            f"""
            <div class="kpi-row">
                {kpi_card_html("Elements traites", n_total, "cable")}
                {kpi_card_html("OK", result.n_ok, "check_circle", "ok")}
                {kpi_card_html("Avertissements", result.n_warnings, "warning", "warn")}
                {kpi_card_html("Erreurs", result.n_errors, "error", "err")}
            </div>
            """,
            unsafe_allow_html=True,
        )

        chart_col1, chart_col2, chart_col3 = st.columns([1, 1, 1.5])
        with chart_col1:
            chart_card_open("Repartition des statuts", "donut_large")
            st.plotly_chart(
                make_status_donut(result.n_ok, result.n_warnings, result.n_errors, height=230),
                use_container_width=True,
                config={"displayModeBar": False},
            )
            chart_card_close()
        with chart_col2:
            chart_card_open("Taux d'elements OK", "speed")
            st.plotly_chart(make_gauge(ok_rate, height=230), use_container_width=True, config={"displayModeBar": False})
            chart_card_close()
        with chart_col3:
            chart_card_open("Statuts par feuille", "stacked_bar_chart")
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

        scatter_fig = make_delta_scatter(result.results_df, height=280)
        if scatter_fig is not None:
            chart_card_open("Delta predit en fonction de la longueur d'origine", "scatter_plot")
            st.plotly_chart(scatter_fig, use_container_width=True, config={"displayModeBar": False})
            chart_card_close()

        section_title("Tableau de controle", "table_view")
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

        section_title("Validation", "task_alt")
        st.session_state.validated = st.checkbox(
            "Je valide ce tableau de controle et souhaite conserver ce calcul",
            value=st.session_state.validated,
        )

        if st.session_state.validated:
            record_history_entry()

            summary = build_change_summary(result.results_df)
            s = summary["stats"]

            section_title("Resume des modifications", "difference")
            st.markdown(
                f"""
                <div class="kpi-row">
                    {kpi_card_html("Elements modifies", s["n_modified"], "edit")}
                    {kpi_card_html("Longueurs augmentees", s["n_increased"], "trending_up", "warn")}
                    {kpi_card_html("Longueurs diminuees", s["n_decreased"], "trending_down")}
                    {kpi_card_html("Ecart moyen (mm)", s["mean_delta_abs"], "swap_vert", "ok")}
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.caption(
                f"Inchanges : {s['n_unchanged']} - "
                f"Plus grande augmentation : {s['max_increase']:+} mm - "
                f"Plus grande diminution : {s['max_decrease']:+} mm"
            )

            chg_col1, chg_col2 = st.columns([1, 1.6])
            with chg_col1:
                chart_card_open("Repartition des modifications", "donut_small")
                st.plotly_chart(
                    _modification_donut(s),
                    use_container_width=True,
                    config={"displayModeBar": False},
                )
                chart_card_close()
            with chg_col2:
                chart_card_open("Distribution des deltas arrondis (mm)", "bar_chart")
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
                if st.button("Aller aux exportations", type="primary", icon=":material/file_download:"):
                    st.session_state.page = "exportations"
                    st.rerun()
            with ec2:
                if st.button("Voir l'historique", icon=":material/history:"):
                    st.session_state.page = "historique"
                    st.rerun()
    else:
        empty_state(
            "upload_file",
            "Aucun fichier calcule",
            "Importez un fichier UCS (.xlsx) puis cliquez sur « Calculer » pour demarrer.",
        )


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
        st.markdown(f'<span class="tag-pill custom">{mi("tune")} Regles personnalisees actives</span>', unsafe_allow_html=True)
    else:
        st.markdown(f'<span class="tag-pill">{mi("verified")} Valeurs par defaut du cahier des charges</span>', unsafe_allow_html=True)

    r = st.session_state.rules

    # Apercu visuel des regles actuellement sauvegardees
    section_title("Apercu de la courbe du modele", "show_chart")
    range_col1, range_col2 = st.columns(2)
    with range_col1:
        l_min = st.number_input("Longueur min (mm)", min_value=1, value=50, step=10)
    with range_col2:
        l_max = st.number_input("Longueur max (mm)", min_value=10, value=3000, step=50)
    chart_card_open("Delta continu vs delta arrondi (regles sauvegardees)", "show_chart")
    st.plotly_chart(make_model_curve(r, float(l_min), float(l_max), height=300), use_container_width=True, config={"displayModeBar": False})
    chart_card_close()

    with st.form("rules_form"):
        section_title("Pas d'arrondi metier", "straighten")
        rounding_step = st.number_input(
            "Pas d'arrondi (mm)",
            min_value=1,
            max_value=50,
            value=int(r["rounding_step"]),
            step=1,
            help="Delta_arrondi = pas x round(Delta / pas)",
        )

        section_title("Composante logarithmique", "function")
        lc1, lc2 = st.columns(2)
        with lc1:
            log_a = st.number_input("Coefficient a (Delta = a.ln(L) + b + ...)", value=float(r["log_a"]), format="%.6f")
        with lc2:
            log_b = st.number_input("Coefficient b", value=float(r["log_b"]), format="%.6f")

        section_title("Corrections gaussiennes (a_i, C_i, sigma_i)", "ssid_chart")
        gaussian_df = pd.DataFrame(r["gaussian_params"], columns=["a_i", "C_i", "sigma_i"])
        edited_gaussian_df = st.data_editor(
            gaussian_df,
            use_container_width=True,
            num_rows="fixed",
            key="gaussian_editor",
        )

        col_save, col_reset = st.columns([1, 1])
        submitted = col_save.form_submit_button("Sauvegarder et appliquer", type="primary", use_container_width=True, icon=":material/save:")
        reset = col_reset.form_submit_button("Reinitialiser aux valeurs par defaut", use_container_width=True, icon=":material/restart_alt:")

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

    section_title("Formule appliquee", "calculate")
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
        empty_state("history", "Historique vide", "Aucun calcul valide pour l'instant dans cette session.")
        if st.button("Aller a « Correction des longueurs »", type="primary", icon=":material/straighten:"):
            st.session_state.page = "correction"
            st.rerun()
        return

    top_col1, top_col2 = st.columns([3, 1])
    with top_col1:
        st.caption(f"{len(historique)} calcul(s) enregistre(s) dans cette session.")
    with top_col2:
        if st.button("Vider l'historique", use_container_width=True, icon=":material/delete:"):
            st.session_state.historique = []
            st.session_state.selected_history_id = None
            st.rerun()

    total_el = sum(h["n_total"] for h in historique)
    st.markdown(
        f"""
        <div class="kpi-row">
            {kpi_card_html("Calculs", len(historique), "calculate")}
            {kpi_card_html("Elements", total_el, "cable", "ok")}
            {kpi_card_html("Avertissements", sum(h["n_warnings"] for h in historique), "warning", "warn")}
            {kpi_card_html("Erreurs", sum(h["n_errors"] for h in historique), "error", "err")}
        </div>
        """,
        unsafe_allow_html=True,
    )

    if len(historique) > 1:
        chronological = list(reversed(historique))
        labels = [f'{h["timestamp"][5:16]}' for h in chronological]
        chart_col1, chart_col2 = st.columns([1.6, 1])
        with chart_col1:
            chart_card_open("Evolution des avertissements / erreurs par calcul", "trending_up")
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
            chart_card_open("Repartition cumulee", "donut_large")
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

    section_title("Detail d'un calcul", "manage_search")
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
            if st.button("Ouvrir dans Rapports", use_container_width=True, icon=":material/fact_check:"):
                st.session_state.selected_history_id = entry["id"]
                st.session_state.page = "rapports"
                st.rerun()
        with rc2:
            if st.button("Exporter ce calcul", use_container_width=True, icon=":material/file_download:"):
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
        empty_state("fact_check", "Aucun rapport disponible", "Effectuez d'abord un calcul valide.")
        if st.button("Aller a « Correction des longueurs »", type="primary", icon=":material/straighten:"):
            st.session_state.page = "correction"
            st.rerun()
        return

    options = {f'{h["timestamp"]} — {h["filename"]}': h["id"] for h in historique}
    default_id = st.session_state.selected_history_id or historique[0]["id"]
    default_label = next((k for k, v in options.items() if v == default_id), list(options.keys())[0])
    label = st.selectbox("Rapport a afficher", list(options.keys()), index=list(options.keys()).index(default_label))
    entry = get_history_entry(options[label])
    st.session_state.selected_history_id = entry["id"]

    section_title("Synthese", "summarize")
    st.markdown(
        f"""
        <div class="kpi-row">
            {kpi_card_html("Fichier source", entry['filename'], "description", "", "font-size:1.05rem;")}
            {kpi_card_html("OK", entry['n_ok'], "check_circle", "ok")}
            {kpi_card_html("Avertissements", entry['n_warnings'], "warning", "warn")}
            {kpi_card_html("Erreurs", entry['n_errors'], "error", "err")}
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
    ok_rate = round(100 * entry["n_ok"] / entry["n_total"], 1) if entry["n_total"] else 0

    section_title("Repartition des statuts", "donut_large")
    donut_col, gauge_col, hist_col = st.columns([1, 1, 1.4])
    with donut_col:
        chart_card_open("Statuts", "donut_large")
        st.plotly_chart(
            make_status_donut(entry["n_ok"], entry["n_warnings"], entry["n_errors"], height=250),
            use_container_width=True,
            config={"displayModeBar": False},
        )
        chart_card_close()
    with gauge_col:
        chart_card_open("Taux d'elements OK", "speed")
        st.plotly_chart(make_gauge(ok_rate, height=250), use_container_width=True, config={"displayModeBar": False})
        chart_card_close()
    with hist_col:
        chart_card_open("Distribution des deltas arrondis (mm)", "bar_chart")
        delta_values = df["Delta arrondi (mm)"].dropna().tolist()
        if delta_values:
            st.plotly_chart(make_histogram(delta_values, color=CHART_COLORS["primary_light"], height=250), use_container_width=True, config={"displayModeBar": False})
        else:
            st.info("Aucune valeur de delta disponible pour ce calcul.")
        chart_card_close()

    scatter_fig = make_delta_scatter(df, height=260)
    if scatter_fig is not None:
        chart_card_open("Delta predit en fonction de la longueur d'origine", "scatter_plot")
        st.plotly_chart(scatter_fig, use_container_width=True, config={"displayModeBar": False})
        chart_card_close()

    section_title("Resume des modifications", "difference")
    summary = build_change_summary(df)
    s = summary["stats"]
    st.markdown(
        f"""
        <div class="kpi-row">
            {kpi_card_html("Elements modifies", s["n_modified"], "edit")}
            {kpi_card_html("Longueurs augmentees", s["n_increased"], "trending_up", "warn")}
            {kpi_card_html("Longueurs diminuees", s["n_decreased"], "trending_down")}
            {kpi_card_html("Ecart moyen (mm)", s["mean_delta_abs"], "swap_vert", "ok")}
        </div>
        """,
        unsafe_allow_html=True,
    )

    mod_col1, mod_col2 = st.columns([1, 1.4])
    with mod_col1:
        chart_card_open("Augmentees / diminuees / inchangees", "donut_small")
        st.plotly_chart(_modification_donut(s, height=230), use_container_width=True, config={"displayModeBar": False})
        chart_card_close()
    with mod_col2:
        chart_card_open("Elements par feuille et par statut", "stacked_bar_chart")
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

    section_title("Tableau de controle complet", "table_view")
    show_issues_only = st.checkbox("Afficher uniquement les avertissements / erreurs", key="rapport_issues_only")
    display_df = df if not show_issues_only else df[df["Statut"] != "OK"]
    st.dataframe(_display_results_df(display_df), use_container_width=True, hide_index=True)

    if st.button("Exporter ce rapport", type="primary", icon=":material/file_download:"):
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
        empty_state("file_download", "Rien a exporter", "Effectuez d'abord un calcul valide.")
        if st.button("Aller a « Correction des longueurs »", type="primary", icon=":material/straighten:"):
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

    section_title("Fichiers disponibles", "folder_open")
    export_col1, export_col2, export_col3 = st.columns(3)

    with export_col1:
        st.markdown(f"{mi('table_view')} **UCS corrige**", unsafe_allow_html=True)
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
                f"Telecharger UCS corrige — {suffix} (.xlsx)",
                data=corrected_ucs_bytes,
                file_name=f"{base_name}_corrected_{suffix}_{timestamp}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
                icon=":material/download:",
            )
        else:
            st.caption("Fichier source non disponible pour ce calcul.")

    with export_col2:
        st.markdown(f"{mi('fact_check')} **Rapport de calcul**", unsafe_allow_html=True)
        st.caption("Tableau de controle complet (deltas arrondi et continu inclus), au format tableur.")
        report_xlsx = export_report_excel(entry["results_df"])
        st.download_button(
            "Rapport (.xlsx)",
            data=report_xlsx,
            file_name=f"{base_name}_rapport_{timestamp}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
            icon=":material/download:",
        )
        report_csv = export_report_csv(entry["results_df"])
        st.download_button(
            "Rapport (.csv)",
            data=report_csv,
            file_name=f"{base_name}_rapport_{timestamp}.csv",
            mime="text/csv",
            use_container_width=True,
            icon=":material/download:",
        )

    with export_col3:
        st.markdown(f"{mi('description')} **Demande d'ajustement**", unsafe_allow_html=True)
        project_name = st.text_input("Nom du projet / faisceau", value=base_name, key="export_project_name")
        letter_bytes = generate_adjustment_letter(entry["results_df"], project_name=project_name)
        st.download_button(
            "Demande d'ajustement (.docx)",
            data=letter_bytes,
            file_name=f"{base_name}_demande_ajustement_{timestamp}.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            use_container_width=True,
            icon=":material/download:",
        )

    section_title("Recapitulatif du calcul selectionne", "receipt_long")
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

render_app_header()

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

render_footer()
