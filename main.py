import hmac
import os
import logging
from typing import Dict, Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Body, Request
import uvicorn

from porkbun_client import PorkbunClient
from adguard_home_client import AdGuardHomeClient
from cloudflare_client import CloudflareClient
from reconciler import Reconciler

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def build_clients() -> Dict[str, Any]:
    api_key = os.getenv("PORKBUN_API_KEY")
    secret_key = os.getenv("PORKBUN_SECRET_KEY")
    adguard_url = os.getenv("ADGUARD_HOME_URL")
    adguard_username = os.getenv("ADGUARD_HOME_USERNAME")
    adguard_password = os.getenv("ADGUARD_HOME_PASSWORD")
    cf_token = os.getenv("CLOUDFLARE_API_TOKEN")

    clients = {}
    if api_key and secret_key:
        clients["porkbun"] = PorkbunClient(api_key, secret_key)
    else:
        logger.warning("PORKBUN_API_KEY and PORKBUN_SECRET_KEY not set, skipping Porkbun")

    if adguard_url:
        clients["adguard_home"] = AdGuardHomeClient(adguard_url, adguard_username, adguard_password)
    else:
        logger.warning("ADGUARD_HOME_URL not set, skipping AdGuard Home")

    if cf_token:
        clients["cloudflare"] = CloudflareClient(cf_token)
    else:
        logger.warning("CLOUDFLARE_API_TOKEN not set, skipping Cloudflare")

    return clients


def create_reconciler() -> Reconciler:
    clients = build_clients()
    if not clients:
        raise RuntimeError("No DNS providers configured.")
    return Reconciler(clients)


app = FastAPI(title="PocketGate API", version="1.1.0")


@app.get("/health")
async def health():
    return {"status": "ok"}


def _check_sync_token(request: Request):
    expected = os.getenv("SYNC_TOKEN", "")
    if not expected:
        return  # auth disabled when SYNC_TOKEN is unset
    provided = request.headers.get("X-Sync-Token", "")
    if not hmac.compare_digest(expected, provided):
        raise HTTPException(status_code=401, detail="invalid or missing X-Sync-Token")


@app.post("/sync")
async def sync_records(request: Request, config: list = Body(...)):
    _check_sync_token(request)
    try:
        reconciler = create_reconciler()
        summary = reconciler.sync_config(config)
        if summary["errors"]:
            raise HTTPException(
                status_code=500,
                detail={"message": "DNS sync completed with errors", "summary": summary},
            )
        return {
            "status": "ok",
            "message": "DNS sync completed",
            "entries": len(config),
            "summary": summary,
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Error during sync: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


def main():
    load_dotenv()

    try:
        create_reconciler()
    except RuntimeError as exc:
        logger.error(str(exc))
        return

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))


if __name__ == "__main__":
    main()
