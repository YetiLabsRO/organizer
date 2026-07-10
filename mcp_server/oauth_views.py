"""OAuth 2.0 discovery + dynamic client registration for MCP clients.

django-oauth-toolkit ships authorize/token/introspect/revoke but not RFC 8414 authorization-server
metadata or RFC 7591 dynamic client registration — both of which MCP clients (e.g. Claude) rely on
to self-configure. These two thin views fill that gap. The advertised issuer/base URL comes from
``settings.MCP_BASE_URL`` so it matches the issuer the MCP resource server announces.
"""

import json
import time

from django.conf import settings
from django.http import JsonResponse
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from oauth2_provider.generators import generate_client_id, generate_client_secret
from oauth2_provider.models import get_application_model

Application = get_application_model()


def _abs(viewname: str) -> str:
    return settings.MCP_BASE_URL + reverse(viewname)


def authorization_server_metadata(request):
    """RFC 8414 metadata served at /.well-known/oauth-authorization-server."""
    return JsonResponse(
        {
            "issuer": settings.MCP_BASE_URL,
            "authorization_endpoint": _abs("oauth2_provider:authorize"),
            "token_endpoint": _abs("oauth2_provider:token"),
            "introspection_endpoint": _abs("oauth2_provider:introspect"),
            "revocation_endpoint": _abs("oauth2_provider:revoke-token"),
            "registration_endpoint": _abs("oauth_register"),
            "scopes_supported": list(settings.OAUTH2_PROVIDER["SCOPES"].keys()),
            "response_types_supported": ["code"],
            "grant_types_supported": ["authorization_code", "refresh_token"],
            "token_endpoint_auth_methods_supported": ["client_secret_post", "client_secret_basic", "none"],
            "code_challenge_methods_supported": ["S256"],
            "service_documentation": "https://modelcontextprotocol.io",
        }
    )


def _reg_error(code: str, description: str, status: int = 400) -> JsonResponse:
    return JsonResponse({"error": code, "error_description": description}, status=status)


@method_decorator(csrf_exempt, name="dispatch")
class RegisterClientView(View):
    """Minimal RFC 7591 dynamic client registration.

    Accepts a client metadata document and creates a django-oauth-toolkit authorization-code
    application (public + PKCE when ``token_endpoint_auth_method`` is ``none``, otherwise
    confidential with a generated secret), returning the issued ``client_id``.
    """

    def post(self, request, *args, **kwargs):
        try:
            meta = json.loads(request.body.decode() or "{}")
        except (ValueError, UnicodeDecodeError):
            return _reg_error("invalid_client_metadata", "Request body must be JSON")

        redirect_uris = meta.get("redirect_uris")
        if not isinstance(redirect_uris, list) or not redirect_uris:
            return _reg_error("invalid_redirect_uri", "redirect_uris must be a non-empty list")

        auth_method = meta.get("token_endpoint_auth_method", "client_secret_post")
        is_public = auth_method == "none"

        application = Application(
            name=(meta.get("client_name") or "MCP client")[:255],
            client_id=generate_client_id(),
            client_type=Application.CLIENT_PUBLIC if is_public else Application.CLIENT_CONFIDENTIAL,
            authorization_grant_type=Application.GRANT_AUTHORIZATION_CODE,
            redirect_uris=" ".join(redirect_uris),
        )
        client_secret = None
        if not is_public:
            # Capture the plaintext before save() hashes it, so we can return it once.
            client_secret = generate_client_secret()
            application.client_secret = client_secret
        application.save()

        body = {
            "client_id": application.client_id,
            "client_id_issued_at": int(time.time()),
            "client_name": application.name,
            "redirect_uris": redirect_uris,
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "token_endpoint_auth_method": auth_method,
            "scope": meta.get("scope", "read write"),
        }
        if client_secret is not None:
            body["client_secret"] = client_secret
            body["client_secret_expires_at"] = 0  # never expires
        return JsonResponse(body, status=201)

    def http_method_not_allowed(self, request, *args, **kwargs):
        return _reg_error("invalid_request", "Only POST is supported", status=405)
