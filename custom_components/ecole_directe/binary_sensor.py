# SPDX-License-Identifier: MIT

"""Capteurs oui/non pour les automatisations (ajout Kerherve)."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTRIBUTION, DOMAIN
from .entity_utils import planning

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .api.client import EDEleve
    from .coordinator import EDDataUpdateCoordinator
    from .data import EDConfigEntry

MINUTE = timedelta(minutes=1)

# clé -> (nom, icône, classe, module requis)
CAPTEURS: dict[str, tuple[str, str, BinarySensorDeviceClass | None, str]] = {
    "en_cours": ("En cours", "mdi:human-male-board", None, "EDT"),
    "ecole_aujourd_hui": ("École aujourd'hui", "mdi:school", None, "EDT"),
    "ecole_demain": ("École demain", "mdi:school-outline", None, "EDT"),
    "cours_annule_aujourd_hui": (
        "Cours annulé aujourd'hui",
        "mdi:calendar-remove",
        BinarySensorDeviceClass.PROBLEM,
        "EDT",
    ),
    "controle_demain": (
        "Contrôle prochain jour",
        "mdi:file-certificate-outline",
        None,
        "CAHIER_DE_TEXTES",
    ),
    "devoirs_non_faits_demain": (
        "Devoirs non faits prochain jour",
        "mdi:book-alert-outline",
        BinarySensorDeviceClass.PROBLEM,
        "CAHIER_DE_TEXTES",
    ),
}


class EDBinaire(CoordinatorEntity, BinarySensorEntity):
    """Capteur oui/non calculé à partir des données déjà chargées."""

    _attr_attribution = ATTRIBUTION
    _attr_has_entity_name = True

    def __init__(
        self, coordinator: EDDataUpdateCoordinator, eleve: EDEleve, cle: str
    ) -> None:
        super().__init__(coordinator)
        nom, icone, classe, _module = CAPTEURS[cle]
        self._cle = cle
        self._eleve_cle = eleve.get_fullname_lower()
        self._attr_name = nom
        self._attr_icon = icone
        self._attr_device_class = classe
        self._attr_unique_id = f"ed_{self._eleve_cle}_x_bin_{cle}"
        appareil = f"ED - {eleve.get_fullname()}"
        self._attr_device_info = DeviceInfo(
            name=appareil,
            entry_type=DeviceEntryType.SERVICE,
            identifiers={(DOMAIN, appareil)},
            manufacturer="Ecole Directe",
            model=appareil,
        )
        self._attributs: dict[str, Any] = {}

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()

        @callback
        def _tic(_maintenant: datetime) -> None:
            self.async_write_ha_state()

        self.async_on_remove(async_track_time_interval(self.hass, _tic, MINUTE))

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success and bool(self.coordinator.data)

    def _prochain_jour_ecole(self, liste: list[dict], aujourd_hui: Any) -> Any:
        """Prochain jour d'école, sinon le prochain jour de semaine."""
        jour = planning.prochain_jour(liste, aujourd_hui)
        if jour is not None:
            return jour
        jour = planning.lendemain(aujourd_hui)
        while jour.weekday() >= 5:  # samedi, dimanche
            jour = planning.lendemain(jour)
        return jour

    @property
    def is_on(self) -> bool:
        tz = self.coordinator.timezone
        maintenant = datetime.now(tz)
        aujourd_hui = maintenant.date()
        data = self.coordinator.data
        liste = planning.cours(data, self._eleve_cle, tz)
        self._attributs = {}

        if self._cle == "en_cours":
            actuel = planning.en_cours(liste, maintenant)
            self._attributs = planning.resume(actuel)
            return actuel is not None
        if self._cle == "ecole_aujourd_hui":
            debut, fin = planning.bornes(liste, aujourd_hui)
            if debut and fin:
                self._attributs = {"debut": debut.isoformat(), "fin": fin.isoformat()}
            return debut is not None
        if self._cle == "ecole_demain":
            debut, fin = planning.bornes(liste, planning.lendemain(aujourd_hui))
            if debut and fin:
                self._attributs = {"debut": debut.isoformat(), "fin": fin.isoformat()}
            return debut is not None
        if self._cle == "cours_annule_aujourd_hui":
            annules = [c for c in planning.du_jour(liste, aujourd_hui) if c["annule"]]
            self._attributs = {"cours": [planning.resume(c) for c in annules]}
            return bool(annules)

        devoirs = planning.devoirs(data, self._eleve_cle, tz)
        jour = self._prochain_jour_ecole(liste, aujourd_hui)
        du_jour = [d for d in devoirs if d["jour"] == jour]
        self._attributs = {"jour": jour.isoformat()}
        if self._cle == "controle_demain":
            controles = [d for d in du_jour if d["controle"]]
            self._attributs["matieres"] = [d["matiere"] for d in controles]
            return bool(controles)
        restants = [d for d in du_jour if not d["fait"]]
        self._attributs["matieres"] = [d["matiere"] for d in restants]
        return bool(restants)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return self._attributs


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001
    entry: EDConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Crée les capteurs oui/non de chaque enfant."""
    coordinator = entry.runtime_data.coordinator
    session = (coordinator.data or {}).get("session")
    if session is None or session.eleves is None:
        return
    async_add_entities(
        EDBinaire(coordinator, eleve, cle)
        for eleve in session.eleves
        for cle, (_nom, _icone, _classe, module) in CAPTEURS.items()
        if module in eleve.modules
    )
