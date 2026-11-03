/**
 * Locket Gold & 30s Video Script for Shadowrocket
 * Handles both Request (strip ETag to force fresh 200 response) and Response (inject Gold & 30s)
 */

if (typeof $response === "undefined") {
    // --- HTTP-REQUEST: Xóa header cache để server luôn trả về JSON mới (200 OK) ---
    let headers = $request.headers;
    delete headers["x-revenuecat-etag"];
    delete headers["X-RevenueCat-ETag"];
    delete headers["if-none-match"];
    delete headers["If-None-Match"];
    $done({ headers });
} else {
    // --- HTTP-RESPONSE: Bơm Gold và 30s video ---
    const url = $request.url;
    let body = $response.body;

    if (url.includes("revenuecat.com")) {
        try {
            let obj = JSON.parse(body);
            const goldEntitlement = {
                "expires_date": "2099-12-31T23:59:59Z",
                "grace_period_expires_date": null,
                "purchase_date": "2024-01-01T00:00:00Z",
                "product_identifier": "com.locket.Locket.Gold.Yearly"
            };
            const goldSubscription = {
                "billing_issues_detected_at": null,
                "expires_date": "2099-12-31T23:59:59Z",
                "is_sandbox": false,
                "original_purchase_date": "2024-01-01T00:00:00Z",
                "purchase_date": "2024-01-01T00:00:00Z",
                "store": "app_store",
                "unsubscribe_detected_at": null
            };

            if (obj.subscriber) {
                obj.subscriber.entitlements = obj.subscriber.entitlements || {};
                obj.subscriber.subscriptions = obj.subscriber.subscriptions || {};
                obj.subscriber.entitlements["Gold"] = goldEntitlement;
                obj.subscriber.entitlements["gold"] = goldEntitlement;
                obj.subscriber.subscriptions["com.locket.Locket.Gold.Yearly"] = goldSubscription;
            } else {
                obj = {
                    "request_date": "2024-01-01T00:00:00Z",
                    "request_date_ms": 1704067200000,
                    "subscriber": {
                        "entitlements": { "Gold": goldEntitlement, "gold": goldEntitlement },
                        "first_seen": "2024-01-01T00:00:00Z",
                        "original_app_user_id": "locket_user",
                        "original_application_version": "1.0",
                        "original_purchase_date": "2024-01-01T00:00:00Z",
                        "subscriptions": { "com.locket.Locket.Gold.Yearly": goldSubscription }
                    }
                };
            }
            body = JSON.stringify(obj);
        } catch (e) {}
    } else {
        // Feature gates / Locket camera limit
        try {
            let obj = JSON.parse(body);
            function patch(o) {
                if (!o || typeof o !== "object") return;
                for (let k in o) {
                    let lk = k.toLowerCase();
                    if (lk.includes("video") && (lk.includes("duration") || lk.includes("limit") || lk.includes("max") || lk.includes("length"))) {
                        if (typeof o[k] === "number") o[k] = 30;
                    } else if (lk.includes("can_record") || lk.includes("allow_long_video")) {
                        o[k] = true;
                    } else if (typeof o[k] === "object") {
                        patch(o[k]);
                    }
                }
            }
            patch(obj);
            body = JSON.stringify(obj);
        } catch (e) {}
    }

    $done({ body });
}
