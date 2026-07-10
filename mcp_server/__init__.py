"""OAuth-protected Model Context Protocol server for the organizer.

Exposes tasks, projects, tags, and task comments as MCP tools over the Streamable HTTP
transport, secured with OAuth 2.1 tokens issued by this app's django-oauth-toolkit
authorization server. See ``mcp_server/server.py`` for the FastMCP app and
``organizer/asgi.py`` for how it is mounted alongside Django.
"""
