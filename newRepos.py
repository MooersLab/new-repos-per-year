"""Count GitHub repositories created per year for a user or organization.

Fetches the public repository list through the GitHub REST API, follows
``Link`` headers to walk every page, and prints an Org-mode table showing
how many repositories were created in each year.

Usage::

    python newRepos.py                    # defaults to MooersLab
    python newRepos.py torvalds           # any GitHub login
    python newRepos.py numpy --token XXX  # authenticated, higher rate limit
"""

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from collections import Counter

DEFAULT_NAME = "MooersLab"
DEFAULT_PER_PAGE = 100
HTTP_NOT_FOUND = 404
HTTP_UNAUTHORIZED = 401
HTTP_FORBIDDEN = 403


def _next_link(link_header):
    """Return the URL for ``rel="next"`` in a GitHub ``Link`` header, or None."""
    if not link_header:
        return None
    for part in link_header.split(","):
        if 'rel="next"' in part:
            return part.split(";")[0].strip("<> ")
    return None


def _build_request(url, token=None):
    """Build a ``urllib`` request with GitHub-friendly headers."""
    headers = {
        "User-Agent": "Python-urllib-Script",
        "Accept": "application/vnd.github+json",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return urllib.request.Request(url, headers=headers)


def _fetch_repo_years(url, token=None):
    """Walk paginated repo lists from ``url`` and yield creation years."""
    while url:
        with urllib.request.urlopen(_build_request(url, token)) as response:
            repos = json.loads(response.read().decode())
            if not repos:
                return
            for repo in repos:
                created = repo.get("created_at")
                if created:
                    yield int(created.split("-")[0])
            url = _next_link(response.headers.get("Link"))


def get_account_repo_years(name=DEFAULT_NAME, token=None, per_page=DEFAULT_PER_PAGE):
    """Return a sorted list of ``(year, count)`` tuples for ``name``.

    Tries the ``/users/{name}/repos`` endpoint first because it works for both
    user accounts and organizations on GitHub. Falls back to the
    ``/orgs/{name}/repos`` endpoint if the user endpoint returns 404. Returns
    ``None`` if no matching account exists or another error occurs.
    """
    base = "https://api.github.com"
    candidates = [
        f"{base}/users/{name}/repos?per_page={per_page}",
        f"{base}/orgs/{name}/repos?per_page={per_page}",
    ]

    for url in candidates:
        try:
            years = list(_fetch_repo_years(url, token=token))
        except urllib.error.HTTPError as exc:
            if exc.code == HTTP_NOT_FOUND:
                continue
            if exc.code in (HTTP_UNAUTHORIZED, HTTP_FORBIDDEN):
                print(
                    f"Error fetching data: {exc} "
                    f"(check your token or rate-limit status)",
                    file=sys.stderr,
                )
            else:
                print(f"Error fetching data: {exc}", file=sys.stderr)
            return None
        except (urllib.error.URLError, json.JSONDecodeError) as exc:
            print(f"Error fetching data: {exc}", file=sys.stderr)
            return None
        return sorted(Counter(years).items())

    print(
        f"Error fetching data: no GitHub user or organization named {name!r}",
        file=sys.stderr,
    )
    return None


def _table_name(login):
    """Return a safe Org-mode table label derived from ``login``."""
    slug = re.sub(r"[^A-Za-z0-9]+", "-", login).strip("-").lower()
    return f"{slug or 'github'}-repos-per-year"


def print_org_table(year_counts, login=DEFAULT_NAME):
    """Print an Org-mode table of repositories created per year."""
    if not year_counts:
        print("No data retrieved.")
        return

    print(f"#+NAME: {_table_name(login)}")
    print(f"#+CAPTION: Public repositories created per year for {login} on GitHub.")
    print("#+ATTR_LATEX: :booktabs t")
    print("| Year | Repositories Created |")
    print("|------+----------------------|")

    total = 0
    for year, count in year_counts:
        print(f"| {year} | {count:>20} |")
        total += count

    print("|------+----------------------|")
    print(f"| Total| {total:>20} |")


def parse_args(argv=None):
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Count public GitHub repositories created per year for a user "
            "or organization, and print the result as an Org-mode table."
        ),
    )
    parser.add_argument(
        "name",
        nargs="?",
        default=DEFAULT_NAME,
        help=(
            "GitHub login of the user or organization to query "
            f"(default: {DEFAULT_NAME})."
        ),
    )
    parser.add_argument(
        "-t",
        "--token",
        default=os.environ.get("GITHUB_TOKEN"),
        help=(
            "GitHub personal access token. Falls back to the GITHUB_TOKEN "
            "environment variable. Authenticated requests get a higher rate "
            "limit."
        ),
    )
    parser.add_argument(
        "-p",
        "--per-page",
        type=int,
        default=DEFAULT_PER_PAGE,
        help=f"Page size for the GitHub API (1-100, default: {DEFAULT_PER_PAGE}).",
    )
    args = parser.parse_args(argv)

    if not 1 <= args.per_page <= DEFAULT_PER_PAGE:
        parser.error("--per-page must be between 1 and 100")
    return args


def main(argv=None):
    """Entry point for the command-line interface."""
    args = parse_args(argv)
    data = get_account_repo_years(args.name, token=args.token, per_page=args.per_page)
    print_org_table(data, login=args.name)
    return 0 if data else 1


if __name__ == "__main__":
    sys.exit(main())
