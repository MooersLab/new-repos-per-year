"""Shared pytest fixtures for the newRepos test suite.

The fixtures here make ``newRepos`` importable as a regular module even though
the script lives next to the tests rather than inside a package, and they
provide a reusable fake ``urlopen`` so no test ever touches the real GitHub
API.
"""

from __future__ import annotations

import io
import json
import pathlib
import sys
import urllib.error
from collections.abc import Iterable
from typing import Any

import pytest

# Make the script under test importable as ``newRepos``.
PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class FakeResponse:
    """Minimal stand-in for ``http.client.HTTPResponse``.

    Supports the context-manager protocol, ``read()``, and ``.headers.get``,
    which are the only members ``newRepos`` touches.
    """

    def __init__(self, payload: Any, link_header: str | None = None):
        self._body = json.dumps(payload).encode("utf-8")
        self.headers = {"Link": link_header} if link_header else {}

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


class FakeUrlopen:
    """Stateful fake ``urlopen`` that returns scripted responses per URL.

    Pass a mapping of URL -> response (either a ``FakeResponse`` or an
    exception to raise). Each call records the request it received so tests
    can assert on headers and ordering.
    """

    def __init__(self, scripted: dict[str, Any]):
        self._scripted = dict(scripted)
        self.calls: list[Any] = []

    def __call__(self, request, *args, **kwargs):  # noqa: D401, ARG002
        self.calls.append(request)
        url = request.full_url if hasattr(request, "full_url") else request
        if url not in self._scripted:
            raise AssertionError(f"unexpected URL requested: {url!r}")
        result = self._scripted[url]
        if isinstance(result, Exception):
            raise result
        return result


def _http_error(code: int, msg: str = "error") -> urllib.error.HTTPError:
    """Build an ``HTTPError`` instance for use as a scripted response."""
    return urllib.error.HTTPError(
        url="https://api.github.com/test",
        code=code,
        msg=msg,
        hdrs={},  # type: ignore[arg-type]
        fp=io.BytesIO(b""),
    )


@pytest.fixture
def fake_response():
    """Factory for ``FakeResponse`` instances."""
    return FakeResponse


@pytest.fixture
def fake_urlopen():
    """Factory for ``FakeUrlopen`` instances."""
    return FakeUrlopen


@pytest.fixture
def http_error():
    """Factory that builds ``urllib.error.HTTPError`` instances."""
    return _http_error


@pytest.fixture
def patch_urlopen(monkeypatch):
    """Patch ``urllib.request.urlopen`` inside ``newRepos`` with a callable.

    Returns a function that takes a callable (typically a ``FakeUrlopen``)
    and installs it for the duration of the test.
    """
    import newRepos

    def _install(callable_):
        monkeypatch.setattr(newRepos.urllib.request, "urlopen", callable_)
        return callable_

    return _install


@pytest.fixture
def make_repo():
    """Factory that builds a minimal repo dict with a ``created_at`` field."""

    def _make(year: int, month: int = 5, day: int = 10, name: str = "repo") -> dict:
        return {
            "name": name,
            "created_at": f"{year:04d}-{month:02d}-{day:02d}T12:00:00Z",
        }

    return _make


@pytest.fixture
def repos_payload(make_repo):
    """Factory that builds a list of repo dicts from a list of years."""

    def _make(years: Iterable[int]) -> list[dict]:
        return [make_repo(y, name=f"repo-{i}") for i, y in enumerate(years)]

    return _make


@pytest.fixture(autouse=True)
def clear_github_token(monkeypatch):
    """Make sure no test inherits a real ``GITHUB_TOKEN`` from the env."""
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
