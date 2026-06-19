import unittest

from text_utils import clean_post_text


class TestCleanPostText(unittest.TestCase):
    # --- markdown images ---

    def test_removes_markdown_image(self):
        text = "Check this out!\n![screenshot](https://i.redd.it/abc123.jpg)\nPretty wild."
        result = clean_post_text(text)
        self.assertNotIn("![", result)
        self.assertNotIn("redd.it", result)
        self.assertIn("Check this out!", result)
        self.assertIn("Pretty wild.", result)

    def test_removes_markdown_image_with_empty_alt(self):
        result = clean_post_text("Look ![](https://imgur.com/x.png) here.")
        self.assertNotIn("imgur.com", result)
        self.assertIn("Look", result)
        self.assertIn("here.", result)

    def test_removes_multiple_images(self):
        text = "![a](https://a.com/1.jpg) text ![b](https://b.com/2.png) end"
        result = clean_post_text(text)
        self.assertNotIn("![", result)
        self.assertIn("text", result)
        self.assertIn("end", result)

    # --- markdown links ---

    def test_markdown_link_keeps_text(self):
        result = clean_post_text("Read [this article](https://example.com) now.")
        self.assertIn("this article", result)
        self.assertNotIn("example.com", result)

    def test_markdown_link_with_empty_text(self):
        result = clean_post_text("Click [](https://example.com) here.")
        self.assertNotIn("example.com", result)
        self.assertIn("here.", result)

    # --- bare URLs ---

    def test_removes_bare_http_url(self):
        result = clean_post_text("See http://imgur.com/abc for proof.")
        self.assertNotIn("imgur.com", result)
        self.assertIn("See", result)
        self.assertIn("for proof.", result)

    def test_removes_bare_https_url(self):
        result = clean_post_text("Source: https://reddit.com/r/foo/comments/123/title")
        self.assertNotIn("reddit.com", result)

    def test_removes_url_not_http(self):
        # Non-http schemes should not be stripped
        result = clean_post_text("See ftp://files.example.com for details.")
        self.assertIn("ftp://", result)

    # --- HTML entities ---

    def test_decodes_amp(self):
        self.assertEqual(clean_post_text("fish &amp; chips"), "fish & chips")

    def test_decodes_lt_gt(self):
        self.assertEqual(clean_post_text("&lt;br&gt;"), "<br>")

    def test_decodes_nbsp(self):
        result = clean_post_text("hello&nbsp;world")
        self.assertIn("hello world", result)

    def test_removes_zero_width_space_entity(self):
        result = clean_post_text("hello&#x200B;world")
        self.assertNotIn("&#x200B;", result)
        self.assertIn("helloworld", result)

    # --- zero-width Unicode characters ---

    def test_removes_zero_width_unicode(self):
        text = "hello\u200bworld"
        result = clean_post_text(text)
        self.assertNotIn("\u200b", result)
        self.assertEqual(result, "helloworld")

    def test_removes_bom(self):
        result = clean_post_text("\ufeffHello")
        self.assertNotIn("\ufeff", result)
        self.assertEqual(result, "Hello")

    # --- blank line collapsing ---

    def test_collapses_excessive_blank_lines(self):
        text = "paragraph one\n\n\n\nparagraph two"
        result = clean_post_text(text)
        self.assertNotIn("\n\n\n", result)
        self.assertIn("paragraph one", result)
        self.assertIn("paragraph two", result)

    def test_preserves_double_newline(self):
        text = "line one\n\nline two"
        result = clean_post_text(text)
        self.assertIn("line one\n\nline two", result)

    # --- strip leading/trailing whitespace ---

    def test_strips_surrounding_whitespace(self):
        self.assertEqual(clean_post_text("  hello  "), "hello")
        self.assertEqual(clean_post_text("\n\nhello\n\n"), "hello")

    # --- combined / real-world ---

    def test_real_world_reddit_post_with_image(self):
        # &amp; → &, &lt; → <  (apostrophe is not &amp; in real Reddit HTML)
        text = (
            "So this happened today.\n\n"
            "![proof](https://i.redd.it/xyz.jpg)\n\n"
            "AT&amp;T is wild &lt;3\n\n"
            "More context here: https://reddit.com/r/foo/comments/bar\n\n"
            "What do you think?"
        )
        result = clean_post_text(text)
        self.assertNotIn("![", result)
        self.assertNotIn("redd.it", result)
        self.assertNotIn("reddit.com", result)
        self.assertIn("So this happened today.", result)
        self.assertIn("AT&T is wild <3", result)
        self.assertIn("What do you think?", result)

    def test_passthrough_plain_text(self):
        plain = "This is just a normal Reddit post with no special characters."
        self.assertEqual(clean_post_text(plain), plain)

    def test_empty_string(self):
        self.assertEqual(clean_post_text(""), "")

    def test_only_image_returns_empty(self):
        result = clean_post_text("![alt](https://i.redd.it/foo.jpg)")
        self.assertEqual(result, "")


if __name__ == "__main__":
    unittest.main()
