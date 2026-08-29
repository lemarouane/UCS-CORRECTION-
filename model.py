"""
Modele mathematique de prediction de la variation de longueur (Delta).

Formule (cahier des charges, section 7-8) :
Delta_hat(L) = a*ln(L) + b + Somme_i ai * exp(-(L-Ci)^2 / (2*sigma_i^2))

Ce module est volontairement independant de Streamlit, de l'UCS et de tout
I/O : il est testable avec une simple liste de longueurs (cahier, section 15).
"""

import math
from decimal import Decimal, ROUND_HALF_UP

from config import (
    LOG_COEFF_A,
    LOG_COEFF_B,
    GAUSSIAN_PARAMS,
    ROUNDING_STEP_MM,
)


def predict_delta(length_mm, log_a=LOG_COEFF_A, log_b=LOG_COEFF_B, gaussian_params=GAUSSIAN_PARAMS):
    """
    Calcule le Delta continu predit par le modele pour une longueur donnee.

    :param length_mm: Old/Current Length en mm (doit etre > 0)
    :return: Delta continu (float)
    :raises ValueError: si length_mm n'est pas strictement positif
    """
    if length_mm is None:
        raise ValueError("La longueur ne peut pas etre vide.")
    if length_mm <= 0:
        raise ValueError(f"La longueur doit etre strictement positive (recu {length_mm}).")

    delta = log_a * math.log(length_mm) + log_b

    for a_i, c_i, sigma_i in gaussian_params:
        delta += a_i * math.exp(-((length_mm - c_i) ** 2) / (2 * sigma_i ** 2))

    if not math.isfinite(delta):
        raise ValueError(f"Resultat non numerique/infini pour L={length_mm}.")

    return delta


def round_to_step(value, step=ROUNDING_STEP_MM):
    """
    Arrondit `value` au multiple de `step` le plus proche, avec un arrondi
    "half away from zero" (comportement Excel ROUND), pour garantir la
    coherence avec les calculs de reference Excel du metier.

    Exemples (step=5) : -17.8 -> -20 ; -12.1 -> -10 ; -7.4 -> -5 ; 3.2 -> 5.
    """
    if step <= 0:
        raise ValueError("Le pas d'arrondi doit etre strictement positif.")

    quotient = Decimal(str(value)) / Decimal(str(step))
    rounded_quotient = quotient.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(rounded_quotient) * step


def compute_new_length(old_length_mm, log_a=LOG_COEFF_A, log_b=LOG_COEFF_B,
                        gaussian_params=GAUSSIAN_PARAMS, rounding_step=ROUNDING_STEP_MM):
    """
    Calcule le triplet (delta_continu, delta_arrondi, new_length) pour une
    longueur donnee, conformement a l'algorithme du cahier des charges
    (section 10).
    """
    delta_continuous = predict_delta(old_length_mm, log_a, log_b, gaussian_params)
    delta_rounded = round_to_step(delta_continuous, rounding_step)
    new_length = old_length_mm + delta_rounded
    return delta_continuous, delta_rounded, new_length