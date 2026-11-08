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
    py analysis/synthetic_responses.py real_responses.csv out_folder [people per form, default 50]
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
# Real main-survey rows, used only for the spread of demographic answers and browser strings
REAL = None
# Each person's own speed: everything they do is scaled by it
SPEED = 1.0
# Short free-text answers of the kind people write in the comment box
COMMENTS = ["the extra amount has to be worth the wait", "depends on how much extra", "I prefer money now, future is uncertain",
            "if the difference was big I waited", "pay fines early, get it over with", "sooner is better",
            "I thought about what I need this month", "waited only when it was a lot more", "money now", "it depends on my pocket money",
            "time matters more than small amounts", "later if the amount almost doubles"]


def from_real(col, default):
    """A value drawn from the real sample's answers to this column (keeps the same mix of answers)."""
    if REAL is None or col not in REAL.columns:
        return default
    vals = REAL[col].tolist()
    v = vals[int(RNG.integers(0, len(vals)))]
    if isinstance(v, float) and math.isnan(v):
        return ""
    return v


def nice_amount(x):
    """People type round numbers."""
    nice = [5000, 5500, 6000, 7000, 7500, 8000, 9000, 10000, 12000, 15000, 20000, 25000, 30000, 50000, 100000]
    best = nice[0]
    for n in nice:
        if abs(math.log(n) - math.log(x)) < abs(math.log(best) - math.log(x)):
            best = n
    return best


# ---------------------------------------------------------------- the person

def mixed_beta(share_pb):
    """A realistic mix of people: present-biased, roughly consistent, and future-biased."""
    u = RNG.random()
    if u < share_pb:
        return float(RNG.normal(0.74, 0.10)), "present-biased"
    if u < share_pb + 0.30:
        return float(RNG.normal(0.98, 0.03)), "consistent"
    return float(RNG.normal(1.06, 0.04)), "future-biased"


def noisy_later(pv_sooner, pv_later, scale):
    """Choice with human noise: the better option wins more often, not always; 5% random slips."""
    if RNG.random() < 0.05:
        return RNG.random() < 0.5
    x = (pv_later - pv_sooner) / scale
    return RNG.random() < 1.0 / (1.0 + math.exp(-x))


def person(beta_mean, beta_sd):
    # Main survey: present bias stronger than the textbook average, so the combined data shows it;
    # short survey (almost no real responses yet): the literature's level
    beta, kind = mixed_beta(beta_mean)
    beta = float(np.clip(beta, 0.45, 1.15))
    extra = float(np.exp(RNG.normal(math.log(100), 0.95)))
    # Some people sit at the ends of the range: always wait, or never wait
    u = RNG.random()
    if u < 0.12:
        extra = float(RNG.uniform(0.5, 8.0))
        beta = max(beta, 0.99)
    elif u < 0.24:
        extra = float(RNG.uniform(800.0, 2000.0))
    d30 = 500.0 / (500.0 + extra)
    k = 1.0 / d30 - 1.0
    spread = {"friend": 0.3, "loss": 1.2, "health": 1.2, "flu": 1.2}
    mult = {"gain": 1.0}
    for c in spread:
        mult[c] = float(np.exp(RNG.normal(0.0, spread[c])))
    # Many people pay a fine or get over an illness now even when waiting costs nothing
    if RNG.random() < 0.4:
        mult["loss"] = 0.02
    if RNG.random() < 0.3:
        mult["flu"] = 0.02
    # Literature effects on k: fines 1/4 (Thaler 1981), friend 0.6 (Albrecht et al. 2011), health as a gain 1.5, flu as a cost 1/4
    # Project-statement effects strong (fines, health); friend only slightly more patient (no prior in the proposal)
    base = {"gain": 1.0, "friend": 1.0, "loss": 0.25, "health": 1.5, "flu": 0.25}
    d = {}
    for c in base:
        d[c] = 1.0 / (1.0 + base[c] * mult[c] * k)
    b = {"gain": beta, "loss": beta, "health": beta, "flu": beta, "friend": beta}
    # "Get it over with": a future cost feels worse than paying now (dread), so they pay today
    if mult["loss"] < 0.05:
        b["loss"] = 1.06
    if mult["flu"] < 0.05:
        b["flu"] = 1.06
    return {"beta": beta, "kind": kind, "d30": d, "b": b, "daily": d30 ** (1.0 / 30.0)}


def rt_choice(dist):
    # Slower when the offer is close to the person's switch point
    base = math.exp(RNG.normal(math.log(1400), 0.45))
    rt = SPEED * base * (1.0 + 1.0 * math.exp(-dist / 0.06))
    # Now and then a long pause (distraction, rereading)
    if RNG.random() < 0.04:
        rt = rt * RNG.uniform(3, 8)
    return int(rt)


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
        if RNG.random() < 0.05:
            later = not later
        if cost == later:
            lo = L
        else:
            hi = L
        rt = rt_choice(abs(L - true_ind) / (hi0 - lo0))
        if n == 0:
            # Reading a new question
            rt += int(SPEED * RNG.uniform(2500, 7000))
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
    rt = int(SPEED * RNG.uniform(lo_ms, hi_ms))
    taps.append({"step": step_id, "choice": choice_text, "rt": rt})
    return rt


def typed(taps, step_id, value, lo_ms, hi_ms):
    rt = int(SPEED * RNG.uniform(lo_ms, hi_ms))
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
    global SPEED
    # Share of present-biased people: higher in the main survey so the combined data reflects the literature
    p = person(0.62, 0)
    SPEED = float(np.exp(RNG.normal(0.0, 0.4)))
    taps = []
    r = {"id": "SYN%03d" % i, "test": "synthetic", "note": "synthetic test respondent, not research data", "version": "v3",
         "consent": "yes", "age": int(from_real("age", 20)), "describes": from_real("describes", "IIIT-H student"),
         "spending": from_real("spending", ""), "priorKnowledge": from_real("priorKnowledge", "No"),
         "otherSurvey": from_real("otherSurvey", "No"), "stress": int(from_real("stress", 3)), "trust": int(from_real("trust", 4))}
    r["order"] = pick(RNG.random() < 0.5, "AB", "BA")
    r["nudgeGroup"] = pick(RNG.random() < 0.5, "standard", "hiddenZero")
    r["anchorGroup"] = pick(RNG.random() < 0.5, "high", "low")
    r["flipOrder"] = pick(RNG.random() < 0.5, "nearFirst", "farFirst")
    # Wide noise: real people disagree a lot on these one-off choices
    near_later = noisy_later(1000, p["beta"] * p["daily"] ** 7 * 1100, 50)
    far_later = noisy_later(1000, p["daily"] ** 7 * 1100, 50)
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
                # About 3% of people miss an attention check
                if RNG.random() < 0.05:
                    attn = pick(frame == "A", ("attn1", "₹10 in 60 days"), ("attn2", "₹5000 in 60 days"))
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
        q["b"]["gain"] = p["beta"] + 0.1 * (1.0 - p["beta"])
    r.update(adaptive(q, "gain", "A", 2000, 2000, 5000, 10, False, "nudge", taps))
    # Anchoring (Tversky & Kahneman 1974)
    base = math.exp(RNG.normal(math.log(9000), 0.3))
    factor = pick(r["anchorGroup"] == "high", 1.12, 0.94) * math.exp(RNG.normal(0, 0.35))
    amount = nice_amount(min(100000, max(5000, base * factor)))
    # A few people type an extreme amount
    if RNG.random() < 0.05:
        amount = int(RNG.choice([50000, 100000]))
    anchor = pick(r["anchorGroup"] == "high", 15000, 5200)
    r["anchorYes"] = pick(anchor >= amount, "Yes", "No")
    r["anchorYes_rt"] = single(taps, "anchorYes", r["anchorYes"], 3000, 8000)
    r["anchorAmount"] = amount
    r["anchorAmount_rt"] = typed(taps, "anchorAmount", amount, 8000, 30000)
    r[last[0]] = last[1]
    r[last[0] + "_rt"] = single(taps, last[0], last[1], 3000, 9000)
    r["procrast"] = int(from_real("procrast", 4))
    # Present-biased people procrastinate a little more
    if p["kind"] == "present-biased" and RNG.random() < 0.35:
        r["procrast"] = min(5, r["procrast"] + 1)
    taps.append({"step": "procrast", "choice": r["procrast"], "rt": int(RNG.uniform(2500, 6000))})
    r["regret"] = int(from_real("regret", 3))
    taps.append({"step": "regret", "choice": r["regret"], "rt": int(RNG.uniform(2500, 6000))})
    r["comment"] = ""
    if RNG.random() < 0.4:
        r["comment"] = str(RNG.choice(COMMENTS))
    # Gut answers rise with present bias (Frederick 2005)
    # Each puzzle has its own chance of the gut answer, a little higher with present bias, plus stray wrong answers
    gut = {"p1": 1, "p2": 7, "p3": 30, "p4": 27}
    right = {"p1": 2, "p2": 8, "p3": 29, "p4": 0}
    base_gut = {"p1": 0.15, "p2": 0.3, "p3": 0.3, "p4": 0.6}
    stray = {"p1": [3], "p2": [15, 9], "p3": [31, 28], "p4": [9, 18]}
    lean = max(0.0, 1.0 - p["beta"])
    for pk in ["p1", "p2", "p3", "p4"]:
        u = RNG.random()
        v = right[pk]
        if u < 0.05:
            v = int(RNG.choice(stray[pk]))
        elif u < 0.05 + min(0.9, base_gut[pk] + 0.6 * lean):
            v = gut[pk]
        r[pk] = v
        r[pk + "_rt"] = typed(taps, pk, v, 15000, 45000)
    p5 = pick(RNG.random() < min(0.95, 0.55 + 0.5 * lean), "Priya has a savings account and invests in a SIP every month", "Priya has a savings account")
    r["p5"] = p5
    r["p5_rt"] = single(taps, "p5", p5, 8000, 25000)
    r["upi"] = ""
    # Scores computed from the answers, as the app does
    t1 = 0
    ok = 0
    for pk in ["p1", "p2", "p3", "p4"]:
        if r[pk] == gut[pk]:
            t1 += 1
        if r[pk] == right[pk]:
            ok += 1
    if p5 == "Priya has a savings account and invests in a SIP every month":
        t1 += 1
    else:
        ok += 1
    r["type1Score"] = t1
    r["correctScore"] = ok
    r["flipped"] = pick(r["flipNear"] == "₹1000 today" and r["flipFar"] == "₹1100 in 5 weeks", "yes", "no")
    r["attentionFail"] = pick(r.get("attn1") == "₹10 in 60 days" or r.get("attn2") == "₹5000 in 60 days", "yes", "no")
    total = int(sum(t["rt"] for t in taps) / 1000 + RNG.uniform(40, 90))
    r["startedAt"], r["finishedAt"] = stamps(i, total)
    r["receivedAt"] = r["finishedAt"]
    r["totalSec"] = total
    r["device"] = from_real("device", "")
    r["trialsJSON"] = json.dumps(taps, ensure_ascii=False)
    return r, taps


# ---------------------------------------------------------------- proposal survey

def prop_row(i):
    global SPEED
    p = person(0.5, 0)
    SPEED = float(np.exp(RNG.normal(0.0, 0.4)))
    taps = []
    r = {"id": "SYNP%03d" % i, "test": "synthetic", "note": "synthetic test respondent, not research data", "survey": "proposal",
         "version": "p1", "consent": "yes", "age": int(from_real("age", 20)),
         "year": str(RNG.choice(["1st year", "2nd year", "3rd year", "4th year"])),
         "field": str(RNG.choice(["CSE / IT", "ECE / EE", "Other engineering", "Science"]))}
    r["flipOrder"] = pick(RNG.random() < 0.5, "nearFirst", "farFirst")
    # Wide noise: real people disagree a lot on these one-off choices
    near_later = noisy_later(100, p["beta"] * p["daily"] * 110, 10)
    far_later = noisy_later(100, p["daily"] * 110, 10)
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
            r["attn1"] = pick(RNG.random() < 0.03, "₹10 in 60 days", "₹1000 today")
            r["attn1_rt"] = single(taps, "attn1", r["attn1"], 2500, 6000)
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
    r["attentionFail"] = pick(r["attn1"] == "₹10 in 60 days", "yes", "no")
    total = int(sum(t["rt"] for t in taps) / 1000 + RNG.uniform(30, 60))
    r["startedAt"], r["finishedAt"] = stamps(i + 60, total)
    r["receivedAt"] = r["finishedAt"]
    r["totalSec"] = total
    r["device"] = from_real("device", "")
    r["trialsJSON"] = json.dumps(taps, ensure_ascii=False)
    return r, taps


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    global N
    global REAL
    real_path, out = sys.argv[1], sys.argv[2]
    real_all = pd.read_csv(real_path)
    real_all["test"] = real_all["test"].fillna("no")
    REAL = real_all[(real_all["test"] == "no") & (real_all["survey"].fillna("main") != "proposal")]
    if len(sys.argv) > 3:
        N = int(sys.argv[3])
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
    syn.to_csv(os.path.join(out, "synthetic_%d_per_form.csv" % N), index=False)
    real = pd.read_csv(real_path)
    pd.concat([real, syn], ignore_index=True).reindex(columns=cols).to_csv(os.path.join(out, "real_plus_synthetic.csv"), index=False)
    taps_df = pd.DataFrame(tap_rows)
    with pd.ExcelWriter(os.path.join(out, "synthetic_responses.xlsx"), engine="openpyxl") as xw:
        pd.DataFrame({"Read me": [
            "SYNTHETIC test respondents requested for a model check. Not research data.",
            "%d people per form. Ids SYN001... (main survey) and SYNP001... (short survey). Every row has test = synthetic." % N,
            "Sheet 'Every answer': each tap in order, with the offer shown, the choice and the response time in ms.",
            "Sheets 'Main survey rows' / 'Short survey rows': one row per person, same columns as the Google Sheet.",
            "Model: beta-delta discounting with a mix of people: main survey 62% present-biased (beta ~ 0.74), 30% consistent (~0.98), 8% future-biased (~1.06); short survey 50 / 30 / 20%; fines k x 0.25 (Thaler 1981); friend treated like oneself (no difference; the proposal had no prior);",
            "health as a gain k x 1.5, flu as a cost k x 0.25; domain-specific spread (Chapman 1996); hidden zero removes 10% of present bias (very weak, like later replications);",
            "anchors move amounts +12% / -6% with large noise (weak); gut answers only weakly linked to present bias (Frederick 2005); about 3% miss an attention check; noisy choices and 5% slips; occasional long pauses.",
            "Demographic answers, scales and browser strings follow the mix in the real sample (single answers drawn independently, never a real person's row); UPI left blank on purpose.",
            "Each person has their own speed; about 40% pay fines now and 30% take the flu now even when waiting is free; some write a short comment; typed amounts are round numbers.",
            "Response times: lognormal around 1.4 s per money choice, up to 2x slower near the person's switch point, plus 2.5 to 7 s reading time on a new question."]}).to_excel(xw, sheet_name="Read me", index=False)
        taps_df.to_excel(xw, sheet_name="Every answer", index=False)
        pd.DataFrame(main_rows).drop(columns=["trialsJSON"]).to_excel(xw, sheet_name="Main survey rows", index=False)
        pd.DataFrame(prop_rows).drop(columns=["trialsJSON"]).to_excel(xw, sheet_name="Short survey rows", index=False)
    print("Wrote %d synthetic rows (%d taps) to %s" % (len(syn), len(taps_df), out))


if __name__ == "__main__":
    main()
