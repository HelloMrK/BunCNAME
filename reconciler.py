import logging
import os
from typing import List, Dict, Any, Optional, Set

from dns_provider import DNSProvider

logger = logging.getLogger(__name__)


class Reconciler:
    def __init__(self, clients: Dict[str, DNSProvider],
                 managed_types: Optional[Set[str]] = None):
        self.clients = clients
        if managed_types is None:
            raw = os.getenv("MANAGED_TYPES", "CNAME")
            managed_types = {t.strip().upper() for t in raw.split(",") if t.strip()}
        self.managed_types = managed_types

    def sync_config(self, config: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Reconcile remote DNS state with the desired config.

        Returns a summary: {"results": [per domain+provider dicts], "errors": [...]}.
        Non-empty "errors" means the sync did not fully converge and callers
        should treat it as a failure rather than success.
        """
        summary: Dict[str, Any] = {"results": [], "errors": []}

        for domain_entry in config:
            domain = domain_entry.get("domain")
            providers = domain_entry.get("providers")
            desired_records = domain_entry.get("records", [])

            if not domain or not providers:
                logger.warning("Skipping entry without domain or provider field")
                continue

            if isinstance(providers, str):
                providers = [providers]  # 兼容旧格式

            for provider in providers:
                if provider not in self.clients:
                    logger.warning(f"Provider {provider} not configured, skipping")
                    summary["results"].append({
                        "domain": domain, "provider": provider,
                        "created": 0, "updated": 0, "deleted": 0,
                        "errors": [f"provider {provider} not configured"],
                    })
                    summary["errors"].append(f"{domain}/{provider}: provider not configured")
                    continue

                client = self.clients[provider]
                logger.info(f"Syncing records for domain: {domain} with provider: {provider}")
                result = self._sync_domain(client, domain, desired_records)
                result["domain"] = domain
                result["provider"] = provider
                summary["results"].append(result)
                for err in result["errors"]:
                    summary["errors"].append(f"{domain}/{provider}: {err}")

        return summary

    def _sync_domain(self, client: DNSProvider, domain: str,
                     desired_records: List[Dict[str, Any]]) -> Dict[str, Any]:
        result: Dict[str, Any] = {"created": 0, "updated": 0, "deleted": 0, "errors": []}

        try:
            remote_records = client.get_records(domain)
        except Exception as e:
            logger.error(f"Failed to fetch remote records for {domain}: {e}")
            result["errors"].append(f"failed to fetch remote records: {e}")
            return result

        remote_map = {}
        for r in remote_records:
            rtype = str(r.get('type', '')).upper()
            if rtype not in self.managed_types:
                continue  # Skip types we don't manage
            name = r.get('name', '')
            if name == domain:
                host = ''
            else:
                host = name.replace(f".{domain}", "")
            key = (host, rtype)
            remote_map[key] = r
            logger.debug(f"Remote record: {host}.{domain} [{rtype}] -> {r.get('content', '')}")

        desired_map = {}
        for r in desired_records:
            rtype = str(r.get('type', 'CNAME')).upper()
            if rtype not in self.managed_types:
                continue  # Skip types we don't manage
            host = r.get('host', '')
            key = (host, rtype)
            desired_map[key] = r
            logger.debug(f"Desired record: {host}.{domain} [{rtype}] -> {r.get('content', '')}")

        logger.info(f"Domain {domain}: {len(remote_map)} remote / {len(desired_map)} desired "
                    f"managed records (types={sorted(self.managed_types)})")

        # 1. Delete records that are on remote but NOT in desired
        for key, remote_rec in remote_map.items():
            if key not in desired_map:
                logger.info(f"Deleting remote record: {key[0] or '@'}.{domain} [{key[1]}]")
                try:
                    client.delete_record(domain, remote_rec['id'])
                    result["deleted"] += 1
                except Exception as e:
                    logger.error(f"Failed to delete record {remote_rec['id']}: {e}")
                    result["errors"].append(f"delete {key[0]}.{domain} [{key[1]}]: {e}")

        # 2. Create or Update records
        for key, desired_rec in desired_map.items():
            host = key[0]
            rtype = key[1]
            content = desired_rec.get('content')
            ttl = int(desired_rec.get('ttl', 600) or 600)

            if key in remote_map:
                remote_rec = remote_map[key]
                needs_update = (
                    remote_rec.get('content') != content or
                    int(remote_rec.get('ttl', 600) or 600) != ttl
                )
                if needs_update:
                    logger.info(f"Updating record: {host or '@'}.{domain} [{rtype}] -> {content}")
                    try:
                        client.edit_record(domain, remote_rec['id'], host, rtype, content, ttl)
                        result["updated"] += 1
                    except Exception as e:
                        logger.error(f"Failed to update record {remote_rec['id']}: {e}")
                        result["errors"].append(f"update {host}.{domain} [{rtype}]: {e}")
                else:
                    logger.debug(f"Record in sync: {host}.{domain}")
            else:
                logger.info(f"Creating record: {host or '@'}.{domain} [{rtype}] -> {content}")
                try:
                    client.create_record(domain, host, rtype, content, ttl)
                    result["created"] += 1
                except Exception as e:
                    logger.error(f"Failed to create record: {e}")
                    result["errors"].append(f"create {host}.{domain} [{rtype}]: {e}")

        return result
