"""Final combined analysis: the main app (index.html) and the short proposal survey (proposal.html).

Usage:
    py analysis/final.py path/to/responses.csv

Runs on the raw Sheet export (it repairs the split id column itself). Uses the same exclusions as
analyze.py (main) and analyze_proposal.py (proposal), then adds the analyses that need both studies
or that the two scripts do not run:
  1. Sample flow for both studies.
  2. k per context with bootstrap CIs, side by side for both studies.
  3. Sign effect across domains: money gain vs fine (within person, both studies) and
     health gain (headache-free days, main) vs health loss (days of flu, proposal), between people.
  4. Present bias with effect sizes (dz of log k(A) - log k(B)) and the smallest effect the sample could detect.
  5. Classic reversal pair: delay (present bias) against question position (order) in the randomised rows.
  6. Trait vs state: Spearman of k across contexts with bootstrap CIs, both studies.
Writes report.txt, key_numbers.json, tables and figures to analysis/out/final/.
"""
import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats
import statsmodels.api as sm
import statsmodels.formula.api as smf

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import analyze  # noqa: E402
import analyze_proposal  # noqa: E402

OUT = os.path.join(HERE, "out", "final")
CONTEXTS = ["gain", "loss", "health", "friend"]
# Validated categorical slots (dataviz reference palette), same as analyze.py
COLORS = {"gain": "#2a78d6", "loss": "#eb6834", "health": "#1baf7a", "friend": "#eda100"}
INK = "#0b0b0b"
INK2 = "#52514e"
GRID = "#e6e5e1"
SURFACE = "#fcfcfb"
LINES = []
KEY = {}


def say(text=""):
    print(text)
    LINES.append(str(text))


def boot_median_ci(x, n=4000, seed=7):
    rng = np.random.default_rng(seed)
    x = np.asarray(pd.Series(x).dropna(), dtype=float)
    meds = np.median(rng.choice(x, (n, len(x))), axis=1)
    return float(np.percentile(meds, 2.5)), float(np.percentile(meds, 97.5))


def boot_spearman_ci(a, b, n=4000, seed=11):
    rng = np.random.default_rng(seed)
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    vals = []
    for _ in range(n):
        i = rng.integers(0, len(a), len(a))
        vals.append(stats.spearmanr(a[i], b[i]).statistic)
    return float(np.nanpercentile(vals, 2.5)), float(np.nanpercentile(vals, 97.5))


def style(ax):
    ax.set_facecolor(SURFACE)
    for side in ["top", "right", "left"]:
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(INK2)
    ax.tick_params(colors=INK2, labelsize=9)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


# ---------------------------------------------------------------- loading


def load_main(path):
    analyze.report_lines = []
    raw = analyze.load(path)
    main, sens, strict = analyze.exclusions(raw)
    KEY["main_flow"] = {"after_dedupe_and_tests": int(len(raw)), "careless_dropped": int(len(raw) - len(main)),
                        "analysed": int(len(main)), "strict": int(len(strict))}
    return main, strict


def load_proposal(path):
    df = analyze.repair_ids(pd.read_csv(path))
    df = df[df["survey"] == "proposal"]
    df = df.sort_values("receivedAt").drop_duplicates("id", keep="first")
    df["test"] = df["test"].fillna("no").replace("", "no")
    df = df[df["test"] == "no"]
    n0 = len(df)
    df = df[df["consent"] == "yes"]
    # Same rule as analyze_proposal.py: drop rushed responses (over 25% of taps under 400 ms),
    # keep a failed dominance check when the other answers were at reading speed
    rushed = df["trialsJSON"].apply(analyze_proposal.fast_share) > analyze_proposal.FAST_SHARE
    failed = df["attentionFail"] == "yes"
    KEY["proposal_rushed"] = {"failed_check": int((failed & rushed).sum()), "passed_check": int((~failed & rushed).sum()),
                              "kept_failed_check": int((failed & ~rushed).sum())}
    df = df[~rushed].copy()
    V = {"gain": 500, "loss": 500, "health": 10, "friend": 500}
    for c in CONTEXTS:
        df["A_%s_k" % c] = pd.to_numeric(df["A_%s_k" % c], errors="coerce")
        ind = pd.to_numeric(df["A_%s_ind" % c], errors="coerce")
        df["A_%s_ind" % c] = ind
        # Recompute the floor flag (the app missed it for 1-day health steps)
        step = 5
        if c == "health":
            step = 1
        df.loc[ind <= V[c] + step, "A_%s_censored" % c] = "low"
    KEY["proposal_flow"] = {"responses": int(n0), "dropped_rushed": int(n0 - len(df)), "analysed": int(len(df))}
    return df.reset_index(drop=True)


# ---------------------------------------------------------------- analyses


def sample_flow(main, prop):
    say("== 1. Samples ==")
    say("Main app: %s" % KEY["main_flow"])
    say("  versions: %s" % main["version"].value_counts().to_dict())
    say("  who: %s | age median %.0f" % (main["describes"].value_counts().to_dict(), main["age"].median()))
    say("Proposal survey: %s" % KEY["proposal_flow"])
    say("  year: %s" % prop["year"].value_counts().to_dict())
    say("  field: %s" % prop["field"].value_counts().to_dict())
    prop_age = pd.to_numeric(prop["age"], errors="coerce")
    say("  age median %.0f (range %.0f-%.0f)" % (prop_age.median(), prop_age.min(), prop_age.max()))


def context_table(main, prop):
    say("\n== 2. k per context (today vs 30 days), median with 95% bootstrap CI ==")
    rows = []
    for study, df in [("main", main), ("proposal", prop)]:
        for c in CONTEXTS:
            k = df["A_%s_k" % c].dropna()
            lo, hi = boot_median_ci(k)
            cens = df["A_%s_censored" % c].value_counts(normalize=True)
            rows.append({"study": study, "context": c, "n": len(k), "median_k": k.median(), "ci_lo": lo, "ci_hi": hi,
                         "pct_floor": 100 * cens.get("low", 0.0), "pct_ceiling": 100 * cens.get("high", 0.0),
                         "annual_rate_pct": 100 * k.median() * 365})
    t = pd.DataFrame(rows)
    say(t.round(5).to_string(index=False))
    say("annual_rate_pct = simple hyperbolic k x 365, for intuition only.")
    t.to_csv(os.path.join(OUT, "k_by_context.csv"), index=False)
    KEY["k_by_context"] = t.round(5).to_dict("records")
    return t


def sign_effect(main, prop):
    say("\n== 3. Sign effect across domains ==")
    out = {}
    for study, df in [("main", main), ("proposal", prop)]:
        g = df["A_gain_k"]
        l = df["A_loss_k"]
        ok = g.notna() & l.notna()
        w = stats.wilcoxon(g[ok], l[ok])
        rb = analyze.rank_biserial_paired(g[ok], l[ok])
        pct = 100 * (g[ok] > l[ok]).mean()
        say("%s: money gain k > fine k for %.0f%% of people; Wilcoxon p=%.2g, r_rb=%.2f (n=%d)" % (study, pct, w.pvalue, rb, ok.sum()))
        out["money_" + study] = {"pct_gain_gt_loss": pct, "p": w.pvalue, "r_rb": rb, "n": int(ok.sum())}
    hg = main["A_health_k"].dropna()
    hl = prop["A_health_k"].dropna()
    u = stats.mannwhitneyu(hg, hl)
    rb = analyze.rank_biserial_indep(hg, hl)
    say("health gain (headache-free days, main, n=%d) median k=%.4f vs health loss (flu days, proposal, n=%d) median k=%.4f;"
        " Mann-Whitney p=%.2g, r_rb=%.2f" % (len(hg), hg.median(), len(hl), hl.median(), u.pvalue, rb))
    say("  Between-subjects and different instruments (sooner 20 vs 10 days), so read as convergent, not causal.")
    out["health_between"] = {"median_gain": hg.median(), "median_loss": hl.median(), "p": u.pvalue, "r_rb": rb}
    # Acting on a cost now: always paid the fine today / chose to be ill today, even when waiting cost almost nothing
    say("Always 'get it over with' (k at floor): fine %.0f%% (main), %.0f%% (proposal); flu %.0f%% (proposal)"
        % (100 * (main["A_loss_censored"] == "low").mean(), 100 * (prop["A_loss_censored"] == "low").mean(),
           100 * (prop["A_health_censored"] == "low").mean()))
    KEY["sign_effect"] = out


def present_bias(main):
    say("\n== 4. Present bias: block A (today vs 30 days) against block B (30 vs 60 days) ==")
    rows = []
    for c in CONTEXTS:
        d = (np.log(main["A_%s_k" % c]) - np.log(main["B_%s_k" % c])).replace([np.inf, -np.inf], np.nan).dropna()
        dz = d.mean() / d.std(ddof=1)
        rng = np.random.default_rng(3)
        boots = []
        for _ in range(4000):
            s = rng.choice(d.values, len(d))
            boots.append(s.mean() / s.std(ddof=1))
        rows.append({"context": c, "n": len(d), "mean_logk_diff": d.mean(), "dz": dz,
                     "dz_lo": np.percentile(boots, 2.5), "dz_hi": np.percentile(boots, 97.5),
                     "pct_A_gt_B": 100 * (d > 0).mean(), "pct_equal": 100 * (d == 0).mean(), "pct_A_lt_B": 100 * (d < 0).mean()})
    t = pd.DataFrame(rows)
    say(t.round(3).to_string(index=False))
    n = len(main)
    # Smallest standardized paired effect detectable with 80% power at alpha .05 (two-sided t approximation)
    mde = (stats.norm.ppf(0.975) + stats.norm.ppf(0.8)) / np.sqrt(n)
    say("Smallest detectable effect at n=%d (80%% power, alpha .05): dz = %.2f (Wilcoxon needs about 5%% more people)" % (n, mde))
    KEY["present_bias"] = {"table": t.round(3).to_dict("records"), "mde_dz": mde}
    t.to_csv(os.path.join(OUT, "present_bias_dz.csv"), index=False)


def reversal(main, prop):
    say("\n== 5. Classic reversal pair: delay or question position? ==")
    rows = []
    # Proposal: Rs 100 today vs Rs 110 tomorrow; Rs 100 in 30 vs Rs 110 in 31 days. Main v3: Rs 1000 today vs 1100 in 1 week; 4 vs 5 weeks.
    p = prop.copy()
    p["near_later"] = (p["flipNear"] == "₹110 tomorrow").astype(int)
    p["far_later"] = (p["flipFar"] == "₹110 in 31 days").astype(int)
    p["study"] = "proposal"
    m = main.copy()
    m["near_later"] = (m["flipNear"] == "₹1100 in 1 week").astype(int)
    m["far_later"] = (m["flipFar"] == "₹1100 in 5 weeks").astype(int)
    m["study"] = "main"
    allrows = pd.concat([p[["id", "study", "flipOrder", "near_later", "far_later", "version"]],
                         m[["id", "study", "flipOrder", "near_later", "far_later", "version"]]])
    for study, g in allrows.groupby("study"):
        classic = int(((g["near_later"] == 0) & (g["far_later"] == 1)).sum())
        rev = int(((g["near_later"] == 1) & (g["far_later"] == 0)).sum())
        ci = stats.binomtest(classic, len(g)).proportion_ci()
        say("%s (n=%d): classic %d (%.1f%%, 95%% CI %.1f-%.1f), reverse %d (%.1f%%)"
            % (study, len(g), classic, 100 * classic / len(g), 100 * ci.low, 100 * ci.high, rev, 100 * rev / len(g)))
    # Only rows where the pair order was randomised can separate delay from position
    rnd = allrows[(allrows["study"] == "proposal") | (allrows["version"] == "v3")].copy()
    say("Randomised rows: %d (%s)" % (len(rnd), rnd.groupby(["study", "flipOrder"]).size().to_dict()))
    for o, g in rnd.groupby("flipOrder"):
        classic = int(((g["near_later"] == 0) & (g["far_later"] == 1)).sum())
        rev = int(((g["near_later"] == 1) & (g["far_later"] == 0)).sum())
        rows.append({"flipOrder": o, "n": len(g), "classic": classic, "reverse": rev})
        say("  %s: classic %d, reverse %d" % (o, classic, rev))
    t = pd.DataFrame(rows)
    disc = t["classic"].sum() + t["reverse"].sum()
    # People who changed answer: did they pick sooner on the pair they saw first?
    first_sooner = int(t.loc[t["flipOrder"] == "nearFirst", "classic"].sum() + t.loc[t["flipOrder"] == "farFirst", "reverse"].sum())
    near_sooner = int(t["classic"].sum())
    bp = stats.binomtest(first_sooner, disc).pvalue
    bd = stats.binomtest(near_sooner, disc).pvalue
    say("Of %d people who changed their answer: %d took the sooner option on the FIRST pair they saw (p=%.3f vs 50%%);"
        " %d took it on the NEAR pair, as present bias predicts (p=%.3f)" % (disc, first_sooner, bp, near_sooner, bd))
    # Within-person logistic model: P(choose later) ~ near pair + asked first, GEE clustered by person
    long = []
    for _, r in rnd.iterrows():
        near_first = int(r["flipOrder"] == "nearFirst")
        long.append({"id": r["id"], "later": r["near_later"], "near": 1, "first": near_first, "study": r["study"]})
        long.append({"id": r["id"], "later": r["far_later"], "near": 0, "first": 1 - near_first, "study": r["study"]})
    long = pd.DataFrame(long)
    gee = smf.gee("later ~ near + first + C(study)", groups="id", data=long, family=sm.families.Binomial()).fit()
    orr = np.exp(gee.params)
    ci = np.exp(gee.conf_int())
    say("GEE logistic, P(choose later): near pair OR=%.2f [%.2f, %.2f] p=%.3f; asked first OR=%.2f [%.2f, %.2f] p=%.3f"
        % (orr["near"], ci.loc["near", 0], ci.loc["near", 1], gee.pvalues["near"],
           orr["first"], ci.loc["first", 0], ci.loc["first", 1], gee.pvalues["first"]))
    KEY["reversal"] = {"by_order": t.to_dict("records"), "discordant": int(disc), "first_sooner": first_sooner,
                       "p_position": bp, "near_sooner": near_sooner, "p_delay": bd,
                       "or_near": orr["near"], "p_near": gee.pvalues["near"], "or_first": orr["first"], "p_first": gee.pvalues["first"]}
    return t


def trait_state(main, prop):
    say("\n== 6. Trait or state? Spearman of k across contexts (95% bootstrap CI) ==")
    rows = []
    for study, df in [("main", main), ("proposal", prop)]:
        for i in range(4):
            for j in range(i + 1, 4):
                a = df["A_%s_k" % CONTEXTS[i]]
                b = df["A_%s_k" % CONTEXTS[j]]
                ok = a.notna() & b.notna()
                rho = stats.spearmanr(a[ok], b[ok]).statistic
                lo, hi = boot_spearman_ci(a[ok], b[ok])
                rows.append({"study": study, "pair": CONTEXTS[i] + "-" + CONTEXTS[j], "rho": rho, "lo": lo, "hi": hi})
    t = pd.DataFrame(rows)
    say(t.round(2).to_string(index=False))
    # Same-context reliability: block A against block B in the main app
    rel = {}
    for c in CONTEXTS:
        rel[c] = stats.spearmanr(main["A_%s_k" % c], main["B_%s_k" % c], nan_policy="omit").statistic
    say("Same context, block A vs block B (main): %s" % {c: round(v, 2) for c, v in rel.items()})
    say("Cross-context correlations well below these within-context ones point to context-specific (state) discounting.")
    KEY["trait_state"] = {"pairs": t.round(3).to_dict("records"), "within_context_AB": rel}
    t.to_csv(os.path.join(OUT, "trait_state.csv"), index=False)


# ---------------------------------------------------------------- figures


def fig_context(t):
    fig, ax = plt.subplots(figsize=(7.6, 4.2), facecolor=SURFACE)
    style(ax)
    xs = {"main": 0, "proposal": 1}
    for i, c in enumerate(CONTEXTS):
        for study in ["main", "proposal"]:
            r = t[(t["study"] == study) & (t["context"] == c)].iloc[0]
            x = xs[study] * 5 + i
            ax.errorbar([x], [r["median_k"]], yerr=[[r["median_k"] - r["ci_lo"]], [r["ci_hi"] - r["median_k"]]],
                        fmt="o", color=COLORS[c], markersize=9, markeredgecolor=SURFACE, markeredgewidth=2,
                        elinewidth=2, capsize=0, zorder=3)
            ax.annotate("%.4f" % r["median_k"], (x, r["median_k"]), xytext=(9, 0), textcoords="offset points",
                        va="center", fontsize=8, color=INK2)
    ax.set_yscale("log")
    ticks = list(range(4)) + list(range(5, 9))
    labels = ["money\ngain", "fine", "health\n(headache-free)", "friend"] + ["money\ngain", "fine", "health\n(flu)", "friend"]
    ax.set_xticks(ticks)
    ax.set_xticklabels(labels, fontsize=8, color=INK2)
    ax.text(1.5, 1.02, "Main app (n=%d)" % t[t["study"] == "main"]["n"].max(), transform=ax.get_xaxis_transform(),
            ha="center", fontsize=9, color=INK)
    ax.text(6.5, 1.02, "Short survey (n=%d)" % t[t["study"] == "proposal"]["n"].max(), transform=ax.get_xaxis_transform(),
            ha="center", fontsize=9, color=INK)
    ax.axvline(4, color=GRID, linewidth=1)
    ax.set_ylabel("Discount rate k per day (log scale)", color=INK2, fontsize=9)
    ax.set_title("Impatience by context: median k, today vs 30 days (95% CI)", loc="left", fontsize=11, color=INK, pad=22)
    ax.text(1.0, -0.2, "No bar: over half the people sit at the floor, so the CI collapses onto the median.",
            transform=ax.transAxes, ha="right", fontsize=7.5, color=INK2)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "figA_k_by_context.png"), dpi=200)
    plt.close(fig)


def fig_reversal(t):
    fig, ax = plt.subplots(figsize=(6.4, 3.8), facecolor=SURFACE)
    style(ax)
    order = ["nearFirst", "farFirst"]
    names = {"nearFirst": "Near pair asked first", "farFirst": "Far pair asked first"}
    w = 0.34
    for i, o in enumerate(order):
        r = t[t["flipOrder"] == o].iloc[0]
        for j, (col, color, lab) in enumerate([("classic", "#2a78d6", "classic flip"), ("reverse", "#eb6834", "reverse flip")]):
            x = i + (j - 0.5) * (w + 0.03)
            ax.bar([x], [r[col]], width=w, color=color, label=lab if i == 0 else None, zorder=3)
            ax.text(x, r[col] + 0.3, "%d" % r[col], ha="center", fontsize=9, color=INK)
    ax.set_xticks([0, 1])
    ax.set_xticklabels([names[o] + "\n(n=%d)" % t[t["flipOrder"] == o]["n"].iloc[0] for o in order], fontsize=9, color=INK2)
    ax.set_ylabel("People", color=INK2, fontsize=9)
    ax.legend(frameon=False, fontsize=9, loc="upper right")
    ax.set_title("Classic and reverse flips by which pair came first (randomised rows)", loc="left", fontsize=11, color=INK)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "figB_reversal_by_order.png"), dpi=200)
    plt.close(fig)


def fig_floor(main, prop):
    fig, ax = plt.subplots(figsize=(7.2, 3.8), facecolor=SURFACE)
    style(ax)
    bars = [("Pay fine today\n(main)", (main["A_loss_censored"] == "low").mean(), COLORS["loss"]),
            ("Pay fine today\n(short survey)", (prop["A_loss_censored"] == "low").mean(), COLORS["loss"]),
            ("Be ill today\n(short survey)", (prop["A_health_censored"] == "low").mean(), COLORS["health"]),
            ("Never wait for money\n(main)", (main["A_gain_censored"] == "high").mean(), COLORS["gain"]),
            ("Never wait for\nheadache relief (main)", (main["A_health_censored"] == "high").mean(), COLORS["health"])]
    for i, (lab, v, col) in enumerate(bars):
        ax.bar([i], [100 * v], width=0.6, color=col, zorder=3)
        ax.text(i, 100 * v + 1.5, "%.0f%%" % (100 * v), ha="center", fontsize=9, color=INK)
    ax.set_xticks(range(len(bars)))
    ax.set_xticklabels([b[0] for b in bars], fontsize=8, color=INK2)
    ax.set_ylim(0, 100)
    ax.set_ylabel("% of people, every question", color=INK2, fontsize=9)
    ax.set_title("Costs: get it over with now. Gains: some never wait", loc="left", fontsize=11, color=INK)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "figC_get_it_over_with.png"), dpi=200)
    plt.close(fig)


def fig_rt(main):
    tl = analyze.taps_long(main)
    tl = tl[(tl["rt"] > 150) & (tl["rt"] < 60000) & tl["frame"].isin(["A", "B"]) & (tl["pos"] > 0)].copy()
    span = tl["ctx"].map({"gain": 750, "loss": 750, "friend": 750, "health": 30})
    span = span.where(~((tl["ctx"] == "health") & (tl["version"] != "v1")), 60)
    tl["dist"] = (tl["offer"] - tl["ind"]).abs() / span
    tl["logrt"] = np.log(tl["rt"])
    tl = tl.dropna(subset=["dist"])
    # Remove each person's speed and the warm-up over question position, then bin by distance
    tl["resid"] = tl["logrt"] - tl.groupby("id")["logrt"].transform("mean")
    tl["resid"] = tl["resid"] - tl.groupby("pos")["resid"].transform("mean")
    bins = pd.cut(tl["dist"], [0, 0.03, 0.06, 0.1, 0.15, 0.25, 0.5], include_lowest=True)
    g = tl.groupby(bins, observed=True)["resid"].agg(["mean", "sem", "count"])
    pct = 100 * (np.exp(g["mean"]) - 1)
    err = 100 * (np.exp(g["mean"] + 1.96 * g["sem"]) - np.exp(g["mean"]))
    fig, ax = plt.subplots(figsize=(6.6, 3.8), facecolor=SURFACE)
    style(ax)
    x = np.arange(len(g))
    ax.plot(x, pct, color="#2a78d6", linewidth=2, marker="o", markersize=8, markeredgecolor=SURFACE, markeredgewidth=2, zorder=3)
    ax.errorbar(x, pct, yerr=err, fmt="none", ecolor="#2a78d6", elinewidth=1.2, zorder=2)
    for xi, v in zip(x, pct):
        ax.annotate("%+.0f%%" % v, (xi, v), xytext=(0, 10), textcoords="offset points", ha="center", fontsize=8, color=INK2)
    ax.axhline(0, color=INK2, linewidth=1, linestyle="--")
    ax.set_xticks(x)
    names = []
    for iv in g.index:
        names.append("%.0f-%.0f%%" % (100 * max(iv.left, 0), 100 * iv.right))
    ax.set_xticklabels(names, fontsize=8, color=INK2)
    ax.set_xlabel("Offer's distance from the person's own switch point (share of range)", color=INK2, fontsize=9)
    ax.set_ylabel("Decision time vs own average", color=INK2, fontsize=9)
    ax.set_title("Hard choices are slow: decision time near the switch point", loc="left", fontsize=11, color=INK)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "figD_rt_conflict.png"), dpi=200)
    plt.close(fig)
    g.assign(pct=pct).to_csv(os.path.join(OUT, "rt_by_distance_adjusted.csv"))
    KEY["rt_adjusted_pct"] = {str(k): round(float(v), 1) for k, v in pct.items()}


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    os.makedirs(OUT, exist_ok=True)
    analyze.OUT = OUT
    main_df, strict = load_main(sys.argv[1])
    prop = load_proposal(sys.argv[1])
    sample_flow(main_df, prop)
    t = context_table(main_df, prop)
    sign_effect(main_df, prop)
    present_bias(main_df)
    rt = reversal(main_df, prop)
    trait_state(main_df, prop)
    fig_context(t)
    fig_reversal(rt)
    fig_floor(main_df, prop)
    fig_rt(main_df)
    with open(os.path.join(OUT, "report.txt"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(LINES) + "\n")
    with open(os.path.join(OUT, "key_numbers.json"), "w", encoding="utf-8") as fh:
        json.dump(KEY, fh, indent=2, default=float)
    say("\nSaved to %s" % OUT)


if __name__ == "__main__":
    main()
