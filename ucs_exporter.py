"""
Export de l'UCS corrige.

Regle imperative (cahier, section 12 et 23) : le fichier source ne doit
JAMAIS etre modifie. Ce module travaille sur une copie du classeur original
et ne modifie QUE les cellules "Length" des lignes traitees avec succes ;
tout le reste (autres feuilles, mise en forme, colonnes non concernees)
reste strictement identique.

L'utilisateur peut choisir la longueur a ecrire dans le fichier corrige via
`length_column` :
  - "New Length (mm)"                  -> longueur basee sur le delta ARRONDI au pas metier (par defaut)
  - "New Length - delta continu (mm)"  -> longueur basee sur le delta CONTINU (non arrondi)
"""

import io

import openpyxl

DEFAULT_LENGTH_COLUMN = "New Length (mm)"
CONTINUOUS_LENGTH_COLUMN = "New Length - delta continu (mm)"


def export_corrected_ucs(source_file_path_or_buffer, results_df, layouts, length_column=DEFAULT_LENGTH_COLUMN):
    """
    :param source_file_path_or_buffer: fichier UCS source original (jamais modifie sur disque)
    :param results_df: DataFrame produit par processor.process_ucs_file
    :param layouts: dict {sheet_name: SheetLayout} renvoye par ucs_parser.parse_ucs_file,
        utilise pour ecrire dans la bonne colonne Length de chaque feuille.
    :param length_column: nom de la colonne de results_df a utiliser comme nouvelle longueur
        (arrondie ou delta continu -- voir DEFAULT_LENGTH_COLUMN / CONTINUOUS_LENGTH_COLUMN).
    :return: bytes du classeur .xlsx corrige, pret a etre propose au telechargement.
    """
    if length_column not in results_df.columns:
        raise ValueError(f"Colonne de longueur inconnue : {length_column!r}.")

    workbook = openpyxl.load_workbook(source_file_path_or_buffer)

    updatable_rows = results_df[
        results_df[length_column].notna() & (results_df["Statut"] != "ERREUR")
    ]

    for _, record in updatable_rows.iterrows():
        sheet_name = record["Feuille"]
        layout = layouts.get(sheet_name)

        if layout is None or sheet_name not in workbook.sheetnames:
            continue

        worksheet = workbook[sheet_name]
        excel_row = int(record["Ligne Excel"])
        worksheet.cell(row=excel_row, column=layout.length_col_index).value = record[length_column]

    buffer = io.BytesIO()
    workbook.save(buffer)
    buffer.seek(0)
    return buffer.getvalue()