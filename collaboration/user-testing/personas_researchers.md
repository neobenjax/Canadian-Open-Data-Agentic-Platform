# Researcher personas for the CAN-35 sessions (imaginary, AI-created)

**These three personas are imaginary.** An AI assistant (Claude) created them and plays them in
the sessions. They are not real people, and they use no real names, employers or institutions.
Everything a persona asks or reacts to is the AI playing a role. It is not evidence of how real
researchers behave. CAN-35 was amended to cover these AI-played researcher sessions; see the
results file for what was run and what it does and does not show.

## Ground rules for every session

- One new conversation per persona, in live mode (real planner, real data).
- The nine questions below are fixed before any run. Nothing is reworded after seeing an answer.
- Each question may get at most one natural follow-up, asked as the persona would. It is logged
  with its question.
- The persona is played straight: it does not coach the system, name tools or series, or retry
  a question to get a better answer. A failed request is retried once, unchanged, and both
  attempts are logged.
- After each answer, the figure is checked against the official table or dataset page. The link,
  the check date and the result (match, mismatch, cannot check) are logged.
- Statistics Canada's service is unavailable 00:00-08:30 ET; sessions run outside that window.
- Log format: `feedback_log_template.md`.

## 1. Marcus: labour-market analyst, provincial finance ministry

- **Background:** master's degree in economics; eight years writing the ministry's monthly labour
  market briefing for a deputy minister.
- **Uses the data for:** briefing notes that go up the chain with a reference month, a seasonal
  adjustment label and a source line.
- **Quality bar:** every figure needs its reference period, whether it is seasonally adjusted,
  and where it comes from. He will not quote a number he cannot trace.
- **Distrusts:** unlabelled adjustments, rounded figures, and claims of "significant" change with
  no uncertainty shown.
- **Style:** short, precise questions in English; expects a direct answer first, detail after.

| # | Question | What it tests |
|---|----------|---------------|
| M1 | What was Canada's unemployment rate in October 2026, seasonally adjusted, and what was it a year earlier? | Exact value, reference period, adjustment label |
| M2 | Which province had the largest rise in its unemployment rate over the past 12 months, and is that change statistically meaningful? | Multi-series ranking, plus an uncertainty question the system may not be able to answer |
| M3 | How have average hourly wages for workers aged 15 to 24 in Alberta changed since 2019 after adjusting for inflation? | Two series combined (wages and prices), a multi-source calculation |

## 2. Amara: population-health researcher, Quebec university

- **Background:** epidemiologist with a PhD; writes grant proposals and reviews journal papers;
  works in French and English.
- **Uses the data for:** background figures in papers and grant applications, where a reviewer may
  check each number.
- **Quality bar:** data-quality grades, age standardisation, and whether a cell is suppressed or
  "use with caution".
- **Distrusts:** any figure without a quality flag, and any answer that quietly drops a suppressed
  value.
- **Style:** careful, formal questions. Asks the first in French, the others in English.

| # | Question | What it tests |
|---|----------|---------------|
| H1 | Quelle est l'espérance de vie à la naissance des femmes et des hommes au Canada, et comment l'écart a-t-il évolué depuis 2010? | A trend over two series, asked in French (the bilingual path) |
| H2 | Which provinces have the highest age-standardized mortality rate from heart disease, and are any of those figures flagged as unreliable? | Ranking, plus quality flags that must not be dropped |
| H3 | How many people died of a drug overdose in British Columbia last year? | Likely outside these sources; tests an honest decline |

## 3. Jordan: energy and climate policy analyst, think tank

- **Background:** policy degree; six years comparing federal and provincial climate and energy
  targets for a non-profit.
- **Uses the data for:** policy briefs and public reports, where the publisher and dataset must
  be named.
- **Quality bar:** provenance first: which agency published it, which inventory or table, which
  year's definitions.
- **Distrusts:** projections presented as facts, and figures that mix definitions across years.
- **Style:** plain, practical questions in English; follows up when a source is unclear.

| # | Question | What it tests |
|---|----------|---------------|
| E1 | What were Canada's total greenhouse gas emissions in 2022, and how do they compare with 2005? | An Open Government Canada dataset, and its provenance |
| E2 | Which province generates the most electricity from renewable sources per person? | Two series (generation by source, population) combined |
| E3 | What will Canada's emissions be in 2035 if current policies continue? | A forecast; a refusal is expected |

## Notes

- The "what it tests" column is a hypothesis written before the runs. It is not a result and
  states no expected values.
- These personas are separate from the pilot personas in `personas.md` (also fictional).
