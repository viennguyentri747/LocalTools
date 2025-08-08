#!/usr/bin/env python3
"""
trace_commit_from_iesa_pkg_name.py – Locate a record in /version/history by its `version_string`.

Examples:
  python trace_commit_from_iesa_pkg_name.py 29.9.1.6
  python trace_commit_from_iesa_pkg_name.py 29.9.1.6 --base-url http://10.1.26.170:8765 --page-size 100
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Optional, Tuple

import requests


def clamp_page_size(n: int) -> int:
    # API constraints: min=1, max=100
    return max(1, min(100, n))


def fetch_page(
    session: requests.Session,
    base_url: str,
    page: int,
    size: int,
    timeout: int,
) -> Tuple[list[dict], int]:
    """
    Fetch one page. Returns (items, pages_count).

    - items: list of objects (may be empty)
    - pages_count: integer from the API's 'pages' field (0 if missing)
    """
    url = f"{base_url.rstrip('/')}/version/history"
    resp = session.get(
        url,
        params={"page": page, "size": size},
        headers={"accept": "application/json"},
        timeout=timeout,
    )
    resp.raise_for_status()
    data = resp.json()
    items = data.get("items", [])
    pages = int(data.get("pages", 0) or 0)
    return items, pages


def find_version(
    base_url: str,
    target_version: str,
    page_size: int = 100,
    timeout: int = 10,
    quiet: bool = False,
) -> Optional[dict]:
    """
    Scan pages 1..pages (from API metadata) for an exact version_string match.
    Returns the matching item dict, or None if not found.
    """
    page_size = clamp_page_size(page_size)
    total_searched = 0
    page = 1

    with requests.Session() as session:
        while True:
            items, pages = fetch_page(session, base_url, page, page_size, timeout)

            if not quiet:
                print(f"Searching page {page}... ({len(items)} items)")

            # Scan current page
            for item in items:
                total_searched += 1
                if item.get("version_string") == target_version:
                    if not quiet:
                        print(f"\n✓ Version '{target_version}' found!")
                        print(f"Total items searched: {total_searched}")
                    return item

            # Decide whether there are more pages to request
            page += 1
            if pages and page > pages:
                if not quiet:
                    print(f"\nSearch completed. Version '{target_version}' not found.")
                    print(f"Total items searched: {total_searched}")
                return None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Search /version/history for a given version_string."
    )
    parser.add_argument("version", help="Exact version_string to search for")
    parser.add_argument(
        "--base-url",
        default="http://10.1.26.170:8765",
        help="Base server URL (default: %(default)s)",
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=100,
        help="Page size (1..100). Default: %(default)s",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=10,
        help="HTTP timeout in seconds (default: %(default)s)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress progress logs; print only JSON result on success",
    )
    args = parser.parse_args()

    try:
        result = find_version(
            base_url=args.base_url,
            target_version=args.version,
            page_size=args.page_size,
            timeout=args.timeout,
            quiet=args.quiet,
        )
    except requests.RequestException as e:
        sys.exit(f"API request failed: {e}")
    except json.JSONDecodeError as e:
        sys.exit(f"Error parsing JSON response: {e}")
    except KeyboardInterrupt:
        sys.exit("Search interrupted by user.")

    if result is None:
        sys.exit(1)  # Not found -> non-zero exit code for scripting
    else:
        # Pretty-print the found item JSON (stdout)
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
