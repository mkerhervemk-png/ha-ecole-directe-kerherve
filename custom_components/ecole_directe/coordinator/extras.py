# SPDX-License-Identifier: MIT

"""
Mise à jour des rubriques supplémentaires (ajout Kerherve).

Principes :
- une rubrique qui échoue n'empêche jamais les autres de se mettre à jour ;
- une rubrique refusée trois fois de suite n'est plus demandée jusqu'au
  prochain redémarrage (certaines écoles ne les activent pas) ;
- ces rubriques changent peu : elles ne sont relues qu'un cycle sur
  CYCLES_ENTRE_LECTURES, les autres cycles réutilisent la dernière valeur.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import ConfigEntryState

from ..api import extras as api_extras
from ..const import DOMAIN, LOGGER

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from ..api.client import EDApiClient, EDEleve
    from .base import EDDataUpdateCoordinator

CYCLES_ENTRE_LECTURES = 4
ECHECS_MAX = 3
MARQUEUR = "_x_"
CLE_COMPTE = "x_"
CLE_ELEVES = f"{DOMAIN}_eleves_attribues"

# rubrique -> (module École Directe requis ou None, événement émis ou None,
#              champs comparés pour détecter une nouveauté)
RUBRIQUES_ELEVE: dict[str, tuple[str | None, str | None, list[str]]] = {
    "timeline": (None, "new_timeline", ["date", "type", "titre", "contenu"]),
    "infos_etablissement": (None, "new_info_etablissement", ["id", "contenu"]),
    "carnet": ("CARNET_CORRESPONDANCE", "new_carnet", []),
    "manuels": ("MANUELS_SCOLAIRES", None, []),
    "qcms": ("QCM", None, []),
    "visios": (None, None, []),
    "menus": (None, "new_menu", ["id", "libelle"]),
    "vie_classe": ("VIE_DE_LA_CLASSE", None, []),
    "seances": ("CAHIER_DE_TEXTES", None, []),
}


def cle_eleve(eleve: EDEleve, rubrique: str) -> str:
    """Clé de stockage d'une rubrique pour un élève."""
    return f"{eleve.get_fullname_lower()}{MARQUEUR}{rubrique}"


def retirer_eleves_deja_suivis(
    coordinator: EDDataUpdateCoordinator, client: EDApiClient
) -> None:
    """
    Évite les doublons quand deux comptes liés listent les mêmes enfants.

    Le premier compte chargé garde l'enfant ; les autres comptes l'ignorent.
    """
    hass = coordinator.hass
    entree = coordinator.config_entry
    attribues: dict[str, str] = hass.data.setdefault(CLE_ELEVES, {})
    gardes = []
    for eleve in client.eleves or []:
        proprietaire = attribues.get(eleve.eleve_id)
        if proprietaire and proprietaire != entree.entry_id:
            autre = hass.config_entries.async_get_entry(proprietaire)
            actif = (
                autre is not None
                and autre.disabled_by is None
                and autre.state
                in (ConfigEntryState.LOADED, ConfigEntryState.SETUP_IN_PROGRESS)
            )
            if actif:
                LOGGER.info(
                    "%s est déjà suivi par le compte « %s » : ignoré ici",
                    eleve.get_fullname(),
                    autre.title,
                )
                continue
        attribues[eleve.eleve_id] = entree.entry_id
        gardes.append(eleve)
    client.eleves = gardes


def liberer_eleves(coordinator: EDDataUpdateCoordinator) -> None:
    """Rend les enfants disponibles quand le compte est déchargé."""
    attribues: dict[str, str] = coordinator.hass.data.get(CLE_ELEVES, {})
    for eleve_id in [
        e for e, p in attribues.items() if p == coordinator.config_entry.entry_id
    ]:
        attribues.pop(eleve_id, None)


def _etat(coordinator: EDDataUpdateCoordinator) -> dict[str, Any]:
    etat = getattr(coordinator, "_x_etat", None)
    if etat is None:
        etat = {"cycle": 0, "echecs": {}, "lecture": False}
        coordinator._x_etat = etat  # noqa: SLF001
    return etat


def debut_cycle(coordinator: EDDataUpdateCoordinator, previous_data: dict | None) -> None:
    """Décide si ce cycle relit les rubriques, sinon reprend les valeurs."""
    etat = _etat(coordinator)
    etat["lecture"] = etat["cycle"] % CYCLES_ENTRE_LECTURES == 0
    etat["cycle"] += 1
    etat["erreurs"] = {}
    if previous_data:
        for cle, valeur in previous_data.items():
            if MARQUEUR in cle or cle.startswith(CLE_COMPTE):
                coordinator.data.setdefault(cle, valeur)


async def _rubrique(
    coordinator: EDDataUpdateCoordinator,
    identifiant: str,
    cle: str,
    lecture: Callable[[], Awaitable[Any]],
) -> bool:
    """Lit une rubrique en isolant ses erreurs. Renvoie True si lue."""
    etat = _etat(coordinator)
    if etat["echecs"].get(identifiant, 0) >= ECHECS_MAX:
        return False
    try:
        coordinator.data[cle] = await lecture()
    except Exception as err:  # noqa: BLE001 - une rubrique ne doit rien casser
        etat["echecs"][identifiant] = etat["echecs"].get(identifiant, 0) + 1
        etat["erreurs"][identifiant] = str(err)[:200]
        LOGGER.debug("Rubrique %s indisponible : %s", identifiant, err)
        return False
    etat["echecs"].pop(identifiant, None)
    return True


async def maj_eleve(
    coordinator: EDDataUpdateCoordinator,
    client: EDApiClient,
    eleve: EDEleve,
    previous_data: dict | None,
) -> None:
    """Relit les rubriques supplémentaires d'un élève."""
    etat = _etat(coordinator)
    if not etat["lecture"]:
        return
    aujourd_hui = datetime.now(coordinator.timezone).strftime("%Y-%m-%d")
    lectures: dict[str, Callable[[], Awaitable[Any]]] = {
        "timeline": lambda: api_extras.timeline(client, eleve),
        "infos_etablissement": lambda: api_extras.infos_etablissement(client, eleve),
        "carnet": lambda: api_extras.carnet(client, eleve),
        "manuels": lambda: api_extras.manuels(client, eleve),
        "qcms": lambda: api_extras.qcms(client, eleve),
        "visios": lambda: api_extras.visios(client, eleve),
        "menus": lambda: api_extras.menus(client, eleve),
        "vie_classe": lambda: api_extras.vie_classe(client, eleve),
        "seances": lambda: api_extras.seances(client, eleve, aujourd_hui),
    }
    for rubrique, (module, evenement, champs) in RUBRIQUES_ELEVE.items():
        if module is not None and module not in eleve.modules:
            continue
        cle = cle_eleve(eleve, rubrique)
        lu = await _rubrique(
            coordinator, f"{eleve.eleve_id}:{rubrique}", cle, lectures[rubrique]
        )
        if lu and evenement and champs:
            coordinator.compare_data(previous_data, cle, champs, evenement, eleve)

    # Les documents sont lus une fois par compte puis répartis par enfant.
    tous = coordinator.data.get(f"{CLE_COMPTE}documents")
    if isinstance(tous, list):
        cle = cle_eleve(eleve, "documents")
        coordinator.data[cle] = [
            d for d in tous if d.get("id_eleve") in ("", "0", eleve.eleve_id)
        ]
        coordinator.compare_data(
            previous_data, cle, ["id", "libelle"], "new_document", eleve
        )


async def maj_compte(
    coordinator: EDDataUpdateCoordinator, client: EDApiClient
) -> None:
    """Relit les rubriques liées au compte (avant la boucle des élèves)."""
    etat = _etat(coordinator)
    if not etat["lecture"]:
        return
    await _rubrique(
        coordinator,
        "compte:documents",
        f"{CLE_COMPTE}documents",
        lambda: api_extras.documents(client),
    )
    await _rubrique(
        coordinator,
        "compte:sondages",
        f"{CLE_COMPTE}sondages",
        lambda: api_extras.sondages(client),
    )


def fin_cycle(coordinator: EDDataUpdateCoordinator) -> None:
    """Enregistre l'état de la dernière mise à jour."""
    etat = _etat(coordinator)
    coordinator.data[f"{CLE_COMPTE}derniere_maj"] = datetime.now(coordinator.timezone)
    if etat["lecture"]:
        coordinator.data[f"{CLE_COMPTE}erreurs"] = dict(etat["erreurs"])
        coordinator.data[f"{CLE_COMPTE}rubriques_coupees"] = sorted(
            r for r, n in etat["echecs"].items() if n >= ECHECS_MAX
        )
