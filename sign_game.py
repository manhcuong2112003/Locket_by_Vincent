#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Trình ký tự động chuyên biệt cho GAME iOS (Asphalt 8 Airborne, v.v.)
Quy cách:
- Dùng cơ chế Remote Sign (Zero-Bandwidth) vì file Game nặng hàng GB (2.82 GB).
- Game độc lập không chứa Widget Extension (.appex) nên đổi Bundle ID tự động (com.ipaomtk.auto) vẫn mở mượt, không bị văng.
- Tự động kiểm tra link sống trước khi ký lại và đồng bộ kết quả sang cả links_cache_game.json, links_cache.json + index.html.
"""

import argparse
import json
import os
import re
import time
import urllib.parse
import urllib.request

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config_game.json")
HEADERS = {
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
    "Origin": "https://signtools.ipaomtk.com",
    "Referer": "https://signtools.ipaomtk.com/"
}


def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def check_manifest_alive(manifest_url: str) -> bool:
    if not manifest_url:
        return False
    try:
        req = urllib.request.Request(
            manifest_url,
            headers={"User-Agent": "itunesstored/1.0 iOS/17.0 model/iPhone14,5"}
        )
        with urllib.request.urlopen(req, timeout=12) as resp:
            if resp.status != 200:
                return False
            body = resp.read().decode("utf-8", errors="ignore")
            if "<plist" not in body or "software-package" not in body:
                return False
            m = re.search(r"<string>(https?://[^<]+\.ipa)</string>", body)
            if m:
                ipa_req = urllib.request.Request(
                    m.group(1),
                    headers={"User-Agent": "itunesstored/1.0 iOS/17.0", "Range": "bytes=0-63"}
                )
                with urllib.request.urlopen(ipa_req, timeout=12) as ipa_resp:
                    return ipa_resp.status in (200, 206)
            return True
    except Exception:
        return False


def load_existing_servers(cfg: dict) -> dict:
    by_cert = {}
    for fname in (cfg["app"].get("cache_file", "links_cache_game.json"), cfg["app"].get("shared_cache_file", "links_cache.json")):
        fpath = os.path.join(BASE_DIR, fname)
        if os.path.exists(fpath):
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                srvs = data.get("servers", [])
                if "apps" in data and cfg["app"]["id"] in data["apps"]:
                    srvs = data["apps"][cfg["app"]["id"]].get("servers", srvs)
                for s in srvs:
                    if s.get("cert_id") and s["cert_id"] not in by_cert:
                        by_cert[s["cert_id"]] = s
            except Exception:
                pass
    return by_cert


def remote_sign_game(cfg: dict, cert_id: str) -> dict:
    api = cfg["signtools_api"]
    app = cfg["app"]
    spec = cfg["signing_spec"]

    payload = urllib.parse.urlencode({
        "certificate_mode": "server",
        "server_certificate": cert_id,
        "bundle": spec.get("bundle_mode", "com.ipaomtk.auto"),
        "ipa_url": app["remote_ipa_url"],
        "app_name": app["name"]
    }).encode("utf-8")

    req = urllib.request.Request(
        api["remote_sign_start"],
        data=payload,
        headers={**HEADERS, "Content-Type": "application/x-www-form-urlencoded"},
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        start_data = json.loads(resp.read().decode("utf-8"))

    job_id = start_data.get("jobId") or start_data.get("id") or start_data.get("job_id")
    if not start_data.get("ok", True) or not job_id:
        raise RuntimeError(f"Không lấy được jobId khi ký Game: {start_data}")

    deadline = time.time() + spec.get("timeout_seconds", 360)
    while time.time() < deadline:
        time.sleep(3)
        status_url = f"{api['remote_sign_status']}?job={urllib.parse.quote(str(job_id))}&t={int(time.time() * 1000)}"
        try:
            req_st = urllib.request.Request(status_url, headers=HEADERS)
            with urllib.request.urlopen(req_st, timeout=20) as resp_st:
                st = json.loads(resp_st.read().decode("utf-8"))
        except Exception as poll_err:
            print(f"[Game Signer] Đang chờ phản hồi từ server ký ({poll_err})...", flush=True)
            continue

        if st.get("status") == "done":
            app_out = st.get("app") or {}
            plist_url = app_out.get("manifestUrl") or st.get("plist") or st.get("manifest_url") or ""
            install_url = app_out.get("installUrl") or st.get("link") or (
                f"itms-services://?action=download-manifest&url={urllib.parse.quote(plist_url, safe='')}"
                if plist_url else ""
            )
            ipa_out = app_out.get("ipaUrl") or st.get("ipa") or st.get("ipa_url", "")
            if not plist_url or not install_url:
                raise RuntimeError(f"Server ký xong nhưng thiếu manifestUrl/installUrl: {st}")
            return {
                "manifest_url": plist_url,
                "install_url": install_url,
                "ipa_url": ipa_out,
                "signed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "status": "active"
            }

        if st.get("status") == "error" or st.get("ok") is False:
            raise RuntimeError(f"Lỗi từ máy chủ ký Game: {st.get('error') or st}")

    raise TimeoutError(f"Quá thời gian chờ ký file Game ({app['name']} — {app.get('size', '2.82 GB')})")


def sync_to_shared_portal(cfg: dict, servers: list) -> None:
    shared_name = cfg["app"].get("shared_cache_file", "links_cache.json")
    shared_path = os.path.join(BASE_DIR, shared_name)
    if not os.path.exists(shared_path):
        return
    try:
        with open(shared_path, "r", encoding="utf-8") as f:
            shared = json.load(f)
        app_id = cfg["app"]["id"]
        if "apps" in shared and app_id in shared["apps"]:
            shared["apps"][app_id]["servers"] = servers
            shared["apps"][app_id]["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
            shared["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
            with open(shared_path, "w", encoding="utf-8") as f:
                json.dump(shared, f, ensure_ascii=False, indent=2)
            import auto_sign_manager
            auto_sign_manager.update_html_file(auto_sign_manager.load_config(), shared)
    except Exception as e:
        print(f"[Game Signer] Lưu ý khi đồng bộ sang {shared_name}: {e}", flush=True)


def run_once(force: bool = False) -> list:
    cfg = load_config()
    existing_by_cert = load_existing_servers(cfg)
    servers = []
    for cert in cfg["preferred_certificates"]:
        cid = cert["id"]
        existing = existing_by_cert.get(cid)
        if not force and existing and check_manifest_alive(existing.get("manifest_url", "")):
            print(f"[Game Signer] ✔ Link {cert['label']} đang hoạt động tốt: {existing['manifest_url']}", flush=True)
            servers.append({
                **existing,
                "cert_id": cid,
                "label": cert["label"],
                "badge": cert["badge"]
            })
            continue

        try:
            print(f"[Game Signer] ⏳ Đang ký {cfg['app']['name']} với {cert['label']}...", flush=True)
            res = remote_sign_game(cfg, cid)
            servers.append({
                "cert_id": cid,
                "label": cert["label"],
                "badge": cert["badge"],
                **res
            })
            print(f"[Game Signer] ✅ Thành công: {res['manifest_url']}", flush=True)
        except Exception as e:
            print(f"[Game Signer] ❌ Thất bại ({cert['label']}): {e}", flush=True)

    cache_path = os.path.join(BASE_DIR, cfg["app"]["cache_file"])
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump({
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "app": cfg["app"],
            "servers": servers
        }, f, ensure_ascii=False, indent=2)

    if servers:
        sync_to_shared_portal(cfg, servers)
    return servers


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Trình ký tự động chuyên biệt cho Game iOS")
    parser.add_argument("--force", action="store_true", help="Bắt buộc ký lại toàn bộ các Server chứng chỉ")
    args = parser.parse_args()
    run_once(force=args.force)
