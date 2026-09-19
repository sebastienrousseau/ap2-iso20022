<!-- SPDX-License-Identifier: Apache-2.0 OR MIT -->

# Releasing ap2-iso20022

This document defines **what merits a release** and **how to cut one**,
so versions are deliberate rather than ad-hoc.

## Versioning scheme

Versions increment by `0.0.1`: `0.1.0` follows `0.0.999`, not `0.0.9`.
The version is stated in `pyproject.toml`, `ap2_iso20022/__init__.py`,
`CHANGELOG.md`, `glama.json` and `server.json`, and
`scripts/verify_versions.py` fails when any of them disagree. The
scheduled `Release Consistency` workflow
(`scripts/check_suite_consistency.py`) fails when the tree and PyPI
disagree, because a version bumped and never published has stranded a
security floor in this suite before.

## What merits a release

Cut a new version when there is user-visible change to ship - bug fixes,
security or dependency patches, new tools / resources / prompts, or
documentation that ships in the package.

Do **not** cut a release that contains only a version-number bump with
no functional, security, or documentation change.

## Pre-flight checklist

A release is ready only when **all** of the following hold on `main`:

1. CI is green: ruff, black, mypy --strict, pytest with the 100% branch
   coverage gate, every example, and the quick benchmark.
2. Every Dependabot / CodeQL / Scorecard alert is resolved or has a
   documented, expiring suppression.
3. `CHANGELOG.md` has a dated section for the new version describing the
   change set.
4. The version is identical in `pyproject.toml`,
   `ap2_iso20022/__init__.py`, `CHANGELOG.md`, `glama.json` and
   `server.json` (enforced by `scripts/verify_versions.py`, which the
   `Version sources agree` workflow runs). The Glama directory and the
   MCP registry read those two manifests; a release that forgets them
   shows an old version to every agent that browses for the server.

## Cutting the release

1. Bump the version in `pyproject.toml`, `ap2_iso20022/__init__.py`,
   `glama.json` and `server.json`, and add the `CHANGELOG.md` section,
   in a single PR.
2. Merge the PR to `main` once CI is green.
3. Push a signed tag:

   ```bash
   git tag -s vX.Y.Z -m "ap2-iso20022 vX.Y.Z" <merge-commit>
   git push origin vX.Y.Z
   ```

4. The tag triggers two workflows:
   - `release.yml` builds with Poetry from hash-pinned tooling, runs
     `twine check`, attaches a SLSA build provenance attestation,
     publishes to PyPI via OIDC trusted publishing, signs every
     distribution keylessly with cosign, publishes the GitHub release
     with the distributions and signatures, and attaches CycloneDX and
     SPDX SBOMs plus a licence manifest.
   - `publish-mcp.yml` stamps `server.json` from the tag, waits for
     PyPI to surface the version, and publishes to the MCP registry.

## After releasing

- Confirm the version is live on
  [PyPI](https://pypi.org/project/ap2-iso20022/) and the GitHub release
  is published (not draft).
- Verify a clean install: `pip install ap2-iso20022==X.Y.Z` and
  `ap2-iso20022-mcp --version`.
- Confirm the MCP registry and Glama show the new version.

## CI integrations

- **PyPI trusted publisher** (`release.yml`): configured at
  <https://pypi.org/manage/account/publishing/>. The publisher claim
  set is `repo:sebastienrousseau/ap2-iso20022:environment:pypi` with
  `workflow_ref` pointing at `.github/workflows/release.yml`.
- **MCP registry** (`publish-mcp.yml`): authenticates with the
  workflow's GitHub OIDC token; no secret to configure.
