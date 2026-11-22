# Copyright (c) 2024-2026
# SPDX-License-Identifier: MIT

"""Service actions package for ecole_directe."""

from __future__ import annotations

from typing import TYPE_CHECKING

import probatio as vol
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import ServiceCall, SupportsResponse
from homeassistant.exceptions import ServiceValidationError
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

# Service action names - only used within service_actions module
SERVICE_DEVOIR_EFFECTUE = "devoir_effectue"
SERVICE_RELOAD_DATA = "reload_data"


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

    def _loaded_entries() -> list:
        entries = [
            entry
            for entry in hass.config_entries.async_entries(DOMAIN)
            if entry.state is ConfigEntryState.LOADED
        ]
        if not entries:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="no_loaded_entry"
            )
        return entries

    async def handle_devoir_effectue(call: ServiceCall) -> None:
        """Handle the service action call."""
        # Pick the account that owns this pupil (several accounts can be set up).
        entries = _loaded_entries()
        eleve_id = str(call.data["eleve_id"])
        entry = next(
            (
                e
                for e in entries
                if any(
                    str(getattr(eleve, "eleve_id", "")) == eleve_id
                    for eleve in getattr(
                        (e.runtime_data.coordinator.data or {}).get("session"),
                        "eleves",
                        [],
                    )
                    or []
                )
            ),
            entries[0],
        )
        await async_handle_devoir_effectue(hass, entry, call)

    async def handle_reload_data(call: ServiceCall) -> None:
        """Refresh every loaded account now."""
        for entry in _loaded_entries():
            await entry.runtime_data.coordinator.async_request_refresh()

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
                }
            ),
            supports_response=SupportsResponse.NONE,
        )

    if not hass.services.has_service(DOMAIN, SERVICE_RELOAD_DATA):
        hass.services.async_register(
            domain=DOMAIN,
            service=SERVICE_RELOAD_DATA,
            service_func=handle_reload_data,
            schema=vol.Schema({}),
            supports_response=SupportsResponse.NONE,
        )

    LOGGER.debug("Services registered for %s", DOMAIN)
