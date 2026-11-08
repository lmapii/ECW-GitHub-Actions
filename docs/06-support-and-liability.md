# Support boundary -- please read before modifying the pipeline

This template's `.github/workflows/ci-job-smoke.yml` and
`.github/scripts/*.py` implement real safety behavior around a shared,
limited resource -- board bookings -- that is easy to break in ways that
are not obvious from reading a single script in isolation. Examples of
things that are *not* accidental and exist for a reason:

- `find_or_create_booking.py` reuses an existing booking instead of always
  creating a new one, specifically to avoid piling up reservations on
  every pipeline run.
- `Release` cancels the booking in almost every outcome (`if: !cancelled()
  && needs.reserve.result == 'success'`), including when earlier jobs
  failed, specifically so a failed run doesn't leak a held booking.
- `Collect`/`Release`'s `if:` conditions are tuned to skip cleanly when
  their prerequisites never ran, rather than running against empty/missing
  state.

## What we support

- **`.github/user/build/build.sh`** -- change this freely. It's entirely
  your project's own build logic; nothing here can affect anyone else's
  bookings or the shared backend.
- **`.github/user/jobs/*.json`** -- change these freely. Adding, removing,
  or reordering CI jobs only affects your own booking's own jobs.
- **Adding your own steps before or after the pipeline's existing steps**
  (in a copy of the workflow you maintain) -- e.g. a notification step
  after `Release`, or a setup step before `Build`. Inserting steps around
  the existing ones is safe as long as you don't remove or reorder the
  existing ones.

## What's unsupported -- change at your own risk

Editing `.github/workflows/ci-job-smoke.yml`'s existing jobs/steps or
`.github/scripts/*.py` themselves (not adding to them, but changing their
logic) is unsupported. If you do and it causes booking leaks, hitting
backend rate limits, stuck reservations, or similar, that's on you --
please don't file that against the ECW backend team, and please don't
expect the same guarantees this template was built to provide.

If something in the generic parts genuinely needs to change (a bug, a
missing capability), open an issue/PR against this template instead of
forking the logic silently -- a fix here benefits every project using it.
