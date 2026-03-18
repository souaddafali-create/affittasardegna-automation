#!/usr/bin/env python3
"""
Fix the Single Blog template: add featured image (post thumbnail).

The site uses Elementor Free + JetEngine. Elementor Free lacks a native
"Featured Image" widget, but JetEngine provides "Dynamic Image" that can
pull the post thumbnail.

This script:
1. DIAGNOSE: Finds the Elementor Single Blog template and shows its structure
2. FIX: Adds a JetEngine Dynamic Image widget (or HTML widget fallback)
   at the top of the template to display the featured image

Usage:
    export WP_SITE_URL=https://affittasardegna.it
    export WP_USER=admin
    export WP_APP_PASSWORD=xxxx xxxx xxxx xxxx

    # Step 1: Find and diagnose the blog template
    python wp_fix_blog_featured_image.py diagnose

    # Step 2a: Add featured image via JetEngine Dynamic Image widget
    python wp_fix_blog_featured_image.py fix --method jetengine

    # Step 2b: Add featured image via HTML widget with PHP shortcode
    python wp_fix_blog_featured_image.py fix --method html

    # Step 2c: Add featured image via custom CSS (simplest)
    python wp_fix_blog_featured_image.py fix --method css
"""

import argparse
import copy
import json
import os
import sys
import time
import uuid
from base64 import b64encode

import requests


# ---------------------------------------------------------------------------
# WordPress REST API client (same as wp_fix_guida_page.py)
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

    def get_raw(self, full_url: str, params: dict | None = None) -> requests.Response:
        r = self.session.get(full_url, params=params or {}, timeout=30)
        r.raise_for_status()
        return r

    def post_raw(self, full_url: str, json_data: dict | None = None) -> requests.Response:
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
# Template discovery
# ---------------------------------------------------------------------------

def find_elementor_templates(client: WPClient) -> list[dict]:
    """Find all Elementor templates (they're stored as 'elementor_library' CPT)."""
    templates = []

    # Method 1: Search in elementor_library custom post type
    for cpt in ["elementor_library", "elementor-thhf"]:  # thhf = theme header/footer
        try:
            r = client.get_raw(
                f"{client.base.replace('/wp/v2', '')}/wp/v2/{cpt}",
                {"per_page": 100, "context": "edit"}
            )
            templates.extend(r.json())
        except requests.HTTPError:
            pass

    # Method 2: Search JetEngine listings (they can act as templates)
    try:
        r = client.get_raw(
            f"{client.base.replace('/wp/v2', '')}/wp/v2/jet-engine",
            {"per_page": 100, "context": "edit"}
        )
        templates.extend(r.json())
    except requests.HTTPError:
        pass

    # Method 3: Try jet-theme-core templates
    try:
        r = client.get_raw(
            f"{client.base.replace('/wp/v2', '')}/wp/v2/jet-theme-core",
            {"per_page": 100, "context": "edit"}
        )
        templates.extend(r.json())
    except requests.HTTPError:
        pass

    return templates


def find_blog_template(client: WPClient) -> dict | None:
    """Try to find the Single Blog/Post template."""
    templates = find_elementor_templates(client)

    # Look for templates with "single", "blog", "post", "article" in the title
    keywords = ["single", "blog", "post", "article", "singolo", "articolo"]

    for tmpl in templates:
        title = tmpl.get("title", {})
        title_text = (title.get("raw", "") or title.get("rendered", "")).lower()
        for kw in keywords:
            if kw in title_text:
                return tmpl

    return None


def get_elementor_data_from_content(content_raw: str) -> list | None:
    """Try to extract Elementor data hints from the content HTML."""
    if not content_raw:
        return None
    # Elementor stores the rendered HTML in post_content
    # The actual JSON is in _elementor_data post meta
    return None


# ---------------------------------------------------------------------------
# Widget builders
# ---------------------------------------------------------------------------

def make_id() -> str:
    """Generate a short hex ID like Elementor uses."""
    return uuid.uuid4().hex[:7]


def build_jetengine_dynamic_image_widget() -> dict:
    """Build a JetEngine Dynamic Image widget that shows post thumbnail."""
    return {
        "id": make_id(),
        "elType": "widget",
        "widgetType": "jet-engine-dynamic-image",  # JetEngine widget
        "settings": {
            "dynamic_image_source": "post_thumbnail",
            "dynamic_image_size": "full",
            "dynamic_image_link": "none",
            "image_style": "default",
            "_margin": {"unit": "px", "top": "0", "right": "0", "bottom": "20", "left": "0"},
        },
        "elements": [],
    }


def build_jetlisting_dynamic_image_widget() -> dict:
    """Alternative: JetEngine listing dynamic field for image."""
    return {
        "id": make_id(),
        "elType": "widget",
        "widgetType": "jet-listing-dynamic-image",
        "settings": {
            "dynamic_image_source": "post_thumbnail",
            "dynamic_image_size": "full",
            "object_context": "default_object",
        },
        "elements": [],
    }


def build_html_widget_featured_image() -> dict:
    """Build an HTML widget with a shortcode/PHP for featured image."""
    # This requires a shortcode to be registered. We'll provide both options.
    html_content = """<div class="blog-featured-image">
    [jet_engine component="dynamic_image" field="post_thumbnail" size="full"]
</div>

<style>
.blog-featured-image {
    width: 100%;
    margin-bottom: 20px;
}
.blog-featured-image img {
    width: 100%;
    height: auto;
    border-radius: 8px;
    object-fit: cover;
    max-height: 500px;
}
</style>"""

    return {
        "id": make_id(),
        "elType": "widget",
        "widgetType": "html",
        "settings": {
            "html": html_content,
        },
        "elements": [],
    }


def build_css_snippet() -> str:
    """Return CSS to add to Customizer > Additional CSS, or Elementor custom CSS."""
    return """/* Featured Image for Single Blog Posts */
.single-post .elementor-section:first-child::before {
    content: '';
    display: block;
    width: 100%;
    padding-bottom: 56.25%; /* 16:9 aspect ratio */
    background-size: cover;
    background-position: center;
    border-radius: 8px;
    margin-bottom: 20px;
}

/* Alternative: If post has thumbnail class */
.single-post .post-thumbnail,
.single-post .wp-post-image {
    width: 100%;
    height: auto;
    max-height: 500px;
    object-fit: cover;
    border-radius: 8px;
    margin-bottom: 20px;
}"""


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_diagnose(args):
    """Diagnose the blog template setup."""
    client = get_client()

    print(f"\n{'='*60}")
    print("DIAGNOSING SINGLE BLOG TEMPLATE")
    print(f"{'='*60}\n")

    # 1. Find all Elementor templates
    print("--- Searching for Elementor templates ---")
    templates = find_elementor_templates(client)
    if templates:
        print(f"Found {len(templates)} templates:")
        for t in templates:
            title = t.get("title", {})
            title_text = title.get("raw", "") or title.get("rendered", "")
            t_type = t.get("type", t.get("template_type", "unknown"))
            print(f"  ID:{t['id']} type:{t_type} title: {title_text}")
    else:
        print("No Elementor templates found via REST API.")
        print("Templates might be stored in a custom post type not exposed to REST.")

    # 2. Search for the blog template specifically
    print(f"\n--- Looking for Single Blog template ---")
    blog_tmpl = find_blog_template(client)
    if blog_tmpl:
        tmpl_id = blog_tmpl["id"]
        title = blog_tmpl.get("title", {}).get("raw", "")
        print(f"Found candidate: ID={tmpl_id} title='{title}'")

        # Get full data
        content_raw = blog_tmpl.get("content", {}).get("raw", "")
        print(f"  Content length: {len(content_raw)} chars")

        meta = blog_tmpl.get("meta", {})
        elementor_keys = [k for k in meta if "elementor" in k.lower()]
        print(f"  Elementor meta keys: {elementor_keys}")

        if content_raw:
            print(f"  Content preview:")
            print(f"    {content_raw[:500]}")

        # Check for featured image related elements
        has_thumbnail_ref = "thumbnail" in content_raw.lower() or "featured" in content_raw.lower()
        has_dynamic_image = "dynamic-image" in content_raw.lower() or "dynamic_image" in content_raw.lower()
        print(f"\n  Has thumbnail/featured reference: {has_thumbnail_ref}")
        print(f"  Has dynamic image widget: {has_dynamic_image}")

        if not has_thumbnail_ref and not has_dynamic_image:
            print(f"\n  CONFIRMED: No featured image widget found in template.")
            print(f"  To fix, run:")
            print(f"    python wp_fix_blog_featured_image.py fix --method jetengine")
    else:
        print("Could not find Single Blog template via REST API.")

    # 3. Check JetEngine availability
    print(f"\n--- Checking JetEngine availability ---")
    try:
        r = client.get_raw(f"{client.site_base}/jet-engine/v2/listings", {"per_page": 10})
        listings = r.json()
        print(f"JetEngine REST API available. Found {len(listings)} listings.")
        for listing in listings[:5]:
            print(f"  - {listing.get('title', listing.get('id', '?'))}")
    except requests.HTTPError:
        try:
            # Try alternative endpoint
            r = client.get_raw(f"{client.site_base}/jet-cct/v1", {})
            print("JetEngine CCT API available.")
        except requests.HTTPError:
            print("JetEngine REST API not found at standard endpoints.")

    # 4. Check what registered widget types are available
    print(f"\n--- Checking available widget types ---")
    try:
        r = client.get_raw(f"{client.site_base}/elementor/v1/widgets")
        widgets = r.json()
        jet_widgets = [w for w in widgets if "jet" in str(w).lower()]
        print(f"Found {len(widgets)} Elementor widgets, {len(jet_widgets)} JetEngine widgets")
        if jet_widgets:
            for w in jet_widgets[:10]:
                print(f"  - {w}")
    except requests.HTTPError:
        print("Elementor widget API not available.")

    # 5. Check a recent blog post to see template in action
    print(f"\n--- Checking recent blog posts ---")
    try:
        r = client.get("posts", {"per_page": 3, "context": "edit", "_fields": "id,title,featured_media,link"})
        posts = r.json()
        for p in posts:
            has_img = "Yes" if p.get("featured_media", 0) > 0 else "No"
            print(f"  Post {p['id']}: '{p['title']['raw']}' - Featured image: {has_img} (media ID: {p.get('featured_media', 0)})")
            print(f"    Link: {p.get('link', 'N/A')}")
    except requests.HTTPError as e:
        print(f"  Could not fetch posts: {e}")

    print(f"\n{'='*60}")
    print("DIAGNOSIS COMPLETE")
    print(f"{'='*60}")
    print(f"\nRecommended fix methods (in order of preference):")
    print(f"  1. JetEngine Dynamic Image: python wp_fix_blog_featured_image.py fix --method jetengine")
    print(f"  2. HTML widget shortcode:   python wp_fix_blog_featured_image.py fix --method html")
    print(f"  3. CSS-only approach:        python wp_fix_blog_featured_image.py fix --method css")


def cmd_fix(args):
    """Add featured image to the blog template."""
    client = get_client()
    method = args.method

    print(f"\n{'='*60}")
    print(f"FIXING BLOG TEMPLATE - Method: {method}")
    print(f"{'='*60}\n")

    if method == "css":
        # CSS method: doesn't need the template, just adds CSS
        css = build_css_snippet()
        print("CSS-only method selected.")
        print("Add this CSS to your site via:")
        print("  WordPress Admin > Appearance > Customize > Additional CSS")
        print("  Or: Elementor > Site Settings > Custom CSS")
        print(f"\n{'-'*40}")
        print(css)
        print(f"{'-'*40}")
        print("\nNote: CSS-only approach has limitations. The post_thumbnail must")
        print("already be rendered somewhere in the HTML. If Elementor template")
        print("doesn't output it at all, you need method 'jetengine' or 'html'.")
        return

    # Find the blog template
    blog_tmpl = find_blog_template(client)
    if not blog_tmpl:
        print("ERROR: Could not find Single Blog template via REST API.")
        print("\nAlternative approaches:")
        print("  1. Find the template ID manually in WordPress admin")
        print("     (Elementor > My Templates, or JetEngine > Listings)")
        print("  2. Run with --template-id <ID>")
        print("  3. Use the CSS method: --method css")
        if args.template_id:
            print(f"\nUsing provided template ID: {args.template_id}")
            blog_tmpl = client.get(f"posts/{args.template_id}", {"context": "edit"}).json()
        else:
            sys.exit(1)

    tmpl_id = blog_tmpl["id"]
    title = blog_tmpl.get("title", {}).get("raw", "")
    content_raw = blog_tmpl.get("content", {}).get("raw", "")
    print(f"Template found: ID={tmpl_id} title='{title}'")

    # Build the widget
    if method == "jetengine":
        widget = build_jetengine_dynamic_image_widget()
        alt_widget = build_jetlisting_dynamic_image_widget()
        print("Using JetEngine Dynamic Image widget")
    elif method == "html":
        widget = build_html_widget_featured_image()
        alt_widget = None
        print("Using HTML widget with JetEngine shortcode")
    else:
        print(f"ERROR: Unknown method '{method}'")
        sys.exit(1)

    # Try to parse existing Elementor data from meta
    meta = blog_tmpl.get("meta", {})
    elementor_data_str = meta.get("_elementor_data", "")
    elementor_data = None

    if elementor_data_str:
        try:
            elementor_data = json.loads(elementor_data_str) if isinstance(elementor_data_str, str) else elementor_data_str
            print(f"Parsed existing Elementor data: {len(elementor_data)} sections")
        except (json.JSONDecodeError, TypeError):
            print("Could not parse existing _elementor_data")

    if elementor_data and isinstance(elementor_data, list) and len(elementor_data) > 0:
        # Insert widget at the top of the first section's first column
        new_data = copy.deepcopy(elementor_data)

        # Find first column and prepend our widget
        inserted = False
        for section in new_data:
            if section.get("elType") == "section":
                for column in section.get("elements", []):
                    if column.get("elType") == "column":
                        column["elements"].insert(0, widget)
                        inserted = True
                        break
            if inserted:
                break

        if not inserted:
            # Create a new section at the top
            new_section = {
                "id": make_id(),
                "elType": "section",
                "settings": {"layout": "full_width"},
                "elements": [{
                    "id": make_id(),
                    "elType": "column",
                    "settings": {"_column_size": 100},
                    "elements": [widget],
                }],
            }
            new_data.insert(0, new_section)

        print(f"Modified Elementor data: widget inserted at top")
    else:
        # No existing Elementor data — create minimal structure
        new_data = [{
            "id": make_id(),
            "elType": "section",
            "settings": {"layout": "full_width"},
            "elements": [{
                "id": make_id(),
                "elType": "column",
                "settings": {"_column_size": 100},
                "elements": [widget],
            }],
        }]
        print("Created new Elementor structure with featured image widget")

    # Confirm
    if not args.yes:
        print(f"\nThis will modify template ID {tmpl_id} ('{title}').")
        print(f"A featured image widget will be added at the top.")
        confirm = input("Proceed? [y/N]: ").strip().lower()
        if confirm != "y":
            print("Aborted.")
            return

    # Export backup first
    backup_file = f"blog_template_{tmpl_id}_backup.json"
    backup = {
        "id": tmpl_id,
        "title": title,
        "content_raw": content_raw,
        "meta": meta,
        "backed_up_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    with open(backup_file, "w", encoding="utf-8") as f:
        json.dump(backup, f, ensure_ascii=False, indent=2)
    print(f"Backup saved to {backup_file}")

    # Update the template
    new_data_json = json.dumps(new_data)

    update_payload = {
        "meta": {
            "_elementor_data": new_data_json,
        }
    }

    # Also update the content with a rendered version
    if method == "html":
        widget_html = widget["settings"]["html"]
        new_content = widget_html + "\n" + content_raw
        update_payload["content"] = new_content

    try:
        # Try updating as the correct CPT
        cpt_type = blog_tmpl.get("type", "")
        endpoint = f"posts/{tmpl_id}" if not cpt_type else f"{cpt_type}/{tmpl_id}"
        # For Elementor templates, use the library endpoint
        try:
            r = client.post(f"elementor_library/{tmpl_id}" if "elementor" in str(cpt_type).lower() else f"pages/{tmpl_id}",
                          update_payload)
        except requests.HTTPError:
            # Fallback: try posts endpoint
            r = client.post(f"posts/{tmpl_id}", update_payload)

        result = r.json()
        print(f"\nTemplate updated!")
        print(f"  Modified: {result.get('modified')}")
    except requests.HTTPError as e:
        print(f"ERROR: Could not update template: {e}")
        if e.response:
            print(f"Response: {e.response.text[:500]}")
        print(f"\nFallback: The widget JSON has been generated.")
        print(f"You can manually add it via Elementor editor.")

        widget_file = "featured_image_widget.json"
        with open(widget_file, "w") as f:
            json.dump(widget, f, indent=2)
        print(f"Widget JSON saved to {widget_file}")

        if alt_widget:
            alt_file = "featured_image_widget_alt.json"
            with open(alt_file, "w") as f:
                json.dump(alt_widget, f, indent=2)
            print(f"Alternative widget JSON saved to {alt_file}")

    print("\nDone. Check a blog post to verify the featured image appears.")
    print("If not, open the template in Elementor, verify the widget is there, and save.")


def cmd_shortcode(args):
    """Register a shortcode via a mu-plugin for featured image display."""
    client = get_client()

    print(f"\n{'='*60}")
    print("SHORTCODE METHOD")
    print(f"{'='*60}\n")

    php_code = """<?php
/**
 * Plugin Name: AffittaSardegna Featured Image Shortcode
 * Description: Provides [as_featured_image] shortcode for Elementor templates
 */

add_shortcode('as_featured_image', function($atts) {
    $atts = shortcode_atts(array(
        'size' => 'full',
        'class' => 'as-featured-image',
    ), $atts);

    if (!has_post_thumbnail()) {
        return '';
    }

    $img = get_the_post_thumbnail(null, $atts['size'], array(
        'class' => $atts['class'],
        'loading' => 'eager',
    ));

    return sprintf(
        '<div class="as-featured-image-wrapper">%s</div>',
        $img
    );
});

// Add default styles
add_action('wp_head', function() {
    if (!is_single()) return;
    echo '<style>
    .as-featured-image-wrapper {
        width: 100%;
        margin-bottom: 20px;
    }
    .as-featured-image-wrapper img {
        width: 100%;
        height: auto;
        max-height: 500px;
        object-fit: cover;
        border-radius: 8px;
    }
    </style>';
});
"""

    print("This PHP code creates a must-use plugin that provides")
    print("the [as_featured_image] shortcode for use in Elementor templates.")
    print()
    print("Installation steps:")
    print("  1. Connect to your server via FTP/SSH")
    print("  2. Navigate to: wp-content/mu-plugins/")
    print("     (create the folder if it doesn't exist)")
    print("  3. Create file: as-featured-image.php")
    print("  4. Paste this code:")
    print(f"\n{'-'*40}")
    print(php_code)
    print(f"{'-'*40}")
    print()
    print("Then in Elementor, add a Shortcode widget with:")
    print("  [as_featured_image]")
    print()
    print("Or add an HTML widget with:")
    print("  [as_featured_image size='large' class='my-custom-class']")

    # Save to file for reference
    out_file = "as-featured-image.php"
    with open(out_file, "w") as f:
        f.write(php_code)
    print(f"\nPHP file also saved locally as: {out_file}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Fix featured image in Single Blog template"
    )

    sub = parser.add_subparsers(dest="command", required=True)

    # diagnose
    sub.add_parser("diagnose", help="Find and analyze the blog template")

    # fix
    p_fix = sub.add_parser("fix", help="Add featured image widget to template")
    p_fix.add_argument("--method", choices=["jetengine", "html", "css"], default="jetengine",
                       help="Method to add featured image (default: jetengine)")
    p_fix.add_argument("--template-id", type=int, help="Override template ID")
    p_fix.add_argument("-y", "--yes", action="store_true", help="Skip confirmation")

    # shortcode
    sub.add_parser("shortcode", help="Generate mu-plugin shortcode for featured image")

    args = parser.parse_args()

    commands = {
        "diagnose": cmd_diagnose,
        "fix": cmd_fix,
        "shortcode": cmd_shortcode,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
