// locket_gold_30s.js - Mở khóa Gold Vĩnh Viễn & 30s Video
let body = $response.body;

try {
    let obj = JSON.parse(body);

    if (obj.subscriber) {
        const subData = {
            "is_sandbox": false,
            "ownership_type": "PURCHASED",
            "billing_issues_detected_at": null,
            "period_type": "normal",
            "expires_date": "2099-12-31T23:59:59Z",
            "grace_period_expires_date": null,
            "unsubscribe_detected_at": null,
            "original_purchase_date": "2024-01-01T00:00:00Z",
            "purchase_date": "2024-01-01T00:00:00Z",
            "store": "app_store"
        };

        const entData = {
            "grace_period_expires_date": null,
            "purchase_date": "2024-01-01T00:00:00Z",
            "product_identifier": "Gold",
            "expires_date": "2099-12-31T23:59:59Z"
        };

        obj.subscriber.subscriptions = obj.subscriber.subscriptions || {};
        obj.subscriber.entitlements = obj.subscriber.entitlements || {};

        obj.subscriber.subscriptions["Gold"] = subData;
        obj.subscriber.subscriptions["com.locket.Locket.Gold.Yearly"] = subData;
        obj.subscriber.subscriptions["com.locket02.premium.yearly"] = subData;

        obj.subscriber.entitlements["Gold"] = entData;
        obj.subscriber.entitlements["gold"] = entData;
        obj.subscriber.entitlements["pro"] = entData;
    }

    // Mở cờ Video 30s
    function patchVideoLimit(o) {
        if (!o || typeof o !== "object") return;
        for (let k in o) {
            let lk = k.toLowerCase();
            if (lk.includes("video") && (lk.includes("duration") || lk.includes("limit") || lk.includes("max") || lk.includes("length") || lk.includes("second"))) {
                if (typeof o[k] === "number") o[k] = 30;
            } else if (lk.includes("can_record") || lk.includes("allow_long_video")) {
                o[k] = true;
            } else if (typeof o[k] === "object") {
                patchVideoLimit(o[k]);
            }
        }
    }
    patchVideoLimit(obj);

    body = JSON.stringify(obj);
} catch (e) {}

$done({ body });
