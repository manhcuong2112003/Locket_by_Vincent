// deleteHeader.js - Xóa cache ETag để ép RevenueCat và Firebase trả về JSON mới
var modifiedHeaders = $request.headers;

delete modifiedHeaders["x-revenuecat-etag"];
delete modifiedHeaders["X-RevenueCat-ETag"];
delete modifiedHeaders["if-none-match"];
delete modifiedHeaders["If-None-Match"];
delete modifiedHeaders["if-modified-since"];
delete modifiedHeaders["If-Modified-Since"];

modifiedHeaders["Cache-Control"] = "no-cache";
modifiedHeaders["Pragma"] = "no-cache";

$done({ headers: modifiedHeaders });
