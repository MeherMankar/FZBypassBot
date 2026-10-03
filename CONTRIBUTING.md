# Contributing to FZBypassBot

Thanks for contributing. This guide describes the project-specific workflow
for changes, especially resolver fixes where a live site can change independently
of this repository.

## Project map

- `FZBypass/bypass/checker.py` dispatches URLs to their resolver.
- `FZBypass/bypass/ddl.py` contains many shortener and file-host resolvers.
- `FZBypass/bypass/dlinks.py` contains additional direct-link and host resolvers.
- `FZBypass/bypass/scrape.py` contains page-scraping and index-site resolvers.
- `FZBypass/core/networking/` provides shared asynchronous HTTP clients and
  normalized response and network-error types.
- `FZBypass/core/exceptions.py` contains resolver-facing exceptions.
- `tests/` contains offline tests and fixtures. The existing capture utilities
  and raw network logs are local artifacts, not test fixtures.

When adding a supported host, update the dispatcher and the relevant README
support table as well as the resolver. Keep the resolver focused on its own
site flow and reuse the shared clients (`http`, `cf`, or `ts`) where appropriate.

## Set up a local environment

The project targets Python 3.10 in its current GitHub Actions workflows. A
virtual environment is recommended. From the repository root:

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

On Linux or macOS, use `python3.10 -m venv .venv` and
`source .venv/bin/activate` instead. If a dependency cannot be installed on
your operating system, note the package and platform in your report rather
than silently removing it from the project requirements.

The bot requires `BOT_TOKEN`, `API_ID`, `API_HASH`, and `OWNER_ID` during
application imports. Unit tests do not start the bot or connect to Telegram,
but imports may still initialize its client. For local testing, create
`config.env` from `sample_config.env` and use disposable test values for the
required fields, or set local environment variables before starting Python.
Never use or commit production credentials. `config.env` is ignored by Git.

## Resolver test strategy

Use two separate kinds of checks:

1. **Offline replay tests** prove the resolver still handles a known
   request/response flow. They must not contact a real shortener and are safe
   to run in CI.
2. **Manual live checks** contact the real site and help determine whether its
   current behavior still matches the recorded flow. They are opt-in and must
   not be part of normal unittest discovery or CI.

A passing offline test does not prove that the live site still works. A failed
live check does not by itself prove a code regression: the site may have
changed, blocked the request, rate-limited the test, or been temporarily
unavailable.

### Run the offline tests

From the repository root:

```powershell
python -m unittest discover -s tests -p "test_*.py" -v
```

The same command works in a POSIX shell. It discovers the existing Webshare
unit tests and the resolver cassette tests. Do not run live checks as part of
this command.

The current GitHub Actions workflows run Ruff; they do not run the unittest
suite. A green workflow therefore does not replace the local unittest command
above. For local lint and formatting checks, install Ruff in your development
environment and run it against the files you changed:

```powershell
ruff check FZBypass tests
ruff format --check FZBypass tests
```

Run the formatter without `--check` if you intend it to rewrite files. Review
its diff before including the result; do not commit unrelated formatting or
automated changes.

### Add an offline cassette test

Put fixtures in `tests/fixtures/<resolver>/` and tests in a file named
`tests/test_<resolver>.py`. The minimal example is:

- `tests/fixtures/mediafire/basic.json`
- `tests/resolver_cassette.py`
- `tests/test_resolver_cassettes.py`

The MediaFire fixture currently included in this repository is explicitly
**synthetic**. It demonstrates the format and is not evidence that a real
MediaFire exchange has been recorded or verified.

A cassette is JSON with:

- `resolver`: stable resolver identifier.
- `fixture_kind`: whether it is synthetic or a sanitized live capture.
- `input_url` and `expected_result`: the resolver input and asserted output.
- `exchanges`: ordered entries containing `request` and `response`.
- A request's `method` and `url`, plus any relevant headers, cookies, query
  parameters, form `data`, or JSON body.
- A response's status, final URL, relevant headers, and body. Include
  `redirect_chain` as useful human-readable capture metadata.

The current `ResolverCassette` helper replays ordered GET/POST exchanges and
checks request fields present in each fixture entry. It constructs a normalized
`HTTPResponse` from the recorded status, final URL, headers, and `body_text`.
At present, it does **not** emulate intermediate redirects or automatically
assert `redirect_chain`; if redirect behavior is important, add a focused test
that verifies the resolver's redirect handling rather than assuming the
metadata field is replayed.

Keep tests deterministic and narrowly scoped:

- Assert the returned destination or expected structured failure.
- Assert that all recorded exchanges were consumed with `assert_complete()`.
- Include a changed/missing-field response test when parsing failures matter.
- Include relevant request headers, cookies, form fields, and POST bodies in
  the fixture so an accidental change in the outbound flow is observable.
- Avoid sleeps, live DNS, random values, current timestamps, and dependence on
  test order. Mock clocks, randomness, or other nondeterministic dependencies
  when those affect the behavior being tested.
- Do not make tests conditional on the real site being available.

The cassette helper is intentionally small. If a resolver needs unsupported
behavior such as request-specific redirect responses, response cookies, binary
content, or additional HTTP verbs, extend the helper and add tests for that
behavior. Do not make a fixture appear to test a behavior the replay helper
does not actually simulate.

### Capture and sanitize fixtures

Fixtures are committed test data. Before adding a real capture:

1. Record the smallest flow that reproduces the resolver path: method, URL,
   relevant request values, status, final URL, headers needed by the resolver,
   response body, and redirect information.
2. Remove credentials and private data. Replace API keys, auth headers,
   cookies, session IDs, CSRF tokens, personal information, and private source
   or destination URLs with stable placeholders.
3. Keep the captured structure needed by the parser, including the names and
   placement of hidden fields or form inputs. Use stable placeholder values for
   rotating token contents unless the token's format itself is what the test
   covers.
4. Check the fixture and the diff for secrets, account-specific identifiers,
   signed URLs, and unnecessarily large HTML before committing.

Never commit `config.env`, production tokens/cookies, unredacted browser
profiles, or raw network logs. Do not add a real, reusable shortener or
download link just to make a test fixture realistic.

## Error reporting and failure diagnosis

Historically, resolvers raise `DDLException` with free-form messages, so there
is not yet a consistent failure-step field across every resolver. New or
substantially updated resolver steps should use
`ResolverStepError(resolver, step, detail)` from
`FZBypass.core.exceptions`. It remains a `DDLException`, so existing bot error
handling continues to work, while tests can inspect `resolver` and `step`.

Use a stable resolver name and a short hyphenated step, for example:

- `landing-page`
- `redirect-follow`
- `token-extraction`
- `timer-validation`
- `form-submit`
- `extract-download-link`

Keep `detail` useful and concise. Do not put secrets, cookies, complete
authorization headers, or private URLs in the exception. Raise network errors
with their original exception as the cause where applicable:

```python
try:
    response = await http.get(url)
except NetworkError as exc:
    raise ResolverStepError("ExampleShortener", "landing-page", type(exc).__name__) from exc
```

When a test or live check fails, identify the earliest failing step:

| Observation | Likely category | How to check |
|:------------|:----------------|:-------------|
| Request differs from the fixture unexpectedly | Code regression | Inspect the cassette assertion and resolver request construction. |
| Request matches, but the captured response shape differs from the fixture | Possible site change | Recheck manually; compare status, final URL, form fields, token names, and redirects. |
| Timeout, DNS/connectivity failure, 429, or transient 5xx | Inconclusive live check | Retry later or from a permitted network; do not mark the resolver broken solely on this evidence. |
| Response matches the fixture but parsing now fails | Parser regression or stale fixture | Check whether the fixture still represents the intended supported layout; update code or fixture based on evidence. |
| Live check succeeds but replay fails | Code regression or fixture drift | Make the offline test reproduce the live flow and correct the mismatch. |

Avoid broad exception catches, silent `None` results, and fallback values that
look like successful destinations. A failure should remain distinguishable
from a valid resolved URL.

## Manual live verification

Live tests are opt-in and make requests to third-party sites. Use only links
you are authorized to test, obey the target service's terms and rate limits,
and avoid repeated or concurrent requests that could burden the service.
Never put a live check in unittest discovery, a GitHub Actions workflow, or
another automatic CI job.

The example MediaFire smoke check is run explicitly:

```powershell
python tests/live_mediafire.py "https://www.mediafire.com/file/..."
```

It requires a real, usable MediaFire link and network access. A placeholder
URL will not be a valid live test. When investigating a failure, first run the
offline test, then make at most the requests reasonably required to identify
the changed step. Compare the observation with a sanitized fixture; do not
paste secrets or full private links into an issue or pull request.

If the site's behavior changed, update the cassette and resolver test to
represent the new observed flow, then update the resolver. If the site is
temporarily unreachable or rate-limited, report the live check as
inconclusive—not broken.

## README resolver status

The README lists **Working**, **Broken**, or **Untested**, along with a
**Last Verified** date:

- **Working**: a successful manual live check was completed on that date.
- **Broken**: a reproducible live failure was confirmed, with transient
  network failures ruled out as far as practical.
- **Untested**: no recent successful live verification is recorded, or the
  available evidence is inconclusive.

Offline cassette tests do not change live status. Update the status and date
when adding or changing support only if you personally ran and observed a
successful live check; don't infer a live result from code inspection or
fixture replay. Keep the table's grouping and domain names consistent with
the dispatcher's actual coverage.

## Implementation constraints

### HTTP, challenge-solving APIs, and browser automation

- Do not add headless browsers, browser automation, browser-driving APIs, or
  browser-based resolver dependencies. Resolver flows should use the
  repository's asynchronous HTTP clients and explicit parsing.
- An HTTP API is acceptable when it materially improves a resolver and has a
  usable free service tier (Peak.fo is an existing example). Document its
  purpose, setup, limits, and behavior when the service is unavailable.
- Do not make a paid-only API or account a requirement for core project
  behavior. Keep API integrations injectable or mockable so their behavior
  can be tested offline.
- If a proposed approach cannot work without browser automation, stop and
  discuss an HTTP/API alternative rather than introducing a browser runtime.

### Runtime and deployment

- Keep asynchronous resolver work bounded with timeouts. Use the shared
  networking layer unless a concrete requirement calls for another client;
  document that exception in code.
- Avoid adding persistent processes or infrastructure that require paid
  hosting. Document a free-tier deployment path on Render or Koyeb where
  feasible, and describe required environment variables and health checks.
- Do not claim that the current long-running polling bot runs on Vercel's
  serverless runtime as-is. Vercel requires a compatible webhook/serverless
  integration for this workload; document one only if it is actually
  implemented and tested. Free-tier products and limits change, so verify
  current platform constraints before promising a deployment path.
- Keep secrets in environment configuration. Never hardcode tokens, cookies,
  or private API keys in code, fixtures, examples, logs, or documentation.

### Code quality and scope

- Keep changes focused and follow the surrounding naming, formatting, and
  async patterns.
- Preserve existing behavior outside the intended change.
- Reuse shared parsers, clients, and helpers rather than duplicating them.
- Add comments only where the reason for non-obvious behavior is not clear
  from the code.
- Include user-facing configuration and documentation changes when a feature
  adds a setting, dependency, supported host, or deployment requirement.

## Pull request checklist

Before opening a pull request, confirm:

- [ ] The change is scoped to the described issue or feature.
- [ ] Relevant offline tests pass:
  `python -m unittest discover -s tests -p "test_*.py" -v`.
- [ ] New or changed resolver behavior has deterministic offline coverage.
- [ ] No test unexpectedly contacts a live site.
- [ ] Any live verification is described separately, with outcome and date.
- [ ] The README status is updated only when live verification supports it.
- [ ] Fixtures and logs contain no secrets, personal data, or private links.
- [ ] Resolver failures identify the failed step where practical.
- [ ] Required config, API limits, and feasible deployment instructions are
  documented.
- [ ] The diff has been reviewed for unrelated formatting or generated files.

In the pull request description, summarize the behavior change, tests run,
whether a manual live check was performed, and any known limitations.
