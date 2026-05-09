#!/usr/bin/env python3
"""
Meshtastic Configuration Manager v1.2
Export/Import COMPLET + Profil Flotte (généralisation)
# ============================================================
# Script name   : MESHTASTIC-CONFIGURATION-MANAGER.py
# Author        : ZIFNAB69_fr@yahoo.fr
# Year          : 2026
#
# Licence : Creative Commons Attribution - Pas d'Utilisation
#           Commerciale 4.0 International (CC BY-NC-SA 4.0)
#
# You are free to:
#   - Share — copy and redistribute this material
#   - Adapt — remix, transform, and build upon this material
#
# Under the following terms:
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
        messagebox.showerror("Missing dependencies",
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
            "No COM port detected.\n\nCheck:\n"
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



def _extract_admin_keys(local_node) -> list:
    """
    Extrait les admin_key depuis localConfig.security comme liste de strings base64.
    Format JSON produit : ["D4Xi3qdGihJj1gTo2T6lyw==", "", ""]
    """
    import base64
    try:
        security = local_node.localConfig.security
        raw = list(getattr(security, "admin_key", []) or [])
        result = []
        for k in raw:
            if isinstance(k, bytes):
                result.append(base64.b64encode(k).decode("ascii") if k else "")
            elif isinstance(k, str):
                result.append(k)
            else:
                result.append("")
        return result
    except Exception:
        return []


def _get_security_section(local_node) -> dict:
    """Exporte la section security proprement depuis localConfig.security."""
    import base64
    try:
        sec = local_node.localConfig.security
        pub  = getattr(sec, "public_key",  b"")
        priv = getattr(sec, "private_key", b"")
        return {
            "public_key":            base64.b64encode(pub).decode("ascii")  if isinstance(pub,  bytes) and pub  else "",
            "private_key":           base64.b64encode(priv).decode("ascii") if isinstance(priv, bytes) and priv else "",
            "admin_key":             _extract_admin_keys(local_node),
            "is_managed":            bool(getattr(sec, "is_managed", False)),
            "admin_channel_enabled": bool(getattr(sec, "admin_channel_enabled", False)),
            "serial_enabled":        bool(getattr(sec, "serial_enabled", True)),
            "debug_log_api_enabled": bool(getattr(sec, "debug_log_api_enabled", False)),
        }
    except Exception:
        return {}


def _apply_security_to_node(local_node, section_data: dict) -> str:
    """
    Restaure la section security via del[:] + append() — méthode CLI officielle.
    NE restaure PAS public_key / private_key (identité hardware unique de l'appareil).
    """
    import base64, time
    try:
        sec = local_node.localConfig.security
        msgs = []
        raw_keys = section_data.get("admin_key", [])
        if isinstance(raw_keys, list):
            valid_keys = []
            for k in raw_keys:
                if isinstance(k, str) and k:
                    try:
                        valid_keys.append(base64.b64decode(k))
                    except Exception:
                        pass
            if valid_keys:
                del sec.admin_key[:]
                local_node.writeConfig("security")
                time.sleep(0.5)
                for kb in valid_keys:
                    sec.admin_key.append(kb)
                local_node.writeConfig("security")
                msgs.append(f"{len(valid_keys)} admin_key(s) restaurée(s)")
        for field in ["is_managed", "admin_channel_enabled", "serial_enabled", "debug_log_api_enabled"]:
            if field in section_data:
                try:
                    setattr(sec, field, bool(section_data[field]))
                except Exception:
                    pass
        # Restaurer private_key (backup complet uniquement — absente des profils flotte)
        priv_b64 = section_data.get("private_key", "")
        if priv_b64:
            try:
                sec.private_key = base64.b64decode(priv_b64)
                msgs.append("private_key restored")
            except Exception as e:
                msgs.append(f"private_key failed: {e}")

        local_node.writeConfig("security")
        msgs.append("champs security écrits")
        return "✓ [security] : " + ", ".join(msgs) if msgs else "✓ [security]"
    except Exception as e:
        return f"✗ [security] : {e}"


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

    # owner — méthodes API officielles MeshInterface
    try:
        owner_info  = {"long_name": "", "short_name": "", "hw_model": ""}
        node_id_hex = ""

        # ── Récupérer l'ID du nœud local (= 4 derniers octets adresse MAC) ─
        try:
            my_num = getattr(iface.myInfo, "my_node_num", None) if iface.myInfo else None
            if my_num:
                node_id_hex = f"!{my_num & 0xFFFFFFFF:08x}"
        except Exception:
            pass

        # ── Méthode 1 : getLongName() / getShortName() ─────────────────────
        try:
            ln = iface.getLongName()
            sn = iface.getShortName()
            if ln or sn:
                owner_info["long_name"]  = ln or ""
                owner_info["short_name"] = sn or ""
        except Exception:
            pass

        # ── Méthode 2 : getMyNodeInfo() ────────────────────────────────────
        if not owner_info["long_name"]:
            try:
                ni = iface.getMyNodeInfo()
                if isinstance(ni, dict):
                    u = ni.get("user", {}) or {}
                    owner_info["long_name"]  = u.get("longName",  u.get("long_name",  ""))
                    owner_info["short_name"] = u.get("shortName", u.get("short_name", ""))
                    hw = u.get("hwModel", u.get("hw_model", ""))
                    owner_info["hw_model"]   = str(hw) if hw else ""
                    if not node_id_hex:
                        uid = ni.get("id", "") or u.get("id", "")
                        if uid: node_id_hex = uid
            except Exception:
                pass

        # ── Méthode 3 : getMyUser() ────────────────────────────────────────
        if not owner_info["long_name"]:
            try:
                u = iface.getMyUser()
                if isinstance(u, dict):
                    owner_info["long_name"]  = u.get("longName",  u.get("long_name",  ""))
                    owner_info["short_name"] = u.get("shortName", u.get("short_name", ""))
                    hw = u.get("hwModel", u.get("hw_model", ""))
                    owner_info["hw_model"]   = str(hw) if hw else ""
                    if not node_id_hex:
                        uid = u.get("id", "")
                        if uid: node_id_hex = uid
            except Exception:
                pass

        # ── Méthode 4 : iface.nodes scanné ─────────────────────────────────
        if not owner_info["long_name"]:
            try:
                my_num = getattr(iface.myInfo, "my_node_num", None) if iface.myInfo else None
                nodes  = iface.nodes or {}
                candidates = []
                if my_num:
                    candidates += [nodes.get(my_num), nodes.get(str(my_num)),
                                   nodes.get(f"!{my_num & 0xFFFFFFFF:08x}")]
                for v in nodes.values():
                    if isinstance(v, dict) and v.get("num") == my_num:
                        candidates.append(v)
                for entry in candidates:
                    if isinstance(entry, dict) and entry.get("user"):
                        u = entry["user"]
                        owner_info["long_name"]  = u.get("longName",  u.get("long_name",  ""))
                        owner_info["short_name"] = u.get("shortName", u.get("short_name", ""))
                        hw = u.get("hwModel", u.get("hw_model", ""))
                        owner_info["hw_model"]   = str(hw) if hw else ""
                        if not node_id_hex:
                            uid = entry.get("id", "") or u.get("id", "")
                            if uid: node_id_hex = uid
                        break
            except Exception:
                pass

        # ── Méthode 5 : localNode.metadata ────────────────────────────────
        if not owner_info["long_name"]:
            try:
                meta = getattr(local_node, "metadata", None)
                if meta:
                    ln = getattr(meta, "long_name", None) or getattr(meta, "longName", None)
                    sn = getattr(meta, "short_name", None) or getattr(meta, "shortName", None)
                    if ln: owner_info["long_name"]  = str(ln)
                    if sn: owner_info["short_name"] = str(sn)
            except Exception:
                pass

        # ── short_name : ajouter suffixe 4 derniers hex de l'ID nœud ──────
        # Format Meshtastic réel : "JMC_5F7B" (partie user + "_" + 4 hex MAC)
        if owner_info["short_name"] and node_id_hex:
            try:
                hex_part = node_id_hex.lstrip("!").upper()[-4:]   # "5F7B"
                sn_base  = owner_info["short_name"].split("_")[0]  # sans suffixe existant
                owner_info["short_name"] = f"{sn_base}_{hex_part}"
            except Exception:
                pass

        # ── hw_model : convertir int enum → nom lisible ────────────────────
        if owner_info["hw_model"] in ("", "0", "UNSET", 0):
            try:
                from meshtastic import mesh_pb2
                my_num = getattr(iface.myInfo, "my_node_num", None) if iface.myInfo else None
                nodes  = iface.nodes or {}
                hw_raw = None
                for v in nodes.values():
                    if isinstance(v, dict) and v.get("num") == my_num:
                        hw_raw = (v.get("user") or {}).get("hwModel",
                                 (v.get("user") or {}).get("hw_model"))
                        break
                if hw_raw is None:
                    try:
                        ni2 = iface.getMyNodeInfo()
                        hw_raw = (ni2.get("user", {}) or {}).get("hwModel") if isinstance(ni2, dict) else None
                    except Exception:
                        pass
                if hw_raw is not None:
                    try:
                        owner_info["hw_model"] = mesh_pb2.HardwareModel.Name(int(hw_raw))
                    except Exception:
                        owner_info["hw_model"] = str(hw_raw)
            except Exception:
                pass

        config["owner"] = owner_info
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

    # security — exportée séparément (repeated bytes mal gérés par MessageToDict)
    try:
        config["local_config"]["security"] = _get_security_section(local_node)
    except Exception:
        pass

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

    # security : traitement spécial (repeated bytes, pas de ParseDict)
    if section_name == "security":
        return _apply_security_to_node(local_node, section_data)

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
    for section in ["device", "position", "power", "network", "display", "lora", "bluetooth", "security"]:
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

    # Normalize to list of (index, entry_dict) regardless of exported structure
    # Dict format: {"0": {...}, "1": {...}}  ← produced by proto_to_dict
    # List format: [{index:0, ...}, {index:1, ...}]  ← alternative format
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
        # Sort: write secondary channels (role=2) first, then primary (role=1) last
        # Writing primary last prevents firmware from resetting it
        ch_entries_sorted = sorted(ch_entries, key=lambda x: (x[1].get("role", 0) == 1, x[0]))

        for ch_index, entry in ch_entries_sorted:
            role_val = entry.get("role", 0)
            settings = entry.get("settings", {}) or {}
            ch_name  = settings.get("name", "")

            # ── Build full Channel protobuf object ──────────────────────────
            try:
                if channel_pb2:
                    ch_obj = channel_pb2.Channel()
                    ch_obj.index = ch_index

                    # Rôle
                    if role_val in (1, 2):
                        ch_obj.role = role_val
                    else:
                        ch_obj.role = 0  # DISABLED

                    # Nom
                    ch_obj.settings.name = ch_name

                    # PSK — hex string → bytes
                    psk_hex = settings.get("psk", "")
                    if psk_hex and psk_hex != "":
                        try:
                            psk_bytes = bytes.fromhex(psk_hex)
                            ch_obj.settings.psk = psk_bytes
                        except Exception as e_psk:
                            log.append(f"⚠ Channel {ch_index} invalid PSK hex: {e_psk}")
                            # Keep existing PSK
                            existing = local_node.getChannelByChannelIndex(ch_index)
                            if existing:
                                ch_obj.settings.psk = existing.settings.psk
                    else:
                        ch_obj.settings.psk = b""

                    # module_settings
                    mod = settings.get("module_settings", {}) or {}
                    if mod:
                        pos_prec = mod.get("position_precision", None)
                        is_muted = mod.get("is_muted", False)
                        if pos_prec is not None:
                            ch_obj.settings.module_settings.position_precision = int(pos_prec)
                        ch_obj.settings.module_settings.is_muted = bool(is_muted)

                    # Write via setChannel + writeChannel
                    local_node.channels[ch_index] = ch_obj
                    local_node.writeChannel(ch_index)

                    psk_info = f"{len(ch_obj.settings.psk)}o" if ch_obj.settings.psk else "vide"
                    status = "DISABLED" if role_val == 0 else f"'{ch_name}'"
                    log.append(f"✓ Channel {ch_index} {status} PSK={psk_info}")

                else:
                    # Fallback without channel_pb2 — legacy method
                    existing = local_node.getChannelByChannelIndex(ch_index)
                    if existing is None:
                        log.append(f"⚠ Channel {ch_index} not found")
                        continue
                    existing.settings.name = ch_name
                    existing.role = role_val if role_val in (1, 2) else 0
                    psk_hex = settings.get("psk", "")
                    if psk_hex:
                        try:
                            existing.settings.psk = bytes.fromhex(psk_hex)
                        except Exception:
                            pass
                    local_node.channels[ch_index] = existing
                    local_node.writeChannel(ch_index)
                    log.append(f"✓ Channel {ch_index} written (fallback)")

            except Exception as e:
                log.append(f"✗ Channel {ch_index}: {e}")
    else:
        log.append("– Channels: no channel data in file")

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
        self.root.title("Meshtastic Config Manager v1.2")
        self.root.geometry("840x900")
        self.root.resizable(True, True)
        self.work_dir = APP_DIR
        self._build_ui()
        self.refresh_files()
        # Détecter automatiquement les ports au démarrage (COM1 exclu)
        self.root.after(200, self.detect_ports)

    def _build_ui(self):
        root = self.root
        # ── En-tête global ────────────────────────────────────────────────────
        ttk.Label(root, text="Meshtastic Config Manager v1.2",
                  font=("Arial", 15, "bold")).pack(pady=(15, 2))
        ttk.Label(root, text="Backup, Restore & Fleet Profile",
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
        df = ttk.LabelFrame(root, text="  📂 Working directory  ", padding=8)
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
        ttk.Label(row, text="COM Port:").pack(side="left")
        self.port_var = tk.StringVar(value="")
        self.port_combo = ttk.Combobox(row, textvariable=self.port_var, width=12)
        self.port_combo.pack(side="left", padx=6)
        ttk.Button(row, text="🔍 Detect ports", command=self.detect_ports).pack(side="left", padx=4)
        ttk.Label(row, text="(empty = auto scan)", foreground="#888", font=("Arial", 8)).pack(side="left", padx=6)

        # Export
        ef = ttk.LabelFrame(root, text="  📤 Export — Read configuration from device  ", padding=8)
        ef.pack(padx=20, pady=6, fill="x")
        tk.Button(ef, text="📤 EXPORT FULL CONFIG → JSON",
                  command=self.export_config,
                  background="#cce0ff", activebackground="#99c2ff",
                  relief="raised", font=("Arial", 9, "bold")).pack(fill="x", ipady=6)
        ttk.Button(ef, text="📤 Multi-node export (sequential)",
                   command=self.export_multi_nodes).pack(fill="x", ipady=3, pady=(3, 0))
        ttk.Label(ef,
            text="Sauvegarde : owner · LoRa · BT · réseau · position · puissance · modules · canaux · nœuds connus",
            font=("Arial", 8), foreground="#666").pack(anchor="w", pady=(3, 0))

        # Liste fichiers — Treeview tabulaire
        lf = ttk.LabelFrame(root, text="  🗃️ JSON backup files  ", padding=8)
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
        ttk.Button(br, text="🔄 Refresh",         command=self.refresh_files).pack(side="left", padx=3)
        ttk.Button(br, text="👁️ View content",       command=self.view_file).pack(side="left", padx=3)
        ttk.Button(br, text="✏️ Edit key fields", command=self.edit_config_fields).pack(side="left", padx=3)
        ttk.Button(br, text="📋 Copy file",     command=self.copy_file).pack(side="left", padx=3)
        ttk.Button(br, text="🗑️ Delete",          command=self.delete_file).pack(side="left", padx=3)
        ttk.Button(br, text="📂 Browse for file…", command=self.import_browse).pack(side="left", padx=(12, 3))

        # Profil flotte
        ff = ttk.LabelFrame(root, text="  🚀 Fleet Profile — Generate a deployable config  ", padding=8)
        ff.pack(padx=20, pady=4, fill="x")
        ttk.Button(ff, text="🚀 GENERATE FLEET PROFILE from selected file",
                   command=self.generate_fleet_profile).pack(fill="x", ipady=6)
        ttk.Label(ff,
            text="Removes: unique keys (pub/priv) · identifiers · nodes · owner · firmware\n"
                 "Keeps: admin_key · LoRa · channels (PSK) · modules · network · display · BT",
            font=("Arial", 8), foreground="#003388").pack(anchor="w", pady=(3, 0))

        # Import
        imf = ttk.LabelFrame(root, text="  📥 Import — Restore configuration to device  ", padding=8)
        imf.pack(padx=20, pady=6, fill="x")
        btn_restore = tk.Button(imf, text="📥 RESTORE selected file → Device",
                   command=self.import_selected,
                   background="#cce0ff", activebackground="#99c2ff",
                   relief="raised", font=("Arial", 9, "bold"))
        btn_restore.pack(fill="x", ipady=6)
        ttk.Button(imf, text="📥 Multi-node import (deploy one file to multiple devices)",
                   command=self.import_multi_nodes).pack(fill="x", ipady=3, pady=(3, 0))

        # Status bar
        self.status_var = tk.StringVar(value="Ready.")
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

        ttk.Label(inner, text="📖  Guide d'utilisation — Meshtastic Config Manager v1.2",
                  font=("Arial", 12, "bold"), foreground="#001f66").pack(
                  anchor="w", padx=6, pady=(8, 2))
        ttk.Label(inner,
                  text="This tool allows you to export, back up and restore the configuration "
                       "de noeuds Meshtastic (T-Echo, ESP32 V3) via USB.",
                  wraplength=680, justify="left", font=("Arial", 9),
                  foreground="#444").pack(anchor="w", padx=6, pady=(0, 4))

        section("Prerequis")
        para("* Python 3.8+  +  packages :  pip install meshtastic pyserial sauf si utilisé en EXE")
        para("* Cable USB DATA (pas un cable de charge uniquement)")
        para("* Pilotes USB installes : CP210x (Silicon Labs) ou CH340 selon le modele")
        para("* Appareil Meshtastic allume en mode normal (pas en mode DFU/bootloader)")

        section("Working directory")
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

        section("Import multi-noeuds (deploiement en serie)")
        para("Deploie le fichier selectionne dans la liste sur plusieurs appareils successivement.")
        step(1, "Selectionnez le fichier JSON cible dans la liste des fichiers.")
        step(2, "Cliquez sur IMPORT MULTI-NOEUDS.")
        step(3, "Pour chaque appareil : branchez-le, selectionnez son port (COM1 exclu), cliquez Restaurer.")
        step(4, "Cliquez Terminer quand tous les noeuds sont traites.")
        para("Note : COM1 est automatiquement exclu de la detection (port systeme Windows).")
        para("Note : le fichier selectionne est identique pour tous les noeuds. Pour un profil flotte,")
        para("  les cles privees/publiques ne seront pas restaurees — chaque noeud garde les siennes.")

        section("Verification d'integrite")
        para("Avant toute restauration, le fichier est automatiquement valide :")
        para("* Presence de local_config et local_config.lora")
        para("* Presence de la section channels")
        para("* Coherence de la config LoRa (region, modem_preset)")
        para("En cas de probleme, un avertissement s'affiche — vous pouvez annuler ou forcer.")

        section("Conseils et bonnes pratiques")
        para("* Nommez vos fichiers explicitement : meshtastic_backup_specialevent_2025.json")
        para("* Exportez toujours AVANT de modifier ou d'appliquer un profil flotte.")
        para("* Les profils flotte peuvent etre partages entre membres d'une meme equipe.")
        para("* Si export echoue avec Timeout : debranchez/rebranchez le cable et reessayez.")
        para("* Sous Windows : verifiez Gestionnaire de peripheriques > Ports (COM et LPT).")
        para("* Le fichier JSON est lisible et editable manuellement avec un editeur de texte.")

        ttk.Separator(inner, orient="horizontal").pack(fill="x", pady=(10, 4))
        ttk.Label(inner, text="Meshtastic Config Manager v1.2",
                  font=("Arial", 8), foreground="#aaa").pack(anchor="e", padx=8, pady=4)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def set_status(self, msg):
        self.status_var.set(msg)
        self.root.update_idletasks()

    def detect_ports(self):
        all_ports = list_serial_ports()
        # COM1 is the Windows system serial port (mouse/BIOS), never a USB device
        EXCLUDED = {"COM1", "com1"}
        ports = [p for p in all_ports if p not in EXCLUDED]
        self.port_combo["values"] = ports
        if ports:
            self.port_combo.set(ports[0])
            excluded_note = f" (COM1 excluded)" if len(all_ports) != len(ports) else ""
            self.set_status(f"✓ {len(ports)} port(s): {', '.join(ports)}{excluded_note}")
        elif all_ports:
            # Uniquement COM1 disponible — on l'affiche mais on avertit
            self.port_combo["values"] = all_ports
            self.port_combo.set("")
            self.set_status("⚠ Only COM1 detected — connect your USB device")
        else:
            self.set_status("⚠ No COM port — check USB cable")

    def choose_work_dir(self):
        s = filedialog.askdirectory(title="Working directory", initialdir=str(self.work_dir))
        if s:
            self.work_dir = Path(s)
            self.dir_var.set(str(self.work_dir))
            self.refresh_files()
            self.set_status(f"✓ Directory: {self.work_dir}")

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
                type_label = "🚀 Fleet" if tag == "fleet" else "💾 Backup"
                iid = self.tree.insert("", "end",
                    values=(type_label, p.name, meta["hw_model"],
                            meta["ch_name"], meta["ch1_name"], meta["date"]),
                    tags=(tag,))
                self._file_map[iid] = p
            self.set_status(f"✓ {len(paths)} file(s) in {self.work_dir.name}")
        except Exception as e:
            self.set_status(f"✗ {e}")

    def open_folder(self):
        try:
            os.startfile(str(self.work_dir))
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def _get_selected_file(self) -> Optional[Path]:
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("No selection", "Select a file from the list.")
            return None
        return self._file_map.get(sel[0])

    # ── Export ────────────────────────────────────────────────────────────────

    def export_config(self):
        self.set_status("⏳ Connecting to device…")

        def do_export():
            iface = None
            try:
                iface = connect_device(self.port_var.get().strip() or None)
                self.root.after(0, lambda: self.set_status("⏳ Reading config…"))
                config = export_full_config(iface)

                # Nom de fichier suggéré avec short_name (ex: JMC_5F7B)
                now      = datetime.now().strftime("%Y%m%d_%H%M%S")
                owner    = config.get("owner", {}) if isinstance(config.get("owner"), dict) else {}
                sn_raw   = owner.get("short_name", "") or owner.get("long_name", "")
                sn_slug  = "".join(c if c.isalnum() or c in "-_" else "_" for c in sn_raw).strip("_")
                suggest  = f"meshtastic_{sn_slug}_{now}.json" if sn_slug else f"meshtastic_backup_{now}.json"

                def ask_and_save():
                    filename = filedialog.asksaveasfilename(
                        title="Save full configuration",
                        initialdir=str(self.work_dir),
                        defaultextension=".json",
                        initialfile=suggest,
                        filetypes=[("JSON", "*.json"), ("Tous", "*.*")]
                    )
                    if not filename:
                        self.set_status("Export annulé.")
                        return
                    try:
                        with open(filename, "w", encoding="utf-8") as f:
                            json.dump(config, f, indent=2, ensure_ascii=False, default=str)
                        self.work_dir = Path(filename).resolve().parent
                        self.dir_var.set(str(self.work_dir))
                        self.refresh_files()
                        self.set_status(f"✓ {Path(filename).name}")
                        messagebox.showinfo("Export successful ✓",
                            f"Full configuration saved:\n{filename}")
                    except Exception as e:
                        messagebox.showerror("Save error", str(e))

                self.root.after(0, ask_and_save)

            except Exception as e:
                err = str(e)
                self.root.after(0, lambda: self.set_status("✗ Export failed"))
                self.root.after(0, lambda: messagebox.showerror("Export error", err))
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
            title="Save fleet profile",
            initialdir=str(self.work_dir),
            defaultextension=".json",
            initialfile=f"fleet_profile_{now}.json",
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
            messagebox.showinfo("Fleet profile created ✓",
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
            messagebox.showerror("Error", str(e))

    # ── Import ────────────────────────────────────────────────────────────────

    def _do_import(self, filename: str):
        file_path = Path(filename)
        if not file_path.exists():
            messagebox.showerror("File not found", str(filename)); return
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
                "⚠ Integrity warnings",
                f"Le fichier présente les problèmes suivants :\n\n{warn_text}\n\n"
                "Continuer quand même la restauration ?"
            ):
                return

        profile_type = config.get("_profile_type", "complet")
        export_date  = config.get("_export_date", config.get("_profile_date", "inconnue"))
        owner = config.get("owner", {})
        ln = owner.get("long_name", "Non défini (profil flotte)") if isinstance(owner, dict) else "?"
        type_label = "⚡ FLEET PROFILE" if profile_type == "fleet" else "📦 Full backup"

        if not messagebox.askyesno("Confirm restore",
            f"Fichier : {file_path.name}\n"
            f"Type    : {type_label}\n"
            f"Date    : {export_date}\n"
            f"Source  : {ln}\n\n"
            "⚠ This will overwrite the current device config.\n\nContinue?"):
            return

        self.set_status(f"⏳ Restoring {file_path.name}…")

        def do_import():
            iface = None
            try:
                iface = connect_device(self.port_var.get().strip() or None)
                self.root.after(0, lambda: self.set_status("⏳ Applying config…"))
                log_lines = import_full_config(iface, config)
                log_text = "\n".join(log_lines)
                self.root.after(0, lambda: self.set_status(f"✓ Restored: {file_path.name}"))
                self.root.after(0, lambda: messagebox.showinfo("Import successful ✓",
                    f"Config restored:\n{filename}\n\n{log_text}\n\n"
                    "⚠ Restart the device to apply changes."))
            except Exception as e:
                err = str(e)
                self.root.after(0, lambda: self.set_status("✗ Import failed"))
                self.root.after(0, lambda: messagebox.showerror("Import error", err))
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
            title="Select a config file",
            initialdir=str(self.work_dir),
            filetypes=[("JSON/YAML", "*.json *.yaml *.yml"), ("Tous", "*.*")]
        )
        if fn: self._do_import(fn)


    # ── Export multi-nœuds ────────────────────────────────────────────────────

    def export_multi_nodes(self):
        """Export séquentiel de plusieurs nœuds. Port sélectionnable à chaque étape."""
        import serial.tools.list_ports as _lp

        def _ask_and_export(count):
            """Boîte de dialogue personnalisée avec sélecteur de port intégré."""
            win = tk.Toplevel(self.root)
            win.title(f"Multi-node export — node #{count + 1}")
            win.geometry("420x200")
            win.resizable(False, False)
            win.grab_set()

            ttk.Label(win,
                text=f"{'Connect' if count == 0 else 'Reconnect'} node #{count + 1} to USB.",
                font=("Arial", 10)).pack(pady=(16, 4), padx=16, anchor="w")

            row = ttk.Frame(win); row.pack(padx=16, pady=4, fill="x")
            ttk.Label(row, text="COM Port:").pack(side="left")
            ports = [p.device for p in sorted(_lp.comports()) if p.device not in {"COM1","com1"}]
            port_var = tk.StringVar(value=ports[0] if ports else "")
            cb = ttk.Combobox(row, textvariable=port_var, values=ports, width=12)
            cb.pack(side="left", padx=6)
            def refresh_ports():
                p2 = [p.device for p in sorted(_lp.comports()) if p.device not in {"COM1","com1"}]
                cb["values"] = p2
                if p2: port_var.set(p2[0])
            ttk.Button(row, text="🔍 Detect", command=refresh_ports).pack(side="left", padx=4)
            ttk.Label(row, text="(empty = auto scan)", foreground="#888",
                      font=("Arial", 8)).pack(side="left", padx=4)

            result = {"action": None, "port": ""}
            def do_export():
                result["action"] = "export"
                result["port"]   = port_var.get().strip()
                win.destroy()
            def do_stop():
                result["action"] = "stop"
                win.destroy()
            def do_skip():
                result["action"] = "skip"
                win.destroy()

            btn_row = ttk.Frame(win); btn_row.pack(pady=12)
            tk.Button(btn_row, text="📤 Export this node", command=do_export,
                      background="#cce0ff", font=("Arial", 9, "bold")).pack(side="left", padx=6)
            ttk.Button(btn_row, text="⏭ Skip", command=do_skip).pack(side="left", padx=4)
            ttk.Button(btn_row, text="🛑 Finish", command=do_stop).pack(side="left", padx=4)

            win.wait_window()
            return result

        count = 0
        while True:
            res = _ask_and_export(count)
            if res["action"] == "stop" or res["action"] is None:
                self.set_status(f"✓ Session complete — {count} node(s) exported")
                if count > 0:
                    messagebox.showinfo("Session complete",
                        f"{count} node(s) exported successfully.")
                break
            if res["action"] == "skip":
                continue

            # Connexion + lecture config
            self.set_status(f"⏳ Connecting to node #{count + 1}…")
            try:
                iface = connect_device(res["port"] or None)
                config = export_full_config(iface)
                iface.close()
            except Exception as e:
                messagebox.showerror(f"Connection error — node #{count + 1}", str(e))
                continue

            # Nom suggéré avec short_name (ex: JMC_5F7B)
            now     = datetime.now().strftime("%Y%m%d_%H%M%S")
            owner   = config.get("owner", {}) if isinstance(config.get("owner"), dict) else {}
            sn_raw  = owner.get("short_name", "") or owner.get("long_name", "")
            sn_slug = "".join(c if c.isalnum() or c in "-_" else "_" for c in sn_raw).strip("_")
            suggest = f"meshtastic_{sn_slug}_{now}.json" if sn_slug else f"meshtastic_node{count+1:02d}_{now}.json"

            filename = filedialog.asksaveasfilename(
                title=f"Save node #{count + 1} — {ln_raw or '?'}",
                initialdir=str(self.work_dir),
                defaultextension=".json",
                initialfile=suggest,
                filetypes=[("JSON", "*.json"), ("Tous", "*.*")]
            )
            if not filename:
                continue

            try:
                with open(filename, "w", encoding="utf-8") as f:
                    json.dump(config, f, indent=2, ensure_ascii=False, default=str)
                self.work_dir = Path(filename).resolve().parent
                self.dir_var.set(str(self.work_dir))
                self.refresh_files()
                count += 1
                self.set_status(f"✓ Node #{count} exported: {Path(filename).name}")
            except Exception as e:
                messagebox.showerror(f"Save error — node #{count + 1}", str(e))


    def import_multi_nodes(self):
        """Import séquentiel du même fichier JSON vers plusieurs nœuds.
        Utilise le fichier sélectionné dans l'UI (même logique que restauration unique)."""
        import serial.tools.list_ports as _lp

        # Utiliser le fichier sélectionné dans l'UI — même comportement que import_selected
        file_path = self._get_selected_file()
        if not file_path:
            messagebox.showwarning("Aucun fichier sélectionné",
                "Please select a JSON file from the file list first.")
            return
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                config = json.load(f)
        except Exception as e:
            messagebox.showerror("Fichier invalide", str(e)); return

        # Vérification intégrité une seule fois
        warns = validate_config_integrity(config)
        if warns:
            if not messagebox.askyesno("⚠ Integrity warnings",
                "\n".join(warns) + "\n\nContinue anyway?"):
                return

        profile_type = config.get("_profile_type", "complet")
        type_label   = "⚡ FLEET PROFILE" if profile_type == "fleet" else "📦 Full backup"

        def _ask_and_import(count):
            win = tk.Toplevel(self.root)
            win.title(f"Multi-node import — node #{count + 1}")
            win.geometry("440x220")
            win.resizable(False, False)
            win.grab_set()

            ttk.Label(win,
                text=f"Connect node #{count + 1} and select its port.",
                font=("Arial", 10)).pack(pady=(16, 2), padx=16, anchor="w")
            ttk.Label(win,
                text=f"Fichier : {file_path.name}  |  Type : {type_label}",
                font=("Arial", 8), foreground="#444").pack(padx=16, anchor="w")

            row = ttk.Frame(win); row.pack(padx=16, pady=6, fill="x")
            ttk.Label(row, text="COM Port:").pack(side="left")
            ports = [p.device for p in sorted(_lp.comports()) if p.device not in {"COM1","com1"}]
            port_var = tk.StringVar(value=ports[0] if ports else "")
            cb = ttk.Combobox(row, textvariable=port_var, values=ports, width=12)
            cb.pack(side="left", padx=6)
            def refresh_ports():
                p2 = [p.device for p in sorted(_lp.comports()) if p.device not in {"COM1","com1"}]
                cb["values"] = p2
                if p2: port_var.set(p2[0])
            ttk.Button(row, text="🔍 Detect", command=refresh_ports).pack(side="left", padx=4)
            ttk.Label(row, text="(empty = auto scan)", foreground="#888",
                      font=("Arial", 8)).pack(side="left", padx=4)

            result = {"action": None, "port": ""}
            def do_import():
                result["action"] = "import"
                result["port"]   = port_var.get().strip()
                win.destroy()
            def do_stop():
                result["action"] = "stop"
                win.destroy()
            def do_skip():
                result["action"] = "skip"
                win.destroy()

            btn_row = ttk.Frame(win); btn_row.pack(pady=10)
            tk.Button(btn_row, text="📥 Restore this node", command=do_import,
                      background="#cce0ff", font=("Arial", 9, "bold")).pack(side="left", padx=6)
            ttk.Button(btn_row, text="⏭ Skip", command=do_skip).pack(side="left", padx=4)
            ttk.Button(btn_row, text="🛑 Finish", command=do_stop).pack(side="left", padx=4)

            win.wait_window()
            return result

        count = 0
        errors = 0
        while True:
            res = _ask_and_import(count)
            if res["action"] == "stop" or res["action"] is None:
                self.set_status(f"✓ Session complete — {count} node(s) restored")
                if count > 0:
                    messagebox.showinfo("Session complete",
                        f"{count} node(s) restored successfully.\n"
                        f"{errors} error(s).\n\n"
                        "⚠ Restart each device to apply changes.")
                break
            if res["action"] == "skip":
                continue

            self.set_status(f"⏳ Restoring node #{count + 1}…")
            try:
                iface = connect_device(res["port"] or None)
                log_lines = import_full_config(iface, config)
                iface.close()
                count += 1
                self.set_status(f"✓ Node #{count} restored")
                messagebox.showinfo(f"Node #{count} restored ✓",
                    "\n".join(log_lines) +
                    "\n\n⚠ Restart the device to apply changes.")
            except Exception as e:
                errors += 1
                messagebox.showerror(f"Node #{count + 1} error", str(e))

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
        v_long  = labeled_entry(1, "Long name:", owner.get("long_name", ""))
        v_short = labeled_entry(2, "Short name:", owner.get("short_name", ""))

        # LoRa
        ttk.Label(frm, text="── LoRa ──", font=("Arial", 9, "bold"),
                  foreground="#333").grid(row=3, column=0, columnspan=2, sticky="w", pady=(8, 2))
        lora = config.get("local_config", {}).get("lora", {}) or {}
        # Région — affichage lisible, stockage entier
        ttk.Label(frm, text="LoRa region:", font=("Arial", 9)).grid(
            row=4, column=0, sticky="w", padx=(0, 10), pady=4)
        v_region = tk.StringVar(value=_region_label_from_int(lora.get("region", 0)))
        ttk.Combobox(frm, textvariable=v_region, values=_region_labels(),
                     state="readonly", width=46).grid(row=4, column=1, sticky="ew", pady=4)
        # Modem preset — affichage lisible, stockage entier
        ttk.Label(frm, text="Modem preset:", font=("Arial", 9)).grid(
            row=5, column=0, sticky="w", padx=(0, 10), pady=4)
        v_modem = tk.StringVar(value=_modem_label_from_int(lora.get("modem_preset", 0)))
        ttk.Combobox(frm, textvariable=v_modem, values=_modem_labels(),
                     state="readonly", width=46).grid(row=5, column=1, sticky="ew", pady=4)

        # Canaux 0 et 1
        ttk.Label(frm, text="── Channels ──", font=("Arial", 9, "bold"),
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
        ttk.Label(frm, text="(PSK cannot be edited here — use the Meshtastic app)",
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
                self.set_status(f"✓ Fields saved: {f.name}")
                win.destroy()
            except Exception as e:
                messagebox.showerror("Save error", str(e))

        btn_frame = ttk.Frame(win)
        btn_frame.pack(fill="x", padx=12, pady=8)
        ttk.Button(btn_frame, text="💾 Save", command=save_and_close).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="✖ Cancel", command=win.destroy).pack(side="left", padx=4)

    # ── Gestion fichiers ──────────────────────────────────────────────────────

    def view_file(self):
        f = self._get_selected_file()
        if not f: return
        try:
            content = f.read_text(encoding="utf-8")
        except Exception as e:
            messagebox.showerror("Error", str(e)); return
        win = tk.Toplevel(self.root)
        win.title(f"Content — {f.name}")
        win.geometry("850x620")
        win.resizable(True, True)
        bar = ttk.Frame(win); bar.pack(fill="x", padx=8, pady=4)
        ttk.Label(bar, text=f.name, font=("Arial", 10, "bold")).pack(side="left")
        ttk.Button(bar, text="✖ Close", command=win.destroy).pack(side="right")
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
            title="Copy file", initialdir=str(self.work_dir),
            defaultextension=".json", initialfile=f"{f.stem}_copie_{now}.json",
            filetypes=[("JSON", "*.json"), ("Tous", "*.*")]
        )
        if dest:
            try:
                shutil.copy2(str(f), dest)
                self.refresh_files()
                self.set_status(f"✓ Copied: {Path(dest).name}")
            except Exception as e:
                messagebox.showerror("Copy error", str(e))

    def delete_file(self):
        f = self._get_selected_file()
        if not f: return
        if messagebox.askyesno("Confirm", f"Delete {f.name}?"):
            try:
                f.unlink(); self.refresh_files()
                self.set_status(f"✓ Deleted: {f.name}")
            except Exception as e:
                messagebox.showerror("Error", str(e))


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