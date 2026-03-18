#!/usr/bin/env python3
"""
Fix the /guida-nord-sardegna/ page on affittasardegna.it.

The page was broken by pasting raw HTML into the classic editor,
overwriting Elementor's _elementor_data. This script:

1. DIAGNOSE: Fetches the page, its revisions, and Elementor meta
2. RECOVER: Finds the last working Elementor revision and restores it
3. INJECT (fallback): Wraps clean HTML in an Elementor HTML widget and pushes it

Usage:
    # Set credentials
    export WP_SITE_URL=https://affittasardegna.it
    export WP_USER=admin
    export WP_APP_PASSWORD=xxxx xxxx xxxx xxxx

    # Step 1: Diagnose the page
    python wp_fix_guida_page.py diagnose

    # Step 2a: Restore from a specific revision
    python wp_fix_guida_page.py restore --revision-id 1234

    # Step 2b: Inject clean HTML file
    python wp_fix_guida_page.py inject --html-file guida_nord_sardegna_clean.html

    # Step 2c: Restore the best Elementor revision automatically
    python wp_fix_guida_page.py restore --auto
"""

import argparse
import json
import os
import sys
import time
from base64 import b64encode
from urllib.parse import urljoin

import requests


# ---------------------------------------------------------------------------
# WordPress REST API client
# ---------------------------------------------------------------------------

class WPClient:
    """Minimal WordPress REST API client with Application Password auth."""

    def __init__(self, site_url: str, user: str, app_password: str):
        self.base = site_url.rstrip("/") + "/wp-json/wp/v2"
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

    def get_raw(self, full_url: str, params: dict | None = None) -> requests.Response:
        """GET with full URL (for custom endpoints outside /wp/v2)."""
        r = self.session.get(full_url, params=params or {}, timeout=30)
        r.raise_for_status()
        return r

    def post_raw(self, full_url: str, json_data: dict | None = None) -> requests.Response:
        """POST with full URL."""
        r = self.session.post(full_url, json=json_data or {}, timeout=60)
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
    """Find a page by slug. Returns the page dict or None."""
    r = client.get("pages", {"slug": slug, "status": "any", "_fields": "id,title,status,date,modified,link"})
    pages = r.json()
    return pages[0] if pages else None


def get_page_full(client: WPClient, page_id: int) -> dict:
    """Get full page data including content and meta."""
    r = client.get(f"pages/{page_id}", {"context": "edit"})
    return r.json()


def get_revisions(client: WPClient, page_id: int) -> list[dict]:
    """Get all revisions for a page."""
    r = client.get(f"pages/{page_id}/revisions", {"per_page": 100, "context": "edit"})
    return r.json()


def fetch_elementor_meta(client: WPClient, page_id: int) -> dict:
    """
    Try to read Elementor meta via multiple methods:
    1. Standard REST API meta (if registered with show_in_rest)
    2. Elementor's own REST endpoints
    3. A custom meta read endpoint
    """
    results = {}

    # Method 1: Check page meta from edit context
    page = get_page_full(client, page_id)
    meta = page.get("meta", {})
    results["rest_meta"] = meta

    # Method 2: Try Elementor REST API endpoint
    site_base = client.base.replace("/wp/v2", "")
    elementor_url = f"{site_base}/elementor/v1/document/{page_id}"
    try:
        r = client.get_raw(elementor_url)
        results["elementor_document"] = r.json()
    except requests.HTTPError:
        results["elementor_document"] = None

    # Method 3: Check content for Elementor markers
    content_raw = page.get("content", {}).get("raw", "")
    has_elementor_markers = "[elementor-template" in content_raw or "elementor-element" in content_raw
    results["has_elementor_in_content"] = has_elementor_markers
    results["content_length"] = len(content_raw)
    results["content_preview"] = content_raw[:500]

    return results


def check_revision_has_elementor(content_raw: str) -> bool:
    """Check if a revision's content looks like valid Elementor output."""
    indicators = [
        "elementor-element",
        "elementor-widget",
        "elementor-section",
        "elementor-column",
        "data-elementor-type",
    ]
    return any(ind in content_raw for ind in indicators)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_diagnose(args):
    """Diagnose the page state and find recoverable revisions."""
    client = get_client()

    slug = args.slug
    print(f"\n{'='*60}")
    print(f"DIAGNOSING PAGE: /{slug}/")
    print(f"{'='*60}\n")

    # 1. Find the page
    page_info = find_page_by_slug(client, slug)
    if not page_info:
        print(f"ERROR: Page with slug '{slug}' not found.")
        print("Trying to search all pages...")
        r = client.get("pages", {"search": "guida nord", "per_page": 20, "_fields": "id,title,slug,status,link"})
        for p in r.json():
            print(f"  - ID:{p['id']} slug:{p['slug']} status:{p['status']} title:{p['title']['rendered']}")
        return

    page_id = page_info["id"]
    print(f"Page found: ID={page_id}")
    print(f"  Title:    {page_info['title']['rendered']}")
    print(f"  Status:   {page_info['status']}")
    print(f"  Modified: {page_info['modified']}")
    print(f"  Link:     {page_info['link']}")

    # 2. Get full page data
    print(f"\n--- Page Content Analysis ---")
    page_full = get_page_full(client, page_id)
    content_raw = page_full.get("content", {}).get("raw", "")
    print(f"  Content length: {len(content_raw)} chars")
    print(f"  Has Elementor markers: {check_revision_has_elementor(content_raw)}")
    print(f"  Content preview (first 300 chars):")
    print(f"    {content_raw[:300]}")

    # 3. Check Elementor meta
    print(f"\n--- Elementor Meta ---")
    meta_info = fetch_elementor_meta(client, page_id)
    rest_meta = meta_info["rest_meta"]
    if rest_meta:
        # Look for elementor-related keys
        elementor_keys = [k for k in rest_meta if "elementor" in k.lower()]
        if elementor_keys:
            print(f"  Elementor meta keys found: {elementor_keys}")
            for k in elementor_keys:
                val = rest_meta[k]
                val_str = str(val)
                print(f"    {k}: {val_str[:200]}{'...' if len(val_str)>200 else ''}")
        else:
            print(f"  No Elementor meta keys in REST response.")
            print(f"  Available meta keys: {list(rest_meta.keys())[:20]}")
    else:
        print("  No meta returned by REST API.")

    if meta_info["elementor_document"]:
        print(f"  Elementor document API: Available")
        doc = meta_info["elementor_document"]
        if isinstance(doc, dict):
            print(f"    Keys: {list(doc.keys())[:10]}")
    else:
        print("  Elementor document API: Not available (expected if Elementor REST not registered)")

    # 4. Check revisions
    print(f"\n--- Revisions ---")
    try:
        revisions = get_revisions(client, page_id)
        print(f"  Found {len(revisions)} revisions")

        elementor_revisions = []
        for rev in revisions:
            rev_content = rev.get("content", {}).get("raw", "") or rev.get("content", {}).get("rendered", "")
            has_el = check_revision_has_elementor(rev_content)
            age = rev.get("date", "unknown")
            rev_info = {
                "id": rev["id"],
                "date": age,
                "has_elementor": has_el,
                "content_length": len(rev_content),
            }
            if has_el:
                elementor_revisions.append(rev_info)
            status = "✓ ELEMENTOR" if has_el else "  plain"
            print(f"    Rev {rev['id']} ({age}) - {len(rev_content)} chars {status}")

        if elementor_revisions:
            best = elementor_revisions[0]  # Most recent Elementor revision
            print(f"\n  BEST CANDIDATE FOR RESTORE: Revision {best['id']} from {best['date']}")
            print(f"    Content length: {best['content_length']} chars")
            print(f"\n  To restore, run:")
            print(f"    python wp_fix_guida_page.py restore --revision-id {best['id']}")
            print(f"\n  Or auto-restore the best revision:")
            print(f"    python wp_fix_guida_page.py restore --auto")
        else:
            print(f"\n  NO Elementor revisions found. Recovery from revisions not possible.")
            print(f"  You'll need to inject clean HTML:")
            print(f"    python wp_fix_guida_page.py inject --html-file your_clean.html")

    except requests.HTTPError as e:
        print(f"  Could not fetch revisions: {e}")

    # 5. Summary
    print(f"\n{'='*60}")
    print("DIAGNOSIS COMPLETE")
    print(f"{'='*60}")


def cmd_restore(args):
    """Restore the page from a revision."""
    client = get_client()
    slug = args.slug

    page_info = find_page_by_slug(client, slug)
    if not page_info:
        print(f"ERROR: Page '{slug}' not found.")
        sys.exit(1)

    page_id = page_info["id"]

    if args.auto:
        # Find the most recent Elementor revision
        revisions = get_revisions(client, page_id)
        best = None
        for rev in revisions:
            rev_content = rev.get("content", {}).get("raw", "") or rev.get("content", {}).get("rendered", "")
            if check_revision_has_elementor(rev_content):
                best = rev
                break
        if not best:
            print("ERROR: No Elementor revision found. Use 'inject' command instead.")
            sys.exit(1)
        revision_id = best["id"]
        print(f"Auto-selected revision {revision_id} from {best['date']}")
    else:
        revision_id = args.revision_id
        if not revision_id:
            print("ERROR: Provide --revision-id or --auto")
            sys.exit(1)

    # Fetch the revision content
    print(f"Fetching revision {revision_id}...")
    r = client.get(f"pages/{page_id}/revisions/{revision_id}", {"context": "edit"})
    revision = r.json()
    revision_content = revision.get("content", {}).get("raw", "")

    if not revision_content:
        print("ERROR: Revision has no content.")
        sys.exit(1)

    print(f"Revision content: {len(revision_content)} chars")
    print(f"Has Elementor markers: {check_revision_has_elementor(revision_content)}")

    # Confirm before overwriting
    if not args.yes:
        print(f"\nThis will overwrite page ID {page_id} content with revision {revision_id}.")
        confirm = input("Proceed? [y/N]: ").strip().lower()
        if confirm != "y":
            print("Aborted.")
            return

    # Update the page content
    print("Updating page content...")
    update_data = {"content": revision_content}
    r = client.post(f"pages/{page_id}", update_data)
    result = r.json()
    print(f"Page updated successfully!")
    print(f"  New modified date: {result.get('modified')}")
    print(f"  Link: {result.get('link')}")

    # Try to trigger Elementor regeneration
    print("\nNote: You may need to open the page in Elementor editor and click")
    print("'Update' to fully regenerate the Elementor CSS and data.")

    # Also try to restore via Elementor's own API
    site_base = client.base.replace("/wp/v2", "")
    elementor_url = f"{site_base}/elementor/v1/document/{page_id}/save"
    try:
        # Attempt to trigger Elementor save/regenerate
        r = client.post_raw(elementor_url, {"status": "publish"})
        print("Elementor document regeneration triggered.")
    except requests.HTTPError:
        print("(Elementor regeneration endpoint not available — manual editor save recommended)")


def cmd_inject(args):
    """Inject clean HTML as Elementor content."""
    client = get_client()
    slug = args.slug

    page_info = find_page_by_slug(client, slug)
    if not page_info:
        print(f"ERROR: Page '{slug}' not found.")
        sys.exit(1)

    page_id = page_info["id"]

    # Read the HTML file
    html_file = args.html_file
    if not os.path.exists(html_file):
        print(f"ERROR: File '{html_file}' not found.")
        sys.exit(1)

    with open(html_file, "r", encoding="utf-8") as f:
        clean_html = f.read()

    print(f"Read {len(clean_html)} chars from {html_file}")

    # Build Elementor JSON structure with the HTML in an HTML widget
    elementor_data = [
        {
            "id": "guida_section_1",
            "elType": "section",
            "settings": {
                "layout": "full_width",
                "content_width": {"size": 1140, "unit": "px"},
            },
            "elements": [
                {
                    "id": "guida_column_1",
                    "elType": "column",
                    "settings": {"_column_size": 100},
                    "elements": [
                        {
                            "id": "guida_html_widget",
                            "elType": "widget",
                            "widgetType": "html",
                            "settings": {
                                "html": clean_html,
                            },
                            "elements": [],
                        }
                    ],
                }
            ],
        }
    ]

    elementor_json = json.dumps(elementor_data)

    # Strategy 1: Update page content with the HTML
    # The raw HTML goes into post_content, the Elementor JSON goes into meta
    print(f"\nUpdating page ID {page_id}...")

    if not args.yes:
        print(f"This will replace the page content with the HTML from {html_file}")
        print(f"wrapped in an Elementor HTML widget structure.")
        confirm = input("Proceed? [y/N]: ").strip().lower()
        if confirm != "y":
            print("Aborted.")
            return

    # Update via REST API
    update_data = {
        "content": clean_html,
        "meta": {
            "_elementor_data": elementor_json,
            "_elementor_edit_mode": "builder",
            "_elementor_template_type": "wp-page",
            "_elementor_version": "3.21.0",  # Adjust to your version
        },
    }

    try:
        r = client.post(f"pages/{page_id}", update_data)
        result = r.json()
        print(f"Page content updated!")
        print(f"  Modified: {result.get('modified')}")
        print(f"  Link: {result.get('link')}")
    except requests.HTTPError as e:
        print(f"REST API update failed: {e}")
        print(f"Response: {e.response.text[:500] if e.response else 'N/A'}")

        # If meta update failed, try content-only
        print("\nRetrying with content-only update (no meta)...")
        update_data_fallback = {"content": clean_html}
        r = client.post(f"pages/{page_id}", update_data_fallback)
        result = r.json()
        print(f"Page content updated (without meta)!")
        print(f"  Modified: {result.get('modified')}")
        print(f"  Link: {result.get('link')}")
        print(f"\nNote: _elementor_data was NOT updated. You'll need to:")
        print(f"  1. Open the page in WordPress admin")
        print(f"  2. Switch to Elementor editor")
        print(f"  3. The HTML widget should have the new content")
        print(f"  4. Click 'Update' to save properly")

    print("\nDone. Check the page in your browser.")
    print("If it still looks broken, open in Elementor editor and save again.")


def cmd_export(args):
    """Export current page content and meta for backup."""
    client = get_client()
    slug = args.slug

    page_info = find_page_by_slug(client, slug)
    if not page_info:
        print(f"ERROR: Page '{slug}' not found.")
        sys.exit(1)

    page_id = page_info["id"]
    page_full = get_page_full(client, page_id)

    export = {
        "id": page_id,
        "slug": slug,
        "title": page_full.get("title", {}).get("raw", ""),
        "content_raw": page_full.get("content", {}).get("raw", ""),
        "meta": page_full.get("meta", {}),
        "exported_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }

    out_file = args.output or f"{slug}_backup.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(export, f, ensure_ascii=False, indent=2)

    print(f"Exported page data to {out_file}")
    print(f"  Content: {len(export['content_raw'])} chars")
    print(f"  Meta keys: {list(export['meta'].keys())}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Fix the /guida-nord-sardegna/ page via WordPress REST API"
    )
    parser.add_argument(
        "--slug", default="guida-nord-sardegna",
        help="Page slug (default: guida-nord-sardegna)"
    )

    sub = parser.add_subparsers(dest="command", required=True)

    # diagnose
    sub.add_parser("diagnose", help="Diagnose page state and find recoverable revisions")

    # restore
    p_restore = sub.add_parser("restore", help="Restore from a revision")
    p_restore.add_argument("--revision-id", type=int, help="Specific revision ID")
    p_restore.add_argument("--auto", action="store_true", help="Auto-select best Elementor revision")
    p_restore.add_argument("-y", "--yes", action="store_true", help="Skip confirmation")

    # inject
    p_inject = sub.add_parser("inject", help="Inject clean HTML as page content")
    p_inject.add_argument("--html-file", required=True, help="Path to clean HTML file")
    p_inject.add_argument("-y", "--yes", action="store_true", help="Skip confirmation")

    # export
    p_export = sub.add_parser("export", help="Export current page content for backup")
    p_export.add_argument("--output", help="Output file (default: {slug}_backup.json)")

    args = parser.parse_args()

    commands = {
        "diagnose": cmd_diagnose,
        "restore": cmd_restore,
        "inject": cmd_inject,
        "export": cmd_export,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
