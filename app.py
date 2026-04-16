"""
Flask web backend for the Phone Number Location & Risk Checker.

Routes
------
GET  /                  Serve the single-page frontend
POST /api/analyze       Full phone-number + IP analysis
POST /api/locate        Reverse-geocode GPS coordinates (from browser)
POST /api/cell-locate   Cell-tower / Wi-Fi triangulation via Mozilla LS
GET  /api/ip-info       VPN/proxy check for the request's own IP
"""

from flask import Flask, request, jsonify, render_template
from location_checker import (
    full_analysis,
    reverse_geocode,
    triangulate_cell,
    analyze_ip,
)

app = Flask(__name__)


# ---------------------------------------------------------------------------
# Frontend
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


# ---------------------------------------------------------------------------
# API: Full phone + IP analysis
# ---------------------------------------------------------------------------

@app.post("/api/analyze")
def api_analyze():
    """
    Body (JSON):
      phone  – phone number string (required)
      ip     – IP address to analyze (optional; defaults to request's remote IP)
    """
    data = request.get_json(silent=True) or {}
    phone = (data.get("phone") or "").strip()
    if not phone:
        return jsonify({"error": "phone is required"}), 400

    # If caller doesn't supply an IP we fall back to the request's remote addr.
    ip = (data.get("ip") or "").strip() or _real_ip()
    result = full_analysis(phone, ip=ip)
    return jsonify(result)


# ---------------------------------------------------------------------------
# API: Reverse geocoding
# ---------------------------------------------------------------------------

@app.post("/api/locate")
def api_locate():
    """
    Body (JSON): { lat: float, lng: float }
    Returns a human-readable address from OpenStreetMap Nominatim.
    """
    data = request.get_json(silent=True) or {}
    try:
        lat = float(data["lat"])
        lng = float(data["lng"])
    except (KeyError, TypeError, ValueError):
        return jsonify({"error": "lat and lng (floats) are required"}), 400

    result = reverse_geocode(lat, lng)
    if "error" in result:
        return jsonify({"error": "Reverse geocoding failed."}), 502
    return jsonify(result)


# ---------------------------------------------------------------------------
# API: Cell-tower / Wi-Fi triangulation
# ---------------------------------------------------------------------------

@app.post("/api/cell-locate")
def api_cell_locate():
    """
    Body (JSON):
      cellTowers       – array of cell-tower objects (optional)
      wifiAccessPoints – array of Wi-Fi AP objects   (optional)

    Cell-tower object keys:
      mobileCountryCode, mobileNetworkCode, locationAreaCode, cellId,
      signalStrength (optional)

    Wi-Fi AP object keys:
      macAddress, signalStrength (optional), channel (optional)
    """
    data = request.get_json(silent=True) or {}
    cell_towers = data.get("cellTowers") or []
    wifi_aps    = data.get("wifiAccessPoints") or []

    if not cell_towers and not wifi_aps:
        return jsonify({"error": "cellTowers or wifiAccessPoints are required"}), 400

    result = triangulate_cell(cell_towers, wifi_aps)
    if "error" in result:
        return jsonify({"error": "Triangulation failed."}), 502
    return jsonify(result)


# ---------------------------------------------------------------------------
# API: IP VPN/proxy check for the caller's own IP
# ---------------------------------------------------------------------------

@app.get("/api/ip-info")
def api_ip_info():
    """Returns VPN/proxy/tor flags for the caller's IP address."""
    ip = _real_ip()
    result = analyze_ip(ip)
    if "error" in result:
        return jsonify({"error": "IP analysis failed."}), 502
    return jsonify(result)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _real_ip() -> str:
    """Return the real client IP, honouring X-Forwarded-For when present."""
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr or ""


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # NOTE: For production deployments use a WSGI server (e.g. gunicorn) and
    # bind to a specific interface.  The 0.0.0.0 binding below is for
    # local development only.
    app.run(debug=False, host="0.0.0.0", port=5000)
