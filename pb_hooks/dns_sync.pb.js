/// PocketGate → sync-service hook (PocketBase >= v0.23)
///
// Rebuilds the full desired DNS state from the "domains" + "dns_records"
// collections and pushes it to the PocketGate /sync endpoint on every record
// change (full reconciliation: creates, updates and deletes are all handled
// server-side). A cron job re-pushes every 5 minutes as a drift safety net.
//
// !!! PocketBase v0.23 runs hook callbacks in POOLED JS runtimes. Closures,
// !!! top-level consts and top-level function declarations from this file are
// !!! NOT visible inside the callbacks (verified empirically on v0.23.9:
// !!! "ReferenceError: <fn> is not defined"). Every callback below is fully
// !!! self-contained — do NOT extract shared helpers without re-testing.
//
// Required collections:
//   domains:     domain (text), providers (text: JSON array or comma list)
//   dns_records: domain (relation → domains), host, type, content, ttl (number)
//
// Env (set on the PocketBase process):
//   BUNSYNC_URL   default http://127.0.0.1:8000/sync
//   BUNSYNC_TOKEN must match the SYNC_TOKEN env of the PocketGate service

onRecordAfterCreateSuccess(function (e) {
        var trigger = "create/" + ((e.record && e.record.id) || "?");
    try {
        var url = ($os.getenv("BUNSYNC_URL") || "http://127.0.0.1:8000/sync").trim();
        var token = ($os.getenv("BUNSYNC_TOKEN") || "").trim();
        var domains = $app.findRecordsByFilter("domains", "id != ''", "", 0, 0);
        var records = $app.findRecordsByFilter("dns_records", "id != ''", "", 0, 0);
        var byDomain = {};
        for (var i = 0; i < records.length; i++) {
            var rr = records[i];
            var did = rr.getString("domain");
            if (!byDomain[did]) { byDomain[did] = []; }
            byDomain[did].push(rr);
        }
        var payload = [];
        for (var j = 0; j < domains.length; j++) {
            var d = domains[j];
            var provRaw = d.getString("providers") || "";
            var providers = [];
            try {
                var parsed = JSON.parse(provRaw);
                if (parsed && typeof parsed === "object" && parsed.length !== undefined) { providers = parsed; }
            } catch (pe) { /* not JSON, fall back to comma list */ }
            if (!providers.length && provRaw) {
                var parts = provRaw.split(",");
                for (var k = 0; k < parts.length; k++) {
                    if (parts[k].trim()) { providers.push(parts[k].trim()); }
                }
            }
            var drecs = byDomain[d.id] || [];
            var recItems = [];
            for (var m = 0; m < drecs.length; m++) {
                recItems.push({
                    host: drecs[m].getString("host"),
                    type: drecs[m].getString("type") || "CNAME",
                    content: drecs[m].getString("content"),
                    ttl: drecs[m].getInt("ttl") || 600
                });
            }
            payload.push({ domain: d.getString("domain"), providers: providers, records: recItems });
        }
        if (!payload.length) { console.log("[pocketgate-sync] no domains, skip (" + trigger + ")"); return; }
        var headers = { "Content-Type": "application/json" };
        if (token) { headers["X-Sync-Token"] = token; }
        var res = $http.send({ url: url, method: "POST", headers: headers, body: JSON.stringify(payload), timeout: 30 });
        if (res.statusCode >= 200 && res.statusCode < 300) {
            console.log("[pocketgate-sync] ok (" + trigger + ") entries=" + payload.length);
        } else {
            console.log("[pocketgate-sync] FAILED (" + trigger + ") HTTP " + res.statusCode + ": " + ("" + (res.body || "")).slice(0, 300));
        }
    } catch (err) {
        console.log("[pocketgate-sync] ERROR (" + trigger + "): " + err);
    }
}, "dns_records", "domains");

onRecordAfterUpdateSuccess(function (e) {
        var trigger = "update/" + ((e.record && e.record.id) || "?");
    try {
        var url = ($os.getenv("BUNSYNC_URL") || "http://127.0.0.1:8000/sync").trim();
        var token = ($os.getenv("BUNSYNC_TOKEN") || "").trim();
        var domains = $app.findRecordsByFilter("domains", "id != ''", "", 0, 0);
        var records = $app.findRecordsByFilter("dns_records", "id != ''", "", 0, 0);
        var byDomain = {};
        for (var i = 0; i < records.length; i++) {
            var rr = records[i];
            var did = rr.getString("domain");
            if (!byDomain[did]) { byDomain[did] = []; }
            byDomain[did].push(rr);
        }
        var payload = [];
        for (var j = 0; j < domains.length; j++) {
            var d = domains[j];
            var provRaw = d.getString("providers") || "";
            var providers = [];
            try {
                var parsed = JSON.parse(provRaw);
                if (parsed && typeof parsed === "object" && parsed.length !== undefined) { providers = parsed; }
            } catch (pe) { /* not JSON, fall back to comma list */ }
            if (!providers.length && provRaw) {
                var parts = provRaw.split(",");
                for (var k = 0; k < parts.length; k++) {
                    if (parts[k].trim()) { providers.push(parts[k].trim()); }
                }
            }
            var drecs = byDomain[d.id] || [];
            var recItems = [];
            for (var m = 0; m < drecs.length; m++) {
                recItems.push({
                    host: drecs[m].getString("host"),
                    type: drecs[m].getString("type") || "CNAME",
                    content: drecs[m].getString("content"),
                    ttl: drecs[m].getInt("ttl") || 600
                });
            }
            payload.push({ domain: d.getString("domain"), providers: providers, records: recItems });
        }
        if (!payload.length) { console.log("[pocketgate-sync] no domains, skip (" + trigger + ")"); return; }
        var headers = { "Content-Type": "application/json" };
        if (token) { headers["X-Sync-Token"] = token; }
        var res = $http.send({ url: url, method: "POST", headers: headers, body: JSON.stringify(payload), timeout: 30 });
        if (res.statusCode >= 200 && res.statusCode < 300) {
            console.log("[pocketgate-sync] ok (" + trigger + ") entries=" + payload.length);
        } else {
            console.log("[pocketgate-sync] FAILED (" + trigger + ") HTTP " + res.statusCode + ": " + ("" + (res.body || "")).slice(0, 300));
        }
    } catch (err) {
        console.log("[pocketgate-sync] ERROR (" + trigger + "): " + err);
    }
}, "dns_records", "domains");

onRecordAfterDeleteSuccess(function (e) {
        var trigger = "delete/" + ((e.record && e.record.id) || "?");
    try {
        var url = ($os.getenv("BUNSYNC_URL") || "http://127.0.0.1:8000/sync").trim();
        var token = ($os.getenv("BUNSYNC_TOKEN") || "").trim();
        var domains = $app.findRecordsByFilter("domains", "id != ''", "", 0, 0);
        var records = $app.findRecordsByFilter("dns_records", "id != ''", "", 0, 0);
        var byDomain = {};
        for (var i = 0; i < records.length; i++) {
            var rr = records[i];
            var did = rr.getString("domain");
            if (!byDomain[did]) { byDomain[did] = []; }
            byDomain[did].push(rr);
        }
        var payload = [];
        for (var j = 0; j < domains.length; j++) {
            var d = domains[j];
            var provRaw = d.getString("providers") || "";
            var providers = [];
            try {
                var parsed = JSON.parse(provRaw);
                if (parsed && typeof parsed === "object" && parsed.length !== undefined) { providers = parsed; }
            } catch (pe) { /* not JSON, fall back to comma list */ }
            if (!providers.length && provRaw) {
                var parts = provRaw.split(",");
                for (var k = 0; k < parts.length; k++) {
                    if (parts[k].trim()) { providers.push(parts[k].trim()); }
                }
            }
            var drecs = byDomain[d.id] || [];
            var recItems = [];
            for (var m = 0; m < drecs.length; m++) {
                recItems.push({
                    host: drecs[m].getString("host"),
                    type: drecs[m].getString("type") || "CNAME",
                    content: drecs[m].getString("content"),
                    ttl: drecs[m].getInt("ttl") || 600
                });
            }
            payload.push({ domain: d.getString("domain"), providers: providers, records: recItems });
        }
        if (!payload.length) { console.log("[pocketgate-sync] no domains, skip (" + trigger + ")"); return; }
        var headers = { "Content-Type": "application/json" };
        if (token) { headers["X-Sync-Token"] = token; }
        var res = $http.send({ url: url, method: "POST", headers: headers, body: JSON.stringify(payload), timeout: 30 });
        if (res.statusCode >= 200 && res.statusCode < 300) {
            console.log("[pocketgate-sync] ok (" + trigger + ") entries=" + payload.length);
        } else {
            console.log("[pocketgate-sync] FAILED (" + trigger + ") HTTP " + res.statusCode + ": " + ("" + (res.body || "")).slice(0, 300));
        }
    } catch (err) {
        console.log("[pocketgate-sync] ERROR (" + trigger + "): " + err);
    }
}, "dns_records", "domains");

cronAdd("pocketgate-sync", "*/5 * * * *", function () {
    var trigger = "cron";
    try {
        var url = ($os.getenv("BUNSYNC_URL") || "http://127.0.0.1:8000/sync").trim();
        var token = ($os.getenv("BUNSYNC_TOKEN") || "").trim();
        var domains = $app.findRecordsByFilter("domains", "id != ''", "", 0, 0);
        var records = $app.findRecordsByFilter("dns_records", "id != ''", "", 0, 0);
        var byDomain = {};
        for (var i = 0; i < records.length; i++) {
            var rr = records[i];
            var did = rr.getString("domain");
            if (!byDomain[did]) { byDomain[did] = []; }
            byDomain[did].push(rr);
        }
        var payload = [];
        for (var j = 0; j < domains.length; j++) {
            var d = domains[j];
            var provRaw = d.getString("providers") || "";
            var providers = [];
            try {
                var parsed = JSON.parse(provRaw);
                if (parsed && typeof parsed === "object" && parsed.length !== undefined) { providers = parsed; }
            } catch (pe) { /* not JSON, fall back to comma list */ }
            if (!providers.length && provRaw) {
                var parts = provRaw.split(",");
                for (var k = 0; k < parts.length; k++) {
                    if (parts[k].trim()) { providers.push(parts[k].trim()); }
                }
            }
            var drecs = byDomain[d.id] || [];
            var recItems = [];
            for (var m = 0; m < drecs.length; m++) {
                recItems.push({
                    host: drecs[m].getString("host"),
                    type: drecs[m].getString("type") || "CNAME",
                    content: drecs[m].getString("content"),
                    ttl: drecs[m].getInt("ttl") || 600
                });
            }
            payload.push({ domain: d.getString("domain"), providers: providers, records: recItems });
        }
        if (!payload.length) { console.log("[pocketgate-sync] no domains, skip (" + trigger + ")"); return; }
        var headers = { "Content-Type": "application/json" };
        if (token) { headers["X-Sync-Token"] = token; }
        var res = $http.send({ url: url, method: "POST", headers: headers, body: JSON.stringify(payload), timeout: 30 });
        if (res.statusCode >= 200 && res.statusCode < 300) {
            console.log("[pocketgate-sync] ok (" + trigger + ") entries=" + payload.length);
        } else {
            console.log("[pocketgate-sync] FAILED (" + trigger + ") HTTP " + res.statusCode + ": " + ("" + (res.body || "")).slice(0, 300));
        }
    } catch (err) {
        console.log("[pocketgate-sync] ERROR (" + trigger + "): " + err);
    }
});
