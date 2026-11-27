# Copyright (c) 2024-2026
# SPDX-License-Identifier: MIT

"""Service actions package for ecole_directe."""

from __future__ import annotations

from typing import TYPE_CHECKING

import probatio as vol
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import ServiceCall, SupportsResponse, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv

from custom_components.ecole_directe.const import (
    DOMAIN,
    LOGGER,
)
from custom_components.ecole_directe.service_actions.service import (
    async_handle_devoir_effectue,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from custom_components.ecole_directe.data import EDConfigEntry

# Service action names - only used within service_actions module
SERVICE_DEVOIR_EFFECTUE = "devoir_effectue"


def _choisir_entree(hass: HomeAssistant, entry_id: str | None) -> EDConfigEntry:
    """Choisit explicitement le compte ciblé ; aucune écriture si le choix est ambigu."""
    entries = hass.config_entries.async_entries(DOMAIN)
    if not entries:
        msg = "Aucun compte École Directe configuré"
        raise HomeAssistantError(msg)
    if entry_id is None:
        if len(entries) > 1:
            msg = "Plusieurs comptes configurés : préciser config_entry_id"
            raise HomeAssistantError(msg)
        entry = entries[0]
    else:
        entry = hass.config_entries.async_get_entry(entry_id)
        if entry is None or entry.domain != DOMAIN:
            msg = f"Compte École Directe inconnu : {entry_id}"
            raise HomeAssistantError(msg)
    if entry.state is not ConfigEntryState.LOADED or getattr(entry, "runtime_data", None) is None:
        msg = "Compte École Directe non chargé"
        raise HomeAssistantError(msg)
    return entry


async def async_setup_services(hass: HomeAssistant) -> None:
    """
    Register services for the integration.

    Services are registered at component level (in async_setup) rather than
    per config entry. This is a Silver Quality Scale requirement and ensures:
    - Service validation works correctly
    - Services are available even without config entries
    - Helpful error messages are provided

    Service handlers iterate over all config entries to find the relevant one.
    """

    @callback
    async def handle_devoir_effectue(call: ServiceCall) -> None:
        """Handle the service action call."""
        entry = _choisir_entree(hass, call.data.get("config_entry_id"))
        await async_handle_devoir_effectue(hass, entry, call)

    # Register services (only once at component level)
    if not hass.services.has_service(DOMAIN, SERVICE_DEVOIR_EFFECTUE):
        hass.services.async_register(
            domain=DOMAIN,
            service=SERVICE_DEVOIR_EFFECTUE,
            service_func=handle_devoir_effectue,
            schema=vol.Schema(
                {
                    vol.Required("eleve_id"): vol.Coerce(int),
                    vol.Required("devoir_id"): vol.Coerce(int),
                    vol.Optional("effectue", default=True): cv.boolean,
                    vol.Optional("config_entry_id"): cv.string,
                }
            ),
            supports_response=SupportsResponse.NONE,
        )

    LOGGER.debug("Services registered for %s", DOMAIN)
