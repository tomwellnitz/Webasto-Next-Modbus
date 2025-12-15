#!/usr/bin/env python3
"""Analyze the Webasto Next wallbox web interface to discover REST API endpoints.

Usage:
    python scripts/analyze_webinterface.py --host <IP> --user admin --password <pwd>

This script will:
1. Attempt to login to the web interface
2. Probe common API endpoints
3. Output a report of discovered endpoints and their responses
"""

from __future__ import annotations

import argparse
import json
from typing import Any

import requests
import urllib3

# Disable SSL warnings for self-signed certificates
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Common API endpoint patterns to probe
COMMON_ENDPOINTS = [
    # Root and info
    "/",
    "/api",
    "/api/",
    "/api/info",
    "/api/status",
    "/api/config",
    "/api/settings",
    "/api/system",
    "/api/version",
    "/api/device",
    "/api/device/info",
    # Webasto-specific (based on menu structure)
    "/api/led",
    "/api/led/brightness",
    "/api/network",
    "/api/network/wifi",
    "/api/network/lan",
    "/api/network/status",
    "/api/hems",
    "/api/backend",
    "/api/auth",
    "/api/power",
    "/api/firmware",
    "/api/firmware/version",
    "/api/update",
    "/api/charging",
    "/api/charging/status",
    "/api/charging/session",
    "/api/charging/history",
    "/api/evse",
    "/api/evse/status",
    "/api/evse/config",
    "/api/wallbox",
    "/api/wallbox/info",
    "/api/wallbox/status",
    "/api/user",
    "/api/users",
    "/api/rfid",
    "/api/ocpp",
    "/api/modbus",
    "/api/modbus/config",
    # Time and scheduling
    "/api/time",
    "/api/ntp",
    "/api/schedule",
    "/api/schedules",
    # Statistics
    "/api/stats",
    "/api/statistics",
    "/api/history",
    "/api/energy",
    "/api/meter",
    "/api/meter/values",
    # System
    "/api/reboot",
    "/api/reset",
    "/api/factory-reset",
    "/api/logs",
    "/api/diagnostics",
    # CGI endpoints (older style)
    "/cgi-bin/api",
    "/cgi-bin/status",
    "/cgi-bin/config",
    # JSON-RPC style
    "/json",
    "/jsonrpc",
    "/rpc",
    # Other common patterns
    "/data",
    "/data.json",
    "/status.json",
    "/config.json",
    "/info.json",
    "/system.json",
]


def probe_endpoint(
    session: requests.Session,
    base_url: str,
    endpoint: str,
) -> dict[str, Any] | None:
    """Probe a single endpoint and return the result."""
    url = f"{base_url}{endpoint}"
    try:
        response = session.get(url, timeout=5, verify=False)
        content_type = response.headers.get("Content-Type", "")

        result: dict[str, Any] = {
            "url": url,
            "status_code": response.status_code,
            "content_type": content_type,
            "content_length": len(response.content),
        }

        # Try to parse as JSON
        if "json" in content_type.lower() or response.text.strip().startswith(("{", "[")):
            try:
                result["json"] = response.json()
            except json.JSONDecodeError:
                result["text"] = response.text[:500]
        elif "html" in content_type.lower():
            # Extract title from HTML
            if "<title>" in response.text.lower():
                start = response.text.lower().find("<title>") + 7
                end = response.text.lower().find("</title>")
                if end > start:
                    result["html_title"] = response.text[start:end].strip()
            result["is_html"] = True
        else:
            result["text"] = response.text[:500] if response.text else None

        return result

    except requests.exceptions.Timeout:
        return {"url": url, "error": "timeout"}
    except requests.exceptions.ConnectionError:
        return {"url": url, "error": "connection_error"}
    except Exception as e:
        return {"url": url, "error": str(e)}


def try_login(
    session: requests.Session,
    base_url: str,
    username: str,
    password: str,
) -> bool:
    """Attempt to login using common authentication patterns."""
    print(f"\n🔐 Attempting login as '{username}'...")

    # Common login endpoints and payload formats
    login_attempts = [
        # JSON body
        ("/api/login", {"username": username, "password": password}),
        ("/api/auth", {"username": username, "password": password}),
        ("/api/auth/login", {"username": username, "password": password}),
        ("/login", {"username": username, "password": password}),
        ("/api/session", {"user": username, "pass": password}),
        # Form data style
        ("/api/login", {"user": username, "pwd": password}),
    ]

    for endpoint, payload in login_attempts:
        url = f"{base_url}{endpoint}"
        try:
            # Try POST with JSON
            response = session.post(
                url,
                json=payload,
                timeout=5,
                verify=False,
            )
            if response.status_code in (200, 201, 204):
                print(f"  ✅ Login successful via {endpoint} (JSON)")
                print(f"     Response: {response.text[:200]}")

                # Extract JWT token if present
                try:
                    data = response.json()
                    token = data.get("access_token") or data.get("token") or data.get("jwt")
                    if token:
                        session.headers.update({"Authorization": f"Bearer {token}"})
                        print("  🔑 JWT token extracted and added to session headers")
                except Exception:
                    pass

                return True

            # Try POST with form data
            response = session.post(
                url,
                data=payload,
                timeout=5,
                verify=False,
            )
            if response.status_code in (200, 201, 204):
                print(f"  ✅ Login successful via {endpoint} (form)")
                print(f"     Response: {response.text[:200]}")

                # Extract JWT token if present
                try:
                    data = response.json()
                    token = data.get("access_token") or data.get("token") or data.get("jwt")
                    if token:
                        session.headers.update({"Authorization": f"Bearer {token}"})
                        print("  🔑 JWT token extracted and added to session headers")
                except Exception:
                    pass

                return True

        except Exception:
            continue

    # Try HTTP Basic Auth on the main page
    session.auth = (username, password)
    try:
        response = session.get(f"{base_url}/", timeout=5, verify=False)
        if response.status_code == 200:
            print("  ✅ HTTP Basic Auth accepted")
            return True
    except Exception:
        pass

    print("  ⚠️  Could not determine login method. Continuing without auth...")
    return False


def analyze_html_for_api_hints(session: requests.Session, base_url: str) -> list[str]:
    """Analyze the main HTML page for JavaScript API hints."""
    print("\n🔍 Analyzing main page for API hints...")
    discovered: list[str] = []

    try:
        response = session.get(f"{base_url}/", timeout=10, verify=False)
        html = response.text

        # Look for API URLs in JavaScript
        import re

        # Find fetch/axios calls
        api_patterns = [
            r'fetch\(["\']([^"\']+)["\']',
            r'axios\.\w+\(["\']([^"\']+)["\']',
            r'url:\s*["\']([^"\']+)["\']',
            r'api["\']:\s*["\']([^"\']+)["\']',
            r'endpoint["\']:\s*["\']([^"\']+)["\']',
            r'href=["\']([^"\']*api[^"\']*)["\']',
            r'src=["\']([^"\']*\.js)["\']',
            r'["\'](/api/[^"\']+)["\']',
            r'GET\s+["\']([^"\']+)["\']',
            r'POST\s+["\']([^"\']+)["\']',
            r'PUT\s+["\']([^"\']+)["\']',
        ]

        for pattern in api_patterns:
            matches = re.findall(pattern, html, re.IGNORECASE)
            for match in matches:
                if match.startswith("/") or match.startswith("api"):
                    if match not in discovered:
                        discovered.append(match)
                        print(f"  Found: {match}")

        # Also fetch and analyze JavaScript files
        js_files = re.findall(r'src=["\']([^"\']*\.js)["\']', html)
        print(f"\n  📜 Found {len(js_files)} JavaScript files, analyzing...")

        for js_file in js_files:
            js_url = js_file if js_file.startswith("http") else f"{base_url}/{js_file.lstrip('/')}"
            try:
                js_response = session.get(js_url, timeout=10, verify=False)
                js_content = js_response.text
                print(f"    Analyzing: {js_file} ({len(js_content)} bytes)")

                # Look for API patterns in JS
                all_api_matches = re.findall(r'["\'](/api[^"\']*)["\']', js_content)
                for match in all_api_matches:
                    if match not in discovered and len(match) < 100:
                        discovered.append(match)
                        print(f"      Found API: {match}")

                # Also look for other patterns
                other_patterns = [
                    r'fetch\([`"\']([^`"\']+)[`"\']',
                    r'\.get\([`"\']([^`"\']+)[`"\']',
                    r'\.post\([`"\']([^`"\']+)[`"\']',
                    r'\.put\([`"\']([^`"\']+)[`"\']',
                    r'\.delete\([`"\']([^`"\']+)[`"\']',
                    r'baseURL[`"\']?\s*[:=]\s*[`"\']([^`"\']+)[`"\']',
                ]
                for pattern in other_patterns:
                    matches = re.findall(pattern, js_content, re.IGNORECASE)
                    for match in matches:
                        if match.startswith("/") and match not in discovered and len(match) < 100:
                            discovered.append(match)
                            print(f"      Found: {match}")

            except Exception as e:
                print(f"    Error fetching {js_file}: {e}")
                continue

    except Exception as e:
        print(f"  Error: {e}")

    return discovered


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze Webasto Next wallbox web interface")
    parser.add_argument("--host", required=True, help="Wallbox IP address or hostname")
    parser.add_argument("--user", default="admin", help="Username (default: admin)")
    parser.add_argument("--password", required=True, help="Password")
    parser.add_argument("--port", type=int, default=443, help="Port (default: 443)")
    parser.add_argument("--http", action="store_true", help="Use HTTP instead of HTTPS")
    parser.add_argument("--output", "-o", help="Output file for results (JSON)")

    args = parser.parse_args()

    protocol = "http" if args.http else "https"
    port_suffix = "" if args.port in (80, 443) else f":{args.port}"
    base_url = f"{protocol}://{args.host}{port_suffix}"

    print(f"🔌 Analyzing Webasto Next web interface at {base_url}")
    print("=" * 60)

    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (Webasto API Analyzer)",
            "Accept": "application/json, text/html, */*",
        }
    )

    # Try to login
    try_login(session, base_url, args.user, args.password)

    # Analyze HTML for API hints
    discovered_endpoints = analyze_html_for_api_hints(session, base_url)

    # Combine with common endpoints
    all_endpoints = list(set(COMMON_ENDPOINTS + discovered_endpoints))

    # Probe all endpoints
    print(f"\n📡 Probing {len(all_endpoints)} endpoints...")
    print("-" * 60)

    results: list[dict[str, Any]] = []
    interesting: list[dict[str, Any]] = []

    for endpoint in sorted(all_endpoints):
        result = probe_endpoint(session, base_url, endpoint)
        if result:
            results.append(result)

            # Check if interesting (not 404, not error)
            status = result.get("status_code", 0)
            if status not in (404, 401, 403, 405) and "error" not in result:
                interesting.append(result)
                emoji = "✅" if status == 200 else "⚠️"
                print(f"  {emoji} [{status}] {endpoint}")

                # Show JSON preview
                if "json" in result:
                    json_str = json.dumps(result["json"], indent=2)
                    if len(json_str) > 300:
                        json_str = json_str[:300] + "..."
                    for line in json_str.split("\n")[:10]:
                        print(f"      {line}")

    # Summary
    print("\n" + "=" * 60)
    print("📊 SUMMARY")
    print("=" * 60)
    print(f"Total endpoints probed: {len(all_endpoints)}")
    print(f"Interesting responses: {len(interesting)}")

    if interesting:
        print("\n🎯 Interesting endpoints found:")
        for r in interesting:
            print(f"  • {r.get('url')} [{r.get('status_code')}]")
            if "json" in r:
                keys = list(r["json"].keys()) if isinstance(r["json"], dict) else []
                if keys:
                    print(f"    Keys: {', '.join(keys[:10])}")

    # Save results
    if args.output:
        output_data = {
            "base_url": base_url,
            "total_probed": len(all_endpoints),
            "interesting": interesting,
            "all_results": results,
        }
        with open(args.output, "w") as f:
            json.dump(output_data, f, indent=2)
        print(f"\n💾 Results saved to {args.output}")

    print("\n✨ Done!")


if __name__ == "__main__":
    main()
