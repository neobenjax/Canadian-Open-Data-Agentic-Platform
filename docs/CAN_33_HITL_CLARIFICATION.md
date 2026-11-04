# CAN-33: Human-in-the-loop `interrupt()` for ambiguous members

When a question's term matches more than one member of a table dimension, the agent no longer
picks one silently. It pauses with LangGraph's `interrupt()`, asks the user which one they mean,
and plans again with the answer. The guardrail 6 example is two members both named
"Smiths Falls, Ontario". Municipal and CMA boundaries are the same kind of problem.

**Stacked on #67 (CAN-43).** The clarification text goes through its output validators, and
every clarification call is in its audit trail.

## Where the interrupt fires, and why

There were two candidate trigger points:
- **At planning:** in `find_members` and `lookup_series`.
- **At fetch:** when the connector raises `StatCanAmbiguousMemberError`.

In the current graph, the fetcher loads series by **vector ID**, which is never ambiguous, and
nothing in the graph calls `resolve_coordinate`, the only place the connector raises
`StatCanAmbiguousMemberError`. So ambiguity can only arise while the planner chooses members,
and that's where the interrupt fires. If a fetch-by-name step is ever added, it should raise
into the same `human_clarification` node.

## Flow

```text
supervisor --plan--------------> data_fetcher / data_analyst ... --> citation_verifier --> END
           --clarification----> human_clarification --interrupt()-- (paused)
                                       ^-- Command(resume=<member>) --> supervisor (plans again)
```

1. **Planner** (`supervisor/planner.py`):
   - **Shared names are marked.** `find_members` marks every member whose name another member
     of the same dimension shares (`same_name_as_another_member`). The comparison ignores
     case, accents and spacing.
   - **Shared names are refused.** `lookup_series` refuses a coordinate that uses such a
     member until the user has chosen it. This is deterministic and doesn't depend on the
     model's judgment.
   - **Looser ambiguity is the model's call.** For cases like a municipality versus a CMA,
     the model calls the new `request_clarification` tool, with the term, table, dimension,
     member IDs and a question for the user.
   - **Options must be real.** They have to be members that `find_members` returned for that
     table and dimension, at least two and distinct. The term and question pass the CAN-43
     text validators.
   - **Planning again.** `plan(question, resolved=[...])` adds each choice to the prompt and
     allows only the chosen member.
2. **Supervisor** (`supervisor/node.py`):
   - It stores the request as `active_interrupt`, a `HITLInterrupt` of type
     `ambiguous_member`, and routes to `human_clarification`.
   - The model call happens in the Supervisor and the pause in a separate node. LangGraph
     re-runs an interrupted node from the start on resume, so this split means resuming never
     repeats or bills the planner call.
3. **`human_clarification` node**:
   - It calls `interrupt(payload)`, with the question, term, table, dimension and options.
   - The resume value can be:
     - a member ID (int or text)
     - an exact member name
     - a mapping with `member_id` or `name`
     - `cancel`
   - Anything else asks again, with an `error` in the payload. The planner isn't called again.
   - The choice is saved in `scratchpad["clarifications"]` and the Supervisor plans again.
4. **Limits:**
   - At most 3 clarifications per question; after that the question is declined.
   - Asking a new question instead of answering replaces the pending clarification.
   - Cancelling declines the question.
5. **UI** (`ui/stream.py`, `apps/agent-ui/app.py`):
   - `stream_question` yields `ClarificationNeeded` when the run pauses.
   - `stream_question(..., resume=answer)` continues it.
   - The page shows the question as a radio list with Continue and Cancel buttons.

## Verification

- `tests/test_clarification.py` has 11 tests:
  - **Answer matching:** by ID or exact name only; bools, floats, partial names and unknown
    IDs are refused.
  - **Planner:**
    - same-name members are marked, even with irregular spacing
    - `lookup_series` refuses them
    - a clarification offering an undiscovered member is refused
    - a valid one ends planning
    - after a choice, only the chosen member is accepted
  - **Graph:**
    - a question pauses
    - a wrong answer asks again without re-planning
    - the right answer plans again with the choice and verifies
    - messages and audit merge across the runs
    - a fork from the paused checkpoint with the other member also verifies (guardrail 26:
      several invocations on one thread, checkpoint history, and fork)
  - **Edge cases:** cancel, a new question replacing an unanswered clarification, and the
    3-clarification limit.
  - **UI stream:** a `ClarificationNeeded` event, then a resumed run showing only its own
    messages.
- **Page, headless:** Streamlit `AppTest` with a scripted planner and fake sources showed the
  question, the two Smiths Falls options and a verified result after Continue. The planner
  received the user's choice.
- `scripts/verify.py` is clean: 430 passed.
- The test also caught a real bug: `find_members` didn't match member names with irregular
  spacing. Names are now compared with collapsed whitespace.

## Known gaps / follow-ups

- **Not run against the live model.** It needs `ANTHROPIC_API_KEY`. Whether Claude asks at the
  right times for looser ambiguity, like a municipality versus a CMA, is judgment that only a
  live run shows. The same-name case is enforced in code.
- **Page layout.** The radio, Continue and Cancel controls are a working baseline in
  `app.py`; Yassir's layout B rewrite should keep the `ClarificationNeeded` and `resume=`
  contract.
- **Other interrupt types.** `HITLInterrupt` also defines `confidentiality_suppressed`,
  `policy_exception` and `user_confirmation`; only `ambiguous_member` is raised so far.
