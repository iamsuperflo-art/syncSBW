# SmartBill → Wix Stock Sync

Sincronizează automat stocurile din SmartBill în Wix Stores, la fiecare 10 minute.

---

## Cum funcționează

```
SmartBill API  →  script Python  →  Wix Stores API
  (stocuri)       (la 10 min)       (actualizare qty)
```

- Preia toate produsele din SmartBill cu stocul curent
- Le compară cu produsele din Wix după **SKU**
- Dacă stocul diferă → actualizează Wix
- Dacă un produs din SmartBill nu există în Wix → îl ignoră

---

## PASUL 1 — Obține API key SmartBill

1. Intră pe [https://app.smartbill.ro](https://app.smartbill.ro)
2. Mergi la **Setări → Integrări → API**
3. Generează / copiază **Token-ul API**
4. Notează și **email-ul contului** și **CIF-ul firmei**

---

## PASUL 2 — Obține API key Wix

1. Intră pe [https://manage.wix.com](https://manage.wix.com)
2. Mergi la **Settings → Advanced → API Keys**
3. Click **+ Generate API Key**
4. Dă-i un nume (ex: "Stock Sync") și selectează permisiunile:
   - ✅ Wix Stores — Read & Write
5. Copiază **API Key**
6. Notează **Account ID** (apare în URL sau în pagina de API Keys)
7. Notează **Site ID** — îl găsești în URL când ești pe site-ul tău:
   `https://manage.wix.com/dashboard/**SITE_ID**/...`

---

## PASUL 3 — Deploy pe Railway (gratuit)

### 3.1 — Pune codul pe GitHub

```bash
# Creează un repo nou pe github.com, apoi:
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/USER/smartbill-wix-sync.git
git push -u origin main
```

### 3.2 — Creează proiect pe Railway

1. Intră pe [https://railway.app](https://railway.app) și loghează-te cu GitHub
2. Click **New Project → Deploy from GitHub repo**
3. Selectează repo-ul `smartbill-wix-sync`
4. Railway detectează automat Python și pornește build-ul

### 3.3 — Adaugă variabilele de mediu

În Railway, mergi la proiect → **Variables** și adaugă:

| Variabilă | Valoare |
|---|---|
| `SMARTBILL_EMAIL` | email@firmata.ro |
| `SMARTBILL_TOKEN` | tokenul din SmartBill |
| `SMARTBILL_CIF` | ex: RO12345678 |
| `WIX_API_KEY` | cheia din Wix |
| `WIX_ACCOUNT_ID` | ID-ul contului Wix |
| `WIX_SITE_ID` | ID-ul site-ului Wix |
| `SYNC_INTERVAL_SEC` | 600 |

### 3.4 — Pornește serviciul

Railway pornește automat după ce salvezi variabilele. Mergi la **Deployments → Logs** și ar trebui să vezi:

```
🚀 SmartBill → Wix Stock Sync pornit
   Interval: 600s (10 minute)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔄 Sincronizare pornită la 2024-01-15 10:00:00
SmartBill: 142 produse preluate
Wix: 138 variante găsite
  ✅  SKU001: 5 → 8
  ✅  SKU045: 12 → 0
Rezultat: 2 actualizate | 4 ignorate | 0 erori
⏳ Următoarea sincronizare în 10 minute...
```

---

## Rulare locală (opțional, pentru testare)

```bash
# Instalează dependențele
pip install -r requirements.txt

# Copiază și completează .env
cp .env.example .env
# editează .env cu valorile reale

# Rulează
python sync.py
```

---

## Troubleshooting

| Problemă | Soluție |
|---|---|
| `401 Unauthorized` SmartBill | Verifică email + token în SmartBill |
| `403 Forbidden` Wix | Verifică că API key-ul are permisiuni Stores |
| Produsele nu se actualizează | Verifică că SKU-urile sunt identice în ambele sisteme |
| `KeyError: SMARTBILL_EMAIL` | Variabilele de mediu nu sunt setate |

---

## Structura fișierelor

```
smartbill-wix-sync/
├── sync.py           # Scriptul principal
├── requirements.txt  # Dependențe Python
├── railway.toml      # Configurare Railway
├── .env.example      # Template variabile de mediu
├── .gitignore        # Exclude .env din git
└── README.md         # Acest fișier
```
