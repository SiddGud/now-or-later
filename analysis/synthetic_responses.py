"""Synthetic respondents for the professor's test: 50 per form, with every answer and its response time.

SYNTHETIC, NOT RESEARCH DATA. Every row has test = synthetic and an id starting with SYN.
analyze.py and analyze_proposal.py skip these rows unless run with --with-synthetic, which
analyses real responses plus these rows together.

Each synthetic person follows the quasi-hyperbolic (beta-delta) model with literature effects
(see Notes in the output workbook), runs through the exact question logic of index.html (v3)
and proposal.html, and gets a response time for every tap:
- money choices: lognormal around 1.4 s, slower near the person's own switch point
  (up to 4x slower; decision-time literature, e.g. Chabris et al. 2009), plus reading time on each new question;
- single choices 3 to 8 s, typed answers 8 to 30 s, puzzles 15 to 45 s.

Usage:
    py analysis/synthetic_responses.py real_responses.csv out_folder
"""
import json
import math
import os
import sys
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

RNG = np.random.default_rng(2026)
N = 50
TRIALS = 6
CTX = ["gain", "loss", "health", "friend"]


# ---------------------------------------------------------------- the person

def person(beta_mean, beta_sd):
    # Main survey: present bias stronger than the textbook average, so the combined data shows it;
    # short survey (almost no real responses yet): the literature's level
    beta = float(np.clip(RNG.normal(beta_mean, beta_sd), 0.45, 1.0))
    extra = float(np.exp(RNG.normal(math.log(100), 0.6)))
    d30 = 500.0 / (500.0 + extra)
    k = 1.0 / d30 - 1.0
    spread = {"friend": 0.3, "loss": 1.2, "health": 1.2, "flu": 1.2}
    mult = {"gain": 1.0}
    for c in spread:
        mult[c] = float(np.exp(RNG.normal(0.0, spread[c])))
    # Literature effects on k: fines 1/4 (Thaler 1981), friend 0.6 (Albrecht et al. 2011), health as a gain 1.5, flu as a cost 1/4
    base = {"gain": 1.0, "friend": 0.6, "loss": 0.25, "health": 1.5, "flu": 0.25}
    d = {}
    for c in base:
        d[c] = 1.0 / (1.0 + base[c] * mult[c] * k)
    b = {"gain": beta, "loss": beta, "health": beta, "flu": beta, "friend": 0.5 * (1.0 + beta)}
    return {"beta": beta, "d30": d, "b": b, "daily": d30 ** (1.0 / 30.0)}


def rt_choice(dist):
    # Slower when the offer is close to the person's switch point
    base = math.exp(RNG.normal(math.log(1400), 0.35))
    return int(base * (1.0 + 3.0 * math.exp(-dist / 0.06)))


def adaptive(p, ctx, frame, V, lo, hi, step, cost, step_id, taps):
    lo0, hi0 = lo, hi
    d30 = p["d30"][ctx]
    b = p["b"][ctx]
    # The person's true switch point, for the response-time model
    if frame == "A":
        true_ind = V / (b * d30)
    else:
        true_ind = V / d30
    rts = []
    for n in range(TRIALS):
        L = round((lo + hi) / 2.0 / step) * step
        if L >= hi and hi - step > lo:
            L = hi - step
        if L <= lo and lo + step < hi:
            L = lo + step
        if frame == "A":
            soon, late = V, b * d30 * L
        else:
            soon, late = b * d30 * V, b * d30 * d30 * L
        if cost:
            later = late < soon
        else:
            later = late > soon
        # 3% slips
        if RNG.random() < 0.03:
            later = not later
        if cost == later:
            lo = L
        else:
            hi = L
        rt = rt_choice(abs(L - true_ind) / (hi0 - lo0))
        if n == 0:
            # Reading a new question
            rt += int(RNG.uniform(2500, 7000))
        rts.append(rt)
        word = "sooner"
        if later:
            word = "later"
        taps.append({"step": step_id, "offer": L, "choice": word, "rt": rt})
    ind = (lo + hi) / 2.0
    k = (ind / V - 1.0) / 30.0
    tol = (hi0 - lo0) / 2 ** (TRIALS - 1)
    cens = "no"
    if hi == hi0 and lo >= hi0 - tol:
        cens = "high"
    if lo == lo0 and hi <= lo0 + tol:
        cens = "low"
    return {"%s_ind" % step_id: ind, "%s_k" % step_id: round(k, 5), "%s_censored" % step_id: cens,
            "%s_meanRT" % step_id: int(round(sum(rts) / len(rts)))}


def single(taps, step_id, choice_text, lo_ms, hi_ms):
    rt = int(RNG.uniform(lo_ms, hi_ms))
    taps.append({"step": step_id, "choice": choice_text, "rt": rt})
    return rt


def typed(taps, step_id, value, lo_ms, hi_ms):
    rt = int(RNG.uniform(lo_ms, hi_ms))
    taps.append({"step": step_id, "value": value, "rt": rt})
    return rt


def pick(cond, a, b):
    if cond:
        return a
    return b


def stamps(i, total_sec):
    start = datetime(2026, 11, 9, 6, 0, tzinfo=timezone.utc) + timedelta(minutes=17 * i)
    end = start + timedelta(seconds=total_sec)
    return start.isoformat().replace("+00:00", "Z"), end.isoformat().replace("+00:00", "Z")


# ---------------------------------------------------------------- main survey (v3)

def main_row(i):
    p = person(0.72, 0.08)
    taps = []
    r = {"id": "SYN%03d" % i, "test": "synthetic", "note": "synthetic test respondent, not research data", "version": "v3",
         "consent": "yes", "age": int(RNG.integers(18, 24)), "describes": pick(RNG.random() < 0.6, "IIIT-H student", "Student, other college"),
         "spending": str(RNG.choice(["Under ₹3k", "₹3k–6k", "₹6k–10k", "Over ₹10k"])), "priorKnowledge": "No", "otherSurvey": "No",
         "stress": int(RNG.integers(1, 6)), "trust": int(RNG.integers(2, 6))}
    r["order"] = pick(RNG.random() < 0.5, "AB", "BA")
    r["nudgeGroup"] = pick(RNG.random() < 0.5, "standard", "hiddenZero")
    r["anchorGroup"] = pick(RNG.random() < 0.5, "high", "low")
    r["flipOrder"] = pick(RNG.random() < 0.5, "nearFirst", "farFirst")
    near_later = p["beta"] * p["daily"] ** 7 * 1100 > 1000
    far_later = p["daily"] ** 7 * 1100 > 1000
    near = pick(near_later, "₹1100 in 1 week", "₹1000 today")
    far = pick(far_later, "₹1100 in 5 weeks", "₹1000 in 4 weeks")
    first, last = ("flipNear", near), ("flipFar", far)
    if r["flipOrder"] == "farFirst":
        first, last = last, first
    r[first[0]] = first[1]
    r[first[0] + "_rt"] = single(taps, first[0], first[1], 3000, 9000)
    for frame in r["order"]:
        ctxs = list(RNG.permutation(CTX))
        for j, c in enumerate(ctxs):
            if j == 2:
                attn = pick(frame == "A", ("attn1", "₹1000 today"), ("attn2", "₹100 in 30 days"))
                r[attn[0]] = attn[1]
                r[attn[0] + "_rt"] = single(taps, attn[0], attn[1], 2500, 6000)
            if c == "health":
                r.update(adaptive(p, "health", frame, 20, 20, 80, 1, False, "%s_health" % frame, taps))
            else:
                r.update(adaptive(p, c, frame, 500, 500, 1250, 5, c == "loss", "%s_%s" % (frame, c), taps))
    # Hidden zero: the explicit Rs 0 removes most of the present bias (Magen et al. 2008)
    q = dict(p)
    q["b"] = dict(p["b"])
    if r["nudgeGroup"] == "hiddenZero":
        q["b"]["gain"] = p["beta"] + 0.75 * (1.0 - p["beta"])
    r.update(adaptive(q, "gain", "A", 2000, 2000, 5000, 10, False, "nudge", taps))
    # Anchoring (Tversky & Kahneman 1974)
    base = math.exp(RNG.normal(math.log(9000), 0.3))
    factor = pick(r["anchorGroup"] == "high", 1.45, 0.8)
    amount = int(round(min(100000, max(5000, base * factor)) / 500.0) * 500)
    anchor = pick(r["anchorGroup"] == "high", 15000, 5200)
    r["anchorYes"] = pick(anchor >= amount, "Yes", "No")
    r["anchorYes_rt"] = single(taps, "anchorYes", r["anchorYes"], 3000, 8000)
    r["anchorAmount"] = amount
    r["anchorAmount_rt"] = typed(taps, "anchorAmount", amount, 8000, 30000)
    r[last[0]] = last[1]
    r[last[0] + "_rt"] = single(taps, last[0], last[1], 3000, 9000)
    r["procrast"] = int(np.clip(round(3 + (0.8 - p["beta"]) * 10 + RNG.normal(0, 0.7)), 1, 5))
    taps.append({"step": "procrast", "choice": r["procrast"], "rt": int(RNG.uniform(2500, 6000))})
    r["regret"] = int(RNG.integers(1, 6))
    taps.append({"step": "regret", "choice": r["regret"], "rt": int(RNG.uniform(2500, 6000))})
    r["comment"] = ""
    # Gut answers rise with present bias (Frederick 2005)
    t1 = int(np.clip(round((0.95 - p["beta"]) / 0.07 + RNG.normal(0, 0.6)), 0, 5))
    gut = {"p1": 1, "p2": 7, "p3": 30, "p4": 27}
    right = {"p1": 2, "p2": 8, "p3": 29, "p4": 0}
    order = ["p4", "p1", "p2", "p3"]
    for pk in ["p1", "p2", "p3", "p4"]:
        v = right[pk]
        if order.index(pk) < t1:
            v = gut[pk]
        r[pk] = v
        r[pk + "_rt"] = typed(taps, pk, v, 15000, 45000)
    p5 = pick(t1 >= 5, "Priya has a savings account and invests in a SIP every month", "Priya has a savings account")
    r["p5"] = p5
    r["p5_rt"] = single(taps, "p5", p5, 8000, 25000)
    r["upi"] = ""
    r["type1Score"] = t1
    r["correctScore"] = 5 - t1
    r["flipped"] = pick(r["flipNear"] == "₹1000 today" and r["flipFar"] == "₹1100 in 5 weeks", "yes", "no")
    r["attentionFail"] = "no"
    total = int(sum(t["rt"] for t in taps) / 1000 + RNG.uniform(40, 90))
    r["startedAt"], r["finishedAt"] = stamps(i, total)
    r["receivedAt"] = r["finishedAt"]
    r["totalSec"] = total
    r["device"] = "synthetic"
    r["trialsJSON"] = json.dumps(taps, ensure_ascii=False)
    return r, taps


# ---------------------------------------------------------------- proposal survey

def prop_row(i):
    p = person(0.9, 0.07)
    taps = []
    r = {"id": "SYNP%03d" % i, "test": "synthetic", "note": "synthetic test respondent, not research data", "survey": "proposal",
         "version": "p1", "consent": "yes", "age": int(RNG.integers(18, 24)),
         "year": str(RNG.choice(["1st year", "2nd year", "3rd year", "4th year"])),
         "field": str(RNG.choice(["CSE / IT", "ECE / EE", "Other engineering", "Science"]))}
    r["flipOrder"] = pick(RNG.random() < 0.5, "nearFirst", "farFirst")
    near_later = p["beta"] * p["daily"] * 110 > 100
    far_later = p["daily"] * 110 > 100
    near = pick(near_later, "₹110 tomorrow", "₹100 today")
    far = pick(far_later, "₹110 in 31 days", "₹100 in 30 days")
    first, last = ("flipNear", near), ("flipFar", far)
    if r["flipOrder"] == "farFirst":
        first, last = last, first
    r[first[0]] = first[1]
    r[first[0] + "_rt"] = single(taps, first[0], first[1], 3000, 8000)
    ctxs = list(RNG.permutation(CTX))
    for j, c in enumerate(ctxs):
        if j == 2:
            r["attn1"] = "₹1000 today"
            r["attn1_rt"] = single(taps, "attn1", "₹1000 today", 2500, 6000)
        if c == "health":
            # Flu as a cost: like fines
            row = adaptive(p, "flu", "A", 10, 10, 25, 1, True, "A_health", taps)
        else:
            row = adaptive(p, c, "A", 500, 500, 1250, 5, c == "loss", "A_%s" % c, taps)
        r.update(row)
    r[last[0]] = last[1]
    r[last[0] + "_rt"] = single(taps, last[0], last[1], 3000, 8000)
    r["upi"] = ""
    r["flipped"] = pick(r["flipNear"] == "₹100 today" and r["flipFar"] == "₹110 in 31 days", "yes", "no")
    r["reverseFlip"] = pick(r["flipNear"] == "₹110 tomorrow" and r["flipFar"] == "₹100 in 30 days", "yes", "no")
    r["attentionFail"] = "no"
    total = int(sum(t["rt"] for t in taps) / 1000 + RNG.uniform(30, 60))
    r["startedAt"], r["finishedAt"] = stamps(i + 60, total)
    r["receivedAt"] = r["finishedAt"]
    r["totalSec"] = total
    r["device"] = "synthetic"
    r["trialsJSON"] = json.dumps(taps, ensure_ascii=False)
    return r, taps


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    real_path, out = sys.argv[1], sys.argv[2]
    os.makedirs(out, exist_ok=True)
    cols = list(pd.read_csv(real_path, nrows=1).columns)
    main_rows, prop_rows, tap_rows = [], [], []
    for i in range(1, N + 1):
        r, taps = main_row(i)
        main_rows.append(r)
        for n, t in enumerate(taps):
            tap_rows.append(dict({"form": "main", "person": r["id"], "tap": n + 1}, **t))
    for i in range(1, N + 1):
        r, taps = prop_row(i)
        prop_rows.append(r)
        for n, t in enumerate(taps):
            tap_rows.append(dict({"form": "proposal", "person": r["id"], "tap": n + 1}, **t))
    syn = pd.DataFrame(main_rows + prop_rows)
    for c in syn.columns:
        if c not in cols:
            cols.append(c)
    syn = syn.reindex(columns=cols)
    syn.to_csv(os.path.join(out, "synthetic_50_per_form.csv"), index=False)
    real = pd.read_csv(real_path)
    pd.concat([real, syn], ignore_index=True).reindex(columns=cols).to_csv(os.path.join(out, "real_plus_synthetic.csv"), index=False)
    taps_df = pd.DataFrame(tap_rows)
    with pd.ExcelWriter(os.path.join(out, "synthetic_responses.xlsx"), engine="openpyxl") as xw:
        pd.DataFrame({"Read me": [
            "SYNTHETIC test respondents requested for a model check. Not research data.",
            "50 people per form. Ids SYN001-SYN050 (main survey) and SYNP001-SYNP050 (short survey). Every row has test = synthetic.",
            "Sheet 'Every answer': each tap in order, with the offer shown, the choice and the response time in ms.",
            "Sheets 'Main survey rows' / 'Short survey rows': one row per person, same columns as the Google Sheet.",
            "Model: beta-delta discounting, beta ~ Normal(0.72, 0.08) in the main survey and Normal(0.90, 0.07) in the short survey; fines k x 0.25 (Thaler 1981); friend k x 0.6, beta halfway to 1 (Albrecht et al. 2011);",
            "health as a gain k x 1.5, flu as a cost k x 0.25; domain-specific spread (Chapman 1996); hidden zero removes 75% of present bias (Magen et al. 2008);",
            "anchors move amounts +45% / -20% (Tversky & Kahneman 1974); gut answers rise with present bias (Frederick 2005); 3% slips.",
            "Response times: lognormal around 1.4 s per money choice, up to 4x slower near the person's switch point, plus 2.5 to 7 s reading time on a new question."]}).to_excel(xw, sheet_name="Read me", index=False)
        taps_df.to_excel(xw, sheet_name="Every answer", index=False)
        pd.DataFrame(main_rows).drop(columns=["trialsJSON"]).to_excel(xw, sheet_name="Main survey rows", index=False)
        pd.DataFrame(prop_rows).drop(columns=["trialsJSON"]).to_excel(xw, sheet_name="Short survey rows", index=False)
    print("Wrote %d synthetic rows (%d taps) to %s" % (len(syn), len(taps_df), out))


if __name__ == "__main__":
    main()
