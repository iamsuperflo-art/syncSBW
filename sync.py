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
SMARTBILL_EMAIL    = os.environ["SMARTBILL_EMAIL"]
SMARTBILL_TOKEN    = os.environ["SMARTBILL_TOKEN"]
SMARTBILL_CIF      = os.environ["SMARTBILL_CIF"]       # CIF-ul firmei tale

WIX_API_KEY        = os.environ["WIX_API_KEY"]
WIX_ACCOUNT_ID     = os.environ["WIX_ACCOUNT_ID"]
WIX_SITE_ID        = os.environ["WIX_SITE_ID"]

SYNC_INTERVAL_SEC  = int(os.getenv("SYNC_INTERVAL_SEC", "600"))  # 10 minute


# ══════════════════════════════════════════════════════════════════════════════
# SMARTBILL
# ══════════════════════════════════════════════════════════════════════════════

def get_smartbill_stocks() -> dict[str, float]:
    """
    Returnează {sku: cantitate} pentru toate produsele din SmartBill.
    Documentație: https://api.smartbill.ro
    """
    url = "https://ws.smartbill.ro/SBORO/api/products"
    params = {"cif": SMARTBILL_CIF}
    headers = {"Accept": "application/json"}

    resp = requests.get(
        url,
        params=params,
        headers=headers,
        auth=(SMARTBILL_EMAIL, SMARTBILL_TOKEN),
        timeout=30
    )
    resp.raise_for_status()
    data = resp.json()

    stocks: dict[str, float] = {}
    for product in data.get("list", []):
        sku = product.get("code", "").strip()
        qty = float(product.get("quantity", 0) or 0)
        if sku:
            stocks[sku] = qty

    log.info(f"SmartBill: {len(stocks)} produse preluate")
    return stocks


# ══════════════════════════════════════════════════════════════════════════════
# WIX
# ══════════════════════════════════════════════════════════════════════════════

WIX_HEADERS = {
    "Authorization": f"Bearer {os.environ.get('WIX_API_KEY', '')}",
    "wix-account-id": os.environ.get("WIX_ACCOUNT_ID", ""),
    "wix-site-id":    os.environ.get("WIX_SITE_ID", ""),
    "Content-Type":   "application/json",
}

def get_wix_products() -> dict[str, dict]:
    """
    Returnează {sku: {inventoryItemId, variantId, currentQuantity}}
    pentru toate produsele din Wix Stores.
    """
    url = "https://www.wixapis.com/stores/v1/inventory/items/query"
    products: dict[str, dict] = {}
    cursor = None

    while True:
        body: dict = {"query": {"paging": {"limit": 100}}}
        if cursor:
            body["query"]["cursorPaging"] = {"cursor": cursor}

        resp = requests.post(url, json=body, headers=WIX_HEADERS, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        for item in data.get("inventoryItems", []):
            inventory_item_id = item.get("id")
            for variant in item.get("variants", []):
                sku = variant.get("variantFields", {}).get("sku", "").strip()
                if not sku:
                    continue
                products[sku] = {
                    "inventoryItemId": inventory_item_id,
                    "variantId":       variant.get("variantId"),
                    "currentQuantity": variant.get("quantity", 0),
                }

        cursor = data.get("metadata", {}).get("cursors", {}).get("next")
        if not cursor:
            break

    log.info(f"Wix: {len(products)} variante găsite")
    return products


def update_wix_inventory(inventory_item_id: str, variant_id: str, quantity: int):
    """Setează cantitatea exactă pentru un variant în Wix."""
    url = f"https://www.wixapis.com/stores/v1/inventory/items/{inventory_item_id}/variants/set"
    body = {
        "inventoryItemId": inventory_item_id,
        "variants": [
            {
                "variantId": variant_id,
                "quantity":  quantity,
            }
        ]
    }
    resp = requests.patch(url, json=body, headers=WIX_HEADERS, timeout=30)
    resp.raise_for_status()


# ══════════════════════════════════════════════════════════════════════════════
# SYNC
# ══════════════════════════════════════════════════════════════════════════════

def sync_once():
    log.info("━" * 60)
    log.info(f"🔄 Sincronizare pornită la {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    try:
        sb_stocks   = get_smartbill_stocks()
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

        sb_qty   = int(sb_stocks[sku])
        wix_qty  = int(wix_info["currentQuantity"] or 0)

        if sb_qty == wix_qty:
            log.debug(f"  OK   {sku} — stoc identic ({sb_qty})")
            continue

        try:
            update_wix_inventory(
                wix_info["inventoryItemId"],
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
