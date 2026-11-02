#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Trình xử lý & ký tự chủ (Self-Hosted ZSign) chuyên biệt cho LOCKET GOLD (com.locket.Locket)
Thực thi đúng kiến trúc tại PLAN.md:
1. Tận dụng nguồn IPA Locket Gold đã giải mã DRM và tích hợp sẵn:
   - Payload/Locket.app/Frameworks/AutoRcSideload.dylib (Mở khóa Locket Gold)
   - Payload/Locket.app/Frameworks/blatantsPatch.dylib (Tự động hook App Group & Keychain chống văng)
2. Gỡ bỏ thư mục Payload/Locket.app/PlugIns/*.appex để tránh xung đột chứng chỉ Enterprise.
3. Tuyệt đối KHÔNG qua signtools.ipaomtk.com (tránh bị tiêm IPAOMTK-real.dylib và bị đổi Bundle ID).
4. Ký sạch đệ quy toàn bộ Frameworks/*.dylib và Locket.app bằng `zsign` với cố định Bundle ID gốc:
   com.locket.Locket
5. Phát hành IPA lên GitHub Releases + tạo manifest.plist OTA tĩnh trên GitHub Pages.
"""

import argparse
import io
import json
import os
import plistlib
import re
import shutil
import subprocess
import tempfile
import time
import urllib.parse
import urllib.request
import zipfile

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config_locket.json")
MANIFESTS_DIR = os.path.join(BASE_DIR, "manifests")
CERTS_DIR = os.path.join(BASE_DIR, "certs")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
    "Origin": "https://signtools.ipaomtk.com",
    "Referer": "https://signtools.ipaomtk.com/"
}


def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def ensure_certificate_files(cfg: dict, cert: dict) -> tuple[str, str, str]:
    """
    Đảm bảo bộ file .p12 và .mobileprovision của chứng chỉ luôn sẵn sàng trong thư mục certs/<slug>/.
    Nếu chưa có trên đĩa, tự động tải gói .zip từ endpoint chứng chỉ và giải nén.
    """
    slug = cert.get("slug") or re.sub(r"[^a-z0-9]+", "", cert["id"].lower())
    p12_rel = cert.get("p12", f"certs/{slug}/cert.p12")
    mp_rel = cert.get("mobileprovision", f"certs/{slug}/cert.mobileprovision")
    password = cert.get("password", "AppleP12.com")

    p12_path = os.path.join(BASE_DIR, p12_rel)
    mp_path = os.path.join(BASE_DIR, mp_rel)

    if os.path.isfile(p12_path) and os.path.isfile(mp_path):
        return p12_path, mp_path, password

    dl_base = cfg["signtools_api"].get(
        "certificate_download_endpoint",
        "https://signtools.ipaomtk.com/server-certificate-download.php"
    )
    dl_url = f"{dl_base}?certificate={urllib.parse.quote(cert['id'], safe='')}"
    print(f"[Locket ZSign] ⬇️ Đang tải chứng chỉ gốc {cert['id']}...")
    req = urllib.request.Request(dl_url, headers=HEADERS)
    data = urllib.request.urlopen(req, timeout=20).read()

    cdir = os.path.dirname(p12_path)
    os.makedirs(cdir, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for name in z.namelist():
            raw = z.read(name)
            base = os.path.basename(name)
            if not base:
                continue
            if base.endswith(".p12"):
                with open(p12_path, "wb") as f:
                    f.write(raw)
            elif base.endswith(".mobileprovision"):
                with open(mp_path, "wb") as f:
                    f.write(raw)
            elif base.endswith(".txt"):
                txt = raw.decode("utf-8", errors="ignore")
                for line in txt.splitlines():
                    if "password" in line.lower() or "密码" in line:
                        password = line.split("：")[-1].split(":")[-1].strip()

    if not os.path.isfile(p12_path) or not os.path.isfile(mp_path):
        raise RuntimeError(f"Không trích xuất được .p12/.mobileprovision cho {cert['id']}")

    return p12_path, mp_path, password


def prepare_clean_locket_gold_ipa(source_ipa_path: str, clean_ipa_path: str, cfg: dict) -> dict:
    """
    Làm sạch gói IPA Locket Gold trước khi đưa vào zsign:
    - Xóa bỏ thư mục Payload/Locket.app/PlugIns/*.appex (chống xung đột App Group).
    - Giữ nguyên 100% binary Locket, AutoRcSideload.dylib và blatantsPatch.dylib.
    - Khóa cố định CFBundleIdentifier = com.locket.Locket trong Info.plist & GoogleService-Info.plist.
    """
    fixed_bundle_id = cfg["signing_spec"].get("fixed_bundle_id", "com.locket.Locket")
    version_str = cfg["app"].get("version", "2.71.0")

    with tempfile.TemporaryDirectory() as tmpdir:
        with zipfile.ZipFile(source_ipa_path, "r") as zf:
            zf.extractall(tmpdir)

        payload_dir = os.path.join(tmpdir, "Payload")
        app_dirs = [d for d in os.listdir(payload_dir) if d.endswith(".app")]
        if not app_dirs:
            raise RuntimeError("Không tìm thấy Payload/*.app trong IPA Locket")

        app_path = os.path.join(payload_dir, app_dirs[0])

        # 1. Gỡ bỏ hoàn toàn PlugIns/*.appex
        plugins_dir = os.path.join(app_path, "PlugIns")
        if os.path.isdir(plugins_dir):
            shutil.rmtree(plugins_dir)
            print("[Locket Patcher] ✔ Đã xóa thư mục PlugIns/*.appex (tránh xung đột chứng chỉ Enterprise).")

        # 2. Nếu có IPAOMTK-real.dylib thì gỡ bỏ để tránh xung đột với AutoRcSideload.dylib & blatantsPatch.dylib
        bad_dylib = os.path.join(app_path, "IPAOMTK-real.dylib")
        if os.path.isfile(bad_dylib):
            os.remove(bad_dylib)
            print("[Locket Patcher] ✔ Đã loại bỏ IPAOMTK-real.dylib thừa.")

        # 3. Kiểm tra sự hiện diện của bộ đôi tweak Locket Gold + Sideload Fix
        fw_dir = os.path.join(app_path, "Frameworks")
        found_tweaks = []
        for tw in ("AutoRcSideload.dylib", "blatantsPatch.dylib"):
            if os.path.isfile(os.path.join(fw_dir, tw)):
                found_tweaks.append(tw)
        print(f"[Locket Patcher] ✔ Tweak tích hợp sẵn trong Frameworks: {', '.join(found_tweaks)}")

        # 4. Đảm bảo Info.plist và GoogleService-Info.plist giữ nguyên com.locket.Locket
        info_plist_path = os.path.join(app_path, "Info.plist")
        if os.path.isfile(info_plist_path):
            with open(info_plist_path, "rb") as f:
                info_data = plistlib.load(f)
            info_data["CFBundleIdentifier"] = fixed_bundle_id
            version_str = info_data.get("CFBundleShortVersionString", version_str)
            with open(info_plist_path, "wb") as f:
                plistlib.dump(info_data, f)

        gs_plist_path = os.path.join(app_path, "GoogleService-Info.plist")
        if os.path.isfile(gs_plist_path):
            with open(gs_plist_path, "rb") as f:
                gs_data = plistlib.load(f)
            gs_data["BUNDLE_ID"] = fixed_bundle_id
            with open(gs_plist_path, "wb") as f:
                plistlib.dump(gs_data, f)

        print(f"[Locket Patcher] ✔ Đã cố định Bundle ID gốc: {fixed_bundle_id} (v{version_str})")

        # 5. Đóng gói lại thành file IPA sạch để đưa vào zsign
        with zipfile.ZipFile(clean_ipa_path, "w", zipfile.ZIP_DEFLATED) as zout:
            for root, _, files in os.walk(tmpdir):
                for file in files:
                    full_path = os.path.join(root, file)
                    rel_path = os.path.relpath(full_path, tmpdir)
                    zout.write(full_path, rel_path)

    return {
        "clean_ipa_path": clean_ipa_path,
        "bundle_id": fixed_bundle_id,
        "version": version_str
    }


def generate_ota_manifest(
    manifest_path: str,
    ipa_download_url: str,
    bundle_id: str,
    version: str,
    title: str,
    icon_url: str
) -> None:
    os.makedirs(os.path.dirname(manifest_path), exist_ok=True)
    plist_content = {
        "items": [
            {
                "assets": [
                    {
                        "kind": "software-package",
                        "url": ipa_download_url
                    },
                    {
                        "kind": "display-image",
                        "url": icon_url
                    },
                    {
                        "kind": "full-size-image",
                        "url": icon_url
                    }
                ],
                "metadata": {
                    "bundle-identifier": bundle_id,
                    "bundle-version": version,
                    "kind": "software",
                    "title": title
                }
            }
        ]
    }
    with open(manifest_path, "wb") as f:
        plistlib.dump(plist_content, f)


def get_github_token() -> str:
    tok = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""
    if tok:
        return tok
    try:
        creds = subprocess.check_output(
            ["git", "credential", "fill"],
            input=b"protocol=https\nhost=github.com\nusername=manhcuong2112003\n\n"
        ).decode("utf-8", errors="ignore")
        for line in creds.splitlines():
            if line.startswith("password="):
                return line.split("=", 1)[1].strip()
    except Exception:
        pass
    return ""


def find_zsign_binary() -> str | None:
    for candidate in (
        shutil.which("zsign"),
        os.path.join(BASE_DIR, "zsign.exe"),
        os.path.join(BASE_DIR, "zsign")
    ):
        if candidate and os.path.isfile(candidate):
            return candidate
    return None


def upload_to_github_release(signed_ipa_path: str, release_tag: str, repo: str) -> str:
    """
    Đẩy file IPA đã ký bằng zsign lên GitHub Releases để làm CDN tải trực tiếp tốc độ cao.
    Hỗ trợ cả `gh` CLI lẫn GitHub REST API trực tiếp.
    """
    asset_name = os.path.basename(signed_ipa_path)
    gh_bin = shutil.which("gh")
    if gh_bin and (os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")):
        subprocess.run(
            [gh_bin, "release", "create", release_tag, "--repo", repo, "--title", f"Signed IPA Builds ({release_tag})", "--notes", "Auto-signed Locket Gold IPA builds via zsign"],
            capture_output=True,
            text=True
        )
        subprocess.run(
            [gh_bin, "release", "upload", release_tag, signed_ipa_path, "--repo", repo, "--clobber"],
            check=True
        )
        return f"https://github.com/{repo}/releases/download/{release_tag}/{asset_name}"

    token = get_github_token()
    if not token:
        raise RuntimeError("Không tìm thấy GitHub Token để upload IPA lên GitHub Releases.")

    api_headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "Locket-ZSign-Uploader"
    }

    # 1. Lấy hoặc tạo Release theo tag
    rel_data = None
    try:
        req = urllib.request.Request(f"https://api.github.com/repos/{repo}/releases/tags/{release_tag}", headers=api_headers)
        rel_data = json.loads(urllib.request.urlopen(req, timeout=20).read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            create_req = urllib.request.Request(
                f"https://api.github.com/repos/{repo}/releases",
                data=json.dumps({
                    "tag_name": release_tag,
                    "name": f"Signed IPA Builds ({release_tag})",
                    "body": "Auto-signed Locket Gold IPA builds via zsign (Bundle ID: com.locket.Locket)"
                }).encode("utf-8"),
                headers={**api_headers, "Content-Type": "application/json"},
                method="POST"
            )
            rel_data = json.loads(urllib.request.urlopen(create_req, timeout=20).read().decode("utf-8"))
        else:
            raise

    # 2. Nếu asset cùng tên đã tồn tại thì xóa asset cũ để ghi đè (clobber)
    for asset in rel_data.get("assets", []):
        if asset.get("name") == asset_name:
            del_req = urllib.request.Request(
                f"https://api.github.com/repos/{repo}/releases/assets/{asset['id']}",
                headers=api_headers,
                method="DELETE"
            )
            urllib.request.urlopen(del_req, timeout=20).read()

    # 3. Upload file nhị phân lên uploads.github.com
    upload_url = f"https://uploads.github.com/repos/{repo}/releases/{rel_data['id']}/assets?name={urllib.parse.quote(asset_name)}"
    with open(signed_ipa_path, "rb") as f:
        ipa_bytes = f.read()

    up_req = urllib.request.Request(
        upload_url,
        data=ipa_bytes,
        headers={
            **api_headers,
            "Content-Type": "application/octet-stream",
            "Content-Length": str(len(ipa_bytes))
        },
        method="POST"
    )
    print(f"[Locket ZSign] ☁️ Đang upload {asset_name} ({len(ipa_bytes) / 1048576:.1f} MB) lên GitHub Releases...")
    urllib.request.urlopen(up_req, timeout=300).read()
    return f"https://github.com/{repo}/releases/download/{release_tag}/{asset_name}"


def sign_with_zsign(
    clean_info: dict,
    cert: dict,
    cfg: dict,
    out_dir: str
) -> dict:
    zsign_bin = find_zsign_binary()
    if not zsign_bin:
        raise RuntimeError("Chưa cài đặt công cụ `zsign` trên môi trường hiện tại.")

    slug = cert.get("slug") or re.sub(r"[^a-z0-9]+", "", cert["id"].lower())
    p12_path, mp_path, password = ensure_certificate_files(cfg, cert)
    fixed_bundle_id = clean_info["bundle_id"]
    version = clean_info["version"]

    signed_ipa_name = f"LocketGold-{slug}.ipa"
    signed_ipa_path = os.path.join(out_dir, signed_ipa_name)

    cmd = [
        zsign_bin,
        "-k", p12_path,
        "-p", password,
        "-m", mp_path,
        "-b", fixed_bundle_id,
        "-z", "6",
        "-o", signed_ipa_path,
        clean_info["clean_ipa_path"]
    ]
    print(f"[Locket ZSign] 🔐 Đang chạy zsign cho {cert['label']} (Bundle ID: {fixed_bundle_id})...")
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0 or not os.path.isfile(signed_ipa_path):
        raise RuntimeError(f"zsign thất bại ({res.returncode}): {res.stderr or res.stdout}")

    repo = cfg["app"].get("github_repo", "manhcuong2112003/Locket_by_Vincent")
    release_tag = cfg["app"].get("release_tag", "v1.0-signed")
    pages_base = cfg["app"].get("github_pages_base", "https://manhcuong2112003.github.io/Locket_by_Vincent").rstrip("/")

    ipa_url = upload_to_github_release(signed_ipa_path, release_tag, repo)

    manifest_filename = f"locket-{slug}.plist"
    manifest_local_path = os.path.join(MANIFESTS_DIR, manifest_filename)
    generate_ota_manifest(
        manifest_path=manifest_local_path,
        ipa_download_url=ipa_url,
        bundle_id=fixed_bundle_id,
        version=version,
        title=cfg["app"].get("name", "Locket Gold"),
        icon_url=cfg["app"].get("icon", "")
    )

    manifest_url = f"{pages_base}/manifests/{manifest_filename}"
    install_url = f"itms-services://?action=download-manifest&url={urllib.parse.quote(manifest_url, safe='')}"

    return {
        "manifest_url": manifest_url,
        "install_url": install_url,
        "ipa_url": ipa_url,
        "signed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "status": "active"
    }


def check_manifest_alive(manifest_url: str) -> bool:
    if not manifest_url:
        return False
    # Chỉ chấp nhận manifest tự ký bằng zsign (nằm trong /manifests/locket-*.plist)
    if "/manifests/locket-" not in manifest_url:
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


def load_existing_zsign_servers(cfg: dict) -> dict:
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
                    if cid and "/manifests/locket-" in murl and cid not in by_cert:
                        by_cert[cid] = s
            except Exception:
                pass
    return by_cert


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
            shared["apps"][app_id]["name"] = cfg["app"].get("name", "Locket Gold")
            shared["apps"][app_id]["version"] = cfg["app"].get("version", "2.71.0")
            shared["apps"][app_id]["servers"] = servers
            shared["apps"][app_id]["appstore_url"] = cfg["app"].get("appstore_url", "https://apps.apple.com/app/locket-widget/id1600525061")
            shared["apps"][app_id]["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
            shared["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
            with open(shared_path, "w", encoding="utf-8") as f:
                json.dump(shared, f, ensure_ascii=False, indent=2)
            import auto_sign_manager
            auto_sign_manager.update_html_file(auto_sign_manager.load_config(), shared)
    except Exception as e:
        print(f"[Locket ZSign] Lưu ý khi đồng bộ sang {shared_name}: {e}")


def run_once(force: bool = False) -> list:
    cfg = load_config()
    existing_by_cert = load_existing_zsign_servers(cfg)
    servers = []
    missing_certs = []

    for cert in cfg["preferred_certificates"]:
        cid = cert["id"]
        existing = existing_by_cert.get(cid)
        if not force and existing and check_manifest_alive(existing.get("manifest_url", "")):
            print(f"[Locket ZSign] ✔ Link ZSign của {cert['label']} đang hoạt động tốt: {existing['manifest_url']}")
            servers.append({
                **existing,
                "cert_id": cid,
                "label": cert["label"],
                "badge": cert["badge"]
            })
        else:
            missing_certs.append(cert)

    if missing_certs:
        zsign_bin = find_zsign_binary()
        repo = cfg["app"].get("github_repo", "manhcuong2112003/Locket_by_Vincent")
        release_tag = cfg["app"].get("release_tag", "v1.0-signed")
        pages_base = cfg["app"].get("github_pages_base", "https://manhcuong2112003.github.io/Locket_by_Vincent").rstrip("/")
        fixed_bundle_id = cfg["signing_spec"].get("fixed_bundle_id", "com.locket.Locket")
        version = cfg["app"].get("version", "2.71.0")

        if not zsign_bin:
            print("[Locket ZSign] ℹ️ Máy hiện tại chưa có binary `zsign`. Sẽ tạo sẵn manifest.plist và thực thi ký tự động trên GitHub Actions Runner.")
            for cert in missing_certs:
                ensure_certificate_files(cfg, cert)
                slug = cert.get("slug") or re.sub(r"[^a-z0-9]+", "", cert["id"].lower())
                ipa_url = f"https://github.com/{repo}/releases/download/{release_tag}/LocketGold-{slug}.ipa"
                manifest_filename = f"locket-{slug}.plist"
                manifest_local_path = os.path.join(MANIFESTS_DIR, manifest_filename)
                generate_ota_manifest(
                    manifest_path=manifest_local_path,
                    ipa_download_url=ipa_url,
                    bundle_id=fixed_bundle_id,
                    version=version,
                    title=cfg["app"].get("name", "Locket Gold"),
                    icon_url=cfg["app"].get("icon", "")
                )
                manifest_url = f"{pages_base}/manifests/{manifest_filename}"
                install_url = f"itms-services://?action=download-manifest&url={urllib.parse.quote(manifest_url, safe='')}"
                servers.append({
                    "cert_id": cert["id"],
                    "label": cert["label"],
                    "badge": cert["badge"],
                    "manifest_url": manifest_url,
                    "install_url": install_url,
                    "ipa_url": ipa_url,
                    "signed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "status": "active"
                })
        else:
            tmp_dir = tempfile.mkdtemp(prefix="locket_zsign_")
            try:
                raw_ipa = os.path.join(tmp_dir, "Locket-Original.ipa")
                clean_ipa = os.path.join(tmp_dir, "LocketGold-Clean-Base.ipa")
                fallback_base_url = f"https://github.com/{repo}/releases/download/{release_tag}/LocketGold-Clean-Base.ipa"
                try:
                    print(f"[Locket ZSign] ⬇️ Đang tải IPA Locket Gold gốc từ {cfg['app']['remote_ipa_url']}...")
                    req = urllib.request.Request(cfg["app"]["remote_ipa_url"], headers=HEADERS)
                    with urllib.request.urlopen(req, timeout=180) as resp, open(raw_ipa, "wb") as out_f:
                        shutil.copyfileobj(resp, out_f)
                    clean_info = prepare_clean_locket_gold_ipa(raw_ipa, clean_ipa, cfg)
                    try:
                        upload_to_github_release(clean_ipa, release_tag, repo)
                    except Exception as base_up_err:
                        print(f"[Locket ZSign] Lưu ý khi lưu bản Base IPA lên Release: {base_up_err}")
                except Exception as dl_err:
                    print(f"[Locket ZSign] ⚠️ Nguồn chính chặn IP đám mây ({dl_err}), chuyển sang tải bản Base sạch từ GitHub Release: {fallback_base_url}")
                    req_fb = urllib.request.Request(fallback_base_url, headers={"User-Agent": "Mozilla/5.0"})
                    with urllib.request.urlopen(req_fb, timeout=180) as resp_fb, open(clean_ipa, "wb") as out_f:
                        shutil.copyfileobj(resp_fb, out_f)
                    clean_info = {
                        "clean_ipa_path": clean_ipa,
                        "bundle_id": fixed_bundle_id,
                        "version": version
                    }

                for cert in missing_certs:
                    try:
                        res = sign_with_zsign(clean_info, cert, cfg, tmp_dir)
                        servers.append({
                            "cert_id": cert["id"],
                            "label": cert["label"],
                            "badge": cert["badge"],
                            **res
                        })
                        print(f"[Locket ZSign] ✅ Đã ký ZSign & phát hành thành công: {res['manifest_url']}")
                    except Exception as e:
                        print(f"[Locket ZSign] ❌ Lỗi khi ký với {cert['label']}: {e}")
            finally:
                shutil.rmtree(tmp_dir, ignore_errors=True)

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
    parser = argparse.ArgumentParser(description="Trình ký tự chủ ZSign cho Locket Gold")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Bắt buộc đóng gói và ký mới lại toàn bộ các Server bằng zsign"
    )
    args = parser.parse_args()
    run_once(force=args.force)
