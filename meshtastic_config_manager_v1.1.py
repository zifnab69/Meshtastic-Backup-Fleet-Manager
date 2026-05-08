#!/usr/bin/env python3
"""
Meshtastic Configuration Manager v1.1
Export/Import COMPLET + Profil Flotte (généralisation)
# ============================================================
# Nom du script : MESHTASTIC-CONFIGURATION-MANAGER.py
# Auteur        : ZIFNAB69_fr@yahoo.fr
# Année         : 2026
#
# Licence : Creative Commons Attribution - Pas d'Utilisation
#           Commerciale 4.0 International (CC BY-NC-SA 4.0)
#
# Vous êtes libre de :
#   - Partager — copier et redistribuer ce matériel
#   - Adapter — remixer, transformer et créer à partir de ce matériel
#
# Selon les conditions suivantes :
#   - Attribution : Vous devez créditer l'auteur, intégrer un lien
#                   vers la licence et indiquer si des modifications
#                   ont été effectuées.
#   - Pas d'utilisation commerciale : Vous ne pouvez pas utiliser
#                   ce matériel à des fins commerciales.
#
# Lien vers la licence complète :
#   https://creativecommons.org/licenses/by-nc-sa/4.0/deed.fr
# ============================================================
"""

import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk
import os, sys, threading, json, shutil, copy
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime


def check_dependencies():
    missing = []
    for pkg in ["meshtastic", "serial"]:
        try:
            __import__(pkg)
        except ImportError:
            missing.append("meshtastic" if pkg == "meshtastic" else "pyserial")
    if missing:
        root = tk.Tk(); root.withdraw()
        messagebox.showerror("Dépendances manquantes",
            f"Installez:\n  pip install meshtastic pyserial\n\nManquant: {', '.join(missing)}")
        sys.exit(1)


def get_app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def list_serial_ports() -> list:
    try:
        import serial.tools.list_ports
        return [p.device for p in sorted(serial.tools.list_ports.comports())]
    except Exception:
        return []


APP_DIR = get_app_dir()
try:
    os.chdir(APP_DIR)
except Exception:
    pass


# ─────────────────────────────────────────────────────────────────────────────
# CONNEXION
# ─────────────────────────────────────────────────────────────────────────────

def connect_device(port: Optional[str] = None):
    import meshtastic.serial_interface, time
    ports_to_try = [port] if port else list_serial_ports()
    if not ports_to_try:
        raise Exception(
            "Aucun port COM détecté.\n\nVérifiez:\n"
            "  - Câble USB data branché\n"
            "  - Drivers CP210x / CH340 installés\n"
            "  - Appareil allumé"
        )
    last_error = None
    for p in ports_to_try:
        try:
            iface = meshtastic.serial_interface.SerialInterface(devPath=p)
            waited = 0
            while not getattr(iface, "isConnected", False) and waited < 8:
                time.sleep(0.5); waited += 0.5
            if not getattr(iface, "isConnected", False):
                iface.close(); raise Exception(f"Timeout sur {p}")
            return iface
        except Exception as e:
            last_error = e
    raise Exception(
        f"Impossible de connecter sur: {', '.join(ports_to_try)}\n\n"
        f"Erreur: {last_error}\n\n"
        "Vérifiez le câble USB data et les drivers."
    )


# ─────────────────────────────────────────────────────────────────────────────
# EXPORT COMPLET
# ─────────────────────────────────────────────────────────────────────────────

def proto_to_dict(obj) -> Any:
    if obj is None or isinstance(obj, (bool, int, float, str)): return obj
    if isinstance(obj, bytes): return obj.hex()
    if isinstance(obj, dict): return {k: proto_to_dict(v) for k, v in obj.items()}
    if hasattr(obj, "DESCRIPTOR"):
        try:
            from google.protobuf.json_format import MessageToDict
            return MessageToDict(obj, preserving_proto_field_name=True,
                                 including_default_value_fields=True)
        except Exception:
            result = {}
            for field in obj.DESCRIPTOR.fields:
                try: result[field.name] = proto_to_dict(getattr(obj, field.name))
                except Exception: result[field.name] = None
            return result
    if hasattr(obj, "__iter__") and not isinstance(obj, (str, bytes)):
        try: return [proto_to_dict(item) for item in obj]
        except Exception: pass
    return str(obj)


def export_full_config(iface) -> Dict[str, Any]:
    config = {"_export_date": datetime.now().isoformat(), "_app_version": "2.2"}
    local_node = getattr(iface, "localNode", None)

    for key, getter in [
        ("my_info",  lambda: proto_to_dict(iface.myInfo) if iface.myInfo else None),
        ("metadata", lambda: proto_to_dict(local_node.metadata) if local_node and getattr(local_node, "metadata", None) else None),
    ]:
        try:
            val = getter()
            if val: config[key] = val
        except Exception as e:
            config[key] = {"error": str(e)}

    # owner
    try:
        ni = local_node.nodeInfo if local_node else None
        user = getattr(ni, "user", None) if ni else None
        config["owner"] = {
            "long_name":  getattr(user, "long_name",  "") if user else "",
            "short_name": getattr(user, "short_name", "") if user else "",
            "hw_model":   str(getattr(user, "hw_model", "")) if user else "",
        }
    except Exception as e:
        config["owner"] = {"error": str(e)}

    # localConfig
    try:
        lc = getattr(local_node, "localConfig", None) if local_node else None
        config["local_config"] = proto_to_dict(lc) if lc else {}
        if not config["local_config"]: raise Exception("vide")
    except Exception:
        config["local_config"] = {}
        for s in ["device","position","power","network","display","lora","bluetooth"]:
            try:
                val = getattr(local_node, s, None) if local_node else None
                if val is not None: config["local_config"][s] = proto_to_dict(val)
            except Exception as e:
                config["local_config"][s] = {"error": str(e)}

    # moduleConfig
    try:
        mc = getattr(local_node, "moduleConfig", None) if local_node else None
        if mc: config["module_config"] = proto_to_dict(mc)
    except Exception as e:
        config["module_config"] = {"error": str(e)}

    # channels
    try:
        ch = getattr(local_node, "channels", None) or getattr(iface, "channels", None)
        if ch: config["channels"] = proto_to_dict(ch)
    except Exception as e:
        config["channels"] = {"error": str(e)}

    # known_nodes
    try:
        if iface.nodes: config["known_nodes"] = proto_to_dict(iface.nodes)
    except Exception as e:
        config["known_nodes"] = {"error": str(e)}

    return config


# ─────────────────────────────────────────────────────────────────────────────
# PROFIL FLOTTE
# ─────────────────────────────────────────────────────────────────────────────

def build_fleet_profile(config: dict) -> dict:
    """
    Supprimé  : my_info, metadata, owner, known_nodes, _export_date,
                security.public_key, security.private_key,
                network.wifi_ssid, network.wifi_psk, compteurs version.
    Conservé  : security.admin_key (commune à la flotte),
                LoRa, canaux (PSK), modules, display, BT, position, power.
    """
    c = copy.deepcopy(config)

    for key in ["_export_date", "_app_version", "my_info", "metadata", "owner", "known_nodes"]:
        c.pop(key, None)

    c["_profile_type"] = "fleet"
    c["_profile_date"] = datetime.now().isoformat()
    c["_profile_note"] = (
        "Profil flotte — clés uniques et données spécifiques "
        "à l'appareil source supprimés. admin_key conservée."
    )

    # Supprimer uniquement les clés uniques par appareil
    sec = c.get("local_config", {}).get("security", {})
    for key in ["public_key", "private_key"]:
        sec.pop(key, None)

    # Supprimer credentials WiFi locaux
    net = c.get("local_config", {}).get("network", {})
    for key in ["wifi_ssid", "wifi_psk"]:
        net.pop(key, None)

    # Supprimer compteurs internes
    c.get("local_config", {}).pop("version", None)
    c.get("module_config", {}).pop("version", None)

    return c


# ─────────────────────────────────────────────────────────────────────────────
# IMPORT
# ─────────────────────────────────────────────────────────────────────────────

def _apply_section_to_node(local_node, section_name: str, section_data: dict) -> str:
    """
    Merge les valeurs JSON dans l'objet protobuf du nœud pour une section donnée,
    puis appelle writeConfig. Retourne un message de log.
    """
    try:
        from google.protobuf.json_format import ParseDict
    except ImportError:
        # Fallback sans ParseDict : writeConfig seul (valeurs non modifiées)
        try:
            local_node.writeConfig(section_name)
            return f"✓ [{section_name}] (sans ParseDict)"
        except Exception as e:
            return f"✗ [{section_name}]: {e}"

    try:
        # Récupérer l'objet protobuf de la section
        proto_obj = getattr(local_node.localConfig, section_name, None)
        if proto_obj is None:
            return f"⚠ [{section_name}] : section protobuf introuvable"
        # Clear() AVANT ParseDict : garantit que les champs absents du JSON
        # ne conservent pas leur ancienne valeur sur la machine cible
        proto_obj.Clear()
        ParseDict(section_data, proto_obj, ignore_unknown_fields=True)
        # Écrire sur le nœud
        local_node.writeConfig(section_name)
        return f"✓ [{section_name}]"
    except Exception as e:
        # Fallback : writeConfig sans modification protobuf
        try:
            local_node.writeConfig(section_name)
            return f"✓ [{section_name}] (fallback, ParseDict échoué: {e})"
        except Exception as e2:
            return f"✗ [{section_name}]: {e2}"


def _apply_module_section(local_node, section_name: str, section_data: dict) -> str:
    """Idem pour les modules."""
    try:
        from google.protobuf.json_format import ParseDict
        proto_obj = getattr(local_node.moduleConfig, section_name, None)
        if proto_obj is None:
            return None
        # Clear() avant ParseDict : écrasement total, pas de merge partiel
        proto_obj.Clear()
        ParseDict(section_data, proto_obj, ignore_unknown_fields=True)
        local_node.writeConfig(section_name)
        return f"✓ module [{section_name}]"
    except Exception:
        try:
            local_node.writeConfig(section_name)
            return f"✓ module [{section_name}] (fallback)"
        except Exception:
            return None


def import_full_config(iface, config: Dict[str, Any]) -> list:
    log = []
    local_node = iface.localNode

    # ── Owner ──
    try:
        owner = config.get("owner", {})
        ln = owner.get("long_name", "") if isinstance(owner, dict) else ""
        sn = owner.get("short_name", "") if isinstance(owner, dict) else ""
        if ln or sn:
            local_node.setOwner(long_name=ln, short_name=sn)
            log.append(f"✓ Owner: '{ln}' / '{sn}'")
        else:
            log.append("– Owner: non modifié (profil flotte)")
    except Exception as e:
        log.append(f"✗ Owner: {e}")

    # ── Config locale (injecte les valeurs JSON dans le protobuf AVANT writeConfig) ──
    local_cfg = config.get("local_config", {})
    for section in ["device", "position", "power", "network", "display", "lora", "bluetooth"]:
        if section in local_cfg and local_cfg[section]:
            msg = _apply_section_to_node(local_node, section, local_cfg[section])
            log.append(msg)

    # ── Modules ──
    module_cfg = config.get("module_config", {})
    for section in ["mqtt", "serial", "external_notification", "store_forward",
                    "range_test", "telemetry", "canned_message",
                    "neighbor_info", "ambient_lighting", "detection_sensor", "paxcounter"]:
        if section in module_cfg and module_cfg[section]:
            msg = _apply_module_section(local_node, section, module_cfg[section])
            if msg:
                log.append(msg)

    # ── Canaux — injection protobuf canal par canal ──────────────────────────
    try:
        from google.protobuf.json_format import ParseDict
        from meshtastic.protobuf import channel_pb2
    except ImportError as ie:
        log.append(f"⚠ Import protobuf canaux impossible: {ie}")
        channel_pb2 = None

    channels_json = config.get("channels", None)

    # Normaliser en liste de (index, entry_dict) quelle que soit la structure exportée
    # Format dict : {"0": {...}, "1": {...}}  ← ce que produit proto_to_dict
    # Format liste : [{index:0, ...}, {index:1, ...}]  ← format alternatif
    ch_entries = []
    if isinstance(channels_json, dict):
        for k, v in channels_json.items():
            if isinstance(v, dict):
                try:
                    ch_entries.append((int(k), v))
                except (ValueError, TypeError):
                    pass
    elif isinstance(channels_json, list):
        for entry in channels_json:
            if isinstance(entry, dict):
                idx_val = entry.get("index", None)
                if idx_val is not None:
                    ch_entries.append((int(idx_val), entry))

    if ch_entries:
        for ch_index, entry in ch_entries:
            role_val = entry.get("role", 0)
            settings = entry.get("settings", {}) or {}
            ch_name  = settings.get("name", "")

            # Récupérer le canal existant sur le nœud (PSK préservée)
            existing = local_node.getChannelByChannelIndex(ch_index)
            if existing is None:
                if channel_pb2:
                    existing = channel_pb2.Channel()
                    existing.index = ch_index
                else:
                    log.append(f"⚠ Canal {ch_index} introuvable et channel_pb2 absent")
                    continue

            # Appliquer nom et rôle
            existing.settings.name = ch_name  # "" si pas de nom = OK
            if role_val in (1, 2):
                existing.role = role_val
            else:
                existing.role = 0  # DISABLED

            try:
                local_node.channels[ch_index] = existing
                local_node.writeChannel(ch_index)
                status = "DISABLED" if role_val == 0 else f"'{ch_name}'"
                log.append(f"✓ Canal {ch_index} {status} écrit")
            except Exception as e:
                log.append(f"✗ Canal {ch_index}: {e}")
    else:
        log.append("– Canaux: aucun canal dans le fichier")

    return log


# ─────────────────────────────────────────────────────────────────────────────
# UI
# ─────────────────────────────────────────────────────────────────────────────


# ─────────────────────────────────────────────────────────────────────────────
# VALIDATION INTÉGRITÉ
# ─────────────────────────────────────────────────────────────────────────────

REQUIRED_SECTIONS = {
    "local_config": ["lora"],
    "channels":     [],
}

def validate_config_integrity(config: dict) -> list:
    """Retourne une liste d'avertissements (vide = OK)."""
    warnings = []
    if not isinstance(config, dict):
        warnings.append("✗ Le fichier n'est pas un objet JSON valide.")
        return warnings
    for section, subsections in REQUIRED_SECTIONS.items():
        if section not in config or not config[section]:
            warnings.append(f"✗ Section manquante ou vide : '{section}'")
        else:
            for sub in subsections:
                val = config[section]
                if isinstance(val, dict) and sub not in val:
                    warnings.append(f"⚠ Sous-section absente : '{section}.{sub}'")
    lc = config.get("local_config", {})
    if isinstance(lc, dict):
        lora = lc.get("lora", {})
        if isinstance(lora, dict) and not lora.get("region") and not lora.get("modem_preset"):
            warnings.append("⚠ LoRa : région et modem_preset absents — vérifiez la config LoRa")
    return warnings


# ─────────────────────────────────────────────────────────────────────────────
# MAPPINGS LORA — valeurs entières <-> labels humains
# ─────────────────────────────────────────────────────────────────────────────

LORA_REGIONS = {
    0:  ("UNSET",   "Non défini"),
    1:  ("US",      "États-Unis 902-928 MHz"),
    2:  ("EU_433",  "Europe 433 MHz"),
    3:  ("EU_868",  "Europe 868 MHz ← France"),
    4:  ("CN",      "Chine 470-510 MHz"),
    5:  ("JP",      "Japon 920-928 MHz"),
    6:  ("ANZ",     "Australie/NZ 915-928 MHz"),
    7:  ("KR",      "Corée 920-923 MHz"),
    8:  ("TW",      "Taïwan 920-925 MHz"),
    9:  ("RU",      "Russie 868 MHz"),
    10: ("IN",      "Inde 865-867 MHz"),
    11: ("NZ_865",  "Nouvelle-Zélande 865 MHz"),
    12: ("TH",      "Thaïlande 920-925 MHz"),
    13: ("LORA_24", "Mondial 2.4 GHz"),
    14: ("UA_433",  "Ukraine 433 MHz"),
    15: ("UA_868",  "Ukraine 868 MHz"),
    16: ("MY_433",  "Malaisie 433 MHz"),
    17: ("MY_919",  "Malaisie 919 MHz"),
    18: ("SG_923",  "Singapour 923 MHz"),
}

MODEM_PRESETS = {
    0: ("LONG_FAST",    "LongFast    — longue portée, débit modéré (défaut)"),
    1: ("LONG_SLOW",    "LongSlow    — très longue portée, débit lent"),
    2: ("VERY_LONG_SLOW","VeryLongSlow — portée max, débit très lent"),
    3: ("MEDIUM_SLOW",  "MediumSlow  — portée moyenne, débit lent"),
    4: ("MEDIUM_FAST",  "MediumFast  — portée moyenne, débit rapide"),
    5: ("SHORT_SLOW",   "ShortSlow   — courte portée, débit lent"),
    6: ("SHORT_FAST",   "ShortFast   — courte portée, débit rapide"),
    7: ("LONG_MODERATE","LongModerate — longue portée, débit modéré+"),
    8: ("SHORT_TURBO",  "ShortTurbo  — courte portée, débit maximum"),
}

# Helpers de conversion int <-> label combobox
def _region_labels():
    return [f"{v} — {k}  [{i}]" for i, (v, k) in LORA_REGIONS.items()]

def _modem_labels():
    return [f"{label}" for label in MODEM_PRESETS.values()]

def _region_int_from_label(label: str) -> int:
    """Extrait l'entier depuis un label de la combobox région."""
    try:
        return int(label.split("[")[-1].rstrip("]"))
    except Exception:
        return 0

def _modem_int_from_label(label: str) -> int:
    """Retrouve l'index du preset depuis son label."""
    for i, (code, desc) in MODEM_PRESETS.items():
        if code in label:
            return i
    return 0

def _region_label_from_int(val) -> str:
    try:
        i = int(val)
        v, k = LORA_REGIONS.get(i, ("UNSET", "Non défini"))
        return f"{v} — {k}  [{i}]"
    except Exception:
        return _region_labels()[0]

def _modem_label_from_int(val) -> str:
    try:
        i = int(val)
        code, desc = MODEM_PRESETS.get(i, ("LONG_FAST", "LongFast — longue portée, débit modéré (défaut)"))
        return f"{code}    — {desc.split('— ', 1)[-1].strip()}"
    except Exception:
        return list(MODEM_PRESETS.values())[0][1]


def read_file_meta(path: Path) -> dict:
    """Lit rapidement les métadonnées clés d'un fichier JSON sans tout parser."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        owner = data.get("owner", {})
        long_name = owner.get("long_name", "") if isinstance(owner, dict) else ""
        hw_model  = owner.get("hw_model", "") if isinstance(owner, dict) else ""
        profile_type = data.get("_profile_type", "")
        date_raw = data.get("_export_date", data.get("_profile_date", ""))
        # shorten date
        date_short = date_raw[:16].replace("T", " ") if date_raw else "?"
        # canal 0 et canal 1
        channels = data.get("channels", [])
        def _ch_name(idx):
            if isinstance(channels, list) and len(channels) > idx:
                ch = channels[idx]
                if isinstance(ch, dict):
                    s = ch.get("settings", {})
                    return s.get("name", "") if isinstance(s, dict) else ""
            return ""
        ch0_name = _ch_name(0) or "—"
        ch1_name = _ch_name(1) or "—"
        tag = "🚀FLOTTE" if profile_type == "fleet" else "💾BACKUP"
        return {
            "tag": tag,
            "long_name": long_name or "?",
            "hw_model": hw_model or "?",
            "ch_name": ch0_name,
            "ch1_name": ch1_name,
            "date": date_short,
        }
    except Exception:
        return {"tag": "?", "long_name": "?", "hw_model": "?", "ch_name": "?", "ch1_name": "?", "date": "?"}

class MeshtasticApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Meshtastic Config Manager v1.1")
        self.root.geometry("840x900")
        self.root.resizable(True, True)
        self.work_dir = APP_DIR
        self._build_ui()
        self.refresh_files()

    def _build_ui(self):
        root = self.root
        # ── En-tête global ────────────────────────────────────────────────────
        ttk.Label(root, text="Meshtastic Config Manager v1.1",
                  font=("Arial", 15, "bold")).pack(pady=(15, 2))
        ttk.Label(root, text="Sauvegarde, Restauration & Profil Flotte",
                  font=("Arial", 9), foreground="#555").pack(pady=(0, 8))
        ttk.Separator(root, orient="horizontal").pack(fill="x", padx=20, pady=(0, 6))

        # ── Notebook (onglets Principal / Aide) ───────────────────────────────
        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill="both", expand=True, padx=8, pady=(0, 4))

        main_tab = ttk.Frame(self.notebook, padding=4)
        self.notebook.add(main_tab, text="  ⚙️  Principal  ")

        aide_tab = ttk.Frame(self.notebook, padding=8)
        self.notebook.add(aide_tab, text="  ❓  Aide  ")
        self._build_aide_tab(aide_tab)

        root = main_tab  # redirige le pack() suivant vers l'onglet Principal

        # Dossier
        df = ttk.LabelFrame(root, text="  📂 Dossier de sauvegarde  ", padding=8)
        df.pack(padx=20, pady=4, fill="x")
        self.dir_var = tk.StringVar(value=str(self.work_dir))
        ttk.Entry(df, textvariable=self.dir_var, state="readonly").pack(
            side="left", fill="x", expand=True, padx=(0, 8))
        ttk.Button(df, text="📁 Choisir", command=self.choose_work_dir).pack(side="left", padx=3)
        ttk.Button(df, text="🗂 Ouvrir",  command=self.open_folder).pack(side="left", padx=3)

        # Connexion
        cf = ttk.LabelFrame(root, text="  🔌 Connexion appareil  ", padding=8)
        cf.pack(padx=20, pady=6, fill="x")
        row = ttk.Frame(cf); row.pack(fill="x")
        ttk.Label(row, text="Port COM :").pack(side="left")
        self.port_var = tk.StringVar(value="")
        self.port_combo = ttk.Combobox(row, textvariable=self.port_var, width=12)
        self.port_combo.pack(side="left", padx=6)
        ttk.Button(row, text="🔍 Détecter ports", command=self.detect_ports).pack(side="left", padx=4)
        ttk.Label(row, text="(vide = scan auto)", foreground="#888", font=("Arial", 8)).pack(side="left", padx=6)

        # Export
        ef = ttk.LabelFrame(root, text="  📤 Export — Lire la config depuis l'appareil  ", padding=8)
        ef.pack(padx=20, pady=6, fill="x")
        tk.Button(ef, text="📤 EXPORTER CONFIG COMPLÈTE → JSON",
                  command=self.export_config,
                  background="#cce0ff", activebackground="#99c2ff",
                  relief="raised", font=("Arial", 9, "bold")).pack(fill="x", ipady=6)
        ttk.Label(ef,
            text="Sauvegarde : owner · LoRa · BT · réseau · position · puissance · modules · canaux · nœuds connus",
            font=("Arial", 8), foreground="#666").pack(anchor="w", pady=(3, 0))

        # Liste fichiers — Treeview tabulaire
        lf = ttk.LabelFrame(root, text="  🗃️ Fichiers de sauvegarde (JSON)  ", padding=8)
        lf.pack(padx=20, pady=4, fill="both", expand=True)
        cols = ("type", "fichier", "modele", "canal0", "canal1", "date")
        self.tree = ttk.Treeview(lf, columns=cols, show="headings",
                                 selectmode="browse", height=6)
        self.tree.heading("type",   text="Type",    anchor="w")
        self.tree.heading("fichier",text="Fichier", anchor="w")
        self.tree.heading("modele", text="Modèle",  anchor="w")
        self.tree.heading("canal0", text="Canal 0", anchor="w")
        self.tree.heading("canal1", text="Canal 1", anchor="w")
        self.tree.heading("date",   text="Date",    anchor="w")
        self.tree.column("type",   width=75,  stretch=False)
        self.tree.column("fichier",width=255, stretch=True)
        self.tree.column("modele", width=85,  stretch=False)
        self.tree.column("canal0", width=90,  stretch=False)
        self.tree.column("canal1", width=90,  stretch=False)
        self.tree.column("date",   width=125, stretch=False)
        self.tree.tag_configure("backup", foreground="#1a5e1a")
        self.tree.tag_configure("fleet",  foreground="#003399")
        vsb = ttk.Scrollbar(lf, orient="vertical",   command=self.tree.yview)
        hsb = ttk.Scrollbar(lf, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        lf.rowconfigure(0, weight=1)
        lf.columnconfigure(0, weight=1)
        self.tree.bind("<Double-Button-1>", lambda e: self.view_file())
        br = ttk.Frame(lf); br.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        ttk.Button(br, text="🔄 Actualiser",         command=self.refresh_files).pack(side="left", padx=3)
        ttk.Button(br, text="👁️ Voir contenu",       command=self.view_file).pack(side="left", padx=3)
        ttk.Button(br, text="📋 Copier fichier",     command=self.copy_file).pack(side="left", padx=3)
        ttk.Button(br, text="🗑️ Supprimer",          command=self.delete_file).pack(side="left", padx=3)
        ttk.Button(br, text="📂 Choisir un autre fichier…", command=self.import_browse).pack(side="left", padx=(12, 3))

        # Profil flotte
        ff = ttk.LabelFrame(root, text="  🚀 Profil Flotte — Générer une config déployable  ", padding=8)
        ff.pack(padx=20, pady=4, fill="x")
        ttk.Button(ff, text="🚀 GÉNÉRER PROFIL FLOTTE depuis le fichier sélectionné",
                   command=self.generate_fleet_profile).pack(fill="x", ipady=6)
        ttk.Label(ff,
            text="Supprime : clés uniques (pub/priv) · identifiants · nœuds · owner · firmware\n"
                 "Conserve : admin_key · LoRa · canaux (PSK) · modules · réseau · display · BT",
            font=("Arial", 8), foreground="#003388").pack(anchor="w", pady=(3, 0))

        # Import
        imf = ttk.LabelFrame(root, text="  📥 Import — Restaurer la config vers l'appareil  ", padding=8)
        imf.pack(padx=20, pady=6, fill="x")
        ttk.Button(imf, text="✏️ Éditer les champs clés du fichier sélectionné…",
                   command=self.edit_config_fields).pack(fill="x", ipady=4, pady=(0, 4))
        btn_restore = tk.Button(imf, text="📥 RESTAURER le fichier sélectionné → Appareil",
                   command=self.import_selected,
                   background="#cce0ff", activebackground="#99c2ff",
                   relief="raised", font=("Arial", 9, "bold"))
        btn_restore.pack(fill="x", ipady=6)

        # Status bar
        self.status_var = tk.StringVar(value="Prêt.")
        ttk.Label(root, textvariable=self.status_var, relief="sunken",
                  font=("Arial", 9), foreground="#003366", anchor="w").pack(
            fill="x", side="bottom", ipady=3)


  
    # ── Onglet Aide ───────────────────────────────────────────────────────────

    def _build_aide_tab(self, parent):
        """Construit l'onglet d'aide avec scroll."""
        canvas = tk.Canvas(parent, highlightthickness=0)
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        inner = ttk.Frame(canvas)
        window_id = canvas.create_window((0, 0), window=inner, anchor="nw")

        def on_frame_configure(event):
            canvas.configure(scrollregion=canvas.bbox("all"))
        def on_canvas_resize(event):
            canvas.itemconfig(window_id, width=event.width)
        inner.bind("<Configure>", on_frame_configure)
        canvas.bind("<Configure>", on_canvas_resize)
        canvas.bind_all("<MouseWheel>",
            lambda e: canvas.yview_scroll(int(-1 * (e.delta / 120)), "units"))

        def section(title):
            ttk.Separator(inner, orient="horizontal").pack(fill="x", pady=(10, 4))
            ttk.Label(inner, text=title, font=("Arial", 11, "bold"),
                      foreground="#003399").pack(anchor="w", padx=6, pady=(0, 3))

        def para(text):
            ttk.Label(inner, text=text, wraplength=680, justify="left",
                      font=("Arial", 9)).pack(anchor="w", padx=16, pady=1)

        def step(num, text):
            ttk.Label(inner, text=f"  {num}. {text}", wraplength=660, justify="left",
                      font=("Arial", 9)).pack(anchor="w", padx=16, pady=1)

        ttk.Label(inner, text="📖  Guide d'utilisation — Meshtastic Config Manager v1.1",
                  font=("Arial", 12, "bold"), foreground="#001f66").pack(
                  anchor="w", padx=6, pady=(8, 2))
        ttk.Label(inner,
                  text="Cet outil permet d'exporter, sauvegarder et restaurer la configuration "
                       "de noeuds Meshtastic (T-Echo, ESP32 V3) via USB.",
                  wraplength=680, justify="left", font=("Arial", 9),
                  foreground="#444").pack(anchor="w", padx=6, pady=(0, 4))

        section("Prerequis")
        para("* Python 3.8+  +  packages :  pip install meshtastic pyserial sauf si utilisé en EXE")
        para("* Cable USB DATA (pas un cable de charge uniquement)")
        para("* Pilotes USB installes : CP210x (Silicon Labs) ou CH340 selon le modele")
        para("* Appareil Meshtastic allume en mode normal (pas en mode DFU/bootloader)")

        section("Dossier de sauvegarde")
        para("Par defaut, les fichiers JSON sont enregistres dans le dossier du script.")
        step(1, "Cliquez sur Choisir pour selectionner un autre dossier.")
        step(2, "Cliquez sur Ouvrir pour l'ouvrir dans l'explorateur de fichiers.")

        section("Connexion a l'appareil")
        para("Le champ Port COM permet de cibler un port precis ou de laisser le scan auto.")
        step(1, "Branchez l'appareil en USB.")
        step(2, "Cliquez sur Detecter ports — le premier port detecte est pre-selectionne.")
        step(3, "Laissez le champ vide pour scanner tous les ports automatiquement.")
        para("Si aucun port n'est detecte : verifiez le cable et les pilotes CP210x / CH340.")

        section("Exporter la configuration")
        para("Lit et sauvegarde en JSON l'integralite de la config de l'appareil connecte.")
        step(1, "Assurez-vous que l'appareil est connecte.")
        step(2, "Cliquez sur EXPORTER CONFIG COMPLETE.")
        step(3, "Choisissez le nom et l'emplacement du fichier de sauvegarde.")
        step(4, "Attendez le message de confirmation Export reussi.")
        para("Contenu : owner, LoRa, Bluetooth, reseau, position, puissance, modules, canaux, noeuds.")

        section("Export multi-noeuds sequentiel")
        para("Exporte plusieurs noeuds en sequence sans quitter l'application.")
        step(1, "Cliquez sur EXPORT MULTI-NOEUDS.")
        step(2, "Branchez chaque noeud a son tour et confirmez a chaque etape.")
        step(3, "Cliquez Non pour terminer — un recapitulatif s'affiche.")

        section("Gestion des fichiers de sauvegarde")
        para("La liste affiche : type, modele, canal, date. Triee par date decroissante.")
        step(1, "Actualiser — recharge la liste.")
        step(2, "Voir contenu ou double-clic — ouvre le JSON en lecture.")
        step(3, "Copier fichier — duplique le fichier selectionne.")
        step(4, "Supprimer — supprime definitivement (confirmation demandee).")
        para("BACKUP = sauvegarde complete (vert)   FLOTTE = profil flotte (bleu)")

        section("Generer un Profil Flotte")
        para("Un profil flotte est une config epuree, deployable sur n'importe quel noeud.")
        step(1, "Selectionnez un fichier d'export complet dans la liste.")
        step(2, "Cliquez sur GENERER PROFIL FLOTTE.")
        step(3, "Choisissez le nom du fichier de profil flotte.")
        para("SUPPRIME : cle pub/priv, identifiant, owner, noeuds, credentials WiFi, compteurs.")
        para("CONSERVE : admin_key, LoRa, canaux PSK, modules, BT, display, position, power.")

        section("Editeur de champs cles")
        para("Modifiez les champs courants d'un JSON sans editeur externe.")
        step(1, "Selectionnez un fichier dans la liste.")
        step(2, "Cliquez sur Editer les champs cles.")
        step(3, "Modifiez : nom long/court, region LoRa, modem preset, nom du canal primaire.")
        step(4, "Cliquez Sauvegarder — le fichier JSON est mis a jour directement.")

        section("Restaurer la configuration")
        para("Ecrit un fichier JSON vers un appareil connecte.")
        step(1, "Selectionnez le fichier dans la liste OU Choisir un autre fichier.")
        step(2, "Cliquez sur RESTAURER.")
        step(3, "Si des avertissements d'integrite s'affichent, lisez-les avant de confirmer.")
        step(4, "Attendez le succes, puis REDEMARREZ l'appareil pour appliquer.")
        para("ATTENTION : la restauration ecrase la config actuelle. Exportez avant si besoin !")

        section("Verification d'integrite")
        para("Avant toute restauration, le fichier est automatiquement valide :")
        para("* Presence de local_config et local_config.lora")
        para("* Presence de la section channels")
        para("* Coherence de la config LoRa (region, modem_preset)")
        para("En cas de probleme, un avertissement s'affiche — vous pouvez annuler ou forcer.")

        section("Conseils et bonnes pratiques")
        para("* Nommez vos fichiers explicitement : meshtastic_backup_HELLFEST_2025.json")
        para("* Exportez toujours AVANT de modifier ou d'appliquer un profil flotte.")
        para("* Les profils flotte peuvent etre partages entre membres d'une meme equipe.")
        para("* Si export echoue avec Timeout : debranchez/rebranchez le cable et reessayez.")
        para("* Sous Windows : verifiez Gestionnaire de peripheriques > Ports (COM et LPT).")
        para("* Le fichier JSON est lisible et editable manuellement avec un editeur de texte.")

        ttk.Separator(inner, orient="horizontal").pack(fill="x", pady=(10, 4))
        ttk.Label(inner, text="Meshtastic Config Manager v1.1",
                  font=("Arial", 8), foreground="#aaa").pack(anchor="e", padx=8, pady=4)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def set_status(self, msg):
        self.status_var.set(msg)
        self.root.update_idletasks()

    def detect_ports(self):
        ports = list_serial_ports()
        self.port_combo["values"] = ports
        if ports:
            self.port_combo.set(ports[0])
            self.set_status(f"✓ {len(ports)} port(s): {', '.join(ports)}")
        else:
            self.set_status("⚠ Aucun port COM — vérifiez le câble USB")

    def choose_work_dir(self):
        s = filedialog.askdirectory(title="Dossier de sauvegarde", initialdir=str(self.work_dir))
        if s:
            self.work_dir = Path(s)
            self.dir_var.set(str(self.work_dir))
            self.refresh_files()
            self.set_status(f"✓ Dossier: {self.work_dir}")

    def refresh_files(self):
        self.tree.delete(*self.tree.get_children())
        self._file_map = {}
        try:
            paths = sorted(
                list(self.work_dir.glob("*.json")) +
                list(self.work_dir.glob("*.yaml")) +
                list(self.work_dir.glob("*.yml")),
                key=lambda p: p.stat().st_mtime, reverse=True
            )
            for p in paths:
                meta = read_file_meta(p)
                tag = "fleet" if meta["tag"].startswith("🚀") else "backup"
                type_label = "🚀 Flotte" if tag == "fleet" else "💾 Backup"
                iid = self.tree.insert("", "end",
                    values=(type_label, p.name, meta["hw_model"],
                            meta["ch_name"], meta["ch1_name"], meta["date"]),
                    tags=(tag,))
                self._file_map[iid] = p
            self.set_status(f"✓ {len(paths)} fichier(s) dans {self.work_dir.name}")
        except Exception as e:
            self.set_status(f"✗ {e}")

    def open_folder(self):
        try:
            os.startfile(str(self.work_dir))
        except Exception as e:
            messagebox.showerror("Erreur", str(e))

    def _get_selected_file(self) -> Optional[Path]:
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("Aucune sélection", "Sélectionnez un fichier dans la liste.")
            return None
        return self._file_map.get(sel[0])

    # ── Export ────────────────────────────────────────────────────────────────

    def export_config(self):
        now = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = filedialog.asksaveasfilename(
            title="Sauvegarder la config complète",
            initialdir=str(self.work_dir),
            defaultextension=".json",
            initialfile=f"meshtastic_backup_{now}.json",
            filetypes=[("JSON", "*.json"), ("Tous", "*.*")]
        )
        if not filename: return
        self.set_status("⏳ Connexion à l'appareil…")

        def do_export():
            iface = None
            try:
                iface = connect_device(self.port_var.get().strip() or None)
                self.root.after(0, lambda: self.set_status("⏳ Lecture config…"))
                config = export_full_config(iface)
                with open(filename, "w", encoding="utf-8") as f:
                    json.dump(config, f, indent=2, ensure_ascii=False, default=str)
                self.work_dir = Path(filename).resolve().parent
                self.root.after(0, lambda: self.dir_var.set(str(self.work_dir)))
                self.root.after(0, self.refresh_files)
                self.root.after(0, lambda: self.set_status(f"✓ {Path(filename).name}"))
                self.root.after(0, lambda: messagebox.showinfo("Export réussi ✓",
                    f"Config complète sauvegardée:\n{filename}"))
            except Exception as e:
                err = str(e)
                self.root.after(0, lambda: self.set_status("✗ Export échoué"))
                self.root.after(0, lambda: messagebox.showerror("Erreur export", err))
            finally:
                if iface:
                    try: iface.close()
                    except Exception: pass

        threading.Thread(target=do_export, daemon=True).start()

    # ── Profil Flotte ─────────────────────────────────────────────────────────

    def generate_fleet_profile(self):
        f = self._get_selected_file()
        if not f: return

        try:
            with open(f, "r", encoding="utf-8") as fp:
                config = json.load(fp)
        except Exception as e:
            messagebox.showerror("Fichier invalide", str(e)); return

        if config.get("_profile_type") == "fleet":
            if not messagebox.askyesno("Déjà un profil flotte",
                "Ce fichier est déjà un profil flotte.\n\nContinuer quand même ?"):
                return

        now = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest = filedialog.asksaveasfilename(
            title="Enregistrer le profil flotte",
            initialdir=str(self.work_dir),
            defaultextension=".json",
            initialfile=f"profil_flotte_{now}.json",
            filetypes=[("JSON", "*.json"), ("Tous", "*.*")]
        )
        if not dest: return

        try:
            fleet = build_fleet_profile(config)
            with open(dest, "w", encoding="utf-8") as fp:
                json.dump(fleet, fp, indent=2, ensure_ascii=False)
            self.work_dir = Path(dest).resolve().parent
            self.dir_var.set(str(self.work_dir))
            self.refresh_files()
            self.set_status(f"✓ Profil flotte créé: {Path(dest).name}")
            messagebox.showinfo("Profil flotte créé ✓",
                f"Fichier créé:\n{dest}\n\n"
                "Éléments supprimés (uniques à l'appareil source):\n"
                "  ✗ my_info (ID, device_id, firmware)\n"
                "  ✗ metadata\n"
                "  ✗ owner (nom de l'appareil)\n"
                "  ✗ known_nodes (nœuds du mesh)\n"
                "  ✗ security.public_key + private_key\n"
                "  ✗ network.wifi_ssid + wifi_psk\n"
                "  ✗ Compteurs version internes\n\n"
                "Éléments conservés (applicables à la flotte):\n"
                "  ✓ security.admin_key\n"
                "  ✓ Config LoRa (LONG_FAST, fréquence, région…)\n"
                "  ✓ Canaux (HellDogs, BackHell avec PSK)\n"
                "  ✓ Config Bluetooth, display, position, power\n"
                "  ✓ Tous les modules"
            )
        except Exception as e:
            messagebox.showerror("Erreur", str(e))

    # ── Import ────────────────────────────────────────────────────────────────

    def _do_import(self, filename: str):
        file_path = Path(filename)
        if not file_path.exists():
            messagebox.showerror("Fichier introuvable", str(filename)); return
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                config = json.load(f)
        except Exception as e:
            messagebox.showerror("Fichier invalide", str(e)); return

        # ── Vérification intégrité ─────────────────────────────────────────
        integrity_warns = validate_config_integrity(config)
        if integrity_warns:
            warn_text = "\n".join(integrity_warns)
            if not messagebox.askyesno(
                "⚠ Avertissements d'intégrité",
                f"Le fichier présente les problèmes suivants :\n\n{warn_text}\n\n"
                "Continuer quand même la restauration ?"
            ):
                return

        profile_type = config.get("_profile_type", "complet")
        export_date  = config.get("_export_date", config.get("_profile_date", "inconnue"))
        owner = config.get("owner", {})
        ln = owner.get("long_name", "Non défini (profil flotte)") if isinstance(owner, dict) else "?"
        type_label = "⚡ PROFIL FLOTTE" if profile_type == "fleet" else "📦 Sauvegarde complète"

        if not messagebox.askyesno("Confirmer la restauration",
            f"Fichier : {file_path.name}\n"
            f"Type    : {type_label}\n"
            f"Date    : {export_date}\n"
            f"Source  : {ln}\n\n"
            "⚠ Écrase la config actuelle de l'appareil.\n\nContinuer ?"):
            return

        self.set_status(f"⏳ Restauration {file_path.name}…")

        def do_import():
            iface = None
            try:
                iface = connect_device(self.port_var.get().strip() or None)
                self.root.after(0, lambda: self.set_status("⏳ Application config…"))
                log_lines = import_full_config(iface, config)
                log_text = "\n".join(log_lines)
                self.root.after(0, lambda: self.set_status(f"✓ Restauré: {file_path.name}"))
                self.root.after(0, lambda: messagebox.showinfo("Import réussi ✓",
                    f"Config restaurée:\n{filename}\n\n{log_text}\n\n"
                    "⚠ Redémarrez l'appareil pour appliquer."))
            except Exception as e:
                err = str(e)
                self.root.after(0, lambda: self.set_status("✗ Import échoué"))
                self.root.after(0, lambda: messagebox.showerror("Erreur import", err))
            finally:
                if iface:
                    try: iface.close()
                    except Exception: pass

        threading.Thread(target=do_import, daemon=True).start()

    def import_selected(self):
        f = self._get_selected_file()
        if f: self._do_import(str(f))

    def import_browse(self):
        fn = filedialog.askopenfilename(
            title="Choisir un fichier de config",
            initialdir=str(self.work_dir),
            filetypes=[("JSON/YAML", "*.json *.yaml *.yml"), ("Tous", "*.*")]
        )
        if fn: self._do_import(fn)


    # ── Export multi-nœuds ────────────────────────────────────────────────────

    def export_multi_nodes(self):
        """Export séquentiel de plusieurs nœuds sans quitter l'application."""
        count = 0
        while True:
            rep = messagebox.askyesno(
                f"Export multi-nœuds — nœud #{count + 1}",
                f"{'Branchez' if count == 0 else 'Rebranchez'} le nœud #{count + 1} "
                f"sur le port USB puis cliquez Oui pour exporter.\n\n"
                "Cliquez Non pour terminer la session."
            )
            if not rep:
                self.set_status(f"✓ Session terminée — {count} nœud(s) exporté(s)")
                break
            now = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = filedialog.asksaveasfilename(
                title=f"Sauvegarder nœud #{count + 1}",
                initialdir=str(self.work_dir),
                defaultextension=".json",
                initialfile=f"meshtastic_node{count+1:02d}_{now}.json",
                filetypes=[("JSON", "*.json"), ("Tous", "*.*")]
            )
            if not filename:
                continue
            self.set_status(f"⏳ Connexion nœud #{count + 1}…")
            try:
                iface = connect_device(self.port_var.get().strip() or None)
                config = export_full_config(iface)
                iface.close()
                with open(filename, "w", encoding="utf-8") as f:
                    json.dump(config, f, indent=2, ensure_ascii=False, default=str)
                self.work_dir = Path(filename).resolve().parent
                self.dir_var.set(str(self.work_dir))
                self.refresh_files()
                count += 1
                self.set_status(f"✓ Nœud #{count} exporté : {Path(filename).name}")
            except Exception as e:
                messagebox.showerror(f"Erreur nœud #{count + 1}", str(e))

    # ── Éditeur de champs clés ────────────────────────────────────────────────

    def edit_config_fields(self):
        """Ouvre un formulaire minimaliste pour modifier les champs courants d'un JSON."""
        f = self._get_selected_file()
        if not f: return
        try:
            with open(f, "r", encoding="utf-8") as fp:
                config = json.load(fp)
        except Exception as e:
            messagebox.showerror("Fichier invalide", str(e)); return

        win = tk.Toplevel(self.root)
        win.title(f"✏️ Éditer champs clés — {f.name}")
        win.geometry("520x530")
        win.resizable(True, True)
        win.grab_set()

        ttk.Label(win, text=f"Fichier : {f.name}",
                  font=("Arial", 9, "bold")).pack(anchor="w", padx=12, pady=(10, 2))
        ttk.Separator(win, orient="horizontal").pack(fill="x", padx=10, pady=4)

        frm = ttk.Frame(win, padding=10)
        frm.pack(fill="both", expand=True)
        frm.columnconfigure(1, weight=1)

        def labeled_entry(row, label, value):
            ttk.Label(frm, text=label, font=("Arial", 9)).grid(
                row=row, column=0, sticky="w", padx=(0, 10), pady=4)
            var = tk.StringVar(value=str(value) if value else "")
            ttk.Entry(frm, textvariable=var, width=38).grid(
                row=row, column=1, sticky="ew", pady=4)
            return var

        # owner
        ttk.Label(frm, text="── Owner ──", font=("Arial", 9, "bold"),
                  foreground="#333").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 2))
        owner = config.get("owner", {}) or {}
        v_long  = labeled_entry(1, "Nom long :", owner.get("long_name", ""))
        v_short = labeled_entry(2, "Nom court :", owner.get("short_name", ""))

        # LoRa
        ttk.Label(frm, text="── LoRa ──", font=("Arial", 9, "bold"),
                  foreground="#333").grid(row=3, column=0, columnspan=2, sticky="w", pady=(8, 2))
        lora = config.get("local_config", {}).get("lora", {}) or {}
        # Région — affichage lisible, stockage entier
        ttk.Label(frm, text="Région LoRa :", font=("Arial", 9)).grid(
            row=4, column=0, sticky="w", padx=(0, 10), pady=4)
        v_region = tk.StringVar(value=_region_label_from_int(lora.get("region", 0)))
        ttk.Combobox(frm, textvariable=v_region, values=_region_labels(),
                     state="readonly", width=46).grid(row=4, column=1, sticky="ew", pady=4)
        # Modem preset — affichage lisible, stockage entier
        ttk.Label(frm, text="Modem preset :", font=("Arial", 9)).grid(
            row=5, column=0, sticky="w", padx=(0, 10), pady=4)
        v_modem = tk.StringVar(value=_modem_label_from_int(lora.get("modem_preset", 0)))
        ttk.Combobox(frm, textvariable=v_modem, values=_modem_labels(),
                     state="readonly", width=46).grid(row=5, column=1, sticky="ew", pady=4)

        # Canaux 0 et 1
        ttk.Label(frm, text="── Canaux ──", font=("Arial", 9, "bold"),
                  foreground="#333").grid(row=6, column=0, columnspan=2, sticky="w", pady=(8, 2))
        channels = config.get("channels", [])
        def _get_ch_name(idx):
            if isinstance(channels, list) and len(channels) > idx:
                ch = channels[idx]
                if isinstance(ch, dict):
                    s = ch.get("settings", {})
                    return s.get("name", "") if isinstance(s, dict) else ""
            return ""
        v_ch0 = labeled_entry(7, "Nom canal 0 :", _get_ch_name(0))
        v_ch1 = labeled_entry(8, "Nom canal 1 :", _get_ch_name(1))
        ttk.Label(frm, text="(PSK non modifiable ici — utilisez l'app Meshtastic)",
                  font=("Arial", 8), foreground="#888").grid(
                  row=9, column=0, columnspan=2, sticky="w")

        def save_and_close():
            # Apply changes
            if "owner" not in config or not isinstance(config["owner"], dict):
                config["owner"] = {}
            config["owner"]["long_name"]  = v_long.get().strip()
            config["owner"]["short_name"] = v_short.get().strip()
            if "local_config" not in config:
                config["local_config"] = {}
            if "lora" not in config["local_config"] or not isinstance(config["local_config"]["lora"], dict):
                config["local_config"]["lora"] = {}
            config["local_config"]["lora"]["region"]       = _region_int_from_label(v_region.get())
            config["local_config"]["lora"]["modem_preset"] = _modem_int_from_label(v_modem.get())
            if isinstance(channels, list) and channels:
                if "settings" not in channels[0] or not isinstance(channels[0]["settings"], dict):
                    channels[0]["settings"] = {}
                channels[0]["settings"]["name"] = v_ch0.get().strip()
            if isinstance(channels, list) and len(channels) > 1:
                if "settings" not in channels[1] or not isinstance(channels[1]["settings"], dict):
                    channels[1]["settings"] = {}
                channels[1]["settings"]["name"] = v_ch1.get().strip()
            try:
                with open(f, "w", encoding="utf-8") as fp:
                    json.dump(config, fp, indent=2, ensure_ascii=False)
                self.refresh_files()
                self.set_status(f"✓ Champs sauvegardés : {f.name}")
                win.destroy()
            except Exception as e:
                messagebox.showerror("Erreur sauvegarde", str(e))

        btn_frame = ttk.Frame(win)
        btn_frame.pack(fill="x", padx=12, pady=8)
        ttk.Button(btn_frame, text="💾 Sauvegarder", command=save_and_close).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="✖ Annuler", command=win.destroy).pack(side="left", padx=4)

    # ── Gestion fichiers ──────────────────────────────────────────────────────

    def view_file(self):
        f = self._get_selected_file()
        if not f: return
        try:
            content = f.read_text(encoding="utf-8")
        except Exception as e:
            messagebox.showerror("Erreur", str(e)); return
        win = tk.Toplevel(self.root)
        win.title(f"Contenu — {f.name}")
        win.geometry("850x620")
        win.resizable(True, True)
        bar = ttk.Frame(win); bar.pack(fill="x", padx=8, pady=4)
        ttk.Label(bar, text=f.name, font=("Arial", 10, "bold")).pack(side="left")
        ttk.Button(bar, text="✖ Fermer", command=win.destroy).pack(side="right")
        txt = scrolledtext.ScrolledText(win, font=("Courier New", 10), wrap=tk.NONE)
        txt.pack(fill="both", expand=True, padx=8, pady=(0, 4))
        txt.insert(tk.END, content); txt.config(state="disabled")
        hbar = ttk.Scrollbar(win, orient="horizontal", command=txt.xview)
        hbar.pack(fill="x", padx=8, pady=(0, 8))
        txt.config(xscrollcommand=hbar.set)

    def copy_file(self):
        f = self._get_selected_file()
        if not f: return
        now = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest = filedialog.asksaveasfilename(
            title="Copier le fichier", initialdir=str(self.work_dir),
            defaultextension=".json", initialfile=f"{f.stem}_copie_{now}.json",
            filetypes=[("JSON", "*.json"), ("Tous", "*.*")]
        )
        if dest:
            try:
                shutil.copy2(str(f), dest)
                self.refresh_files()
                self.set_status(f"✓ Copié: {Path(dest).name}")
            except Exception as e:
                messagebox.showerror("Erreur copie", str(e))

    def delete_file(self):
        f = self._get_selected_file()
        if not f: return
        if messagebox.askyesno("Confirmer", f"Supprimer {f.name} ?"):
            try:
                f.unlink(); self.refresh_files()
                self.set_status(f"✓ Supprimé: {f.name}")
            except Exception as e:
                messagebox.showerror("Erreur", str(e))


# ─────────────────────────────────────────────────────────────────────────────
# ENTRÉE
# ─────────────────────────────────────────────────────────────────────────────

def main():
    check_dependencies()
    root = tk.Tk()
    MeshtasticApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()