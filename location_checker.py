"""
Phone Number Location & Risk Checker (CLI)

Enhanced analysis using the phonenumbers library plus optional third-party
HLR/Telecom lookup APIs.  API keys are read from environment variables so
the tool works without them (graceful degradation).

Environment variables (all optional):
  TWILIO_ACCOUNT_SID   / TWILIO_AUTH_TOKEN  – Twilio Lookup v2
  NUMVERIFY_API_KEY                          – NumVerify HLR lookup
  IPQS_API_KEY                               – IPQualityScore IP check
"""

import os
import json
import requests
import phonenumbers
from phonenumbers import geocoder, carrier, timezone

# ---------------------------------------------------------------------------
# Number-type labels
# ---------------------------------------------------------------------------
NUMBER_TYPE_LABELS = {
    phonenumbers.PhoneNumberType.MOBILE:            "Mobile",
    phonenumbers.PhoneNumberType.FIXED_LINE:        "Fixed-line",
    phonenumbers.PhoneNumberType.FIXED_LINE_OR_MOBILE: "Fixed-line or Mobile",
    phonenumbers.PhoneNumberType.TOLL_FREE:         "Toll-free",
    phonenumbers.PhoneNumberType.PREMIUM_RATE:      "Premium-rate",
    phonenumbers.PhoneNumberType.SHARED_COST:       "Shared-cost",
    phonenumbers.PhoneNumberType.VOIP:              "VoIP",
    phonenumbers.PhoneNumberType.PERSONAL_NUMBER:   "Personal number",
    phonenumbers.PhoneNumberType.PAGER:             "Pager",
    phonenumbers.PhoneNumberType.UAN:               "UAN",
    phonenumbers.PhoneNumberType.VOICEMAIL:         "Voicemail",
    phonenumbers.PhoneNumberType.UNKNOWN:           "Unknown",
}

# Known VoIP / virtual-number carrier name fragments (lower-case)
VOIP_CARRIER_KEYWORDS = [
    "twilio", "google voice", "vonage", "bandwidth", "sinch",
    "telnyx", "skype", "magicjack", "lingo", "ooma", "ringcentral",
    "grasshopper", "openphone", "dialpad", "nextiva", "8x8",
]

# Known MVNO / virtual-network fragments (lower-case)
MVNO_KEYWORDS = [
    "mvno", "virtual", "prepaid", "boost", "cricket", "mint",
    "metro", "consumer cellular", "tracfone", "straight talk",
    "republic wireless", "ting", "visible", "google fi",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def normalize_phone_number(phone_number: str) -> str:
    """Strip non-digit characters; prepend +852 for bare 8-digit HK numbers."""
    normalized = ''.join(filter(str.isdigit, phone_number))
    if len(normalized) == 8:
        normalized = '+852' + normalized
    elif not phone_number.strip().startswith('+'):
        normalized = '+' + normalized
    else:
        normalized = phone_number.strip()
    return normalized


def _carrier_flags(carrier_name: str) -> dict:
    """Derive is_voip / is_virtual flags from carrier name heuristics."""
    name_lc = carrier_name.lower()
    return {
        "is_voip":    any(k in name_lc for k in VOIP_CARRIER_KEYWORDS),
        "is_virtual": any(k in name_lc for k in MVNO_KEYWORDS),
    }


# ---------------------------------------------------------------------------
# Local analysis (phonenumbers library only – no API key required)
# ---------------------------------------------------------------------------

def analyze_phone_local(phone_number: str) -> dict:
    """Return rich phone-number metadata using the phonenumbers library."""
    normalized = normalize_phone_number(phone_number)
    try:
        parsed = phonenumbers.parse(normalized, None)
    except phonenumbers.phonenumberutil.NumberParseException as exc:
        return {"error": str(exc)}

    valid = phonenumbers.is_valid_number(parsed)
    possible = phonenumbers.is_possible_number(parsed)
    num_type = phonenumbers.number_type(parsed)
    region = geocoder.description_for_number(parsed, "en")
    carrier_name = carrier.name_for_number(parsed, "en")
    timezones = list(timezone.time_zones_for_number(parsed))
    e164 = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
    intl  = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.INTERNATIONAL)

    flags = _carrier_flags(carrier_name)
    is_voip_type = num_type == phonenumbers.PhoneNumberType.VOIP
    is_toll_free = num_type == phonenumbers.PhoneNumberType.TOLL_FREE

    result = {
        "input":          phone_number,
        "e164":           e164,
        "international":  intl,
        "country_code":   parsed.country_code,
        "region":         region or "Unknown",
        "carrier":        carrier_name or "Unknown",
        "number_type":    NUMBER_TYPE_LABELS.get(num_type, "Unknown"),
        "timezones":      timezones,
        "is_valid":       valid,
        "is_possible":    possible,
        "is_voip":        is_voip_type or flags["is_voip"],
        "is_virtual":     flags["is_virtual"],
        "is_toll_free":   is_toll_free,
        "source":         "phonenumbers (local)",
    }
    return result


# ---------------------------------------------------------------------------
# Twilio Lookup v2 (optional – requires TWILIO_ACCOUNT_SID + TWILIO_AUTH_TOKEN)
# ---------------------------------------------------------------------------

def _twilio_lookup(e164: str) -> dict | None:
    sid   = os.getenv("TWILIO_ACCOUNT_SID", "")
    token = os.getenv("TWILIO_AUTH_TOKEN", "")
    if not sid or not token:
        return None
    url = (
        f"https://lookups.twilio.com/v2/PhoneNumbers/{e164}"
        "?Fields=line_type_intelligence,sim_swap,call_forwarding"
    )
    try:
        resp = requests.get(url, auth=(sid, token), timeout=10)
        resp.raise_for_status()
        data = resp.json()
        lti  = data.get("line_type_intelligence") or {}
        return {
            "is_valid":    data.get("valid", None),
            "carrier":     lti.get("carrier_name", ""),
            "line_type":   lti.get("type", ""),
            "is_ported":   lti.get("ported", None),
            "is_roaming":  lti.get("roaming", None),
            "mobile_country_code": lti.get("mobile_country_code", ""),
            "mobile_network_code": lti.get("mobile_network_code", ""),
            "source":      "Twilio Lookup v2",
        }
    except Exception:
        return None


# ---------------------------------------------------------------------------
# NumVerify HLR lookup (optional – requires NUMVERIFY_API_KEY)
# ---------------------------------------------------------------------------

def _numverify_lookup(e164: str) -> dict | None:
    api_key = os.getenv("NUMVERIFY_API_KEY", "")
    if not api_key:
        return None
    url = f"https://apilayer.net/api/validate?access_key={api_key}&number={e164}&format=1"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if not data.get("valid"):
            return {"is_valid": False, "source": "NumVerify"}
        line_type = data.get("line_type", "")
        return {
            "is_valid":    data.get("valid", False),
            "carrier":     data.get("carrier", ""),
            "line_type":   line_type,
            "location":    data.get("location", ""),
            "country_code": data.get("country_code", ""),
            "country_name": data.get("country_name", ""),
            "is_voip":     line_type.lower() == "voip",
            "source":      "NumVerify",
        }
    except Exception:
        return None


# ---------------------------------------------------------------------------
# IP VPN/Proxy detection (optional – IPQS_API_KEY; fallback: ipapi.co)
# ---------------------------------------------------------------------------

def analyze_ip(ip: str = "") -> dict:
    """
    Return VPN/proxy/tor flags for *ip*.
    If ip is empty, the lookup is skipped (no outbound call without an address).
    """
    if not ip:
        return {"note": "No IP address provided; skipping IP analysis."}

    api_key = os.getenv("IPQS_API_KEY", "")
    if api_key:
        url = f"https://www.ipqualityscore.com/api/json/ip/{api_key}/{ip}"
        try:
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            return {
                "ip":             ip,
                "country":        data.get("country_code", ""),
                "region":         data.get("region", ""),
                "city":           data.get("city", ""),
                "isp":            data.get("ISP", ""),
                "is_vpn":         data.get("vpn", False),
                "is_proxy":       data.get("proxy", False),
                "is_tor":         data.get("tor", False),
                "is_datacenter":  data.get("active_vpn", False),
                "fraud_score":    data.get("fraud_score", None),
                "source":         "IPQualityScore",
            }
        except Exception:
            pass

    # Free fallback: ipapi.co (no key required, rate-limited to 1 000 req/day)
    try:
        resp = requests.get(f"https://ipapi.co/{ip}/json/", timeout=10)
        resp.raise_for_status()
        data = resp.json()
        return {
            "ip":         ip,
            "country":    data.get("country_code", ""),
            "region":     data.get("region", ""),
            "city":       data.get("city", ""),
            "isp":        data.get("org", ""),
            "is_vpn":     None,   # not available in free tier
            "is_proxy":   None,
            "is_tor":     None,
            "note":       "VPN/proxy flags unavailable without IPQS_API_KEY",
            "source":     "ipapi.co (free fallback)",
        }
    except Exception as exc:
        return {"ip": ip, "error": str(exc)}


# ---------------------------------------------------------------------------
# Reverse geocoding (Nominatim – no key required)
# ---------------------------------------------------------------------------

def reverse_geocode(lat: float, lng: float) -> dict:
    """Convert GPS coordinates to a human-readable address via Nominatim."""
    url = "https://nominatim.openstreetmap.org/reverse"
    params = {"lat": lat, "lon": lng, "format": "json"}
    headers = {"User-Agent": "phone-number-location-checker/2.0"}
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        addr = data.get("address", {})
        return {
            "lat":      lat,
            "lng":      lng,
            "display":  data.get("display_name", ""),
            "city":     addr.get("city") or addr.get("town") or addr.get("village", ""),
            "state":    addr.get("state", ""),
            "country":  addr.get("country", ""),
            "country_code": addr.get("country_code", "").upper(),
            "source":   "OpenStreetMap Nominatim",
        }
    except Exception as exc:
        return {"lat": lat, "lng": lng, "error": str(exc)}


# ---------------------------------------------------------------------------
# Cell-tower / Wi-Fi triangulation (Mozilla Location Services)
# ---------------------------------------------------------------------------

def triangulate_cell(cell_towers: list[dict], wifi_aps: list[dict] | None = None) -> dict:
    """
    Estimate location from cell tower and/or Wi-Fi AP scan data.

    cell_towers – list of dicts with keys: mobileCountryCode, mobileNetworkCode,
                  locationAreaCode, cellId, [signalStrength]
    wifi_aps    – list of dicts with keys: macAddress, [signalStrength], [channel]

    Returns {lat, lng, accuracy, source} or {error}.
    """
    body: dict = {"considerIp": False}
    if cell_towers:
        body["cellTowers"] = cell_towers
    if wifi_aps:
        body["wifiAccessPoints"] = wifi_aps

    try:
        resp = requests.post(
            "https://location.services.mozilla.com/v1/geolocate?key=test",
            json=body,
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        loc = data.get("location", {})
        return {
            "lat":      loc.get("lat"),
            "lng":      loc.get("lng"),
            "accuracy": data.get("accuracy"),
            "source":   "Mozilla Location Services",
        }
    except Exception as exc:
        return {"error": str(exc)}


# ---------------------------------------------------------------------------
# Unified analysis
# ---------------------------------------------------------------------------

def full_analysis(phone_number: str, ip: str = "") -> dict:
    """
    Run the full analysis pipeline and return a unified risk profile.
    GPS coordinates are only available when called from the web interface.
    """
    report: dict = {}

    # 1. Local phone analysis
    local = analyze_phone_local(phone_number)
    report["phone"] = local

    if "error" in local:
        return report

    e164 = local.get("e164", "")

    # 2. HLR enrichment – Twilio first, NumVerify as fallback
    hlr = _twilio_lookup(e164) or _numverify_lookup(e164)
    if hlr:
        report["hlr"] = hlr
        # Merge key flags back into phone section
        for key in ("is_voip", "is_virtual", "is_ported", "is_roaming"):
            if hlr.get(key) is not None:
                report["phone"][key] = hlr[key]
        if hlr.get("carrier"):
            report["phone"]["carrier_live"] = hlr["carrier"]

    # 3. IP analysis
    if ip:
        report["ip"] = analyze_ip(ip)

    # 4. Risk summary
    phone_country = local.get("region", "")
    ip_country    = report.get("ip", {}).get("country", "")
    country_mismatch = (
        bool(ip_country) and bool(phone_country)
        and ip_country.upper() not in phone_country.upper()
        and phone_country.upper() not in ip_country.upper()
    )
    report["risk_summary"] = {
        "is_valid":           local.get("is_valid", False),
        "is_voip":            local.get("is_voip", False),
        "is_virtual":         local.get("is_virtual", False),
        "is_toll_free":       local.get("is_toll_free", False),
        "is_ported":          report.get("hlr", {}).get("is_ported"),
        "is_roaming":         report.get("hlr", {}).get("is_roaming"),
        "is_vpn":             report.get("ip", {}).get("is_vpn"),
        "is_proxy":           report.get("ip", {}).get("is_proxy"),
        "is_tor":             report.get("ip", {}).get("is_tor"),
        "country_mismatch":   country_mismatch,
        "fraud_score":        report.get("ip", {}).get("fraud_score"),
    }
    return report


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    phone_number = input("Enter a phone number (with country code, e.g. +14155552671): ").strip()
    ip_address   = input("Enter IP address to check (leave blank to skip): ").strip()

    result = full_analysis(phone_number, ip=ip_address)
    print(json.dumps(result, indent=2, default=str))
