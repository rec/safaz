# safaz

safaz owns SFZ parsing, conversion, diagnostics, local sample inspection, and
the SFZ support catalog. uFor owns generic instrument definitions and portable
preparation; safaz depends on uFor, never the reverse. Audio playback belongs
to consumers.

Keep extraction changes mechanical. Import symbols from their defining modules
and keep `__init__.py` empty. Preserve existing metadata comment syntax. Do not
add compatibility forwarding modules in the former owners.

Use Python 3.13, uv, explicit types, and frozen Pydantic models where possible.
Before committing Python/data changes run pytest, Ruff, formatting,
`ty check safaz`, pyupgrade on changed Python, and `git diff --check`.
Commit and push requested changes, with dependency changes in separate commits.
Preserve unrelated work and never switch existing branches or create merge
commits. Plans must include `Additional work beyond the prompt`, with `None.`
when there is no extra work.
