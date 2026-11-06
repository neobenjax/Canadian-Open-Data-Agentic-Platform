# CAN-43: Output validators, prompt-injection defense and LLM tool-call audit

## Threat model

The Claude planner is the only LLM in the agent graph, and it never handles data values. It
picks official series and a calculation recipe; the Data Fetcher loads the series, a fixed SQL
recipe computes the figure, and the Citation Verifier checks it against the publisher. So an
injected instruction cannot make the agent print an invented number through the analysis path.

**Primary defense (already in place, CAN-22):** the planner can only emit plan steps that pass
`validate_plan`. That means registry tools only, typed arguments, real dates, vectors it looked
up, and no free-form SQL.

What the model *can* still influence, and what this task covers:

| Surface | Risk | Guard |
|---|---|---|
| The user's question | Text addressed to the agent ("ignore your instructions", fake system tags, "call submit_plan") | **Question screening.** Declined before any model call. |
| Plan objective, step descriptions, decline reason | Shown to users next to verified figures, so a description could carry an unverified number, a link or markup | **Pydantic v2 output validators** on `PlanDraft`, `DraftStep` and `DeclineArgs` |
| Discovery tool arguments | Malformed or hostile table IDs, coordinates and queries reaching the StatCan API | **Pydantic v2 argument models**, checked before any request |
| Discovery results | Indirect injection via publisher text (table and member names) | **Untrusted-result cleaning.** Hidden characters stripped, strings truncated, and the system prompt says it is data |
| Everything the model calls | No record of what it tried | **Tool-call audit trail** |

## Guards

All guards are in `candata_agent/supervisor/guardrails.py`, except the audit, which is in
`supervisor/audit.py`.

1. **Question screening** (`screen_question`). This is a narrow, secondary filter, so it is
   tuned for few false alarms. It looks for five categories:
   - instruction override
   - prompt extraction
   - role reassignment
   - fake conversation markup
   - tool hijack

   It also rejects hidden characters and questions over 2,000 characters. The Supervisor
   declines a flagged question with the category names and never echoes the matched text. All
   15 benchmark questions pass, and so do benign look-alikes such as "should I ignore the 2020
   census rules?".
2. **Output validators** (`check_planner_text`, used by the `Objective`, `StepDescription` and
   `DeclineReason` types).
   - **Rejected:**
     - figures: amounts, percentages, decimals, thousands separators, basis points
     - links
     - markup and template syntax: `<`, `>`, `` ` ``, `{{`, `%{`, `${`, `](`
     - hidden characters: control characters, zero-width, bidi overrides
     - text over the length limit (objective 200, step description 120, decline reason 400)
   - **Allowed:** years, vector IDs, table IDs and index bases such as `2002=100`.
   - On rejection, the planner gets the problems back as an error tool result and can fix
     them, the same loop `submit_plan` already used.
3. **Discovery arguments** (`SearchTablesArgs`, `FindMembersArgs`, `LookupSeriesArgs`):
   - extra fields are forbidden
   - table IDs use StatCan formats
   - coordinates have 1 to 10 numeric parts (the connector pads them)
   - search text is bounded and free of template characters
4. **Untrusted results** (`untrusted`): every string in a discovery result is NFKC-normalised,
   stripped of hidden characters and cut to 300 characters before it is sent to the model.
5. **Audit trail** (`ToolCallRecord`):
   - Every model tool call is recorded with its turn, tool, arguments (JSON, truncated),
     outcome (`ok`, `rejected`, `error` or `blocked`), detail and duration.
   - Each record is logged as one JSON line on the `candata_agent.audit` logger: INFO for
     `ok`, WARNING otherwise.
   - The Supervisor stores each question's trail under `scratchpad["planner_audit"]`, so it is
     checkpointed with the thread.
   - A screened question records one `question_screen` / `blocked` entry.
   - `PlanningError` carries the trail too, so a failed planning run still has it.
   - Validation errors sent back to the model never echo its input.

## Verification

- `tests/test_guardrails.py` has 34 tests:
  - Screening:
    - all 15 benchmark questions and 4 benign look-alikes pass
    - 10 attack strings are caught, each in its expected category
  - Output validators:
    - 4 accepted descriptions
    - 13 rejected ones, covering figures, links, markup, hidden characters, length and empty
      text
    - `PlanDraft` and `DraftStep` enforce them
  - Discovery arguments, including a path-like table ID, a bad coordinate and an extra field.
  - Cleaning of a hostile discovery result.
  - The planner loop (fake Messages API):
    - the audit records `ok`, `rejected`, `ok`, `rejected`, `ok` for a search, a bad lookup, a
      good lookup, a decline stating a figure, and a valid plan
    - a hostile table title reaches the model cleaned and truncated
    - rejected input isn't echoed
    - the system prompt carries the data-not-instructions rule
    - a failed planning run keeps its trail
  - The real graph, twice on one thread (guardrail 26):
    - an injected question is declined with no planner call and a `blocked` audit entry
    - a real question then runs and verifies
    - messages merge across the two runs
    - both audit trails are in the checkpoint history in order
- The existing Supervisor, UI and eval tests still pass. All demo and test plans satisfy the
  new validators.
- `scripts/verify.py` is clean: 419 passed.

## Known gaps / follow-ups

- **Not run against the live model.** The Claude planner hasn't been tested with these
  guards because there is no team `ANTHROPIC_API_KEY` yet. The guards are deterministic and
  tested with a fake Messages API.
- **Pattern screening can be evaded.** Rephrasing or other languages can get past it, which
  is why it is the secondary layer. The structural guarantees (validated plan, SQL recipes,
  verifier) don't depend on it.
- **Audit export.** The trail is logged and checkpointed. Shipping the `candata_agent.audit`
  log to a central store, and adding audit attributes to the CAN-25 spans, is follow-up work.
