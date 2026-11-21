# Results

Made from the responses received from 5 to 15 November 2026 (main survey: 123 analysed; short survey: 65 analysed).
These files hold only summary numbers and random respondent ids, never UPI IDs.

- `main/`: the main survey (index.html), from `py analysis/analyze.py responses.csv`. Start with `main/report.txt`.
- `short/`: the short survey (proposal.html), from `py analysis/analyze_proposal.py responses.csv`. Start with `short/report.txt`.
- `combined/`: analyses that use both surveys (sample flow, k per context with intervals, sign effect, effect sizes, question order, trait vs state), from `py analysis/final.py responses.csv`.

To refresh them, download the Sheet as CSV, rerun the three commands, and copy `analysis/out/`, `analysis/out/proposal/` and `analysis/out/final/` here.
