# Correction Automatique des Longueurs UCS

**Projet de Fin d'Etudes (PFE)** — Automatisation du calcul et de l'ajustement des longueurs de fils et tubes (UCS) dans un dossier de cablage automobile, a partir d'un modele mathematique valide sur donnees reelles.

![Python](https://img.shields.io/badge/Python-3.10+-blue)
![Streamlit](https://img.shields.io/badge/Streamlit-App-red)
![License](https://img.shields.io/badge/statut-PFE-lightgrey)

---

## Sommaire

- [Contexte](#contexte)
- [Fonctionnalites](#fonctionnalites)
- [Modele mathematique](#modele-mathematique)
- [Architecture du projet](#architecture-du-projet)
- [Installation](#installation)
- [Utilisation](#utilisation)
- [Format attendu du fichier UCS](#format-attendu-du-fichier-ucs)
- [Tests](#tests)
- [Limites connues](#limites-connues)
- [Pistes d'amelioration](#pistes-damelioration)

---

## Contexte

Dans un dossier de cablage automobile, les longueurs de fils et de tubes definies en CAO doivent frequemment etre ajustees pour correspondre a la realite du process de fabrication (routage physique, tolerances, connectique). Cet ajustement etait realise manuellement, faisceau par faisceau — une operation chronophage et difficile a tracer.

Ce projet automatise ce calcul via un modele empirique (composante logarithmique + corrections gaussiennes), calibre sur des donnees reelles avant/apres correction, tout en garantissant que chaque decision reste **tracable, verifiable et modifiable par le metier**.

## Fonctionnalites

- **Import et detection automatique** des feuilles `Wires` / `Tubes` d'un fichier UCS (`.xlsx`), et de leurs colonnes `Name` / `Length`, quelle que soit leur position exacte dans le classeur.
- **Calcul automatique** de la variation de longueur (delta) via un modele mathematique versionne, puis arrondi au pas metier de 5 mm.
- **Validation des donnees** : longueurs manquantes, non numeriques, nulles ou negatives ; noms manquants ou en doublon — chaque ligne recoit un statut `OK` / `AVERTISSEMENT` / `ERREUR`.
- **Fichier source jamais modifie** : la correction est toujours ecrite dans une copie du classeur original.
- **Resume des modifications** : statistiques agregees (elements modifies, augmentes, diminues, ecart moyen) et detail trie par ampleur de changement.
- **Exports** :
  - UCS corrige (`.xlsx`)
  - Rapport de calcul / tableau de controle (`.xlsx` et `.csv`)
  - Demande d'ajustement (`.docx`)

## Modele mathematique
