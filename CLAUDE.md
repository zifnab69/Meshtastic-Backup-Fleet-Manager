# CLAUDE.md — Nodes Backup & Fleet Manager

> Mémo technique pour Claude. Référence obligatoire avant toute modification du code.

---

## Table des matières

1. [Objectif global](#1-objectif-global)
2. [Contexte technique](#2-contexte-technique)
3. [Structure du projet](#3-structure-du-projet)
4. [Workflow d'exécution](#4-workflow-dexécution)
5. [Architecture du code](#5-architecture-du-code)
6. [Conventions de code](#6-conventions-de-code)
7. [Contraintes spécifiques](#7-contraintes-spécifiques)
8. [Roadmap / TODO](#8-roadmap--todo)

---

## 1. Objectif global

Application desktop **Python/Tkinter** pour **sauvegarder, restaurer et déployer des configurations de nœuds Meshtastic** via USB, sous Windows uniquement.

**Public cible** : utilisateurs Meshtastic (radioamateurs, équipes de communication d'urgence) qui veulent gérer plusieurs nœuds ou déployer une config commune en flotte.

**Fonctionnalités principales** :
- Export complet de la config d'un nœud → fichier JSON (.NBFM)
- Restauration complète d'un fichier .NBFM → nœud
- Génération de profil flotte (suppression des clés uniques, conservation de l'admin_key et de la config LoRa/canaux)
- Export/import multi-nœuds séquentiels dans une même session
- Éditeur intégré : région LoRa, modem preset, noms de canaux, clés PSK, rôle appareil
- Générateur de clés PSK (AES-128 / AES-256)
- UI bilingue FR/EN commutable sans redémarrage
- Rapport HTML exportable de tous les fichiers NBFM
- Compilation en EXE autonome via PyInstaller

**Auteur** : zifnab69 — ZIFNAB69_fr@yahoo.fr  
**Licence** : CC BY-NC-SA 4.0

---

## 2. Contexte technique

| Paramètre | Valeur |
|---|---|
| Langage | Python 3.10+ |
| GUI | tkinter + ttk (stdlib) |
| Dépendances runtime | `meshtastic`, `pyserial`, `protobuf` (google.protobuf) |
| Dépendance build | `pyinstaller` |
| OS cible | Windows uniquement |
| Protocole | USB série (COM ports), Meshtastic Python API |
| Format de sauvegarde | JSON renommé `.NBFM` |

**Installation des dépendances** :
```bash
pip install meshtastic pyserial protobuf
```

---

## 3. Structure du projet

```
Nodes-Backup-Fleet-Manager/
├── NBFM_20260528_1135.py     ← script principal actif (~3100 lignes) [ex NBFMV1_78]
├── NBFM_20260527_1612.py     ← version précédente (référence)        [ex NBFMV1_77]
├── NBFM_20260520_1318.py     ← version ancienne (référence)          [ex NBFMV1.75]
├── README.md                 ← documentation bilingue FR/EN
├── CONTRIBUTING.md           ← guide de contribution
├── LICENCE                   ← CC BY-NC-SA 4.0
├── Images/                   ← screenshots pour le README
│   ├── CM_Firstpannel 1.77.jpg
│   ├── CM_vueprincipale 1.7.7.jpg
│   └── ...
├── ADC.jpg                   ← screenshots racine (legacy)
├── CM_Firstpannel.jpg
└── CM_vueprincipale1.jpg
```

> **Note sur les noms de fichiers** : les anciens scripts portaient un numéro de version
> (`NBFMV1_78`, `NBFMV1_77`, `NBFMV1.75`). La convention adoptée à partir de mai 2026
> est `NBFM_YYYYMMDD_HHMM.py`. Les fichiers sur disque peuvent encore avoir l'ancien nom ;
> tout nouveau fichier créé doit respecter la nouvelle convention.

**Fichiers générés à l'exécution** (jamais commités) :
- `NBFM_Config.json` — persistance langue (fr/en), dans le dossier du script/EXE
- `NBFM_notes.json` — notes personnelles par fichier NBFM, dans le dossier de travail
- `*.NBFM` — fichiers de sauvegarde (JSON), dans le dossier de travail choisi par l'utilisateur
- `NBFM_report_YYYYMMDD_HHMMSS.html` — rapports HTML

**Convention de nommage des fichiers NBFM exportés** :
```
meshtastic_[ShortName]_[YYYYMMDD]_[HHMMSS].NBFM
# Exemple : meshtastic_JMC_5F7B_20260509_095500.NBFM
```
Le `short_name` contient les 4 derniers hex de l'adresse MAC du nœud (`JMC_5F7B`).

---

## 4. Workflow d'exécution

### Lancer depuis le source
```bash
python NBFM_20260528_1135.py
```

### Compiler en EXE (PyInstaller)
```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name "NBFM" NBFM_20260528_1135.py
# EXE généré dans dist/NBFM.exe
```
Le code gère les deux modes via `get_app_dir()` : `sys.frozen` pour l'EXE, `__file__` pour le source.

### Convention de nommage des nouveaux scripts
**Toujours utiliser le format `YYYYMMDD_HHMM` à la place de toute numérotation de version.**
```
# Ancien : NBFMV1_78.py
# Nouveau : NBFM_20260528_1135.py
```

---

## 5. Architecture du code

### Organisation actuelle — fichier unique

Le script actif `NBFM_20260528_1135.py` contient tout le code (~3100 lignes).
Sections principales dans l'ordre :

| Lignes | Contenu |
|---|---|
| ~37–109 | Utilitaires, `_ToolTip`, `check_dependencies`, `get_app_dir`, `list_serial_ports` |
| ~115–135 | Connexion : `connect_device` |
| ~142–447 | Export : `proto_to_dict`, clés de sécurité, `export_full_config` |
| ~454–488 | Profil flotte : `build_fleet_profile` |
| ~495–697 | Import : `_apply_section_to_node`, `_apply_module_section`, `import_full_config` |
| ~709–733 | Validation : `validate_config_integrity` |
| ~740–834 | Mappings LoRa/modem : `LORA_REGIONS`, `MODEM_PRESETS`, helpers de conversion |
| ~837–937 | Lecture métadonnées : `read_file_meta` |
| ~943–983 | Persistance : `load_lang`, `save_lang`, `load_notes`, `save_notes` |
| ~989–1558 | Chaînes UI : `UI_STRINGS` (FR + EN), `tr()` |
| ~1566–3105 | Classe `NBFMApp` (UI Tkinter complète) |
| ~3111–3119 | Point d'entrée : `main()` |

### Découpage en modules — approche recommandée si le code grossit

Il n'y a pas d'obligation de rester en fichier unique. Si une nouvelle fonctionnalité
ou un refactor le justifie, découper en modules est bienvenu. Découpe naturelle suggérée :

```
nbfm/
├── __main__.py          ← point d'entrée (check_dependencies + mainloop)
├── core/
│   ├── connect.py       ← connect_device, list_serial_ports
│   ├── export.py        ← export_full_config, proto_to_dict, clés sécurité
│   ├── import_.py       ← import_full_config, _apply_section_to_node
│   ├── fleet.py         ← build_fleet_profile
│   └── validate.py      ← validate_config_integrity
├── ui/
│   ├── app.py           ← classe NBFMApp
│   ├── tooltip.py       ← _ToolTip
│   └── edit_popup.py    ← éditeur de champs clés (edit_config_fields)
└── data/
    ├── strings.py       ← UI_STRINGS, tr()
    ├── mappings.py      ← LORA_REGIONS, MODEM_PRESETS, DEVICE_ROLES
    └── persistence.py   ← load_lang, save_lang, load_notes, save_notes, read_file_meta
```

Si tu crées un module ou un nouveau fichier Python, nomme-le `NBFM_YYYYMMDD_HHMM.py`
ou place-le dans la structure ci-dessus selon son rôle.

### Fonctions et méthodes importantes à connaître

**Connexion / export**
- `connect_device(port)` — tente chaque port, timeout 8 s, vérifie `isConnected`
- `proto_to_dict(obj)` — convertit protobuf → dict Python (5 stratégies de fallback)
- `export_full_config(iface)` — exporte : my_info, metadata, owner (5 méthodes de fallback), local_config, module_config, channels, known_nodes

**Clés de sécurité**
- `_get_security_section()` — export des clés en base64
- `_apply_security_to_node()` — restaure admin_key via `del[:] + append()` (méthode CLI officielle Meshtastic)

**Import**
- `_apply_section_to_node()` — `Clear()` + `ParseDict()` sur le protobuf avant `writeConfig`
- `import_full_config(iface, config)` — owner, 8 sections local_config, 11 modules, canaux
- **Ordre critique des canaux** : secondaires (role=2) d'abord, primaire (role=1) en dernier → évite le reset firmware

**Profil flotte**
- `build_fleet_profile(config)` — supprime : my_info, metadata, owner, known_nodes, public_key, private_key, wifi_ssid, wifi_psk, compteurs version ; **conserve** admin_key

**UI**
- `_apply_lang()` — mise à jour inline de tous les textes sans reconstruire l'UI
- `refresh_files()` — recharge la liste, groupe par MAC (4 derniers hex du short_name), tri par mtime
- `export_config()` — export single node (thread daemon, `root.after()` pour les callbacks UI)
- `edit_config_fields()` — popup éditeur (owner, LoRa, rôle, 3 canaux + PSK, générateur de clés, nettoyage avancé)
- `export_report()` — génère un rapport HTML et l'ouvre dans le navigateur

---

## 6. Conventions de code

### Nommage des fichiers créés
- **Scripts Python** : `NBFM_YYYYMMDD_HHMM.py` — jamais de numéro de version `V1_XX`
- **Fichiers NBFM** : `meshtastic_[ShortName]_[YYYYMMDD]_[HHMMSS].NBFM`
- **Profil flotte** : `profil_flotte_[YYYYMMDD]_[HHMMSS].NBFM`
- **Rapport HTML** : `NBFM_report_[YYYYMMDD_HHMMSS].html`

### Gestion des erreurs
- Broad `try/except Exception` partout — priorité à la robustesse sur la précision
- Toujours un fallback (ex : `writeConfig` seul si `ParseDict` échoue)
- Messages d'erreur affichés via `messagebox.showerror` ou `set_status()`
- Jamais de crash silencieux : tout est loggué dans `log[]` ou dans `set_status()`

### Threading
- Les opérations bloquantes (connexion série, export, import) tournent dans des **threads daemon**
- Les mises à jour UI depuis un thread se font **exclusivement** via `root.after(0, callback)`
- Ne jamais appeler `set_status()` ou tout widget tkinter directement depuis un thread

### Protobuf
- `Clear()` avant `ParseDict()` — garantit l'écrasement total, pas de merge partiel
- `admin_key` : `del sec.admin_key[:] + append()` — méthode CLI officielle (pas ParseDict)
- `ignore_unknown_fields=True` dans ParseDict — compatibilité firmware
- PSK stockée en **hex** dans le JSON, convertie en **base64** dans l'UI et en **bytes** pour le protobuf

### Langue et UI
- `UI_STRINGS` est la **seule source de vérité** pour les textes UI — ne jamais hardcoder du texte en dehors
- `tr(key, **kwargs)` recharge la langue à chaque appel — pas de variable globale de langue
- Ajout d'une clé UI = l'ajouter dans **les deux** dictionnaires `"fr"` et `"en"`
- `_apply_lang()` met à jour **tous** les widgets sans détruire/recréer l'UI (sauf l'onglet Aide)

### Pas de tests automatisés
- Aucun framework de test (pytest, unittest)
- Validation manuelle sur matériel réel (T-Echo, ESP32 V3)

---

## 7. Contraintes spécifiques

| Contrainte | Détail |
|---|---|
| Windows uniquement | `os.startfile()`, COM ports style Windows |
| COM1 exclu | Port système Windows (BIOS/souris), jamais un appareil USB Meshtastic |
| Redémarrage obligatoire | Après toute restauration, l'appareil doit être redémarré manuellement |
| Ordre canaux critique | Secondaires (role=2) avant primaire (role=1) — sinon le firmware réinitialise le canal primaire |
| private_key non restaurée dans les profils flotte | Chaque nœud garde ses propres clés cryptographiques |
| Frozen/non-frozen | `get_app_dir()` doit être utilisé pour tout chemin relatif à l'app |
| Dossier de travail variable | L'utilisateur peut choisir n'importe quel dossier ; `work_dir` est une variable |
| Connexion série fragile | Timeout 8 s, fallback sur tous les ports si non spécifié, `iface.close()` dans `finally` |

---

## 8. Roadmap / TODO

### Priorité haute
- [ ] **Persistance du dossier de travail** dans `NBFM_Config.json` (perdu à chaque lancement)
- [ ] **Persistance du port COM** sélectionné dans `NBFM_Config.json`
- [ ] **Documenter la commande PyInstaller** dans le README (commande exacte + options `--icon`, `--add-data`)

### Priorité moyenne
- [ ] **Support YAML natif** : le glob inclut `*.yaml/*.yml` mais `import_full_config` ne gère que JSON
- [ ] **Rapport CSV** : format CSV en plus du HTML (plus facile à filtrer dans Excel)
- [ ] **Validation PSK** : avertir si la PSK saisie en Base64 n'a pas la bonne longueur (16 ou 32 octets)
- [ ] **Détection firmware** : afficher la version firmware dans la liste des fichiers (champ `metadata`)

### Priorité basse
- [ ] **Icône application** pour l'EXE PyInstaller
- [ ] **Tests basiques** : au moins un test sur `build_fleet_profile()` et `validate_config_integrity()`
- [ ] **Auto-détection port** plus fine : filtrer par VID/PID Silicon Labs (CP210x) ou CH340
- [ ] **Mode ligne de commande** : export/import sans GUI (pour automatisation)
- [ ] **Refactoring modulaire** : découper en packages `core/`, `ui/`, `data/` si le code dépasse ~4000 lignes
