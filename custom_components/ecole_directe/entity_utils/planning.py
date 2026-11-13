# SPDX-License-Identifier: MIT

"""Calculs sur l'emploi du temps et les devoirs (ajout Kerherve)."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from datetime import tzinfo

SEMAINES = ("_timetable_1", "_timetable_2", "_timetable_3")


def _local(valeur: Any, tz: tzinfo) -> datetime | None:
    """Les heures École Directe sont locales et sans fuseau."""
    if not isinstance(valeur, datetime):
        return None
    if valeur.tzinfo is None:
        return valeur.replace(tzinfo=tz)
    return valeur.astimezone(tz)


def cours(data: dict | None, eleve_cle: str, tz: tzinfo) -> list[dict]:
    """Tous les cours connus de l'élève, triés, avec heures localisées."""
    if not data:
        return []
    vus: set = set()
    resultat = []
    for suffixe in SEMAINES:
        for lecon in data.get(f"{eleve_cle}{suffixe}") or []:
            debut = _local(lecon.get("start"), tz)
            fin = _local(lecon.get("end"), tz)
            if debut is None or fin is None:
                continue
            identifiant = (lecon.get("id"), debut)
            if identifiant in vus:
                continue
            vus.add(identifiant)
            resultat.append(
                {
                    "debut": debut,
                    "fin": fin,
                    "matiere": lecon.get("lesson") or "",
                    "salle": lecon.get("salle") or "",
                    "prof": lecon.get("prof") or "",
                    "annule": bool(lecon.get("is_annule")),
                    "modifie": bool(lecon.get("is_modifie")),
                    "dispense": bool(lecon.get("dispense")),
                }
            )
    resultat.sort(key=lambda c: c["debut"])
    return resultat


def maintenus(liste: list[dict]) -> list[dict]:
    """Cours qui ont réellement lieu."""
    return [c for c in liste if not c["annule"]]


def du_jour(liste: list[dict], jour: date) -> list[dict]:
    return [c for c in liste if c["debut"].date() == jour]


def en_cours(liste: list[dict], maintenant: datetime) -> dict | None:
    for c in maintenus(liste):
        if c["debut"] <= maintenant < c["fin"]:
            return c
    return None


def prochain(liste: list[dict], maintenant: datetime) -> dict | None:
    for c in maintenus(liste):
        if c["debut"] > maintenant:
            return c
    return None


def bornes(liste: list[dict], jour: date) -> tuple[datetime | None, datetime | None]:
    """Début du premier cours et fin du dernier cours maintenus d'un jour."""
    jour_cours = du_jour(maintenus(liste), jour)
    if not jour_cours:
        return None, None
    return jour_cours[0]["debut"], max(c["fin"] for c in jour_cours)


def prochain_jour(liste: list[dict], apres: date) -> date | None:
    """Premier jour d'école strictement après la date donnée."""
    for c in maintenus(liste):
        if c["debut"].date() > apres:
            return c["debut"].date()
    return None


def resume(c: dict | None) -> dict[str, Any]:
    if c is None:
        return {}
    return {
        "debut": c["debut"].isoformat(),
        "fin": c["fin"].isoformat(),
        "matiere": c["matiere"],
        "salle": c["salle"],
        "prof": c["prof"],
        "modifie": c["modifie"],
    }


def devoirs(data: dict | None, eleve_cle: str, tz: tzinfo) -> list[dict]:
    """Devoirs connus de l'élève avec leur date d'échéance."""
    resultat = []
    for devoir in (data or {}).get(f"{eleve_cle}_homeworks") or []:
        echeance = devoir.get("date")
        if isinstance(echeance, datetime):
            jour = (_local(echeance, tz) or echeance).date()
        elif isinstance(echeance, date):
            jour = echeance
        else:
            continue
        resultat.append(
            {
                "jour": jour,
                "matiere": devoir.get("matiere") or "",
                "description": devoir.get("short_description") or "",
                "fait": bool(devoir.get("effectue")),
                "controle": bool(devoir.get("interrogation")),
            }
        )
    resultat.sort(key=lambda d: d["jour"])
    return resultat


def lendemain(jour: date) -> date:
    return jour + timedelta(days=1)
