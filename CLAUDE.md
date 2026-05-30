# CLAUDE.md — Nodes Backup & Fleet Manager

> Mémo technique pour Claude. Référence obligatoire avant toute modification du code.

---

## Table des matières

- [**État du projet — mai 2026 (lire en premier)**](#état-du-projet--mai-2026-lire-en-premier)
1. [Objectif global](#1-objectif-global)
2. [Contexte technique](#2-contexte-technique)
3. [Structure du projet](#3-structure-du-projet)
4. [Workflow d'exécution](#4-workflow-dexécution)
5. [Format NBFM réel](#5-format-nbfm-réel--observations-sur-fichier-de-référence)
6. [Architecture du code](#6-architecture-du-code)
7. [Conventions de code](#7-conventions-de-code)
8. [Contraintes spécifiques](#8-contraintes-spécifiques)
9. [Notes API Meshtastic Python](#9-notes-api-meshtastic-python--faits-confirmés)
10. [Roadmap / TODO](#10-roadmap--todo)

---

## État du projet — 31 mai 2026 (lire en premier)

### ▶ POUR REPRENDRE LA PROCHAINE FOIS

- **Fichier de travail actif** : `NBFM_20260531_0001.py` (~3460 lignes, fichier unique). Compile OK. Fonctionnel sur matériel réel (T-Echo, Heltec V3).
- **État** : application stable. **Aucun bug bloquant.** Tous les bugs A, B, C, E–L sont corrigés et validés. **Seul Bug D reste ouvert** (basse priorité, neutralisé — voir §Bug D).
- **Avant toute modif** : appliquer le protocole de versioning (timestamp FR → copie dans `Backup/` → renommer en `NBFM_YYYYMMDD_HHMM.py` → modifier → `py_compile`).
- **Environnement critique** : **protobuf 7.34.1 / Python 3.14** (voir Pièges). Toujours tester en intégration avec un faux nœud + vrais protos `localonly_pb2`/`channel_pb2`.

### ★ Pistes d'évolution proposées (rappel demandé par l'utilisateur)

À proposer / faire quand l'utilisateur le souhaite (aucune urgente) :

| Piste | Priorité | Note |
|---|---|---|
| ✅ Validation longueur PSK dans l'éditeur | — | **FAIT (0001)** — bloque la sauvegarde si la clé Base64 ≠ 1/16/32 octets |
| Rapport CSV (en plus du HTML) | moyenne | Réutiliser la génération HTML existante |
| Firmware dans la bulle de survol | moyenne | Champ `metadata`, sans nouvelle colonne |
| Support YAML natif à l'import | moyenne | Le glob accepte déjà `*.yaml/*.yml` mais `import_full_config` ne lit que JSON |
| Doc PyInstaller dans le README | moyenne | Commande exacte + `--icon`, `--windowed` |
| Icône d'application pour l'EXE | basse | `--icon=nbfm.ico` |
| Auto-détection port par VID/PID (CP210x/CH340) | basse | Pré-sélection plus fine |
| Mode ligne de commande (sans GUI) | basse | Automatisation de flotte |
| Bug D — `statusmessage` inscriptible | basse | Voie alternative API à investiguer |

### Travaux récents (résumé)

- **Validation longueur PSK (0001)** : éditeur — `_validate_psk_b64()` dans `save_and_close` bloque la sauvegarde et avertit si une clé Base64 ne décode pas en 1/16/32 octets (avant : longueur non vérifiée → rejet silencieux du firmware).
- **Persistance langue + dossier (2348, Bugs A/B)** : `save_lang()` au démarrage dans `__init__` (crée `NBFM_Config.json` même en anglais) ; helpers `load_work_dir()`/`save_work_dir()`, lecture au démarrage, persistance dans `choose_work_dir()` + 3 chemins export. **Port COM non persisté.**
- **Barre de progression restauration (2332)** : `import_full_config(iface, config, progress=cb)` ; callback `progress(done,total,kind,detail)` ; UI `_open_progress(threaded=...)` + `_progress_label()` (mono-nœud=thread+`root.after` ; multi-nœuds=synchrone+`win.update()`).
- **Aide in-app FR+EN à jour** + **`RELEASE_NOTES.md`** (notes de version GitHub bilingues : fonctions absentes de la page des releases).
- **Bug L (PSK base64 vs hex) corrigé (2308, validé matériel réel)** : l'export stocke la PSK en base64 mais l'import la décodait en hex (`bytes.fromhex`) → clés perdues. Fix : `_psk_str_to_bytes()` tolère hex ET base64 (contrôle de longueur 1/16/32 o pour désambiguïser), utilisé dans les 2 chemins d'import canaux.

### Script actif

`NBFM_20260531_0001.py` (~3460 lignes, fichier unique).  
Backups les plus récents dans `Backup/` (du plus récent au plus ancien) : `NBFM_20260530_2348.py`, `2332.py`, `2308.py`, `1850.py`, `1823.py`, `1749.py`, `1402.py`.

### Pièges & leçons techniques durables (À LIRE avant de toucher export/import)
- **protobuf 7.x (upb)** : ne JAMAIS supposer l'API descriptor. Utiliser `field.is_repeated` (pas `.label`).
  MessageToDict : `always_print_fields_with_no_presence` + `use_integers_for_enums` impératifs.
- **`our_exit()` de la lib Meshtastic → `sys.exit()` → `SystemExit`** (hérite de BaseException). `except
  Exception` ne l'attrape PAS. Tout appel lib peut tuer le thread silencieusement.
- **Clé de session admin rotative** (firmware + admin_key/PKI) : encadrer les écritures par une transaction
  et espacer (0,5 s) pour laisser la clé se rafraîchir.
- **TOUJOURS tester en intégration** avec faux nœud + vrais protos `localonly_pb2`/`channel_pb2` sous le
  protobuf réellement installé. Les tests unitaires isolés masquent les régressions (cf. `re` non importé).
- **Auto-reboot** : le device redémarre seul à la fin du download. Le message « redémarrez l'appareil »
  est conservé volontairement (inoffensif, rassure l'utilisateur). Pas de changement.
- **Canal par défaut = nom VIDE** (vérifié dans la lib) : l'identité d'un canal = `generate_channel_hash(name, psk)`.
  Le primaire standard a `name=""` (l'app affiche le nom du preset, ex « LongFast ») et `psk=0x01`/`AQ==`
  (= clé par défaut, cf. `util.py:68 bytes([1])`). **Le nommer « default » changerait le hash → incompatibilité.**
  Donc `clear_channels` garde `name=""` : c'est correct, NE PAS mettre « default ».

### Ce que fait le logiciel — ce qui fonctionne

L'application est **fonctionnelle et utilisée sur matériel réel** (T-Echo, Heltec V3). Tout est ✅ fonctionnel :

- Export complet d'un nœud → fichier `.NBFM` (tous les champs + tous les modules, même inconnus)
- Restauration `.NBFM` → nœud (lora, canaux, owner, PSK, transaction admin) **avec barre de progression**
- Génération de profil flotte (épure les clés uniques, conserve `admin_key` + LoRa + canaux)
- Export / restauration multi-nœuds séquentiels
- Éditeur de champs clés : owner, région LoRa, modem, fréquence override, override_duty_cycle, rôle, canaux 0-2 (nom + PSK) — **avec validation de longueur PSK**
- Générateur de clés PSK (AES-128 / AES-256), « supprimer tous les canaux », nettoyage ADC / known_nodes
- Liste : groupement par MAC, tri, renommage (double-clic), menu contextuel, bulles de survol, notes par fichier
- Rapport HTML, validation d'intégrité avant restauration
- UI bilingue FR/EN à chaud, persistance langue + dossier de travail (`NBFM_Config.json`)
- Compilation EXE via PyInstaller

### Bugs — état

Tous les bugs historiques sont **résolus** : A, B (persistance langue/dossier), C (suppression known_nodes),
E (LoRa no-op / protobuf 7.x), F (bruit `statusmessage`), G (clé session admin / transaction), H/I (enums →
tableau + ordre canaux), J (PSK effaçable), K (noms canaux en double), L (PSK base64 vs hex). **Seul Bug D
reste ouvert** (basse priorité, neutralisé) :

#### Bug D — `statusmessage` non inscriptible (priorité basse — neutralisé, plus bloquant)
**État (mis à jour 30/05)** : le proto `moduleConfig.statusmessage` EXISTE désormais (protobuf récent), mais
`writeConfig` de la lib ne le gère pas → `our_exit()` → SystemExit. C'est attrapé (`_apply_module_section`)
et le `print` parasite est avalé (`_write_config_quiet`). Donc **plus de crash ni de bruit shell** ; le module
est simplement ignoré (ligne `⚠` dans le popup). Reste théoriquement non restaurable via l'API Python standard.
**À investiguer un jour** : voie alternative pour écrire `statusmessage` (peut-être un module interne non exposé).

### Règles non négociables pour toute modification

1. **Zéro régression** — tout changement préserve le comportement existant. En cas de doute, ajouter *à côté*, pas à la place.
2. **Import exhaustif** — jamais de liste blanche de modules/sections. Tout ce qui est dans le JSON doit être restauré.
3. **NBFM = backup/déploiement, pas configurateur** — le paramétrage source reste sur https://client.meshtastic.org.
4. **Nommage** — tout nouveau fichier Python : `NBFM_YYYYMMDD_HHMM.py`.

### Fichier de référence matériel disponible

`meshtastic_GB_A7F9_20260525_094518.nbfm` — export réel d'un T-Echo (EU868, 869.5 MHz, MediumSlow).  
Utiliser ce fichier pour valider tout développement sur le parsing/import/export.  
Contient : 2 canaux actifs (AES-256), 6 nœuds connus, modules `statusmessage` + `traffic_management` + `audio` + `remote_hardware`, `adc_multiplier_override: 2.0`.

---

## 1. Objectif global

Application desktop **Python/Tkinter** pour **sauvegarder, restaurer et déployer des configurations de nœuds Meshtastic** via USB, sous Windows uniquement.

**Public cible** : utilisateurs Meshtastic (radioamateurs, équipes de communication d'urgence) qui veulent gérer plusieurs nœuds ou déployer une config commune en flotte.

### Philosophie de conception — à garder en tête en permanence

Le paramétrage fin du matériel Meshtastic se fait via le client web officiel
(**https://client.meshtastic.org**), qui expose toutes les fonctionnalités à jour des firmwares.
**NBFM n'a pas vocation à remplacer ce site.**

Le rôle de NBFM est strictement :
1. **Sauvegarder** fidèlement 100 % de la configuration d'un nœud
2. **Restaurer** fidèlement 100 % de cette configuration, y compris les sections que l'UI n'expose pas
3. **Générer des profils flotte** (config commune déployable sur plusieurs nœuds)
4. **Modifier à la marge** quelques paramètres courants (région LoRa, canaux, owner, PSK…)

> **Conséquence directe pour le code** : l'export et l'import doivent traiter *tous* les champs
> et *tous* les modules présents dans le JSON — même les inconnus. Ne jamais ignorer
> silencieusement une section sous prétexte que l'UI ne l'expose pas.
> Un paramètre non géré par l'UI doit quand même être sauvegardé et restauré.

**Fonctionnalités principales** :
- Export complet de la config d'un nœud → fichier JSON (.NBFM)
- Restauration complète d'un fichier .NBFM → nœud (tous les champs, sans exception)
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
├── NBFM_20260531_0001.py     ← script principal actif (~3460 lignes) — voir « Script actif » pour le nom exact
├── Backup/                   ← versions horodatées précédentes (protocole de versioning)
├── RELEASE_NOTES.md          ← notes de version GitHub (bilingue)
├── README.md                 ← documentation bilingue FR/EN
├── CONTRIBUTING.md           ← guide de contribution
├── LICENCE                   ← CC BY-NC-SA 4.0
├── Images/                   ← screenshots pour le README
└── ...
```

> ⚠ Le nom du script actif change à chaque session (versioning horodaté). Se fier à la section
> « Script actif » en tête de ce fichier, pas au nom figé ci-dessus.

**Fichiers générés à l'exécution** (jamais commités) :
- `NBFM_Config.json` — persistance langue (fr/en) **et** dernier dossier de travail (`work_dir`), dans le dossier du script/EXE. Le port COM n'y est PAS stocké.
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

> Remplacer `NBFM_<actif>.py` par le nom du script actif (voir « Script actif »).

### Lancer depuis le source
```bash
python NBFM_<actif>.py
```

### Compiler en EXE (PyInstaller)
```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name "NBFM" NBFM_<actif>.py
# EXE généré dans dist/NBFM.exe
```
Le code gère les deux modes via `get_app_dir()` : `sys.frozen` pour l'EXE, `__file__` pour le source.

### Convention de nommage des nouveaux scripts
**Toujours utiliser le format `NBFM_YYYYMMDD_HHMM.py`** (jamais de numéro de version type `V1_78`).

---

## 5. Format NBFM réel — observations sur fichier de référence

> Fichier de référence : `meshtastic_GB_A7F9_20260525_094518.nbfm` (T-Echo, EU868, MediumSlow, 869.5 MHz)

### Structure JSON constatée sur matériel réel

| Champ | Valeur observée / notes |
|---|---|
| `_app_version` | `"2.2"` — évolue avec les versions du script (actuellement `"2.6"`) |
| `_export_date` | ISO 8601 avec microsecondes |
| `_profile_date` | Peut coexister avec `_export_date` sur des fichiers issus d'anciennes versions — ne pas supposer que sa présence signifie profil flotte (vérifier `_profile_type`) |
| `my_info.nodedb_count` | Nombre de nœuds connus au moment de l'export |
| `my_info.pio_env` | Environnement PlatformIO du firmware (ex : `"t-echo-inkhud"`) |
| `local_config.lora.override_frequency` | Float en MHz (ex : `869.5`) — prioritaire sur `frequency` pour l'affichage |
| `local_config.lora.override_duty_cycle` | `true` sur T-Echo France (contournement limite légale 1% duty cycle EU868) |
| `local_config.power.adc_multiplier_override` | `2.0` sur T-Echo — c'est ce que l'option "clear ADC" supprime |
| `local_config.device.tzdef` | Fuseau horaire POSIX (`"CET-1CEST,M3.5.0/2:00:00,M10.5.0/3:00:00"` pour la France) |
| `local_config.security.admin_key` | Liste de 3 entrées (2 clés base64 + 1 chaîne vide `""`) — forme normale sur T-Echo |
| `channels` | Liste de 8 objets (index 0–7), toujours présents même si désactivés (role=0, PSK="") |
| `channels[n].settings.psk` | Hex string 64 chars = 32 bytes = AES-256 ; 32 chars = AES-128 ; `""` = canal désactivé |
| `known_nodes` | Dict keyed par `!hex_node_id` (ex : `"!1666a7f9"`) — **pas une liste** |
| `known_nodes[id].user.publicKey` | Base64 — correspond aux valeurs de `security.admin_key` pour les nœuds de confiance |

### Modules présents dans ce fichier

Depuis la session 30/05/2026, `import_full_config` itère sur **tous** les modules présents dans le JSON (itération dynamique). Les modules `traffic_management`, `audio`, `remote_hardware` sont désormais restaurés. `statusmessage` est présent dans le fichier mais non exposé par l'API `writeConfig` — il est tenté silencieusement et ignoré si introuvable (voir Bug D).

### Extension de fichier
Le fichier de référence utilise l'extension `.nbfm` (minuscules). Le code recherche `*.NBFM` (majuscules). Sous Windows le filesystem est insensible à la casse — ça fonctionne. Sur Linux ce serait cassé. À garder en tête si portabilité Linux envisagée.

---

## 6. Architecture du code


### Organisation actuelle — fichier unique

Le script actif (voir « Script actif » pour le nom horodaté exact) contient tout le code (~3460 lignes).
Sections principales dans l'ordre (⚠ numéros de ligne **approximatifs** — ils dérivent à chaque édition ;
**se fier aux noms de fonctions, pas aux numéros**) :

| Lignes | Contenu |
|---|---|
| ~37–109 | Utilitaires, `_ToolTip`, `check_dependencies`, `get_app_dir`, `list_serial_ports` |
| ~115–135 | Connexion : `connect_device` |
| ~142–447 | Export : `proto_to_dict`, clés de sécurité, `export_full_config` |
| ~454–490 | Profil flotte : `build_fleet_profile` |
| ~495–510 | **`_coerce_repeated_fields()`** — normalise les champs repeated pour ParseDict |
| ~512–740 | Import : `_apply_section_to_node`, `_apply_module_section`, `import_full_config` |
| ~750–775 | Validation : `validate_config_integrity` |
| ~782–880 | Mappings LoRa/modem : `LORA_REGIONS`, `MODEM_PRESETS`, helpers de conversion |
| ~883–985 | Lecture métadonnées : `read_file_meta` |
| persistance | `load_lang`/`save_lang`, `load_work_dir`/`save_work_dir`, `load_notes`/`save_notes` |
| ~1036–1610 | Chaînes UI : `UI_STRINGS` (FR + EN), `tr()` |
| ~1618–3185 | Classe `NBFMApp` (UI Tkinter complète) |
| ~3190–3200 | Point d'entrée : `main()` |

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
- `_coerce_repeated_fields(section_data, proto_obj)` — convertit les scalaires en listes pour les champs `repeated` avant ParseDict (corrige `ignore_incoming: 0` → `[]`)
- `_apply_section_to_node()` — sauvegarde proto via CopyFrom, `Clear()` + `_coerce_repeated_fields()` + `ParseDict()` + `writeConfig` ; restauration en cas d'échec ParseDict
- `_apply_module_section()` — idem pour les modules
- `import_full_config(iface, config)` — owner, **toutes** les sections local_config (itération dynamique), **tous** les modules (itération dynamique), canaux
- **Ordre des canaux** : secondaires (role=2 ou 0) d'abord, primaire (role=1) en dernier — `writeChannel()` ne provoque PAS de reboot dans les firmwares actuels (confirmé source node.py), mais l'ordre est conservé pour compatibilité descendante

**Profil flotte**
- `build_fleet_profile(config)` — supprime : my_info, metadata, owner, known_nodes, public_key, private_key, wifi_ssid, wifi_psk, compteurs version ; **conserve** admin_key

**UI**
- `_apply_lang()` — mise à jour inline de tous les textes sans reconstruire l'UI
- `refresh_files()` — recharge la liste, groupe par MAC (4 derniers hex du short_name), tri par mtime
- `export_config()` — export single node (thread daemon, `root.after()` pour les callbacks UI)
- `edit_config_fields()` — popup éditeur (owner, LoRa, rôle, 3 canaux + PSK, générateur de clés, nettoyage avancé)
- `export_report()` — génère un rapport HTML et l'ouvre dans le navigateur

---

## 7. Conventions de code

### Nommage des fichiers créés
- **Scripts Python** : `NBFM_YYYYMMDD_HHMM.py` — jamais de numéro de version `V1_XX`
- **Fichiers NBFM** : `meshtastic_[ShortName]_[YYYYMMDD]_[HHMMSS].NBFM`
- **Profil flotte** : `profil_flotte_[YYYYMMDD]_[HHMMSS].NBFM`
- **Rapport HTML** : `NBFM_report_[YYYYMMDD_HHMMSS].html`

### Règle absolue — zéro régression
Avant toute modification d'une fonction existante :
1. Comprendre précisément ce qu'elle fait aujourd'hui
2. Identifier les cas limites et les fallbacks en place
3. S'assurer que le comportement résultant est identique ou strictement meilleur
4. Ajouter le nouveau comportement *en complément*, pas en remplacement, si le moindre doute subsiste
5. Ne jamais supprimer un fallback existant, même s'il semble inutile

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
- **Sauvegarder l'état proto avant `Clear()`** via `CopyFrom` — si ParseDict échoue, restaurer avant le fallback `writeConfig` (sinon l'appareil reçoit un proto à zéros)
- **`_coerce_repeated_fields()` obligatoire avant ParseDict** — les champs `repeated` peuvent être stockés en scalaire (`0`) dans d'anciens fichiers NBFM au lieu de liste (`[]`)
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

## 8. Contraintes spécifiques

| Contrainte | Détail |
|---|---|
| **Zéro régression** | Toute modification du code doit préserver le comportement existant. Avant de changer une fonction : identifier ce qu'elle fait, s'assurer que le résultat est identique ou strictement meilleur. En cas de doute, ajouter le nouveau comportement *à côté* de l'ancien, pas à la place. Les fallbacks existants ne doivent jamais être supprimés. |
| Client web officiel | Le paramétrage source se fait sur https://client.meshtastic.org — NBFM est un outil de backup/déploiement, pas un configurateur complet |
| Exhaustivité de l'import | Tous les modules et sections présents dans le JSON doivent être restaurés, y compris les inconnus. Ne jamais ignorer silencieusement un champ. |
| Windows uniquement | `os.startfile()`, COM ports style Windows |
| COM1 exclu | Port système Windows (BIOS/souris), jamais un appareil USB Meshtastic |
| Redémarrage obligatoire | Après toute restauration, l'appareil doit être redémarré manuellement |
| Ordre canaux | Secondaires (role=2 ou 0) avant primaire (role=1). `writeChannel()` ne provoque PAS de reboot dans les firmwares actuels (confirmé source `node.py` Meshtastic Python). L'ordre est conservé pour compatibilité descendante. |
| private_key non restaurée dans les profils flotte | Chaque nœud garde ses propres clés cryptographiques |
| Frozen/non-frozen | `get_app_dir()` doit être utilisé pour tout chemin relatif à l'app |
| Dossier de travail variable | L'utilisateur peut choisir n'importe quel dossier ; `work_dir` est une variable |
| Connexion série fragile | Timeout 8 s, fallback sur tous les ports si non spécifié, `iface.close()` dans `finally` |

---

## 9. Notes API Meshtastic Python — faits confirmés

> Issus de l'analyse du source `node.py` (github.com/meshtastic/python) lors de la session 30/05/2026.

| Point | Détail |
|---|---|
| `writeConfig(name)` — sections locales valides | `device`, `position`, `power`, `network`, `display`, `lora`, `bluetooth`, `security` |
| `writeConfig(name)` — modules valides | `mqtt`, `serial`, `external_notification`, `store_forward`, `range_test`, `telemetry`, `canned_message`, `audio`, `remote_hardware`, `neighbor_info`, `detection_sensor`, `ambient_lighting`, `paxcounter`, `traffic_management` |
| `writeChannel(index)` | N'entraîne **pas** de reboot dans les firmwares actuels |
| `setOwner(long_name, short_name)` | Tronque `short_name` à **4 caractères** automatiquement (message d'avertissement dans le terminal — comportement normal, pas un bug NBFM) |
| `beginSettingsTransaction()` / `commitSettingsTransaction()` | Existent dans l'API. Utiles pour les nœuds distants (mesh). Non utilisés actuellement pour les connexions USB directes. |
| `statusmessage` | Présent dans les fichiers NBFM du T-Echo mais **absent** de la liste writeConfig officielle. Non accessible via `moduleConfig.statusmessage`. Peut-être un module interne non exposé par l'API Python. |

---

## 10. Roadmap / TODO

> Tous les bugs (A, B, C, E–L) + la barre de progression + la validation PSK sont **faits** — voir
> « Travaux récents » en tête. Ci-dessous, uniquement les pistes ouvertes (aucune urgente). La liste
> priorisée pour rappel utilisateur est dans « ★ Pistes d'évolution proposées » en tête de fichier.

### Priorité moyenne
- [ ] **Rapport CSV** : format CSV en plus du HTML (plus facile à filtrer dans Excel)
- [ ] **Support YAML natif** : le glob inclut `*.yaml/*.yml` mais `import_full_config` ne gère que JSON
- [ ] **Firmware dans la bulle de survol** : afficher la version firmware (`metadata`) — pas de colonne supplémentaire
- [ ] **Documenter la commande PyInstaller** dans le README (commande exacte + `--icon`, `--windowed`)

### Priorité basse
- [ ] **Icône application** pour l'EXE PyInstaller
- [ ] **Tests basiques** : au moins un test sur `build_fleet_profile()` et `validate_config_integrity()`
- [ ] **Auto-détection port** plus fine : filtrer par VID/PID Silicon Labs (CP210x) ou CH340
- [ ] **Mode ligne de commande** : export/import sans GUI (pour automatisation)
- [ ] **Refactoring modulaire** : découper en packages `core/`, `ui/`, `data/` si le code dépasse ~4000 lignes
- [ ] **Bug D — `statusmessage`** : vérifier si ce module est accessible autrement dans l'API Meshtastic Python
