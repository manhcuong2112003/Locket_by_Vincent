#!/usr/bin/env python3
"""
Tr?nh k? t? ??ng chuy?n bi?t cho GAME iOS (Asphalt 8 Airborne, v.v.)
Quy c?ch:
- D?ng c? ch? Remote Sign (Zero-Bandwidth) v? file Game n?ng h?ng GB (2.82 GB).
- Game ??c l?p kh?ng ch?a Widget Extension (.appex) n?n ??i Bundle ID t? ??ng (com.ipaomtk.auto) v?n m? m??t, kh?ng b? v?ng.
"""

import json
import os
import time
import urllib.parse
import urllib.request

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config_game.json")
HEADERS = {
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15"
}


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def remote_sign_game(cfg, cert_id):
    api = cfg["signtools_api"]
    app = cfg["app"]
    spec = cfg["signing_spec"]
    payload = urllib.parse.urlencode({
        "ipa": app["remote_ipa_url"],
        "cert": cert_id,
        "bundle": spec.get("bundle_mode", "com.ipaomtk.auto"),
        "name": app["name"]
    }).encode("utf-8")

    req = urllib.request.Request(
        api["remote_sign_start"],
        data=payload,
        headers={**HEADERS, "Content-Type": "application/x-www-form-urlencoded"},
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        start_data = json.loads(resp.read().decode("utf-8"))

    job_id = start_data.get("id") or start_data.get("job_id")
    if not job_id:
        raise RuntimeError(f"Kh?ng l?y ???c job_id khi k? Game: {start_data}")

    deadline = time.time() + spec.get("timeout_seconds", 360)
    while time.time() < deadline:
        status_url = f"{api['remote_sign_status']}?id={urllib.parse.quote(str(job_id))}"
        req_st = urllib.request.Request(status_url, headers=HEADERS)
        with urllib.request.urlopen(req_st, timeout=20) as resp_st:
            st = json.loads(resp_st.read().decode("utf-8"))
        if st.get("status") == "done" or st.get("plist"):
            plist_url = st.get("plist") or st.get("manifest_url")
            ipa_out = st.get("ipa") or st.get("ipa_url", "")
            return {
                "manifest_url": plist_url,
                "install_url": f"itms-services://?action=download-manifest&url={urllib.parse.quote(plist_url, safe='')}",
                "ipa_url": ipa_out,
                "signed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "status": "active"
            }
        if st.get("status") == "error":
            raise RuntimeError(f"L?i t? m?y ch? k? Game: {st}")
        time.sleep(4)

    raise TimeoutError("Qu? th?i gian ch? k? file Game (2.82 GB)")


def run_once():
    cfg = load_config()
    servers = []
    for cert in cfg["preferred_certificates"]:
        try:
            print(f"[Game Signer] ?ang k? {cfg['app']['name']} v?i {cert['label']}...")
            res = remote_sign_game(cfg, cert["id"])
            servers.append({
                "cert_id": cert["id"],
                "label": cert["label"],
                "badge": cert["badge"],
                **res
            })
            print(f"[Game Signer] Th?nh c?ng: {res['manifest_url']}")
        except Exception as e:
            print(f"[Game Signer] Th?t b?i ({cert['label']}): {e}")

    cache_path = os.path.join(BASE_DIR, cfg["app"]["cache_file"])
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump({
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "app": cfg["app"],
            "servers": servers
        }, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    run_once()
