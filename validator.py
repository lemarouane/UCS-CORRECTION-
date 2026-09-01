"""
Controles et regles de validation des donnees d'entree UCS
(cahier des charges, section 12).
"""

from dataclasses import dataclass, field


@dataclass
class RowValidation:
    is_valid: bool
    status: str  # "OK", "ERREUR", "AVERTISSEMENT"
    messages: list = field(default_factory=list)


def validate_length(raw_length):
    """
    Verifie que la longueur est numerique et strictement positive.
    Retourne (longueur_normalisee: float|None, erreurs: list[str]).
    """
    errors = []

    if raw_length is None or (isinstance(raw_length, str) and raw_length.strip() == ""):
        errors.append("Old/Current Length manquante.")
        return None, errors

    try:
        length_value = float(raw_length)
    except (TypeError, ValueError):
        errors.append(f"Old/Current Length non numerique : {raw_length!r}.")
        return None, errors

    if length_value == 0:
        errors.append("Old/Current Length est egale a zero.")
        return None, errors

    if length_value < 0:
        errors.append(f"Old/Current Length est negative ({length_value}).")
        return None, errors

    return length_value, errors


def validate_name(raw_name):
    """
    Verifie la presence du Wire Name.
    Retourne (nom_normalise: str, avertissements: list[str]).
    """
    warnings = []
    if raw_name is None or str(raw_name).strip() == "":
        warnings.append("Wire Name manquant.")
        return "", warnings
    return str(raw_name).strip(), warnings


def detect_duplicate_names(names):
    """
    Detecte les doublons de Wire Name sans suppression silencieuse
    (cahier, section 12). Retourne un set des noms en doublon.
    """
    seen = set()
    duplicates = set()
    for name in names:
        if not name:
            continue
        if name in seen:
            duplicates.add(name)
        else:
            seen.add(name)
    return duplicates


def build_row_status(length_errors, name_warnings, is_duplicate, calc_errors):
    """
    Agrege les erreurs/avertissements d'une ligne en un statut unique et
    une liste de messages, pour affichage dans le tableau de controle.
    """
    messages = []
    messages.extend(length_errors)
    messages.extend(calc_errors)
    messages.extend(name_warnings)
    if is_duplicate:
        messages.append("Wire Name en doublon dans la feuille.")

    if length_errors or calc_errors:
        return RowValidation(is_valid=False, status="ERREUR", messages=messages)
    if name_warnings or is_duplicate:
        return RowValidation(is_valid=True, status="AVERTISSEMENT", messages=messages)
    return RowValidation(is_valid=True, status="OK", messages=messages)