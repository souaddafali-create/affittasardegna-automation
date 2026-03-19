#!/usr/bin/env python3
"""
Fix pages showing the wrong template (e.g. homepage template instead of content).

Pages affected:
  /cookie-policy/
  /terms-of-service/
  /sitemap/
  /privacy-policy/

These pages need a simple content template (Elementor Canvas or theme default)
instead of the homepage template they currently show.

Usage:
    export WP_SITE_URL=https://affittasardegna.it
    export WP_USER=admin
    export WP_APP_PASSWORD=xxxx xxxx xxxx xxxx

    # Step 1: Diagnose — see current template for each page
    python wp_fix_page_templates.py diagnose

    # Step 2: Fix — assign correct template to all affected pages
    python wp_fix_page_templates.py fix

    # Fix a single page
    python wp_fix_page_templates.py fix --slug cookie-policy

    # Use a specific template
    python wp_fix_page_templates.py fix --template elementor_canvas
"""

import argparse
import json
import os
import sys
from base64 import b64encode

import requests


# Target pages that need template fix
TARGET_SLUGS = [
    "cookie-policy",
    "terms-of-service",
    "sitemap",
    "privacy-policy",
]


# ---------------------------------------------------------------------------
# WordPress REST API client
# ---------------------------------------------------------------------------

class WPClient:
    def __init__(self, site_url: str, user: str, app_password: str):
        self.base = site_url.rstrip("/") + "/wp-json/wp/v2"
        self.site_base = site_url.rstrip("/") + "/wp-json"
        self.session = requests.Session()
        token = b64encode(f"{user}:{app_password}".encode()).decode()
        self.session.headers.update({
            "Authorization": f"Basic {token}",
            "User-Agent": "affittasardegna-automation/1.0",
        })

    def get(self, endpoint: str, params: dict | None = None) -> requests.Response:
        url = f"{self.base}/{endpoint}"
        r = self.session.get(url, params=params or {}, timeout=30)
        r.raise_for_status()
        return r

    def post(self, endpoint: str, json_data: dict | None = None) -> requests.Response:
        url = f"{self.base}/{endpoint}"
        r = self.session.post(url, json=json_data or {}, timeout=60)
        r.raise_for_status()
        return r


def get_client() -> WPClient:
    site_url = os.environ.get("WP_SITE_URL")
    user = os.environ.get("WP_USER")
    app_password = os.environ.get("WP_APP_PASSWORD")
    if not all([site_url, user, app_password]):
        print("ERROR: Set WP_SITE_URL, WP_USER, WP_APP_PASSWORD env vars.")
        sys.exit(1)
    return WPClient(site_url, user, app_password)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def find_page_by_slug(client: WPClient, slug: str) -> dict | None:
    r = client.get("pages", {"slug": slug, "status": "any", "context": "edit"})
    pages = r.json()
    return pages[0] if pages else None


def get_available_templates(client: WPClient) -> dict:
    """Fetch available page templates from the REST API."""
    # WordPress exposes templates via the page schema
    try:
        r = client.session.options(f"{client.base}/pages", timeout=30)
        schema = r.json()
        templates = schema.get("schema", {}).get("properties", {}).get("template", {}).get("enum", [])
        return templates
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_diagnose(args):
    """Show current template assignment for each target page."""
    client = get_client()

    print(f"\n{'='*60}")
    print("DIAGNOSING PAGE TEMPLATES")
    print(f"{'='*60}\n")

    # Check available templates
    print("--- Available Page Templates ---")
    try:
        # Get one page to inspect its template options
        r = client.session.options(f"{client.base}/pages", timeout=30)
        if r.status_code == 200:
            print("  (Use REST schema to list templates — or check diagnose output below)")
    except Exception:
        pass

    # Check each target page
    print("\n--- Target Pages ---")
    for slug in TARGET_SLUGS:
        page = find_page_by_slug(client, slug)
        if not page:
            print(f"\n  /{slug}/ — NOT FOUND")
            continue

        page_id = page["id"]
        title = page.get("title", {}).get("raw", "")
        template = page.get("template", "")
        status = page.get("status", "")
        content_raw = page.get("content", {}).get("raw", "")
        meta = page.get("meta", {})
        elementor_mode = meta.get("_elementor_edit_mode", "")

        print(f"\n  /{slug}/")
        print(f"    ID:        {page_id}")
        print(f"    Title:     {title}")
        print(f"    Status:    {status}")
        print(f"    Template:  '{template}' {'(DEFAULT/EMPTY)' if not template else ''}")
        print(f"    Elementor: {elementor_mode or 'none'}")
        print(f"    Content:   {len(content_raw)} chars")

        # Check for Elementor markers
        has_elementor = "elementor" in content_raw.lower() if content_raw else False
        print(f"    Has Elementor in content: {has_elementor}")

        if content_raw:
            print(f"    Content preview: {content_raw[:200]}...")

    # Also show homepage for reference
    print(f"\n--- Homepage (reference) ---")
    homepage = find_page_by_slug(client, "home")
    if not homepage:
        # Try front page
        try:
            r = client.get("pages", {"per_page": 5, "orderby": "menu_order", "order": "asc", "context": "edit"})
            pages = r.json()
            if pages:
                hp = pages[0]
                print(f"  First page: ID={hp['id']} slug={hp.get('slug','')} template='{hp.get('template','')}'")
        except Exception:
            pass
    else:
        print(f"  ID={homepage['id']} template='{homepage.get('template', '')}'")

    # Show a known working page with correct template for comparison
    print(f"\n--- Known working pages (reference) ---")
    for ref_slug in ["localita", "chi-siamo", "contatti"]:
        ref = find_page_by_slug(client, ref_slug)
        if ref:
            print(f"  /{ref_slug}/: ID={ref['id']} template='{ref.get('template', '')}'")

    print(f"\n{'='*60}")
    print("DIAGNOSIS COMPLETE")
    print(f"{'='*60}")
    print(f"\nTo fix all pages:")
    print(f"  python wp_fix_page_templates.py fix")
    print(f"\nTo fix with a specific template:")
    print(f"  python wp_fix_page_templates.py fix --template elementor_canvas")
    print(f"  python wp_fix_page_templates.py fix --template default")


def cmd_fix(args):
    """Assign the correct template to target pages."""
    client = get_client()
    template = args.template  # e.g. "elementor_canvas", "default", or ""
    slugs = [args.slug] if args.slug else TARGET_SLUGS

    print(f"\n{'='*60}")
    print(f"FIXING PAGE TEMPLATES → '{template}'")
    print(f"{'='*60}\n")

    results = []
    for slug in slugs:
        page = find_page_by_slug(client, slug)
        if not page:
            print(f"  /{slug}/ — NOT FOUND, skipping")
            results.append((slug, "NOT FOUND"))
            continue

        page_id = page["id"]
        old_template = page.get("template", "")
        print(f"  /{slug}/ (ID={page_id}): '{old_template}' → '{template}'")

        if old_template == template:
            print(f"    Already correct, skipping.")
            results.append((slug, "ALREADY OK"))
            continue

        # Build update payload
        update_data = {"template": template}

        # If switching away from Elementor, also clear Elementor edit mode
        # so WordPress uses the standard template rendering
        if template in ("default", ""):
            update_data["meta"] = {
                "_elementor_edit_mode": "",
            }

        if not args.yes:
            confirm = input(f"    Change template for /{slug}/? [y/N]: ").strip().lower()
            if confirm != "y":
                print(f"    Skipped.")
                results.append((slug, "SKIPPED"))
                continue

        try:
            r = client.post(f"pages/{page_id}", update_data)
            result = r.json()
            new_template = result.get("template", "")
            print(f"    Updated! New template: '{new_template}'")
            results.append((slug, "FIXED"))
        except requests.HTTPError as e:
            print(f"    ERROR: {e}")
            if e.response:
                print(f"    Response: {e.response.text[:300]}")
            results.append((slug, f"ERROR: {e}"))

    # Summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    for slug, status in results:
        print(f"  /{slug}/ — {status}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Fix page templates via WordPress REST API"
    )

    sub = parser.add_subparsers(dest="command", required=True)

    # diagnose
    sub.add_parser("diagnose", help="Show current template for each affected page")

    # fix
    p_fix = sub.add_parser("fix", help="Assign correct template to pages")
    p_fix.add_argument("--template", default="elementor_canvas",
                       help="Template to assign (default: elementor_canvas). "
                            "Use 'default' for theme default, or 'elementor_canvas' for blank canvas.")
    p_fix.add_argument("--slug", help="Fix only this slug (default: all target pages)")
    p_fix.add_argument("-y", "--yes", action="store_true", help="Skip confirmation")

    args = parser.parse_args()
    {"diagnose": cmd_diagnose, "fix": cmd_fix}[args.command](args)


if __name__ == "__main__":
    main()
