"""Lot 2 : devoir_effectue choisit explicitement le compte et valide l'élève."""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ecole_directe.const import DOMAIN
from custom_components.ecole_directe.service_actions import async_setup_services

SERVICE = "devoir_effectue"


def _compte(hass, eleves=("111",), state=ConfigEntryState.LOADED, runtime=True, titre="Kerherve1"):
    client = SimpleNamespace(
        eleves=[SimpleNamespace(eleve_id=e, account_id_login=42) for e in eleves],
        switch_account=AsyncMock(),
        post_homework=AsyncMock(return_value=True),
    )

    @asynccontextmanager
    async def logged_in():
        yield client

    coordinator = SimpleNamespace(
        async_logged_in_client=logged_in, async_request_refresh=AsyncMock()
    )
    entry = MockConfigEntry(domain=DOMAIN, title=titre, state=state)
    entry.add_to_hass(hass)
    if runtime:
        entry.runtime_data = SimpleNamespace(coordinator=coordinator)
    return entry, client, coordinator


async def _appel(hass, **data):
    await async_setup_services(hass)
    await hass.services.async_call(DOMAIN, SERVICE, data, blocking=True)


async def test_un_compte_sans_config_entry_id_reste_accepte(hass):
    _, client, coord = _compte(hass)
    await _appel(hass, eleve_id=111, devoir_id=9)
    client.switch_account.assert_awaited_once_with(42)
    client.post_homework.assert_awaited_once_with(eleve_id=111, devoir_id=9, effectue=True)
    coord.async_request_refresh.assert_awaited_once()


async def test_plusieurs_comptes_sans_identifiant_refuse_sans_ecriture(hass):
    _, c1, _ = _compte(hass, titre="A")
    _, c2, _ = _compte(hass, titre="B")
    with pytest.raises(HomeAssistantError, match="config_entry_id"):
        await _appel(hass, eleve_id=111, devoir_id=9)
    c1.post_homework.assert_not_awaited()
    c2.post_homework.assert_not_awaited()


async def test_plusieurs_comptes_identifiant_valide_cible_le_bon_compte(hass):
    _, c1, _ = _compte(hass, titre="A")
    e2, c2, _ = _compte(hass, titre="B")
    await _appel(hass, eleve_id=111, devoir_id=9, config_entry_id=e2.entry_id)
    c1.post_homework.assert_not_awaited()
    c2.post_homework.assert_awaited_once()


async def test_entree_inconnue_refusee(hass):
    _, client, _ = _compte(hass)
    with pytest.raises(HomeAssistantError, match="inconnu"):
        await _appel(hass, eleve_id=111, devoir_id=9, config_entry_id="nexistepas")
    client.post_homework.assert_not_awaited()


async def test_entree_non_chargee_refusee(hass):
    _, client, _ = _compte(hass, state=ConfigEntryState.SETUP_RETRY)
    with pytest.raises(HomeAssistantError, match="non chargé"):
        await _appel(hass, eleve_id=111, devoir_id=9)
    client.post_homework.assert_not_awaited()


async def test_entree_sans_runtime_data_refusee(hass):
    _compte(hass, runtime=False)
    with pytest.raises(HomeAssistantError, match="non chargé"):
        await _appel(hass, eleve_id=111, devoir_id=9)


async def test_aucun_compte_refuse(hass):
    with pytest.raises(HomeAssistantError, match="Aucun compte"):
        await _appel(hass, eleve_id=111, devoir_id=9)


async def test_eleve_absent_aucune_ecriture(hass):
    _, client, coord = _compte(hass, eleves=("222",))
    with pytest.raises(HomeAssistantError, match="absent"):
        await _appel(hass, eleve_id=111, devoir_id=9)
    client.switch_account.assert_not_awaited()
    client.post_homework.assert_not_awaited()
    coord.async_request_refresh.assert_not_awaited()


async def test_decocher_un_devoir(hass):
    _, client, _ = _compte(hass)
    await _appel(hass, eleve_id=111, devoir_id=9, effectue=False)
    client.post_homework.assert_awaited_once_with(eleve_id=111, devoir_id=9, effectue=False)


async def test_refus_ecole_directe_remonte_une_erreur(hass):
    _, client, coord = _compte(hass)
    client.post_homework.return_value = False
    with pytest.raises(HomeAssistantError, match="refused"):
        await _appel(hass, eleve_id=111, devoir_id=9)
    coord.async_request_refresh.assert_not_awaited()
