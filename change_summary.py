"""
Resume statique (sans IA) des modifications effectuees sur un UCS.
Calcule uniquement a partir du tableau de controle deja produit par
processor.process_ucs_file -- aucun appel externe.
"""

import pandas as pd


def build_change_summary(results_df):
    """
    Retourne un dict avec :
      - stats : compteurs agreges (modifies, augmentes, diminues, inchanges...)
      - per_sheet : DataFrame recapitulatif par feuille
      - changes_df : DataFrame des lignes reellement modifiees (delta != 0),
        triees par ampleur de changement decroissante
    """
    df = results_df.copy()

    modified = df[df["Delta arrondi (mm)"].notna() & (df["Delta arrondi (mm)"] != 0)].copy()
    increased = modified[modified["Delta arrondi (mm)"] > 0]
    decreased = modified[modified["Delta arrondi (mm)"] < 0]
    unchanged = df[df["Delta arrondi (mm)"] == 0]

    modified["Delta abs (mm)"] = modified["Delta arrondi (mm)"].abs()
    changes_df = modified.sort_values("Delta abs (mm)", ascending=False).drop(columns=["Delta abs (mm)"])
    changes_df = changes_df[
        [
            "Feuille",
            "Wire Name",
            "Old Length (mm)",
            "Delta predit continu (mm)",
            "Delta arrondi (mm)",
            "New Length (mm)",
            "New Length - delta continu (mm)",
            "Statut",
        ]
    ]

    stats = {
        "total": len(df),
        "n_modified": len(modified),
        "n_increased": len(increased),
        "n_decreased": len(decreased),
        "n_unchanged": len(unchanged),
        "mean_delta_abs": round(modified["Delta arrondi (mm)"].abs().mean(), 1) if len(modified) else 0,
        "max_increase": int(increased["Delta arrondi (mm)"].max()) if len(increased) else 0,
        "max_decrease": int(decreased["Delta arrondi (mm)"].min()) if len(decreased) else 0,
    }

    per_sheet = (
        df.groupby("Feuille")
        .apply(
            lambda g: pd.Series(
                {
                    "Elements": len(g),
                    "Modifies": int((g["Delta arrondi (mm)"] != 0).sum()),
                    "Inchanges": int((g["Delta arrondi (mm)"] == 0).sum()),
                }
            )
        )
        .reset_index()
    )

    return {"stats": stats, "per_sheet": per_sheet, "changes_df": changes_df}