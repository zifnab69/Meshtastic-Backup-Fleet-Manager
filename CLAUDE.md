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
9. [Roadmap / TODO](#9-roadmap--todo)

---

## État du projet — 30 mai 2026 (lire en premier)

### ▶ POUR REPRENDRE LA PROCHAINE FOIS

- **Fichier de travail actif** : `NBFM_20260530_1850.py`. Compile OK. Fonctionnel sur matériel réel.
- **Dernier état** : restauration vérifiée OK (lora appliqué, canaux dans le bon ordre, owner correct, modifs prises en compte). Tableau de la liste complet (modèle/rôle/région/modem). Plus de message d'erreur bloquant.
- **PROCHAINE ACTION prévue** : implémenter la **barre de progression de la restauration** (voir Roadmap §10, priorité haute — piste d'implémentation détaillée).
- **Avant toute modif** : appliquer le protocole de versioning (timestamp FR → copie dans `Backup/` → renommer en `NBFM_YYYYMMDD_HHMM.py` → modifier → `py_compile`).
- **Environnement critique à ne pas oublier** : **protobuf 7.34.1 / Python 3.14** (voir pièges ci-dessous). Toujours tester en intégration avec un faux nœud + vrais protos `localonly_pb2`/`channel_pb2`.

### Script actif

`NBFM_20260530_1850.py` (~3310 lignes, fichier unique).  
Backups (les plus récents) : `Backup/NBFM_20260530_1823.py`, `1754.py`, `1749.py`, `1703.py`, `1621.py`, `1402.py`.  
Versions de référence antérieures : `NBFM_20260528_1135.py`, `NBFM_20260527_1612.py`, `NBFM_20260520_1318.py`.

### Session 30/05/2026 — résumé (lire en premier)

> Longue session de debug autour d'un symptôme : « la restauration ne change rien sur l'appareil ».
> Plusieurs fausses pistes avant la vraie cause racine. Résumé condensé ci-dessous ; détails par bug
> dans la section « Bugs ouverts/résolus ».

**La cause racine (Bug E réel)** : l'environnement tourne sous **protobuf 7.34.1 / Python 3.14**, qui a
supprimé/renommé deux API utilisées par NBFM :
1. `MessageToDict(including_default_value_fields=True)` → renommé `always_print_fields_with_no_presence`.
   L'ancien levait `TypeError` → `proto_to_dict` tombait dans un fallback qui sérialisait les champs
   `repeated` via `str()` → `lora.ignore_incoming = '[]'` (chaîne au lieu de liste).
2. `FieldDescriptor.label` → supprimé en upb (AttributeError). `_coerce_repeated_fields` l'utilisait →
   no-op silencieux → le `'[]'` n'était jamais réparé.
   
   Combinés : `ParseDict` échouait sur toute la section `lora` → fallback → **modifs LoRa perdues en silence**.

**Fix racine (1749/1823)** : `proto_to_dict` (~L.159) appelle MessageToDict avec
`always_print_fields_with_no_presence=True` **et** `use_integers_for_enums=True` (enums en int, pas en
noms — sinon casse le tableau et la restauration des canaux, cf. H/I). Helpers de tolérance :
`_field_is_repeated()` (is_repeated/label), `_coerce_repeated_fields()` (`'[]'`→`[]`),
`_channel_role_to_int()` ("PRIMARY"→1), `_enum_short_label()` (read_file_meta tolère int OU nom).

**Ce qui a été corrigé cette session** (tous vérifiés par tests d'intégration avec faux nœud + vrais protos) :

| Bug | Sujet | Fix |
|---|---|---|
| **E** | LoRa no-op (cause racine protobuf 7.x) | proto_to_dict + coerce + `use_integers_for_enums` |
| **F** | `Error: No valid config with name statusmessage` (shell) | `_write_config_quiet()` redirige stdout (~L.574) |
| **G** | Restauration no-op via clé de session admin périmée | transaction `begin/commitSettingsTransaction` + `time.sleep(0.5)` après chaque écriture (~L.724). **NB : G n'était PAS le vrai symptôme utilisateur (c'était E), mais c'est une vraie amélioration alignée sur le CLI officiel — conservée.** |
| **H** | Tableau : modèle/rôle/région/modem = « ? » | `use_integers_for_enums` + `_enum_short_label()` |
| **I** | Décalage des canaux + canal 0 fantôme `AQ==` | `use_integers_for_enums` + `_channel_role_to_int()` |
| **J** | Éditeur : PSK non effaçable | champ vide → `psk=""` (~L.3245) |
| **K** | Validation noms de canaux identiques | refus de sauvegarde si doublon |
| — | `SystemExit` (our_exit) tuait le thread d'import | `except SystemExit` dans `_apply_section/module` |
| — | `short_name` pollué par suffixe MAC → corrompu à l'import | découplage : MAC dérivée de `my_info.my_node_num` |
| — | `re` non importé (régression interne) → owner non restauré | `re` remonté au niveau module (~L.31) |
| — | override_duty_cycle (demande) | case à cocher dans l'éditeur (~L.3061) |

**Pièges/leçons retenus** :
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

### Ce que fait le logiciel en l'état actuel — ce qui fonctionne

L'application est **fonctionnelle et utilisée sur matériel réel** (T-Echo, Heltec V3).

| Fonctionnalité | État |
|---|---|
| Export complet d'un nœud → fichier .NBFM | ✅ Fonctionnel |
| Restauration .NBFM → nœud | ✅ Fonctionnel (corrigé en profondeur le 30/05 — lora, canaux, owner, transaction) |
| Case override_duty_cycle dans l'éditeur | ✅ Ajouté session 30/05 |
| Génération profil flotte | ✅ Fonctionnel |
| Éditeur champs clés (owner, LoRa, canaux, PSK, rôle) | ✅ Fonctionnel |
| "Supprimer tous les canaux" dans l'éditeur | ✅ Corrigé session 30/05 |
| Import exhaustif local_config + modules | ✅ Corrigé session 30/05 |
| Export/import multi-nœuds séquentiels | ✅ Fonctionnel |
| Groupement par MAC dans la liste des fichiers | ✅ Fonctionnel |
| Tooltip au survol (nom long, région, canal, nœuds connus) | ✅ Fonctionnel |
| UI bilingue FR/EN commutable sans redémarrage | ✅ Fonctionnel |
| Rapport HTML exportable | ✅ Fonctionnel |
| Validation d'intégrité avant restauration | ✅ Fonctionnel |
| Générateur de clés PSK (AES-128 / AES-256) | ✅ Fonctionnel |
| Compilation EXE via PyInstaller | ✅ Fonctionnel |

### Corrections apportées — session 30/05/2026

Toutes les corrections ci-dessous sont dans `NBFM_20260530_1402.py`.

| Correction | Localisation | Détail |
|---|---|---|
| `_apply_section_to_node` : Clear()+fallback dangereux | ~L.530 | Sauvegarde proto avant Clear() via CopyFrom ; restauration si ParseDict échoue. Avant : le fallback écrivait un proto à zéros sur l'appareil (role=0, tzdef="", etc.) |
| `_apply_module_section` : même bug | ~L.590 | Même correction + ImportError séparé du except général |
| `_coerce_repeated_fields()` | ~L.495 | Nouvelle fonction. Convertit les valeurs scalaires (`0`) en liste vide (`[]`) pour les champs `repeated` protobuf avant ParseDict. Corrige l'erreur "lora fallback, parsedict échoué: repeated field ignore_incoming must be in []" |
| Import exhaustif local_config (ex-Bug 2) | ~L.633 | Itération dynamique sur `local_cfg.items()` au lieu d'une liste fixe de 8 sections |
| Import exhaustif modules (ex-Bug 1) | ~L.643 | Itération dynamique sur `module_cfg.items()` ; couvre désormais `audio`, `remote_hardware`, `traffic_management` et tout futur module firmware |
| `clear_channels` : canaux 1–7 non effacés | ~L.3077 | Génère maintenant 8 entrées : canaux 1–7 avec role=0 (DISABLED) + canal 0 avec role=1, name="", psk="01" |
| `clear_channels` : ancien nom conservé | ~L.3077 | name="" → l'appareil utilise son nom par défaut ("LongFast") |
| `clear_channels` : "role":"PRIMARY" (string) | ~L.3077 | Remplacé par `"role": 1` (int) |
| `_modem_labels()` : retournait repr(tuple) | ~L.814 | Labels formatés comme `_modem_label_from_int` |
| `_role/region/modem_label_from_int` : pas de gestion string enum | ~L.820–860 | Fallback sur comparaison de nom string (ex: "ROUTER") pour compatibilité protobuf futur |

### Bugs ouverts et leur emplacement précis dans le code

> Les bugs E, F, G, H, I, J, K (session 30/05) sont **résolus** — voir le tableau « Session 30/05 — résumé ».
> Restent ouverts les 4 bugs d'origine ci-dessous (A, B, C, D).

#### Bug A — NBFM_Config.json non créé en anglais (priorité haute)
**Fichier** : `NBFM_20260530_1402.py`, lignes ~1000–1020 (`save_lang`) et ~1630 (`NBFMApp.__init__`)  
**Problème** : `save_lang()` n'est appelé que quand l'utilisateur change de langue via les boutons FR/EN. Si l'utilisateur reste en anglais (langue par défaut), le fichier n'est jamais créé, empêchant toute persistance future de préférences.  
**Correction** : appeler `save_lang(self.lang_var.get())` dans `NBFMApp.__init__()` au démarrage, inconditionnellement.

#### Bug B — Dossier de travail non persisté (priorité haute)
**Fichier** : `NBFM_20260530_1402.py`, ligne ~1630 (`self.work_dir = APP_DIR`)  
**Problème** : à chaque lancement, `work_dir` est réinitialisé au dossier du script. L'utilisateur doit resélectionner son dossier de sauvegarde à chaque fois.  
**Correction** : lire `work_dir` depuis `NBFM_Config.json` au démarrage, sauvegarder à chaque changement via `choose_work_dir()`.

#### Bug C — Suppression des known_nodes non fonctionnelle sur l'appareil (priorité haute)
**Fichier** : `NBFM_20260530_1402.py`, popup `edit_config_fields`, option `clear_known_nodes_var`  
**Problème signalé** : cocher "supprimer les nœuds connus" dans l'éditeur supprime la clé du fichier JSON mais **ne nettoie pas la base de nœuds sur l'appareil** lors du push. La fonction `import_full_config` n'a aucun code pour effacer les known_nodes sur le device.  
**Piste de correction** : l'API Meshtastic Python expose probablement une méthode pour supprimer des nœuds individuellement ou vider la node DB. À rechercher dans `meshtastic.node` / `iface.nodesByNum`. Probablement via `iface.localNode.remove_position_from_node_db()` ou en itérant `iface.nodes` et appelant `local_node.removeNode()` pour chaque entrée présente dans le fichier mais désirée supprimée.

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
├── NBFM_20260530_1402.py     ← script principal actif (~3200 lignes)
├── NBFM_20260528_1135.py     ← version précédente (référence)
├── NBFM_20260527_1612.py     ← version ancienne (référence)
├── NBFM_20260520_1318.py     ← version ancienne (référence)
├── Backup/
│   └── NBFMV1_78.py          ← backup avant renommage (30/05/2026)
├── README.md                 ← documentation bilingue FR/EN
├── CONTRIBUTING.md           ← guide de contribution
├── LICENCE                   ← CC BY-NC-SA 4.0
├── Images/                   ← screenshots pour le README
└── ...
```

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
python NBFM_20260530_1402.py
```

### Compiler en EXE (PyInstaller)
```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name "NBFM" NBFM_20260530_1402.py
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

Le script actif `NBFM_20260530_1850.py` contient tout le code (~3310 lignes).
Sections principales dans l'ordre (⚠ numéros de ligne **approximatifs** — ils dérivent à chaque édition ;
se fier aux noms de fonctions, pas aux numéros) :

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
| ~990–1030 | Persistance : `load_lang`, `save_lang`, `load_notes`, `save_notes` |
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

### Priorité haute — PROCHAINE ACTION
- [ ] **Barre de progression pour la restauration** (demandé 30/05). `import_full_config` fait ~33 écritures
  espacées de 0,5 s (≈15-20 s). Ajouter une progressbar (ttk.Progressbar) alimentée depuis le thread d'import
  via `root.after()`. Idée : `import_full_config` accepte un callback `progress(done, total, label)` appelé après
  chaque section/module/canal ; l'UI met à jour la barre. Total = owner + nb sections + nb modules + nb canaux + commit.
- [ ] **Bug C — Suppression known_nodes sur l'appareil** : `clear_known_nodes_var` supprime la clé du JSON mais ne nettoie pas la node DB sur l'appareil lors du push. Rechercher la méthode Meshtastic Python pour effacer les nœuds connus (probablement via `iface.nodes` + appel de suppression individuel).
- [ ] **Bug A — `NBFM_Config.json` créé quelle que soit la langue** : appeler `save_lang(self.lang_var.get())` dans `NBFMApp.__init__()` au démarrage, inconditionnellement. Le port COM **ne doit pas** être persisté.
- [ ] **Bug B — Persistance du dossier de travail** dans `NBFM_Config.json` (perdu à chaque lancement). Lire au démarrage, sauvegarder à chaque `choose_work_dir()`.
- [ ] **Documenter la commande PyInstaller** dans le README (commande exacte + options `--icon`, `--add-data`)

### Priorité moyenne
- [ ] **Support YAML natif** : le glob inclut `*.yaml/*.yml` mais `import_full_config` ne gère que JSON
- [ ] **Rapport CSV** : format CSV en plus du HTML (plus facile à filtrer dans Excel)
- [ ] **Validation PSK** : avertir si la PSK saisie en Base64 n'a pas la bonne longueur (16 ou 32 octets)
- [ ] **Firmware dans la bulle de survol** : afficher la version firmware (champ `metadata`) dans le tooltip — pas de colonne supplémentaire dans le Treeview.

### Priorité basse
- [ ] **Icône application** pour l'EXE PyInstaller
- [ ] **Tests basiques** : au moins un test sur `build_fleet_profile()` et `validate_config_integrity()`
- [ ] **Auto-détection port** plus fine : filtrer par VID/PID Silicon Labs (CP210x) ou CH340
- [ ] **Mode ligne de commande** : export/import sans GUI (pour automatisation)
- [ ] **Refactoring modulaire** : découper en packages `core/`, `ui/`, `data/` si le code dépasse ~4000 lignes
- [ ] **Bug D — `statusmessage`** : vérifier si ce module est accessible autrement dans l'API Meshtastic Python
