"""Planned analysis for "Now or Later?" (PROJECT_CONTEXT.md, section "Planned analysis").

Usage:
    py analysis/analyze.py path/to/responses.csv [v1|v2|all]

The optional last argument keeps only one question version (default: all).
v1 = the first version (5 steps per task, health up to 50 days); v2 = 6 steps, health up to 80 days.

Reads the CSV exported from the Google Sheet ("responses" tab: File -> Download -> CSV)
and writes every table, test result and figure to analysis/out/.
"""
import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
import numpy as np
import pandas as pd
from scipy import stats
import statsmodels.formula.api as smf
from statsmodels.stats.multitest import multipletests

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
CONTEXTS = ["gain", "loss", "health", "friend"]
FRAMES = ["A", "B"]
# Sooner amount V for each context (health in days)
# Which question version to analyse; set from the command line
KEEP = "all"
# True with --bench: analyse only the lab benchmark plays
BENCH = False
# True with --with-synthetic: real responses plus the synthetic test respondents
SYNTH = False
V = {"gain": 500, "loss": 500, "health": 20, "friend": 500}
# Validated categorical slots 1-4 (dataviz reference palette), fixed per context
COLORS = {"gain": "#2a78d6", "loss": "#eb6834", "health": "#1baf7a", "friend": "#eda100"}
INK = "#0b0b0b"
INK2 = "#52514e"
SURFACE = "#fcfcfb"
INTUITIVE_P5 = "Priya has a savings account and invests in a SIP every month"

report_lines = []


def say(text=""):
    print(text)
    report_lines.append(str(text))


def holm(pvals):
    return list(multipletests(pvals, method="holm")[1])


def rank_biserial_paired(x, y):
    # Matched-pairs rank-biserial correlation for a Wilcoxon signed-rank test
    d = np.asarray(x) - np.asarray(y)
    d = d[d != 0]
    if len(d) == 0:
        return 0.0
    r = stats.rankdata(np.abs(d))
    return float((r[d > 0].sum() - r[d < 0].sum()) / r.sum())


def rank_biserial_indep(x, y):
    u = stats.mannwhitneyu(x, y, alternative="two-sided").statistic
    return float(2 * u / (len(x) * len(y)) - 1)


def style_axes(ax):
    ax.set_facecolor(SURFACE)
    for side in ["top", "right"]:
        ax.spines[side].set_visible(False)
    for side in ["left", "bottom"]:
        ax.spines[side].set_color("#c9c8c2")
    ax.tick_params(colors=INK2, labelsize=9)
    ax.yaxis.label.set_color(INK2)
    ax.xaxis.label.set_color(INK2)
    ax.grid(axis="y", color="#ebeae6", linewidth=0.8)
    ax.set_axisbelow(True)


# ---------------------------------------------------------------- load


def load(path):
    df = pd.read_csv(path)
    # The Sheet's id header was once cleared: old ids sit under a blank header, new ones in an id column at the end
    if " " in df.columns:
        if "id" in df.columns:
            df["id"] = df[" "].fillna(df["id"])
        else:
            df["id"] = df[" "]
        df = df.drop(columns=[" "])
    say("Rows in file: %d" % len(df))
    # Retries can create duplicate rows; keep the first arrival of each id
    if "receivedAt" in df.columns:
        df = df.sort_values("receivedAt")
    before = len(df)
    df = df.drop_duplicates("id", keep="first")
    say("Duplicate ids removed: %d" % (before - len(df)))
    if "test" not in df.columns:
        df["test"] = "no"
    df["test"] = df["test"].fillna("no").replace("", "no")
    if BENCH:
        # Benchmark mode: only the lab plays made with the rule cards (#bench)
        df = df[df["test"] == "bench"]
        say("Benchmark mode: keeping only #bench plays: %d" % len(df))
    elif SYNTH:
        # Real responses plus the synthetic test respondents (ids SYN...)
        df = df[df["test"].isin(["no", "synthetic"])]
        say("With synthetic respondents: %d real + %d synthetic" % (int((df["test"] == "no").sum()), int((df["test"] == "synthetic").sum())))
    else:
        n_test = int((df["test"] != "no").sum())
        df = df[df["test"] == "no"]
        say("Test, benchmark and synthetic rows removed: %d" % n_test)
    # Rows from the short proposal survey (proposal.html) are analysed by analyze_proposal.py
    if "survey" in df.columns:
        n_prop = int((df["survey"] == "proposal").sum())
        df = df[df["survey"] != "proposal"]
        say("Proposal-survey rows set aside: %d" % n_prop)
    numeric = ["age", "stress", "trust", "procrast", "regret", "anchorAmount", "totalSec",
               "type1Score", "correctScore", "flipNear_rt", "flipFar_rt"]
    for c in CONTEXTS:
        for f in FRAMES:
            numeric += ["%s_%s_ind" % (f, c), "%s_%s_k" % (f, c), "%s_%s_meanRT" % (f, c)]
    numeric += ["nudge_ind", "nudge_k", "nudge_meanRT"]
    for col in numeric:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df["spending"] = df["spending"].fillna("").replace("", "Not given")
    # Rows from before the version column existed are v1
    if "version" not in df.columns:
        df["version"] = "v1"
    df["version"] = df["version"].fillna("v1").replace("", "v1")
    say("Versions: %s" % df["version"].value_counts().to_dict())
    # v1 and v2 always asked the near classic pair first
    if "flipOrder" not in df.columns:
        df["flipOrder"] = "nearFirst"
    df["flipOrder"] = df["flipOrder"].fillna("nearFirst").replace("", "nearFirst")
    if KEEP != "all":
        df = df[df["version"] == KEEP]
        say("Keeping only %s: %d rows" % (KEEP, len(df)))
    df["flipped_yes"] = (df["flipped"] == "yes").astype(int)
    return df.reset_index(drop=True)


def careless_flags(df):
    """Counts warning signs of careless answering, one point each (0 to 5).

    1. Total time under 5 minutes (median is about 8).
    2. Median time per money question under 0.8 s (median is about 1.6 s).
    3. More than 25% of money questions answered in under 0.4 s.
    4. 7 or more of the 9 money tasks answered all on one side.
    5. Failed both attention checks.
    """
    flags = []
    for _, r in df.iterrows():
        try:
            taps = [t for t in json.loads(r["trialsJSON"]) if "offer" in t]
        except (TypeError, ValueError):
            taps = []
        n = 0
        if r["totalSec"] < 300:
            n += 1
        if taps:
            rts = np.array([t["rt"] for t in taps])
            if np.median(rts) < 800:
                n += 1
            if np.mean(rts < 400) > 0.25:
                n += 1
            tasks = {}
            for t in taps:
                tasks.setdefault(t["step"], set()).add(t["choice"])
            one_sided = 0
            for v in tasks.values():
                if len(v) == 1:
                    one_sided += 1
            if one_sided >= 7:
                n += 1
        if r["attn1"] == "₹10 in 60 days" and r["attn2"] == "₹5000 in 60 days":
            n += 1
        flags.append(n)
    return pd.Series(flags, index=df.index)


def exclusions(df):
    say("\n== Exclusions ==")
    n0 = len(df)
    df = df[df["consent"] == "yes"].copy()
    say("No consent: %d" % (n0 - len(df)))
    # Main rule: drop a response only when it shows 3 or more signs of careless answering.
    # A failed attention check alone is not enough, because the v1 wording of check 2 caught careful people too.
    df["carelessFlags"] = careless_flags(df)
    careless = df[df["carelessFlags"] >= 3]
    say("Careless (3+ of 5 warning signs): %d, of whom %d failed an attention check and %d passed both"
        % (len(careless), int((careless["attentionFail"] == "yes").sum()), int((careless["attentionFail"] != "yes").sum())))
    say("  ids: %s" % ", ".join(careless["id"].astype(str)))
    if BENCH:
        # Benchmark plays follow rule cards, so speed-based careless flags do not apply
        say("Benchmark mode: careless screen not applied")
    else:
        df = df[df["carelessFlags"] < 3]
    say("Kept despite failing an attention check: %d" % int((df["attentionFail"] == "yes").sum()))
    say("Main sample: %d" % len(df))
    strict = df[df["attentionFail"] != "yes"]
    say("Strict sample (also drops every attention-check fail): %d" % len(strict))
    sens = df[(df["priorKnowledge"] != "Yes, in detail") & (df["otherSurvey"] != "Yes")]
    say("Sensitivity sample (drops prior knowledge 'Yes, in detail' and otherSurvey 'Yes'): %d" % len(sens))
    return df.reset_index(drop=True), sens.reset_index(drop=True), strict.reset_index(drop=True)


# ---------------------------------------------------------------- hypotheses


def h1(df, label):
    say("\n== H1 paradox (%s) ==" % label)
    n = len(df)
    k_flip = int(df["flipped_yes"].sum())
    if n:
        ci = stats.binomtest(k_flip, n).proportion_ci()
        say("Flipped (today in near pair, later in far pair): %d/%d = %.1f%% [95%% CI %.1f-%.1f]"
            % (k_flip, n, 100 * k_flip / n, 100 * ci.low, 100 * ci.high))
        say("Pattern table (flipNear x flipFar):")
        say(pd.crosstab(df["flipNear"], df["flipFar"]).to_string())
        # Exploratory: classic reversals (today, then later) against reverse ones (later, then sooner)
        rev = (df["flipNear"] == "₹1100 in 1 week") & (df["flipFar"] == "₹1000 in 4 weeks")
        n_rev = int(rev.sum())
        if k_flip + n_rev > 0:
            mc = stats.binomtest(k_flip, k_flip + n_rev).pvalue
            say("Exploratory McNemar: classic %d vs reverse %d, exact p=%.4f" % (k_flip, n_rev, mc))
        # v1 and v2 always asked the near pair first; v3 randomises it
        for o, g in df.groupby("flipOrder"):
            g_rev = int(((g["flipNear"] == "₹1100 in 1 week") & (g["flipFar"] == "₹1000 in 4 weeks")).sum())
            say("  %s (n=%d): classic %d, reverse %d" % (o, len(g), int(g["flipped_yes"].sum()), g_rev))
    rows = []
    for c in CONTEXTS:
        a = df["A_%s_k" % c]
        b = df["B_%s_k" % c]
        ok = a.notna() & b.notna()
        res = stats.wilcoxon(a[ok], b[ok])
        rows.append({"context": c, "n": int(ok.sum()), "median_kA": a[ok].median(), "median_kB": b[ok].median(),
                     "pct_kA_gt_kB": 100 * (a[ok] > b[ok]).mean(), "W": res.statistic, "p": res.pvalue,
                     "r_rb": rank_biserial_paired(a[ok], b[ok])})
    t = pd.DataFrame(rows)
    t["p_holm"] = holm(t["p"])
    say(t.round(5).to_string(index=False))
    return t


def h2(df):
    say("\n== H2 contexts ==")
    out = []
    for f in FRAMES:
        cols = ["%s_%s_k" % (f, c) for c in CONTEXTS]
        sub = df[cols].dropna()
        fr = stats.friedmanchisquare(*[sub[c] for c in cols])
        kendall_w = fr.statistic / (len(sub) * (len(cols) - 1))
        say("Block %s Friedman: chi2=%.3f p=%.5f Kendall W=%.3f (n=%d)" % (f, fr.statistic, fr.pvalue, kendall_w, len(sub)))
        rows = []
        for i in range(len(CONTEXTS)):
            for j in range(i + 1, len(CONTEXTS)):
                x = sub[cols[i]]
                y = sub[cols[j]]
                w = stats.wilcoxon(x, y)
                rows.append({"block": f, "pair": CONTEXTS[i] + " vs " + CONTEXTS[j], "W": w.statistic,
                             "p": w.pvalue, "r_rb": rank_biserial_paired(x, y)})
        t = pd.DataFrame(rows)
        t["p_holm"] = holm(t["p"])
        say(t.round(5).to_string(index=False))
        out.append(t)
    return pd.concat(out)


def h3(df):
    say("\n== H3 trait vs state: Spearman of k across contexts ==")
    mats = []
    for f in FRAMES:
        cols = ["%s_%s_k" % (f, c) for c in CONTEXTS]
        rho = df[cols].corr(method="spearman")
        rho.index = CONTEXTS
        rho.columns = CONTEXTS
        say("Block %s:" % f)
        say(rho.round(3).to_string())
        rho.to_csv(os.path.join(OUT, "h3_spearman_block%s.csv" % f))
        mats.append(rho)
    return mats


def h4(df):
    say("\n== H4 hidden-zero nudge: nudge_k by nudgeGroup ==")
    s = df.loc[df["nudgeGroup"] == "standard", "nudge_k"].dropna()
    h = df.loc[df["nudgeGroup"] == "hiddenZero", "nudge_k"].dropna()
    u = stats.mannwhitneyu(h, s, alternative="two-sided")
    say("standard: n=%d median=%.5f | hiddenZero: n=%d median=%.5f | U=%.1f p=%.5f r_rb=%.3f"
        % (len(s), s.median(), len(h), h.median(), u.statistic, u.pvalue, rank_biserial_indep(h, s)))
    say("Expected direction: hiddenZero lower k (more patient).")
    return {"U": u.statistic, "p": u.pvalue}


def h5(df):
    say("\n== H5 anchoring: anchorAmount by anchorGroup ==")
    hi = df.loc[df["anchorGroup"] == "high", "anchorAmount"].dropna()
    lo = df.loc[df["anchorGroup"] == "low", "anchorAmount"].dropna()
    u = stats.mannwhitneyu(hi, lo, alternative="two-sided")
    say("high: n=%d median=%.0f | low: n=%d median=%.0f | U=%.1f p=%.5f r_rb=%.3f"
        % (len(hi), hi.median(), len(lo), lo.median(), u.statistic, u.pvalue, rank_biserial_indep(hi, lo)))
    # H5 predicts a direction (high anchor gives higher amounts), so the one-sided test is also reported
    u1 = stats.mannwhitneyu(hi, lo, alternative="greater")
    say("One-sided (high > low, as H5 predicts): p=%.5f" % u1.pvalue)
    say("Anchor yes-rate: " + df.groupby("anchorGroup")["anchorYes"].apply(yes_rate).round(3).to_string())
    return {"U": u.statistic, "p": u.pvalue}


def yes_rate(s):
    return (s == "Yes").mean()


def mean_logk_A(df):
    cols = ["A_%s_k" % c for c in CONTEXTS]
    return np.log(df[cols]).mean(axis=1)


def h6(df):
    say("\n== H6 Type 1 thinking ==")
    say("All versions together. v1 and v2 used easier puzzles that most people solved, so type1Score varied little there.")
    h6_part(df)
    v3 = df[df["version"] == "v3"]
    if len(v3) >= 5:
        say("\n-- H6, v3 only (harder CRT-2 and Toplak puzzles), n=%d --" % len(v3))
        say("type1Score distribution: %s" % v3["type1Score"].value_counts().sort_index().to_dict())
        h6_part(v3)


def h6_part(df):
    df = df.copy()
    df["logk_A"] = mean_logk_A(df)
    rho = stats.spearmanr(df["type1Score"], df["logk_A"], nan_policy="omit")
    say("type1Score vs mean log k (block A): rho=%.3f p=%.5f" % (rho.statistic, rho.pvalue))
    for c in CONTEXTS:
        r = stats.spearmanr(df["type1Score"], np.log(df["A_%s_k" % c]), nan_policy="omit")
        say("  %s: rho=%.3f p=%.5f" % (c, r.statistic, r.pvalue))
    if df["flipped_yes"].nunique() == 2:
        try:
            m = smf.logit("flipped_yes ~ type1Score", data=df).fit(disp=0)
            orr = np.exp(m.params["type1Score"])
            lo, hi = np.exp(m.conf_int().loc["type1Score"])
            say("Logistic flipped ~ type1Score: OR=%.3f [%.3f, %.3f] p=%.5f" % (orr, lo, hi, m.pvalues["type1Score"]))
        except Exception as e:
            say("Logistic regression failed: %s" % e)
    else:
        say("Logistic regression skipped: flipped has one value only.")


def taps_long(df):
    rows = []
    for _, r in df.iterrows():
        try:
            taps = json.loads(r["trialsJSON"])
        except (TypeError, ValueError):
            continue
        # Position of each tap within its own task; 0 = first question, which also includes reading time
        pos = {}
        for t in taps:
            step = t.get("step", "")
            if "offer" not in t:
                continue
            frame = step.split("_")[0]
            ctx = step.split("_")[-1]
            if step == "nudge":
                frame = "nudge"
                ctx = "nudge"
            ind = r.get(step + "_ind")
            n = pos.get(step, 0)
            pos[step] = n + 1
            rows.append({"id": r["id"], "step": step, "frame": frame, "ctx": ctx, "offer": t["offer"],
                         "choice": t["choice"], "rt": t["rt"], "ind": ind,
                         "version": r.get("version", "v1"), "pos": n})
    return pd.DataFrame(rows)


def h7(df):
    say("\n== H7 decision time ==")
    tl = taps_long(df)
    tl = tl[(tl["rt"] > 150) & (tl["rt"] < 60000)]
    ab = tl[tl["frame"].isin(FRAMES)]
    per = ab.groupby(["id", "frame"])["rt"].median().unstack()
    per = per.dropna()
    w = stats.wilcoxon(per["A"], per["B"])
    say("Median RT today-vs-later (A) %.0f ms vs later-vs-later (B) %.0f ms; Wilcoxon p=%.5f r_rb=%.3f (n=%d)"
        % (per["A"].median(), per["B"].median(), w.pvalue, rank_biserial_paired(per["A"], per["B"]), len(per)))
    ff = df[["flipNear_rt", "flipFar_rt"]].dropna()
    w2 = stats.wilcoxon(ff["flipNear_rt"], ff["flipFar_rt"])
    say("Classic pair RT: near %.0f ms vs far %.0f ms; Wilcoxon p=%.5f" % (ff["flipNear_rt"].median(), ff["flipFar_rt"].median(), w2.pvalue))
    # Distance of each offer from the person's own switch point, as a share of the task range
    # The first question of each task includes reading the new question, so it is left out here
    ab = ab[ab["pos"] > 0]
    span = ab["ctx"].map({"gain": 750, "loss": 750, "friend": 750, "health": 30})
    # Health runs to 80 days in v2
    span = span.where(~((ab["ctx"] == "health") & (ab["version"] == "v2")), 60)
    ab = ab.assign(dist=(ab["offer"] - ab["ind"]).abs() / span, logrt=np.log(ab["rt"]))
    ab = ab.dropna(subset=["dist"])
    rhos = []
    for _, g in ab.groupby("id"):
        if g["dist"].nunique() > 2:
            rhos.append(stats.spearmanr(g["dist"], g["logrt"]).statistic)
    rhos = pd.Series(rhos).dropna()
    if len(rhos) > 1:
        w3 = stats.wilcoxon(rhos)
        say("Within-person Spearman(distance from switch point, log RT): median rho=%.3f, Wilcoxon vs 0 p=%.5f (n=%d)"
            % (rhos.median(), w3.pvalue, len(rhos)))
        say("Expected: negative rho (slower near the switch point).")
    bins = pd.cut(ab["dist"], [0, 0.05, 0.1, 0.2, 0.3, 0.5, 1.0], include_lowest=True)
    curve = ab.groupby(bins, observed=True)["rt"].median()
    say("Median RT by distance from switch point:")
    say(curve.round(0).to_string())
    curve.to_csv(os.path.join(OUT, "h7_rt_by_distance.csv"))
    return ab


def regression(df):
    say("\n== Regression: log k ~ context + frame + type1Score + trust + stress + spending + priorKnowledge + otherSurvey + order ==")
    rows = []
    for _, r in df.iterrows():
        for c in CONTEXTS:
            for f in FRAMES:
                k = r["%s_%s_k" % (f, c)]
                if pd.notna(k) and k > 0:
                    rows.append({"id": r["id"], "logk": np.log(k), "context": c, "frame": f,
                                 "type1Score": r["type1Score"], "trust": r["trust"], "stress": r["stress"],
                                 "spending": r["spending"], "priorKnowledge": r["priorKnowledge"],
                                 "otherSurvey": r["otherSurvey"], "order": r["order"]})
    long = pd.DataFrame(rows).dropna()
    formula = ("logk ~ C(context, Treatment('gain')) + C(frame, Treatment('B')) + type1Score + trust + stress"
               " + C(spending) + C(priorKnowledge) + C(otherSurvey) + C(order)")
    m = smf.ols(formula, data=long).fit(cov_type="cluster", cov_kwds={"groups": pd.factorize(long["id"])[0]})
    say("OLS, %d observations from %d people, SEs clustered by person" % (len(long), long["id"].nunique()))
    say(m.summary().tables[1].as_text())
    with open(os.path.join(OUT, "regression.txt"), "w", encoding="utf-8") as fh:
        fh.write(m.summary().as_text())
    return m


# ---------------------------------------------------------------- figures


def boot_ci(x, fn, n=2000, seed=1):
    rng = np.random.default_rng(seed)
    x = np.asarray(x)
    x = x[~np.isnan(x)]
    if len(x) < 2:
        return np.nan, np.nan
    vals = [fn(rng.choice(x, len(x))) for _ in range(n)]
    return np.percentile(vals, 2.5), np.percentile(vals, 97.5)


def fig_discount_curves(df):
    fig, ax = plt.subplots(figsize=(7, 4.6), facecolor=SURFACE)
    style_axes(ax)
    days = [0, 30, 60]
    for i, c in enumerate(CONTEXTS):
        dA = V[c] / df["A_%s_ind" % c]
        dB = V[c] / df["B_%s_ind" % c]
        # Discount factor at 60 days chains block A (0->30) and block B (30->60)
        d60 = dA * dB
        meds = [1.0, dA.median(), d60.median()]
        lo30, hi30 = boot_ci(dA, np.median)
        lo60, hi60 = boot_ci(d60, np.median, seed=2)
        # Small horizontal offset per context so error bars do not overlap
        x = [d + (i - 1.5) * 0.9 for d in days]
        ax.plot(x, meds, color=COLORS[c], linewidth=2, marker="o", markersize=8,
                markeredgecolor=SURFACE, markeredgewidth=2, label=c, zorder=3)
        ax.errorbar([x[1], x[2]], meds[1:], yerr=[[meds[1] - lo30, meds[2] - lo60], [hi30 - meds[1], hi60 - meds[2]]],
                    fmt="none", ecolor=COLORS[c], elinewidth=1.2, capsize=3, zorder=2)
    ax.set_xticks(days)
    ax.set_xticklabels(["today", "30 days", "60 days"])
    ax.set_xlim(-5, 72)
    ax.set_ylabel("Discount factor (sooner / indifference)")
    ax.set_title("Discount curve per context (median, 95% bootstrap CI)", loc="left", fontsize=11, color=INK)
    ax.legend(frameon=False, fontsize=9, loc="lower left")
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "fig1_discount_curves.png"), dpi=200)
    plt.close(fig)


def fig_heatmap(df):
    df = df.copy()
    t1_cut = df["type1Score"].median()
    groups = [
        ("Standard frame", df["nudgeGroup"] == "standard"),
        ("Hidden zero", df["nudgeGroup"] == "hiddenZero"),
        ("Low anchor", df["anchorGroup"] == "low"),
        ("High anchor", df["anchorGroup"] == "high"),
        ("Type 1 <= %g" % t1_cut, df["type1Score"] <= t1_cut),
        ("Type 1 > %g" % t1_cut, df["type1Score"] > t1_cut),
    ]
    mat = np.full((len(CONTEXTS), len(groups)), np.nan)
    ns = np.zeros((len(CONTEXTS), len(groups)), dtype=int)
    for i, c in enumerate(CONTEXTS):
        # Present bias: log k(A) - log k(B); above 0 = more impatient when "today" is an option
        pb = np.log(df["A_%s_k" % c]) - np.log(df["B_%s_k" % c])
        for j, (_, mask) in enumerate(groups):
            vals = pb[mask].dropna()
            ns[i, j] = len(vals)
            if len(vals):
                mat[i, j] = vals.median()
    lim = np.nanmax(np.abs(mat))
    if not np.isfinite(lim) or lim == 0:
        lim = 1.0
    cmap = LinearSegmentedColormap.from_list("div", ["#2a78d6", "#f0efec", "#eb6834"])
    fig, ax = plt.subplots(figsize=(8.2, 3.9), facecolor=SURFACE)
    im = ax.imshow(mat, cmap=cmap, vmin=-lim, vmax=lim, aspect="auto")
    ax.set_xticks(range(len(groups)))
    ax.set_xticklabels([g[0] for g in groups], fontsize=9, color=INK2)
    ax.set_yticks(range(len(CONTEXTS)))
    ax.set_yticklabels(CONTEXTS, fontsize=9, color=INK2)
    for i in range(len(CONTEXTS)):
        for j in range(len(groups)):
            if np.isfinite(mat[i, j]):
                ax.text(j, i, "%.2f\nn=%d" % (mat[i, j], ns[i, j]), ha="center", va="center", fontsize=8, color=INK)
    for side in ax.spines:
        ax.spines[side].set_visible(False)
    cb = fig.colorbar(im, ax=ax, fraction=0.03, pad=0.02)
    cb.set_label("median log k(A) - log k(B)", color=INK2, fontsize=9)
    cb.outline.set_visible(False)
    ax.set_title("Inconsistency (present bias) by context and condition", loc="left", fontsize=11, color=INK)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "fig2_inconsistency_heatmap.png"), dpi=200)
    plt.close(fig)
    pd.DataFrame(mat, index=CONTEXTS, columns=[g[0] for g in groups]).to_csv(os.path.join(OUT, "fig2_heatmap_values.csv"))


def inconsistency_map(df):
    """Share of people who are present-biased, future-biased or consistent, per context.

    Compares the switch point with "today" (block A) and without it (block B), same 30-day wait.
    Present-biased: A is higher than B by more than two final bisection intervals (needs more to wait
    when today is an option; for fines, accepts a bigger later fine to avoid paying today).
    Future-biased: the reverse. Consistent: within that tolerance.
    """
    say("\n== Inconsistency map (time inconsistency per context, block A vs block B) ==")
    rows = []
    # Inconsistent in at least one context
    any_inc = pd.Series(False, index=df.index)
    for c in CONTEXTS:
        span = 750
        if c == "health":
            span = 30
        tol = pd.Series(span / 16.0, index=df.index)
        if c == "health":
            # v2 and later run health from 20 to 80 days, with 6 steps
            tol = tol.where(df["version"] == "v1", 60 / 32.0)
        diff = df["A_%s_ind" % c] - df["B_%s_ind" % c]
        ok = diff.notna()
        any_inc = any_inc | (diff.abs() > tol)
        pb = (diff[ok] > tol[ok]).mean()
        fb = (diff[ok] < -tol[ok]).mean()
        rows.append({"context": c, "n": int(ok.sum()), "present_biased_pct": round(100 * pb, 1),
                     "future_biased_pct": round(100 * fb, 1), "consistent_pct": round(100 * (1 - pb - fb), 1),
                     "inconsistent_pct": round(100 * (pb + fb), 1)})
    t = pd.DataFrame(rows)
    say(t.to_string(index=False))
    say("Inconsistent in at least one context: %.0f%%" % (100 * any_inc.mean()))
    return t


def beta_delta(df):
    # Quasi-hyperbolic model: block B gives delta^30 = V/ind_B; block A gives beta*delta^30 = V/ind_A
    rows = []
    for c in CONTEXTS:
        beta = df["B_%s_ind" % c] / df["A_%s_ind" % c]
        delta_day = (V[c] / df["B_%s_ind" % c]) ** (1.0 / 30)
        delta_month = delta_day ** 30
        blo, bhi = boot_ci(beta, np.median)
        dlo, dhi = boot_ci(delta_month, np.median, seed=3)
        w = stats.wilcoxon(beta.dropna() - 1)
        rows.append({"context": c, "n": int(beta.notna().sum()), "beta_median": beta.median(), "beta_lo": blo,
                     "beta_hi": bhi, "pct_beta_lt_1": 100 * (beta < 1).mean(), "p_beta_ne_1": w.pvalue,
                     "delta30_median": delta_month.median(), "delta30_lo": dlo, "delta30_hi": dhi})
    t = pd.DataFrame(rows)
    say("\n== Beta-delta per context (beta < 1 = present bias) ==")
    say(t.round(4).to_string(index=False))
    t.to_csv(os.path.join(OUT, "beta_delta.csv"), index=False)
    return t


def fig_beta_delta(t):
    fig, axes = plt.subplots(1, 2, figsize=(8.4, 3.8), facecolor=SURFACE)
    panels = [("beta", "beta (present bias)", 1.0), ("delta30", "delta per 30 days (long-run)", None)]
    for ax, (key, title, ref) in zip(axes, panels):
        style_axes(ax)
        for i, r in t.iterrows():
            m = r[key + "_median"]
            ax.errorbar([i], [m], yerr=[[m - r[key + "_lo"]], [r[key + "_hi"] - m]], fmt="o", markersize=8,
                        color=COLORS[r["context"]], markeredgecolor=SURFACE, markeredgewidth=2, elinewidth=2, capsize=0)
            ax.annotate("%.3f" % m, (i, m), xytext=(10, 0), textcoords="offset points", va="center", fontsize=8, color=INK2)
        if ref is not None:
            ax.axhline(ref, color=INK2, linewidth=1, linestyle="--")
            ax.text(-0.55, ref, "no present bias", fontsize=8, color=INK2, ha="left", va="bottom")
        ax.set_xticks(range(len(t)))
        ax.set_xticklabels(t["context"])
        ax.set_xlim(-0.6, len(t) - 0.4)
        ax.set_title(title, loc="left", fontsize=10, color=INK)
    fig.suptitle("Beta-delta per context (median, 95% bootstrap CI)", x=0.02, ha="left", fontsize=11, color=INK)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "fig3_beta_delta.png"), dpi=200)
    plt.close(fig)


# ---------------------------------------------------------------- main


def describe(df):
    say("\n== Sample ==")
    say("Age: median %.0f (range %.0f-%.0f)" % (df["age"].median(), df["age"].min(), df["age"].max()))
    for col in ["describes", "order", "nudgeGroup", "anchorGroup", "priorKnowledge", "otherSurvey"]:
        say("%s: %s" % (col, df[col].value_counts().to_dict()))
    cens = {}
    for c in CONTEXTS:
        for f in FRAMES:
            cens["%s_%s" % (f, c)] = df["%s_%s_censored" % (f, c)].value_counts().to_dict()
    say("Censoring (high = true k is at least the value; low = at most): %s" % cens)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    os.makedirs(OUT, exist_ok=True)
    global KEEP, BENCH, SYNTH
    if "--with-synthetic" in sys.argv:
        SYNTH = True
        sys.argv.remove("--with-synthetic")
    if "--bench" in sys.argv:
        BENCH = True
        sys.argv.remove("--bench")
    # Rupee signs must print on any console
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if len(sys.argv) > 2:
        KEEP = sys.argv[2]
    raw = load(sys.argv[1])
    df, sens, strict = exclusions(raw)
    if len(df) < 5:
        say("Too few responses after exclusions to analyse.")
        sys.exit(1)
    describe(df)
    h1(df, "main sample").to_csv(os.path.join(OUT, "h1_wilcoxon.csv"), index=False)
    h2(df).to_csv(os.path.join(OUT, "h2_pairwise.csv"), index=False)
    h3(df)
    inconsistency_map(df).to_csv(os.path.join(OUT, "inconsistency_map.csv"), index=False)
    h4(df)
    h5(df)
    h6(df)
    h7(df)
    regression(df)
    t = beta_delta(df)
    fig_discount_curves(df)
    fig_heatmap(df)
    fig_beta_delta(t)
    say("\n== Sensitivity check (H1, H2 without prior-knowledge / other-survey respondents) ==")
    if len(sens) >= 5:
        h1(sens, "sensitivity").to_csv(os.path.join(OUT, "h1_wilcoxon_sensitivity.csv"), index=False)
        h2(sens).to_csv(os.path.join(OUT, "h2_pairwise_sensitivity.csv"), index=False)
    if len(strict) >= 5:
        say("\n== Strict check (H1, H2, H4, H5 without any attention-check fails) ==")
        h1(strict, "strict").to_csv(os.path.join(OUT, "h1_wilcoxon_strict.csv"), index=False)
        h2(strict).to_csv(os.path.join(OUT, "h2_pairwise_strict.csv"), index=False)
        h4(strict)
        h5(strict)
    else:
        say("Skipped: fewer than 5 respondents.")
    with open(os.path.join(OUT, "report.txt"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(report_lines))
    print("\nSaved to " + OUT)


if __name__ == "__main__":
    main()
