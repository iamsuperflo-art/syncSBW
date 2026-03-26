import os
import time
import logging
import requests
from datetime import datetime

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)
log = logging.getLogger(__name__)

# ── Config din variabile de mediu ─────────────────────────────────────────────
SMARTBILL_EMAIL     = os.environ["SMARTBILL_EMAIL"]
SMARTBILL_TOKEN     = os.environ["SMARTBILL_TOKEN"]
SMARTBILL_CIF       = os.environ["SMARTBILL_CIF"]
SMARTBILL_WAREHOUSE = os.environ.get("SMARTBILL_WAREHOUSE", "GESTIUNE MARFURI")

WIX_API_KEY         = os.environ["WIX_API_KEY"]
WIX_ACCOUNT_ID      = os.environ["WIX_ACCOUNT_ID"]
WIX_SITE_ID         = os.environ["WIX_SITE_ID"]

SYNC_INTERVAL_SEC   = int(os.getenv("SYNC_INTERVAL_SEC", "600"))


# ══════════════════════════════════════════════════════════════════════════════
# SMARTBILL
# ══════════════════════════════════════════════════════════════════════════════

def get_smartbill_stocks() -> dict[str, float]:
    """Returnează {productCode: cantitate} din gestiunea SmartBill."""
    url = "https://ws.smartbill.ro/SBORO/api/stocks"
    params = {
        "cif":           SMARTBILL_CIF,
        "date":          datetime.now().strftime("%Y-%m-%d"),
        "warehouseName": SMARTBILL_WAREHOUSE,
    }
    resp = requests.get(
        url, params=params,
        headers={"Accept": "application/json"},
        auth=(SMARTBILL_EMAIL, SMARTBILL_TOKEN),
        timeout=30
    )
    resp.raise_for_status()
    data = resp.json()

    # Structura: data["list"][i]["products"][j]
    stocks: dict[str, float] = {}
    for warehouse_entry in data.get("list", []):
        for product in warehouse_entry.get("products", []):
            sku = (product.get("productCode") or "").strip()
            qty = float(product.get("quantity", 0) or 0)
            if sku:
                stocks[sku] = qty

    log.info(f"SmartBill: {len(stocks)} produse preluate din '{SMARTBILL_WAREHOUSE}'")
    return stocks


# ══════════════════════════════════════════════════════════════════════════════
# WIX
# ══════════════════════════════════════════════════════════════════════════════

def wix_headers():
    return {
        "Authorization": WIX_API_KEY,
        "wix-account-id": WIX_ACCOUNT_ID,
        "wix-site-id":    WIX_SITE_ID,
        "Content-Type":   "application/json",
    }

def get_wix_products() -> dict[str, dict]:
    """
    Returnează {sku: {productId, variantId, currentQuantity}}
    folosind Wix Stores Products API v1.
    """
    url = "https://www.wixapis.com/stores/v1/products/query"
    products: dict[str, dict] = {}
    offset = 0
    limit = 100

    while True:
        body = {
            "query": {
                "paging": {"limit": limit, "offset": offset}
            },
            "includeVariants": True
        }
        resp = requests.post(url, json=body, headers=wix_headers(), timeout=30)
        if not resp.ok:
            log.error(f"DEBUG Wix error {resp.status_code}: {resp.text[:500]}")
        resp.raise_for_status()
        data = resp.json()

        items = data.get("products", [])
        for product in items:
            product_id = product.get("id")
            variants = product.get("variants", [])
            for variant in variants:
                sku = variant.get("variant", {}).get("sku", "").strip()
                if not sku:
                    sku = product.get("sku", "").strip()
                if not sku:
                    continue
                stock = variant.get("stock", {})
                products[sku] = {
                    "productId":       product_id,
                    "variantId":       variant.get("id"),
                    "currentQuantity": stock.get("quantity", 0),
                }

        if len(items) < limit:
            break
        offset += limit

    log.info(f"Wix: {len(products)} variante găsite")
    return products


def update_wix_inventory(product_id: str, variant_id: str, quantity: int):
    """Setează cantitatea pentru un produs/variant în Wix."""
    NULL_UUID = "00000000-0000-0000-0000-000000000000"

    if variant_id and variant_id != NULL_UUID:
        # Produs cu variante
        url = f"https://www.wixapis.com/stores/v1/products/{product_id}/variants/{variant_id}"
        body = {"stock": {"quantity": quantity, "trackInventory": True}}
        resp = requests.patch(url, json=body, headers=wix_headers(), timeout=30)
    else:
        # Produs simplu (fara variante) — actualizam direct pe produs
        url = f"https://www.wixapis.com/stores/v1/products/{product_id}"
        body = {"product": {"stock": {"quantity": quantity, "trackInventory": True}}}
        resp = requests.patch(url, json=body, headers=wix_headers(), timeout=30)

    resp.raise_for_status()
    log.info(f"DEBUG update response {resp.status_code}: {resp.text[:300]}")


# ══════════════════════════════════════════════════════════════════════════════
# SYNC
# ══════════════════════════════════════════════════════════════════════════════

def sync_once():
    log.info("━" * 60)
    log.info(f"🔄 Sincronizare pornită la {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    try:
        sb_stocks    = get_smartbill_stocks()
        wix_products = get_wix_products()
    except Exception as e:
        log.error(f"Eroare la preluarea datelor: {e}")
        return

    updated = skipped = errors = 0

    for sku, wix_info in wix_products.items():
        if sku not in sb_stocks:
            log.debug(f"  SKIP {sku} — nu există în SmartBill")
            skipped += 1
            continue

        sb_qty  = int(sb_stocks[sku])
        wix_qty = int(wix_info["currentQuantity"] or 0)

        if sb_qty == wix_qty:
            log.debug(f"  OK   {sku} — stoc identic ({sb_qty})")
            continue

        try:
            update_wix_inventory(
                wix_info["productId"],
                wix_info["variantId"],
                sb_qty
            )
            log.info(f"  ✅  {sku}: {wix_qty} → {sb_qty}")
            updated += 1
        except Exception as e:
            log.error(f"  ❌  {sku}: eroare update — {e}")
            errors += 1

    log.info(f"Rezultat: {updated} actualizate | {skipped} ignorate | {errors} erori")


def main():
    log.info("🚀 SmartBill → Wix Stock Sync pornit")
    log.info(f"   Interval: {SYNC_INTERVAL_SEC}s ({SYNC_INTERVAL_SEC//60} minute)")

    while True:
        sync_once()
        log.info(f"⏳ Următoarea sincronizare în {SYNC_INTERVAL_SEC//60} minute...\n")
        time.sleep(SYNC_INTERVAL_SEC)


if __name__ == "__main__":
    main()
