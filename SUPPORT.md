<!-- SPDX-License-Identifier: Apache-2.0 OR MIT -->

# Getting support

Thanks for using ap2-iso20022. Here's the fastest way to get help, by need.

## Questions & how-to

- **Read first:** the [README](README.md), the three runnable
  [`examples/`](examples/), and [`docs/index.md`](docs/index.md) for the
  canonical mandate, every function, and what conversion does *not*
  check.
- **Still stuck?** Open a question issue at
  <https://github.com/sebastienrousseau/ap2-iso20022/issues/new>. Include
  your Python version, the `ap2-iso20022` version
  (`ap2-iso20022-mcp --version`), your MCP client (Claude Desktop / IDE /
  agent) if you run the server, the transport you run, and a minimal
  reproducer.

## Bugs

Open a bug report at
<https://github.com/sebastienrousseau/ap2-iso20022/issues/new> with a
minimal reproducer, the function or tool name, the arguments, and the
full error payload. A mandate that reproduces it (with accounts,
addresses and signatures redacted) helps enormously.

## Feature requests

Open a feature request at
<https://github.com/sebastienrousseau/ap2-iso20022/issues/new>. New
guardrails and new MCP tools over the bridge are welcome - see
[ARCHITECTURE.md](ARCHITECTURE.md) for the extension points and
[ROADMAP.md](ROADMAP.md) for what's planned. A request that would let
the package move money is out of scope by design.

## Security

**Do not** open public issues for vulnerabilities. Follow the private
disclosure process in [SECURITY.md](SECURITY.md).

## Contributing & maintaining

See [CONTRIBUTING.md](CONTRIBUTING.md) and [GOVERNANCE.md](GOVERNANCE.md).

## Supported versions

Fixes land on the latest release line. See [SECURITY.md](SECURITY.md) for
the supported-version policy. ap2-iso20022 requires Python 3.10+.
