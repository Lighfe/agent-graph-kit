import marimo

__generated_with = "0.25.2"
app = marimo.App(width="full")


@app.cell
def _():
    # Monitor notebook (issues #265, #266): totals, drill-down to steps, running stage, retry cases.
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
def _(data, mo, project):
    # Built from the files as read at open (not after each refresh), so a refresh keeps the chosen stage.
    _rows = data.select(data.load_steps() + data.load_cases(), {"project": project.value})
    _stages = [s for s in data.values(_rows, "stage") if s is not None]
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


@app.cell
def _(collect_note, data, mo, project, refresh, stage):
    # Runs `cases.py collect` only after a click on refresh with a chosen project and stage, after
    # `steps.py collect` (this cell reads its note), never on open or export.
    _ = collect_note
    cases_note = None
    if refresh.value and project.value and stage.value:
        _code, _out = data.collect_cases(project.value, stage.value)
        cases_note = (f"`cases.py collect --project {project.value} --repo-slug {project.value} "
                      f"--stage {stage.value}`: exit {_code}\n\n```\n{_out}\n```")
    mo.md(cases_note) if cases_note else None
    return (cases_note,)


@app.cell
def _(cases_note, data):
    _ = cases_note  # read again after each refresh
    cases = data.load_cases()
    return (cases,)


@app.cell
def _(data, saved_note):
    _ = saved_note  # read again after each saved tag
    tags = data.load_tags()
    return (tags,)


@app.cell
def _(cases, data, mo):
    _rows = data.case_table(cases, {})
    case_choices = {f: {str(v): v for v in data.values(_rows, f) if v is not None}
                    for f in ("project", "stage", "role", "marker")}
    case_filters = mo.ui.dictionary({f: mo.ui.dropdown(options=["all"] + list(case_choices[f]), value="all",
                                                       label=f) for f in case_choices})
    return case_choices, case_filters


@app.cell
def _(cases, data, mo, tags):
    # The tags in use and "no tag"; nothing else is offered.
    tag_filter = mo.ui.dropdown(options=["all"] + data.tag_values(data.case_table(cases, tags)),
                                 value="all", label="tag")
    return (tag_filter,)


@app.cell
def _(case_choices, case_filters, cases, data, frame, mo, tag_filter, tags):
    _where = {f: (None if v in (None, "all") else case_choices[f][v]) for f, v in case_filters.value.items()}
    _where["tag"] = None if tag_filter.value in (None, "all") else tag_filter.value
    _rows = data.select_cases(data.case_table(cases, tags), _where)
    mo.vstack([
        mo.md("## Retry cases\n\nOne row per return round of the case file "
              f"`{data.cases_path()}`. Role: the word before the first `:` of the marker. "
              f"Tag and note: your own words, from `{data.tags_path()}` (the last line per case counts)."),
        mo.hstack(list(case_filters.values()) + [tag_filter], justify="start", wrap=True),
        mo.ui.table(frame(_rows, list(data.CASE_FIELDS)), selection=None),
    ])
    return


@app.cell
def _(cases, mo):
    _ids = [c["id"] for c in cases if isinstance(c.get("id"), str)]
    case_pick = mo.ui.dropdown(options=_ids, value=_ids[0] if _ids else None, label="Case")
    tag = mo.ui.text(label="Tag", full_width=True)
    note = mo.ui.text_area(label="Note", full_width=True)
    save = mo.ui.run_button(label="Save tag and note")
    mo.vstack([mo.md("### Tag a case\n\nFree text. An empty tag and note clears the tag of the case."),
               case_pick, tag, note, save])
    return case_pick, note, save, tag


@app.cell
def _(case_pick, data, mo, note, save, tag):
    # Writes one tag line only after a click on the save button, never on open or export.
    saved_note = None
    if save.value and case_pick.value:
        data.save_tag(case_pick.value, tag.value.strip(), note.value.strip())
        saved_note = f"Saved for `{case_pick.value}`."
    mo.md(saved_note) if saved_note else None
    return (saved_note,)


@app.cell
def _(case_pick, mo, tags):
    _t = tags.get(case_pick.value) or {}
    mo.md(f"Current tag of `{case_pick.value}`: `{_t.get('tag') or ''}`, note: {_t.get('note') or ''}"
          if case_pick.value else "No cases.")
    return


if __name__ == "__main__":
    app.run()
