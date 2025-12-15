#!/usr/bin/env python3
"""
Wallbox API Capture Script

This script performs a login and attempts to capture
the API structure through various methods.
"""

import sys

import requests
import urllib3

urllib3.disable_warnings()

BASE_URL = "https://192.168.178.109"
USERNAME = "admin"
PASSWORD = "trcuz&58Md#pzczD#tUJ"


def get_token():
    """Login und JWT Token holen."""
    resp = requests.post(
        f"{BASE_URL}/api/login",
        json={"username": USERNAME, "password": PASSWORD},
        verify=False,
        timeout=10,
    )
    if resp.status_code == 200:
        data = resp.json()
        return data.get("access_token")
    return None


def probe_endpoints(token):
    """Verschiedene API Endpoints testen."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

    # Basierend auf den Function-Namen im JS:
    # loadDashboardInformationGroups, loadCurrentErrors, loadConfigurationModel

    # Versuche verschiedene URL-Muster
    patterns = [
        # Direkte API-Pfade (bereits getestet - alle 404)
        # Versuche ohne /api/ Prefix
        "/dashboard",
        "/configuration",
        "/errors",
        "/status",
        "/info",
        # Versuche mit JSON suffix
        "/api/dashboard.json",
        "/api/configuration.json",
        # Versuche mit v1
        "/api/v1/dashboard",
        "/api/v1/configuration",
        "/api/v1/status",
        # Versuche REST-Pfade
        "/rest/dashboard",
        "/rest/configuration",
        # Webservice Pfade
        "/ws/dashboard",
        # GraphQL?
        "/graphql",
        # Backend Pfade
        "/backend/api/dashboard",
        "/backend/dashboard",
        # CGI-Stil
        "/cgi-bin/api",
        # Index-basiert
        "/api/index",
        "/api/main",
    ]

    results = {}
    for path in patterns:
        try:
            resp = requests.get(f"{BASE_URL}{path}", headers=headers, verify=False, timeout=5)
            results[path] = {
                "status": resp.status_code,
                "content_type": resp.headers.get("Content-Type", ""),
                "length": len(resp.content),
                "preview": resp.text[:200] if resp.status_code != 404 else "",
            }
            if resp.status_code == 200:
                print(f"✅ {path}: {resp.status_code} - {resp.headers.get('Content-Type', '')}")
        except Exception as e:
            results[path] = {"error": str(e)}

    return results


def main():
    print("🔐 Login...")
    token = get_token()
    if not token:
        print("❌ Login fehlgeschlagen!")
        sys.exit(1)

    print(f"✅ Token erhalten: {token[:50]}...")
    print("\n🔍 Probe Endpoints...")
    results = probe_endpoints(token)

    # Zeige alle nicht-404 Ergebnisse
    print("\n📊 Ergebnisse (nicht-404):")
    found = False
    for path, data in results.items():
        if isinstance(data, dict) and data.get("status") != 404:
            print(f"  {path}: {data}")
            found = True

    if not found:
        print("  Keine erfolgreichen Endpoints gefunden")
        print("\n💡 Empfehlung: Browser DevTools nutzen!")
        print("   1. Öffne https://192.168.178.109 im Browser")
        print("   2. Öffne Developer Tools (F12)")
        print("   3. Gehe zum Network Tab")
        print("   4. Navigiere durch das Webinterface")
        print("   5. Suche nach XHR/Fetch Requests")


if __name__ == "__main__":
    main()
