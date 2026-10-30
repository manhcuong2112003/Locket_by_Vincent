#!/usr/bin/env python3
"""
Tr?nh x? l? & k? chuy?n bi?t cho LOCKET WIDGET (com.locket.Locket)
Quy c?ch kh?c bi?t ho?n to?n v?i Game:
1. T?i IPA g?c v? m?y/CI v? gi?i n?n Payload/Locket.app.
2. G? b? to?n b? th? m?c PlugIns/*.appex (Widget Extension, Notification Extension)
   v? c?c .appex n?y y?u c?u App Group 'group.com.locket.Locket-Shared' ch?nh ch? c?a Locket Labs,
   khi k? b?ng ch?ng ch? doanh nghi?p b?n th? 3 s? khi?n iOS kill app ngay l?c m? (v?ng app).
3. ??ng b? CFBundleIdentifier trong Info.plist tr?ng kh?p v?i GoogleService-Info.plist (com.locket.Locket).
4. ??ng g?i l?i file IPA s?ch (Clean IPA) tr??c khi k? b?ng ch?ng ch? doanh nghi?p.
"""

import json
import os
import plistlib
import shutil
import tempfile
import time
import urllib.request
import zipfile

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config_locket.json")
HEADERS = {
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15"
}


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def patch_locket_ipa(source_ipa_path, output_ipa_path, cfg):
    """
    Gi?i n?n IPA Locket, x?a PlugIns/*.appex g?y xung ??t App Group v? ??ng b? Bundle ID.
    """
    spec = cfg["signing_spec"]
    target_bundle_id = cfg["app"].get("bundle_id", "com.locket.Locket")

    with tempfile.TemporaryDirectory() as tmpdir:
        with zipfile.ZipFile(source_ipa_path, "r") as zf:
            zf.extractall(tmpdir)

        payload_dir = os.path.join(tmpdir, "Payload")
        app_dirs = [d for d in os.listdir(payload_dir) if d.endswith(".app")]
        if not app_dirs:
            raise RuntimeError("Kh?ng t?m th?y th? m?c .app trong Payload c?a Locket IPA")

        app_path = os.path.join(payload_dir, app_dirs[0])

        # 1. X?a th? m?c PlugIns/*.appex (nguy?n nh?n s? 1 g?y v?ng app do l?ch App Group)
        if spec.get("strip_plugins_appex", True):
            plugins_dir = os.path.join(app_path, "PlugIns")
            if os.path.isdir(plugins_dir):
                shutil.rmtree(plugins_dir)
                print("[Locket Patcher] ?? g? b? th? m?c PlugIns/*.appex ?? ch?ng v?ng App Group.")

        # 2. ??ng b? Bundle ID trong Info.plist
        info_plist_path = os.path.join(app_path, "Info.plist")
        if os.path.isfile(info_plist_path):
            with open(info_plist_path, "rb") as f:
                info_data = plistlib.load(f)
            info_data["CFBundleIdentifier"] = target_bundle_id
            with open(info_plist_path, "wb") as f:
                plistlib.dump(info_data, f)
            print(f"[Locket Patcher] ?? c? ??nh CFBundleIdentifier = {target_bundle_id}")

        # 3. ??ng b? BUNDLE_ID trong GoogleService-Info.plist (tr?nh Firebase crash l?c m? app)
        if spec.get("sync_google_service_plist", True):
            gs_plist_path = os.path.join(app_path, "GoogleService-Info.plist")
            if os.path.isfile(gs_plist_path):
                with open(gs_plist_path, "rb") as f:
                    gs_data = plistlib.load(f)
                gs_data["BUNDLE_ID"] = target_bundle_id
                with open(gs_plist_path, "wb") as f:
                    plistlib.dump(gs_data, f)
                print(f"[Locket Patcher] ?? ??ng b? GoogleService-Info.plist BUNDLE_ID = {target_bundle_id}")

        # 4. ??ng g?i l?i th?nh file IPA s?ch
        with zipfile.ZipFile(output_ipa_path, "w", zipfile.ZIP_DEFLATED) as zout:
            for root, _, files in os.walk(tmpdir):
                for file in files:
                    full_path = os.path.join(root, file)
                    rel_path = os.path.relpath(full_path, tmpdir)
                    zout.write(full_path, rel_path)

    print(f"[Locket Patcher] ?? t?o IPA s?ch t?i: {output_ipa_path}")
    return output_ipa_path


if __name__ == "__main__":
    cfg = load_config()
    print(f"?? t?i c?u h?nh chuy?n bi?t cho {cfg['app']['name']} ({cfg['app']['bundle_id']})")
