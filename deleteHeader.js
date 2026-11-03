// deleteHeader.js - Xóa cache ETag để ép RevenueCat trả về JSON mới
function setHeaderValue(headers, key, value) {
    const lowerKey = key.toLowerCase();
    if (lowerKey in headers) {
        headers[lowerKey] = value;
    } else {
        headers[key] = value;
    }
}

var modifiedHeaders = $request.headers;
const headersToModify = {
    "X-RevenueCat-ETag": "",
    "If-None-Match": "",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache"
};

for (let key in headersToModify) {
    setHeaderValue(modifiedHeaders, key, headersToModify[key]);
}

$done({ headers: modifiedHeaders });
