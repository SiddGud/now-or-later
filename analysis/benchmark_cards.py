"""Rule cards for the lab benchmark: 50 people answer as the literature's model predicts.

NOT RESEARCH DATA. Each card gives one person the cutoffs to follow, so their answers match
the quasi-hyperbolic (beta-delta) model with the assumptions in model_prediction.py.
They play the links ending in #bench, which tags every row test = bench; the normal analysis
ignores those rows, and `--bench` analyses only them for the comparison.

Usage:
    py analysis/benchmark_cards.py [people]      (default 50)
Writes analysis/out/benchmark/cards.html (printable) and cards.csv.
"""
import math
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import model_prediction as M

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out", "benchmark")
BASE = "https://siddgud.github.io/now-or-later/"


def cutoff_gain(p, ctx, frame, V):
    # Later option is chosen when the later amount is at least this
    d30 = M.d30_for(p, ctx)
    b = M.beta_for(p, ctx)
    if frame == "A":
        return V / (b * d30)
    return V / d30


def describe_gain(c, lo, hi, unit):
    if c >= hi:
        return "always pick the SOONER option"
    if c <= lo:
        return "always pick the LATER option"
    return "pick the LATER option if it is %s or more, otherwise the sooner one" % unit(math.ceil(c))


def describe_cost(c, lo, hi, unit):
    # For a cost, postpone while the later amount is below the cutoff
    if c >= hi:
        return "always pick the LATER option (postpone)"
    if c <= lo:
        return "always pick TODAY"
    return "postpone (later option) only if the later amount is below %s, otherwise pick today" % unit(math.ceil(c))


def rupees(x):
    return "Rs %s" % format(int(x), ",")


def days(x):
    return "%d days" % int(x)


def card(i, p, rng):
    b = p["beta"]
    daily = p["d30"] ** (1.0 / 30.0)
    r = {"person": i, "beta": round(b, 3), "d30": round(p["d30"], 4)}
    lines_main = []
    for frame, label in [("A", "today vs in 30 days"), ("B", "in 30 days vs in 60 days")]:
        g = cutoff_gain(p, "gain", frame, 500)
        f = cutoff_gain(p, "friend", frame, 500)
        lo_ = cutoff_gain(p, "loss", frame, 500)
        h = cutoff_gain(p, "health_gain", frame, 20)
        r["%s_gain" % frame] = round(g, 1)
        r["%s_friend" % frame] = round(f, 1)
        r["%s_loss" % frame] = round(lo_, 1)
        r["%s_health" % frame] = round(h, 1)
        lines_main.append(("Money for you, %s" % label, describe_gain(g, 500, 1250, rupees)))
        lines_main.append(("Money for your friend, %s" % label, describe_gain(f, 500, 1250, rupees)))
        lines_main.append(("Rs 500 fine, %s" % label, describe_cost(lo_, 500, 1250, rupees)))
        lines_main.append(("Headache-free days, %s" % label, describe_gain(h, 20, 80, days)))
    # Hidden-zero nudge (Magen et al. 2008): the "Rs 0" wording halves the present bias
    nz_std = 2000.0 / (b * p["d30"])
    nz_hz = 2000.0 / (((1.0 + b) / 2.0) * p["d30"])
    r["nudge_standard"] = round(nz_std, 1)
    r["nudge_hiddenZero"] = round(nz_hz, 1)
    lines_main.append(("Rs 2000 today vs more in 30 days, plain wording", describe_gain(nz_std, 2000, 5000, rupees)))
    lines_main.append(("Same, but the options mention 'Rs 0'", describe_gain(nz_hz, 2000, 5000, rupees)))
    # Classic pair
    near_later = b * daily ** 7 * 1100 > 1000
    far_later = daily ** 7 * 1100 > 1000
    lines_main.append(("Rs 1000 today vs Rs 1100 in 1 week", M.pick(near_later, "Rs 1100 in 1 week", "Rs 1000 today")))
    lines_main.append(("Rs 1000 in 4 weeks vs Rs 1100 in 5 weeks", M.pick(far_later, "Rs 1100 in 5 weeks", "Rs 1000 in 4 weeks")))
    # Anchoring (Tversky & Kahneman 1974): own amount, pulled toward the anchor seen
    base = float(np.exp(rng.normal(math.log(9000), 0.35)))
    hi_amt = int(round(min(100000, max(5000, base * 1.3)) / 500.0) * 500)
    lo_amt = int(round(min(100000, max(5000, base * 0.85)) / 500.0) * 500)
    r["anchor_high_amount"] = hi_amt
    r["anchor_low_amount"] = lo_amt
    lines_main.append(("Give up Rs 5,000 today for Rs 15,000 in 1 year?", M.pick(15000 >= hi_amt, "Yes", "No") + "; then type " + rupees(hi_amt)))
    lines_main.append(("Give up Rs 5,000 today for Rs 5,200 in 1 year?", M.pick(5200 >= lo_amt, "Yes", "No") + "; then type " + rupees(lo_amt)))
    # Type 1 thinking (Frederick 2005): more present bias, more gut answers
    t1 = int(min(5, max(0, round((1.0 - b) / 0.06))))
    r["type1_gut_answers"] = t1
    gut = ["race: 1", "sheep: 7", "Jerry: 30", "hole: 27", "Priya: savings account AND SIP"]
    right = ["race: 2", "sheep: 8", "Jerry: 29", "hole: 0", "Priya: savings account"]
    puzzle = []
    for j in range(5):
        if j < t1:
            puzzle.append(gut[j])
        else:
            puzzle.append(right[j])
    lines_main.append(("Brain teasers", "; ".join(puzzle)))
    lines_main.append(("Quick checks", "Rs 1000 today; Rs 100 in 30 days"))
    lines_main.append(("Everything else", "age 18 to 25, any other answers, no UPI ID"))
    # Proposal survey
    lines_prop = []
    pg = cutoff_gain(p, "gain", "A", 500)
    pf = cutoff_gain(p, "friend", "A", 500)
    pl = cutoff_gain(p, "loss", "A", 500)
    flu = cutoff_gain(p, "health_cost", "A", 10)
    r["prop_flu"] = round(flu, 1)
    lines_prop.append(("Money for you, today vs in 30 days", describe_gain(pg, 500, 1250, rupees)))
    lines_prop.append(("Money for your friend", describe_gain(pf, 500, 1250, rupees)))
    lines_prop.append(("Rs 500 fine", describe_cost(pl, 500, 1250, rupees)))
    lines_prop.append(("Ill for 10 days today vs more days in 30 days", describe_cost(flu, 10, 25, days)))
    lines_prop.append(("Rs 100 today vs Rs 110 tomorrow", M.pick(b * daily * 110 > 100, "Rs 110 tomorrow", "Rs 100 today")))
    lines_prop.append(("Rs 100 in 30 days vs Rs 110 in 31 days", M.pick(daily * 110 > 100, "Rs 110 in 31 days", "Rs 100 in 30 days")))
    lines_prop.append(("Quick check and the rest", "Rs 1000 today; any age, year and field; no UPI ID"))
    return r, lines_main, lines_prop


def html_rows(lines):
    out = []
    for q, a in lines:
        out.append("<tr><td>%s</td><td>%s</td></tr>" % (q, a))
    return "".join(out)


def main():
    n = 50
    if len(sys.argv) > 1:
        n = int(sys.argv[1])
    os.makedirs(OUT, exist_ok=True)
    rng = np.random.default_rng(7)
    M.RNG = np.random.default_rng(7)
    rows = []
    cards = []
    for i in range(1, n + 1):
        p = M.person()
        r, lm, lp = card(i, p, rng)
        rows.append(r)
        cards.append(
            "<section><h2>Person %d</h2>"
            "<p class=meta>Model: beta = %.2f, 30-day factor = %.3f</p>"
            "<h3>Main survey: <a href='%s#bench'>%s#bench</a></h3><table>%s</table>"
            "<h3>Short survey: <a href='%sproposal.html#bench'>%sproposal.html#bench</a></h3><table>%s</table></section>"
            % (i, p["beta"], p["d30"], BASE, BASE, html_rows(lm), BASE, BASE, html_rows(lp)))
    pd.DataFrame(rows).to_csv(os.path.join(OUT, "cards.csv"), index=False)
    page = ("<!doctype html><html><head><meta charset=utf-8><title>Benchmark rule cards</title><style>"
            "body{font-family:Arial,sans-serif;max-width:820px;margin:24px auto;padding:0 16px;color:#1c1b1a}"
            "section{border:1px solid #ccc;border-radius:6px;padding:14px 16px;margin:0 0 18px;break-inside:avoid;page-break-after:always}"
            "h1{font-size:22px}h2{margin:0 0 4px;font-size:18px}h3{font-size:14px;margin:14px 0 6px}"
            "table{border-collapse:collapse;width:100%;font-size:13px}td{border-top:1px solid #e4e2de;padding:5px 6px;vertical-align:top}"
            "td:first-child{width:42%;color:#555}.meta{color:#777;font-size:12px;margin:0}"
            "</style></head><body><h1>Benchmark rule cards (not research data)</h1>"
            "<p>Each person opens both links on their own phone and answers every question by their card. "
            "The questions come in random order: find the matching row each time. Links ending in #bench keep these answers "
            "out of the real data.</p>" + "".join(cards) + "</body></html>")
    with open(os.path.join(OUT, "cards.html"), "w", encoding="utf-8") as f:
        f.write(page)
    print("Wrote %d cards to %s" % (n, OUT))


if __name__ == "__main__":
    main()
