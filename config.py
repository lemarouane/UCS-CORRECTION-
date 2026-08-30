"""
Configuration du modele de correction des longueurs UCS.
Toutes les constantes du modele mathematique sont centralisees ici
pour permettre un remplacement facile dans une future version
(cf. cahier des charges, section 19 - Versionnement).
"""

MODEL_VERSION = "MODEL_V1"

# Composante logarithmique : a * ln(L) + b
LOG_COEFF_A = -13.045
LOG_COEFF_B = 80.57

# Corrections gaussiennes : liste de (ai, Ci, sigma_i)
GAUSSIAN_PARAMS = [
    (-0.85176136, 917.21091, 146.04),
    (4.66336484, 1335.07643, 133.548753),
    (1.07711073, 1819.32093, 141.674871),
    (-4.32883776, 2099.96541, 109.747574),
    (11.1882733, 2300.63359, 143.582982),
]

# Pas d'arrondi metier (mm)
ROUNDING_STEP_MM = 5

# Bornes de validite pour Old/Current Length (mm)
MIN_VALID_LENGTH_MM = 0.000001  # doit etre strictement positif
# Pas de borne max definie dans le cahier des charges (section 21 : a
# obtenir aupres du metier). Laisse a None tant que non fourni.
MAX_VALID_LENGTH_MM = None

# Feuilles UCS a traiter (contiennent Wire/Tube Name + Length)
SHEETS_TO_PROCESS = ["Wires", "Tubes"]

# Mots-cles (en minuscule) pour la detection automatique des colonnes
LENGTH_HEADER_KEYWORDS = ["length"]
NAME_HEADER_EXCLUDE_KEYWORDS = ["splice", "doubling"]
NAME_HEADER_INCLUDE_KEYWORDS = ["name"]

# Reference de performance du modele (cahier, section 18) - informatif uniquement
REFERENCE_MAE_MM = 7.97
REFERENCE_PCT_ERROR_LE_5MM = 47.89
REFERENCE_PCT_ERROR_LE_10MM = 78.87


GEMINI_MODEL = "gemini-flash-latest"

PROJECT_TITLE = "Correction automatique des longueurs UCS"
PROJECT_SUBTITLE = (
    "Automatisation du calcul et de l'ajustement des longueurs de fils et "
    "tubes (UCS) a partir d'un modele mathematique valide sur donnees reelles."
)
PROJECT_TYPE = "Projet de Fin d'Etudes (PFE)"
PROJECT_AUTHOR = "Ouiame Yachou"
PROJECT_INSTITUTION = "FST TANGER"
PROJECT_ACADEMIC_YEAR = "2025 / 2026"
PROJECT_SUPERVISOR_ACADEMIC = "OMAR AKKOURI"
PROJECT_SUPERVISOR_INDUSTRY = "MAHDI ZAITANE"