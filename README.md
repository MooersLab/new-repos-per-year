# newRepos

Count public GitHub repositories created per year for a user or organization, and print the result as an Org-mode table ready to drop into a LaTeX document.

The script walks the GitHub REST API, follows `Link` headers across every page of results, groups repositories by creation year, and renders an Org-mode table with `booktabs`-style attributes that exports cleanly through `org-latex-export-to-pdf`.

## Features

- Works for both user accounts and organization accounts. The script tries `/users/{name}/repos` first because that endpoint serves both kinds, and falls back to `/orgs/{name}/repos` only when the first call returns 404.
- Streams paginated results. The full repository history is collected even for accounts with hundreds of repositories.
- Optional GitHub token support, picked up from a `--token` flag or the `GITHUB_TOKEN` environment variable. Authenticated calls get the higher GitHub API rate limit.
- Pure standard library. No third-party runtime dependencies. The only extra packages are testing tools.
- Org-mode output. The table includes a `#+NAME`, `#+CAPTION`, and `#+ATTR_LATEX: :booktabs t` line for clean LaTeX export.
- Clean exit codes. Returns 0 on success and 1 on failure so the script composes well with shell pipelines.

## Requirements

The runtime needs only Python 3.8 or newer. The test suite adds `pytest`, `pytest-cov`, `coverage`, and `ruff`. No build steps or compiled extensions are involved.

## Installation

### Option 1. Clone and use directly

```bash
git clone https://github.com/MooersLab/newRepos.git
cd newRepos
python3 newRepos.py --help
```

### Option 2. Install as a package and use the `newrepos` entry point

```bash
git clone https://github.com/MooersLab/newRepos.git
cd newRepos
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
newrepos --help
```

The editable install registers a `newrepos` console script that wraps the same `main()` function as the standalone module.

### Option 3. Install the test extras as well

```bash
pip install -e ".[test]"
```

This adds `pytest`, `pytest-cov`, `coverage`, and `ruff`, which the `Makefile` uses for `make test`, `make coverage`, and `make lint`.

## Quick start

```bash
# Default account: MooersLab.
python3 newRepos.py

# Any GitHub login (user or organization).
python3 newRepos.py torvalds

# Authenticated call. Use this if you hit rate-limit errors.
GITHUB_TOKEN=ghp_xxx python3 newRepos.py numpy

# Equivalent with an explicit flag.
python3 newRepos.py numpy --token ghp_xxx

# Smaller page size, useful when debugging pagination.
python3 newRepos.py MooersLab --per-page 25
```

### Sample output

```
#+NAME: mooerslab-repos-per-year
#+CAPTION: Public repositories created per year for MooersLab on GitHub.
#+ATTR_LATEX: :booktabs t
| Year | Repositories Created |
|------+----------------------|
| 2018 |                    3 |
| 2019 |                    7 |
| 2020 |                   12 |
| 2021 |                   18 |
| 2022 |                   22 |
|------+----------------------|
| Total|                   62 |
```

Paste this block into an Org file and `org-export-dispatch C-c C-e l p` to compile the table into a `booktabs`-formatted LaTeX table.

## Command-line reference

```
python3 newRepos.py [-h] [-t TOKEN] [-p PER_PAGE] [name]
```

| Argument | Default | Description |
|----------|---------|-------------|
| `name` | `MooersLab` | GitHub login of the user or organization to query. |
| `-t`, `--token TOKEN` | `$GITHUB_TOKEN` | Personal access token used for authenticated calls. |
| `-p`, `--per-page N` | `100` | Page size for the GitHub API. Must be between 1 and 100. |
| `-h`, `--help` | | Show the help message and exit. |

The script exits with status code `0` when it prints a populated table, and with status code `1` when no data can be retrieved (404 on both endpoints, network failure, authentication failure, or JSON decoding failure).

## How it works

The pipeline is small enough to summarize in one paragraph. The script builds the first URL from the supplied login, sends a single request with a `User-Agent` and an `Accept: application/vnd.github+json` header, and parses the JSON response. For each repository in the page, it extracts the four-digit year from the `created_at` ISO 8601 timestamp. The response's `Link` header is then parsed; if a `rel="next"` URL is present, the loop walks to the next page. When a page has no `next` link or returns an empty list, the loop ends. Years are aggregated with `collections.Counter` and printed as an Org-mode table.

If the `/users/{name}/repos` endpoint returns HTTP 404, the script retries against `/orgs/{name}/repos` because GitHub treats user accounts and organization accounts as separate entities at that path. A 401 or 403 surfaces a hint about checking the token and rate-limit status. Other HTTP errors and network errors produce a clear stderr message without a stack trace.

## Org-mode and LaTeX integration

The output is ready for inclusion in an Org-mode document with a `booktabs`-aware LaTeX preamble. The `#+NAME` line is a deterministic slug derived from the login (`MooersLab` becomes `mooerslab-repos-per-year`, `numpy` becomes `numpy-repos-per-year`), so the same script can populate multiple labeled tables in the same Org file without name collisions. To capture the output directly into an Org file you can use a shell source block:

```org
#+BEGIN_SRC sh :results output replace :exports both
python3 newRepos.py MooersLab
#+END_SRC
```

## Testing

The project ships with a pytest suite, a Makefile that exposes every common workflow, and a coverage gate set at 90 percent.

### Prerequisites

Install the testing extras into the active environment:

```bash
make install-test-deps
```

This installs `pytest`, `pytest-cov`, `coverage`, and `ruff`, all declared in the `[project.optional-dependencies]` block of `pyproject.toml`.

### Quick start

```bash
make test
```

That single command runs the unit suite and the integration suite together, with verbose output. All tests are network-free; the suite patches `urllib.request.urlopen` so it never reaches GitHub.

### Make targets

| Target | Purpose |
|--------|---------|
| `make help` | Show the table of available targets. |
| `make install-test-deps` | Install pytest, pytest-cov, coverage, and ruff. |
| `make test` | Run all tests (unit and integration). |
| `make test-unit` | Run unit tests only. Equivalent to `pytest -m "not integration"`. |
| `make test-integration` | Run integration tests only. Equivalent to `pytest -m integration`. |
| `make coverage` | Run the suite with coverage and produce terminal, HTML, and XML reports. |
| `make coverage-html` | Run `make coverage` and try to open the HTML report in a browser. |
| `make coverage-check` | Run the suite with `--cov-fail-under=90`. Fails the build below threshold. |
| `make lint` | Run `ruff check` over the script and the tests folder. |
| `make clean` | Remove `htmlcov/`, `.coverage`, `coverage.xml`, and pytest and ruff caches. |

### Running specific tests

The pytest framework supports several selection idioms; the ones below cover most needs:

```bash
# Run a single test class.
pytest tests/test_newRepos.py::TestNextLink

# Run a single test function.
pytest tests/test_newRepos.py::TestNextLink::test_extracts_next_url_from_typical_header

# Run every test whose name matches a keyword.
pytest -k "fallback"

# Stop on the first failure and print local variables.
pytest -x -l

# Show stdout from passing tests (useful when iterating on print_org_table).
pytest -s
```

### Coverage

```bash
make coverage           # text + HTML + XML reports
make coverage-html      # open htmlcov/index.html
make coverage-check     # fail if below 90 percent
```

The HTML report lives at `htmlcov/index.html`. The XML report at `coverage.xml` is consumed by services such as Codecov and SonarCloud. Coverage settings live in the `[tool.coverage.run]` and `[tool.coverage.report]` blocks of `pyproject.toml`. Branch coverage is enabled.

### Writing new tests

Place every test file under `tests/` and start the filename with `test_`. Group related tests inside a class named `Test<UnitUnderTest>`. The test name itself should describe the behavior being verified, not the implementation. Pytest fixtures live in `tests/conftest.py`; reuse `fake_urlopen`, `fake_response`, `patch_urlopen`, `http_error`, and `repos_payload` rather than rebuilding the same scaffolding inside individual tests. New end-to-end tests that drive `newRepos.main` belong in the `@pytest.mark.integration` class so they can be filtered with `make test-unit` and `make test-integration`. Mark tests that legitimately need to compare against a literal number with the `PLR2004` ignore already configured in `pyproject.toml`. Always use `tmp_path` for any filesystem work because it is cleaned up automatically. Never call the live GitHub API from a test; the fake `urlopen` in `conftest.py` exists for that reason.

### CI integration

Every target is CI-friendly because the Makefile is the only entry point CI needs to invoke. A minimal GitHub Actions workflow looks like this:

```yaml
name: tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.x"
      - run: make install-test-deps
      - run: make lint
      - run: make coverage-check
```

The same workflow translates to GitLab CI, Jenkins, or any other runner that can invoke `make`.

## Project layout

```
newRepos/
├── LICENSE
├── Makefile
├── README.md
├── newRepos.py            # the script
├── pyproject.toml         # packaging, pytest, coverage, and ruff config
└── tests/
    ├── __init__.py
    ├── conftest.py        # shared fixtures and the fake urlopen
    └── test_newRepos.py   # unit and integration tests
```

## Troubleshooting

If `python3 newRepos.py SomeName` prints `Error fetching data: HTTP Error 404: Not Found`, the supplied login does not exist on GitHub as either a user account or an organization. Double check the spelling at `https://github.com/SomeName`.

If you see `Error fetching data: HTTP Error 403: Forbidden`, you have probably exceeded the unauthenticated rate limit of 60 requests per hour. Set `GITHUB_TOKEN` to a personal access token; authenticated calls get 5000 requests per hour.

If your terminal renders the table without alignment, the issue is your terminal font. The numbers are right-aligned in a 20-character-wide cell with the `:>20` format specifier, which renders correctly in any monospace font.

## Contributing

Issues and pull requests are welcome. Before sending a pull request, run `make lint` and `make coverage-check` and make sure both pass. New code should keep coverage at or above 90 percent and follow the test-naming and fixture conventions described above. The project targets Python 3.8 and newer, so avoid features that require a more recent version.

## License

This project is released under the MIT License. See [LICENSE](LICENSE) for the full text.

## Author

Blaine Mooers, Department of Biochemistry and Physiology, University of Oklahoma Health Campus.

## Funding

- NIH: R01 CA242845, R01 AI088011
- NIH: P30 CA225520 (PI: R. Mannel); P30 GM145423 (PI: A. West)
