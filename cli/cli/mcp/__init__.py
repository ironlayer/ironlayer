"""IronLayer MCP (Model Context Protocol) server.

Exposes IronLayer's SQL intelligence as MCP tools that AI coding
assistants (Claude Code, Cursor, Windsurf) can discover and invoke.

Install with the ``mcp`` extra::

    pip install ironlayer[mcp]

Start the server::

    ironlayer mcp serve            # stdio transport (Claude Code / Cursor)
    ironlayer mcp serve --sse 3333 # SSE transport (remote access)
"""
