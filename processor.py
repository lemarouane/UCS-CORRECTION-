"""
Orchestration du pipeline UCS : parse -> calcul -> arrondi -> validation ->
tableau de resultats (cahier, section 5 et 10).

Ce module accepte desormais des parametres de modele/arrondi optionnels
(log_a, log_b, gaussian_params, rounding_step) afin de permettre a
l'application de piloter le calcul avec les regles definies et sauvegardees
par le metier sur la page "Regles d'arrondi", sans jamais modifier les
valeurs par defaut de config.py (qui restent la reference d'origine).

Seuls les Wires sont traites (les Tubes sont hors perimetre, cf. config).
"""

from dataclasses import dataclass
from datetime import datetime

import pandas as pd

from config import (
    MODEL_VERSION,
    ROUNDING_STEP_MM,
    LOG_COEFF_A,
    LOG_COEFF_B,
    GAUSSIAN_PARAMS,
)
from model import compute_new_length
from ucs_parser import parse_ucs_file
from validator import validate_length, validate_name, detect_duplicate_names, build_row_status


@dataclass
class ProcessingResult:
    results_df: "pd.DataFrame"
    layouts: dict
    skipped_sheets: list
    n_ok: int
    n_warnings: int
    n_errors: int


# Deux longueurs "nouvelle" sont disponibles en sortie :
#   - "New Length (mm)"                    -> basee sur le delta ARRONDI au pas metier
#   - "New Length - delta continu (mm)"    -> basee sur le delta CONTINU (non arrondi) predit par le modele
# Le choix de la colonne a utiliser pour l'export est fait par l'utilisateur (page Exportations).
RESULT_COLUMNS = [
    "Feuille",
    "Ligne Excel",
    "Wire Name",
    "Old Length (mm)",
    "Delta predit continu (mm)",
    "Delta arrondi (mm)",
    "New Length (mm)",
    "New Length - delta continu (mm)",
    "Statut",
    "Avertissement / Erreur",
    "Version du modele",
    "Date/heure",
]


def process_ucs_file(
    file_path_or_buffer,
    rounding_step=ROUNDING_STEP_MM,
    log_a=LOG_COEFF_A,
    log_b=LOG_COEFF_B,
    gaussian_params=GAUSSIAN_PARAMS,
    model_version_label=MODEL_VERSION,
):
    """
    Execute le pipeline complet sur un fichier UCS et retourne un
    ProcessingResult pret a etre affiche / exporte.

    :param rounding_step: pas d'arrondi metier (mm), issu des regles actives
    :param log_a: coefficient "a" de la composante logarithmique du modele
    :param log_b: coefficient "b" de la composante logarithmique du modele
    :param gaussian_params: liste de (ai, Ci, sigma_i) pour les corrections gaussiennes
    :param model_version_label: etiquette affichee dans le rapport (ex : "MODEL_V1 (personnalise)")
    """
    layouts, rows, skipped_sheets = parse_ucs_file(file_path_or_buffer)

    names_by_sheet = {}
    for row in rows:
        names_by_sheet.setdefault(row.sheet_name, []).append(
            str(row.wire_name).strip() if row.wire_name is not None else ""
        )
    duplicates_by_sheet = {
        sheet: detect_duplicate_names(names) for sheet, names in names_by_sheet.items()
    }

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    records = []

    for row in rows:
        name_value, name_warnings = validate_name(row.wire_name)
        length_value, length_errors = validate_length(row.old_length_raw)

        is_duplicate = name_value in duplicates_by_sheet.get(row.sheet_name, set())

        delta_continuous = None
        delta_rounded = None
        new_length = None
        new_length_continuous = None
        calc_errors = []

        if length_value is not None:
            try:
                delta_continuous, delta_rounded, new_length = compute_new_length(
                    length_value,
                    log_a=log_a,
                    log_b=log_b,
                    gaussian_params=gaussian_params,
                    rounding_step=rounding_step,
                )
                new_length_continuous = length_value + delta_continuous
            except ValueError as exc:
                calc_errors.append(str(exc))

        row_status = build_row_status(length_errors, name_warnings, is_duplicate, calc_errors)

        records.append(
            {
                "Feuille": row.sheet_name,
                "Ligne Excel": row.excel_row_index,
                "Wire Name": name_value if name_value else row.wire_name,
                "Old Length (mm)": length_value if length_value is not None else row.old_length_raw,
                "Delta predit continu (mm)": round(delta_continuous, 3) if delta_continuous is not None else None,
                "Delta arrondi (mm)": delta_rounded,
                "New Length (mm)": new_length,
                "New Length - delta continu (mm)": (
                    round(new_length_continuous, 3) if new_length_continuous is not None else None
                ),
                "Statut": row_status.status,
                "Avertissement / Erreur": " | ".join(row_status.messages) if row_status.messages else "",
                "Version du modele": model_version_label,
                "Date/heure": now_str,
            }
        )

    results_df = pd.DataFrame(records, columns=RESULT_COLUMNS)

    n_ok = int((results_df["Statut"] == "OK").sum())
    n_warnings = int((results_df["Statut"] == "AVERTISSEMENT").sum())
    n_errors = int((results_df["Statut"] == "ERREUR").sum())

    return ProcessingResult(
        results_df=results_df,
        layouts=layouts,
        skipped_sheets=skipped_sheets,
        n_ok=n_ok,
        n_warnings=n_warnings,
        n_errors=n_errors,
    )