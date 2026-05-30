#!/usr/bin/env python3
"""
Nodes Backup & Fleet Manager v1.75
Export/Import COMPLET + Profil Flotte (généralisation)
# ============================================================
# Nom du script : NODES-BACKUP-FLEET-MANAGER.py
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
        raise Exception(tr("conn_no_com"))
    last_error = None
    for p in ports_to_try:
        try:
            iface = meshtastic.serial_interface.SerialInterface(devPath=p)
            waited = 0
            while not getattr(iface, "isConnected", False) and waited < 8:
                time.sleep(0.5); waited += 0.5
            if not getattr(iface, "isConnected", False):
                iface.close()
                raise Exception(tr("conn_timeout_on_port", port=p))
            return iface
        except Exception as e:
            last_error = e
    raise Exception(
        tr("conn_failed_on_ports", ports=", ".join(ports_to_try), error=last_error)
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
                msgs.append("private_key restaurée")
            except Exception as e:
                msgs.append(f"private_key échouée: {e}")

        local_node.writeConfig("security")
        msgs.append("champs security écrits")
        return "✓ [security] : " + ", ".join(msgs) if msgs else "✓ [security]"
    except Exception as e:
        return f"✗ [security] : {e}"


def export_full_config(iface) -> Dict[str, Any]:
    config = {"_export_date": datetime.now().isoformat(), "_app_version": "2.6"}
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
        # Trier : écrire d'abord les canaux secondaires (role=2), puis le primaire (role=1)
        # Le canal primaire écrit en dernier évite que le firmware le réinitialise
        ch_entries_sorted = sorted(ch_entries, key=lambda x: (x[1].get("role", 0) == 1, x[0]))

        for ch_index, entry in ch_entries_sorted:
            role_val = entry.get("role", 0)
            settings = entry.get("settings", {}) or {}
            ch_name  = settings.get("name", "")

            # ── Construire l'objet Channel complet via protobuf ────────────
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
                            log.append(f"⚠ Canal {ch_index} PSK hex invalide: {e_psk}")
                            # Garder PSK existante
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

                    # Écrire via setChannel + writeChannel
                    local_node.channels[ch_index] = ch_obj
                    local_node.writeChannel(ch_index)

                    psk_info = f"{len(ch_obj.settings.psk)}o" if ch_obj.settings.psk else "vide"
                    status = "DISABLED" if role_val == 0 else f"'{ch_name}'"
                    log.append(f"✓ Canal {ch_index} {status} PSK={psk_info}")

                else:
                    # Fallback sans channel_pb2 — méthode ancienne
                    existing = local_node.getChannelByChannelIndex(ch_index)
                    if existing is None:
                        log.append(f"⚠ Canal {ch_index} introuvable")
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
                    log.append(f"✓ Canal {ch_index} écrit (fallback)")

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
        warnings.append(tr("integrity_invalid_json"))
        return warnings
    for section, subsections in REQUIRED_SECTIONS.items():
        if section not in config or not config[section]:
            warnings.append(tr("integrity_missing_section", section=section))
        else:
            for sub in subsections:
                val = config[section]
                if isinstance(val, dict) and sub not in val:
                    warnings.append(tr("integrity_missing_subsection", section=section, sub=sub))
    lc = config.get("local_config", {})
    if isinstance(lc, dict):
        lora = lc.get("lora", {})
        if isinstance(lora, dict) and not lora.get("region") and not lora.get("modem_preset"):
            warnings.append(tr("integrity_lora_missing"))
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
        # modem preset
        try:
            mp_int = int(data.get("local_config", {}).get("lora", {}).get("modem_preset", -1))
            MODEM_SHORT = {0:"LongFast",1:"LongSlow",2:"VeryLongSlow",3:"MedSlow",4:"MedFast",5:"ShortSlow",6:"ShortFast",7:"LongMod",8:"ShortTurbo"}
            modem_label = MODEM_SHORT.get(mp_int, f"#{mp_int}" if mp_int >= 0 else "?")
        except Exception:
            modem_label = "?"
        # frequence (override_frequency prioritaire sur frequency)
        try:
            lora_cfg = data.get("local_config", {}).get("lora", {})
            freq = lora_cfg.get("override_frequency") or lora_cfg.get("frequency") or 0
            freq = float(freq)
            if freq > 0:
                # override_frequency est déjà en MHz ; frequency peut être en Hz (>10000) ou MHz
                if freq > 10_000:
                    freq = freq / 1_000_000
                freq_label = f"{freq:.3f}".rstrip("0").rstrip(".") + " MHz"
            else:
                freq_label = "—"
        except Exception:
            freq_label = "?"
        return {
            "tag": tag,
            "long_name": long_name or "?",
            "hw_model": hw_model or "?",
            "ch_name": ch0_name,
            "ch1_name": ch1_name,
            "date": date_short,
            "modem": modem_label,
            "freq": freq_label,
        }
    except Exception:
        return {"tag": "?", "long_name": "?", "hw_model": "?", "ch_name": "?", "ch1_name": "?", "date": "?", "modem": "?", "freq": "?"}

# ─────────────────────────────────────────────────────────────────────────────
# PERSISTANCE LANGUE
# ─────────────────────────────────────────────────────────────────────────────

_CONFIG_PATH = APP_DIR / "NBFM_Config.json"

def load_lang() -> str:
    try:
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f).get("lang", "en")
    except Exception:
        return "en"

def save_lang(lang: str):
    try:
        data = {}
        if _CONFIG_PATH.exists():
            try:
                with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                pass
        data["lang"] = lang
        with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception:
        pass

# ─────────────────────────────────────────────────────────────────────────────
# CHAÎNES UI — FR / EN
# ─────────────────────────────────────────────────────────────────────────────

UI_STRINGS = {
    "fr": {
        "subtitle":          "Sauvegarde, Restauration & Profil Flotte pour noeuds Meshtastic",
        "tab_main":          "  ⚙️  Principal  ",
        "tab_help":          "  ❓  Aide  ",
        "lf_folder":         "  📂 Dossier de sauvegarde  ",
        "btn_choose":        "📁 Choisir",
        "btn_open":          "🗂 Ouvrir",
        "lf_connect":        "  🔌 Connexion appareil  ",
        "lbl_port":          "Port COM :",
        "btn_detect":        "🔍 Détecter ports",
        "lbl_scan":          "(vide = scan auto)",
        "lf_export":         "  📤 Export — Lire la config depuis l'appareil  ",
        "btn_export_1":      "📤 Exporter (1 appareil)",
        "btn_export_multi":  "📤 Export multi-nœuds",
        "lbl_export_hint":   "Sauvegarde : owner · LoRa · BT · réseau · position · puissance · modules · canaux · nœuds connus",
        "lf_files":          "  🗃️ Fichiers de sauvegarde (nbfm)  ",
        "col_type":  "Type",  "col_file":  "Fichier", "col_model": "Modèle",
        "col_modem": "Modem", "col_freq":  "Fréquence", "col_ch0": "Canal 0", "col_ch1": "Canal 1", "col_date": "Date",
        "btn_refresh": "🔄 Actualiser",   "btn_view":   "👁 Voir contenu",
        "btn_edit":    "✏ Éditer champs clés", "btn_copy": "📋 Copier fichier",
        "btn_delete":  "🗑 Supprimer",    "btn_browse": "📂 Choisir un autre fichier…",
        "lf_fleet":    "  🚀 Profil Flotte — Générer une configuration déployable  ",
        "btn_fleet":   "🚀 GÉNÉRER LE PROFIL FLOTTE depuis le fichier sélectionné",
        "lbl_fleet_hint": "Supprime : clés uniques (pub/priv) · identifiants · nœuds · owner · firmware\nConserve : admin_key · LoRa · canaux (PSK) · modules · réseau · display · BT",
        "lf_import":        "  📥 Import — Restaurer la config vers l'appareil  ",
        "btn_restore_1":    "📥 Restaurer (1 appareil)",
        "btn_restore_multi":"📥 Restauration multi-nœuds",
        "status_ready":     "Prêt.",
        "help_title": "📖  Guide d'utilisation — Nodes Backup & Fleet Manager",
        "help_intro": "Cet outil permet d'exporter, sauvegarder et restaurer la configuration de nœuds Meshtastic (T-Echo, ESP32 V3) via USB.",
        "help_sections": [
            ("Prérequis", [
                ("p","* Python 3.8+ + packages : pip install meshtastic pyserial (sauf si EXE)"),
                ("p","* Câble USB DATA (pas un câble de charge uniquement)"),
                ("p","* Pilotes USB installés : CP210x (Silicon Labs) ou CH340 selon le modèle"),
                ("p","* Appareil Meshtastic allumé en mode normal (pas en mode DFU/bootloader)"),
            ]),
            ("Dossier de sauvegarde", [
                ("p","Par défaut, les fichiers NBFM sont enregistrés dans le dossier du script."),
                ("s",(1,"Cliquez sur Choisir pour sélectionner un autre dossier.")),
                ("s",(2,"Cliquez sur Ouvrir pour l'ouvrir dans l'explorateur de fichiers.")),
            ]),
            ("Connexion à l'appareil", [
                ("p","Le champ Port COM permet de cibler un port précis ou de laisser le scan auto."),
                ("s",(1,"Branchez l'appareil en USB.")),
                ("s",(2,"Cliquez sur Détecter ports — le premier port détecté est pré-sélectionné.")),
                ("s",(3,"Laissez le champ vide pour scanner tous les ports automatiquement.")),
                ("p","Si aucun port n'est détecté : vérifiez le câble et les pilotes CP210x / CH340."),
            ]),
            ("Exporter la configuration", [
                ("p","Lit et sauvegarde en JSON l'intégralité de la config de l'appareil connecté."),
                ("s",(1,"Assurez-vous que l'appareil est connecté.")),
                ("s",(2,"Cliquez sur Exporter (1 appareil).")),
                ("s",(3,"Choisissez le nom et l'emplacement du fichier de sauvegarde.")),
                ("s",(4,"Attendez le message de confirmation Export réussi.")),
                ("p","Contenu : owner, LoRa, Bluetooth, réseau, position, puissance, modules, canaux, nœuds."),
            ]),
            ("Export multi-nœuds séquentiel", [
                ("p","Exporte plusieurs nœuds en séquence sans quitter l'application."),
                ("s",(1,"Cliquez sur Export multi-nœuds.")),
                ("s",(2,"Branchez chaque nœud à son tour et confirmez à chaque étape.")),
                ("s",(3,"Cliquez Terminer — un récapitulatif s'affiche.")),
            ]),
            ("Gestion des fichiers de sauvegarde", [
                ("p","La liste affiche : type, modèle, modem, fréquence, canal, date. Triable par clic sur l'en-tête."),
                ("s",(1,"Actualiser — recharge la liste.")),
                ("s",(2,"Voir contenu ou double-clic — ouvre le NBFM en lecture.")),
                ("s",(3,"Copier fichier — duplique le fichier sélectionné.")),
                ("s",(4,"Supprimer — supprime définitivement (confirmation demandée).")),
                ("p","BACKUP = sauvegarde complète (vert)   FLOTTE = profil flotte (bleu)"),
                ("p","La colonne Fréquence affiche override_frequency si définie, sinon la fréquence standard."),
            ]),
            ("Générer un Profil Flotte", [
                ("p","Un profil flotte est une config épurée, déployable sur n'importe quel nœud."),
                ("s",(1,"Sélectionnez un fichier d'export complet dans la liste.")),
                ("s",(2,"Cliquez sur GÉNÉRER PROFIL FLOTTE.")),
                ("s",(3,"Choisissez le nom du fichier de profil flotte.")),
                ("p","SUPPRIMÉ : clé pub/priv, identifiant, owner, nœuds, credentials WiFi, compteurs."),
                ("p","CONSERVÉ : admin_key, LoRa, canaux PSK (0-2), modules, BT, display, position, power."),
            ]),
            ("Éditeur de champs clés", [
                ("p","Modifiez les champs essentiels d'un NBFM sans éditeur externe."),
                ("s",(1,"Sélectionnez un fichier dans la liste.")),
                ("s",(2,"Cliquez sur Éditer les champs clés.")),
                ("s",(3,"Section Owner : modifiez le nom long et le nom court.")),
                ("s",(4,"Section LoRa : choisissez la région et le modem preset dans les listes déroulantes.")),
                ("s",(5,"Section LoRa : saisissez la fréquence override en MHz (laisser vide = pas d'override).")),
                ("s",(6,"Section Canaux : modifiez le nom et la clé PSK (Base64) des canaux 0, 1 et 2.")),
                ("s",(7,"Générateur de clé : choisissez la taille (Défaut / 128 bits / 256 bits), cliquez Générer, copiez la clé depuis le champ résultat.")),
                ("s",(8,"Nettoyage avancé : cochez les suppressions souhaitées (canaux, ADC, nœuds connus).")),
                ("s",(9,"Cliquez Sauvegarder — le fichier NBFM est mis à jour directement.")),
                ("p","Les clés PSK doivent être en Base64, format identique à l'application Meshtastic."),
            ]),
            ("Restaurer la configuration", [
                ("p","Écrit un fichier NBFM vers un appareil connecté."),
                ("s",(1,"Sélectionnez le fichier dans la liste OU Choisir un autre fichier.")),
                ("s",(2,"Cliquez sur Restaurer (1 appareil).")),
                ("s",(3,"Si des avertissements d'intégrité s'affichent, lisez-les avant de confirmer.")),
                ("s",(4,"Attendez le succès, puis REDÉMARREZ l'appareil pour appliquer.")),
                ("p","ATTENTION : la restauration écrase la config actuelle. Exportez avant si besoin !"),
            ]),
            ("Import multi-nœuds (déploiement en série)", [
                ("p","Déploie le fichier sélectionné sur plusieurs appareils successivement."),
                ("s",(1,"Sélectionnez le fichier NBFM cible dans la liste.")),
                ("s",(2,"Cliquez sur Restauration multi-nœuds.")),
                ("s",(3,"Pour chaque appareil : branchez-le, sélectionnez son port (COM1 exclu), cliquez Restaurer.")),
                ("s",(4,"Cliquez Terminer quand tous les nœuds sont traités.")),
                ("p","Note : COM1 est automatiquement exclu (port système Windows)."),
                ("p","Note : pour un profil flotte, les clés privées/publiques ne sont pas restaurées."),
            ]),
            ("Vérification d'intégrité", [
                ("p","Avant toute restauration, le fichier est automatiquement validé :"),
                ("p","* Présence de local_config et local_config.lora"),
                ("p","* Présence de la section channels"),
                ("p","* Cohérence de la config LoRa (région, modem_preset)"),
                ("p","En cas de problème, un avertissement s'affiche — vous pouvez annuler ou forcer."),
            ]),
            ("Conseils et bonnes pratiques", [
                ("p","* Nommez vos fichiers explicitement : meshtastic_backup_festival_2025.NBFM"),
                ("p","* Exportez toujours AVANT de modifier ou d'appliquer un profil flotte."),
                ("p","* Les profils flotte peuvent être partagés entre membres d'une même équipe."),
                ("p","* Si export échoue avec Timeout : débranchez/rebranchez le câble et réessayez."),
                ("p","* Sous Windows : vérifiez Gestionnaire de périphériques > Ports (COM et LPT)."),
                ("p","* Le fichier NBFM est lisible et éditable manuellement avec un éditeur de texte."),
            ]),
            ("Divers", [
                ("p","* Le choix de la langue française génère un fichier NBFM_Config.json permettant la persistance du choix."),
            ]),
        ],
        "edit_title": "✏ Éditer champs clés — {filename}",
        "edit_file": "Fichier : {filename}",
        "edit_owner": "Owner",
        "edit_long_name": "Nom long",
        "edit_short_name": "Nom court",
        "edit_lora": "LoRa",
        "edit_region": "Région",
        "edit_modem": "Modem preset",
        "edit_override_freq": "Fréquence override (MHz)",
        "edit_channels": "Canaux",
        "edit_ch0": "Nom canal 0",
        "edit_ch0_key": "Clé chiffrement canal 0",
        "edit_ch1": "Nom canal 1",
        "edit_ch1_key": "Clé chiffrement canal 1",
        "edit_ch2": "Nom canal 2",
        "edit_ch2_key": "Clé chiffrement canal 2",
        "edit_psk_hint": "Clés en Base64 — format identique à l'application Meshtastic",
        "edit_gen_key": "🎲 Générer clé",
        "edit_gen_key_size": "Taille :",
        "edit_cleanup": "Nettoyage avancé",
        "edit_clear_channels": "Supprimer tous les channels ; garder uniquement Canal 0 par défaut",
        "edit_clear_power": "Supprimer le paramètre ADC",
        "edit_clear_known_nodes": "Supprimer les nœuds connus (known_nodes)",
        "edit_save": "💾 Sauvegarder",
        "edit_save_as": "💾 Enregistrer sous…",
        "edit_cancel": "Annuler",
        "edit_invalid_file": "Fichier invalide",
        "edit_empty_fields": "Champs vides",
        "edit_long_required": "Le nom long ne peut pas être vide.",
        "edit_short_required": "Le nom court ne peut pas être vide.",
        "sel_choose_backup_folder": "Dossier de sauvegarde",
        "sel_save_full_config": "Sauvegarder la config complète",
        "sel_save_fleet_profile": "Enregistrer le profil flotte",
        "sel_choose_config_file": "Choisir un fichier de config",
        "sel_copy_file": "Copier le fichier",
        "sel_save_node": "Sauvegarder nœud #{index} — {name}",
        "sel_no_selection_title": "Aucune sélection",
        "sel_no_selection_text": "Sélectionnez un fichier dans la liste.",
        "sel_no_file_title": "Aucun fichier sélectionné",
        "sel_no_file_text": "Sélectionnez d'abord un fichier NBFM dans la liste des fichiers.",
        "sel_delete_confirm_title": "Confirmer",
        "sel_delete_confirm_text": "Supprimer {filename} ?",
        "multi_export_title": "Export multi-nœuds — nœud #{index}",
        "multi_export_text_first": "Branchez le nœud #{index} sur le port USB.",
        "multi_export_text_next": "Rebranchez le nœud #{index} sur le port USB.",
        "multi_import_title": "Import multi-nœuds — nœud #{index}",
        "multi_import_text": "Branchez le nœud #{index} et sélectionnez son port.",
        "multi_file_line": "Fichier : {filename}  |  Type : {type_label}",
        "multi_detect": "🔍 Détecter",
        "multi_scan_hint": "(vide = scan auto)",
        "multi_export_btn": "📤 Exporter ce nœud",
        "multi_import_btn": "📥 Restaurer ce nœud",
        "multi_skip_btn": "⏭ Passer",
        "multi_finish_btn": "🛑 Terminer",
        "export_error_title": "Erreur export",
        "export_error_no_com": "Aucun port COM détecté. Vérifiez le câble USB ou laissez le champ vide pour le scan auto.",
        "multi_session_done_title": "Session terminée",
        "multi_export_done_text": "{count} nœud(s) exporté(s) avec succès.",
        "multi_import_done_text": "{count} nœud(s) restauré(s) avec succès.\n{errors} erreur(s).\n\n⚠ Redémarrez chaque appareil pour appliquer.",
        "multi_node_connect_error": "Erreur connexion nœud #{index}",
        "multi_node_save_error": "Erreur sauvegarde nœud #{index}",
        "multi_node_error": "Erreur nœud #{index}",
        "multi_node_restored_title": "Nœud #{index} restauré ✓",
        "popup_error_title": "Erreur",
        "popup_invalid_file": "Fichier invalide",
        "popup_file_not_found": "Fichier introuvable",
        "popup_integrity_title": "⚠ Avertissements d'intégrité",
        "popup_integrity_restore_text": "Le fichier présente les problèmes suivants :\n\n{warns}\n\nContinuer quand même la restauration ?",
        "popup_integrity_continue_text": "{warns}\n\nContinuer quand même ?",
        "popup_restore_confirm_title": "Confirmer la restauration",
        "popup_restore_confirm_text": "Fichier : {filename}\nType    : {type_label}\nDate    : {export_date}\nSource  : {source}\n\n⚠ Écrase la config actuelle de l'appareil.\n\nContinuer ?",
        "popup_import_success_title": "Import réussi ✓",
        "popup_import_success_text": "Config restaurée:\n{filename}\n\n{log_text}\n\n⚠ Redémarrez l'appareil pour appliquer.",
        "popup_import_error_title": "Erreur import",
        "popup_export_success_title": "Export réussi ✓",
        "popup_export_success_text": "Config complète sauvegardée :\n{filename}",
        "popup_save_error_title": "Erreur sauvegarde",
        "popup_export_error_title": "Erreur export",
        "popup_fleet_exists_title": "Déjà un profil flotte",
        "popup_fleet_exists_text": "Ce fichier est déjà un profil flotte.\n\nContinuer quand même ?",
        "popup_fleet_created_title": "Profil flotte créé ✓",
        "popup_fleet_created_text": "Fichier créé:\n{dest}\n\nÉléments supprimés (uniques à l'appareil source):\n  ✗ my_info (ID, device_id, firmware)\n  ✗ metadata\n  ✗ owner (nom de l'appareil)\n  ✗ known_nodes (nœuds du mesh)\n  ✗ security.public_key + private_key\n  ✗ network.wifi_ssid + wifi_psk\n  ✗ Compteurs version internes\n\nÉléments conservés (applicables à la flotte):\n  ✓ security.admin_key\n  ✓ Config LoRa (LONG_FAST, fréquence, région…)\n  ✓ Canaux (HellDogs, BackHell avec PSK)\n  ✓ Config Bluetooth, display, position, power\n  ✓ Tous les modules",
        "popup_view_title": "Contenu — {filename}",
        "popup_close": "✖ Fermer",
        "popup_copy_error_title": "Erreur copie",
        "deps_missing_title": "Dépendances manquantes",
        "deps_missing_text": "Installez: pip install meshtastic pyserial Manquant: {missing}",
        "conn_no_com": "Aucun port COM détecté.\nVérifiez:\n  - Câble USB data branché\n  - Drivers CP210x / CH340 installés\n  - Appareil allumé",
        "conn_timeout_on_port": "Timeout sur {port}",
        "conn_failed_on_ports": "Impossible de connecter sur: {ports}\nErreur: {error}\nVérifiez le câble USB data et les drivers.",
        "integrity_invalid_json": "✗ Le fichier n'est pas un objet JSON valide.",
        "integrity_missing_section": "✗ Section manquante ou vide : '{section}'",
        "integrity_missing_subsection": "⚠ Sous-section absente : '{section}.{sub}'",
        "integrity_lora_missing": "⚠ LoRa : région et modem_preset absents — vérifiez la config LoRa",
        "status_ports_found": "✓ {count} port(s): {ports}{excluded_note}",
        "status_only_com1": "⚠ Seul COM1 détecté — branchez l'appareil USB",
        "status_no_com": "⚠ Aucun port COM — vérifiez le câble USB",
        "status_folder": "✓ Dossier: {folder}",
        "status_files_in_dir": "✓ {count} fichier(s) dans {dirname}",
        "status_error": "✗ {error}",
        "status_connecting_device": "⏳ Connexion à l'appareil…",
        "status_reading_config": "⏳ Lecture config…",
        "status_export_cancelled": "Export annulé.",
        "status_export_failed": "✗ Export échoué",
        "status_fleet_created": "✓ Profil flotte créé: {filename}",
        "status_restoring_file": "⏳ Restauration {filename}…",
        "status_applying_config": "⏳ Application config…",
        "status_restored_file": "✓ Restauré: {filename}",
        "status_import_failed": "✗ Import échoué",
        "status_multi_export_done": "✓ Session terminée — {count} nœud(s) exporté(s)",
        "status_connecting_node": "⏳ Connexion nœud #{index}…",
        "status_node_exported": "✓ Nœud #{index} exporté : {filename}",
        "status_multi_import_done": "✓ Session terminée — {count} nœud(s) restauré(s)",
        "status_restoring_node": "⏳ Restauration nœud #{index}…",
        "status_node_restored": "✓ Nœud #{index} restauré",
        "status_file_copied": "✓ Copié: {filename}",
        "status_file_deleted": "✓ Supprimé: {filename}",
        "popup_already_fleet_title": "Déjà un profil flotte",
        "popup_already_fleet_text": "Ce fichier est déjà un profil flotte.\nContinuer quand même ?",
        "popup_session_done_title": "Session terminée",
        "popup_multi_import_done_text": "{count} nœud(s) restauré(s) avec succès.\n{errors} erreur(s).\n\n⚠ Redémarrez chaque appareil pour appliquer.",
        "popup_node_restored_text": "{log_text}\n⚠ Redémarrez l'appareil pour appliquer.",

    },
    "en": {
        "subtitle":          "Backup, Restore & Fleet Profile for Meshtastic Nodes",
        "tab_main":          "  ⚙️  Main  ",
        "tab_help":          "  ❓  Help  ",
        "lf_folder":         "  📂 Backup folder  ",
        "btn_choose":        "📁 Choose",
        "btn_open":          "🗂 Open",
        "lf_connect":        "  🔌 Device connection  ",
        "lbl_port":          "COM port:",
        "btn_detect":        "🔍 Detect ports",
        "lbl_scan":          "(empty = auto scan)",
        "lf_export":         "  📤 Export — Read config from device  ",
        "btn_export_1":      "📤 Export (1 device)",
        "btn_export_multi":  "📤 Multi-node export",
        "lbl_export_hint":   "Saves: owner · LoRa · BT · network · position · power · modules · channels · known nodes",
        "lf_files":          "  🗃️ Backup files (nbfm)  ",
        "col_type":  "Type",    "col_file":  "File",      "col_model": "Model",
        "col_modem": "Modem",   "col_freq":  "Frequency", "col_ch0":   "Channel 0", "col_ch1":   "Channel 1", "col_date": "Date",
        "btn_refresh": "🔄 Refresh",      "btn_view":   "👁 View content",
        "btn_edit":    "✏ Edit key fields", "btn_copy": "📋 Copy file",
        "btn_delete":  "🗑 Delete",       "btn_browse": "📂 Choose another file…",
        "lf_fleet":    "  🚀 Fleet Profile — Generate a deployable configuration  ",
        "btn_fleet":   "🚀 GENERATE FLEET PROFILE from selected file",
        "lbl_fleet_hint": "Removes: unique keys (pub/priv) · IDs · nodes · owner · firmware\nKeeps: admin_key · LoRa · channels (PSK) · modules · network · display · BT",
        "lf_import":        "  📥 Import — Restore config to device  ",
        "btn_restore_1":    "📥 Restore (1 device)",
        "btn_restore_multi":"📥 Multi-node restore",
        "status_ready":     "Ready.",
        "help_title": "📖  User Guide — Nodes Backup & Fleet Manager",
        "help_intro": "This tool allows you to export, backup and restore the configuration of Meshtastic nodes (T-Echo, ESP32 V3) via USB.",
        "help_sections": [
            ("Requirements", [
                ("p","* Python 3.8+ + packages: pip install meshtastic pyserial (not needed for EXE)"),
                ("p","* USB DATA cable (not a charge-only cable)"),
                ("p","* USB drivers installed: CP210x (Silicon Labs) or CH340 depending on the model"),
                ("p","* Meshtastic device powered on in normal mode (not DFU/bootloader mode)"),
            ]),
            ("Backup folder", [
                ("p","By default, NBFM files are saved in the script folder."),
                ("s",(1,"Click Choose to select a different folder.")),
                ("s",(2,"Click Open to open it in the file explorer.")),
            ]),
            ("Device connection", [
                ("p","The COM port field lets you target a specific port or leave auto-scan active."),
                ("s",(1,"Plug the device via USB.")),
                ("s",(2,"Click Detect ports — the first detected port is pre-selected.")),
                ("s",(3,"Leave the field empty to scan all ports automatically.")),
                ("p","If no port is detected: check the cable and CP210x / CH340 drivers."),
            ]),
            ("Export configuration", [
                ("p","Reads and saves the full device configuration to a NBFM file."),
                ("s",(1,"Make sure the device is connected.")),
                ("s",(2,"Click Export (1 device).")),
                ("s",(3,"Choose a name and location for the backup file.")),
                ("s",(4,"Wait for the Export successful confirmation.")),
                ("p","Contents: owner, LoRa, Bluetooth, network, position, power, modules, channels, nodes."),
            ]),
            ("Multi-node sequential export", [
                ("p","Exports multiple nodes in sequence without closing the app."),
                ("s",(1,"Click Multi-node export.")),
                ("s",(2,"Plug each node in turn and confirm at each step.")),
                ("s",(3,"Click Finish — a summary is displayed.")),
            ]),
            ("Backup file management", [
                ("p","The list shows: type, model, modem, frequency, channel, date. Click headers to sort."),
                ("s",(1,"Refresh — reloads the list.")),
                ("s",(2,"View content or double-click — opens the NBFM read-only.")),
                ("s",(3,"Copy file — duplicates the selected file.")),
                ("s",(4,"Delete — permanently deletes (confirmation required).")),
                ("p","BACKUP = full backup (green)   FLEET = fleet profile (blue)"),
                ("p","The Frequency column shows override_frequency if set, otherwise the standard frequency."),
            ]),
            ("Generate a Fleet Profile", [
                ("p","A fleet profile is a trimmed config deployable on any node."),
                ("s",(1,"Select a full export file in the list.")),
                ("s",(2,"Click GENERATE FLEET PROFILE.")),
                ("s",(3,"Choose a name for the fleet profile file.")),
                ("p","REMOVED: pub/priv keys, unique ID, owner, nodes, WiFi credentials, counters."),
                ("p","KEPT: admin_key, LoRa, channels PSK (0-2), modules, BT, display, position, power."),
            ]),
            ("Key fields editor", [
                ("p","Edit key fields of a NBFM file without an external editor."),
                ("s",(1,"Select a file in the list.")),
                ("s",(2,"Click Edit key fields.")),
                ("s",(3,"Owner section: edit the long name and short name.")),
                ("s",(4,"LoRa section: choose region and modem preset from the dropdown lists.")),
                ("s",(5,"LoRa section: enter override frequency in MHz (leave empty = no override).")),
                ("s",(6,"Channels section: edit the name and PSK key (Base64) for channels 0, 1 and 2.")),
                ("s",(7,"Key generator: choose size (Default / 128 bits / 256 bits), click Generate, copy the key from the result field.")),
                ("s",(8,"Advanced cleanup: check desired deletions (channels, ADC, known nodes).")),
                ("s",(9,"Click Save — the NBFM file is updated directly.")),
                ("p","PSK keys must be in Base64 format, identical to the Meshtastic app."),
            ]),
            ("Restore configuration", [
                ("p","Writes a NBFM file to a connected device."),
                ("s",(1,"Select a file in the list OR Choose another file.")),
                ("s",(2,"Click Restore (1 device).")),
                ("s",(3,"If integrity warnings appear, read them before confirming.")),
                ("s",(4,"Wait for success, then RESTART the device to apply.")),
                ("p","WARNING: restoring overwrites the current config. Export first if needed!"),
            ]),
            ("Multi-node import (batch deployment)", [
                ("p","Deploys the selected file to multiple devices sequentially."),
                ("s",(1,"Select the target NBFM file in the list.")),
                ("s",(2,"Click Multi-node restore.")),
                ("s",(3,"For each device: plug it, select its COM port (COM1 excluded), click Restore.")),
                ("s",(4,"Click Finish when all nodes are done.")),
                ("p","Note: COM1 is automatically excluded (Windows system port)."),
                ("p","Note: for a fleet profile, private/public keys are not restored — each node keeps its own."),
            ]),
            ("Integrity check", [
                ("p","Before any restore, the file is automatically validated:"),
                ("p","* Presence of local_config and local_config.lora"),
                ("p","* Presence of the channels section"),
                ("p","* Consistent LoRa config (region, modem_preset)"),
                ("p","If an issue is found, a warning is shown — you can cancel or force."),
            ]),
            ("Tips & best practices", [
                ("p","* Name your files explicitly: meshtastic_backup_festival_2025.NBFM"),
                ("p","* Always export BEFORE modifying or applying a fleet profile."),
                ("p","* Fleet profiles can be shared between team members."),
                ("p","* If export fails with Timeout: unplug/replug the cable and retry."),
                ("p","* On Windows: check Device Manager > Ports (COM & LPT)."),
                ("p","* The NBFM file is readable and manually editable with any text editor."),
            ]),
            ("Miscellaneous", [
            ("p","* Choosing the French language generates an NBFM_Config.json file allowing the choice to persist."),
            ]),
        ],
        "edit_title": "✏ Edit key fields — {filename}",
        "edit_file": "File: {filename}",
        "edit_owner": "Owner",
        "edit_long_name": "Long name",
        "edit_short_name": "Short name",
        "edit_lora": "LoRa",
        "edit_region": "Region",
        "edit_modem": "Modem preset",
        "edit_override_freq": "Override frequency (MHz)",
        "edit_channels": "Channels",
        "edit_ch0": "Channel 0 name",
        "edit_ch0_key": "Channel 0 encryption key",
        "edit_ch1": "Channel 1 name",
        "edit_ch1_key": "Channel 1 encryption key",
        "edit_ch2": "Channel 2 name",
        "edit_ch2_key": "Channel 2 encryption key",
        "edit_psk_hint": "Keys in Base64 — same format as the Meshtastic app",
        "edit_gen_key": "🎲 Generate key",
        "edit_gen_key_size": "Size:",
        "edit_cleanup": "Advanced cleanup",
        "edit_clear_channels": "Remove all channels; keep only default Channel 0",
        "edit_clear_power": "Remove the ADC Multiplier Override setting",
        "edit_clear_known_nodes": "Remove known nodes (known_nodes)",
        "edit_save": "💾 Save",
        "edit_save_as": "💾 Save as…",
        "edit_cancel": "Cancel",
        "edit_invalid_file": "Invalid file",
        "edit_empty_fields": "Empty fields",
        "edit_long_required": "Long name cannot be empty.",
        "edit_short_required": "Short name cannot be empty.",
        "sel_choose_backup_folder": "Backup folder",
        "sel_save_full_config": "Save full configuration",
        "sel_save_fleet_profile": "Save fleet profile",
        "sel_choose_config_file": "Choose a configuration file",
        "sel_copy_file": "Copy file",
        "sel_save_node": "Save node #{index} — {name}",
        "sel_no_selection_title": "No selection",
        "sel_no_selection_text": "Select a file from the list.",
        "sel_no_file_title": "No file selected",
        "sel_no_file_text": "Select a NBFM file first from the file list.",
        "sel_delete_confirm_title": "Confirm",
        "sel_delete_confirm_text": "Delete {filename}?",
        "multi_export_title": "Multi-node export — node #{index}",
        "multi_export_text_first": "Connect node #{index} to the USB port.",
        "multi_export_text_next": "Reconnect node #{index} to the USB port.",
        "multi_import_title": "Multi-node restore — node #{index}",
        "multi_import_text": "Connect node #{index} and select its port.",
        "multi_file_line": "File: {filename}  |  Type: {type_label}",
        "multi_detect": "🔍 Detect",
        "multi_scan_hint": "(empty = auto scan)",
        "multi_export_btn": "📤 Export this node",
        "multi_import_btn": "📥 Restore this node",
        "multi_skip_btn": "⏭ Skip",
        "multi_finish_btn": "🛑 Finish",
        "export_error_title": "Export error",
        "export_error_no_com": "No COM port detected. Check the USB cable or leave the field empty for auto scan.",
        "multi_session_done_title": "Session finished",
        "multi_export_done_text": "{count} node(s) exported successfully.",
        "multi_import_done_text": "{count} node(s) restored successfully.\n{errors} error(s).\n\n⚠ Restart each device to apply changes.",
        "multi_node_connect_error": "Node #{index} connection error",
        "multi_node_save_error": "Node #{index} save error",
        "multi_node_error": "Node #{index} error",
        "multi_node_restored_title": "Node #{index} restored ✓",
        "popup_error_title": "Error",
        "popup_invalid_file": "Invalid file",
        "popup_file_not_found": "File not found",
        "popup_integrity_title": "⚠ Integrity warnings",
        "popup_integrity_restore_text": "The file has the following issues:\n\n{warns}\n\nContinue with restore anyway?",
        "popup_integrity_continue_text": "{warns}\n\nContinue anyway?",
        "popup_restore_confirm_title": "Confirm restore",
        "popup_restore_confirm_text": "File: {filename}\nType    : {type_label}\nDate    : {export_date}\nSource  : {source}\n\n⚠ This will overwrite the device's current configuration.\n\nContinue?",
        "popup_import_success_title": "Import successful ✓",
        "popup_import_success_text": "Configuration restored:\n{filename}\n\n{log_text}\n\n⚠ Restart the device to apply changes.",
        "popup_import_error_title": "Import error",
        "popup_export_success_title": "Export successful ✓",
        "popup_export_success_text": "Full configuration saved:\n{filename}",
        "popup_save_error_title": "Save error",
        "popup_export_error_title": "Export error",
        "popup_fleet_exists_title": "Already a fleet profile",
        "popup_fleet_exists_text": "This file is already a fleet profile.\n\nContinue anyway?",
        "popup_fleet_created_title": "Fleet profile created ✓",
        "popup_fleet_created_text": "File created:\n{dest}\n\nRemoved items (unique to the source device):\n  ✗ my_info (ID, device_id, firmware)\n  ✗ metadata\n  ✗ owner (device name)\n  ✗ known_nodes (mesh nodes)\n  ✗ security.public_key + private_key\n  ✗ network.wifi_ssid + wifi_psk\n  ✗ Internal version counters\n\nKept items (applicable to the fleet):\n  ✓ security.admin_key\n  ✓ LoRa config (LONG_FAST, frequency, region…)\n  ✓ Channels (HellDogs, BackHell with PSK)\n  ✓ Bluetooth, display, position, power config\n  ✓ All modules",
        "popup_view_title": "Content — {filename}",
        "popup_close": "✖ Close",
        "popup_copy_error_title": "Copy error",
        "deps_missing_title": "Missing dependencies",
        "deps_missing_text": "Install:\npip install meshtastic pyserial\n\nMissing: {missing}",
        "conn_no_com": "No COM port detected.\n\nCheck:\n  - USB data cable connected\n  - CP210x / CH340 drivers installed\n  - Device powered on",
        "conn_timeout_on_port": "Timeout on {port}",
        "conn_failed_on_ports": "Unable to connect on: {ports}\n\nError: {error}\n\nCheck the USB data cable and drivers.",
        "integrity_invalid_json": "✗ The file is not a valid JSON object.",
        "integrity_missing_section": "✗ Missing or empty section: '{section}'",
        "integrity_missing_subsection": "⚠ Missing subsection: '{section}.{sub}'",
        "integrity_lora_missing": "⚠ LoRa: region and modem_preset missing — check the LoRa configuration",
        "status_ports_found": "✓ {count} port(s): {ports}{excluded_note}",
        "status_only_com1": "⚠ Only COM1 detected — connect the USB device",
        "status_no_com": "⚠ No COM port — check the USB cable",
        "status_folder": "✓ Folder: {folder}",
        "status_files_in_dir": "✓ {count} file(s) in {dirname}",
        "status_error": "✗ {error}",
        "status_connecting_device": "⏳ Connecting to device…",
        "status_reading_config": "⏳ Reading config…",
        "status_export_cancelled": "Export cancelled.",
        "status_export_failed": "✗ Export failed",
        "status_fleet_created": "✓ Fleet profile created: {filename}",
        "status_restoring_file": "⏳ Restoring {filename}…",
        "status_applying_config": "⏳ Applying config…",
        "status_restored_file": "✓ Restored: {filename}",
        "status_import_failed": "✗ Import failed",
        "status_multi_export_done": "✓ Session finished — {count} node(s) exported",
        "status_connecting_node": "⏳ Connecting node #{index}…",
        "status_node_exported": "✓ Node #{index} exported: {filename}",
        "status_multi_import_done": "✓ Session finished — {count} node(s) restored",
        "status_restoring_node": "⏳ Restoring node #{index}…",
        "status_node_restored": "✓ Node #{index} restored",
        "status_file_copied": "✓ Copied: {filename}",
        "status_file_deleted": "✓ Deleted: {filename}",
        "popup_already_fleet_title": "Already a fleet profile",
        "popup_already_fleet_text": "This file is already a fleet profile.\n\nContinue anyway?",
        "popup_session_done_title": "Session finished",
        "popup_multi_import_done_text": "{count} node(s) restored successfully.\n{errors} error(s).\n\n⚠ Restart each device to apply changes.",
        "popup_node_restored_text": "{log_text}\n\n⚠ Restart the device to apply changes.",

    },
}


def tr(key: str, **kwargs) -> str:
    s = UI_STRINGS[load_lang()].get(key, key)
    return s.format(**kwargs) if kwargs else s


class NBFMApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Nodes Backup & Fleet Manager v1.75")
        self.root.geometry("930x840")
        self.root.resizable(True, True)
        self.work_dir = APP_DIR
        # Langue
        self.lang_var = tk.StringVar(value=load_lang())
        self._build_ui()
        self.refresh_files()
        self.root.after(200, self.detect_ports)
        self._edit_popup_refresh = None
    def _build_ui(self):
        root = self.root
        T = UI_STRINGS[self.lang_var.get()]

        # ── En-tête global ────────────────────────────────────────────────────
        hdr = ttk.Frame(root)
        hdr.pack(fill="x", pady=(12, 2), padx=20)
        ttk.Label(hdr, text="Nodes Backup & Fleet Manager v1.75",
                  font=("Arial", 15, "bold")).pack(side="left")
        # Sélecteur de langue FR / EN
        lang_frame = ttk.Frame(hdr)
        lang_frame.pack(side="right")
        tk.Radiobutton(lang_frame, text="FR", variable=self.lang_var, value="fr",
                       font=("Arial", 9, "bold"), command=self._apply_lang,
                       relief="flat", cursor="hand2").pack(side="left")
        tk.Radiobutton(lang_frame, text="EN", variable=self.lang_var, value="en",
                       font=("Arial", 9, "bold"), command=self._apply_lang,
                       relief="flat", cursor="hand2").pack(side="left")

        self._lbl_subtitle = ttk.Label(root, text=T["subtitle"],
                  font=("Arial", 9), foreground="#555")
        self._lbl_subtitle.pack(pady=(0, 6))
        ttk.Separator(root, orient="horizontal").pack(fill="x", padx=20, pady=(0, 6))

        # ── Notebook ──────────────────────────────────────────────────────────
        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill="both", expand=True, padx=8, pady=(0, 4))

        self._main_tab = ttk.Frame(self.notebook, padding=4)
        self.notebook.add(self._main_tab, text=T["tab_main"])

        self._aide_tab = ttk.Frame(self.notebook, padding=8)
        self.notebook.add(self._aide_tab, text=T["tab_help"])
        self._build_aide_tab(self._aide_tab, T)

        root = self._main_tab

        # Dossier
        self._lf_folder = ttk.LabelFrame(root, text=T["lf_folder"], padding=8)
        self._lf_folder.pack(padx=20, pady=4, fill="x")
        self.dir_var = tk.StringVar(value=str(self.work_dir))
        ttk.Entry(self._lf_folder, textvariable=self.dir_var, state="readonly").pack(
            side="left", fill="x", expand=True, padx=(0, 8))
        self._btn_choose = ttk.Button(self._lf_folder, text=T["btn_choose"], command=self.choose_work_dir)
        self._btn_choose.pack(side="left", padx=3)
        self._btn_open = ttk.Button(self._lf_folder, text=T["btn_open"], command=self.open_folder)
        self._btn_open.pack(side="left", padx=3)

        # Connexion
        self._lf_connect = ttk.LabelFrame(root, text=T["lf_connect"], padding=8)
        self._lf_connect.pack(padx=20, pady=6, fill="x")
        row = ttk.Frame(self._lf_connect); row.pack(fill="x")
        self._lbl_port = ttk.Label(row, text=T["lbl_port"])
        self._lbl_port.pack(side="left")
        self.port_var = tk.StringVar(value="")
        self.port_combo = ttk.Combobox(row, textvariable=self.port_var, width=12)
        self.port_combo.pack(side="left", padx=6)
        self._btn_detect = ttk.Button(row, text=T["btn_detect"], command=self.detect_ports)
        self._btn_detect.pack(side="left", padx=4)
        self._lbl_scan = ttk.Label(row, text=T["lbl_scan"], foreground="#888", font=("Arial", 8))
        self._lbl_scan.pack(side="left", padx=6)

        # Export
        self._lf_export = ttk.LabelFrame(root, text=T["lf_export"], padding=8)
        self._lf_export.pack(padx=20, pady=6, fill="x")
        _ef_row = ttk.Frame(self._lf_export)
        _ef_row.pack(fill="x")
        self._btn_export_1 = tk.Button(_ef_row, text=T["btn_export_1"],
                  command=self.export_config,
                  background="#cce0ff", activebackground="#99c2ff",
                  relief="raised", font=("Arial", 9, "bold"))
        self._btn_export_1.pack(side="left", fill="x", expand=True, ipady=6, padx=(0, 3))
        self._btn_export_multi = tk.Button(_ef_row, text=T["btn_export_multi"],
                  command=self.export_multi_nodes,
                  background="#ddeeff", activebackground="#bbddff",
                  relief="raised", font=("Arial", 9, "bold"))
        self._btn_export_multi.pack(side="left", fill="x", expand=True, ipady=6)
        self._lbl_export_hint = ttk.Label(self._lf_export, text=T["lbl_export_hint"],
            font=("Arial", 8), foreground="#666")
        self._lbl_export_hint.pack(anchor="w", pady=(3, 0))

        # Liste fichiers — Treeview tabulaire
        self._lf_files = ttk.LabelFrame(root, text=T["lf_files"], padding=8)
        self._lf_files.pack(padx=20, pady=4, fill="both", expand=True)
        cols = ("type", "fichier", "modele", "modem", "freq", "canal0", "canal1", "date")
        self.tree = ttk.Treeview(self._lf_files, columns=cols, show="headings",
                                 selectmode="browse", height=6)
        self._sort_reverse = {c: False for c in cols}
        def _make_sort(col):
            def _sort():
                data = [(self.tree.set(k, col), k) for k in self.tree.get_children("")]
                self._sort_reverse[col] = not self._sort_reverse[col]
                data.sort(reverse=self._sort_reverse[col], key=lambda x: x[0].lower() if x[0] else "")
                for i, (_, k) in enumerate(data):
                    self.tree.move(k, "", i)
                arrow = " ▲" if not self._sort_reverse[col] else " ▼"
                for c in cols:
                    self.tree.heading(c, text=self.tree.heading(c)["text"].rstrip(" ▲▼"))
                self.tree.heading(col, text=self.tree.heading(col)["text"] + arrow)
            return _sort
        col_keys = [("type","col_type"),("fichier","col_file"),("modele","col_model"),
                    ("modem","col_modem"),("freq","col_freq"),("canal0","col_ch0"),("canal1","col_ch1"),("date","col_date")]
        for cid, tkey in col_keys:
            self.tree.heading(cid, text=T[tkey], anchor="w", command=_make_sort(cid))
        self._tree_col_keys = col_keys  # mémorise pour _apply_lang
        self.tree.column("type",    width=70,  stretch=False, minwidth=40)
        self.tree.column("fichier", width=200, stretch=True,  minwidth=80)
        self.tree.column("modele",  width=80,  stretch=False, minwidth=50)
        self.tree.column("modem",   width=85,  stretch=False, minwidth=60)
        self.tree.column("freq",    width=95,  stretch=False, minwidth=70)
        self.tree.column("canal0",  width=75,  stretch=False, minwidth=50)
        self.tree.column("canal1",  width=75,  stretch=False, minwidth=50)
        self.tree.column("date",    width=115, stretch=False, minwidth=80)
        self.tree.tag_configure("backup", foreground="#1a5e1a")
        self.tree.tag_configure("fleet",  foreground="#003399")
        vsb = ttk.Scrollbar(self._lf_files, orient="vertical",   command=self.tree.yview)
        hsb = ttk.Scrollbar(self._lf_files, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        self._lf_files.rowconfigure(0, weight=1)
        self._lf_files.columnconfigure(0, weight=1)
        self.tree.bind("<Double-Button-1>", lambda e: self.view_file())
        br = ttk.Frame(self._lf_files); br.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        self._btn_refresh = ttk.Button(br, text=T["btn_refresh"], command=self.refresh_files)
        self._btn_refresh.pack(side="left", padx=3)
        self._btn_view = ttk.Button(br, text=T["btn_view"], command=self.view_file)
        self._btn_view.pack(side="left", padx=3)
        self._btn_edit = ttk.Button(br, text=T["btn_edit"], command=self.edit_config_fields)
        self._btn_edit.pack(side="left", padx=3)
        self._btn_copy = ttk.Button(br, text=T["btn_copy"], command=self.copy_file)
        self._btn_copy.pack(side="left", padx=3)
        self._btn_delete = ttk.Button(br, text=T["btn_delete"], command=self.delete_file)
        self._btn_delete.pack(side="left", padx=3)
        self._btn_browse = ttk.Button(br, text=T["btn_browse"], command=self.import_browse)
        self._btn_browse.pack(side="left", padx=(12, 3))

        # Profil flotte
        self._lf_fleet = ttk.LabelFrame(root, text=T["lf_fleet"], padding=8)
        self._lf_fleet.pack(padx=20, pady=4, fill="x")
        self._btn_fleet = ttk.Button(self._lf_fleet, text=T["btn_fleet"],
                   command=self.generate_fleet_profile)
        self._btn_fleet.pack(fill="x", ipady=6)
        self._lbl_fleet_hint = ttk.Label(self._lf_fleet, text=T["lbl_fleet_hint"],
            font=("Arial", 8), foreground="#003388")
        self._lbl_fleet_hint.pack(anchor="w", pady=(3, 0))

        # Import
        self._lf_import = ttk.LabelFrame(root, text=T["lf_import"], padding=8)
        self._lf_import.pack(padx=20, pady=6, fill="x")
        _imf_row = ttk.Frame(self._lf_import)
        _imf_row.pack(fill="x")
        self._btn_restore_1 = tk.Button(_imf_row, text=T["btn_restore_1"],
                  command=self.import_selected,
                  background="#cce0ff", activebackground="#99c2ff",
                  relief="raised", font=("Arial", 9, "bold"))
        self._btn_restore_1.pack(side="left", fill="x", expand=True, ipady=6, padx=(0, 3))
        self._btn_restore_multi = tk.Button(_imf_row, text=T["btn_restore_multi"],
                  command=self.import_multi_nodes,
                  background="#ddeeff", activebackground="#bbddff",
                  relief="raised", font=("Arial", 9, "bold"))
        self._btn_restore_multi.pack(side="left", fill="x", expand=True, ipady=6)

        # Status bar
        self.status_var = tk.StringVar(value=T["status_ready"])
        self._status_bar = ttk.Label(root, textvariable=self.status_var, relief="sunken",
                  font=("Arial", 9), foreground="#003366", anchor="w")
        self._status_bar.pack(fill="x", side="bottom", ipady=3)

    # ── Langue ────────────────────────────────────────────────────────────────

    def _apply_lang(self):
        """Met à jour tous les textes UI selon la langue choisie (sans reconstruire)."""
        lang = self.lang_var.get()
        save_lang(lang)
        T = UI_STRINGS[lang]
        # En-tête
        self._lbl_subtitle.config(text=T["subtitle"])
        # Onglets
        self.notebook.tab(0, text=T["tab_main"])
        self.notebook.tab(1, text=T["tab_help"])
        # Dossier
        self._lf_folder.config(text=T["lf_folder"])
        self._btn_choose.config(text=T["btn_choose"])
        self._btn_open.config(text=T["btn_open"])
        # Connexion
        self._lf_connect.config(text=T["lf_connect"])
        self._lbl_port.config(text=T["lbl_port"])
        self._btn_detect.config(text=T["btn_detect"])
        self._lbl_scan.config(text=T["lbl_scan"])
        # Export
        self._lf_export.config(text=T["lf_export"])
        self._btn_export_1.config(text=T["btn_export_1"])
        self._btn_export_multi.config(text=T["btn_export_multi"])
        self._lbl_export_hint.config(text=T["lbl_export_hint"])
        # Fichiers - en-têtes colonnes (sans flèche de tri)
        for cid, tkey in self._tree_col_keys:
            cur = self.tree.heading(cid)["text"].rstrip(" ▲▼")
            self.tree.heading(cid, text=T[tkey])
        self._lf_files.config(text=T["lf_files"])
        self._btn_refresh.config(text=T["btn_refresh"])
        self._btn_view.config(text=T["btn_view"])
        self._btn_edit.config(text=T["btn_edit"])
        self._btn_copy.config(text=T["btn_copy"])
        self._btn_delete.config(text=T["btn_delete"])
        self._btn_browse.config(text=T["btn_browse"])
        # Flotte
        self._lf_fleet.config(text=T["lf_fleet"])
        self._btn_fleet.config(text=T["btn_fleet"])
        self._lbl_fleet_hint.config(text=T["lbl_fleet_hint"])
        # Import
        self._lf_import.config(text=T["lf_import"])
        self._btn_restore_1.config(text=T["btn_restore_1"])
        self._btn_restore_multi.config(text=T["btn_restore_multi"])
        # Reconstruire l'aide
        for w in self._aide_tab.winfo_children():
            w.destroy()
        self._build_aide_tab(self._aide_tab, T)
        if callable(self._edit_popup_refresh):
            try:
                self._edit_popup_refresh()
            except Exception:
                pass

    # ── Onglet Aide ───────────────────────────────────────────────────────────

    def _build_aide_tab(self, parent, T=None):
        """Construit l'onglet d'aide avec scroll (bilingue)."""
        if T is None:
            T = UI_STRINGS[self.lang_var.get()]
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

        ttk.Label(inner, text=T["help_title"],
                  font=("Arial", 12, "bold"), foreground="#001f66").pack(
                  anchor="w", padx=6, pady=(8, 2))
        ttk.Label(inner, text=T["help_intro"],
                  wraplength=680, justify="left", font=("Arial", 9),
                  foreground="#444").pack(anchor="w", padx=6, pady=(0, 4))

        for sec_title, items in T["help_sections"]:
            section(sec_title)
            for kind, val in items:
                if kind == "p":
                    para(val)
                elif kind == "s":
                    step(val[0], val[1])

        ttk.Separator(inner, orient="horizontal").pack(fill="x", pady=(10, 4))
        ttk.Label(inner, text="Nodes Backup & Fleet Manager v1.75",
                  font=("Arial", 8), foreground="#aaa").pack(anchor="e", padx=8, pady=4)


    # ── Helpers ───────────────────────────────────────────────────────────────

    def set_status(self, msg):
        self.status_var.set(msg)
        self.root.update_idletasks()

    def detect_ports(self):
        all_ports = list_serial_ports()
        # COM1 est le port série système Windows (souris/BIOS), jamais un appareil USB
        EXCLUDED = {"COM1", "com1"}
        ports = [p for p in all_ports if p not in EXCLUDED]
        self.port_combo["values"] = ports
        if ports:
            self.port_combo.set(ports[0])
            excluded_note = f" (COM1 exclu)" if len(all_ports) != len(ports) else ""
            self.set_status(
                UI_STRINGS[self.lang_var.get()]["status_ports_found"].format(
                    count=len(ports), ports=", ".join(ports), excluded_note=excluded_note
                )
            )
        elif all_ports:
            # Uniquement COM1 disponible — on l'affiche mais on avertit
            self.port_combo["values"] = all_ports
            self.port_combo.set("")
            self.set_status(UI_STRINGS[self.lang_var.get()]["status_only_com1"])
        else:
            self.set_status(UI_STRINGS[self.lang_var.get()]["status_no_com"])

    def choose_work_dir(self):
        T = UI_STRINGS[self.lang_var.get()]
        s = filedialog.askdirectory(title=T["sel_choose_backup_folder"], initialdir=str(self.work_dir))
        if s:
            self.work_dir = Path(s)
            self.dir_var.set(str(self.work_dir))
            self.refresh_files()
            self.set_status(UI_STRINGS[self.lang_var.get()]["status_folder"].format(folder=self.work_dir))

    def refresh_files(self):
        self.tree.delete(*self.tree.get_children())
        self._file_map = {}
        try:
            paths = sorted(
                list(self.work_dir.glob("*.NBFM")) +
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
                            meta.get("modem", "?"),
                            meta.get("freq", "?"),
                            meta["ch_name"], meta["ch1_name"], meta["date"]),
                    tags=(tag,))
                self._file_map[iid] = p
            self.set_status(
                UI_STRINGS[self.lang_var.get()]["status_files_in_dir"].format(
                    count=len(paths), dirname=self.work_dir.name
                )
            )
        except Exception as e:
            self.set_status(UI_STRINGS[self.lang_var.get()]["status_error"].format(error=e))

    def open_folder(self):
        try:
            os.startfile(str(self.work_dir))
        except Exception as e:
            messagebox.showerror(UI_STRINGS[self.lang_var.get()]["popup_error_title"], str(e))

    def _get_selected_file(self) -> Optional[Path]:
        sel = self.tree.selection()
        if not sel:
            T = UI_STRINGS[self.lang_var.get()]
            messagebox.showwarning(T["sel_no_selection_title"], T["sel_no_selection_text"])
            return None
        return self._file_map.get(sel[0])

    # ── Export ────────────────────────────────────────────────────────────────

    def export_config(self):
        self.set_status(UI_STRINGS[self.lang_var.get()]["status_connecting_device"])

        def do_export():
            iface = None
            try:
                iface = connect_device(self.port_var.get().strip() or None)
                self.root.after(0, lambda: self.set_status(UI_STRINGS[self.lang_var.get()]["status_reading_config"]))
                config = export_full_config(iface)

                # Nom de fichier suggéré avec short_name (ex: JMC_5F7B)
                now      = datetime.now().strftime("%Y%m%d_%H%M%S")
                owner    = config.get("owner", {}) if isinstance(config.get("owner"), dict) else {}
                sn_raw   = owner.get("short_name", "") or owner.get("long_name", "")
                sn_slug  = "".join(c if c.isalnum() or c in "-_" else "_" for c in sn_raw).strip("_")
                suggest  = f"meshtastic_{sn_slug}_{now}.NBFM" if sn_slug else f"meshtastic_backup_{now}.NBFM"

                def ask_and_save():
                    filename = filedialog.asksaveasfilename(
                        title=UI_STRINGS[self.lang_var.get()]["sel_save_full_config"],
                        initialdir=str(self.work_dir),
                        defaultextension=".NBFM",
                        initialfile=suggest,
                        filetypes=[("NBFM files", "*.NBFM"), ("Tous", "*.*")]
                    )
                    if not filename:
                        self.set_status(UI_STRINGS[self.lang_var.get()]["status_export_cancelled"])
                        return
                    try:
                        with open(filename, "w", encoding="utf-8") as f:
                            json.dump(config, f, indent=2, ensure_ascii=False, default=str)
                        self.work_dir = Path(filename).resolve().parent
                        self.dir_var.set(str(self.work_dir))
                        self.refresh_files()
                        self.set_status(f"✓ {Path(filename).name}")
                        messagebox.showinfo("Export réussi ✓",
                            f"Config complète sauvegardée :\n{filename}")
                    except Exception as e:
                        messagebox.showerror(UI_STRINGS[self.lang_var.get()]["popup_save_error_title"], str(e))

                self.root.after(0, ask_and_save)

            except Exception as e:
                err = str(e)
                self.root.after(0, lambda: self.set_status(UI_STRINGS[self.lang_var.get()]["status_export_failed"]))
                self.root.after(0, lambda: messagebox.showerror(UI_STRINGS[self.lang_var.get()]["popup_export_error_title"], err))
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
            messagebox.showerror(UI_STRINGS[self.lang_var.get()]["popup_invalid_file"], str(e)); return

        if config.get("_profile_type") == "fleet":
            if not messagebox.askyesno("Déjà un profil flotte",
                "Ce fichier est déjà un profil flotte.\n\nContinuer quand même ?"):
                return

        now = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest = filedialog.asksaveasfilename(
            title=UI_STRINGS[self.lang_var.get()]["sel_save_fleet_profile"],
            initialdir=str(self.work_dir),
            defaultextension=".NBFM",
            initialfile=f"profil_flotte_{now}.NBFM",
            filetypes=[("NBFM files", "*.NBFM"), ("Tous", "*.*")]
        )
        if not dest: return

        try:
            fleet = build_fleet_profile(config)
            with open(dest, "w", encoding="utf-8") as fp:
                json.dump(fleet, fp, indent=2, ensure_ascii=False)
            self.work_dir = Path(dest).resolve().parent
            self.dir_var.set(str(self.work_dir))
            self.refresh_files()
            self.set_status(UI_STRINGS[self.lang_var.get()]["status_fleet_created"].format(filename=Path(dest).name))
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
            messagebox.showerror(UI_STRINGS[self.lang_var.get()]["popup_error_title"], str(e))

    # ── Import ────────────────────────────────────────────────────────────────

    def _do_import(self, filename: str):
        file_path = Path(filename)
        if not file_path.exists():
            messagebox.showerror(UI_STRINGS[self.lang_var.get()]["popup_file_not_found"], str(filename)); return
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                config = json.load(f)
        except Exception as e:
            messagebox.showerror(UI_STRINGS[self.lang_var.get()]["popup_invalid_file"], str(e)); return

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

        self.set_status(UI_STRINGS[self.lang_var.get()]["status_restoring_file"].format(filename=file_path.name))

        def do_import():
            iface = None
            try:
                iface = connect_device(self.port_var.get().strip() or None)
                self.root.after(0, lambda: self.set_status(UI_STRINGS[self.lang_var.get()]["status_applying_config"]))
                log_lines = import_full_config(iface, config)
                log_text = "\n".join(log_lines)
                self.root.after(0, lambda: self.set_status(UI_STRINGS[self.lang_var.get()]["status_restored_file"].format(filename=file_path.name)))
                self.root.after(0, lambda: messagebox.showinfo("Import réussi ✓",
                    f"Config restaurée:\n{filename}\n\n{log_text}\n\n"
                    "⚠ Redémarrez l'appareil pour appliquer."))
            except Exception as e:
                err = str(e)
                self.root.after(0, lambda: self.set_status(UI_STRINGS[self.lang_var.get()]["status_import_failed"]))
                self.root.after(0, lambda: messagebox.showerror(UI_STRINGS[self.lang_var.get()]["popup_import_error_title"], err))
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
            title=UI_STRINGS[self.lang_var.get()]["sel_choose_config_file"],
            initialdir=str(self.work_dir),
            filetypes=[("NBFM files", "*.NBFM"), ("JSON/YAML", "*.json *.yaml *.yml"), ("Tous", "*.*")]
        )
        if fn: self._do_import(fn)


    # ── Export multi-nœuds ────────────────────────────────────────────────────

    def export_multi_nodes(self):
        """Export séquentiel de plusieurs nœuds. Port sélectionnable à chaque étape."""
        import serial.tools.list_ports as _lp

        def _ask_and_export(count):
            """Boîte de dialogue personnalisée avec sélecteur de port intégré."""
            win = tk.Toplevel(self.root)
            T = UI_STRINGS[self.lang_var.get()]
            win.title(T["multi_export_title"].format(index=count + 1))
            win.geometry("420x200")
            win.resizable(False, False)
            win.grab_set()

            ttk.Label(win,
                text=(T["multi_export_text_first"] if count == 0 else T["multi_export_text_next"]).format(index=count + 1),
                font=("Arial", 10)).pack(pady=(16, 4), padx=16, anchor="w")

            row = ttk.Frame(win); row.pack(padx=16, pady=4, fill="x")
            ttk.Label(row, text=UI_STRINGS[self.lang_var.get()]["lbl_port"]).pack(side="left")
            ports = [p.device for p in sorted(_lp.comports()) if p.device not in {"COM1","com1"}]
            port_var = tk.StringVar(value=ports[0] if ports else "")
            cb = ttk.Combobox(row, textvariable=port_var, values=ports, width=12)
            cb.pack(side="left", padx=6)
            def refresh_ports():
                p2 = [p.device for p in sorted(_lp.comports()) if p.device not in {"COM1","com1"}]
                cb["values"] = p2
                if p2: port_var.set(p2[0])
            ttk.Button(row, text=T["multi_detect"], command=refresh_ports).pack(side="left", padx=4)
            ttk.Label(row, text=T["multi_scan_hint"], foreground="#888",
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
            tk.Button(btn_row, text=T["multi_export_btn"], command=do_export,
                      background="#cce0ff", font=("Arial", 9, "bold")).pack(side="left", padx=6)
            ttk.Button(btn_row, text=T["multi_skip_btn"], command=do_skip).pack(side="left", padx=4)
            ttk.Button(btn_row, text=T["multi_finish_btn"], command=do_stop).pack(side="left", padx=4)

            win.wait_window()
            return result

        count = 0
        while True:
            res = _ask_and_export(count)
            if res["action"] == "stop" or res["action"] is None:
                self.set_status(UI_STRINGS[self.lang_var.get()]["status_multi_export_done"].format(count=count))
                if count > 0:
                    T = UI_STRINGS[self.lang_var.get()]
                    messagebox.showinfo(T["multi_session_done_title"], T["multi_export_done_text"].format(count=count))
                break
            if res["action"] == "skip":
                continue

            # Connexion + lecture config
            self.set_status(UI_STRINGS[self.lang_var.get()]["status_connecting_node"].format(index=count + 1))
            try:
                iface = connect_device(res["port"] or None)
                config = export_full_config(iface)
                iface.close()
            except Exception as e:
                T = UI_STRINGS[self.lang_var.get()]
                if not (res["port"] or "").strip():
                    messagebox.showerror(T["export_error_title"], T["export_error_no_com"])
                else:
                    messagebox.showerror(T["multi_node_connect_error"].format(index=count + 1), str(e))
                continue

            # Nom suggéré avec short_name (ex: JMC_5F7B)
            now     = datetime.now().strftime("%Y%m%d_%H%M%S")
            owner   = config.get("owner", {}) if isinstance(config.get("owner"), dict) else {}
            sn_raw  = owner.get("short_name", "") or owner.get("long_name", "")
            ln_raw  = owner.get("long_name", "") or owner.get("short_name", "")
            sn_slug = "".join(c if c.isalnum() or c in "-_" else "_" for c in sn_raw).strip("_")
            suggest = f"meshtastic_{sn_slug}_{now}.NBFM" if sn_slug else f"meshtastic_node{count+1:02d}_{now}.NBFM"

            filename = filedialog.asksaveasfilename(
                title=UI_STRINGS[self.lang_var.get()]["sel_save_node"].format(index=count + 1, name=ln_raw or "?"),
                initialdir=str(self.work_dir),
                defaultextension=".NBFM",
                initialfile=suggest,
                filetypes=[("NBFM files", "*.NBFM"), ("Tous", "*.*")]
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
                self.set_status(UI_STRINGS[self.lang_var.get()]["status_node_exported"].format(index=count, filename=Path(filename).name))
            except Exception as e:
                messagebox.showerror(UI_STRINGS[self.lang_var.get()]["multi_node_save_error"].format(index=count + 1), str(e))


    def import_multi_nodes(self):
        """Import séquentiel du même fichier NBFM vers plusieurs nœuds.
        Utilise le fichier sélectionné dans l'UI (même logique que restauration unique)."""
        import serial.tools.list_ports as _lp

        # Utiliser le fichier sélectionné dans l'UI — même comportement que import_selected
        file_path = self._get_selected_file()
        if not file_path:
            messagebox.showwarning(UI_STRINGS[self.lang_var.get()]["sel_no_file_title"],
                UI_STRINGS[self.lang_var.get()]["sel_no_file_text"])
            return
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                config = json.load(f)
        except Exception as e:
            messagebox.showerror(UI_STRINGS[self.lang_var.get()]["popup_invalid_file"], str(e)); return

        # Vérification intégrité une seule fois
        warns = validate_config_integrity(config)
        if warns:
            if not messagebox.askyesno("⚠ Avertissements d'intégrité",
                "\n".join(warns) + "\n\nContinuer quand même ?"):
                return

        profile_type = config.get("_profile_type", "complet")
        type_label   = "⚡ PROFIL FLOTTE" if profile_type == "fleet" else "📦 Sauvegarde complète"

        def _ask_and_import(count):
            win = tk.Toplevel(self.root)
            T = UI_STRINGS[self.lang_var.get()]
            win.title(T["multi_import_title"].format(index=count + 1))
            win.geometry("440x220")
            win.resizable(False, False)
            win.grab_set()

            ttk.Label(win,
                text=T["multi_import_text"].format(index=count + 1),
                font=("Arial", 10)).pack(pady=(16, 2), padx=16, anchor="w")
            ttk.Label(win,
                text=T["multi_file_line"].format(filename=file_path.name, type_label=type_label),
                font=("Arial", 8), foreground="#444").pack(padx=16, anchor="w")

            row = ttk.Frame(win); row.pack(padx=16, pady=6, fill="x")
            ttk.Label(row, text=UI_STRINGS[self.lang_var.get()]["lbl_port"]).pack(side="left")
            ports = [p.device for p in sorted(_lp.comports()) if p.device not in {"COM1","com1"}]
            port_var = tk.StringVar(value=ports[0] if ports else "")
            cb = ttk.Combobox(row, textvariable=port_var, values=ports, width=12)
            cb.pack(side="left", padx=6)
            def refresh_ports():
                p2 = [p.device for p in sorted(_lp.comports()) if p.device not in {"COM1","com1"}]
                cb["values"] = p2
                if p2: port_var.set(p2[0])
            ttk.Button(row, text=T["multi_detect"], command=refresh_ports).pack(side="left", padx=4)
            ttk.Label(row, text=T["multi_scan_hint"], foreground="#888",
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
            tk.Button(btn_row, text=T["multi_import_btn"], command=do_import,
                      background="#cce0ff", font=("Arial", 9, "bold")).pack(side="left", padx=6)
            ttk.Button(btn_row, text=T["multi_skip_btn"], command=do_skip).pack(side="left", padx=4)
            ttk.Button(btn_row, text=T["multi_finish_btn"], command=do_stop).pack(side="left", padx=4)

            win.wait_window()
            return result

        count = 0
        errors = 0
        while True:
            res = _ask_and_import(count)
            if res["action"] == "stop" or res["action"] is None:
                self.set_status(UI_STRINGS[self.lang_var.get()]["status_multi_import_done"].format(count=count))
                if count > 0:
                    messagebox.showinfo("Session terminée",
                        f"{count} nœud(s) restauré(s) avec succès.\n"
                        f"{errors} erreur(s).\n\n"
                        "⚠ Redémarrez chaque appareil pour appliquer.")
                break
            if res["action"] == "skip":
                continue

            self.set_status(UI_STRINGS[self.lang_var.get()]["status_restoring_node"].format(index=count + 1))
            try:
                iface = connect_device(res["port"] or None)
                log_lines = import_full_config(iface, config)
                iface.close()
                count += 1
                self.set_status(UI_STRINGS[self.lang_var.get()]["status_node_restored"].format(index=count))
                messagebox.showinfo(f"Nœud #{count} restauré ✓",
                    "\n".join(log_lines) +
                    "\n\n⚠ Redémarrez l'appareil pour appliquer.")
            except Exception as e:
                errors += 1
                messagebox.showerror(UI_STRINGS[self.lang_var.get()]["multi_node_error"].format(index=count + 1), str(e))

    # ── Éditeur de champs clés ────────────────────────────────────────────────


    def edit_config_fields(self):
        """Ouvre un formulaire minimaliste pour modifier les champs courants d'un NBFM."""
        f = self._get_selected_file()
        if not f:
            return

        T = UI_STRINGS[self.lang_var.get()]

        try:
            with open(f, "r", encoding="utf-8") as fp:
                config = json.load(fp)
        except Exception as e:
            messagebox.showerror(T["edit_invalid_file"], str(e))
            return

        win = tk.Toplevel(self.root)
        win.geometry("520x750")
        win.resizable(True, True)
        win.grab_set()

        header_lbl = ttk.Label(win, font=("Arial", 9, "bold"))
        header_lbl.pack(anchor="w", padx=12, pady=(10, 2))
        ttk.Separator(win, orient="horizontal").pack(fill="x", padx=10, pady=4)

        frm = ttk.Frame(win, padding=10)
        frm.pack(fill="both", expand=True)
        frm.columnconfigure(1, weight=1)

        def TT():
            return UI_STRINGS[self.lang_var.get()]

        popup_labels = []
        popup_buttons = []
        popup_checks = []

        def mk_label(row, key, value):
            lbl = ttk.Label(frm, font=("Arial", 9))
            lbl.grid(row=row, column=0, sticky="w", padx=(0, 10), pady=2)
            var = tk.StringVar(value=str(value) if value else "")
            ent = ttk.Entry(frm, textvariable=var, width=38)
            ent.grid(row=row, column=1, sticky="ew", pady=2)
            popup_labels.append((lbl, key))
            return var

        def mk_combo(row, key, value, choices):
            lbl = ttk.Label(frm, font=("Arial", 9))
            lbl.grid(row=row, column=0, sticky="w", padx=(0, 10), pady=2)
            var = tk.StringVar(value=str(value) if value else "")
            combo = ttk.Combobox(frm, textvariable=var, values=choices, state="readonly", width=38)
            combo.grid(row=row, column=1, sticky="ew", pady=2)
            popup_labels.append((lbl, key))
            return var

        owner = config.get("owner", {}) or {}

        lbl_owner = ttk.Label(frm, font=("Arial", 9, "bold"), foreground="#333")
        lbl_owner.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 2))
        popup_labels.append((lbl_owner, "edit_owner"))

        vlong = mk_label(1, "edit_long_name", owner.get("long_name", ""))
        vshort = mk_label(2, "edit_short_name", owner.get("short_name", ""))

        # espaceur entre short_name et LoRa
        ttk.Label(frm).grid(row=3, column=0, pady=2)

        lbl_lora = ttk.Label(frm, font=("Arial", 9, "bold"), foreground="#333")
        lbl_lora.grid(row=4, column=0, columnspan=2, sticky="w", pady=(0, 2))
        popup_labels.append((lbl_lora, "edit_lora"))

        lc = config.get("local_config", {}) or {}
        lora = lc.get("lora", {}) or {}
        vregion = mk_combo(5, "edit_region", _region_label_from_int(lora.get("region", 0)), _region_labels())
        vmodem  = mk_combo(6, "edit_modem",  _modem_label_from_int(lora.get("modem_preset", 0)), _modem_labels())

        # override_frequency
        raw_ovf = lora.get("override_frequency", 0) or 0
        ovf_init = f"{float(raw_ovf):.4f}".rstrip("0").rstrip(".") if float(raw_ovf) > 0 else ""
        voverride_freq = mk_label(7, "edit_override_freq", ovf_init)

        # espaceur entre override_freq et Channels
        ttk.Label(frm).grid(row=8, column=0, pady=2)

        lbl_channels = ttk.Label(frm, font=("Arial", 9, "bold"), foreground="#333")
        lbl_channels.grid(row=9, column=0, columnspan=2, sticky="w", pady=(0, 2))
        popup_labels.append((lbl_channels, "edit_channels"))

        channels = config.get("channels", [])
        def _get_ch_name(idx):
            if isinstance(channels, list) and len(channels) > idx:
                ch = channels[idx]
                if isinstance(ch, dict):
                    s = ch.get("settings", {})
                    if isinstance(s, dict):
                        return s.get("name", "")
            return ""

        def _get_ch_psk_b64(idx):
            """Retourne la PSK du canal en Base64 (format Meshtastic), depuis le hex stocké."""
            import base64
            if isinstance(channels, list) and len(channels) > idx:
                ch = channels[idx]
                if isinstance(ch, dict):
                    s = ch.get("settings", {})
                    if isinstance(s, dict):
                        psk_hex = s.get("psk", "")
                        if psk_hex and isinstance(psk_hex, str):
                            try:
                                return base64.b64encode(bytes.fromhex(psk_hex)).decode("ascii")
                            except Exception:
                                return psk_hex  # retourner tel quel si conversion impossible
            return ""

        vch0     = mk_label(10, "edit_ch0",     _get_ch_name(0))
        vch0_key = mk_label(11, "edit_ch0_key", _get_ch_psk_b64(0))

        # espaceur entre ch0_key et ch1
        ttk.Label(frm).grid(row=12, column=0, pady=2)

        vch1     = mk_label(13, "edit_ch1",     _get_ch_name(1))
        vch1_key = mk_label(14, "edit_ch1_key", _get_ch_psk_b64(1))

        # espaceur entre ch1_key et ch2
        ttk.Label(frm).grid(row=15, column=0, pady=2)

        vch2     = mk_label(16, "edit_ch2",     _get_ch_name(2))
        vch2_key = mk_label(17, "edit_ch2_key", _get_ch_psk_b64(2))

        lbl_psk = ttk.Label(frm, font=("Arial", 8), foreground="#888")
        lbl_psk.grid(row=18, column=0, columnspan=2, sticky="w", pady=(4, 0))
        popup_labels.append((lbl_psk, "edit_psk_hint"))

        # ── Générateur de clé unique avec dropdown taille ──────────────────
        def generate_key(nb_bytes: int) -> str:
            import os, base64
            return base64.b64encode(os.urandom(nb_bytes)).decode("ascii")

        KEY_SIZES = [("Default", 0), ("128 bits", 16), ("256 bits", 32)]  # tailles acceptées par Meshtastic

        gen_outer = ttk.Frame(frm)
        gen_outer.grid(row=19, column=0, columnspan=2, sticky="ew", pady=(6, 0))

        # Ligne 1 : bouton + label "Taille :" + dropdown
        gen_top = ttk.Frame(gen_outer)
        gen_top.pack(fill="x")

        btn_gen = ttk.Button(gen_top)
        btn_gen.pack(side="left", padx=(0, 8))
        popup_buttons.append((btn_gen, "edit_gen_key"))

        lbl_size = ttk.Label(gen_top, font=("Arial", 9))
        lbl_size.pack(side="left", padx=(0, 4))
        popup_labels.append((lbl_size, "edit_gen_key_size"))

        size_var = tk.StringVar(value=KEY_SIZES[1][0])  # défaut : 256 bits
        size_combo = ttk.Combobox(gen_top, textvariable=size_var,
                                  values=[s[0] for s in KEY_SIZES],
                                  state="readonly", width=10)
        size_combo.pack(side="left")

        # Ligne 2 : champ résultat (copier/coller)
        gen_result_var = tk.StringVar(value="")
        gen_result_entry = ttk.Entry(gen_outer, textvariable=gen_result_var, width=52)
        gen_result_entry.pack(fill="x", pady=(4, 0))

        def _do_generate():
            label = size_var.get()
            nb = next((b for lbl, b in KEY_SIZES if lbl == label), 32)
            key = "AQ==" if nb == 0 else generate_key(nb)
            gen_result_var.set(key)
            gen_result_entry.selection_range(0, "end")

        btn_gen.config(command=_do_generate)

        ttk.Separator(win, orient="horizontal").pack(fill="x", padx=10, pady=6)

        frm_cleanup = ttk.LabelFrame(win, padding=8)
        frm_cleanup.pack(fill="x", padx=12, pady=(0, 8))

        clear_channels_var = tk.BooleanVar(value=False)
        chk_channels = ttk.Checkbutton(frm_cleanup, variable=clear_channels_var)
        chk_channels.pack(anchor="w", padx=4, pady=2)
        popup_checks.append((chk_channels, "edit_clear_channels"))

        clear_power_var = tk.BooleanVar(value=False)
        chk_power = ttk.Checkbutton(frm_cleanup, variable=clear_power_var)
        chk_power.pack(anchor="w", padx=4, pady=2)
        popup_checks.append((chk_power, "edit_clear_power"))

        clear_known_nodes_var = tk.BooleanVar(value=False)
        chk_known_nodes = ttk.Checkbutton(frm_cleanup, variable=clear_known_nodes_var)
        chk_known_nodes.pack(anchor="w", padx=4, pady=2)
        popup_checks.append((chk_known_nodes, "edit_clear_known_nodes"))

        def refresh_popup_lang():
            t = TT()
            win.title(t["edit_title"].format(filename=f.name))
            header_lbl.config(text=t["edit_file"].format(filename=f.name))
            frm_cleanup.config(text=t["edit_cleanup"])

            for widget, key in popup_labels:
                widget.config(text=t[key])
            for widget, key in popup_checks:
                widget.config(text=t[key])
            for widget, key in popup_buttons:
                widget.config(text=t[key])

        btn_row = ttk.Frame(win)
        btn_row.pack(fill="x", padx=12, pady=(0, 12))

        def save_and_close(save_as=False):
            try:
                owner = config.get("owner", {}) or {}
                owner["long_name"] = vlong.get().strip()
                owner["short_name"] = vshort.get().strip()
                config["owner"] = owner

                lc = config.get("local_config", {}) or {}
                lora = lc.get("lora", {}) or {}
                lora["region"] = _region_int_from_label(vregion.get())
                lora["modem_preset"] = _modem_int_from_label(vmodem.get())
                # override_frequency : vide = supprimer la clé, sinon float MHz
                ovf_str = voverride_freq.get().strip()
                if ovf_str:
                    try:
                        lora["override_frequency"] = float(ovf_str)
                    except ValueError:
                        pass  # valeur invalide : on garde l'ancienne
                else:
                    lora.pop("override_frequency", None)
                lc["lora"] = lora
                config["local_config"] = lc

                isfleet = config.get("_profile_type", "") == "fleet"
                t = TT()
                if not isfleet:
                    if not vlong.get().strip():
                        messagebox.showwarning(t["edit_empty_fields"], t["edit_long_required"])
                        return
                    if not vshort.get().strip():
                        messagebox.showwarning(t["edit_empty_fields"], t["edit_short_required"])
                        return

                channels = config.get("channels", [])
                if isinstance(channels, list) and channels:
                    if "settings" not in channels[0] or not isinstance(channels[0]["settings"], dict):
                        channels[0]["settings"] = {}
                    channels[0]["settings"]["name"] = vch0.get().strip()
                    # PSK canal 0 : convertir Base64 → hex
                    psk0_b64 = vch0_key.get().strip()
                    if psk0_b64:
                        try:
                            import base64
                            channels[0]["settings"]["psk"] = base64.b64decode(psk0_b64).hex()
                        except Exception:
                            pass  # Garder la valeur existante si la Base64 est invalide
                    if len(channels) > 1:
                        if "settings" not in channels[1] or not isinstance(channels[1]["settings"], dict):
                            channels[1]["settings"] = {}
                        channels[1]["settings"]["name"] = vch1.get().strip()
                        # PSK canal 1 : convertir Base64 → hex
                        psk1_b64 = vch1_key.get().strip()
                        if psk1_b64:
                            try:
                                import base64
                                channels[1]["settings"]["psk"] = base64.b64decode(psk1_b64).hex()
                            except Exception:
                                pass  # Garder la valeur existante si la Base64 est invalide
                    if len(channels) > 2:
                        if "settings" not in channels[2] or not isinstance(channels[2]["settings"], dict):
                            channels[2]["settings"] = {}
                        channels[2]["settings"]["name"] = vch2.get().strip()
                        psk2_b64 = vch2_key.get().strip()
                        if psk2_b64:
                            try:
                                import base64
                                channels[2]["settings"]["psk"] = base64.b64decode(psk2_b64).hex()
                            except Exception:
                                pass

                if clear_channels_var.get():
                    config["channels"] = [{
                        "index": 0,
                        "role": "PRIMARY",
                        "settings": {"name": vch0.get().strip(), "psk": "AQ=="}
                    }]

                if clear_power_var.get():
                    power = ((config.get("local_config") or {}).get("power"))
                    if isinstance(power, dict):
                        keys_to_remove = [k for k in list(power.keys())
                                          if "multdbm" in k.lower() or "adcmultiplier" in k.lower()]
                        for k in keys_to_remove:
                            del power[k]
                        config["local_config"]["power"] = power

                if clear_known_nodes_var.get():
                    config.pop("known_nodes", None)

                target = f
                if save_as:
                    filename = filedialog.asksaveasfilename(
                        title=TT()["edit_save_as"],
                        initialdir=str(self.work_dir),
                        defaultextension=".NBFM",
                        initialfile=f.stem + "_edited" + f.suffix,
                        filetypes=[("NBFM files", "*.NBFM"), ("Tous", "*.*")]
                    )
                    if not filename:
                        return
                    target = Path(filename)

                with open(target, "w", encoding="utf-8") as fp:
                    json.dump(config, fp, indent=2, ensure_ascii=False)

                self.refresh_files()
                self._edit_popup_refresh = None
                win.destroy()

            except Exception as e:
                messagebox.showerror(UI_STRINGS[self.lang_var.get()]["popup_error_title"], str(e))

        btn_save = ttk.Button(btn_row, command=lambda: save_and_close(False))
        btn_save.pack(side="left", padx=(0, 6))
        popup_buttons.append((btn_save, "edit_save"))

        btn_save_as = ttk.Button(btn_row, command=lambda: save_and_close(True))
        btn_save_as.pack(side="left", padx=6)
        popup_buttons.append((btn_save_as, "edit_save_as"))

        btn_cancel = ttk.Button(btn_row, command=win.destroy)
        btn_cancel.pack(side="right")
        popup_buttons.append((btn_cancel, "edit_cancel"))

        def on_close():
            self._edit_popup_refresh = None
            win.destroy()

        win.protocol("WM_DELETE_WINDOW", on_close)
        self._edit_popup_refresh = refresh_popup_lang
        refresh_popup_lang()

    def view_file(self):
        f = self._get_selected_file()
        if not f: return
        try:
            content = f.read_text(encoding="utf-8")
        except Exception as e:
            messagebox.showerror(UI_STRINGS[self.lang_var.get()]["popup_error_title"], str(e)); return
        win = tk.Toplevel(self.root)
        win.title(UI_STRINGS[self.lang_var.get()]["popup_view_title"].format(filename=f.name))
        win.geometry("850x620")
        win.resizable(True, True)
        bar = ttk.Frame(win); bar.pack(fill="x", padx=8, pady=4)
        ttk.Label(bar, text=f.name, font=("Arial", 10, "bold")).pack(side="left")
        ttk.Button(bar, text=UI_STRINGS[self.lang_var.get()]["popup_close"], command=win.destroy).pack(side="right")
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
            title=UI_STRINGS[self.lang_var.get()]["sel_copy_file"], initialdir=str(self.work_dir),
            defaultextension=".NBFM", initialfile=f"{f.stem}_copie_{now}.NBFM",
            filetypes=[("NBFM files", "*.NBFM"), ("Tous", "*.*")]
        )
        if dest:
            try:
                shutil.copy2(str(f), dest)
                self.refresh_files()
                self.set_status(UI_STRINGS[self.lang_var.get()]["status_file_copied"].format(filename=Path(dest).name))
            except Exception as e:
                messagebox.showerror(UI_STRINGS[self.lang_var.get()]["popup_copy_error_title"], str(e))

    def delete_file(self):
        f = self._get_selected_file()
        if not f: return
        T = UI_STRINGS[self.lang_var.get()]
        if messagebox.askyesno(T["sel_delete_confirm_title"], T["sel_delete_confirm_text"].format(filename=f.name)):
            try:
                f.unlink(); self.refresh_files()
                self.set_status(UI_STRINGS[self.lang_var.get()]["status_file_deleted"].format(filename=f.name))
            except Exception as e:
                messagebox.showerror(UI_STRINGS[self.lang_var.get()]["popup_error_title"], str(e))


# ─────────────────────────────────────────────────────────────────────────────
# ENTRÉE
# ─────────────────────────────────────────────────────────────────────────────

def main():
    check_dependencies()
    root = tk.Tk()
    NBFMApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()