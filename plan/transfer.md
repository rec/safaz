# Context transfer

Updated 2026-10-19. This file records conversation context and observations
not yet captured elsewhere in the repository. Read the existing reference-test
plan, README and findings for the implementation, pins, comparison contract
and earlier results; those are intentionally not repeated here.

## GitHub access is now working

Use `gh` outside the execution sandbox via `sandbox_permissions="require_escalated"`.
This exposes the user's existing macOS Keychain credentials. Verified operations:
workflow dispatch, job-log retrieval, and artifact download followed by ZIP
integrity verification. The user was already logged in throughout; do not ask
them to run `gh auth login`, manually dispatch workflows, or paste/download logs
as the normal workflow.

The user explicitly authorized changing only `approval_policy` in
`/Users/tom/.codex/config.toml` from `never` to `on-request`. The active session
subsequently gained escalation support. A future context should test its actual
permissions rather than assume that reading this setting proves they are active.
No further edits under `.codex` are authorized by that earlier approval.

The connected GitHub integration can read logs and download artifacts, but its
job-rerun action reached GitHub and returned HTTP 403, `Resource not accessible
by integration`. Use the verified CLI path for writes. App action-approval
settings are distinct from GitHub Actions write permission. Browser access
remained denied despite Website Permissions changes and restarts; do not repeat
that setup loop or try to bypass the denial.

Working CLI commands, executed with escalation:

```sh
gh workflow run reference-test.yml --ref main --repo rec/safaz
gh api repos/rec/safaz/actions/runs/RUN_ID/jobs
gh api --allow-escape-sequences repos/rec/safaz/actions/jobs/JOB_ID/logs > /private/tmp/safaz-job.log
gh api repos/rec/safaz/actions/artifacts/ARTIFACT_ID/zip > /private/tmp/safaz-artifact.zip
```

The escape-sequence option is needed because this installed CLI otherwise
rejects the job log's embedded terminal formatting, even when redirected.
Save logs to files rather than dumping their contents into tool output.
Never print credential values.

## Evidence newer than the committed findings

Run [39251400304](https://github.com/rec/safaz/actions/runs/39251400304), at
`191fa65456c9e6f47ac0e5cf280ebb1b7bdb178b`, established that the macOS Xcode
selection works: configuration and compilation succeeded. Linux and macOS
both reached comparisons and reported 9 failures and 5 passes. These are
comparison failures, not the earlier macOS compilation failure. Their detailed
cross-platform reports and audio still need inspection.

The Windows log identifies its actual image as `windows-2025-vs2026`, version
`20261007.264.1`. The selected Visual Studio 2022 generator could not find an
installation. The prior inventory assumption in the committed findings was
therefore insufficient. Inspect the actual runner's compiler inventory before
choosing a correction; do not simply repeat the current generator selection.

The downloaded macOS artifact from that run contains only CMake cache/compiler
metadata, with no comparison reports or WAVs. Transfer and ZIP validation
succeeded. A likely cause is upload-artifact's hidden-file exclusion of
`.reference-artifacts/`; confirm and address evidence collection before claiming
that successful upload means the audio was preserved.

Access verification itself dispatched
[run 39264689528](https://github.com/rec/safaz/actions/runs/39264689528) on the
same revision. Its final metadata was checked while writing this handoff:

| Platform | Job ID | Failed step |
| --- | --- | --- |
| macOS | 118101093668 | Compare and preserve findings |
| Windows | 118101093816 | Configure unmodified sfizz |
| Linux | 118101093878 | Compare and preserve findings |

Do not launch another identical run merely to verify access. The latest run's
full logs and artifacts have not yet been inspected.

## Resume from here

The next useful work is to inspect the latest logs, correct Windows toolchain
selection and missing comparison-artifact collection, then gather the unchanged
unity evidence on all three platforms. Keep the user's standing instruction:
sfizz and tolerances remain unchanged. Updating the committed findings should
replace stale access/setup conclusions with verified outcomes, without claiming
audio agreement from matching failure counts alone.

The user prefers diagnosing uncertain behavior and has explicitly said to
assume that preference rather than repeatedly ask whether to diagnose it.
That does not authorize changing playback semantics or accepting mismatches.

Local access-verification files, if still present, are
`/private/tmp/safaz-cli-access-macos.log` and
`/private/tmp/safaz-cli-access-macos.zip`, both from run 39251400304. They are
temporary conveniences, not durable evidence or required inputs.

## Additional work beyond the prompt

None.
