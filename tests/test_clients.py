import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cloudflare_client import CloudflareClient
from adguard_home_client import AdGuardHomeClient


class FakeResponse:
    def __init__(self, status_code=200, body=None):
        self.status_code = status_code
        self._body = body or {}
        self.ok = status_code < 400
        self.text = json.dumps(self._body)

    def json(self):
        return self._body


class FakeSession:
    """Pre-scripted requests.Session double used by both client tests."""

    def __init__(self, script):
        # script: list of (method, path_or_url, response)
        self.script = list(script)
        self.calls = []
        self.headers = {}

    def request(self, method, url, **kwargs):
        path = url.replace("https://api.cloudflare.com/client/v4", "")
        for i, (m, p, resp) in enumerate(self.script):
            if m == method and p == path:
                self.script.pop(i)
                self.calls.append((method, path, kwargs))
                return resp
        raise AssertionError(f"unexpected request {method} {path}; "
                             f"remaining script: {[(m, p) for m, p, _ in self.script]}")


def cf_zone_page():
    return FakeResponse(body={"success": True, "result": [{"id": "zone123", "name": "example.com"}]})


# ---- Cloudflare ----

def test_cf_get_records_normalizes_and_paginates():
    s = FakeSession([
        ("GET", "/zones", cf_zone_page()),
        ("GET", "/zones/zone123/dns_records", FakeResponse(body={
            "success": True,
            "result": [{"id": "r1", "type": "CNAME", "name": "www.example.com",
                        "content": "t.io", "ttl": 600, "proxied": False}],
            "result_info": {"total_pages": 1},
        })),
    ])
    c = CloudflareClient("tok", session=s)
    recs = c.get_records("example.com")
    assert recs[0]["id"] == "r1" and recs[0]["name"] == "www.example.com"
    # zone id cached: second call does not hit /zones again
    s.script.append(("GET", "/zones/zone123/dns_records", FakeResponse(body={
        "success": True, "result": [], "result_info": {"total_pages": 1},
    })))
    c.get_records("example.com")
    assert all(m != "GET" or p != "/zones" for m, p, _ in s.calls[1:])


def test_cf_create_uses_fqdn_dnsonly_and_min_ttl():
    s = FakeSession([
        ("GET", "/zones", cf_zone_page()),
        ("POST", "/zones/zone123/dns_records", FakeResponse(body={"success": True, "result": {}})),
    ])
    c = CloudflareClient("tok", session=s)
    c.create_record("example.com", "www", "CNAME", "t.io", ttl=30)
    method, path, kwargs = s.calls[-1]
    body = kwargs["json"]
    assert body["name"] == "www.example.com" and body["proxied"] is False
    assert body["ttl"] == 60  # clamped to Cloudflare minimum


def test_cf_apex_host_uses_zone_name():
    s = FakeSession([
        ("GET", "/zones", cf_zone_page()),
        ("POST", "/zones/zone123/dns_records", FakeResponse(body={"success": True, "result": {}})),
    ])
    CloudflareClient("tok", session=s).create_record("example.com", "", "A", "1.2.3.4")
    assert s.calls[-1][2]["json"]["name"] == "example.com"


def test_cf_zone_not_found_raises():
    s = FakeSession([("GET", "/zones", FakeResponse(body={"success": True, "result": []}))])
    try:
        CloudflareClient("tok", session=s)._zone_id("example.com")
        raise AssertionError("expected RuntimeError")
    except RuntimeError as e:
        assert "zone not found" in str(e)


def test_cf_api_error_raises_with_status():
    s = FakeSession([("GET", "/zones", FakeResponse(status_code=403, body={"success": False}))])
    try:
        CloudflareClient("tok", session=s)._zone_id("example.com")
        raise AssertionError("expected RuntimeError")
    except RuntimeError as e:
        assert "403" in str(e)


# ---- AdGuard Home ----

class FakeAdGuardSession(AdGuardHomeClient):
    """Bypass HTTP: directly stub _get/_post."""

    def __init__(self, rules):
        self.rules = rules
        self.posts = []

    def _get(self, endpoint):
        assert endpoint == "/control/rewrite/list"
        return self.rules

    def _post(self, endpoint, data=None):
        self.posts.append((endpoint, data))
        return {}


def test_adguard_classifies_domain_and_ip_answers():
    c = FakeAdGuardSession([
        {"domain": "www.example.com", "answer": "t.io"},
        {"domain": "home.example.com", "answer": "192.168.1.10"},
        {"domain": "v6.example.com", "answer": "fd00::1"},
        {"domain": "other.org", "answer": "x.org"},
    ])
    recs = c.get_records("example.com")
    by_type = {r["type"]: r for r in recs}
    assert by_type["CNAME"]["content"] == "t.io"
    assert by_type["A"]["content"] == "192.168.1.10"
    assert by_type["AAAA"]["content"] == "fd00::1"
    assert len(recs) == 3  # other.org filtered out


def test_adguard_create_accepts_a_record():
    c = FakeAdGuardSession([])
    c.create_record("example.com", "home", "A", "192.168.1.10")
    endpoint, data = c.posts[-1]
    assert endpoint == "/control/rewrite/add"
    assert data == {"domain": "home.example.com", "answer": "192.168.1.10"}


def test_adguard_rejects_unsupported_type():
    c = FakeAdGuardSession([])
    try:
        c.create_record("example.com", "x", "MX", "mail.io")
        raise AssertionError("expected ValueError")
    except ValueError:
        pass
