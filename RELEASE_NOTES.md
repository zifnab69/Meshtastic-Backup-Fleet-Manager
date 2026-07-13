# Nodes Backup & Fleet Manager — Notes de version / Release notes

> Texte de version prêt à coller dans une **GitHub Release** — tag **V1.9**.
> Il décrit les **fonctions utiles à connaître** qui ne sont **pas encore détaillées**
> sur la page des releases (https://github.com/zifnab69/Nodes-Backup-Fleet-Manager/releases).
>
> Numéro de version applicatif des fichiers exportés : **2.6** (schéma d'export interne).

---

## 🇫🇷 Français

### ✨ Nouveautés V1.9

- **Éditeur de champs clés en deux onglets** (« Principal » + « Canaux »). L'onglet Principal
  regroupe owner, LoRa, override duty cycle, rôle et multiplicateur ADC ; l'onglet Canaux gère
  les **8 canaux**.
- **Les 8 canaux éditables**, chacun avec une case **« Activé »** qui définit le rôle
  (le canal 0 reste primaire, verrouillé). Saisir un nom **auto-active** le canal, et les canaux
  actifs sont **tassés sans trou** à la sauvegarde. Correction du bug où un canal nommé restait
  désactivé (role=0).
- **Précision GPS par canal** (position_precision : NA / 23 km / … / 1 m) et **multiplicateur ADC**
  avec presets par appareil.
- **Injection des canaux fiabilisée** : ordre canonique (primaire d'abord, aligné sur `setURL`),
  **vérification post-commit** (relecture des canaux) et **relance automatique** des canaux
  silencieusement rejetés par l'appareil (nœuds non vierges / clé PKI). Testé sur Heltec V4 /
  firmware 2.7.x.
- **Validation de la longueur des PSK** dans l'éditeur (1/16/32 octets) — bloque une clé invalide
  avant qu'elle ne soit rejetée en silence par le firmware.
- **Visualiseur JSON éditable** : case « ✏ Éditer » + bouton « 💾 Enregistrer » (validation JSON
  stricte, copie horodatée dans `Backup/` avant écrasement).
- **Journaux d'import copiables** (copier/coller du détail de restauration).

### 🧩 Rappel des nouveautés récentes (V1.8)

- **Barre de progression de la restauration.** Fenêtre de progression étape par étape
  (propriétaire, sections, modules, canaux, validation finale), en mono comme en multi-nœuds.
- **Restauration fiable des clés de chiffrement des canaux (PSK).** Les clés exportées en Base64
  sont restaurées correctement (hex ET Base64 acceptés). Auparavant, restaurer une sauvegarde
  standard pouvait vider les PSK de certains canaux (les noms revenaient, pas les clés). Corrigé.
- **Persistance de la langue et du dossier de travail** (`NBFM_Config.json`).

### 🔑 Fonctions à connaître (déjà présentes mais non listées sur la page des releases)

- **Sauvegarde fidèle à 100 %.** L'export enregistre *toute* la configuration du nœud : owner,
  LoRa, Bluetooth, réseau, position, puissance, affichage, sécurité, **tous les modules** (même
  ceux que l'interface n'expose pas), canaux et nœuds connus.
- **Restauration exhaustive.** L'import réécrit *toutes* les sections et *tous* les modules présents
  dans le fichier — rien n'est ignoré en silence.
- **Profil flotte déployable.** Génère une configuration épurée (clés uniques, identifiant, owner,
  nœuds, identifiants WiFi retirés) tout en **conservant** `admin_key`, la config LoRa, les canaux
  et leurs PSK, les modules — prête à déployer sur toute une flotte.
- **Export ET restauration multi-nœuds en série.** Traitez plusieurs appareils à la suite dans une
  même session, avec sélection du port à chaque étape (COM1 exclu automatiquement).
- **Éditeur de champs clés.** Modifiez sans éditeur externe : nom long/court, région LoRa, modem
  preset, **fréquence override (MHz)**, **override duty cycle** (limite légale 1 % EU868), rôle de
  l'appareil, noms et clés PSK des canaux 0-2.
- **Générateur de clés PSK** intégré (Défaut / AES-128 / AES-256), copie en un clic.
- **Nettoyage avancé** dans l'éditeur : supprimer tous les canaux (garder le canal par défaut),
  supprimer le paramètre ADC, supprimer les nœuds connus.
- **Validation d'intégrité avant restauration** : le fichier est vérifié (présence de `local_config`,
  `lora`, `channels`, cohérence région/modem) et vous êtes averti avant d'écraser un appareil.
- **Interface bilingue FR / EN**, commutable à chaud sans redémarrer l'application.
- **Format ouvert.** Un fichier `.NBFM` est un JSON lisible et éditable avec n'importe quel éditeur
  de texte.
- **Exécutable autonome.** Compilation possible en `.exe` Windows via PyInstaller (aucune
  installation Python requise pour l'utilisateur final).

### ⚠ Rappels d'usage

- Après toute restauration, **redémarrez l'appareil** pour appliquer la configuration.
- **Exportez toujours avant** de modifier un fichier ou d'appliquer un profil flotte.
- Câble **USB DATA** requis (pas un câble de charge seul) ; pilotes CP210x / CH340 installés.
- Le paramétrage fin du firmware se fait sur https://client.meshtastic.org — NBFM est un outil de
  **sauvegarde, restauration et déploiement**, pas un configurateur complet.

---

## 🇬🇧 English

### ✨ What's new in V1.9

- **Two-tab key fields editor** ("Main" + "Channels"). The Main tab groups owner, LoRa, override
  duty cycle, role and ADC multiplier; the Channels tab manages all **8 channels**.
- **All 8 channels editable**, each with an **"Enabled"** checkbox that sets the role (channel 0
  stays primary, locked). Typing a name **auto-enables** the channel, and active channels are
  **compacted without gaps** on save. Fixes the bug where a named channel stayed disabled (role=0).
- **Per-channel GPS precision** (position_precision: NA / 23 km / … / 1 m) and **ADC multiplier**
  with per-device presets.
- **Hardened channel injection**: canonical order (primary first, aligned with `setURL`),
  **post-commit verification** (channel re-read) and **automatic retry** of channels silently
  rejected by the device (non-blank nodes / PKI key). Tested on Heltec V4 / firmware 2.7.x.
- **PSK length validation** in the editor (1/16/32 bytes) — blocks an invalid key before the
  firmware silently rejects it.
- **Editable raw-JSON viewer**: "✏ Edit" checkbox + "💾 Save" button (strict JSON validation,
  timestamped copy in `Backup/` before overwriting).
- **Copyable import logs** (copy/paste the restore details).

### 🧩 Recent additions recap (V1.8)

- **Restore progress bar.** Step-by-step progress window (owner, sections, modules, channels, final
  commit), for single-node and multi-node restores.
- **Reliable channel encryption key (PSK) restore.** Keys exported in Base64 are restored correctly
  (both hex and Base64 accepted). Previously, restoring a standard backup could wipe some channels'
  PSKs (names came back, keys did not). Fixed.
- **Language and working-directory persistence** (`NBFM_Config.json`).

### 🔑 Functions worth knowing (already present but not listed on the releases page)

- **100 % faithful backup.** Export saves the *entire* node configuration: owner, LoRa, Bluetooth,
  network, position, power, display, security, **all modules** (even those the UI does not expose),
  channels and known nodes.
- **Exhaustive restore.** Import rewrites *all* sections and *all* modules found in the file — nothing
  is silently skipped.
- **Deployable fleet profile.** Generates a trimmed configuration (unique keys, ID, owner, nodes, WiFi
  credentials removed) while **keeping** `admin_key`, LoRa config, channels and their PSKs, modules —
  ready to deploy across a whole fleet.
- **Multi-node sequential export AND restore.** Process several devices in a row within one session,
  selecting the port at each step (COM1 automatically excluded).
- **Key fields editor.** Edit without an external tool: long/short name, LoRa region, modem preset,
  **override frequency (MHz)**, **override duty cycle** (EU868 1 % legal limit), device role, channel
  0-2 names and PSK keys.
- **Built-in PSK key generator** (Default / AES-128 / AES-256), one-click copy.
- **Advanced cleanup** in the editor: clear all channels (keep the default channel), clear the ADC
  setting, clear known nodes.
- **Integrity check before restore**: the file is validated (presence of `local_config`, `lora`,
  `channels`, region/modem consistency) and you are warned before overwriting a device.
- **Bilingual FR / EN interface**, switchable on the fly without restarting the app.
- **Open format.** A `.NBFM` file is readable JSON, editable with any text editor.
- **Standalone executable.** Can be compiled to a Windows `.exe` via PyInstaller (no Python install
  required for the end user).

### ⚠ Usage reminders

- After any restore, **restart the device** to apply the configuration.
- **Always export first** before editing a file or applying a fleet profile.
- A **USB DATA** cable is required (not charge-only); CP210x / CH340 drivers installed.
- Fine firmware tuning is done on https://client.meshtastic.org — NBFM is a **backup, restore and
  deployment** tool, not a full configurator.
