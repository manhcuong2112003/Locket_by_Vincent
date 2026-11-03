/**
 * Locket Gold & 30s Video Script for Shadowrocket
 * Target: api.revenuecat.com & api.locketcamera.com
 */

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
            obj.subscriber.subscriptions["com.locket.Locket.Gold.Yearly"] = goldSubscription;
            body = JSON.stringify(obj);
        }
    } catch (e) {
        // Fallback
    }
} else if (url.includes("locketcamera.com") || url.includes("firebaseremoteconfig")) {
    try {
        let obj = JSON.parse(body);
        // Ghi đè các cờ giới hạn thời lượng video của camera
        const overrideKeys = [
            "video_max_duration",
            "camera_video_limit_seconds",
            "max_recording_duration",
            "video_duration_limit",
            "can_record_long_video"
        ];
        
        function patchObject(target) {
            if (typeof target !== "object" || target === null) return;
            for (let key in target) {
                if (overrideKeys.includes(key)) {
                    target[key] = typeof target[key] === "boolean" ? true : 30.0;
                } else if (typeof target[key] === "object") {
                    patchObject(target[key]);
                }
            }
        }
        patchObject(obj);
        body = JSON.stringify(obj);
    } catch (e) {
        // Fallback
    }
}

$done({ body });
