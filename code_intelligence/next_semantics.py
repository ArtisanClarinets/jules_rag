import os
import re
from typing import Optional, Tuple, List

# Standard Next.js App Router special files
SEGMENT_TYPES = {
    "page": "page",
    "layout": "layout",
    "loading": "loading",
    "error": "error",
    "not-found": "not-found",
    "global-error": "error",
    "route": "route",
    "template": "template",
    "default": "default",
    "middleware": "middleware",
    "opendata-image": "other",
    "icon": "other",
    "apple-icon": "other",
    "sitemap": "other",
    "robots": "other"
}

def get_segment_type(filename: str) -> str:
    """
    Classify the file based on Next.js conventions.
    """
    base = os.path.basename(filename)
    name, _ = os.path.splitext(base)

    # Check for direct match
    if name in SEGMENT_TYPES:
        return SEGMENT_TYPES[name]

    # Check for middleware (can be .ts, .js)
    if name == "middleware":
        return "middleware"

    return "other"

def derive_next_route(filepath: str) -> Optional[str]:
    """
    Derive the Next.js route path from the file path.
    Only supports App Router conventions properly.

    Example:
      app/(marketing)/blog/[slug]/page.tsx -> /blog/:slug
      app/api/auth/[...nextauth]/route.ts -> /api/auth/*nextauth
    """
    parts = filepath.split(os.sep)

    # Identify 'app' directory index
    try:
        app_idx = parts.index("app")
    except ValueError:
        # Not in app dir, maybe middleware at root
        if get_segment_type(filepath) == "middleware":
            return "/"
        return None

    # We are interested in everything after 'app' up to the file
    route_parts = parts[app_idx + 1 : -1] # excluding filename
    filename = parts[-1]

    # If the file is not a route defining file (page.tsx, route.ts),
    # strictly speaking it doesn't define a route, but it belongs to one.
    # However, usually we only assign route paths to page/route files.
    # But for RAG context, it's useful to know the "associated route" for layout/loading too.

    clean_parts = []

    for part in route_parts:
        # 1. Ignore Route Groups (e.g. (marketing))
        if part.startswith("(") and part.endswith(")"):
            continue

        # 2. Ignore Parallel Routes (e.g. @slot)
        if part.startswith("@"):
            continue

        # 3. Handle Dynamic Segments
        if part.startswith("[") and part.endswith("]"):
            inner = part[1:-1]

            # Optional Catch-all [[...slug]]
            if inner.startswith("[") and inner.endswith("]"):
                inner = inner[1:-1]

            # Catch-all [...slug]
            if inner.startswith("..."):
                clean_parts.append(f"*{inner[3:]}")
            else:
                clean_parts.append(f":{inner}")
        else:
            clean_parts.append(part)

    route = "/" + "/".join(clean_parts)

    # Normalize trailing slash
    if route == "/" and not clean_parts:
        return "/"

    return route

def detect_next_directives(content: str) -> Tuple[bool, bool, str]:
    """
    Detect 'use client', 'use server' and 'runtime' config.
    Returns: (is_client, is_server, runtime)
    """
    is_client = False
    is_server = False
    runtime = "unknown"

    lines = content.splitlines()
    for line in lines[:20]: # Check first 20 lines for directives
        line = line.strip()
        if not line: continue

        if line.startswith(('"', "'")) and "use client" in line:
            is_client = True
        if line.startswith(('"', "'")) and "use server" in line:
            is_server = True

        # Detect runtime export
        # export const runtime = 'edge'
        if "export const runtime" in line:
            match = re.search(r"runtime\s*=\s*['\"](edge|nodejs)['\"]", line)
            if match:
                runtime = match.group(1)

    return is_client, is_server, runtime
