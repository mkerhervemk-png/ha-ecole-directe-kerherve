"""Préparation des tests : charge uniquement le module des services.

Le paquet complet dépend de bibliothèques externes (ecoledirecte, probatio)
non nécessaires ici. On enregistre un paquet vide à la place de
custom_components.ecole_directe, et probatio est remplacé par voluptuous,
dont il reprend l'API (Schema, Required, Optional, Coerce).
"""

import pathlib
import sys
import types

import pytest
import voluptuous

RACINE = pathlib.Path(__file__).resolve().parents[1]
sys.modules.setdefault("probatio", voluptuous)
for nom, chemin in [
    ("custom_components", RACINE / "custom_components"),
    ("custom_components.ecole_directe", RACINE / "custom_components" / "ecole_directe"),
]:
    if nom not in sys.modules:
        mod = types.ModuleType(nom)
        mod.__path__ = [str(chemin)]
        sys.modules[nom] = mod


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield
