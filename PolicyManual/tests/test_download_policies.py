import sys
import os
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from download_policies import strip_tags, slugify, parse_policy_links, parse_policy_body


class StripTagsTests(unittest.TestCase):
    def test_removes_plain_html_tags(self):
        self.assertEqual(strip_tags('<p>Hello</p>'), 'Hello')

    def test_removes_script_blocks(self):
        html = 'before<script>var x=1;\nalert(x);</script>after'
        result = strip_tags(html)
        self.assertNotIn('<script>', result)
        self.assertNotIn('var x=1', result)
        self.assertIn('before', result)
        self.assertIn('after', result)

    def test_removes_style_blocks(self):
        html = 'before<style>\nbody { color: red; }\n</style>after'
        result = strip_tags(html)
        self.assertNotIn('<style>', result)
        self.assertNotIn('color: red', result)
        self.assertIn('before', result)
        self.assertIn('after', result)

    def test_decodes_html_entities(self):
        self.assertEqual(strip_tags('&amp; &lt;tag&gt;'), '& <tag>')

    def test_collapses_whitespace(self):
        self.assertEqual(strip_tags('  a   b  '), 'a b')


class SlugifyTests(unittest.TestCase):
    def test_basic_text(self):
        self.assertEqual(slugify('Hello World'), 'Hello_World')

    def test_preserves_dots_hyphens(self):
        self.assertEqual(slugify('policy-1.0'), 'policy-1.0')

    def test_strips_leading_trailing_underscores(self):
        result = slugify('  Hello  ')
        self.assertFalse(result.startswith('_'))
        self.assertFalse(result.endswith('_'))

    def test_empty_string_returns_policy(self):
        self.assertEqual(slugify(''), 'policy')

    def test_whitespace_only_returns_policy(self):
        self.assertEqual(slugify('   '), 'policy')

    def test_long_string_is_truncated(self):
        result = slugify('a' * 200)
        self.assertLessEqual(len(result), 120)


class ParsePolicyLinksTests(unittest.TestCase):
    _LINK = '/board-of-education/news/default-post-display-page/~board/board-of-education-policies/post/test-policy'

    def _make_html(self, href, label):
        return f'<a href="{href}">{label}</a>'

    def test_extracts_policy_link(self):
        html = self._make_html(self._LINK, 'Test Policy Title')
        items = parse_policy_links(html)
        self.assertEqual(len(items), 1)
        title, url = items[0]
        self.assertEqual(title, 'Test Policy Title')
        self.assertIn('bpcsd.org', url)

    def test_deduplicates_same_url(self):
        single = self._make_html(self._LINK, 'Policy A')
        html = single + single
        items = parse_policy_links(html)
        self.assertEqual(len(items), 1)

    def test_ignores_unrelated_links(self):
        html = '<a href="/other/page">Other Link</a>'
        items = parse_policy_links(html)
        self.assertEqual(items, [])

    def test_strips_html_from_label(self):
        html = self._make_html(self._LINK, '<span>Nested <b>Title</b></span>')
        items = parse_policy_links(html)
        self.assertEqual(len(items), 1)
        self.assertNotIn('<span>', items[0][0])


class ParsePolicyBodyTests(unittest.TestCase):
    # Phrase used by parse_policy_body to strip pagination cruft from the end of text.
    _PAGINATION_CUT = 'Previous posts Next posts'
    def _make_page(self, title, body, nav='', footer=''):
        return (
            f'<html><body>'
            f'<h1>{title}</h1>'
            f'<main>'
            f'{nav}'
            f'<div class="content">{body}</div>'
            f'{footer}'
            f'</main>'
            f'</body></html>'
        )

    def test_extracts_title_and_body(self):
        page = self._make_page('My Policy', '<p>Policy text here.</p>')
        result = parse_policy_body(page)
        self.assertIn('My Policy', result)
        self.assertIn('Policy text here.', result)

    def test_strips_nav_elements(self):
        page = self._make_page('P', 'body', nav='<nav>Nav links</nav>')
        result = parse_policy_body(page)
        self.assertNotIn('Nav links', result)

    def test_strips_footer_elements(self):
        page = self._make_page('P', 'body', footer='<footer>Footer text</footer>')
        result = parse_policy_body(page)
        self.assertNotIn('Footer text', result)

    def test_cuts_at_pagination_marker(self):
        page = self._make_page('P', f'real content {self._PAGINATION_CUT} extra junk')
        result = parse_policy_body(page)
        self.assertIn('real content', result)
        self.assertNotIn('extra junk', result)

    def test_fallback_title_when_no_h1(self):
        result = parse_policy_body('<html><body><p>text</p></body></html>')
        self.assertTrue(result.startswith('Policy'))


if __name__ == '__main__':
    unittest.main()
