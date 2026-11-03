# Quy Tắc Dự Án Locket (`Locket_by_Vincent`)

## 1. Phạm Vi Dự Án (Project Scope)
- Dự án này **chỉ tập trung 100% vào ứng dụng Locket (`Locket Widget`)** trên repository `https://github.com/manhcuong2112003/Locket_by_Vincent` (GitHub Pages: `https://manhcuong2112003.github.io/Locket_by_Vincent/`).
- **Tuyệt đối không** thêm lại các thành phần liên quan đến Game (`Asphalt 8`, `sign_game.py`, `config_game.json`) và không làm ảnh hưởng đến dự án `SDRK` (`Shadowrocket`).

## 2. Quy Cách Đóng Gói & Ký Locket (`sign_locket.py`)
1. **Bản Locket Chuẩn (Chưa cần Gold Tweak) & Đồng bộ Bundle ID chống xung đột App Store:**
   - Gỡ bỏ `AutoRcSideload.dylib` khi `remove_gold_tweak = true` trong `config_locket.json` (do `AutoRcSideload.dylib` được liên kết bằng `LC_LOAD_WEAK_DYLIB` `0x80000018` nên gỡ file `.dylib` sẽ trả về bản Locket gốc sạch, nhẹ hơn ~6.2 MB).
   - Giữ lại `blatantsPatch.dylib` trong `Payload/Locket.app/Frameworks/` để tự động hook App Group và Keychain theo Bundle ID hiện hành.
   - Xóa thư mục `Payload/Locket.app/PlugIns/*.appex` trước khi ký bằng chứng chỉ doanh nghiệp.
   - Đồng bộ 100% `CFBundleIdentifier` trong `Info.plist` và `BUNDLE_ID` trong `GoogleService-Info.plist` (`com.ipaomtk.auto.locketwidgetipaomtkcom`) để không bị xung đột với bản Locket App Store trên iPhone (giúp iOS luôn nạp chứng chỉ vào *Quản lý VPN & Thiết bị*) và không bị văng Firebase khi mở app.
2. **Hỗ trợ song song tải Locket Gốc (App Store / 3uTools) & Cấu hình DNS (`Vincent-DNS` + `NextDNS d438ff`):**
   - Giao diện `index.html` tích hợp sẵn nút tải Locket gốc trực tiếp (`https://apps.apple.com/vn/app/locket-widget/id1600525061`), nút `Vincent-DNS.mobileconfig` (đã bổ sung `ppq.apple.com` và `api.revenuecat.com`) và nút `NextDNS (d438ff).mobileconfig`.
3. **Bắt buộc chuẩn hóa quyền thực thi Unix (`chmod 0755`) trong ZIP Central Directory:**
   - Luôn gọi `fix_ipa_unix_permissions(ipa_path)` sau khi đóng gói/ký để đặt `version_made_by = 0x0314` (Unix) và `external_attr = 0o100755 << 16` (`0x81ed0000`) cho tất cả Mach-O binary & `.dylib`.

## 3. Đồng Bộ Git & GitHub Actions
- Trước khi `git push origin main`, luôn chạy `git pull --rebase -X theirs origin main` để tránh xung đột với commit tự động từ GitHub Actions.
- Khi đẩy từ Windows, sử dụng remote có tiền tố username `https://manhcuong2112003@github.com/manhcuong2112003/Locket_by_Vincent.git` để khớp với token lưu trong Windows Credential Manager.
