# CAN-55 case study: manual-research timing protocol

**Status: protocol only (2026-11-25).** No manual research has been timed. No result in this
repository supports the "4 hours" in the CAN-55 task title. This file says how to measure it. An
AI assistant cannot supply these timings, and the AI-played sessions do not count.

## Purpose

Measure how long a person takes to answer benchmark questions from the official Statistics Canada
and Bank of Canada websites, and whether the answer is right and traceable. The result is the
manual side of the comparison.

## Who

- Two or three people who work with data but did not build this project.
- They are not shown the expected answers or the agent's answers.
- Their names are not published. The report says "participant A", "participant B" and so on.

## Which questions

A sample of the 15 benchmark questions in `collaboration/benchmarks/gta_ground_truth_v1.json`,
chosen before the sessions start and never changed after:
- GT-01 (Toronto two-bedroom rent in the October 2025 survey, and the change from 2024)
- GT-05 (Toronto housing starts in 2025, compared with 2024)
- GT-12 (Toronto shelter prices against overall prices, August 2026, year over year)

Each participant answers the same questions, in a different order.

## Rules

- Allowed: the Statistics Canada and Bank of Canada websites and a spreadsheet.
- Not allowed: AI assistants, the CanData tools, or asking someone who has the answer.
- The clock starts when the participant finishes reading the question.
- The clock stops when the participant has written a figure with its table, vector and reference
  period.
- A participant may give up. Record the time and mark the question "not answered".
- Statistics Canada's service is unavailable between 00:00 and 08:30 ET. Run sessions outside
  that window.

## What to record

| Field | Example |
|---|---|
| Participant | A |
| Question | GT-05 |
| Time to a cited figure | minutes and seconds |
| Steps taken | tables opened, filters set |
| Figure given | value, table, vector, period |
| Matches the ground truth within tolerance | yes / no / not answered |
| Difficulty noted | free text |

## What to report

- For each question: the median and the range of the times, and how many answers matched.
- The same measures for the agent on the same questions (see the user-testing file and the
  evaluation file).
- The number of participants and what they do. With two or three people, say plainly that the
  sample is small.

## If it cannot be done

If no one can be timed before publishing, the report drops "4 hours" and compares only what has
been measured: the agent against the baseline arms.
