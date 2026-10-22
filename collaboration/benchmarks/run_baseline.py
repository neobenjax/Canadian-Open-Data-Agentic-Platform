"""Run and grade the CAN-15 baseline benchmark against the GTA ground truth (CAN-14).

Three arms answer the same 15 questions with the same model, system prompt and agent loop
(headless Claude Code, `claude -p`), so the only thing that changes is the data access:

- no_tools:     the model alone, no tools and no MCP servers
- mcp_statcan:  the community `mcp-statcan` server (Aryan-Jhaveri/mcp-statcan), hosted HTTP
- candata_mcp:  this repo's CanData-MCP server over stdio

Each run writes one JSONL file to `baseline/runs/` holding the exact model IDs reported by the
API, the run time (UTC), every tool call and the full answer. `grade` then scores every run
file offline against `gta_ground_truth_v1.json` and writes `baseline/baseline_results_v1.*`.

Automatic grades are a first pass. Anything you re-grade by hand goes in
`baseline/manual_overrides.json` as {"<arm>/<model>/<question id>": {"outcome", "reason"}};
overrides win and are listed in the report.

Usage (standard library only, Python 3.12+; needs a logged-in `claude` CLI to run):
    python collaboration/benchmarks/run_baseline.py run --arm no_tools --model claude-sonnet-5-5
    python collaboration/benchmarks/run_baseline.py run --arm candata_mcp --model claude-sonnet-5-5
    python collaboration/benchmarks/run_baseline.py grade
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
GROUND_TRUTH = HERE / "gta_ground_truth_v1.json"
OUT_DIR = HERE / "baseline"
RUNS_DIR = OUT_DIR / "runs"
OVERRIDES = OUT_DIR / "manual_overrides.json"
JSON_OUT = OUT_DIR / "baseline_results_v1.json"
MD_OUT = OUT_DIR / "baseline_results_v1.md"

TIMEOUT = 600
MAX_TURNS = 25

Arm = Literal["no_tools", "mcp_statcan", "candata_mcp"]
Outcome = Literal["correct", "partial", "abstained", "hallucinated"]
ARMS: tuple[Arm, ...] = ("no_tools", "mcp_statcan", "candata_mcp")

# Same words for every arm. Asking the no-tools arm for identifiers is deliberate: inventing
# a table or vector ID is the hallucination this benchmark exists to catch.
SYSTEM_PROMPT = """\
You are a research assistant answering questions about Canadian housing and economic \
statistics. Today's date is {run_date}.

Use official Statistics Canada and Bank of Canada data. For every figure you give, cite the \
Statistics Canada table ID (for example 34-10-0133-01) and vector ID (for example v3823103), \
or the Bank of Canada series, and the reference period.

If the data does not exist, or you cannot verify a figure, say so plainly instead of \
estimating. Keep the answer short."""

MCP_SERVERS: dict[Arm, dict[str, Any]] = {
    "mcp_statcan": {
        "statcan": {"type": "http", "url": "https://mcp-statcan.onrender.com/mcp"},
    },
    "candata_mcp": {
        "candata": {
            "command": "uv",
            "args": ["run", "--directory", str(REPO), "python", "-m", "candata_mcp"],
            # The monorepo is not installed as a package (`[tool.uv] package = false`).
            "env": {"PYTHONPATH": str(REPO / "packages" / "candata-mcp" / "src")},
        },
    },
}


# ------------------------------------------------------------------- running


@dataclass
class Answer:
    question_id: str
    arm: Arm
    requested_model: str
    model_ids: list[str]
    started_at: str
    duration_s: float
    num_turns: int
    tool_calls: list[str]
    is_error: bool
    response: str


def _claude_command(arm: Arm, model: str, run_date: str, mcp_file: Path | None) -> list[str]:
    cmd = [
        "claude",
        "-p",
        "--model",
        model,
        "--system-prompt",
        SYSTEM_PROMPT.format(run_date=run_date),
        "--tools",
        "",
        "--strict-mcp-config",
        "--setting-sources",
        "",
        "--no-session-persistence",
        "--max-turns",
        str(MAX_TURNS),
        "--output-format",
        "stream-json",
        "--verbose",
    ]
    if mcp_file is not None:
        server = next(iter(MCP_SERVERS[arm]))
        cmd += ["--mcp-config", str(mcp_file), "--allowedTools", f"mcp__{server}"]
    return cmd


def ask(arm: Arm, model: str, question: dict[str, Any], mcp_file: Path | None) -> Answer:
    started = datetime.now(UTC)
    # An empty working directory keeps repo files (AGENTS.md, CLAUDE.md, the ground truth
    # itself) out of the model's context.
    with tempfile.TemporaryDirectory() as cwd:
        proc = subprocess.run(
            _claude_command(arm, model, started.date().isoformat(), mcp_file),
            input=question["question"],
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=TIMEOUT,
            check=False,
        )
    tool_calls: list[str] = []
    result: dict[str, Any] = {}
    for line in proc.stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "assistant":
            for block in event["message"].get("content", []):
                if block.get("type") == "tool_use":
                    tool_calls.append(block["name"])
        elif event.get("type") == "result":
            result = event
    response = result.get("result") or proc.stderr.strip() or "no result event"
    return Answer(
        question_id=question["id"],
        arm=arm,
        requested_model=model,
        model_ids=sorted(result.get("modelUsage", {})),
        started_at=started.isoformat(timespec="seconds"),
        duration_s=round((datetime.now(UTC) - started).total_seconds(), 1),
        num_turns=result.get("num_turns", 0),
        tool_calls=tool_calls,
        is_error=bool(result.get("is_error", True)) or proc.returncode != 0,
        response=response,
    )


def run(arm: Arm, model: str, only: list[str] | None) -> Path:
    questions = [q for q in load_questions() if not only or q["id"] in only]
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    suffix = "_partial" if only else ""
    out = RUNS_DIR / f"{datetime.now(UTC).date().isoformat()}_{arm}_{model}{suffix}.jsonl"
    with tempfile.TemporaryDirectory() as tmp:
        mcp_file = None
        if arm in MCP_SERVERS:
            mcp_file = Path(tmp) / "mcp.json"
            mcp_file.write_text(json.dumps({"mcpServers": MCP_SERVERS[arm]}))
        with out.open("w") as fh:
            for q in questions:
                answer = ask(arm, model, q, mcp_file)
                fh.write(json.dumps(asdict(answer), ensure_ascii=False) + "\n")
                fh.flush()
                status = "ERROR" if answer.is_error else f"{len(answer.tool_calls)} tool calls"
                print(f"{q['id']} {arm} {model}: {status}, {answer.duration_s}s", file=sys.stderr)
    return out


# ------------------------------------------------------------------- grading

TABLE_ID = re.compile(r"\b\d{2}-\d{2}-\d{4}-\d{2}\b|\b\d{10}\b|\b\d{8}\b")
VECTOR_ID = re.compile(r"\bv\d{5,11}\b", re.IGNORECASE)
NUMBER = re.compile(r"(?<![\w.])[-−]?\$?\d[\d,]*(?:\.\d+)?")
REFUSAL = re.compile(
    r"\b(not (?:publish|publicly|available|exist|cover)\w*|no (?:official |such )?(?:data|series|"
    r"index|figure)|does not (?:exist|cover|go back|extend)|doesn't (?:exist|cover|go back|"
    r"extend)|(?:cannot|can't|unable to) (?:verify|find|provide|confirm|give)|isn't available|"
    r"don't have|do not have|starts? in|begins? in|only (?:goes|available))",
    re.IGNORECASE,
)
MISMATCH = re.compile(
    r"\b(mismatch|vintage|different (?:year|period)s?|not comparable|"
    r"five years|5 years|out of date|outdated|apples)",
    re.IGNORECASE,
)

# The categorical part of each comparison question, as a pattern that commits to the right
# answer in any phrasing. "Toronto was highest; Oshawa 3.6%" must not pass GT-04.
ANSWER_PATTERNS: dict[str, re.Pattern[str]] = {
    "GT-04": re.compile(
        r"oshawa[^.]{0,60}\b(highest|most)\b|\b(highest|most)\b[^.]{0,60}oshawa", re.IGNORECASE
    ),
    "GT-10": re.compile(r"\b(faster|outpac\w*|higher than|more than)\b", re.IGNORECASE),
    "GT-11": re.compile(r"\b(lower|slower|less than|below)\b", re.IGNORECASE),
    "GT-12": re.compile(r"\b(fell|declin\w*|decreas\w*|dropped|down)\b", re.IGNORECASE),
}


def load_questions() -> list[dict[str, Any]]:
    return json.loads(GROUND_TRUTH.read_text())["questions"]


def normalise_table(table_id: str) -> str:
    """34-10-0133-01, 3410013301 and 34100133 are the same table."""
    return re.sub(r"\D", "", table_id)[:8]


def expected_values(question: dict[str, Any]) -> dict[str, float]:
    """Numeric leaves of `expected`, one level of nesting deep (lists are detail, not graded)."""
    values: dict[str, float] = {}
    for key, value in question["expected"].items():
        if isinstance(value, bool):
            continue
        if isinstance(value, int | float):
            values[key] = float(value)
        elif isinstance(value, dict):
            for sub, v in value.items():
                if isinstance(v, int | float) and not isinstance(v, bool):
                    values[f"{key}.{sub}"] = float(v)
    return values


def tolerance(key: str, value: float) -> float:
    if "pct" in key or key.endswith("_pp"):
        return 0.1
    return 0.5 if value.is_integer() else 0.05


def numbers_in(text: str) -> list[float]:
    """Every number in the answer, with identifiers removed so v3823103 is not a rent."""
    text = VECTOR_ID.sub(" ", TABLE_ID.sub(" ", text))
    found: list[float] = []
    for match in NUMBER.findall(text):
        cleaned = match.replace("$", "").replace(",", "").replace("−", "-")
        try:
            found.append(float(cleaned))
        except ValueError:
            continue
    return found


def matched_values(question: dict[str, Any], text: str) -> dict[str, bool]:
    # Signs are compared as magnitudes: "fell 30.8%" and "-30.8%" both state the change.
    seen = [abs(n) for n in numbers_in(text)]
    return {
        key: any(abs(n - abs(v)) <= tolerance(key, v) for n in seen)
        for key, v in expected_values(question).items()
    }


@dataclass
class Citations:
    tables_expected: list[str]
    tables_cited: list[str]
    vectors_expected: list[str]
    vectors_cited: list[str]
    unverified_ids: list[str] = field(default_factory=list[str])

    @property
    def table_coverage(self) -> float:
        return _share(self.tables_cited, self.tables_expected)

    @property
    def vector_coverage(self) -> float:
        return _share(self.vectors_cited, self.vectors_expected)


def _share(found: list[str], wanted: list[str]) -> float:
    return len(set(found) & set(wanted)) / len(set(wanted)) if wanted else 1.0


def citations_in(question: dict[str, Any], text: str) -> Citations:
    """Compare identifiers in the answer with the question's Core Verification Tuples.

    StatCan identifiers in the answer that are not in the ground truth are listed as
    unverified: they may be real tables the answer used instead, or invented ones.
    """
    cores = [c["core"] for c in question["citations"]]
    tables = sorted({normalise_table(c["table_id"]) for c in cores if c["table_id"] != "Valet"})
    vectors = sorted({c["vector_id"].lower() for c in cores if c["table_id"] != "Valet"})
    cited_tables = {normalise_table(t) for t in TABLE_ID.findall(text)}
    cited_vectors = {v.lower() for v in VECTOR_ID.findall(text)}
    if any(c["table_id"] == "Valet" for c in cores):
        tables.append("valet")
        vectors.append("v39079")
        if re.search(r"valet|bank of canada", text, re.IGNORECASE):
            cited_tables.add("valet")
    unverified = sorted((cited_tables - set(tables)) | (cited_vectors - set(vectors)))
    return Citations(
        tables_expected=tables,
        tables_cited=sorted(cited_tables & set(tables)),
        vectors_expected=vectors,
        vectors_cited=sorted(cited_vectors & set(vectors)),
        unverified_ids=unverified,
    )


@dataclass
class Grade:
    question_id: str
    eval_type: str
    outcome: Outcome
    reason: str
    value_recall: float
    citations: Citations
    overridden: bool = False


def grade_answer(question: dict[str, Any], text: str) -> Grade:
    eval_type = question["eval_type"]
    matches = matched_values(question, text)
    recall = sum(matches.values()) / len(matches) if matches else 1.0
    refused = bool(REFUSAL.search(text))
    gave_numbers = bool(numbers_in(text))
    missing = [k for k, ok in matches.items() if not ok]

    outcome: Outcome
    if eval_type == "refusal":
        # GT-15 asks for a year with no data: any dollar figure is a made-up rent.
        invented = question["id"] == "GT-15" and bool(re.search(r"\$\s?\d", text))
        if refused and not invented:
            outcome, reason = "correct", "declined the unavailable figure"
        elif invented or (gave_numbers and not refused):
            outcome, reason = "hallucinated", "gave a figure the official data does not have"
        else:
            outcome, reason = "partial", "did not clearly decline"
    elif eval_type == "flag":
        if MISMATCH.search(text) and "2020" in text:
            outcome, reason = "correct", "flagged the 2020 income vs 2025 rent mismatch"
        elif gave_numbers:
            outcome, reason = "hallucinated", "computed a share without flagging the mismatch"
        else:
            outcome, reason = "abstained", "no answer and no flag"
    else:
        pattern = ANSWER_PATTERNS.get(question["id"])
        right_call = pattern is None or bool(pattern.search(text))
        if recall == 1.0 and right_call:
            outcome, reason = "correct", "all expected values within tolerance"
        elif recall >= 0.5 and right_call:
            outcome, reason = "partial", f"missing or off: {', '.join(missing)}"
        elif refused and recall < 0.5:
            outcome, reason = "abstained", "declined instead of answering"
        elif gave_numbers:
            outcome = "hallucinated"
            reason = f"stated figures that do not match: {', '.join(missing) or 'wrong call'}"
        else:
            outcome, reason = "abstained", "no figures given"
    return Grade(
        question_id=question["id"],
        eval_type=eval_type,
        outcome=outcome,
        reason=reason,
        value_recall=round(recall, 2),
        citations=citations_in(question, text),
    )


def load_runs(paths: Iterable[Path]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(paths):
        rows += [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    return rows


def grade(run_paths: Iterable[Path]) -> dict[str, Any]:
    questions = {q["id"]: q for q in load_questions()}
    overrides: dict[str, dict[str, str]] = (
        json.loads(OVERRIDES.read_text()) if OVERRIDES.exists() else {}
    )
    graded: list[dict[str, Any]] = []
    for row in load_runs(run_paths):
        g = grade_answer(questions[row["question_id"]], row["response"])
        if row["is_error"]:
            g.outcome, g.reason = "abstained", "run error: " + row["response"][:120]
        key = f"{row['arm']}/{row['requested_model']}/{row['question_id']}"
        if key in overrides:
            g.outcome = overrides[key]["outcome"]  # type: ignore[assignment]
            g.reason, g.overridden = overrides[key]["reason"], True
        graded.append(
            {
                "run": {k: v for k, v in row.items() if k != "response"},
                "response": row["response"],
                "grade": asdict(g),
                "table_coverage": g.citations.table_coverage,
                "vector_coverage": g.citations.vector_coverage,
            }
        )
    return {
        "benchmark": "gta_ground_truth_v1",
        "graded_on": datetime.now(UTC).date().isoformat(),
        "summary": summarise(graded),
        "answers": graded,
    }


def summarise(graded: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for item in graded:
        groups.setdefault((item["run"]["arm"], item["run"]["requested_model"]), []).append(item)
    rows: list[dict[str, Any]] = []
    for (arm, model), items in sorted(groups.items(), key=lambda kv: ARMS.index(kv[0][0])):
        counts = {
            o: sum(i["grade"]["outcome"] == o for i in items)
            for o in ("correct", "partial", "abstained", "hallucinated")
        }
        rows.append(
            {
                "arm": arm,
                "requested_model": model,
                "model_ids": sorted({m for i in items for m in i["run"]["model_ids"]}),
                "run_dates": sorted({i["run"]["started_at"][:10] for i in items}),
                "questions": len(items),
                **counts,
                "table_coverage": round(sum(i["table_coverage"] for i in items) / len(items), 2),
                "vector_coverage": round(sum(i["vector_coverage"] for i in items) / len(items), 2),
                "unverified_ids": sum(
                    len(i["grade"]["citations"]["unverified_ids"]) for i in items
                ),
                "errors": sum(i["run"]["is_error"] for i in items),
            }
        )
    return rows


def _pct(x: float) -> str:
    return f"{x * 100:.0f}%"


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# CAN-15 Baseline Benchmark Results",
        "",
        "> Generated by `collaboration/benchmarks/run_baseline.py grade` on "
        f"{report['graded_on']}. Do not edit by hand; re-run the script.",
        "",
        "Same 15 GTA questions (`gta_ground_truth_v1.json`), same system prompt, same agent "
        "loop. Only the data access changes between arms.",
        "",
        "## Summary",
        "",
        "| Arm | Model ID(s) | Run date | Correct | Partial | Abstained | Hallucinated "
        "| Table coverage | Vector coverage | Unverified IDs | Errors |",
        "| :-- | :-- | :-- | --: | --: | --: | --: | --: | --: | --: | --: |",
    ]
    for s in report["summary"]:
        models = ", ".join(f"`{m}`" for m in s["model_ids"]) or f"`{s['requested_model']}`"
        lines.append(
            f"| {s['arm']} | {models} | {', '.join(s['run_dates'])} | {s['correct']} "
            f"| {s['partial']} | {s['abstained']} | **{s['hallucinated']}** "
            f"| {_pct(s['table_coverage'])} | {_pct(s['vector_coverage'])} "
            f"| {s['unverified_ids']} | {s['errors']} |"
        )
    lines += [
        "",
        "**Outcomes.** *Correct*: every expected value within tolerance (and the right call on "
        "comparison, refusal and flag questions). *Partial*: at least half the values. "
        "*Abstained*: declined or gave no figures. *Hallucinated*: stated figures that do not "
        "match the official data, invented a number for a period with no data, or computed "
        "across mismatched years without flagging it.",
        "",
        "**Citation coverage** is the share of the ground-truth table IDs and vector IDs the "
        "answer names. **Unverified IDs** are StatCan identifiers the answer names that are not "
        "in the ground truth: real alternatives or invented ones, check by hand.",
        "",
        "## Per question",
        "",
    ]
    arms = [(s["arm"], s["requested_model"]) for s in report["summary"]]
    lines.append("| Question | " + " | ".join(f"{a} · {m}" for a, m in arms) + " |")
    lines.append("| :-- |" + " :-: |" * len(arms))
    by_key = {
        (i["run"]["arm"], i["run"]["requested_model"], i["run"]["question_id"]): i
        for i in report["answers"]
    }
    for qid in sorted({i["run"]["question_id"] for i in report["answers"]}):
        cells = []
        for a, m in arms:
            item = by_key.get((a, m, qid))
            cells.append(
                item["grade"]["outcome"] + ("*" if item["grade"]["overridden"] else "")
                if item
                else "–"
            )
        lines.append(f"| {qid} | " + " | ".join(cells) + " |")
    lines += [
        "",
        "`*` re-graded by hand (see `manual_overrides.json`).",
        "",
        "## Hallucination log",
        "",
    ]
    logged = [i for i in report["answers"] if i["grade"]["outcome"] == "hallucinated"]
    if not logged:
        lines.append("None.")
    for i in logged:
        excerpt = " ".join(i["response"].split())[:400]
        lines += [
            f"### {i['run']['question_id']} · {i['run']['arm']} · {i['run']['requested_model']}",
            "",
            f"- **Why:** {i['grade']['reason']}",
            f"- **Unverified IDs:** {', '.join(i['grade']['citations']['unverified_ids']) or '-'}",
            f"- **Answer (excerpt):** {excerpt}",
            "",
        ]
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    run_p = sub.add_parser("run", help="ask every question through one arm and model")
    run_p.add_argument("--arm", choices=ARMS, required=True)
    run_p.add_argument("--model", required=True, help="exact model ID, e.g. claude-sonnet-5-5")
    run_p.add_argument("--only", nargs="*", help="question IDs to run, e.g. GT-13 GT-15")
    grade_p = sub.add_parser("grade", help="grade every run file and write the report")
    grade_p.add_argument("runs", nargs="*", type=Path, help="run files (default: all)")
    args = parser.parse_args()

    if args.command == "run":
        print(f"wrote {run(args.arm, args.model, args.only)}")
        return 0
    report = grade(args.runs or RUNS_DIR.glob("*.jsonl"))
    JSON_OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    MD_OUT.write_text(render_markdown(report))
    print(f"wrote {JSON_OUT.relative_to(REPO)} and {MD_OUT.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
