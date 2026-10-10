import ipaddress

import requests
from typing import List, Dict, Any
from dns_provider import DNSProvider

class AdGuardHomeClient(DNSProvider):
    def __init__(self, base_url: str, username: str = None, password: str = None):
        self.base_url = base_url.rstrip('/')
        self.username = username
        self.password = password
        self.session = requests.Session()
        if username and password:
            self.session.auth = (username, password)

    def _get(self, endpoint: str) -> Dict[str, Any]:
        response = self.session.get(f"{self.base_url}{endpoint}")
        response.raise_for_status()
        return response.json()

    def _post(self, endpoint: str, data: Dict[str, Any] = None) -> Dict[str, Any]:
        if data is None:
            data = {}
        response = self.session.post(f"{self.base_url}{endpoint}", json=data)
        response.raise_for_status()
        try:
            return response.json()
        except ValueError:
            # If response is not JSON, return empty dict
            return {}

    def get_records(self, domain: str) -> List[Dict[str, Any]]:
        """Retrieve DNS rewrite rules. For AdGuard Home, we treat rewrite rules as records."""
        result = self._get("/control/rewrite/list")
        if isinstance(result, list):
            rules = result
        else:
            rules = result.get("rules", [])
        # AdGuard Home rewrites are global (not per-zone); filter to rules whose
        # domain equals or ends with ".{domain}" and map them into host records.
        records = []
        for rule in rules:
            domain_name = rule.get("domain")
            answer = rule.get("answer")
            rtype = self._classify_answer(answer)
            if domain_name.endswith(f".{domain}") or domain_name == domain:
                host = domain_name.replace(f".{domain}", "") if domain_name != domain else ""
                records.append({
                    "id": f"{domain_name}=>{answer}",  # Unique ID
                    "name": domain_name,
                    "type": rtype,
                    "content": answer,
                    "ttl": 600  # AdGuard Home doesn't have TTL for rewrites
                })
        return records

    def create_record(self, domain: str, host: str, rtype: str, content: str, ttl: int = 600):
        """Create a DNS rewrite rule (CNAME to domain, or A/AAAA to IP answer)."""
        if rtype not in ("CNAME", "A", "AAAA"):
            raise ValueError("AdGuard Home only supports CNAME/A/AAAA-like rewrites")
        full_domain = f"{host}.{domain}" if host else domain
        data = {
            "domain": full_domain,
            "answer": content
        }
        return self._post("/control/rewrite/add", data)

    def delete_record(self, domain: str, record_id: str):
        """Delete a DNS rewrite rule."""
        # record_id is "domain=>answer"
        domain_name, answer = record_id.split("=>", 1)
        data = {
            "domain": domain_name,
            "answer": answer
        }
        return self._post("/control/rewrite/delete", data)

    def edit_record(self, domain: str, record_id: str, host: str, rtype: str, content: str, ttl: int = 600):
        """Edit a DNS rewrite rule. Since AdGuard Home doesn't support edit, delete and create."""
        self.delete_record(domain, record_id)
        self.create_record(domain, host, rtype, content, ttl)

    @staticmethod
    def _classify_answer(answer: str) -> str:
        """Classify a rewrite answer: IPv4 -> A, IPv6 -> AAAA, otherwise CNAME."""
        try:
            return "AAAA" if ipaddress.ip_address(answer).version == 6 else "A"
        except ValueError:
            return "CNAME"