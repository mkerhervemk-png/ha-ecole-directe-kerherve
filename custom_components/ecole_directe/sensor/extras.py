# SPDX-License-Identifier: MIT

"""Capteurs supplémentaires (ajout Kerherve)."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntityDescription,
)
from homeassistant.core import callback
from homeassistant.helpers.event import async_track_time_interval

from custom_components.ecole_directe.coordinator.extras import (
    CLE_COMPTE,
    MARQUEUR,
    cle_eleve,
)
from custom_components.ecole_directe.entity_utils import planning
from custom_components.ecole_directe.sensor.generic import (
    EDGenericSensor,
    is_too_big,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from custom_components.ecole_directe.api.client import EDEleve
    from custom_components.ecole_directe.coordinator import EDDataUpdateCoordinator
    from custom_components.ecole_directe.data import EDConfigEntry

MINUTE = timedelta(minutes=1)

# rubrique -> (nom affiché, icône, nom de l'attribut qui porte la liste)
RUBRIQUES: dict[str, tuple[str, str, str]] = {
    "timeline": ("Fil d'actualité", "mdi:timeline-text-outline", "evenements"),
    "infos_etablissement": ("Infos établissement", "mdi:bulletin-board", "infos"),
    "carnet": ("Carnet de correspondance", "mdi:notebook-outline", "mots"),
    "documents": ("Documents", "mdi:file-document-multiple-outline", "documents"),
    "manuels": ("Manuels numériques", "mdi:book-open-page-variant-outline", "manuels"),
    "qcms": ("QCM", "mdi:format-list-checks", "qcm"),
    "visios": ("Visios", "mdi:video-outline", "visios"),
    "menus": ("Menus cantine", "mdi:silverware-fork-knife", "menus"),
    "vie_classe": ("Vie de la classe", "mdi:account-group-outline", "elements"),
    "seances": ("Séances du jour", "mdi:school-outline", "seances"),
}


def _raccourcir(liste: list) -> list:
    """Garde les attributs sous la limite de taille de Home Assistant."""
    liste = list(liste)
    while liste and is_too_big(liste):
        liste = liste[: max(1, len(liste) // 2)] if len(liste) > 1 else []
    return liste


class EDRubriqueSensor(EDGenericSensor):
    """Nombre d'éléments d'une rubrique, avec la liste en attribut."""

    def __init__(
        self,
        coordinator: EDDataUpdateCoordinator,
        eleve: EDEleve,
        rubrique: str,
    ) -> None:
        nom, icone, self._attribut = RUBRIQUES[rubrique]
        super().__init__(
            coordinator,
            SensorEntityDescription(key=f"x_{rubrique}", icon=icone),
            cle_eleve(eleve, rubrique),
            nom,
            eleve,
            "len",
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        resultat = super().extra_state_attributes
        resultat[self._attribut] = _raccourcir(
            self.coordinator.data.get(self._key) or []
        )
        return resultat


class EDCalculSensor(EDGenericSensor):
    """Capteur calculé à partir de l'emploi du temps ou des devoirs."""

    _actualisation_minute = False

    def __init__(
        self,
        coordinator: EDDataUpdateCoordinator,
        eleve: EDEleve,
        cle: str,
        nom: str,
        icone: str,
        device_class: SensorDeviceClass | None = None,
    ) -> None:
        super().__init__(
            coordinator,
            SensorEntityDescription(
                key=f"x_{cle}", icon=icone, device_class=device_class
            ),
            f"{eleve.get_fullname_lower()}{MARQUEUR}calc_{cle}",
            nom,
            eleve,
        )
        self._eleve_cle = eleve.get_fullname_lower()

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if self._actualisation_minute:

            @callback
            def _tic(_maintenant: datetime) -> None:
                self.async_write_ha_state()

            self.async_on_remove(async_track_time_interval(self.hass, _tic, MINUTE))

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success and bool(self.coordinator.data)

    @property
    def _maintenant(self) -> datetime:
        return datetime.now(self.coordinator.timezone)

    @property
    def _cours(self) -> list[dict]:
        return planning.cours(
            self.coordinator.data, self._eleve_cle, self.coordinator.timezone
        )

    @property
    def _devoirs(self) -> list[dict]:
        return planning.devoirs(
            self.coordinator.data, self._eleve_cle, self.coordinator.timezone
        )


class EDCoursActuel(EDCalculSensor):
    """Matière du cours en train de se dérouler."""

    _actualisation_minute = True

    def __init__(self, coordinator: EDDataUpdateCoordinator, eleve: EDEleve) -> None:
        super().__init__(
            coordinator, eleve, "cours_actuel", "Cours actuel", "mdi:human-male-board"
        )

    @property
    def native_value(self) -> str:
        actuel = planning.en_cours(self._cours, self._maintenant)
        return actuel["matiere"] if actuel else "Aucun"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        resultat = super().extra_state_attributes
        resultat.update(
            planning.resume(planning.en_cours(self._cours, self._maintenant))
        )
        return resultat


class EDProchainCours(EDCalculSensor):
    """Prochain cours maintenu."""

    _actualisation_minute = True

    def __init__(self, coordinator: EDDataUpdateCoordinator, eleve: EDEleve) -> None:
        super().__init__(
            coordinator, eleve, "prochain_cours", "Prochain cours", "mdi:skip-next"
        )

    @property
    def native_value(self) -> str:
        suivant = planning.prochain(self._cours, self._maintenant)
        return suivant["matiere"] if suivant else "Aucun"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        resultat = super().extra_state_attributes
        resultat.update(
            planning.resume(planning.prochain(self._cours, self._maintenant))
        )
        return resultat


class EDHoraire(EDCalculSensor):
    """Heure de début ou de fin des cours, pour aujourd'hui ou le prochain jour."""

    def __init__(
        self,
        coordinator: EDDataUpdateCoordinator,
        eleve: EDEleve,
        cle: str,
        nom: str,
        icone: str,
        *,
        fin: bool,
        prochain_jour: bool,
    ) -> None:
        super().__init__(
            coordinator, eleve, cle, nom, icone, SensorDeviceClass.TIMESTAMP
        )
        self._fin = fin
        self._prochain_jour = prochain_jour
        self._actualisation_minute = True

    @property
    def native_value(self) -> datetime | None:
        liste = self._cours
        jour = self._maintenant.date()
        if self._prochain_jour:
            jour = planning.prochain_jour(liste, jour)
            if jour is None:
                return None
        debut, fin = planning.bornes(liste, jour)
        return fin if self._fin else debut


class EDCoursAnnules(EDCalculSensor):
    """Cours annulés aujourd'hui et le prochain jour d'école."""

    def __init__(self, coordinator: EDDataUpdateCoordinator, eleve: EDEleve) -> None:
        super().__init__(
            coordinator,
            eleve,
            "cours_annules",
            "Cours annulés à venir",
            "mdi:calendar-remove",
        )
        self._actualisation_minute = True

    def _annules(self) -> list[dict]:
        maintenant = self._maintenant
        limite = maintenant.date() + timedelta(days=7)
        return [
            c
            for c in self._cours
            if c["annule"] and c["fin"] > maintenant and c["debut"].date() <= limite
        ]

    @property
    def native_value(self) -> int:
        return len(self._annules())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        resultat = super().extra_state_attributes
        resultat["cours"] = [planning.resume(c) for c in self._annules()]
        return resultat


class EDDevoirsAFaire(EDCalculSensor):
    """Devoirs non faits dont l'échéance n'est pas passée."""

    def __init__(self, coordinator: EDDataUpdateCoordinator, eleve: EDEleve) -> None:
        super().__init__(
            coordinator,
            eleve,
            "devoirs_a_faire",
            "Devoirs à faire",
            "mdi:book-edit-outline",
        )

    def _restants(self) -> list[dict]:
        jour = self._maintenant.date()
        return [d for d in self._devoirs if not d["fait"] and d["jour"] >= jour]

    @property
    def native_value(self) -> int:
        return len(self._restants())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        resultat = super().extra_state_attributes
        resultat["devoirs"] = _raccourcir(
            [
                {
                    "pour_le": d["jour"].isoformat(),
                    "matiere": d["matiere"],
                    "description": d["description"],
                    "controle": d["controle"],
                }
                for d in self._restants()
            ]
        )
        return resultat


class EDProchainControle(EDCalculSensor):
    """Date du prochain contrôle annoncé dans le cahier de textes."""

    def __init__(self, coordinator: EDDataUpdateCoordinator, eleve: EDEleve) -> None:
        super().__init__(
            coordinator,
            eleve,
            "prochain_controle",
            "Prochain contrôle",
            "mdi:file-certificate-outline",
            SensorDeviceClass.DATE,
        )

    def _controles(self) -> list[dict]:
        jour = self._maintenant.date()
        return [d for d in self._devoirs if d["controle"] and d["jour"] >= jour]

    @property
    def native_value(self) -> Any:
        controles = self._controles()
        return controles[0]["jour"] if controles else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        resultat = super().extra_state_attributes
        controles = self._controles()
        if controles:
            resultat["matiere"] = controles[0]["matiere"]
            resultat["description"] = controles[0]["description"]
        resultat["controles"] = [
            {"pour_le": d["jour"].isoformat(), "matiere": d["matiere"]}
            for d in controles[:10]
        ]
        return resultat


class EDCompteSensor(EDGenericSensor):
    """Capteur rattaché au compte (pas à un enfant)."""

    def __init__(
        self,
        coordinator: EDDataUpdateCoordinator,
        cle: str,
        nom: str,
        icone: str,
        device_class: SensorDeviceClass | None = None,
        etat: str | None = None,
    ) -> None:
        super().__init__(
            coordinator,
            SensorEntityDescription(
                key=f"x_{cle}", icon=icone, device_class=device_class
            ),
            f"{CLE_COMPTE}{cle}",
            nom,
            None,
            etat,
        )


class EDSondages(EDCompteSensor):
    """Sondages ouverts."""

    def __init__(self, coordinator: EDDataUpdateCoordinator) -> None:
        super().__init__(coordinator, "sondages", "Sondages", "mdi:poll", etat="len")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"sondages": _raccourcir(self.coordinator.data.get(self._key) or [])}


class EDDerniereMaj(EDCompteSensor):
    """Heure de la dernière mise à jour réussie, avec les rubriques en erreur."""

    def __init__(self, coordinator: EDDataUpdateCoordinator) -> None:
        super().__init__(
            coordinator,
            "derniere_maj",
            "Dernière mise à jour",
            "mdi:cloud-check-outline",
            SensorDeviceClass.TIMESTAMP,
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data
        return {
            "erreurs": data.get(f"{CLE_COMPTE}erreurs") or {},
            "rubriques_coupees": data.get(f"{CLE_COMPTE}rubriques_coupees") or [],
        }


@callback
def async_setup_extras(
    hass: HomeAssistant,  # noqa: ARG001
    config_entry: EDConfigEntry,
    coordinator: EDDataUpdateCoordinator,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Crée les capteurs supplémentaires, y compris ceux qui apparaissent plus tard."""
    deja: set[str] = set()

    @callback
    def ajouter() -> None:
        data = coordinator.data or {}
        session = data.get("session")
        if session is None or session.eleves is None:
            return
        nouveaux: list = []

        def une_fois(identifiant: str, fabrique: Any) -> None:
            if identifiant not in deja:
                deja.add(identifiant)
                nouveaux.append(fabrique())

        if f"{CLE_COMPTE}derniere_maj" in data:
            une_fois("compte:maj", lambda: EDDerniereMaj(coordinator))
        if f"{CLE_COMPTE}sondages" in data:
            une_fois("compte:sondages", lambda: EDSondages(coordinator))

        for eleve in session.eleves:
            base = eleve.eleve_id
            if "EDT" in eleve.modules:
                une_fois(f"{base}:actuel", lambda e=eleve: EDCoursActuel(coordinator, e))
                une_fois(
                    f"{base}:prochain", lambda e=eleve: EDProchainCours(coordinator, e)
                )
                une_fois(
                    f"{base}:annules", lambda e=eleve: EDCoursAnnules(coordinator, e)
                )
                for cle, nom, icone, fin, prochain_jour in (
                    ("debut_cours", "Début des cours", "mdi:clock-start", False, False),
                    ("fin_cours", "Fin des cours", "mdi:clock-end", True, False),
                    (
                        "prochain_jour_debut",
                        "Prochain jour début",
                        "mdi:calendar-start",
                        False,
                        True,
                    ),
                    (
                        "prochain_jour_fin",
                        "Prochain jour fin",
                        "mdi:calendar-end",
                        True,
                        True,
                    ),
                ):
                    une_fois(
                        f"{base}:{cle}",
                        lambda e=eleve, c=cle, n=nom, i=icone, f=fin, p=prochain_jour: (
                            EDHoraire(coordinator, e, c, n, i, fin=f, prochain_jour=p)
                        ),
                    )
            if "CAHIER_DE_TEXTES" in eleve.modules:
                une_fois(
                    f"{base}:devoirs", lambda e=eleve: EDDevoirsAFaire(coordinator, e)
                )
                une_fois(
                    f"{base}:controle",
                    lambda e=eleve: EDProchainControle(coordinator, e),
                )
            for rubrique in RUBRIQUES:
                if cle_eleve(eleve, rubrique) in data:
                    une_fois(
                        f"{base}:{rubrique}",
                        lambda e=eleve, r=rubrique: EDRubriqueSensor(coordinator, e, r),
                    )
        if nouveaux:
            async_add_entities(nouveaux)

    ajouter()
    config_entry.async_on_unload(coordinator.async_add_listener(ajouter))
