"""In-memory DNSProvider for tests: records stored as (host, type) -> record."""
from typing import List, Dict, Any

from dns_provider import DNSProvider


class FakeProvider(DNSProvider):
    def __init__(self, records: List[Dict[str, Any]] = None, fail_on: str = None):
        # records: [{"host": "www", "type": "CNAME", "content": ..., "ttl": ...}]
        self.store: Dict[tuple, Dict[str, Any]] = {}
        self.next_id = 1
        self.fail_on = fail_on  # method name that should raise
        for r in (records or []):
            self._seed(r)

    def _seed(self, r):
        key = (r["host"], r.get("type", "CNAME").upper())
        self.store[key] = {
            "id": str(self.next_id), "name": f"{r['host']}.{r.get('_domain', 'example.com')}"
            if r["host"] else r.get("_domain", "example.com"),
            "type": key[1], "content": r["content"], "ttl": r.get("ttl", 600),
        }
        self.next_id += 1

    def _guard(self, name):
        if self.fail_on == name:
            raise RuntimeError(f"injected failure in {name}")

    def get_records(self, domain: str) -> List[Dict[str, Any]]:
        self._guard("get_records")
        return [dict(v) for v in self.store.values()]

    def create_record(self, domain: str, host: str, rtype: str, content: str, ttl: int = 600):
        self._guard("create_record")
        key = (host, rtype.upper())
        rec = {"id": str(self.next_id), "name": f"{host}.{domain}" if host else domain,
               "type": rtype.upper(), "content": content, "ttl": ttl}
        self.next_id += 1
        self.store[key] = rec
        return rec

    def delete_record(self, domain: str, record_id: str):
        self._guard("delete_record")
        for key, rec in list(self.store.items()):
            if rec["id"] == record_id:
                del self.store[key]
                return {"status": "deleted"}
        raise ValueError(f"record {record_id} not found")

    def edit_record(self, domain: str, record_id: str, host: str, rtype: str,
                    content: str, ttl: int = 600):
        self._guard("edit_record")
        for key, rec in self.store.items():
            if rec["id"] == record_id:
                rec.update({"name": f"{host}.{domain}" if host else domain,
                            "type": rtype.upper(), "content": content, "ttl": ttl})
                return {"status": "edited"}
        raise ValueError(f"record {record_id} not found")
