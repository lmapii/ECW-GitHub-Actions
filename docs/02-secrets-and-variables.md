# Secrets and variables

Everything project-specific about *where* and *what* to book lives in your
repository's own GitHub config (**Settings > Secrets and variables >
Actions**), never in the workflow YAML. This is what makes
`ci-job-smoke.yml` copy-paste-safe across projects.

## Secret: `ECW_API_KEY` (required)

The bearer credential for every ECW backend call the pipeline makes
(`X-API-Key` header). See [docs/01-getting-started.md](01-getting-started.md#2-create-an-ecw-api-key)
for how to mint one.

Treat it like a password:
- It's never printed in logs (GitHub masks secret values automatically,
  and the workflow never echoes it directly).
- Revoke it if it ever leaks, and mint a fresh one -- from the ECW
  frontend, **Profile > Developer Settings**, click **Revoke** next to the
  key. (The underlying call is `GET /revoke-api-key?name=...` -- see
  [docs/05-api-reference.md](05-api-reference.md) -- but use the frontend
  unless you're scripting this.)
- If your team rotates keys periodically, just update the secret value;
  nothing else needs to change.

## Variable: `BOARD_NAME` (required, no default)

Text the pipeline searches for (case-insensitive substring match) against
the backend's board types, to pick which kind of board to book. There is
**deliberately no fallback default** baked into the workflow -- an unset
`BOARD_NAME` fails the `Reserve` job immediately with a clear message,
rather than silently booking whatever board happens to match an empty
string first.

Examples: `Arduino UNO R4 WiFi`, `STM32 DK`.

## Variable: `ECW_BACKEND_URL` (optional)

Base URL of the ECW backend to talk to. Defaults to
`https://api-dev.edgebench.io` if unset. Set it explicitly when choosing
another environment. For production, use `https://www.edgebench.io/api`.
The API key and board must belong to the same environment.

For HIL, confirm that the selected backend exposes `/v1/peripheral-prepare`.
The client reuses this existing frontend API; a backend version without it
cannot run Configure HIL. The integration does not add new backend routes.

## Variable: `ECW_BOOKING_WAIT_TIMEOUT_SECONDS` (optional)

How long the `Wait` job will keep polling for your booking to become
active before giving up. Defaults to `86400` (24 hours) -- matching how
far ahead auto-booking itself searches for a free slot, so this ceiling
covers the whole window rather than giving up early on a busy board.

## Variable: `ECW_JOB_WAIT_TIMEOUT_SECONDS` (optional)

How long the `Test` job will keep polling any single CI job for a terminal
status before giving up on it. Defaults to `180` seconds.

## Setting variables without the GitHub UI

If your `gh` CLI is recent enough (`gh variable set NAME --body value`)
works; on an older `gh` (no `variable` subcommand), use the REST API
directly:

```bash
gh api repos/<owner>/<repo>/actions/variables -f name=BOARD_NAME -f value="Arduino UNO R4 WiFi" -X POST
```

## Optional HIL configuration

Add repository variable `HIL_SENSOR_NAME` for the exact ECW sensor name.
Configure HIL skips setup if it is blank. `HIL_CSV_FILE` optionally chooses
another CSV path relative to `.github/user/hil/`. CSV values use the same
physical units and columns as the frontend export. See
[Configure HIL](10-hil-configuration.md). Both operations use `ECW_API_KEY`;
no new secret is needed.
