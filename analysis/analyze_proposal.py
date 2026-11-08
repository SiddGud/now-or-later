"""Analysis for the short proposal survey (proposal.html), as planned in the project proposal.

Usage:
    py analysis/analyze_proposal.py path/to/responses.csv

Uses only rows with survey = proposal. Writes report and figure to analysis/out/proposal/.
"""
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out", "proposal")
CONTEXTS = ["gain", "loss", "health", "friend"]
# Sooner amount per context (health: days of flu)
V = {"gain": 500, "loss": 500, "health": 10, "friend": 500}
COLORS = {"gain": "#2a78d6", "loss": "#eb6834", "health": "#1baf7a", "friend": "#eda100"}
LINES = []


def say(text):
    print(text)
    LINES.append(text)


def holm(p):
    p = np.asarray(p, dtype=float)
    order = np.argsort(p)
    adj = np.empty_like(p)
    running = 0.0
    for rank, i in enumerate(order):
        running = max(running, (len(p) - rank) * p[i])
        adj[i] = min(running, 1.0)
    return adj


def main():
    if len([a for a in sys.argv[1:] if not a.startswith("--")]) < 1:
        print(__doc__)
        sys.exit(1)
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    os.makedirs(OUT, exist_ok=True)
    df = pd.read_csv([a for a in sys.argv[1:] if not a.startswith("--")][0])
    if "survey" not in df.columns:
        say("No proposal-survey rows yet.")
        sys.exit(1)
    df = df[df["survey"] == "proposal"]
    df = df.sort_values("receivedAt").drop_duplicates("id", keep="first")
    df["test"] = df["test"].fillna("no").replace("", "no")
    if "--bench" in sys.argv:
        # Benchmark mode: only the lab plays made with the rule cards (#bench)
        df = df[df["test"] == "bench"]
        say("Benchmark mode: only #bench plays")
    elif "--with-synthetic" in sys.argv:
        # Real responses plus the synthetic test respondents (ids SYNP...)
        df = df[df["test"].isin(["no", "synthetic"])]
        say("With synthetic respondents")
    else:
        df = df[df["test"] == "no"]
    say("Proposal-survey responses: %d" % len(df))

    # Exclusions planned in the proposal: no consent, failed dominance check
    df = df[df["consent"] == "yes"]
    n0 = len(df)
    df = df[df["attentionFail"] != "yes"]
    say("Failed the dominance check: %d" % (n0 - len(df)))
    say("Analysed: %d" % len(df))
    if len(df) < 5:
        say("Too few responses to analyse.")
        sys.exit(1)
    for c in CONTEXTS:
        df["A_%s_k" % c] = pd.to_numeric(df["A_%s_k" % c], errors="coerce")
    say("Censoring per context: %s" % {c: df["A_%s_censored" % c].value_counts().to_dict() for c in CONTEXTS})

    # Discounting per context
    say("\n== k per context (today vs 30 days) ==")
    for c in CONTEXTS:
        say("%-6s median k = %.5f" % (c, df["A_%s_k" % c].median()))
    ks = [df["A_%s_k" % c] for c in CONTEXTS]
    fr = stats.friedmanchisquare(*ks)
    n = len(df)
    say("Friedman: chi2=%.2f p=%.5f Kendall W=%.3f" % (fr.statistic, fr.pvalue, fr.statistic / (n * 3)))
    rows = []
    for i in range(4):
        for j in range(i + 1, 4):
            a = df["A_%s_k" % CONTEXTS[i]]
            b = df["A_%s_k" % CONTEXTS[j]]
            w = stats.wilcoxon(a, b)
            rows.append({"pair": CONTEXTS[i] + " vs " + CONTEXTS[j], "W": w.statistic, "p": w.pvalue})
    t = pd.DataFrame(rows)
    t["p_holm"] = holm(t["p"])
    say(t.round(5).to_string(index=False))
    say("Proposal predicted: loss k < gain k, health k < gain k.")

    # Trait vs state
    say("\n== Spearman of k across contexts ==")
    say(pd.DataFrame({c: df["A_%s_k" % c] for c in CONTEXTS}).corr(method="spearman").round(3).to_string())

    # The reversal pair
    say("\n== Near/far reversal (100 today vs 110 tomorrow; day 30 vs day 31) ==")
    classic = int((df["flipped"] == "yes").sum())
    reverse = int((df["reverseFlip"] == "yes").sum())
    ci = stats.binomtest(classic, n).proportion_ci()
    say("Classic reversal: %d/%d = %.1f%% [95%% CI %.1f-%.1f]" % (classic, n, 100 * classic / n, 100 * ci.low, 100 * ci.high))
    say("Reverse: %d/%d = %.1f%% | Any reversal: %.1f%%" % (reverse, n, 100 * reverse / n, 100 * (classic + reverse) / n))
    if classic + reverse > 0:
        say("McNemar classic vs reverse: p=%.4f" % stats.binomtest(classic, classic + reverse).pvalue)
    say(pd.crosstab(df["flipNear"], df["flipFar"]).to_string())
    for o, g in df.groupby("flipOrder"):
        say("  %s (n=%d): classic %d, reverse %d" % (o, len(g), int((g["flipped"] == "yes").sum()), int((g["reverseFlip"] == "yes").sum())))
    say("Proposal predicted: a third or more show the reversal.")

    # The map: V = A / (1 + kD), one curve per context
    fig, ax = plt.subplots(figsize=(7, 4.2))
    days = np.linspace(0, 365, 200)
    for c in CONTEXTS:
        k = df["A_%s_k" % c].median()
        ax.plot(days, 1 / (1 + k * days), color=COLORS[c], linewidth=2.2, label="%s (k = %.4f)" % (c, k))
    ax.set_xlabel("Delay (days)")
    ax.set_ylabel("Present value of 1 unit")
    ax.set_ylim(0, 1.02)
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(frameon=False)
    ax.set_title("Discounting by context (median k, V = A / (1 + kD))", loc="left", fontsize=11)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "proposal_discount_curves.png"), dpi=200)
    t.to_csv(os.path.join(OUT, "proposal_pairwise.csv"), index=False)
    with open(os.path.join(OUT, "report.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(LINES) + "\n")
    say("\nSaved to %s" % OUT)


if __name__ == "__main__":
    main()
