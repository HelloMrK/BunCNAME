import ipaddress
import logging
from typing import List, Dict, Any

import requests

from dns_provider import DNSProvider

logger = logging.getLogger(__name__)

API_BASE = "https://api.cloudflare.com/client/v4"


class CloudflareClient(DNSProvider):
    """Cloudflare DNS provider via API v4 (Bearer token).

    Token needs Zone.DNS Edit + Zone Read permissions on the zones being managed.
    TTL must be >= 60 (1 means "auto" in Cloudflare and is not used here).
    Records are always created as DNS-only (proxied=false) so CNAME targets
    resolve directly.
    """

    def __init__(self, api_token: str, session: requests.Session = None):
        self.api_token = api_token
        self.session = session or requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
        })
        self._zone_ids: Dict[str, str] = {}

    def _request(self, method: str, path: str, **kwargs) -> requests.Response:
        response = self.session.request(method, f"{API_BASE}{path}", timeout=30, **kwargs)
        if not response.ok:
            raise RuntimeError(f"Cloudflare API {method} {path} failed: "
                               f"{response.status_code} {response.text[:300]}")
        return response

    def _zone_id(self, domain: str) -> str:
        if domain not in self._zone_ids:
            data = self._request("GET", "/zones", params={"name": domain}).json()
            zones = data.get("result") or []
            if not zones:
                raise RuntimeError(f"Cloudflare zone not found for domain {domain} "
                                   f"(token may lack Zone Read or zone not in account)")
            self._zone_ids[domain] = zones[0]["id"]
        return self._zone_ids[domain]

    def get_records(self, domain: str) -> List[Dict[str, Any]]:
        """Retrieve all DNS records for a zone (paginated), normalized like Porkbun."""
        zone_id = self._zone_id(domain)
        records: List[Dict[str, Any]] = []
        page = 1
        while True:
            data = self._request("GET", f"/zones/{zone_id}/dns_records",
                                 params={"per_page": 100, "page": page}).json()
            result = data.get("result") or []
            records.extend(result)
            total_pages = (data.get("result_info") or {}).get("total_pages", 1)
            if page >= total_pages:
                break
            page += 1
        return records

    def _fqdn(self, domain: str, host: str) -> str:
        host = (host or "").strip()
        if host in ("", "@"):
            return domain
        return f"{host}.{domain}"

    def create_record(self, domain: str, host: str, rtype: str, content: str, ttl: int = 600):
        zone_id = self._zone_id(domain)
        payload = {
            "type": rtype.upper(),
            "name": self._fqdn(domain, host),
            "content": content,
            "ttl": max(60, int(ttl or 600)),
            "proxied": False,
        }
        return self._request("POST", f"/zones/{zone_id}/dns_records", json=payload).json()

    def delete_record(self, domain: str, record_id: str):
        zone_id = self._zone_id(domain)
        return self._request("DELETE", f"/zones/{zone_id}/dns_records/{record_id}").json()

    def edit_record(self, domain: str, record_id: str, host: str, rtype: str,
                    content: str, ttl: int = 600):
        zone_id = self._zone_id(domain)
        payload = {
            "type": rtype.upper(),
            "name": self._fqdn(domain, host),
            "content": content,
            "ttl": max(60, int(ttl or 600)),
            "proxied": False,
        }
        return self._request("PUT", f"/zones/{zone_id}/dns_records/{record_id}",
                             json=payload).json()

    @staticmethod
    def classify(answer: str) -> str:
        """Classify an answer into A/AAAA/CNAME for callers that need it."""
        try:
            return f"AAAA" if ipaddress.ip_address(answer).version == 6 else "A"
        except ValueError:
            return "CNAME"
