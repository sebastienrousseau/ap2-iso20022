<!-- SPDX-License-Identifier: Apache-2.0 OR MIT -->

# 0001. Serve stdio, streamable HTTP and SSE from one command line

- **Status:** Accepted
- **Date:** 2026-09-19
- **Deciders:** maintainer

## Context

Until now the server spoke stdio only: a client spawns the process,
nothing listens. That still fits a developer's laptop. It does not fit a
shared deployment, a gateway that fans one server out to many agents, or
an auditor such as scout that speaks HTTP. The MCP specification now has
two current revisions on the HTTP binding, `2025-11-25` (an `initialize`
handshake and a session header) and `2026-07-28` (stateless, per-request
`_meta`, `server/discover`), and clients on either must be served. The
older HTTP+SSE transport (`2024-11-05`) is still what some hosts expect.

## Options considered

1. Stay on stdio and leave remote use to a wrapper process.
2. Add HTTP behind a bespoke module per server, each with its own flags.
3. One shared module, copied verbatim into every server of the suite,
   that maps the same three flags onto the SDK's transports.

## Decision

Option 3. `ap2-iso20022-mcp` runs stdio; `ap2-iso20022-mcp --transport
streamable-http` listens on `--host`/`--port` at `/mcp` and speaks both
current protocol revisions on that one endpoint, streaming responses as
server-sent events and offering the server-to-client stream on `GET`;
`ap2-iso20022-mcp --transport sse` serves the older HTTP+SSE transport at
`/sse` and `/messages/`. The module binds loopback unless told otherwise
and adds no authentication of its own: a routable deployment sits behind
a gateway the operator trusts. Servers that already carry authenticated
HTTP keep it as additional flags on the same command line.

## Consequences

`main()` delegates to `_cli.serve`, which with `_transports.run` is the
same pair of files in every server, so the suite is started, documented
and tested the same way. Each server is verified over streamable HTTP
with scout in both protocol eras and over SSE with the SDK client before
release; the conformance workflow lists tools over every transport.
