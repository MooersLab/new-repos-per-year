"""Comprehensive tests for newRepos.py.

The test suite is split into focused classes per function under test. Every
test patches ``urllib.request.urlopen`` so the suite never hits the real
GitHub API. Integration tests live at the bottom and are marked with
``@pytest.mark.integration``.
"""

from __future__ import annotations

import json
import urllib.error

import pytest

import newRepos


# ---------------------------------------------------------------------------
# _next_link
# ---------------------------------------------------------------------------


class TestNextLink:
    """Unit tests for newRepos._next_link."""

    def test_returns_none_for_empty_header(self):
        assert newRepos._next_link(None) is None
        assert newRepos._next_link("") is None

    def test_extracts_next_url_from_typical_header(self):
        header = (
            '<https://api.github.com/x?page=2>; rel="next", '
            '<https://api.github.com/x?page=5>; rel="last"'
        )
        assert newRepos._next_link(header) == "https://api.github.com/x?page=2"

    def test_returns_none_when_no_next_rel(self):
        header = '<https://api.github.com/x?page=5>; rel="last"'
        assert newRepos._next_link(header) is None

    def test_returns_none_when_only_prev_present(self):
        header = '<https://api.github.com/x?page=1>; rel="prev"'
        assert newRepos._next_link(header) is None

    def test_finds_next_among_many_rels(self):
        header = (
            '<https://api.github.com/x?page=1>; rel="first", '
            '<https://api.github.com/x?page=2>; rel="prev", '
            '<https://api.github.com/x?page=4>; rel="next", '
            '<https://api.github.com/x?page=99>; rel="last"'
        )
        assert newRepos._next_link(header) == "https://api.github.com/x?page=4"

    def test_strips_angle_brackets_and_whitespace(self):
        header = '   <https://example/x>;  rel="next"  '
        assert newRepos._next_link(header) == "https://example/x"


# ---------------------------------------------------------------------------
# _build_request
# ---------------------------------------------------------------------------


class TestBuildRequest:
    """Unit tests for newRepos._build_request."""

    def test_returns_request_with_url(self):
        req = newRepos._build_request("https://api.github.com/users/x/repos")
        assert req.full_url == "https://api.github.com/users/x/repos"

    def test_sets_user_agent_and_accept(self):
        req = newRepos._build_request("https://example/x")
        # urllib lowercases header keys when stored, hence get_header().
        assert req.get_header("User-agent") == "Python-urllib-Script"
        assert req.get_header("Accept") == "application/vnd.github+json"

    def test_omits_authorization_when_no_token(self):
        req = newRepos._build_request("https://example/x", token=None)
        assert req.get_header("Authorization") is None

    def test_sets_bearer_authorization_when_token_provided(self):
        req = newRepos._build_request("https://example/x", token="ghp_secret")
        assert req.get_header("Authorization") == "Bearer ghp_secret"

    def test_empty_token_does_not_set_authorization(self):
        req = newRepos._build_request("https://example/x", token="")
        assert req.get_header("Authorization") is None


# ---------------------------------------------------------------------------
# _fetch_repo_years
# ---------------------------------------------------------------------------


class TestFetchRepoYears:
    """Unit tests for newRepos._fetch_repo_years (urlopen patched)."""

    def test_yields_years_from_single_page(
        self, patch_urlopen, fake_urlopen, fake_response, repos_payload
    ):
        url = "https://api.github.com/users/x/repos?per_page=100"
        patch_urlopen(fake_urlopen({url: fake_response(repos_payload([2020, 2021, 2020]))}))

        assert list(newRepos._fetch_repo_years(url)) == [2020, 2021, 2020]

    def test_follows_link_header_across_multiple_pages(
        self, patch_urlopen, fake_urlopen, fake_response, repos_payload
    ):
        page1 = "https://api.github.com/users/x/repos?per_page=100"
        page2 = "https://api.github.com/users/x/repos?per_page=100&page=2"
        page3 = "https://api.github.com/users/x/repos?per_page=100&page=3"
        scripted = {
            page1: fake_response(
                repos_payload([2018, 2019]),
                link_header=f'<{page2}>; rel="next", <{page3}>; rel="last"',
            ),
            page2: fake_response(
                repos_payload([2020]),
                link_header=f'<{page3}>; rel="next"',
            ),
            page3: fake_response(repos_payload([2021, 2021])),
        }
        patch_urlopen(fake_urlopen(scripted))

        assert list(newRepos._fetch_repo_years(page1)) == [2018, 2019, 2020, 2021, 2021]

    def test_stops_on_empty_page(
        self, patch_urlopen, fake_urlopen, fake_response
    ):
        url = "https://api.github.com/users/x/repos?per_page=100"
        patch_urlopen(fake_urlopen({url: fake_response([])}))

        assert list(newRepos._fetch_repo_years(url)) == []

    def test_skips_repos_with_no_created_at(
        self, patch_urlopen, fake_urlopen, fake_response
    ):
        url = "https://api.github.com/users/x/repos?per_page=100"
        payload = [
            {"name": "with-date", "created_at": "2022-01-15T00:00:00Z"},
            {"name": "no-date"},  # missing key
            {"name": "null-date", "created_at": None},  # explicit null
        ]
        patch_urlopen(fake_urlopen({url: fake_response(payload)}))

        assert list(newRepos._fetch_repo_years(url)) == [2022]

    def test_sends_authorization_header_when_token_supplied(
        self, patch_urlopen, fake_urlopen, fake_response, repos_payload
    ):
        url = "https://api.github.com/users/x/repos?per_page=100"
        fu = patch_urlopen(fake_urlopen({url: fake_response(repos_payload([2024]))}))

        list(newRepos._fetch_repo_years(url, token="ghp_test"))

        assert fu.calls[0].get_header("Authorization") == "Bearer ghp_test"


# ---------------------------------------------------------------------------
# get_account_repo_years
# ---------------------------------------------------------------------------


class TestGetAccountRepoYears:
    """Unit tests for newRepos.get_account_repo_years (urlopen patched)."""

    @staticmethod
    def _url(kind: str, name: str = "octocat", per_page: int = 100) -> str:
        return f"https://api.github.com/{kind}/{name}/repos?per_page={per_page}"

    def test_returns_sorted_year_counts_from_users_endpoint(
        self, patch_urlopen, fake_urlopen, fake_response, repos_payload
    ):
        url = self._url("users")
        patch_urlopen(
            fake_urlopen({url: fake_response(repos_payload([2021, 2020, 2021, 2022]))})
        )

        result = newRepos.get_account_repo_years("octocat")

        assert result == [(2020, 1), (2021, 2), (2022, 1)]

    def test_falls_back_to_orgs_when_users_404s(
        self, patch_urlopen, fake_urlopen, fake_response, http_error, repos_payload
    ):
        users_url = self._url("users")
        orgs_url = self._url("orgs")
        patch_urlopen(
            fake_urlopen(
                {
                    users_url: http_error(404, "Not Found"),
                    orgs_url: fake_response(repos_payload([2019, 2019, 2020])),
                }
            )
        )

        assert newRepos.get_account_repo_years("octocat") == [(2019, 2), (2020, 1)]

    def test_returns_none_when_both_endpoints_404(
        self, patch_urlopen, fake_urlopen, http_error, capsys
    ):
        users_url = self._url("users", "ghost")
        orgs_url = self._url("orgs", "ghost")
        patch_urlopen(
            fake_urlopen(
                {
                    users_url: http_error(404, "Not Found"),
                    orgs_url: http_error(404, "Not Found"),
                }
            )
        )

        assert newRepos.get_account_repo_years("ghost") is None
        err = capsys.readouterr().err
        assert "no GitHub user or organization named 'ghost'" in err

    @pytest.mark.parametrize("status", [401, 403])
    def test_auth_errors_return_none_and_explain(
        self, patch_urlopen, fake_urlopen, http_error, capsys, status
    ):
        url = self._url("users")
        patch_urlopen(fake_urlopen({url: http_error(status, "Auth fail")}))

        assert newRepos.get_account_repo_years("octocat") is None
        assert "token" in capsys.readouterr().err.lower()

    def test_other_http_errors_return_none_without_token_hint(
        self, patch_urlopen, fake_urlopen, http_error, capsys
    ):
        url = self._url("users")
        patch_urlopen(fake_urlopen({url: http_error(500, "Server crash")}))

        assert newRepos.get_account_repo_years("octocat") is None
        err = capsys.readouterr().err
        assert "Error fetching data" in err
        assert "token" not in err.lower()

    def test_url_error_returns_none(
        self, patch_urlopen, fake_urlopen, capsys
    ):
        url = self._url("users")
        patch_urlopen(fake_urlopen({url: urllib.error.URLError("dns down")}))

        assert newRepos.get_account_repo_years("octocat") is None
        assert "Error fetching data" in capsys.readouterr().err

    def test_json_decode_error_returns_none(
        self, patch_urlopen, fake_urlopen, capsys
    ):
        url = self._url("users")
        bad = json.JSONDecodeError("Expecting value", "x", 0)
        patch_urlopen(fake_urlopen({url: bad}))

        assert newRepos.get_account_repo_years("octocat") is None
        assert "Error fetching data" in capsys.readouterr().err

    def test_empty_repo_list_yields_empty_year_counts(
        self, patch_urlopen, fake_urlopen, fake_response
    ):
        url = self._url("users")
        patch_urlopen(fake_urlopen({url: fake_response([])}))

        assert newRepos.get_account_repo_years("octocat") == []

    def test_per_page_value_propagates_to_url(
        self, patch_urlopen, fake_urlopen, fake_response, repos_payload
    ):
        url = self._url("users", per_page=25)
        patch_urlopen(fake_urlopen({url: fake_response(repos_payload([2024]))}))

        result = newRepos.get_account_repo_years("octocat", per_page=25)

        assert result == [(2024, 1)]

    def test_token_forwarded_to_request(
        self, patch_urlopen, fake_urlopen, fake_response, repos_payload
    ):
        url = self._url("users")
        fu = patch_urlopen(
            fake_urlopen({url: fake_response(repos_payload([2024]))})
        )

        newRepos.get_account_repo_years("octocat", token="ghp_token")

        assert fu.calls[0].get_header("Authorization") == "Bearer ghp_token"


# ---------------------------------------------------------------------------
# _table_name
# ---------------------------------------------------------------------------


class TestTableName:
    @pytest.mark.parametrize(
        "login, expected",
        [
            ("MooersLab", "mooerslab-repos-per-year"),
            ("numpy", "numpy-repos-per-year"),
            ("Some Org!", "some-org-repos-per-year"),
            ("foo_bar.baz", "foo-bar-baz-repos-per-year"),
            ("---weird---", "weird-repos-per-year"),
            ("", "github-repos-per-year"),
            ("!!!", "github-repos-per-year"),
            ("123", "123-repos-per-year"),
        ],
    )
    def test_slugifies_login_into_table_name(self, login, expected):
        assert newRepos._table_name(login) == expected


# ---------------------------------------------------------------------------
# print_org_table
# ---------------------------------------------------------------------------


class TestPrintOrgTable:
    def test_prints_no_data_message_for_none(self, capsys):
        newRepos.print_org_table(None)

        out = capsys.readouterr().out
        assert "No data retrieved." in out
        assert "|" not in out

    def test_prints_no_data_message_for_empty_list(self, capsys):
        newRepos.print_org_table([])

        out = capsys.readouterr().out
        assert "No data retrieved." in out

    def test_prints_expected_org_table_structure(self, capsys):
        newRepos.print_org_table([(2020, 1), (2021, 2), (2022, 3)], login="numpy")

        out = capsys.readouterr().out
        assert "#+NAME: numpy-repos-per-year" in out
        assert "#+CAPTION:" in out
        assert "#+ATTR_LATEX: :booktabs t" in out
        assert "| Year | Repositories Created |" in out
        # Rows contain the year and right-aligned counts.
        assert "| 2020 |" in out
        assert "| 2021 |" in out
        assert "| 2022 |" in out

    def test_computes_total_correctly(self, capsys):
        newRepos.print_org_table([(2020, 5), (2021, 7), (2022, 3)])

        out = capsys.readouterr().out
        # Total row is the last data line.
        total_line = [line for line in out.splitlines() if line.startswith("| Total")]
        assert total_line, "Total row not printed"
        assert "15" in total_line[0]

    def test_default_login_used_when_not_supplied(self, capsys):
        newRepos.print_org_table([(2020, 1)])

        out = capsys.readouterr().out
        assert "#+NAME: mooerslab-repos-per-year" in out


# ---------------------------------------------------------------------------
# parse_args
# ---------------------------------------------------------------------------


class TestParseArgs:
    def test_defaults_used_when_no_args_given(self):
        args = newRepos.parse_args([])
        assert args.name == "MooersLab"
        assert args.per_page == 100
        assert args.token is None

    def test_positional_name_is_picked_up(self):
        args = newRepos.parse_args(["torvalds"])
        assert args.name == "torvalds"

    def test_token_via_long_flag(self):
        args = newRepos.parse_args(["--token", "ghp_x"])
        assert args.token == "ghp_x"

    def test_token_via_short_flag(self):
        args = newRepos.parse_args(["-t", "ghp_y"])
        assert args.token == "ghp_y"

    def test_per_page_validated(self):
        with pytest.raises(SystemExit):
            newRepos.parse_args(["--per-page", "0"])

    def test_per_page_upper_bound_validated(self):
        with pytest.raises(SystemExit):
            newRepos.parse_args(["--per-page", "101"])

    def test_per_page_accepts_minimum(self):
        args = newRepos.parse_args(["--per-page", "1"])
        assert args.per_page == 1

    def test_per_page_accepts_maximum(self):
        args = newRepos.parse_args(["--per-page", "100"])
        assert args.per_page == 100

    def test_help_exits_cleanly(self, capsys):
        with pytest.raises(SystemExit) as exc:
            newRepos.parse_args(["--help"])
        assert exc.value.code == 0
        assert "usage:" in capsys.readouterr().out.lower()

    def test_github_token_env_var_is_default(self, monkeypatch):
        monkeypatch.setenv("GITHUB_TOKEN", "from-env")
        args = newRepos.parse_args([])
        assert args.token == "from-env"

    def test_explicit_token_overrides_env(self, monkeypatch):
        monkeypatch.setenv("GITHUB_TOKEN", "from-env")
        args = newRepos.parse_args(["--token", "explicit"])
        assert args.token == "explicit"


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


class TestMain:
    def test_returns_zero_on_success(
        self, patch_urlopen, fake_urlopen, fake_response, repos_payload, capsys
    ):
        url = "https://api.github.com/users/MooersLab/repos?per_page=100"
        patch_urlopen(fake_urlopen({url: fake_response(repos_payload([2020, 2021]))}))

        exit_code = newRepos.main([])

        assert exit_code == 0
        assert "| Year | Repositories Created |" in capsys.readouterr().out

    def test_returns_one_on_failure(
        self, patch_urlopen, fake_urlopen, http_error, capsys
    ):
        users_url = "https://api.github.com/users/ghost/repos?per_page=100"
        orgs_url = "https://api.github.com/orgs/ghost/repos?per_page=100"
        patch_urlopen(
            fake_urlopen(
                {
                    users_url: http_error(404, "Not Found"),
                    orgs_url: http_error(404, "Not Found"),
                }
            )
        )

        exit_code = newRepos.main(["ghost"])

        assert exit_code == 1
        assert "No data retrieved." in capsys.readouterr().out

    def test_propagates_cli_name_through_to_table(
        self, patch_urlopen, fake_urlopen, fake_response, repos_payload, capsys
    ):
        url = "https://api.github.com/users/numpy/repos?per_page=50"
        patch_urlopen(fake_urlopen({url: fake_response(repos_payload([2024]))}))

        newRepos.main(["numpy", "--per-page", "50"])

        out = capsys.readouterr().out
        assert "#+NAME: numpy-repos-per-year" in out


# ---------------------------------------------------------------------------
# Integration tests (still mocked, but exercise full pipeline)
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestEndToEndPipeline:
    """End-to-end checks that drive ``main`` against a multi-page fake API."""

    def test_paginated_user_endpoint_renders_full_table(
        self, patch_urlopen, fake_urlopen, fake_response, repos_payload, capsys
    ):
        page1 = "https://api.github.com/users/MooersLab/repos?per_page=100"
        page2 = "https://api.github.com/users/MooersLab/repos?per_page=100&page=2"
        scripted = {
            page1: fake_response(
                repos_payload([2018, 2018, 2019, 2020]),
                link_header=f'<{page2}>; rel="next"',
            ),
            page2: fake_response(repos_payload([2020, 2020, 2021])),
        }
        patch_urlopen(fake_urlopen(scripted))

        exit_code = newRepos.main([])

        assert exit_code == 0
        out = capsys.readouterr().out
        assert "#+NAME: mooerslab-repos-per-year" in out
        # Verify every year appears in the rendered table.
        for year in (2018, 2019, 2020, 2021):
            assert f"| {year} |" in out
        # Total row sums to seven repos across all years.
        total_line = next(line for line in out.splitlines() if line.startswith("| Total"))
        assert "7" in total_line

    def test_orgs_fallback_then_pagination(
        self,
        patch_urlopen,
        fake_urlopen,
        fake_response,
        http_error,
        repos_payload,
        capsys,
    ):
        users_url = "https://api.github.com/users/SomeOrg/repos?per_page=100"
        orgs_page1 = "https://api.github.com/orgs/SomeOrg/repos?per_page=100"
        orgs_page2 = "https://api.github.com/orgs/SomeOrg/repos?per_page=100&page=2"
        scripted = {
            users_url: http_error(404, "Not Found"),
            orgs_page1: fake_response(
                repos_payload([2015, 2016]),
                link_header=f'<{orgs_page2}>; rel="next"',
            ),
            orgs_page2: fake_response(repos_payload([2017])),
        }
        patch_urlopen(fake_urlopen(scripted))

        exit_code = newRepos.main(["SomeOrg"])

        assert exit_code == 0
        out = capsys.readouterr().out
        assert "#+NAME: someorg-repos-per-year" in out
        # Years from both pages of the orgs endpoint are present.
        for year in (2015, 2016, 2017):
            assert f"| {year} |" in out

    def test_token_from_environment_reaches_the_request(
        self,
        patch_urlopen,
        fake_urlopen,
        fake_response,
        repos_payload,
        monkeypatch,
    ):
        monkeypatch.setenv("GITHUB_TOKEN", "env-token")
        url = "https://api.github.com/users/MooersLab/repos?per_page=100"
        fu = patch_urlopen(
            fake_urlopen({url: fake_response(repos_payload([2022]))})
        )

        newRepos.main([])

        # Each request carried the Bearer token from the environment.
        assert all(
            req.get_header("Authorization") == "Bearer env-token" for req in fu.calls
        )
