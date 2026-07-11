"""Bridge django-oauth-toolkit access tokens into the MCP SDK's resource-server auth.

The MCP server is an OAuth 2.1 *resource server*: every request carries a bearer access token
issued by this app's authorization server (django-oauth-toolkit). Because the authorization
server and resource server share a process and database, we introspect the opaque token
directly against the toolkit's ``AccessToken`` table instead of calling the introspection
endpoint over HTTP, and map it to the owning Django user.
"""

from mcp.server.auth.provider import AccessToken as MCPAccessToken
from mcp.server.auth.provider import TokenVerifier
from oauth2_provider.models import get_access_token_model

from ._dbcall import db_call


class DjangoOAuthTokenVerifier(TokenVerifier):
    """Verify bearer tokens by looking them up in django-oauth-toolkit, in-process."""

    async def verify_token(self, token: str) -> MCPAccessToken | None:
        return await db_call(self._verify, token)

    @staticmethod
    def _verify(token: str) -> MCPAccessToken | None:
        access_token_model = get_access_token_model()
        try:
            access_token = access_token_model.objects.select_related("user", "application").get(token=token)
        except access_token_model.DoesNotExist:
            return None
        # is_valid() with no scopes rejects expired tokens; a user-less token is unusable here.
        if not access_token.is_valid() or access_token.user_id is None:
            return None
        return MCPAccessToken(
            token=token,
            client_id=str(access_token.application.client_id) if access_token.application_id else "",
            scopes=access_token.scope.split() if access_token.scope else [],
            expires_at=int(access_token.expires.timestamp()) if access_token.expires else None,
            subject=str(access_token.user_id),
            claims={"username": access_token.user.get_username()},
        )
