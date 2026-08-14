#!/usr/bin/env python3
"""The site must build, and stay findable and citable.

Two audiences are tested here. Humans need the pages to render and the links
to work. Machines need `llms.txt`, raw Markdown at stable URLs, and JSON-LD
that actually parses — because the goal is to be the source an answer engine
cites, and a broken structured-data block fails silently and forever.

Run:  python3 tests/test_site.py
"""

from __future__ import annotations

import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "site"))

import build as site_build  # noqa: E402
import markdown  # noqa: E402

BASE = "https://example.org/estate-agent"


class MarkdownRenderer(unittest.TestCase):
    def test_headings_get_stable_anchors(self) -> None:
        html = markdown.render("## The resolution ladder\n")
        self.assertIn('id="the-resolution-ladder"', html)

    def test_duplicate_headings_get_distinct_anchors(self) -> None:
        html = markdown.render("## Notes\n\ntext\n\n## Notes\n")
        self.assertIn('id="notes"', html)
        self.assertIn('id="notes-2"', html)

    def test_tables_render_and_scroll(self) -> None:
        html = markdown.render("| A | B |\n| --- | --- |\n| 1 | 2 |\n")
        self.assertIn("<table>", html)
        self.assertIn("<th>A</th>", html)
        self.assertIn("<td>2</td>", html)
        self.assertIn('class="scroll"', html)

    def test_code_fences_are_escaped_not_executed(self) -> None:
        html = markdown.render("```\n<script>alert(1)</script>\n```")
        self.assertNotIn("<script>alert", html)
        self.assertIn("&lt;script&gt;", html)

    def test_inline_code_is_not_reformatted(self) -> None:
        html = markdown.render("Use `a_b_c` and `**not bold**`.")
        self.assertIn("<code>a_b_c</code>", html)
        self.assertIn("<code>**not bold**</code>", html)

    def test_doc_links_are_rewritten_to_site_urls(self) -> None:
        html = markdown.render("See [tiers](tiers.md) and [x](tiers.md#one).")
        self.assertIn('href="tiers/"', html)
        self.assertIn('href="tiers/#one"', html)

    def test_lists_and_blockquotes(self) -> None:
        html = markdown.render("- one\n- two\n\n> quoted\n")
        self.assertIn("<ul><li>one</li><li>two</li></ul>", html)
        self.assertIn("<blockquote>", html)

    def test_strip_produces_a_description(self) -> None:
        text = markdown.strip("# Title\n\nSome **real** prose here.\n")
        self.assertNotIn("#", text)
        self.assertIn("real prose", text)


class SiteBuild(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.out = Path(cls.tmp.name) / "site"
        site_build.build(cls.out, BASE)
        cls.index = (cls.out / "index.html").read_text(encoding="utf-8")

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    # -- humans ---------------------------------------------------------

    def test_every_documented_page_is_published(self) -> None:
        for slug, _title, _description in site_build.PAGES + site_build.WORKFLOWS:
            with self.subTest(slug=slug):
                self.assertTrue(
                    (self.out / slug / "index.html").is_file(),
                    f"{slug} did not build",
                )

    def test_pages_have_exactly_one_h1(self) -> None:
        for page in self.out.rglob("index.html"):
            with self.subTest(page=page.name):
                text = page.read_text(encoding="utf-8")
                self.assertEqual(
                    1, len(re.findall(r"<h1[ >]", text)),
                    f"{page} should have exactly one h1",
                )

    def test_no_internal_link_is_broken(self) -> None:
        broken: list[str] = []
        for page in self.out.rglob("*.html"):
            text = page.read_text(encoding="utf-8")
            for match in re.finditer(r'href="(?!https?://|#|mailto:)([^"]+)"', text):
                target = match.group(1).split("#")[0]
                if not target or target.startswith("data:"):
                    continue
                resolved = (page.parent / target).resolve()
                if resolved.is_dir():
                    resolved = resolved / "index.html"
                if not resolved.exists():
                    broken.append(f"{page.relative_to(self.out)} -> {target}")
        self.assertEqual([], broken, f"broken links: {broken[:10]}")

    def test_assets_are_present_and_local(self) -> None:
        self.assertTrue((self.out / "assets" / "theme.css").is_file())
        self.assertTrue((self.out / "assets" / "hero.js").is_file())
        # A corporate laptop behind a proxy must render this instantly.
        for page in self.out.rglob("*.html"):
            text = page.read_text(encoding="utf-8")
            # rel="canonical" and rel="alternate" are legitimately
            # absolute; what must never be remote is a stylesheet or script.
            external = re.findall(
                r'<script[^>]+src="(https?://[^"]+)"'
                r'|<link[^>]+rel="stylesheet"[^>]+href="(https?://[^"]+)"',
                text,
            )
            external = [u for pair in external for u in pair if u]
            self.assertEqual(
                [], external, f"{page.name} loads an external asset: {external}"
            )

    def test_demo_is_on_the_home_page(self) -> None:
        self.assertIn('id="demo"', self.index)
        self.assertIn("assets/hero.js", self.index)

    # -- machines -------------------------------------------------------

    def test_structured_data_parses(self) -> None:
        for page in self.out.rglob("*.html"):
            text = page.read_text(encoding="utf-8")
            for match in re.finditer(
                r'<script type="application/ld\+json">(.*?)</script>', text, re.S
            ):
                with self.subTest(page=page.name):
                    data = json.loads(match.group(1))
                    self.assertIn("@context", data)
                    self.assertIn("@type", data)

    def test_faq_is_structured_and_question_shaped(self) -> None:
        blocks = re.findall(
            r'<script type="application/ld\+json">(.*?)</script>', self.index, re.S
        )
        faq = [json.loads(b) for b in blocks]
        faq = [f for f in faq if f.get("@type") == "FAQPage"]
        self.assertTrue(faq, "the home page needs FAQPage structured data")
        questions = [q["name"] for q in faq[0]["mainEntity"]]
        self.assertGreaterEqual(len(questions), 5)
        for question in questions:
            self.assertTrue(
                question.rstrip().endswith("?"),
                f"not question-shaped: {question}",
            )

    def test_llms_txt_indexes_every_page(self) -> None:
        llms = (self.out / "llms.txt").read_text(encoding="utf-8")
        self.assertTrue(llms.startswith("# Estate Agent"))
        for slug, _title, _description in site_build.PAGES:
            self.assertIn(f"{slug}.md", llms, f"{slug} missing from llms.txt")
        self.assertIn("spec.md", llms)

    def test_llms_full_contains_the_actual_text(self) -> None:
        full = (self.out / "llms-full.txt").read_text(encoding="utf-8")
        self.assertGreater(len(full), 20_000)
        self.assertIn("resolution ladder", full)
        self.assertIn("MUST NOT overwrite", full)

    def test_every_page_is_also_raw_markdown(self) -> None:
        """Agents fetch Markdown far more reliably than they parse HTML."""
        for slug, _title, _description in site_build.PAGES + site_build.WORKFLOWS:
            with self.subTest(slug=slug):
                self.assertTrue((self.out / f"{slug}.md").is_file())
        self.assertTrue((self.out / "spec.md").is_file())

    def test_pages_declare_their_markdown_alternate(self) -> None:
        page = (self.out / "estate" / "index.html").read_text(encoding="utf-8")
        self.assertIn('type="text/markdown"', page)

    def test_canonical_and_sitemap_agree(self) -> None:
        sitemap = (self.out / "sitemap.xml").read_text(encoding="utf-8")
        self.assertTrue(sitemap.startswith("<?xml"))
        for slug, _title, _description in site_build.PAGES:
            self.assertIn(f"{BASE}/{slug}/", sitemap)
        page = (self.out / "tiers" / "index.html").read_text(encoding="utf-8")
        self.assertIn(f'rel="canonical" href="{BASE}/tiers/"', page)

    def test_robots_allows_crawling(self) -> None:
        robots = (self.out / "robots.txt").read_text(encoding="utf-8")
        self.assertIn("Allow: /", robots)
        self.assertIn(f"Sitemap: {BASE}/sitemap.xml", robots)
        self.assertNotIn("Disallow: /\n", robots)

    def test_spec_anchors_are_stable(self) -> None:
        """Citations point at these; renaming one silently breaks them."""
        spec = (self.out / "spec" / "index.html").read_text(encoding="utf-8")
        for anchor in (
            "1-the-deed", "3-tiers", "4-the-resolution-ladder", "5-evidence",
            "6-ambiguity", "8-ship-cost-and-landing-order", "9-self-healing",
        ):
            self.assertIn(f'id="{anchor}"', spec, f"spec anchor {anchor} moved")

    def test_meta_descriptions_are_present_and_useful(self) -> None:
        for page in self.out.rglob("index.html"):
            text = page.read_text(encoding="utf-8")
            match = re.search(r'<meta name="description" content="([^"]*)"', text)
            self.assertIsNotNone(match, f"{page} has no description")
            self.assertGreater(
                len(match.group(1)), 40, f"{page} description is too thin"
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
