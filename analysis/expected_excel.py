"""Excel workbook: expected results (with real-world noise) vs your real data vs the noise-free model benchmark.

Usage:
    py analysis/expected_excel.py real_responses.csv bench_plays.csv out.xlsx

- Expected with noise: 50 simulated people following the beta-delta model (model_prediction.py) with
  choice noise 2.5x the textbook level and 5% random slips, repeated REPEATS times (median and 90% range).
- Your real data: the main sample used in analyze.py (careless screen applied), and the proposal survey.
- Model benchmark: the 50 rule cards played exactly (rows tagged test = bench).
"""
import io
import contextlib
import math
import os
import sys

import numpy as np
import pandas as pd
from scipy import stats
from openpyxl.styles import Font

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import model_prediction as M
import analyze as A

N_PEOPLE = 50
REPEATS = 500
CTX = ["gain", "loss", "health", "friend"]


# ---------------------------------------------------------------- simulated respondents

def sim_main(p):
    r = {}
    for frame in "AB":
        for ctx in ["gain", "loss", "friend"]:
            ind, k, _ = M.adaptive(p, ctx, frame, 500, 500, 1250, 5, ctx == "loss")
            r["%s_%s_k" % (frame, ctx)] = k
        ind, k, _ = M.adaptive(p, "health_gain", frame, 20, 20, 80, 1, False)
        r["%s_health_k" % frame] = k
    near_later = M.pair(p, 1000, 1100, 0, 7)
    far_later = M.pair(p, 1000, 1100, 28, 35)
    r["classic"] = (not near_later) and far_later
    r["reverse"] = near_later and (not far_later)
    # Hidden zero halves the present bias
    group = "standard"
    q = dict(p)
    if M.RNG.random() < 0.5:
        group = "hiddenZero"
        q["beta"] = (1.0 + p["beta"]) / 2.0
    ind, k, _ = M.adaptive(q, "gain", "A", 2000, 2000, 5000, 10, False)
    r["nudgeGroup"] = group
    r["nudge_k"] = k
    # Anchoring: own amount pulled 30% up or 15% down, with personal noise
    base = math.exp(M.RNG.normal(math.log(9000), 0.35))
    group = "low"
    factor = 0.85
    if M.RNG.random() < 0.5:
        group = "high"
        factor = 1.3
    r["anchorGroup"] = group
    r["anchorAmount"] = min(100000, max(5000, base * factor * math.exp(M.RNG.normal(0, 0.15))))
    # Gut answers rise with present bias, plus noise
    r["type1Score"] = int(min(5, max(0, round((1.0 - p["beta"]) / 0.06 + M.RNG.normal(0, 1)))))
    return r


def sim_prop(p):
    r = {}
    for ctx in ["gain", "loss", "friend"]:
        ind, k, _ = M.adaptive(p, ctx, "A", 500, 500, 1250, 5, ctx == "loss")
        r["A_%s_k" % ctx] = k
    ind, k, _ = M.adaptive(p, "health_cost", "A", 10, 10, 25, 1, True)
    r["A_health_k"] = k
    near_later = M.pair(p, 100, 110, 0, 1)
    far_later = M.pair(p, 100, 110, 30, 31)
    r["classic"] = (not near_later) and far_later
    r["reverse"] = near_later and (not far_later)
    return r


# ---------------------------------------------------------------- one set of statistics for every column

def safe_p(fn):
    try:
        return float(fn())
    except Exception:
        return float("nan")


def main_stats(df):
    s = {"People analysed": len(df)}
    s["Classic reversal (%)"] = 100 * df["classic"].mean()
    s["Reverse reversal (%)"] = 100 * df["reverse"].mean()
    c = int(df["classic"].sum())
    rv = int(df["reverse"].sum())
    s["Classic vs reverse, McNemar p"] = safe_p(binom_p(c, rv))
    for b in "AB":
        for x in CTX:
            s["Median k, %s, block %s" % (x, b)] = df["%s_%s_k" % (b, x)].median()
    s["People with k(A) > k(B), gain (%)"] = 100 * (df["A_gain_k"] > df["B_gain_k"]).mean()
    s["Present bias, gain A vs B, Wilcoxon p"] = safe_p(wilcoxon_p(df["A_gain_k"], df["B_gain_k"]))
    s["Contexts differ (block A), Friedman p"] = safe_p(friedman_p(df, "A"))
    s["Fine vs gain (block A), Wilcoxon p"] = safe_p(wilcoxon_p(df["A_loss_k"], df["A_gain_k"]))
    s["Health vs gain (block A), Wilcoxon p"] = safe_p(wilcoxon_p(df["A_health_k"], df["A_gain_k"]))
    s["Friend vs self (block A), Wilcoxon p"] = safe_p(wilcoxon_p(df["A_friend_k"], df["A_gain_k"]))
    s["Spearman gain-fine (block B)"] = spearman(df["B_gain_k"], df["B_loss_k"])
    s["Spearman gain-health (block B)"] = spearman(df["B_gain_k"], df["B_health_k"])
    s["Spearman gain-friend (block B)"] = spearman(df["B_gain_k"], df["B_friend_k"])
    st = df.loc[df["nudgeGroup"] == "standard", "nudge_k"]
    hz = df.loc[df["nudgeGroup"] == "hiddenZero", "nudge_k"]
    s["Nudge: median k, plain wording"] = st.median()
    s["Nudge: median k, hidden zero"] = hz.median()
    s["Nudge: hidden zero lower, one-sided p"] = safe_p(mw_p(st, hz))
    hi = df.loc[df["anchorGroup"] == "high", "anchorAmount"]
    lo = df.loc[df["anchorGroup"] == "low", "anchorAmount"]
    s["Anchoring: median amount, high anchor (Rs)"] = hi.median()
    s["Anchoring: median amount, low anchor (Rs)"] = lo.median()
    s["Anchoring: high > low, one-sided p"] = safe_p(mw_p(hi, lo))
    logk = np.log(df[["A_%s_k" % x for x in CTX]]).mean(axis=1)
    s["Type 1: Spearman gut answers vs log k"] = spearman(df["type1Score"], logk)
    return s


def prop_stats(df):
    s = {"People analysed": len(df)}
    s["Classic reversal (%)"] = 100 * df["classic"].mean()
    s["Reverse reversal (%)"] = 100 * df["reverse"].mean()
    for x in CTX:
        s["Median k, %s" % x] = df["A_%s_k" % x].median()
    s["Contexts differ, Friedman p"] = safe_p(friedman_p(df, "A"))
    s["Fine vs gain, Wilcoxon p"] = safe_p(wilcoxon_p(df["A_loss_k"], df["A_gain_k"]))
    s["Flu vs gain, Wilcoxon p"] = safe_p(wilcoxon_p(df["A_health_k"], df["A_gain_k"]))
    s["Spearman gain-flu"] = spearman(df["A_gain_k"], df["A_health_k"])
    return s


def binom_p(c, rv):
    def f():
        return stats.binomtest(c, c + rv).pvalue
    return f


def wilcoxon_p(a, b):
    def f():
        return stats.wilcoxon(a, b).pvalue
    return f


def friedman_p(df, block):
    def f():
        return stats.friedmanchisquare(*[df["%s_%s_k" % (block, x)] for x in CTX]).pvalue
    return f


def mw_p(a, b):
    def f():
        return stats.mannwhitneyu(a, b, alternative="greater").pvalue
    return f


def spearman(a, b):
    try:
        return float(stats.spearmanr(a, b, nan_policy="omit").statistic)
    except Exception:
        return float("nan")


# ---------------------------------------------------------------- real and benchmark rows

def quiet(fn, *args):
    # The analysis helpers print; keep the console clean
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*args)


def prepare_main(df):
    df = df.copy()
    df["classic"] = df["flipped"] == "yes"
    df["reverse"] = (df["flipNear"] == "₹1100 in 1 week") & (df["flipFar"] == "₹1000 in 4 weeks")
    for col in ["nudge_k", "anchorAmount", "type1Score"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def prepare_prop(df):
    df = df.copy()
    df["classic"] = df["flipped"] == "yes"
    df["reverse"] = df["reverseFlip"] == "yes"
    for x in CTX:
        df["A_%s_k" % x] = pd.to_numeric(df["A_%s_k" % x], errors="coerce")
    return df


def load_main(path, bench):
    A.BENCH = bench
    A.KEEP = "all"
    raw = quiet(A.load, path)
    df, sens, strict = quiet(A.exclusions, raw)
    return prepare_main(df)


def load_prop(path, bench):
    df = pd.read_csv(path)
    if "survey" not in df.columns:
        return None
    df = df[df["survey"] == "proposal"]
    df["test"] = df["test"].fillna("no").replace("", "no")
    if bench:
        df = df[df["test"] == "bench"]
    else:
        df = df[df["test"] == "no"]
    df = df[(df["consent"] == "yes") & (df["attentionFail"] != "yes")]
    return prepare_prop(df)


# ---------------------------------------------------------------- workbook

def fmt(stat, v):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "n/a"
    if "p" == stat.split(" ")[-1]:
        if v < 0.001:
            return "< .001"
        return "%.3f" % v
    if "Median k" in stat or "Nudge: median k" in stat:
        return "%.4f" % v
    if "(Rs)" in stat or stat == "People analysed":
        return "%d" % round(v)
    if "Spearman" in stat:
        return "%.2f" % v
    return "%.1f" % v


def expected_cell(stat, vals):
    vals = np.array([x for x in vals if not (isinstance(x, float) and math.isnan(x))], dtype=float)
    if len(vals) == 0:
        return "n/a"
    if stat.split(" ")[-1] == "p":
        share = 100 * np.mean(vals < 0.05)
        return "%s (significant in %d%% of studies)" % (fmt(stat, float(np.median(vals))), round(share))
    return "%s [%s to %s]" % (fmt(stat, float(np.median(vals))), fmt(stat, float(np.percentile(vals, 5))), fmt(stat, float(np.percentile(vals, 95))))


def build(name, sim_fn, stat_fn, real, bench):
    runs = []
    for _ in range(REPEATS):
        people = [sim_fn(M.person()) for _ in range(N_PEOPLE)]
        runs.append(stat_fn(pd.DataFrame(people)))
    real_s = {}
    if real is not None and len(real) >= 5:
        real_s = stat_fn(real)
    bench_s = {}
    if bench is not None and len(bench) >= 5:
        bench_s = stat_fn(bench)
    rows = []
    for stat in runs[0]:
        real_v = "not enough responses yet"
        if real_s:
            real_v = fmt(stat, real_s[stat])
        if stat == "People analysed" and real is not None and not real_s:
            real_v = "%d (too few to analyse)" % len(real)
        bench_v = "n/a"
        if bench_s:
            bench_v = fmt(stat, bench_s[stat])
        rows.append({"Statistic": stat,
                     "Expected with real-world noise (50 people)": expected_cell(stat, [r[stat] for r in runs]),
                     "Your real data till now": real_v,
                     "Model benchmark, no noise (50 rule cards)": bench_v})
    print("built", name)
    return pd.DataFrame(rows)


def main():
    if len(sys.argv) < 4:
        print(__doc__)
        sys.exit(1)
    real_path, bench_path, out = sys.argv[1], sys.argv[2], sys.argv[3]
    M.RNG = np.random.default_rng(11)
    # Real-world noise: 2.5x the textbook choice noise and 5% random slips
    M.NOISE = 2.5
    M.SLIP = 0.05
    main_t = build("main", sim_main, main_stats, load_main(real_path, False), load_main(bench_path, True))
    prop_t = build("proposal", sim_prop, prop_stats, load_prop(real_path, False), load_prop(bench_path, True))
    notes = pd.DataFrame({"Notes": [
        "Model: quasi-hyperbolic beta-delta discounting (Laibson 1997; McClure et al. 2004).",
        "Present bias beta ~ Normal(0.85, 0.10). 30-vs-60-day gain switch point = Rs 500 + lognormal extra (median Rs 100).",
        "Sign effect: fines discounted at 1/4 of the gain rate (Thaler 1981). Friend: k x 0.8, beta halfway to 1 (Albrecht et al. 2011).",
        "Health as a gain (main survey): k x 1.5. Flu as a cost (short survey): like fines.",
        "Domain-specific patience (Chapman 1996): personal multiplier on k, sd 0.3 for a friend, 1.2 for fines and health.",
        "Hidden zero halves present bias (Magen et al. 2008). Anchors move amounts +30% / -15% (Tversky & Kahneman 1974).",
        "Gut answers rise with present bias (Frederick 2005).",
        "Real-world noise: choice noise 2.5x the textbook level and 5%% random taps. %d simulated studies of %d people." % (REPEATS, N_PEOPLE),
        "Expected column: median across simulated studies, [5th to 95th percentile]. For p values: median p and how often p < .05.",
        "Your real data: main survey main sample (careless-response screen applied); short survey after the dominance check.",
        "Model benchmark: the 50 rule cards played exactly through both live surveys (#bench links).",
        "Simulated and benchmark rows are not research data."]})
    with pd.ExcelWriter(out, engine="openpyxl") as xw:
        main_t.to_excel(xw, sheet_name="Main survey", index=False)
        prop_t.to_excel(xw, sheet_name="Short survey", index=False)
        notes.to_excel(xw, sheet_name="Notes", index=False)
        for ws in xw.book.worksheets:
            for col in ws.columns:
                width = max(len(str(c.value or "")) for c in col)
                ws.column_dimensions[col[0].column_letter].width = min(70, width + 2)
            for c in ws[1]:
                c.font = Font(bold=True)
            ws.freeze_panes = "B2"
    print("Saved", out)


if __name__ == "__main__":
    main()
