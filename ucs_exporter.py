"""
Export de l'UCS corrige.

Regle imperative (cahier, section 12 et 23) : le fichier source ne doit
JAMAIS etre modifie. Ce module travaille sur une copie du classeur original
et ne modifie QUE les cellules "Length" des lignes traitees avec succes ;
tout le reste (autres feuilles, mise en forme, colonnes non concernees)
reste strictement identique.
"""

import io

import openpyxl


def export_corrected_ucs(source_file_path_or_buffer, results_df, layouts):
    """
    :param source_file_path_or_buffer: fichier UCS source original (jamais modifie sur disque)
    :param results_df: DataFrame produit par processor.process_ucs_file
    :param layouts: dict {sheet_name: SheetLayout} renvoye par ucs_parser.parse_ucs_file,
        utilise pour ecrire dans la bonne colonne Length de chaque feuille.
    :return: bytes du classeur .xlsx corrige, pret a etre propose au telechargement.
    """
    workbook = openpyxl.load_workbook(source_file_path_or_buffer)

    updatable_rows = results_df[
        results_df["New Length (mm)"].notna() & (results_df["Statut"] != "ERREUR")
    ]

    for _, record in updatable_rows.iterrows():
        sheet_name = record["Feuille"]
        layout = layouts.get(sheet_name)

        if layout is None or sheet_name not in workbook.sheetnames:
            continue

        worksheet = workbook[sheet_name]
        excel_row = int(record["Ligne Excel"])
        worksheet.cell(row=excel_row, column=layout.length_col_index).value = record["New Length (mm)"]

    buffer = io.BytesIO()
    workbook.save(buffer)
    buffer.seek(0)
    return buffer.getvalue()