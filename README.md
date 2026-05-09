> 🇫🇷 **French below — Version française plus bas**

---

# Meshtastic Config Manager

A Python/Tkinter desktop application to **backup, restore and deploy Meshtastic node configurations** over USB on Windows.

![Python](https://img.shields.io/badge/Python-3.10+-blue)
![License](https://img.shields.io/badge/License-CC%20BY--NC--SA%204.0-lightgrey)
![Platform](https://img.shields.io/badge/Platform-Windows-blue)
![Meshtastic](https://img.shields.io/badge/Meshtastic-2.x-green)

---

## Features

- **Full config export** — reads the complete node configuration and saves it as a structured JSON file (owner, LoRa, channels + PSK, Bluetooth, network, modules, security keys…)
- **Full config restore** — writes back every section to the node, including AES-256 channel PSKs, admin keys and security keys
- **Fleet profile generation** — strips device-unique data (private/public keys, owner, WiFi credentials) and keeps the shared config (admin_key, LoRa, channels, modules…) for multi-node deployment
- **Sequential multi-node export** — export multiple nodes one after another in the same session
- **Sequential multi-node import** — deploy the same JSON file to multiple nodes in one session
- **Key fields editor** — edit region, modem preset, owner name and channel names directly in the UI without touching the JSON
- **Integrity validation** — automatic pre-restore checks with warnings
- **Standalone EXE** — compiled with PyInstaller, no Python installation required

---

## Screenshots

![alt](https://github.com/zifnab69/Meshtastic-Configuration-Manager/blob/main/CM_Firstpannel.jpg)
---

## Requirements

### Running from source

```
Python 3.10+
meshtastic
pyserial
protobuf
```

```bash
pip install meshtastic pyserial protobuf
python meshtastic_config_manager_v1.2_EN.py
```

### Running the standalone EXE

No installation needed. Download the EXE from the [Releases](../../releases) page and run it directly.

---

## Quick start

1. Connect your Meshtastic device via USB
2. Launch the application
3. Select the COM port (COM1 is automatically excluded — Windows system port)
4. Click **EXPORT FULL CONFIG → JSON** to save your configuration
5. To restore, select a JSON file in the list and click **RESTORE selected file → Device**
6. Restart the device to apply changes

---

## Fleet deployment workflow

1. Export a reference node to JSON
2. Click **GENERATE FLEET PROFILE** — this removes unique keys and owner info
3. Select the generated `*_fleet.json` file
4. Click **Multi-node import** and restore to each node in sequence

---

## JSON structure

| Section | Description |
|---|---|
| `owner` | long_name, short_name, hw_model |
| `local_config` | LoRa, Bluetooth, network, display, position, power, device, security |
| `module_config` | MQTT, serial, telemetry, canned messages, range test, … |
| `channels` | Channels 0–7 with PSK (AES-256), name, role, module_settings |
| `known_nodes` | List of known mesh nodes |
| `my_info` | Raw local node info |
| `metadata` | Firmware metadata |

---

## File naming

```
meshtastic_[short_name]_[YYYYMMDD]_[HHMMSS].json
```

Example: `meshtastic_JMC_5F7B_20260509_095500.json`

The short_name includes the last 4 hex characters of the node's MAC address for unique identification.

---

## Channel restore order

Channels are restored in this specific order to prevent the firmware from resetting the primary channel:

1. Secondary channels (role = 2) first
2. Primary channel (role = 1) last

---
## Disclamer
I’m not a software developer by training. This tool was built with the help of an AI and a lot of work on my side to design, test, and refine it. If you’re a developer and would like to contribute, any help to keep this project alive and evolving is greatly appreciated.
## License

[Creative Commons Attribution – NonCommercial – ShareAlike 4.0 International](https://creativecommons.org/licenses/by-nc-sa/4.0/)

---

## Author

**zifnab69** — ZIFNAB69_fr@yahoo.fr


---

## Changelog

### v1.2 (May 2026)
- Help tab added to the UI
- Export: device is read before the save dialog opens
- Automatic filename with short_name + 4 hex MAC suffix
- Multi-node export with per-node port selection, COM1 excluded
- Multi-node import uses the file selected in the UI
- COM1 automatically excluded from all port lists
- Auto port detection on startup
- Full PSK restore for all channels (bug fix)
- Channel restore order: secondary first, primary last
- module_settings restored (position_precision, is_muted)
- Full security key restore (private_key included)
- Fleet profile strips both public_key and private_key (admin_key kept)
- hw_model converted from protobuf enum to readable name
- short_name appended with last 4 hex of MAC address

### v1.0
- Initial release

---
---

# 🇫🇷 Version française

# Meshtastic Config Manager

Application Python/Tkinter pour **sauvegarder, restaurer et déployer les configurations de nœuds Meshtastic** via USB sous Windows.

![Python](https://img.shields.io/badge/Python-3.10+-blue)
![Licence](https://img.shields.io/badge/Licence-CC%20BY--NC--SA%204.0-lightgrey)
![Plateforme](https://img.shields.io/badge/Plateforme-Windows-blue)
![Meshtastic](https://img.shields.io/badge/Meshtastic-2.x-green)

---

## Fonctionnalités

- **Export complet de la configuration** — lit toute la config du nœud et la sauvegarde en JSON (owner, LoRa, canaux + PSK, Bluetooth, réseau, modules, clés de sécurité…)
- **Restauration complète** — réécrit chaque section vers le nœud, y compris les PSK AES-256, les admin_key et les clés de sécurité
- **Génération de profils flotte** — supprime les données uniques (clés privées/publiques, owner, WiFi) et conserve la config partagée (admin_key, LoRa, canaux, modules…) pour déploiement multi-nœuds
- **Export multi-nœuds séquentiel** — exporter plusieurs nœuds l'un après l'autre dans la même session
- **Import multi-nœuds séquentiel** — déployer le même fichier JSON sur plusieurs nœuds en une session
- **Éditeur de champs clés** — modifier région, modem preset, nom owner et noms des canaux directement dans l'interface
- **Validation d'intégrité** — vérifications automatiques avant chaque restauration
- **EXE autonome** — compilé avec PyInstaller, aucune installation Python requise

---

## Captures d'écran

![alt](https://github.com/zifnab69/Meshtastic-Configuration-Manager/blob/main/CM_vueprincipale1.jpg)


---

## Prérequis

### Depuis le source Python

```
Python 3.10+
meshtastic
pyserial
protobuf
```

```bash
pip install meshtastic pyserial protobuf
python meshtastic_config_manager_v1.1.py
```

### Depuis l'EXE autonome

Aucune installation requise. Télécharger l'EXE depuis la page [Releases](../../releases) et le lancer directement.

---

## Démarrage rapide

1. Brancher l'appareil Meshtastic via USB
2. Lancer l'application
3. Sélectionner le port COM (COM1 exclu automatiquement — port système Windows)
4. Cliquer **EXPORTER CONFIG COMPLÈTE → JSON** pour sauvegarder la configuration
5. Pour restaurer, sélectionner un fichier JSON dans la liste et cliquer **RESTAURER le fichier sélectionné → Appareil**
6. Redémarrer l'appareil pour appliquer les changements

---

## Déploiement en flotte

1. Exporter un nœud de référence en JSON
2. Cliquer **GÉNÉRER PROFIL FLOTTE** — les clés uniques et les infos owner sont supprimées
3. Sélectionner le fichier `*_fleet.json` généré
4. Cliquer **Import multi-nœuds** et restaurer sur chaque nœud à la suite

---

## Structure du fichier JSON

| Section | Description |
|---|---|
| `owner` | long_name, short_name, hw_model |
| `local_config` | LoRa, Bluetooth, réseau, display, position, power, device, security |
| `module_config` | MQTT, série, télémétrie, messages prédéfinis, range test, … |
| `channels` | Canaux 0–7 avec PSK (AES-256), nom, rôle, module_settings |
| `known_nodes` | Liste des nœuds mesh connus |
| `my_info` | Informations brutes du nœud local |
| `metadata` | Métadonnées firmware |

---

## Nommage automatique des fichiers

```
meshtastic_[short_name]_[YYYYMMDD]_[HHMMSS].json
```

Exemple : `meshtastic_JMC_5F7B_20260509_095500.json`

---

## Ordre de restauration des canaux

1. Canaux secondaires (role = 2) en premier
2. Canal primaire (role = 1) en dernier

---

## Licence

[Creative Commons Attribution – Pas d'Utilisation Commerciale – Partage dans les Mêmes Conditions 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/deed.fr)

---

## Auteur

**zifnab69** — ZIFNAB69_fr@yahoo.fr

## Information
Je ne suis absolument pas développeur de formation. Ce logiciel a été conçu avec l’aide d’une IA et beaucoup d’efforts de ma part pour le penser, le tester et l’améliorer. Si vous êtes développeur et que vous souhaitez contribuer, toute aide sera la bienvenue pour faire vivre et progresser ce projet.

---

## Changelog

### v1.2 (mai 2026)
- Ajout de l'onglet Aide dans l'interface
- Export : lecture de l'appareil avant la boîte de sauvegarde
- Nommage automatique avec short_name + 4 hex MAC
- Export multi-nœuds avec sélection de port par nœud, COM1 exclu
- Import multi-nœuds : utilise le fichier sélectionné dans l'UI
- COM1 exclu automatiquement de toutes les listes de ports
- Détection automatique des ports au démarrage
- Restauration complète des PSK canaux (bug corrigé)
- Ordre restauration canaux : secondaires d'abord, primaire en dernier
- module_settings restaurés (position_precision, is_muted)
- Restauration complète des clés de sécurité (private_key incluse)
- Profil flotte : suppression public_key ET private_key (admin_key conservée)

### v1.0
- Version initiale


# Meshtastic-Configuration-Manager
Outil Python/Tkinter pour sauvegarder, restaurer et déployer les configurations de nœuds Meshtastic via USB et sous windows. Export complet en JSON, génération de profils flotte (suppression des clés uniques à l'appareil), Conçu pour n’importe quel  nœuds .

[![License: CC BY-NC 4.0](https://img.shields.io/badge/License-CC_BY--NC_4.0-lightgrey.svg)](https://creativecommons.org/licenses/by-nc/4.0/)
