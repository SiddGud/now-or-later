# Now or Later? Setup (about 20 minutes)

## 1. Backend (Google Sheet)
1. Create a new Google Sheet named "Now or Later responses".
2. Extensions -> Apps Script. Delete the sample code and paste all of Code.gs. Save.
3. Deploy -> New deployment -> gear icon -> Web app.
   - Execute as: Me
   - Who has access: Anyone
4. Deploy -> Authorize -> Advanced -> Go to project -> Allow.
5. Copy the Web app URL (ends with /exec). Open it in a browser: it should say "Backend is running."

## 2. Frontend (index.html)
1. Open index.html. Near the top, replace:
   - PASTE_YOUR_WEB_APP_URL_HERE -> your /exec URL
   - [DATE] -> the draw date
   Until ENDPOINT starts with https:// the app sends nothing (responses wait in the phone's localStorage).
2. Host it free on GitHub Pages (this folder is already a git repo on branch main):
   - github.com -> New repository (public), e.g. "now-or-later". Do not add a README.
   - In this folder: `git remote add origin https://github.com/YOURNAME/now-or-later.git` then `git push -u origin main`
   - Settings -> Pages -> Source: Deploy from a branch -> main / (root) -> Save
   - After about 1 minute the link is https://YOURNAME.github.io/now-or-later/
   - Note: everything in the repo is public, including PROJECT_CONTEXT.md (the hypotheses). Never commit the Sheet CSV (.gitignore blocks *.csv).

## 3. Test before sharing
- Automated: `npm install`, `npx playwright install chromium`, then `npm test` (80 full plays on a 390x844 phone; takes about 8 minutes).
- Open the link with #test at the end (e.g. .../now-or-later/#test). This skips the "already played" lock so you can play many times. These rows get test = yes.
- Play 3-4 times on your phone. Check that a new row appears in the Sheet each time.
- Then delete those test rows from the Sheet (analyze.py also drops test = yes).

## Analysis
- Sheet -> File -> Download -> CSV (keep it outside the repo, it has UPI IDs).
- `py -m pip install pandas scipy matplotlib statsmodels`
- `py analysis/analyze.py path/to/responses.csv` -> results and figures in analysis/out/ (report.txt has everything).

## 4. Lottery (keep this rule written down)
- Draw 1 winner at random from rows with a UPI ID and attentionFail = no.
- Open their trialsJSON, pick at random one trial with step A_gain or B_gain, and pay what they chose:
  - choice "sooner" -> ₹500 (A_gain: today, B_gain: in 30 days)
  - choice "later" -> the offer amount (A_gain: in 30 days, B_gain: in 60 days)
- Then draw 4 more for the ₹200 Amazon vouchers.
- Delete the upi column after paying.

## What each column means
- order (AB/BA), nudgeGroup (standard/hiddenZero), anchorGroup (high/low): random groups
- A_* = today vs 30 days, B_* = 30 vs 60 days; contexts gain, loss, health, friend
- *_ind = switch point (indifference amount), *_k = (ind/V - 1)/30, *_meanRT = mean decision time in ms
- *_censored = "high" if the switch point is pinned at the top of the range (k is a lower bound; gain/friend/health/nudge: never chose later; loss: always postponed), "low" if pinned at the bottom (k is an upper bound), else "no"
- test = yes for plays opened with #test
- duplicate ids can appear if a retry resends a response; keep the first (analyze.py does this)
- nudge_* = hidden-zero task, compare by nudgeGroup
- anchorAmount = anchoring result, compare by anchorGroup
- flipNear/flipFar/flipped = classic preference reversal
- p1-p5 = puzzles; type1Score = number of quick intuitive answers (0-5); correctScore = correct (0-5)
- attentionFail = yes -> remove this response
- trialsJSON = every single tap with offer, choice and decision time (ms)

## Short proposal survey (proposal.html)
A 3-minute survey that follows the project proposal exactly: gain, fine, flu and friend (today vs 30 days, 6 adaptive questions each, random order), one dominance check, and the near/far pair (₹100 today vs ₹110 tomorrow; day 30 vs day 31), one at the start and one at the end in random order.
- Link: https://siddgud.github.io/now-or-later/proposal.html
- Same Sheet and prize draw. Rows have `survey = proposal`; `analysis/analyze.py` skips them.
- Analyse: `py analysis/analyze_proposal.py responses.csv` (writes to analysis/out/proposal/).
- Test: `node tests/proposal.js`
