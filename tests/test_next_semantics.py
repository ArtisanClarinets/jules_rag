import unittest
from code_intelligence.next_semantics import derive_next_route, get_segment_type, detect_next_directives

class TestNextSemantics(unittest.TestCase):
    def test_derive_route_basic(self):
        self.assertEqual(derive_next_route("app/page.tsx"), "/")
        self.assertEqual(derive_next_route("app/dashboard/page.tsx"), "/dashboard")
        self.assertEqual(derive_next_route("src/app/settings/page.tsx"), "/settings")

    def test_derive_route_groups(self):
        self.assertEqual(derive_next_route("app/(marketing)/about/page.tsx"), "/about")
        self.assertEqual(derive_next_route("app/(shop)/cart/page.tsx"), "/cart")

    def test_derive_route_dynamic(self):
        self.assertEqual(derive_next_route("app/blog/[slug]/page.tsx"), "/blog/:slug")
        self.assertEqual(derive_next_route("app/users/[id]/settings/page.tsx"), "/users/:id/settings")

    def test_derive_route_catch_all(self):
        self.assertEqual(derive_next_route("app/docs/[...slug]/page.tsx"), "/docs/*slug")
        # Optional catch all [[...slug]] usually treated same in path structure
        self.assertEqual(derive_next_route("app/shop/[[...category]]/page.tsx"), "/shop/*category")

    def test_derive_route_parallel(self):
        self.assertEqual(derive_next_route("app/dashboard/@analytics/page.tsx"), "/dashboard")

    def test_segment_type(self):
        self.assertEqual(get_segment_type("app/page.tsx"), "page")
        self.assertEqual(get_segment_type("app/layout.tsx"), "layout")
        self.assertEqual(get_segment_type("app/route.ts"), "route")
        self.assertEqual(get_segment_type("middleware.ts"), "middleware")
        self.assertEqual(get_segment_type("utils.ts"), "other")

    def test_detect_directives(self):
        content_client = """
        'use client';
        import { useState } from 'react';
        """
        c, s, r = detect_next_directives(content_client)
        self.assertTrue(c)
        self.assertFalse(s)
        self.assertEqual(r, "unknown")

        content_server = """
        "use server";
        export async function myAction() {}
        """
        c, s, r = detect_next_directives(content_server)
        self.assertFalse(c)
        self.assertTrue(s)

        content_runtime = """
        export const runtime = 'edge';
        """
        c, s, r = detect_next_directives(content_runtime)
        self.assertEqual(r, "edge")

if __name__ == "__main__":
    unittest.main()
