# Experiment and evidence index

This index links complete experiment records rather than repeating their
methods, results, or limitations. Operational test procedures belong in the
[verification guide](../docs/verification.md).

| Date | Experiment | Paper |
|---|---|---|
| 2026-10-13 | [GPT-6 Luna migration: automated and live compatibility checks](2026-10-13-gpt-6-luna.md) | [PDF](2026-10-13-gpt-6-luna.pdf) |
| 2026-10-22 | [Independent fact-check: corrections, source coverage, and verification limits](2026-10-22-independent-fact-check.md) | [PDF](2026-10-22-independent-fact-check.pdf) |

The migration is an API compatibility check; the fact-check is a repository
correctness check. Neither is a controlled model-accuracy or training experiment.
There are no trained networks or measured accuracy scores to compare. Here,
"verdict" means a model's sampled judgment, "credited minutes" means app
accounting, and "desired policy" means the state the app asks its enforcement
adapter to apply. The linked reports distinguish these from observed reality.

## Rebuild the papers

From the repository root:

```powershell
uv run scripts/render_report.py reports/2026-10-13-gpt-6-luna.md reports/2026-10-22-independent-fact-check.md
```

The [renderer](../scripts/render_report.py) pins its own ReportLab and Mistune
dependencies using [uv script metadata](https://docs.astral.sh/uv/guides/scripts/#declaring-script-dependencies).
uv creates an isolated script environment; these PDF-only packages are not app
dependencies. Each PDF sits beside its Markdown source, carries Libor Burian
as author, and uses linked, wrapped paragraphs and tables. Rendering does not
load `.env` or private runtime artifacts. Inspect every rendered page after a
source change; a successful build alone does not verify layout.
