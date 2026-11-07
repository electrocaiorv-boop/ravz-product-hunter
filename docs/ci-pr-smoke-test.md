# CI smoke test (temporary)

This file exists only to exercise the `pull_request` path of
`.github/workflows/ci.yml`.

Every CI run so far has been a `push` to `main`, so two things had never
actually executed:

- the `Whitespace and conflict-marker check (PR range)` step, which is gated
  on `github.event_name == 'pull_request'` and had always been reported as
  `skipped`;
- the `PR_BASE_SHA` validation added to the `Determine diff range` step, which
  had only been proven locally.

This change is deliberately harmless: one documentation file, no credentials,
no configuration, no application code, no test changes.

**Not intended for merge.** The pull request will be closed without merging
and the `ci/pr-smoke-test` branch deleted once the CI behaviour has been
confirmed.
