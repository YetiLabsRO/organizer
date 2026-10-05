"""The OAuth callback must reach Django, not the SPA (see integrations/notion/tests/test_routing.py)."""

import json
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase
from django.urls import resolve, reverse

NGSW_CONFIG = Path(settings.BASE_DIR) / "frontend" / "ngsw-config.json"


class CallbackUrlTests(SimpleTestCase):
    def test_callback_resolves_to_the_callback_view(self):
        self.assertEqual(reverse("volunhub:callback"), "/integrations/volunhub/callback/")
        self.assertEqual(resolve("/integrations/volunhub/callback/").func.__module__, "integrations.volunhub.views")

    def test_default_redirect_uri_points_at_the_callback(self):
        # The redirect URI is declared at client registration; it must name this exact path.
        self.assertTrue(settings.VOLUNHUB_REDIRECT_URI.endswith(reverse("volunhub:callback")))

    def test_service_worker_does_not_claim_the_callback(self):
        if not NGSW_CONFIG.is_file():
            self.skipTest("frontend/ngsw-config.json not present")
        callback = reverse("volunhub:callback")
        rules = json.loads(NGSW_CONFIG.read_text())["navigationUrls"]
        self.assertTrue(
            any(rule.startswith("!") and callback.startswith(rule[1:].rstrip("*")) for rule in rules),
            f"No navigationUrls exclusion covers {callback}",
        )
