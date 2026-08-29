#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Sebastien Rousseau <sebastian.rousseau@gmail.com>
# SPDX-License-Identifier: Apache-2.0 OR MIT
"""Check this package's tree against what is actually published.

`ap2-iso20022` ships on its own rather than as one member of a versioned
suite, so there is no sibling to compare against. The failure worth
catching here is the single-package one:

* **A version bumped in the tree and never released.** Three
  repositories in this suite have done exactly that, each time stranding
  a `cryptography` advisory floor that reached nobody. Nothing fails when
  it happens -- the tree is consistent, the tests pass, the changelog is
  written -- and only the index disagrees.

* **A tree left behind what was published.** Rarer, and usually a sign
  that a release was cut from somewhere other than `main`.

Exits non-zero when the two disagree, so a schedule turns into a
notification rather than a report nobody opens. A tree that is ahead
between merging a bump and pushing its tag is the expected transient
state, and is reported as such rather than as a hard error.

Usage:
    python3 scripts/check_suite_consistency.py
    python3 scripts/check_suite_consistency.py --json
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import quote

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - exercised only on the 3.10 floor
    import tomli as tomllib

ROOT = Path(__file__).resolve().parent.parent

#: The distribution this repository publishes.
DISTRIBUTION = "ap2-iso20022"

TIMEOUT = 30


def published_version(distribution: str) -> str | None:
    """The newest version of ``distribution`` on PyPI, or None."""
    # The name is quoted and the scheme is checked before the request.
    # Both are belt-and-braces here -- DISTRIBUTION is a literal in this
    # file -- but urlopen honours file:// and custom schemes, so a URL
    # reaching it unchecked is worth refusing on principle rather than on
    # the argument that today's input happens to be safe.
    url = "https://pypi.org/pypi/" + quote(distribution, safe="") + "/json"
    if not url.startswith("https://pypi.org/"):  # pragma: no cover
        raise ValueError(f"refusing to fetch a non-PyPI URL: {url}")
    try:
        # B310 is satisfied by the scheme check above. Only bandit's
        # suppression is used: ruff's S rules are not enabled in most of
        # these repositories, and an unused noqa is itself a lint error
        # (RUF100). The reason sits here rather than inline because
        # bandit parses words following "nosec" as test ids.
        opened = urllib.request.urlopen(url, timeout=TIMEOUT)  # nosec B310
        with opened as response:
            return str(json.load(response)["info"]["version"])
    except (urllib.error.URLError, KeyError, ValueError, TimeoutError):
        return None


def tree_version() -> str:
    """The version this checkout declares."""
    with (ROOT / "pyproject.toml").open("rb") as handle:
        data = tomllib.load(handle)
    poetry = data.get("tool", {}).get("poetry", {})
    return str(poetry.get("version") or data["project"]["version"])


def _as_tuple(version: str) -> tuple[int, ...]:
    """Compare versions numerically, so 0.0.10 sorts above 0.0.9."""
    parts = []
    for piece in version.split("."):
        digits = "".join(c for c in piece if c.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


def check() -> tuple[list[str], dict[str, object]]:
    """Return (problems, report)."""
    problems: list[str] = []
    tree = tree_version()
    published = published_version(DISTRIBUTION)

    if published is None:
        problems.append(
            f"{DISTRIBUTION}: could not read PyPI. Either the package has "
            f"never been published, or the index was unreachable."
        )
    elif published != tree:
        if _as_tuple(tree) > _as_tuple(published):
            problems.append(
                f"{DISTRIBUTION}: tree is {tree} but PyPI has "
                f"{published}. The bump was never released -- expected "
                f"only between merging a bump and pushing its tag."
            )
        else:
            problems.append(
                f"{DISTRIBUTION}: tree is {tree} but PyPI has "
                f"{published}, which is newer. A release was cut from "
                f"somewhere other than this branch."
            )

    return problems, {
        "distribution": DISTRIBUTION,
        "tree": tree,
        "published": published,
        "problems": problems,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit JSON")
    args = parser.parse_args()

    problems, report = check()
    if args.json:
        json.dump(report, sys.stdout, indent=1)
        print()
    else:
        print(f"distribution: {report['distribution']}")
        print(f"  tree:       {report['tree']}")
        print(f"  published:  {report['published']}")
        if problems:
            print("\nproblems:")
            for problem in problems:
                print(f"  - {problem}")
        else:
            print("\nthe tree agrees with what is published")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
