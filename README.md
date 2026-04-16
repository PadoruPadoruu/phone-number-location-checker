# Phone Number Location & Risk Checker

A multi-signal location and risk-analysis tool for phone numbers.  
It combines **phone metadata**, **real-time GPS**, **cell-tower triangulation**, and **IP intelligence** into a single unified risk profile.

> ⚠️ **Legal notice** — Real-time device location requires **explicit user consent** (the OS enforces this). All lookups must comply with GDPR/CCPA and the ToS of each API provider. Never use this tool to track someone without their knowledge and consent.

---

## Features

| Signal | What it tells you |
|---|---|
| `phonenumbers` library | Region, carrier name, number type (Mobile/Fixed/VoIP/Toll-free), timezones |
| Twilio Lookup v2 *(optional)* | Live carrier, ported status, roaming, line type |
| NumVerify HLR *(optional)* | Carrier, line type, validity, country |
| Browser GPS (`navigator.geolocation`) | Precise coordinates → reverse-geocoded address via OpenStreetMap |
| Cell-tower / Wi-Fi triangulation | Coarse location from cell IDs / BSSIDs via Mozilla Location Services |
| IP intelligence (IPQualityScore / ipapi.co) | VPN, proxy, Tor, datacenter, fraud score |
| Risk summary | Consolidated flags: `is_voip`, `is_virtual`, `is_roaming`, `is_ported`, `is_vpn`, `country_mismatch`, … |

---

## Requirements

- Python 3.10+

```bash
pip install -r requirements.txt
```

---

## Configuration (environment variables)

All third-party API keys are **optional**. The tool works without them (graceful degradation).

| Variable | Service | Free tier? |
|---|---|---|
| `TWILIO_ACCOUNT_SID` + `TWILIO_AUTH_TOKEN` | Twilio Lookup v2 — live carrier, porting, roaming | Trial credits |
| `NUMVERIFY_API_KEY` | NumVerify HLR — carrier, line type, validity | 100 req/month |
| `IPQS_API_KEY` | IPQualityScore — VPN/proxy/Tor/fraud score | 5 000 req/month |

Without API keys the tool still returns full `phonenumbers`-based metadata and reverse-geocoding.

---

## Usage

### CLI (phone number + optional IP)

```bash
python location_checker.py
# Enter a phone number (with country code, e.g. +14155552671):
# Enter IP address to check (leave blank to skip):
```

Output is a JSON risk profile:

```json
{
  "phone": { "e164": "+14155552671", "region": "California", "carrier": "AT&T", ... },
  "hlr":  { "is_ported": false, "is_roaming": false, ... },
  "ip":   { "is_vpn": false, "is_proxy": false, ... },
  "risk_summary": {
    "is_valid": true, "is_voip": false, "is_ported": false,
    "is_vpn": false, "country_mismatch": false, ...
  }
}
```

### Web app

```bash
python app.py
# Open http://localhost:5000
```

The web interface provides four panels:

1. **Phone Number Analysis** — type a number, click Analyse → risk badge grid + full JSON.
2. **Real-Time GPS** — click *Get My Location*; browser asks for permission; coordinates are reverse-geocoded server-side.
3. **Cell-Tower / Wi-Fi Triangulation** — paste cell-tower scan JSON (from a native mobile app) to get a coarse location estimate via Mozilla Location Services.
4. **IP / VPN / Proxy Check** — one-click check of your own IP address.

### API endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/analyze` | `{ phone, ip? }` → full risk profile |
| `POST` | `/api/locate` | `{ lat, lng }` → reverse-geocoded address |
| `POST` | `/api/cell-locate` | `{ cellTowers?, wifiAccessPoints? }` → estimated coordinates |
| `GET`  | `/api/ip-info` | VPN/proxy check for the caller's IP |

---

## Architecture

```
Browser / Client
    │
    ├─ GPS (navigator.geolocation) ──── POST /api/locate ──► Nominatim (OSM)
    ├─ Cell/Wi-Fi scan (native app) ─── POST /api/cell-locate ► Mozilla LS
    └─ IP address (HTTP header) ─────── GET  /api/ip-info ───► IPQualityScore / ipapi.co
                                        │
                                 POST /api/analyze
                                        │
                          phonenumbers lib (local)
                                        │
                          Twilio Lookup v2 / NumVerify (optional)
                                        │
                          Unified risk profile JSON
```

---

## Contributing

Contributions are welcome! Fork the repository, make your changes, and open a pull request.

## License

GNU General Public License v3.0 — see [LICENSE](LICENSE).
