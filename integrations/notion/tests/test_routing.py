"""Guards for the OAuth callback's URL, which two other layers can silently steal.

The callback is a plain browser navigation to Django, but it lives under a path the Angular SPA
would otherwise claim. Both the reverse proxy and the app's service worker decide, per navigation,
whether a URL belongs to the backend or the SPA — and when the SPA wins, Notion redirects the user
to a blank page and the authorization code is discarded with no error anywhere.

The proxy side is deployment config and cannot be asserted here (it is documented in README.md and
docs/notion.md). The service-worker side ships in this repo, so it is checked.
"""

import json
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase
from django.urls import resolve, reverse

NGSW_CONFIG = Path(settings.BASE_DIR) / "frontend" / "ngsw-config.json"

# Prefixes Django serves to browsers. The SPA must not claim any of them.
BACKEND_BROWSER_PREFIXES = ("/integrations/", "/o/", "/admin/", "/api/", "/rest-auth/")


class CallbackUrlTests(SimpleTestCase):
    def test_callback_resolves_to_the_callback_view(self):
        self.assertEqual(reverse("notion:callback"), "/integrations/notion/callback/")
        self.assertEqual(resolve("/integrations/notion/callback/").func.__name__, "callback")

    def test_callback_lives_under_the_documented_prefix(self):
        # The registered redirect URI and the nginx location block are both written against this
        # prefix; moving it silently would break every existing Notion integration.
        self.assertTrue(reverse("notion:callback").startswith("/integrations/"))


class ServiceWorkerNavigationTests(SimpleTestCase):
    """The SPA's service worker must not serve index.html for backend navigations."""

    def setUp(self):
        if not NGSW_CONFIG.is_file():
            self.skipTest("frontend/ngsw-config.json not present")
        self.navigation_urls = json.loads(NGSW_CONFIG.read_text())["navigationUrls"]

    def test_every_backend_browser_prefix_is_excluded(self):
        for prefix in BACKEND_BROWSER_PREFIXES:
            with self.subTest(prefix=prefix):
                self.assertIn(
                    f"!{prefix}**",
                    self.navigation_urls,
                    f"{prefix} is not excluded from the service worker's navigationUrls, so a "
                    f"browser navigation there would be served the cached SPA shell instead of "
                    f"reaching Django.",
                )

    def test_the_notion_callback_is_covered(self):
        callback = reverse("notion:callback")
        matching = [
            rule for rule in self.navigation_urls if rule.startswith("!") and callback.startswith(rule[1:].rstrip("*"))
        ]
        self.assertTrue(matching, f"No navigationUrls exclusion covers {callback}")
