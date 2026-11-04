import marimo

__generated_with = "0.25.2"
app = marimo.App(width="full")


@app.cell
def _():
    # Monitor notebook (issue #265): totals, drill-down to steps, running stage.
    # It shows numbers and text only. Start: see SKILL.md of the monitor skill.
    import importlib.util
    from pathlib import Path

    import marimo as mo
    import polars as pl

    _src = Path(__file__).resolve().parent / "data.py"
    _spec = importlib.util.spec_from_file_location("agk_monitor_data", _src)
    data = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(data)
    return data, mo, pl


@app.cell
def _(mo, pl):
    def flat(row):
        """One table row: lists joined to text, the weighted dict as one column per provider."""
        out = {}
        for k, v in row.items():
            if k == "weighted":
                for provider, value in v.items():
                    out[f"weighted_{provider}"] = round(value, 1)
            elif isinstance(v, list):
                out[k] = ", ".join(map(str, v))
            else:
                out[k] = v
        return out

    def frame(rows, columns):
        """A polars frame of the rows with the given columns first; an empty frame keeps the columns."""
        rows = [flat(r) for r in rows]
        extra = [k for r in rows for k in r if k not in columns]
        cols = list(columns) + list(dict.fromkeys(extra))
        if not rows:
            return pl.DataFrame({c: [] for c in cols})
        return pl.DataFrame([{c: r.get(c) for c in cols} for r in rows], strict=False, infer_schema_length=None)

    def context_svg(rows):
        """A line of the context size over the steps of one launch."""
        pts = [(r.get("seq"), r.get("context_tokens")) for r in rows
               if isinstance(r.get("seq"), int) and isinstance(r.get("context_tokens"), (int, float))]
        if not pts:
            return mo.md("No context sizes for this launch.")
        w, h, pad = 640, 160, 24
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        x0, x1, y1 = min(xs), max(xs), max(ys) or 1
        sx = (lambda x: pad + (x - x0) * (w - 2 * pad) / (x1 - x0)) if x1 > x0 else (lambda x: w / 2)
        sy = lambda y: h - pad - y * (h - 2 * pad) / y1
        line = " ".join(f"{sx(x):.1f},{sy(y):.1f}" for x, y in pts)
        return mo.Html(
            f'<svg viewBox="0 0 {w} {h}" width="100%" style="max-width:{w}px" role="img" '
            f'aria-label="context tokens over the steps">'
            f'<polyline points="{line}" fill="none" stroke="currentColor" stroke-width="2"/>'
            f'<text x="{pad}" y="14" font-size="12" fill="currentColor">context tokens, max {y1:,}</text>'
            f'<text x="{pad}" y="{h - 6}" font-size="12" fill="currentColor">seq {x0}</text>'
            f'<text x="{w - pad}" y="{h - 6}" font-size="12" text-anchor="end" fill="currentColor">seq {x1}</text>'
            f"</svg>")

    return context_svg, frame


@app.cell
def _(data, mo):
    _initial = data.load_record() + data.load_steps()
    _projects = [p for p in data.values(_initial, "project") if p is not None]
    project = mo.ui.dropdown(options=_projects, value=_projects[0] if _projects else None,
                             label="Project")
    refresh = mo.ui.run_button(label="Refresh: collect the step rows of the project")
    mo.vstack([
        mo.md("# Monitor\n\nTokens, time and steps of the kit's launches. "
              f"Run record: `{data.rr.record_path()}`. Step rows: `{data.steps_path()}`."),
        mo.hstack([project, refresh], justify="start"),
    ])
    return project, refresh


@app.cell
def _(data, mo, project, refresh):
    # Runs `steps.py collect` only after a click on the button, never on open or export.
    collect_note = None
    if refresh.value and project.value:
        _code, _out = data.collect_steps(project.value)
        collect_note = f"`steps.py collect --project {project.value}`: exit {_code}\n\n```\n{_out}\n```"
    mo.md(collect_note) if collect_note else None
    return (collect_note,)


@app.cell
def _(collect_note, data):
    _ = collect_note  # read again after each refresh
    record = data.load_record()
    steps = data.load_steps()
    weights = data.load_weights()
    providers = [k for k, v in weights.items() if isinstance(v, dict)]
    return providers, record, steps, weights


@app.cell
def _(data, mo, record):
    choices = {f: {str(v): v for v in data.values(record, f) if v is not None} for f in data.GROUP_FIELDS}
    filters = mo.ui.dictionary({f: mo.ui.dropdown(options=["all"] + list(choices[f]), value="all", label=f)
                                for f in data.GROUP_FIELDS})
    group_by = mo.ui.multiselect(options=list(data.GROUP_FIELDS), value=["role"], label="Group by")
    mo.vstack([mo.md("## Totals"), mo.hstack(list(filters.values()), justify="start", wrap=True), group_by])
    return choices, filters, group_by


@app.cell
def _(choices, data, filters, frame, group_by, mo, providers, record, weights):
    where = {f: (None if v in (None, "all") else choices[f][v]) for f, v in filters.value.items()}
    by = list(group_by.value)
    _rows = data.totals(data.select(record, where), by, weights)
    for _r in _rows:
        _r["weighted"] = {p: _r["weighted"][p] for p in providers if p in _r["weighted"]}
    _cols = by + ["estimate", "lines", *data.TOKEN_KINDS, "seconds"] + [f"weighted_{p}" for p in providers]
    totals_table = mo.ui.table(frame(_rows, _cols), selection="single", label="Totals (select a row to see its launches)")
    mo.vstack([
        mo.md(f"Time is `end` minus `start` of each record line. Weighted columns: **{data.WEIGHT_LABEL}**, "
              f"one column per provider (Claude and Codex are not added together; lines with no provider "
              f"have no weighted value). Weights file: `{data.weights_path()}`. "
              "Rows with `estimate` true are estimated lines, shown apart from the measured lines."),
        totals_table,
    ])
    return by, totals_table, where


@app.cell
def _(by, data, frame, mo, record, steps, totals_table, where):
    _picked = totals_table.value.to_dicts() if len(totals_table.value) else []
    _group = {f: _picked[0][f] for f in by + ["estimate"]} if _picked else {}
    _rows = data.launches(record, where, _group, steps) if _picked else []
    _cols = ["launch", "project", "stage", "issue", "role", "provider", "model", "retry", "estimate",
             "start", "end", "seconds", *data.TOKEN_KINDS]
    launch_table = mo.ui.table(frame(_rows, _cols), selection="single",
                               label="Launches of the selected total (select one to see its steps)")
    mo.vstack([mo.md("## Drill-down"), launch_table if _picked else mo.md("Select a row of the totals.")])
    return (launch_table,)


@app.cell
def _(context_svg, data, frame, launch_table, mo, steps):
    _picked = launch_table.value.to_dicts() if len(launch_table.value) else []
    _launch = _picked[0]["launch"] if _picked else None
    _rows = data.launch_steps(steps, _launch) if _launch else []
    _cols = ["seq", "time", "duration_s", "tool", "target", *data.TOKEN_KINDS, "context_tokens",
             "result_chars", "is_error", "kit_doc"]
    _reads = data.kit_doc_reads(_rows, ["launch"])
    mo.vstack([
        mo.md(f"### Steps of launch `{_launch}`" if _launch else "### Steps"),
        mo.ui.table(frame(_rows, _cols), selection=None) if _launch else mo.md("Select a launch."),
        context_svg(_rows) if _launch else mo.md(""),
        mo.md("Kit document reads of this launch"),
        mo.ui.table(frame(_reads, ["launch", "kit_doc", "reads"]), selection=None),
    ])
    return


@app.cell
def _(data, frame, mo, steps, where):
    _where = {k: v for k, v in where.items() if k in ("project", "stage", "issue", "role", "model")}
    _steps = data.select(steps, _where)
    mo.vstack([
        mo.md("### Kit document reads per role (filters of the totals)"),
        mo.ui.table(frame(data.kit_doc_reads(_steps, ["role"]), ["role", "kit_doc", "reads"]), selection=None),
        mo.md("### Kit document reads per launch"),
        mo.ui.table(frame(data.kit_doc_reads(_steps, ["launch"]), ["launch", "kit_doc", "reads"]), selection=None),
    ])
    return


@app.cell
def _(data, mo, project, steps):
    _stages = [s for s in data.values(data.select(steps, {"project": project.value}), "stage") if s is not None]
    stage = mo.ui.dropdown(options=[str(s) for s in _stages], value=str(_stages[-1]) if _stages else None,
                           label="Stage")
    mo.vstack([mo.md("## Running stage"), stage])
    return (stage,)


@app.cell
def _(data, frame, mo, project, stage, steps):
    _now = data.now_utc()
    _stage = int(stage.value) if stage.value else None
    _rows = data.running(steps, _now, stage=_stage, project=project.value) if _stage is not None else []
    _cols = ["launch", "role", "issue", "start", "run_time_s", "tokens", "steps", "last_seq", "last_tool",
             "last_target", "newest_step", "active"]
    mo.vstack([
        mo.md(f"Now: `{data.rr.iso(_now)}`. `active`: the newest step time is at most 5 minutes before now. "
              "A Codex QA attempt counts as active only in the 5 minutes after its start, "
              "since its rows carry the attempt start as `time`. "
              "Tokens so far: the sum of the four token kinds of the step rows."),
        mo.ui.table(frame(_rows, _cols), selection=None),
    ])
    return


if __name__ == "__main__":
    app.run()
