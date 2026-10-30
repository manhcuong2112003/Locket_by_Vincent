#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Trình xử lý & ký chuyên biệt cho LOCKET WIDGET (com.locket.Locket)
Giải quyết triệt để bài toán: Vừa chống văng App trên chứng chỉ doanh nghiệp, vừa giữ được Widget ngoài Màn hình khóa/chính!

Hỗ trợ 3 chế độ xử lý (tùy chọn qua --mode hoặc config_locket.json):
1. Chế độ "dual_clone" (Khuyên dùng số 1 — Có Widget 100% + Không bao giờ văng):
   - Đóng gói bản IPA thành "Locket Gold" (Bundle ID: com.locket.Locket.gold) để cài SONG SONG với Locket chính chủ từ App Store (com.locket.Locket).
   - Gỡ bỏ các .appex gây xung đột trong bản IPA, đồng bộ GoogleService-Info.plist trùng khớp tuyệt đối với Bundle ID sau khi ký.
   - Bản App Store đảm nhiệm hiển thị Widget Màn hình khóa & Màn hình chính chính chủ Apple (100% không lỗi), bản Locket Gold đảm nhiệm chụp/đăng ảnh từ thư viện & tính năng VIP!
2. Chế độ "smart_widget" (Giữ LocketWidgetExtension.appex trên Chứng chỉ có App Group như Beihang / Rakuten):
   - Chỉ xóa 2 extension phụ gây crash ngầm (LocketNotificationServiceExtension.appex, LocketWidgetLocationExtension.appex).
   - Giữ nguyên LocketWidgetExtension.appex, LocketWidgetIntent.appex, LocketWidgetIntentUI.appex.
   - Tự động tính toán chính xác Bundle ID đầu ra của signtools (<bundle>.<sanitized_filename>) và đồng bộ đồng loạt:
     + Payload/Locket.app/Info.plist -> CFBundleIdentifier
     + Payload/Locket.app/GoogleService-Info.plist -> BUNDLE_ID
     + Payload/Locket.app/PlugIns/*.appex/Info.plist -> <MainBundleID>.<ExtensionSuffix>
     + Payload/Locket.app/PlugIns/*.appex/GoogleService-Info.plist -> BUNDLE_ID
3. Chế độ "clean" (Gỡ toàn bộ PlugIns/*.appex để mở độc lập nhanh, nhẹ, chống văng tuyệt đối).
"""

import argparse
import io
import json
import os
import plistlib
import re
import shutil
import tempfile
import time
import urllib.parse
import urllib.request
import zipfile

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config_locket.json")
HEADERS = {
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
    "Origin": "https://signtools.ipaomtk.com",
    "Referer": "https://signtools.ipaomtk.com/"
}


def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def compute_signtools_final_bundle_id(bundle_param: str, ipa_filename: str) -> str:
    """
    Máy chủ signtools.ipaomtk.com tự động nối thêm hậu tố tên file IPA đã làm sạch
    vào sau tham số `bundle` (VD: bundle='com.locket.Locket' + file='Locket-Widget-IPAOMTK.com.ipa'
    -> 'com.locket.Locket.locketwidgetipaomtkcom').
    Hàm này tính chính xác CFBundleIdentifier cuối cùng để đồng bộ GoogleService-Info.plist khớp 100%.
    """
    stem = re.sub(r"\.ipa$", "", os.path.basename(ipa_filename), flags=re.IGNORECASE)
    clean_stem = re.sub(r"[^a-z0-9]", "", stem.lower())
    if clean_stem:
        return f"{bundle_param}.{clean_stem}"
    return bundle_param


def patch_locket_ipa(
    source_ipa_path: str,
    output_ipa_path: str,
    cfg: dict,
    mode: str = "smart_widget",
    cert_id: str = ""
) -> dict:
    """
    Giải nén IPA Locket, xử lý PlugIns/*.appex theo chế độ (dual_clone / smart_widget / clean),
    và đồng bộ toàn diện Info.plist + GoogleService-Info.plist cho cả App chính lẫn Widget Extension.
    """
    spec = cfg["signing_spec"]
    app_cfg = cfg["app"]

    if mode == "dual_clone":
        base_bundle_id = app_cfg.get("clone_bundle_id", "com.locket.Locket.gold")
        display_name = app_cfg.get("clone_name", "Locket Gold")
    else:
        base_bundle_id = app_cfg.get("bundle_id", "com.locket.Locket")
        display_name = app_cfg.get("name", "Locket Widget")

    final_bundle_id = compute_signtools_final_bundle_id(base_bundle_id, output_ipa_path)

    with tempfile.TemporaryDirectory() as tmpdir:
        with zipfile.ZipFile(source_ipa_path, "r") as zf:
            zf.extractall(tmpdir)

        payload_dir = os.path.join(tmpdir, "Payload")
        app_dirs = [d for d in os.listdir(payload_dir) if d.endswith(".app")]
        if not app_dirs:
            raise RuntimeError("Không tìm thấy thư mục .app trong Payload của Locket IPA")

        app_path = os.path.join(payload_dir, app_dirs[0])
        plugins_dir = os.path.join(app_path, "PlugIns")

        # 1. Xử lý thư mục PlugIns/*.appex theo từng chế độ
        if os.path.isdir(plugins_dir):
            if mode in ("clean", "dual_clone"):
                shutil.rmtree(plugins_dir)
                print(f"[Locket Patcher] ({mode}) Đã gỡ bỏ PlugIns/*.appex để chống xung đột App Group & chạy song song mượt với bản App Store.")
            elif mode == "smart_widget":
                crash_exts = set(spec.get("strip_crash_extensions", [
                    "LocketNotificationServiceExtension.appex",
                    "LocketWidgetLocationExtension.appex"
                ]))
                for entry in os.listdir(plugins_dir):
                    ext_path = os.path.join(plugins_dir, entry)
                    if entry in crash_exts and os.path.isdir(ext_path):
                        shutil.rmtree(ext_path)
                        print(f"[Locket Patcher] Đã gỡ extension phụ gây xung đột ngầm: {entry}")
                    elif entry.endswith(".appex") and os.path.isdir(ext_path):
                        # Đồng bộ Info.plist và GoogleService-Info.plist bên trong từng Widget .appex giữ lại
                        ext_info_path = os.path.join(ext_path, "Info.plist")
                        if os.path.isfile(ext_info_path):
                            with open(ext_info_path, "rb") as f:
                                ext_info = plistlib.load(f)
                            old_ext_bid = ext_info.get("CFBundleIdentifier", "")
                            suffix = old_ext_bid.split(".")[-1] if "." in old_ext_bid else entry.replace(".appex", "")
                            new_ext_bid = f"{final_bundle_id}.{suffix}"
                            ext_info["CFBundleIdentifier"] = new_ext_bid
                            with open(ext_info_path, "wb") as f:
                                plistlib.dump(ext_info, f)
                            print(f"[Locket Patcher] Đã đồng bộ Widget {entry} CFBundleIdentifier = {new_ext_bid}")

                        ext_gs_path = os.path.join(ext_path, "GoogleService-Info.plist")
                        if os.path.isfile(ext_gs_path):
                            with open(ext_gs_path, "rb") as f:
                                ext_gs = plistlib.load(f)
                            ext_gs["BUNDLE_ID"] = final_bundle_id
                            with open(ext_gs_path, "wb") as f:
                                plistlib.dump(ext_gs, f)
                            print(f"[Locket Patcher] Đã đồng bộ {entry}/GoogleService-Info.plist BUNDLE_ID = {final_bundle_id}")

        # 2. Đồng bộ Bundle ID & Tên hiển thị trong Payload/Locket.app/Info.plist
        info_plist_path = os.path.join(app_path, "Info.plist")
        if os.path.isfile(info_plist_path):
            with open(info_plist_path, "rb") as f:
                info_data = plistlib.load(f)
            info_data["CFBundleIdentifier"] = final_bundle_id
            if mode == "dual_clone":
                info_data["CFBundleDisplayName"] = display_name
                info_data["CFBundleName"] = display_name
            with open(info_plist_path, "wb") as f:
                plistlib.dump(info_data, f)
            print(f"[Locket Patcher] Đã cập nhật Info.plist: CFBundleIdentifier = {final_bundle_id} ({display_name})")

        # 3. Đồng bộ BUNDLE_ID trong Payload/Locket.app/GoogleService-Info.plist
        if spec.get("sync_google_service_plist", True):
            gs_plist_path = os.path.join(app_path, "GoogleService-Info.plist")
            if os.path.isfile(gs_plist_path):
                with open(gs_plist_path, "rb") as f:
                    gs_data = plistlib.load(f)
                gs_data["BUNDLE_ID"] = final_bundle_id
                with open(gs_plist_path, "wb") as f:
                    plistlib.dump(gs_data, f)
                print(f"[Locket Patcher] Đã đồng bộ GoogleService-Info.plist: BUNDLE_ID = {final_bundle_id}")

        # 4. Đóng gói lại thành file IPA sạch
        with zipfile.ZipFile(output_ipa_path, "w", zipfile.ZIP_DEFLATED) as zout:
            for root, _, files in os.walk(tmpdir):
                for file in files:
                    full_path = os.path.join(root, file)
                    rel_path = os.path.relpath(full_path, tmpdir)
                    zout.write(full_path, rel_path)

    print(f"[Locket Patcher] ✅ Đã đóng gói IPA hoàn chỉnh tại: {output_ipa_path}")
    return {
        "ipa_path": output_ipa_path,
        "base_bundle_id": base_bundle_id,
        "final_bundle_id": final_bundle_id,
        "display_name": display_name,
        "mode": mode
    }


def upload_and_sign_patched_ipa(cfg: dict, patched_info: dict, cert_id: str) -> dict:
    """
    Upload bản IPA Locket đã patch lên endpoint sign-merge.php để ký bằng chứng chỉ doanh nghiệp.
    """
    merge_url = cfg["signtools_api"]["local_sign_merge"]
    local_ipa = patched_info["ipa_path"]
    boundary = f"----WebKitFormBoundary{int(time.time() * 1000)}"

    fields = {
        "certificate_mode": "server",
        "server_certificate": cert_id,
        "bundle": patched_info["base_bundle_id"],
        "custom_name": patched_info["display_name"],
        "mode": "custom_ipa"
    }

    body = io.BytesIO()
    for k, v in fields.items():
        body.write(f"--{boundary}\r\n".encode("utf-8"))
        body.write(f'Content-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode("utf-8"))

    filename = os.path.basename(local_ipa)
    body.write(f"--{boundary}\r\n".encode("utf-8"))
    body.write(f'Content-Disposition: form-data; name="custom_ipa"; filename="{filename}"\r\n'.encode("utf-8"))
    body.write(b"Content-Type: application/octet-stream\r\n\r\n")
    with open(local_ipa, "rb") as f:
        body.write(f.read())
    body.write(f"\r\n--{boundary}--\r\n".encode("utf-8"))

    req_headers = {
        **HEADERS,
        "Content-Type": f"multipart/form-data; boundary={boundary}"
    }
    req = urllib.request.Request(merge_url, data=body.getvalue(), headers=req_headers, method="POST")
    with urllib.request.urlopen(req, timeout=240) as resp:
        payload = json.loads(resp.read().decode("utf-8"))

    if not payload.get("ok"):
        raise RuntimeError(payload.get("error") or payload.get("message") or "Lỗi khi ký qua sign-merge.php")

    app_out = payload.get("app") or payload.get("customApp") or (payload.get("apps")[0] if payload.get("apps") else {})
    manifest_url = app_out.get("manifestUrl") or ""
    install_url = app_out.get("installUrl") or ""
    ipa_url = app_out.get("ipaUrl") or ""
    if not manifest_url or not install_url:
        raise RuntimeError(f"sign-merge.php không trả về manifestUrl/installUrl: {payload}")

    return {
        "manifest_url": manifest_url,
        "install_url": install_url,
        "ipa_url": ipa_url,
        "signed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "status": "active"
    }


def remote_sign_locket(cfg: dict, cert_id: str, bundle_override: str = "") -> dict:
    """
    Ký Locket trực tiếp qua Remote Sign API (tạo bản cài đặt song song cùng bản App Store).
    Vì signtools tự động đổi Bundle ID sang com.locket.Locket.locketwidgetipaomtkcom (khác với
    com.locket.Locket của App Store), người dùng có thể cài CẢ 2 BẢN trên cùng 1 iPhone:
    - Bản App Store: giữ Widget ngoài màn hình chính & màn hình khóa 100% chính chủ Apple.
    - Bản IPA đã ký: mở khóa tính năng mở rộng (IPAOMTK-real.dylib).
    """
    api = cfg["signtools_api"]
    app = cfg["app"]
    spec = cfg["signing_spec"]

    payload = urllib.parse.urlencode({
        "certificate_mode": "server",
        "server_certificate": cert_id,
        "bundle": bundle_override or app.get("bundle_id", "com.locket.Locket"),
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

    job_id = start_data.get("jobId") or start_data.get("id")
    if not start_data.get("ok", True) or not job_id:
        raise RuntimeError(f"Không tạo được job ký Locket: {start_data}")

    deadline = time.time() + spec.get("timeout_seconds", 240)
    while time.time() < deadline:
        time.sleep(3)
        status_url = f"{api['remote_sign_status']}?job={urllib.parse.quote(str(job_id))}&t={int(time.time() * 1000)}"
        try:
            req_st = urllib.request.Request(status_url, headers=HEADERS)
            with urllib.request.urlopen(req_st, timeout=20) as resp_st:
                st = json.loads(resp_st.read().decode("utf-8"))
        except Exception:
            continue

        if st.get("status") == "done":
            app_out = st.get("app") or {}
            manifest_url = app_out.get("manifestUrl") or ""
            install_url = app_out.get("installUrl") or st.get("link") or ""
            ipa_url = app_out.get("ipaUrl") or ""
            if not manifest_url or not install_url:
                raise RuntimeError("Server ký xong nhưng thiếu manifestUrl/installUrl.")
            return {
                "manifest_url": manifest_url,
                "install_url": install_url,
                "ipa_url": ipa_url,
                "signed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "status": "active"
            }

        if st.get("status") == "error" or st.get("ok") is False:
            raise RuntimeError(f"Lỗi từ máy chủ ký Locket: {st.get('error') or st}")

    raise TimeoutError("Quá thời gian chờ ký Locket Widget")


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
            shared["apps"][app_id]["appstore_url"] = cfg["app"].get("appstore_url", "https://apps.apple.com/app/locket-widget/id1600525061")
            shared["apps"][app_id]["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
            shared["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
            with open(shared_path, "w", encoding="utf-8") as f:
                json.dump(shared, f, ensure_ascii=False, indent=2)
            import auto_sign_manager
            auto_sign_manager.update_html_file(auto_sign_manager.load_config(), shared)
    except Exception as e:
        print(f"[Locket Signer] Lưu ý khi đồng bộ sang {shared_name}: {e}")


def check_manifest_alive(manifest_url: str) -> bool:
    if not manifest_url or "Locket-signed-" not in manifest_url:
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


def load_existing_patched_servers(cfg: dict) -> dict:
    by_cert = {}
    for fname in (cfg["app"].get("cache_file", "links_cache_locket.json"), cfg["app"].get("shared_cache_file", "links_cache.json")):
        fpath = os.path.join(BASE_DIR, fname)
        if os.path.exists(fpath):
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                srvs = data.get("servers", [])
                if "apps" in data and cfg["app"]["id"] in data["apps"]:
                    srvs = data["apps"][cfg["app"]["id"]].get("servers", srvs)
                for s in srvs:
                    cid = s.get("cert_id")
                    murl = s.get("manifest_url", "")
                    if cid and "Locket-signed-" in murl and cid not in by_cert:
                        by_cert[cid] = s
            except Exception:
                pass
    return by_cert


def run_once(local_patch: bool = True, patch_mode: str = "clean", force: bool = False) -> list:
    cfg = load_config()
    existing_by_cert = load_existing_patched_servers(cfg)
    servers = []
    missing_certs = []

    for cert in cfg["preferred_certificates"]:
        cid = cert["id"]
        existing = existing_by_cert.get(cid)
        if not force and existing and check_manifest_alive(existing.get("manifest_url", "")):
            print(f"[Locket Signer] ✔ Link đã patch của {cert['label']} đang hoạt động tốt: {existing['manifest_url']}")
            servers.append({
                **existing,
                "cert_id": cid,
                "label": cert["label"],
                "badge": cert["badge"]
            })
        else:
            missing_certs.append(cert)

    patched_info = None
    tmp_dir = None
    if local_patch and missing_certs:
        tmp_dir = tempfile.mkdtemp(prefix="locket_patch_")
        raw_ipa = os.path.join(tmp_dir, "Locket-Original.ipa")
        out_ipa = os.path.join(tmp_dir, "Locket.ipa")
        print(f"[Locket Signer] ⬇️ Đang tải IPA gốc từ {cfg['app']['remote_ipa_url']}...")
        req = urllib.request.Request(cfg["app"]["remote_ipa_url"], headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=180) as resp, open(raw_ipa, "wb") as out_f:
            shutil.copyfileobj(resp, out_f)
        patched_info = patch_locket_ipa(raw_ipa, out_ipa, cfg, mode=patch_mode)

    try:
        for cert in missing_certs:
            try:
                print(f"[Locket Signer] ⏳ Đang ký {cfg['app']['name']} với {cert['label']}...")
                if patched_info:
                    try:
                        res = upload_and_sign_patched_ipa(cfg, patched_info, cert["id"])
                    except Exception as up_err:
                        print(f"[Locket Signer] ⚠️ Upload IPA patch thất bại ({up_err}), chuyển sang Remote Sign...")
                        res = remote_sign_locket(cfg, cert["id"])
                else:
                    res = remote_sign_locket(cfg, cert["id"])

                servers.append({
                    "cert_id": cert["id"],
                    "label": cert["label"],
                    "badge": cert["badge"],
                    **res
                })
                print(f"[Locket Signer] ✅ Thành công: {res['manifest_url']}")
            except Exception as e:
                print(f"[Locket Signer] ❌ Thất bại ({cert['label']}): {e}")
    finally:
        if tmp_dir and os.path.isdir(tmp_dir):
            shutil.rmtree(tmp_dir, ignore_errors=True)

    # Thêm tùy chọn cài song song Bản App Store Chính Chủ ở cuối danh sách để giữ Widget 100%
    appstore_url = cfg["app"].get("appstore_url", "https://apps.apple.com/app/locket-widget/id1600525061")
    servers.append({
        "cert_id": "apple_appstore_official",
        "label": f"Server {len(servers) + 1} — Bản Gốc App Store (Giữ Widget 100%)",
        "badge": "Chính chủ Apple • Hiện Widget Màn hình khóa",
        "manifest_url": appstore_url,
        "install_url": appstore_url,
        "ipa_url": cfg["app"]["remote_ipa_url"],
        "signed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "ocsp_status": "APPLE_OFFICIAL",
        "status": "active"
    })

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
    parser = argparse.ArgumentParser(description="Trình xử lý & ký chuyên biệt cho Locket Widget")
    parser.add_argument(
        "--local-patch",
        action="store_true",
        help="Tải IPA về máy, giải nén xử lý PlugIns/*.appex + đồng bộ GoogleService-Info.plist rồi upload ký"
    )
    parser.add_argument(
        "--mode",
        choices=["dual_clone", "smart_widget", "clean"],
        default="clean",
        help="Chế độ xử lý IPA: dual_clone (chạy song song App Store để giữ Widget 100%%), smart_widget (giữ LocketWidgetExtension.appex), clean (gỡ toàn bộ .appex)"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Bắt buộc đóng gói và ký mới lại toàn bộ các Server"
    )
    args = parser.parse_args()
    run_once(local_patch=True, patch_mode=args.mode, force=args.force)
