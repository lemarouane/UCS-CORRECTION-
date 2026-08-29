"""
Export du rapport de calcul / tableau de controle
(cahier, section 14.2 et 11).
"""

import io

import pandas as pd


def export_report_excel(results_df):
    """Retourne les bytes d'un fichier .xlsx contenant le tableau de controle."""
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        results_df.to_excel(writer, index=False, sheet_name="Rapport de calcul")
    buffer.seek(0)
    return buffer.getvalue()


def export_report_csv(results_df):
    """Retourne les bytes d'un fichier .csv (separateur ;, encodage utf-8-sig pour Excel FR)."""
    return results_df.to_csv(index=False, sep=";").encode("utf-8-sig")