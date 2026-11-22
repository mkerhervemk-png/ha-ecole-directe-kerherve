# École Directe — version Kerherve (1.3.0.2)

Base : intégration officielle hacf-fr/hass-ecoledirecte v1.3.0 (licence MIT),
connexion et capteurs d'origine inchangés. Ajouts ci-dessous.

## Pré-requis
Home Assistant 2026.10.2 ou plus récent (exigence de la version officielle 1.3.0).

## Installation (HACS)
1. Sauvegarde HA.
2. Dans HACS, retirer « Ecole Directe » officielle (même nom technique, les deux ne cohabitent pas).
   Ne PAS supprimer l'intégration dans Paramètres > Appareils et services.
3. HACS > menu ⋮ > Dépôts personnalisés : ajouter
   `https://github.com/mkerhervemk-png/ha-ecole-directe-kerherve`, type « Intégration ».
4. Installer « Ecole Directe (Kerherve) », puis redémarrer Home Assistant.
5. Paramètres > Appareils et services > Ecole Directe : reconnecter le compte si demandé,
   répondre à la question de sécurité (entités « select »), recharger.
6. Si les 3 enfants n'apparaissent pas avec un seul identifiant, « Ajouter une entrée »
   avec le second identifiant. Un enfant déjà suivi par un compte n'est jamais doublé.

## Ajouts par enfant
Emploi du temps (module EDT) : Cours actuel, Prochain cours, Début des cours, Fin des cours,
Prochain jour début, Prochain jour fin, Cours annulés à venir.
Oui/non : En cours, École aujourd'hui, École demain, Cours annulé aujourd'hui,
Contrôle prochain jour, Devoirs non faits prochain jour.
Devoirs : Devoirs à faire, Prochain contrôle.
Rubriques du site : Fil d'actualité, Infos établissement, Carnet de correspondance,
Documents, Manuels numériques, QCM, Visios, Menus cantine, Vie de la classe, Séances du jour.

## Ajouts par compte
Sondages, Dernière mise à jour (avec la liste des rubriques en erreur ou coupées).

## Nouveaux événements (`ecole_directe_event`)
`new_timeline`, `new_info_etablissement`, `new_document`, `new_menu`.

## Comportement
- Les rubriques du site sont relues un cycle sur 4 (toutes les 2 h avec le réglage par défaut).
- Une rubrique refusée 3 fois de suite n'est plus demandée jusqu'au redémarrage.
- Un capteur de rubrique n'est créé que si l'école fournit cette rubrique.
- Actions : `ecole_directe.reload_data` actualise tout de suite tous les comptes ;
  `ecole_directe.devoir_effectue` s'applique au compte qui contient l'élève indiqué.

## Fichiers ajoutés ou modifiés
Ajoutés : `api/extras.py`, `coordinator/extras.py`, `sensor/extras.py`,
`entity_utils/planning.py`, `binary_sensor.py`.
Modifiés (quelques lignes) : `coordinator/base.py`, `sensor/__init__.py`, `__init__.py`,
`const.py`, `manifest.json`, `service_actions/__init__.py`, traductions.

## Retour arrière
Retirer ce dépôt de HACS, réinstaller « Ecole Directe » officielle, redémarrer.
