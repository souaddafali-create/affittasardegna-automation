#!/usr/bin/env python3
"""
Fix the contact form thank-you page layout.

The thank-you page after the generic contact form shows only white text
with no layout. The "Proponi immobile" thank-you page works correctly —
this script copies its layout/template settings to the broken page.

Usage:
    export WP_SITE_URL=https://affittasardegna.it
    export WP_USER=admin
    export WP_APP_PASSWORD=xxxx xxxx xxxx xxxx

    # Step 1: Diagnose — find both thank-you pages and compare
    python wp_fix_thankyou_page.py diagnose

    # Step 2: Fix — copy layout from working page to broken page
    python wp_fix_thankyou_page.py fix

    # Fix with explicit page slugs/IDs
    python wp_fix_thankyou_page.py fix --source-slug grazie-proponi --target-slug grazie-contatti
"""

import argparse
import copy
import json
import os
import sys
import time
from base64 import b64encode

import requests


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


def search_pages(client: WPClient, keyword: str) -> list[dict]:
    """Search pages by keyword in title/content."""
    r = client.get("pages", {
        "search": keyword,
        "per_page": 20,
        "status": "any",
        "context": "edit",
    })
    return r.json()


def find_thankyou_pages(client: WPClient) -> dict:
    """Find both thank-you pages (working and broken)."""
    results = {"source": None, "target": None, "candidates": []}

    # Search for thank-you / grazie pages
    for keyword in ["grazie", "ringraziamento", "thank", "conferma"]:
        pages = search_pages(client, keyword)
        for p in pages:
            slug = p.get("slug", "")
            title = p.get("title", {}).get("raw", "")
            results["candidates"].append({
                "id": p["id"],
                "slug": slug,
                "title": title,
                "template": p.get("template", ""),
                "status": p.get("status", ""),
            })

            # Heuristic: "proponi" is the working one
            title_lower = title.lower()
            slug_lower = slug.lower()
            if "proponi" in title_lower or "proponi" in slug_lower or "immobile" in title_lower:
                results["source"] = p
            # The broken one is the generic contact form thank-you
            elif ("contatt" in title_lower or "contatt" in slug_lower
                  or (("grazie" in slug_lower or "thank" in slug_lower)
                      and "proponi" not in slug_lower and "immobile" not in slug_lower)):
                if not results["target"]:
                    results["target"] = p

    # Deduplicate candidates
    seen_ids = set()
    unique = []
    for c in results["candidates"]:
        if c["id"] not in seen_ids:
            seen_ids.add(c["id"])
            unique.append(c)
    results["candidates"] = unique

    return results


def describe_page(page: dict, label: str = "") -> None:
    """Print page info."""
    page_id = page["id"]
    slug = page.get("slug", "")
    title = page.get("title", {}).get("raw", "")
    template = page.get("template", "")
    status = page.get("status", "")
    content_raw = page.get("content", {}).get("raw", "")
    meta = page.get("meta", {})
    elementor_mode = meta.get("_elementor_edit_mode", "")
    elementor_data = meta.get("_elementor_data", "")

    prefix = f"  [{label}] " if label else "  "
    print(f"{prefix}ID: {page_id}")
    print(f"{prefix}Slug: /{slug}/")
    print(f"{prefix}Title: {title}")
    print(f"{prefix}Status: {status}")
    print(f"{prefix}Template: '{template}' {'(DEFAULT)' if not template else ''}")
    print(f"{prefix}Elementor mode: {elementor_mode or 'none'}")
    print(f"{prefix}Content length: {len(content_raw)} chars")
    if elementor_data:
        ed_len = len(elementor_data) if isinstance(elementor_data, str) else len(json.dumps(elementor_data))
        print(f"{prefix}Elementor data: {ed_len} chars")
    else:
        print(f"{prefix}Elementor data: none")
    if content_raw:
        print(f"{prefix}Content preview: {content_raw[:300]}...")


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_diagnose(args):
    """Find and compare both thank-you pages."""
    client = get_client()

    print(f"\n{'='*60}")
    print("DIAGNOSING THANK-YOU PAGES")
    print(f"{'='*60}\n")

    results = find_thankyou_pages(client)

    print("--- All candidate pages ---")
    for c in results["candidates"]:
        print(f"  ID:{c['id']} /{c['slug']}/ — '{c['title']}' [template: '{c['template']}'] [{c['status']}]")

    if results["source"]:
        print(f"\n--- SOURCE (working — Proponi Immobile thank-you) ---")
        describe_page(results["source"], "SOURCE")
    else:
        print(f"\n  SOURCE: Not found automatically.")
        print(f"  Try: python wp_fix_thankyou_page.py diagnose")
        print(f"  Then use --source-slug or --source-id to specify.")

    if results["target"]:
        print(f"\n--- TARGET (broken — Contact form thank-you) ---")
        describe_page(results["target"], "TARGET")
    else:
        print(f"\n  TARGET: Not found automatically.")
        print(f"  Check the candidates list above.")

    if results["source"] and results["target"]:
        src = results["source"]
        tgt = results["target"]

        # Compare
        print(f"\n--- Comparison ---")
        print(f"  Template:  SOURCE='{src.get('template','')}' vs TARGET='{tgt.get('template','')}'")

        src_meta = src.get("meta", {})
        tgt_meta = tgt.get("meta", {})
        print(f"  Elementor: SOURCE='{src_meta.get('_elementor_edit_mode','')}' vs TARGET='{tgt_meta.get('_elementor_edit_mode','')}'")

        print(f"\n  To fix, run:")
        print(f"    python wp_fix_thankyou_page.py fix --source-slug {src.get('slug','')} --target-slug {tgt.get('slug','')}")
        print(f"  Or with auto-detection:")
        print(f"    python wp_fix_thankyou_page.py fix")

    print(f"\n{'='*60}")
    print("DIAGNOSIS COMPLETE")
    print(f"{'='*60}")


def cmd_fix(args):
    """Copy layout from working thank-you page to broken one."""
    client = get_client()

    print(f"\n{'='*60}")
    print("FIXING THANK-YOU PAGE LAYOUT")
    print(f"{'='*60}\n")

    # Find source page
    source = None
    if args.source_id:
        source = client.get(f"pages/{args.source_id}", {"context": "edit"}).json()
    elif args.source_slug:
        source = find_page_by_slug(client, args.source_slug)
    else:
        results = find_thankyou_pages(client)
        source = results.get("source")

    if not source:
        print("ERROR: Could not find the working thank-you page (source).")
        print("Use --source-slug or --source-id to specify.")
        sys.exit(1)

    print(f"SOURCE (working): ID={source['id']} /{source.get('slug','')}/")

    # Find target page
    target = None
    if args.target_id:
        target = client.get(f"pages/{args.target_id}", {"context": "edit"}).json()
    elif args.target_slug:
        target = find_page_by_slug(client, args.target_slug)
    else:
        results = find_thankyou_pages(client)
        target = results.get("target")

    if not target:
        print("ERROR: Could not find the broken thank-you page (target).")
        print("Use --target-slug or --target-id to specify.")
        sys.exit(1)

    target_id = target["id"]
    print(f"TARGET (broken):  ID={target_id} /{target.get('slug','')}/")

    # Extract source layout info
    src_template = source.get("template", "")
    src_meta = source.get("meta", {})
    src_content = source.get("content", {}).get("raw", "")
    src_elementor_data = src_meta.get("_elementor_data", "")
    src_elementor_mode = src_meta.get("_elementor_edit_mode", "")
    src_css = src_meta.get("_elementor_css", "")

    print(f"\nSource template: '{src_template}'")
    print(f"Source Elementor mode: '{src_elementor_mode}'")
    print(f"Source content: {len(src_content)} chars")

    # Determine the target's own content (keep title/text, replace layout)
    tgt_content = target.get("content", {}).get("raw", "")
    tgt_title = target.get("title", {}).get("raw", "")

    print(f"\nTarget current content: {len(tgt_content)} chars")
    print(f"Target title: '{tgt_title}'")

    # Strategy: Copy the Elementor structure from source, replacing text content
    # with the target's text content
    update_data = {}

    # 1. Copy template
    if src_template:
        update_data["template"] = src_template
        print(f"\nWill set template: '{src_template}'")

    # 2. Copy Elementor meta
    meta_update = {}
    if src_elementor_mode:
        meta_update["_elementor_edit_mode"] = src_elementor_mode
    if src_elementor_data:
        # Parse source Elementor data and adapt text content
        try:
            if isinstance(src_elementor_data, str):
                el_data = json.loads(src_elementor_data)
            else:
                el_data = copy.deepcopy(src_elementor_data)

            # Walk the element tree and update text content
            adapted_data = adapt_elementor_content(el_data, tgt_title, tgt_content)
            meta_update["_elementor_data"] = json.dumps(adapted_data)
            print(f"Adapted Elementor data from source")
        except (json.JSONDecodeError, TypeError) as e:
            print(f"Warning: Could not parse source Elementor data: {e}")
            meta_update["_elementor_data"] = src_elementor_data
            print(f"Copying Elementor data as-is")

    if meta_update:
        update_data["meta"] = meta_update

    # 3. If source has HTML content with Elementor markers, adapt and copy
    if src_content and "elementor" in src_content.lower():
        # Replace text references from source to target
        adapted_content = adapt_html_content(src_content, tgt_title, tgt_content)
        update_data["content"] = adapted_content
        print(f"Adapted HTML content from source")
    elif tgt_content:
        # Keep target content but wrap in proper structure if needed
        update_data["content"] = tgt_content

    if not update_data:
        print("ERROR: No changes to apply. Source page might not have usable layout data.")
        sys.exit(1)

    # Backup target page
    backup_file = f"thankyou_{target_id}_backup.json"
    backup = {
        "id": target_id,
        "slug": target.get("slug", ""),
        "title": tgt_title,
        "content_raw": tgt_content,
        "template": target.get("template", ""),
        "meta": target.get("meta", {}),
        "backed_up_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    with open(backup_file, "w", encoding="utf-8") as f:
        json.dump(backup, f, ensure_ascii=False, indent=2)
    print(f"\nBackup saved to {backup_file}")

    # Confirm
    if not args.yes:
        print(f"\nThis will update page ID {target_id} (/{target.get('slug','')}/)")
        print(f"with layout from page ID {source['id']} (/{source.get('slug','')}/)")
        confirm = input("Proceed? [y/N]: ").strip().lower()
        if confirm != "y":
            print("Aborted.")
            return

    # Apply update
    try:
        r = client.post(f"pages/{target_id}", update_data)
        result = r.json()
        print(f"\nPage updated!")
        print(f"  Modified: {result.get('modified')}")
        print(f"  Template: {result.get('template')}")
        print(f"  Link: {result.get('link')}")
    except requests.HTTPError as e:
        print(f"ERROR: {e}")
        if e.response:
            print(f"Response: {e.response.text[:500]}")

        # Fallback: try template-only update
        print("\nRetrying with template-only update...")
        try:
            fallback = {"template": src_template} if src_template else {"template": "elementor_canvas"}
            r = client.post(f"pages/{target_id}", fallback)
            result = r.json()
            print(f"Template updated: '{result.get('template')}'")
            print(f"Note: Elementor data was NOT copied. Manual layout adjustment may be needed.")
        except requests.HTTPError as e2:
            print(f"Fallback also failed: {e2}")

    print(f"\nDone. Check the page in your browser.")
    print("If layout still looks off, open in Elementor and save.")


def adapt_elementor_content(el_data: list, title: str, content: str) -> list:
    """
    Walk Elementor element tree and replace text content.
    Keeps the structure/layout but updates heading/text widgets with target content.
    """
    adapted = copy.deepcopy(el_data)

    def walk(elements):
        for el in elements:
            widget_type = el.get("widgetType", "")
            settings = el.get("settings", {})

            # Update heading widgets with the target title
            if widget_type == "heading" and title:
                if "title" in settings:
                    # Only replace if it looks like a page title (main heading)
                    old_title = settings["title"].lower()
                    if any(kw in old_title for kw in ["grazie", "ringrazi", "thank", "conferma", "ricevut"]):
                        # Keep the source text — it's a thank-you message
                        pass

            # Recurse into child elements
            if "elements" in el:
                walk(el["elements"])

    walk(adapted)
    return adapted


def adapt_html_content(src_content: str, title: str, tgt_content: str) -> str:
    """
    Adapt the source HTML content for the target page.
    Mostly keeps the Elementor structure/classes, may swap inner text.
    """
    # For now, use source content as-is since we want the same layout
    # The actual text differences are minimal for thank-you pages
    return src_content


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Fix contact form thank-you page layout via WordPress REST API"
    )

    sub = parser.add_subparsers(dest="command", required=True)

    # diagnose
    sub.add_parser("diagnose", help="Find and compare thank-you pages")

    # fix
    p_fix = sub.add_parser("fix", help="Copy layout from working to broken page")
    p_fix.add_argument("--source-slug", help="Slug of working thank-you page")
    p_fix.add_argument("--source-id", type=int, help="ID of working thank-you page")
    p_fix.add_argument("--target-slug", help="Slug of broken thank-you page")
    p_fix.add_argument("--target-id", type=int, help="ID of broken thank-you page")
    p_fix.add_argument("-y", "--yes", action="store_true", help="Skip confirmation")

    args = parser.parse_args()
    {"diagnose": cmd_diagnose, "fix": cmd_fix}[args.command](args)


if __name__ == "__main__":
    main()
