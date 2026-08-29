"""
Orchestration du pipeline UCS : parse -> calcul -> arrondi -> validation ->
tableau de resultats (cahier, section 5 et 10).
"""

from dataclasses import dataclass
from datetime import datetime

import pandas as pd

from config import MODEL_VERSION, ROUNDING_STEP_MM
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


RESULT_COLUMNS = [
    "Feuille",
    "Ligne Excel",
    "Wire/Tube Name",
    "Old Length (mm)",
    "Delta predit continu (mm)",
    "Delta arrondi (mm)",
    "New Length (mm)",
    "Statut",
    "Avertissement / Erreur",
    "Version du modele",
    "Date/heure",
]


def process_ucs_file(file_path_or_buffer, rounding_step=ROUNDING_STEP_MM):
    """
    Execute le pipeline complet sur un fichier UCS et retourne un
    ProcessingResult pret a etre affiche / exporte.
    """
    layouts, rows, skipped_sheets = parse_ucs_file(file_path_or_buffer)

    names_by_sheet = {}
    for row in rows:
        names_by_sheet.setdefault(row.sheet_name, []).append(
            str(row.wire_tube_name).strip() if row.wire_tube_name is not None else ""
        )
    duplicates_by_sheet = {
        sheet: detect_duplicate_names(names) for sheet, names in names_by_sheet.items()
    }

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    records = []

    for row in rows:
        name_value, name_warnings = validate_name(row.wire_tube_name)
        length_value, length_errors = validate_length(row.old_length_raw)

        is_duplicate = name_value in duplicates_by_sheet.get(row.sheet_name, set())

        delta_continuous = None
        delta_rounded = None
        new_length = None
        calc_errors = []

        if length_value is not None:
            try:
                delta_continuous, delta_rounded, new_length = compute_new_length(
                    length_value, rounding_step=rounding_step
                )
            except ValueError as exc:
                calc_errors.append(str(exc))

        row_status = build_row_status(length_errors, name_warnings, is_duplicate, calc_errors)

        records.append(
            {
                "Feuille": row.sheet_name,
                "Ligne Excel": row.excel_row_index,
                "Wire/Tube Name": name_value if name_value else row.wire_tube_name,
                "Old Length (mm)": length_value if length_value is not None else row.old_length_raw,
                "Delta predit continu (mm)": round(delta_continuous, 3) if delta_continuous is not None else None,
                "Delta arrondi (mm)": delta_rounded,
                "New Length (mm)": new_length,
                "Statut": row_status.status,
                "Avertissement / Erreur": " | ".join(row_status.messages) if row_status.messages else "",
                "Version du modele": MODEL_VERSION,
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