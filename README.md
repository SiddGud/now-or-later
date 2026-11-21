# Now or Later?

A cross-contextual study of the time-discounting paradox and of inconsistencies in time valuation.
Neuroeconomics, IIIT Hyderabad, Team 6: Siddhant Gudwani (2024102042) and Yogansh (2024101006). Supervised by Prof. Kavita Vemuri, November 2026.

**Final report:** [report/Now_or_Later_Final_Report.pdf](report/Now_or_Later_Final_Report.pdf)

## The surveys

| Survey | Link | What it measures |
|---|---|---|
| Main | [siddgud.github.io/now-or-later](https://siddgud.github.io/now-or-later/) | The same 30-day wait starting today or in 30 days, in four contexts (money gain, fine, healthy days, money for a friend), with six adaptive questions each. It also has the classic reversal pair, a hidden-zero nudge, an anchor, five reflection puzzles and a timestamp on every tap. About 8 minutes. |
| Short | [siddgud.github.io/now-or-later/proposal.html](https://siddgud.github.io/now-or-later/proposal.html) | The design from our proposal, word for word: gain, fine, flu and friend (today vs 30 days), the ₹100 today vs ₹110 tomorrow pair, and one dominance check. About 2 minutes. Used as a replication sample. |

Responses were collected from 5 to 15 November 2026: 215 unique responses, of which 188 were analysed (123 main, 65 short).

## Folders

| Folder | Contents |
|---|---|
| `index.html`, `proposal.html` | The two survey apps (single-file HTML, served by GitHub Pages from the repository root) |
| [`backend/`](backend/) | Google Apps Script that writes each response to the Google Sheet |
| [`data/`](data/) | Cleaned responses, one row per response, with personal identifiers removed. Start here to look at the data. |
| [`analysis/`](analysis/) | Python scripts for every result in the report |
| [`results/`](results/) | Output of those scripts: reports, tables and figures |
| [`report/`](report/) | The final report PDF, its figures and its source |
| [`docs/`](docs/) | Design notes (`PROJECT_CONTEXT.md`) and deployment steps (`SETUP.md`) |
| [`tests/`](tests/) | Automated playthroughs of both surveys (Playwright) |

## Reproducing the results

The raw Sheet export contains UPI IDs, so it is not in this repository (`.gitignore` blocks it). With the export saved as `responses.csv`:

```
py -m pip install pandas scipy matplotlib statsmodels
py analysis/analyze.py responses.csv           # main survey      -> analysis/out/
py analysis/analyze_proposal.py responses.csv  # short survey     -> analysis/out/proposal/
py analysis/final.py responses.csv             # both surveys     -> analysis/out/final/
py analysis/report_assets.py responses.csv     # data/ files and report/figures/
npm install && node report/source/render.js    # report/Now_or_Later_Final_Report.pdf
```

`npm test` runs the survey playthroughs.
