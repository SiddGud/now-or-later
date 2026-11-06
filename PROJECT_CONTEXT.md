# Project context: "Now or Later?" survey app

## Who / what
- Course: Neuroeconomics, IIIT Hyderabad. Team 6: Siddhant Gudwani and Yogansh.
- Project title: "Cross-contextual analysis of the time discounting paradox through a behavioral economic study and mapping the inconsistencies w.r.t time valuation."
- Deliverable: a mobile-first web survey app ("Now or Later?") that collects intertemporal choices and saves them to a Google Sheet, plus a later analysis.
- Prof's requirement: include behavioural economics concepts (framing, nudges, heuristics, anchoring) and link to neuroeconomics (Type 1 / Type 2 thinking from class slides, dual-system model).
- At least one other team is doing a similar "immediate vs future rewards" survey, so the app must be clearly better (precision, decision times, randomisation, retention).

## Files already built (in this folder)
- index.html: the complete single-page app (vanilla HTML/CSS/JS, no build step). Hosted on GitHub Pages.
- Code.gs: Google Apps Script backend. Container-bound to a Google Sheet, deployed as a web app (Execute as me, Anyone). doPost appends one row per response to the "responses" tab, adding columns for new keys.
- SETUP.md: deployment and lottery instructions.
- The app was tested end to end with Playwright on a 390x844 viewport: no JS errors, 84 fields posted, report card renders. tests/playthrough.js (npm test) repeats this 80 times.
- analysis/analyze.py runs the planned analysis on the exported Sheet CSV.

## Research design (do not change without a reason)
Every element must tie to the project title. Nothing should feel "added on".

1. Contexts (cross-contextual): money gain, money loss (fine), health (headache-free days), choosing for a close friend.
2. Paradox: each context is measured twice:
   - Block A: today vs 30 days
   - Block B: 30 days vs 60 days
   Same 30-day gap, only the start moves. k(A) - k(B) = present bias per context. Allows beta-delta (Laibson 1997; McClure et al. 2004) per context.
3. Classic flip pair: "₹1000 today vs ₹1100 in 1 week" (start) and "₹1000 in 4 weeks vs ₹1100 in 5 weeks" (near end). flipped = chose today in first and later in second.
4. Adaptive titration (adjusting-amount; Du, Green & Myerson 2002; Koffarnus & Bickel 2014): 5 bisection trials per task. Sooner amount fixed (₹500, or 20 days for health). Later amount bisects between lo and hi.
   - Gain/friend: lo 500, hi 1250, step 5. Choose later -> hi = L, else lo = L.
   - Loss: lo 500, hi 1250. Choose later (postpone) -> lo = L, else hi = L.
   - Health: lo 20, hi 50 days, step 1.
   - Indifference = (lo+hi)/2; k = (ind/V - 1)/30. Censored "high" if pinned at the top of the range (never chose later; for loss, always postponed), "low" if pinned at the bottom.
5. Framing nudge (hidden zero; Magen, Dweck & Gross 2008): one extra gain task, ₹2000 today vs later (2000 to 5000). Random group: standard labels vs "₹2000 today and ₹0 in 30 days" / "₹0 today and ₹X in 30 days".
6. Anchoring (Tversky & Kahneman 1974): random high (₹15,000) or low (₹5,200) yes/no question, then "smallest amount in 1 year to give up ₹5,000 today" (5,000 to 1,00,000).
7. Type 1 / Type 2 (Frederick 2005 CRT; Toplak et al. 2014), money/time themed, placed LAST so they cannot prime choices:
   - p1 save together (correct 4, intuitive 9)
   - p2 savings double, half (9, intuitive 5)
   - p3 20% + 20% off (36, intuitive 40)
   - p4 stock -50% then +75% (7000, intuitive 10000)
   - p5 conjunction fallacy, Priya (correct: "savings account"; intuitive: "...and invests in a SIP")
   type1Score = count of intuitive answers (0-5).
8. Decision time (ms) on every tap. Framed around the paradox: are people slower (more torn) when "today" is an option (McClure 2004 conflict)? Evidence accumulation / court-trial model from Lecture 1.
9. Controls: trust in future payment (Kidd et al. 2013), stress (Starcke & Brand 2012), monthly spending band, prior knowledge of the topic, "filled another now-vs-later survey this week", who you are (IIIT-H student / other student / working / other), age 18-70.
10. Validity: procrastination (1-5), regret spending (1-5), optional free text "how did you decide".
11. Attention checks: "₹1000 today vs ₹10 in 60 days" (Block A), "fine ₹100 in 30 days vs ₹5000 in 60 days" (Block B).
12. Random assignment in code: block order (AB/BA), nudge group, anchor group. Context order shuffled inside each block.

Deliberately dropped (do NOT re-add): stranger condition, branch/year/gender, 3-second timer manipulation, separate lottery form, 4-digit code, form-level question shuffle.

## Rewards and ethics
- 5 winners: 1 person gets one of their own choices paid for real via UPI (random lottery incentive; Charness, Gneezy & Halladay 2016), drawn only from A_gain or B_gain trials, so max ₹1,250. 4 more get ₹200 Amazon vouchers.
- Rewards never depend on answers and never offer a now-vs-later choice.
- Confidential, not anonymous (optional UPI ID at the end, deleted after payment). 18+ only.
- One play per device (localStorage); #test in the URL bypasses this for testing.

## Style constraints
- Simple, short English on screen. One question per screen. Mobile first. No emojis in the UI.
- Don't reveal the hypothesis in the UI (avoid "time discounting", "patience test" before the end).
- Code style: no ternary operators, no arrow functions or lambdas, one-line comments placed above the line (not to the right).
- Vanilla JS, single index.html, no frameworks, no build step.

## Data columns (sent to the Sheet)
id, order, nudgeGroup, anchorGroup, startedAt, test, consent, age, describes, spending, priorKnowledge, otherSurvey, stress, trust, flipNear(+_rt), {A,B}_{gain,loss,health,friend}_{ind,k,censored,meanRT}, attn1, attn2, nudge_{ind,k,censored,meanRT}, anchorYes, anchorAmount, flipFar, procrast, regret, comment, p1..p5 (+_rt), upi, type1Score, correctScore, flipped, attentionFail, finishedAt, totalSec, device, trialsJSON (every tap: step, offer, choice, rt), receivedAt.

## Planned analysis (for later)
- H1 paradox: % flipped; Wilcoxon k(A) vs k(B) per context.
- H2 contexts: Friedman across contexts, pairwise Wilcoxon (Holm).
- H3 trait vs state: Spearman matrix of k across contexts.
- H4 nudge: Mann-Whitney nudge_k by nudgeGroup.
- H5 anchoring: Mann-Whitney anchorAmount by anchorGroup.
- H6 Type 1: Spearman type1Score vs log k; logistic regression type1Score -> flipped.
- H7 decision time: RT for today-vs-later vs later-vs-later; RT peaks near the switch point.
- Regression: log k ~ context + frame + type1Score + trust + stress + spending + priorKnowledge + otherSurvey + order.
- Main figures: discount curve per context, inconsistency heatmap (context x framing/anchor/Type 1), beta-delta per context.
- Exclusions: attentionFail = yes, totalSec < 120, priorKnowledge/otherSurvey as sensitivity checks.

## Version 2 (from 6 November 2026)
Every response now has a `version` column (85 fields). Rows without it are v1.
- 6 bisection steps per task instead of 5 (finer switch points).
- Health task range 20 to 80 days (was 20 to 50), because about a quarter of v1 respondents hit the top.
- Second attention check reworded to an explicit instruction: 'Quick check: to show you are reading, tap "₹100 in 30 days".' The options are unchanged. In v1, 21% failed the old wording.
- Unchanged: all other wording, money ranges, delays, the k formula, groups and the report card. k is on the same scale in v1 and v2, so they can be pooled with version as a covariate, or analysed separately: `py analysis/analyze.py responses.csv v2`.

## Version 3 (from 7 November 2026)
New column `flipOrder` (86 fields). Rows without it asked the near pair first.
- The two classic pairs are in random order: `nearFirst` (today vs 1 week at the start, 4 vs 5 weeks near the end) or `farFirst` (the reverse). In v1 and v2 the near pair always came first, so order and fatigue were confounded with present bias. In v1 and v2, reverse flips outnumbered classic ones (25 vs 12).
- Brain teasers p1 to p4 replaced, because about 85% of people solved the v1/v2 items, leaving type1Score almost no variation. New items, as [gut answer, correct answer]:
  p1 race, pass second place [1, 2]; p2 farmer, 15 sheep, all but 8 die [7, 8] (both CRT-2, Thomson & Oppenheimer 2016);
  p3 Jerry, 15th highest and 15th lowest [30, 29] (Toplak et al. 2014); p4 dirt in a 3x3x3 m hole [27, 0] (CRT-2).
  p5 (Priya) unchanged. type1Score from v1/v2 and v3 measure different items: analyse H6 on v3 separately (the script does).
- Analysis additions: exploratory McNemar test (classic vs reverse flips, overall and by flipOrder); one-sided H5 test, since H5 is directional.
