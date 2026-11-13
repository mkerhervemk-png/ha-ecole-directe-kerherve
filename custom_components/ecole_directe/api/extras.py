# SPDX-License-Identifier: MIT

"""
Rubriques supplémentaires du site École Directe (ajout Kerherve).

Chaque fonction lit une rubrique du site que l'intégration d'origine ne
remonte pas : fil d'actualité, infos de l'établissement, carnet de
correspondance, documents, manuels, QCM, visios, menus, vie de la classe,
contenu des séances. Toutes sont en lecture seule.
"""

from __future__ import annotations

import base64
import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .client import EDApiClient, EDEleve

_BALISES = re.compile(r"<[^>]+>")
_ESPACES = re.compile(r"\s+")
TEXTE_MAX = 400
LISTE_MAX = 25


def texte(valeur: Any, limite: int = TEXTE_MAX) -> str:
    """Décode le base64 éventuel, retire le HTML et raccourcit."""
    if valeur is None:
        return ""
    brut = str(valeur)
    try:
        decode = base64.b64decode(brut, validate=True).decode("utf-8")
        # Un texte court en clair peut être du base64 valide par hasard :
        # on ne garde le décodage que s'il est lisible.
        if decode and decode.isprintable() or "<" in decode or "\n" in decode:
            brut = decode
    except (ValueError, UnicodeDecodeError):
        pass
    brut = _BALISES.sub(" ", brut)
    brut = (
        brut.replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&#39;", "'")
        .replace("&quot;", '"')
        .replace("&lt;", "<")
        .replace("&gt;", ">")
    )
    brut = _ESPACES.sub(" ", brut).strip()
    return brut if len(brut) <= limite else brut[: limite - 1] + "…"


async def _lire(
    client: EDApiClient,
    chemin: str,
    corps: str = "data={}",
    params: dict[str, Any] | None = None,
) -> Any:
    """Appelle une rubrique et renvoie son bloc « data »."""
    ed = client.ed_client
    requete: dict[str, Any] = {"verbe": "get", "v": ed.api_version}
    requete.update(params or {})
    # La bibliothèque n'expose pas d'appel générique public.
    reponse = await ed._EDClient__post(path=chemin, params=requete, payload=corps)  # noqa: SLF001
    return reponse.get("data") if isinstance(reponse, dict) else None


def _liste(valeur: Any) -> list:
    return valeur if isinstance(valeur, list) else []


async def timeline(client: EDApiClient, eleve: EDEleve) -> list[dict]:
    """Fil d'actualité de l'élève (notes, absences, documents, messages…)."""
    data = await _lire(client, f"/eleves/{eleve.eleve_id}/timeline.awp")
    return [
        {
            "date": item.get("date"),
            "type": item.get("typeElement"),
            "id": item.get("idElement"),
            "titre": texte(item.get("titre"), 120),
            "soustitre": texte(item.get("soustitre"), 120),
            "contenu": texte(item.get("contenu"), 200),
        }
        for item in _liste(data)[:LISTE_MAX]
        if isinstance(item, dict)
    ]


async def infos_etablissement(client: EDApiClient, eleve: EDEleve) -> list[dict]:
    """Post-its et événements affichés par l'établissement sur l'accueil."""
    data = await _lire(client, f"/E/{eleve.eleve_id}/timelineAccueilCommun.awp")
    if not isinstance(data, dict):
        return []
    resultat = []
    for postit in _liste(data.get("postits")):
        if not isinstance(postit, dict):
            continue
        auteur = postit.get("auteur") or {}
        resultat.append(
            {
                "id": postit.get("id"),
                "type": postit.get("type") or "info",
                "contenu": texte(postit.get("contenu")),
                "date_creation": postit.get("dateCreation"),
                "date_debut": postit.get("dateDebut"),
                "date_fin": postit.get("dateFin"),
                "auteur": " ".join(
                    str(auteur[c])
                    for c in ("civilite", "prenom", "nom")
                    if auteur.get(c)
                ),
            }
        )
    for evenement in _liste(data.get("evenements")):
        if not isinstance(evenement, dict):
            continue
        resultat.append(
            {
                "id": evenement.get("id"),
                "type": "evenement",
                "contenu": texte(
                    evenement.get("libelle")
                    or evenement.get("titre")
                    or evenement.get("contenu")
                ),
                "date_creation": evenement.get("dateCreation"),
                "date_debut": evenement.get("dateDebut") or evenement.get("date"),
                "date_fin": evenement.get("dateFin"),
                "auteur": "",
            }
        )
    return resultat[:LISTE_MAX]


def _resume(item: Any) -> dict:
    """Résumé prudent d'un élément dont la forme n'est pas documentée."""
    if not isinstance(item, dict):
        return {"contenu": texte(item)}
    resume: dict[str, Any] = {}
    for cle, valeur in item.items():
        if isinstance(valeur, (dict, list)):
            continue
        if isinstance(valeur, str):
            valeur = texte(valeur, 200)
        resume[cle] = valeur
        if len(resume) >= 12:
            break
    return resume


async def carnet(client: EDApiClient, eleve: EDEleve) -> list[dict]:
    """Carnet de correspondance : mots et suivis."""
    data = await _lire(
        client, f"/eleves/{eleve.eleve_id}/eleveCarnetCorrespondance.awp"
    )
    if not isinstance(data, dict):
        return []
    resultat = []
    for categorie in ("correspondances", "suivis"):
        for item in _liste(data.get(categorie)):
            ligne = _resume(item)
            ligne["categorie"] = categorie
            resultat.append(ligne)
    return resultat[:LISTE_MAX]


CATEGORIES_DOCUMENTS = (
    "factures",
    "notes",
    "viescolaire",
    "administratifs",
    "inscriptions",
)


async def documents(client: EDApiClient) -> list[dict]:
    """Documents à télécharger : bulletins, factures, certificats…"""
    chemin = (
        "/elevesDocuments.awp"
        if str(client.account_type) == "E"
        else "/familledocuments.awp"
    )
    data = await _lire(client, chemin, params={"archive": ""})
    if not isinstance(data, dict):
        return []
    resultat = []
    for categorie in CATEGORIES_DOCUMENTS:
        for doc in _liste(data.get(categorie)):
            if not isinstance(doc, dict):
                continue
            resultat.append(
                {
                    "id": doc.get("id"),
                    "libelle": texte(doc.get("libelle"), 160),
                    "date": doc.get("date"),
                    "categorie": categorie,
                    "type": doc.get("type"),
                    "id_eleve": str(doc.get("idEleve") or ""),
                    "signature_demandee": bool(doc.get("signatureDemandee")),
                }
            )
    resultat.sort(key=lambda d: str(d.get("date") or ""), reverse=True)
    return resultat


async def manuels(client: EDApiClient, eleve: EDEleve) -> list[dict]:
    """Manuels numériques de l'élève."""
    data = await _lire(client, f"/Eleves/{eleve.eleve_id}/manuelsNumeriques.awp")
    return [
        {
            "libelle": texte(item.get("libelle"), 160),
            "editeur": item.get("editeur"),
            "url": item.get("url"),
            "disciplines": item.get("disciplines") or [],
        }
        for item in _liste(data)[:LISTE_MAX]
        if isinstance(item, dict)
    ]


async def qcms(client: EDApiClient, eleve: EDEleve) -> list[dict]:
    """QCM proposés à l'élève."""
    data = await _lire(client, f"/eleves/{eleve.eleve_id}/qcms/0/associations.awp")
    return [_resume(item) for item in _liste(data)[:LISTE_MAX]]


async def visios(client: EDApiClient, eleve: EDEleve) -> list[dict]:
    """Classes virtuelles programmées."""
    data = await _lire(client, f"/E/{eleve.eleve_id}/visios.awp")
    return [_resume(item) for item in _liste(data)[:LISTE_MAX]]


async def menus(client: EDApiClient, eleve: EDEleve) -> list[dict]:
    """Menus de la cantine publiés par l'établissement."""
    reponse = await client.ed_client.get_menus(eleve.eleve_id)
    data = reponse.get("data") if isinstance(reponse, dict) else None
    resultat = []
    for semaine in _liste(data):
        if not isinstance(semaine, dict):
            continue
        for doc in _liste(semaine.get("doc")):
            if isinstance(doc, dict):
                resultat.append(
                    {
                        "semaine": semaine.get("semaine"),
                        "libelle": texte(doc.get("libelle"), 160),
                        "id": doc.get("id"),
                    }
                )
    return resultat[:LISTE_MAX]


async def vie_classe(client: EDApiClient, eleve: EDEleve) -> list[dict]:
    """Vie de la classe."""
    if not eleve.classe_id:
        return []
    data = await _lire(client, f"/Classes/{eleve.classe_id}/viedelaclasse.awp")
    if isinstance(data, list):
        return [_resume(item) for item in data[:LISTE_MAX]]
    if isinstance(data, dict):
        resultat = []
        for cle, valeur in data.items():
            if isinstance(valeur, list):
                for item in valeur:
                    ligne = _resume(item)
                    ligne["rubrique"] = cle
                    resultat.append(ligne)
            elif valeur not in (None, "", {}, []):
                resultat.append({"rubrique": cle, "contenu": texte(valeur)})
        return resultat[:LISTE_MAX]
    return []


async def seances(client: EDApiClient, eleve: EDEleve, jour: str) -> list[dict]:
    """Ce qui a été fait en classe un jour donné (contenu de séance)."""
    data = await client.get_homeworks_by_date(eleve, jour)
    resultat = []
    for matiere in _liste((data or {}).get("matieres")):
        if not isinstance(matiere, dict):
            continue
        seance = matiere.get("contenuDeSeance") or {}
        contenu = texte(seance.get("contenu")) if isinstance(seance, dict) else ""
        if not contenu:
            continue
        resultat.append(
            {
                "matiere": matiere.get("matiere"),
                "prof": matiere.get("nomProf"),
                "contenu": contenu,
                "documents": len(_liste(seance.get("documents"))),
            }
        )
    return resultat


async def sondages(client: EDApiClient) -> list[dict]:
    """Sondages ouverts sur le compte."""
    reponse = await client.ed_client.get_sondages()
    data = reponse.get("data") if isinstance(reponse, dict) else None
    return [_resume(item) for item in _liste(data)[:LISTE_MAX]]
