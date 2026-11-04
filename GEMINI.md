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

## 3. Quy Cách Cấu Hình Shadowrocket (`locket.module`, `locket_gold_30s.js`, `locket_30s.js`, `deleteHeader.js`)
1. **Bảo Toàn Trọn Bộ 1.014 Cờ Firebase Remote Config & `ETag` Động:**
   - **Tuyệt đối không** lọc rút gọn danh sách `entries` của `firebaseremoteconfig.googleapis.com` theo từ khóa `"video"`/`"camera"`. Tính năng 30s và giao diện Gold VIP phụ thuộc trực tiếp vào các cờ không chứa chữ `video`:
     - `feature_gates` & `feature_gates_override` (`"can_record_30s_video":"enabled"`, `"video_30s":"enabled"`, `"camera_theme":"enabled"`, `"custom_widget_frames":"enabled"`).
     - `flag_6: "3000"`, `flag_10: "5030"`, `flag_14: "5030"`, `flag_15: "5030"` (cờ giới hạn thời lượng mã hóa).
     - `feature_discovery_popup_config` (Popup hiệu ứng vàng *"Đã mở khoá GOLD thành công!"*).
     - `all_widget_frames`, `available_widget_frames`, `custom_widget_frames_list`, `widget_frames` (Khung **Hoàng Gia Gold VIP 👑**).
     - `is_gold`, `gold_enabled`, `locket_gold_enabled`, `gold_badge_profile_menu`, `gold_custom_app_icons`.
   - Luôn trả về HTTP response header `ETag: String(Date.now())` cùng body `"templateVersion": String(Date.now())`, `"state": "UPDATE"` để ép Firebase iOS SDK nạp cấu hình mới ngay lập tức.
2. **Bắt Buộc Chặn QUIC (`UDP 443`) & Kênh Firebase Realtime Trong `[Rule]` của `locket.module`:**
   - Luôn giữ quy tắc `AND,((PROTOCOL,UDP),(DEST-PORT,443)),REJECT` để ép `NSURLSession` trên iOS hạ từ QUIC (HTTP/3) xuống TCP HTTPS (tránh việc kết nối Firebase đi vòng qua bộ giải mã MITM của Shadowrocket).
   - Chặn `DOMAIN,firebaseremoteconfigrealtime.googleapis.com,REJECT` và `DOMAIN,appattest.apple.com,REJECT` để ngăn Google đẩy luồng Realtime ghi đè lại cấu hình gốc.
3. **Bao Phủ Đầy Đủ `rc-cdn.revenuecat.com` & `sdk.revenuecat.com` Trong `[MITM]` và `[Script]`:**
   - Kịch bản `revenuecat` và danh sách `hostname` trong `[MITM]` phải bao phủ cả `api.revenuecat.com`, `rc-cdn.revenuecat.com`, `sdk.revenuecat.com`, `revenuecat.com` để tiêm đủ 160 quyền VIP, 7 Product Entitlement Mappings và 16 Offerings.
4. **Xóa `ETag` Trong `deleteHeader.js` Bằng Chuỗi Rỗng `""` (Không Dùng Toán Tử `delete`):**
   - Trong môi trường Objective-C bridge (`NSMutableURLRequest`) của Shadowrocket, lệnh `delete headers[k]` không xóa được header gốc của request. Bắt buộc dùng `setHeaderValue(modifiedHeaders, key, "")` cho `X-RevenueCat-ETag`, `If-None-Match` và `If-Modified-Since` để ngăn server trả về `304 Not Modified`.
5. **Quy Trình Người Dùng Chuẩn (Locket App Store + Shadowrocket):**
   - Hỗ trợ người dùng sử dụng trực tiếp app Locket gốc tải từ App Store.
   - Thiết bị chỉ cần: Cài Shadowrocket ➔ Thêm `locket.module` ➔ Bật HTTPS Decryption & Tin cậy chứng chỉ MITM của máy ➔ Bật VPN và dùng Locket.

## 4. Đồng Bộ Git & GitHub Actions
- Trước khi `git push origin main`, luôn chạy `git pull --rebase -X theirs origin main` để tránh xung đột với commit tự động từ GitHub Actions.
- Khi đẩy từ Windows, sử dụng remote có tiền tố username `https://manhcuong2112003@github.com/manhcuong2112003/Locket_by_Vincent.git` để khớp với token lưu trong Windows Credential Manager.
