"""Report assets: the cleaned public data file, sample numbers and the report figures.

Usage:
    py analysis/report_assets.py path/to/responses.csv

Reads the raw Sheet export (which holds UPI IDs and must never be committed) and writes:
  data/now_or_later_responses_clean.csv    every response, identifiers removed, with status and exclusion_reason
  data/now_or_later_responses_summary.csv  the same rows without the per-tap trialsJSON column (easy to view)
  report/figures/*.svg and report/figures/numbers.json   figures and numbers used in the final report
Exclusions are the same as in analyze.py (main survey) and analyze_proposal.py (short survey).
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

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import analyze  # noqa: E402
import analyze_proposal  # noqa: E402
import final  # noqa: E402

SRC = sys.argv[1]
ROOT = os.path.join(HERE, "..")
DATA = os.path.join(ROOT, "data")
OUT = os.path.join(ROOT, "report", "figures")
os.makedirs(DATA, exist_ok=True)
os.makedirs(OUT, exist_ok=True)
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BLUE = "#2a78d6"
ORANGE = "#eb6834"
GREY = "#b9b8b1"
INK = "#0b0b0b"
INK2 = "#52514e"
GRIDC = "#e6e5e1"
plt.rcParams.update({"font.family": "Arial", "font.size": 8, "svg.fonttype": "none"})

N = {}

# ------------------------------------------------------------ analysed samples
main, strict = final.load_main(SRC)
prop = final.load_proposal(SRC)
main_ids = set(main["id"].astype(str))
prop_ids = set(prop["id"].astype(str))

# ------------------------------------------------------------ cleaned public CSV
raw = analyze.repair_ids(pd.read_csv(SRC))
n_rows = len(raw)
raw["test"] = raw["test"].fillna("no").replace("", "no")
raw = raw.sort_values("receivedAt")
raw["duplicate"] = raw.duplicated("id", keep="first")
raw["survey"] = raw["survey"].fillna("main").replace("", "main")
real = raw[(raw["test"] == "no") & (~raw["duplicate"])].copy()
N["unique_real"] = int(len(real))
N["unique_main"] = int((real["survey"] == "main").sum())
N["unique_short"] = int((real["survey"] == "proposal").sum())

flags = analyze.careless_flags(real[real["survey"] == "main"].assign(
    totalSec=pd.to_numeric(real["totalSec"], errors="coerce")))


def reason(r):
    i = str(r["id"])
    if r["survey"] == "main":
        if i in main_ids:
            return "analysed", ""
        if r.get("consent") != "yes":
            return "excluded", "no consent"
        if flags.get(r.name, 0) >= 3:
            return "excluded", "careless answering (3+ of 5 warning signs)"
        return "excluded", "other"
    if i in prop_ids:
        return "analysed", ""
    if r.get("consent") != "yes":
        return "excluded", "no consent"
    return "excluded", "rushed (over 25% of taps under 400 ms)"


res = real.apply(reason, axis=1, result_type="expand")
real["status"] = res[0]
real["exclusion_reason"] = res[1]
real["careless_flags"] = flags.reindex(real.index)


def device_type(ua):
    s = str(ua)
    if "iPhone" in s or "Android" in s or "Mobile" in s:
        return "phone"
    if s in ("", "nan"):
        return ""
    return "computer"


real["device_type"] = real["device"].apply(device_type)
drop = ["upi", "comment", "note", "device", "duplicate", "test"]
pub = real.drop(columns=[c for c in drop if c in real.columns])
pub = pub.rename(columns={"survey": "survey_form"})
pub["survey_form"] = pub["survey_form"].replace({"main": "main (index.html)", "proposal": "short (proposal.html)"})
front = ["id", "survey_form", "status", "exclusion_reason", "careless_flags", "receivedAt", "version"]
pub = pub[[c for c in front if c in pub.columns] + [c for c in pub.columns if c not in front]]
pub.to_csv(os.path.join(DATA, "now_or_later_responses_clean.csv"), index=False, encoding="utf-8")
pub.drop(columns=["trialsJSON"]).to_csv(os.path.join(DATA, "now_or_later_responses_summary.csv"), index=False, encoding="utf-8")
N["public_rows"] = int(len(pub))
N["public_analysed"] = int((pub["status"] == "analysed").sum())
N["excluded_reasons"] = pub[pub["status"] == "excluded"].groupby(["survey_form", "exclusion_reason"]).size().to_dict()
N["excluded_reasons"] = {"%s | %s" % k: int(v) for k, v in N["excluded_reasons"].items()}
N["rows_in_sheet"] = int(n_rows)
N["dates"] = [str(real["receivedAt"].min()), str(real["receivedAt"].max())]

# ------------------------------------------------------------ demographics
both = pd.concat([main.assign(s="main"), prop.assign(s="short")])
both["age"] = pd.to_numeric(both["age"], errors="coerce")
N["age_all"] = {"median": float(both["age"].median()), "min": float(both["age"].min()), "max": float(both["age"].max()),
                "share_18_24": float((both["age"] <= 24).mean())}
N["main_describes"] = main["describes"].value_counts().to_dict()
N["main_spending"] = main["spending"].value_counts().to_dict()
N["main_age"] = [float(main["age"].median()), float(main["age"].min()), float(main["age"].max())]
p_age = pd.to_numeric(prop["age"], errors="coerce")
N["short_age"] = [float(p_age.median()), float(p_age.min()), float(p_age.max())]
N["short_year"] = prop["year"].value_counts().to_dict()
N["short_field"] = prop["field"].value_counts().to_dict()
dev = real[real["status"] == "analysed"]["device_type"].value_counts(normalize=True).to_dict()
N["device"] = {k: round(v, 3) for k, v in dev.items()}
N["trust_median"] = float(pd.to_numeric(main["trust"], errors="coerce").median())
N["stress_median"] = float(pd.to_numeric(main["stress"], errors="coerce").median())
N["prior"] = main["priorKnowledge"].value_counts().to_dict()
N["otherSurvey"] = main["otherSurvey"].value_counts().to_dict()
N["minutes_main"] = float(pd.to_numeric(main["totalSec"], errors="coerce").median() / 60)
N["minutes_short"] = float(pd.to_numeric(prop["totalSec"], errors="coerce").median() / 60)
N["versions"] = main["version"].value_counts().to_dict()


# ------------------------------------------------------------ helpers
def lost(k):
    return 100 * 30 * k / (1 + 30 * k)


def style(ax):
    for side in ["top", "right", "left"]:
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(INK2)
    ax.tick_params(colors=INK2, length=0)
    ax.set_axisbelow(True)


# ------------------------------------------------------------ Fig 1: % lost by context, both surveys
rows = []
for study, df in [("main", main), ("short", prop)]:
    for c in final.CONTEXTS:
        k = pd.to_numeric(df["A_%s_k" % c], errors="coerce").dropna()
        lo, hi = final.boot_median_ci(k)
        rows.append({"study": study, "ctx": c, "med": lost(k.median()), "lo": lost(lo), "hi": lost(hi),
                     "floor": float((df["A_%s_censored" % c] == "low").mean())})
t1 = pd.DataFrame(rows)
N["fig1"] = t1.round(2).to_dict("records")

# ------------------------------------------------------------ Fig 2: inconsistency map (main)
inc = analyze.inconsistency_map(main)
N["inconsistency"] = inc.round(1).to_dict("records")
order2 = ["loss", "friend", "gain", "health"]
names2 = {"loss": "Fine", "friend": "Friend's money", "gain": "Money gain", "health": "Healthy days"}
d = inc.set_index("context").loc[order2]
fig, ax = plt.subplots(figsize=(3.35, 1.75))
yy = np.arange(len(order2))
left = np.zeros(len(order2))
for col, colr, lab in [("present_biased_pct", ORANGE, "Present-biased"), ("future_biased_pct", BLUE, "Future-biased"),
                       ("consistent_pct", GREY, "Consistent")]:
    vals = d[col].values
    ax.barh(yy, vals, left=left, color=colr, height=0.62, edgecolor="white", linewidth=1.2, label=lab)
    for yi, l0, v in zip(yy, left, vals):
        tc = "white"
        if col == "consistent_pct":
            tc = INK
        ax.text(l0 + v / 2, yi, "%.0f%%" % v, ha="center", va="center", fontsize=7, color=tc)
    left = left + vals
ax.set_yticks(yy)
ax.set_yticklabels([names2[c] for c in order2], fontsize=7.5, color=INK)
ax.invert_yaxis()
ax.set_xlim(0, 100)
ax.set_xticks([])
for s in ["top", "right", "left", "bottom"]:
    ax.spines[s].set_visible(False)
ax.tick_params(length=0)
ax.legend(frameon=False, fontsize=7, ncol=3, loc="upper center", bbox_to_anchor=(0.45, -0.02), handlelength=1.2,
          columnspacing=1.0)
fig.tight_layout(pad=0.3)
fig.savefig(os.path.join(OUT, "fig2_inconsistency.svg"))
plt.close(fig)

# ------------------------------------------------------------ Fig 3: trait vs state matrix (main, block A)
ctx3 = ["gain", "loss", "health", "friend"]
nm3 = ["Gain", "Fine", "Health", "Friend"]
kk = pd.DataFrame({c: pd.to_numeric(main["A_%s_k" % c], errors="coerce") for c in ctx3})
rho = kk.corr(method="spearman").values
N["rho_main"] = np.round(rho, 2).tolist()
fig, ax = plt.subplots(figsize=(2.2, 2.0))
cmap = matplotlib.colors.LinearSegmentedColormap.from_list("b", ["#f5f8fd", "#9ec5f4", "#2a78d6", "#104281"])
m = rho.copy()
np.fill_diagonal(m, np.nan)
ax.imshow(m, cmap=cmap, vmin=0, vmax=1)
for i in range(4):
    for j in range(4):
        if i == j:
            ax.text(j, i, "–", ha="center", va="center", fontsize=8, color=INK2)
        else:
            v = rho[i, j]
            ax.text(j, i, ("%.2f" % v).replace("0.", "."), ha="center", va="center", fontsize=7.5,
                    color="white" if v > 0.55 else INK)
ax.set_xticks(range(4))
ax.set_yticks(range(4))
ax.set_xticklabels(nm3, fontsize=7.2, color=INK)
ax.set_yticklabels(nm3, fontsize=7.2, color=INK)
ax.tick_params(length=0)
for s in ax.spines.values():
    s.set_visible(False)
ax.set_xticks(np.arange(-0.5, 4), minor=True)
ax.set_yticks(np.arange(-0.5, 4), minor=True)
ax.grid(which="minor", color="white", linewidth=1.5)
ax.tick_params(which="minor", length=0)
fig.tight_layout(pad=0.2)
fig.savefig(os.path.join(OUT, "fig3_trait.svg"))
plt.close(fig)

# ------------------------------------------------------------ extra numbers
an = main.copy()
an["anchorAmount"] = pd.to_numeric(an["anchorAmount"], errors="coerce")
hi_a = an[an["anchorGroup"] == "high"]["anchorAmount"].dropna()
lo_a = an[an["anchorGroup"] == "low"]["anchorAmount"].dropna()
u = stats.mannwhitneyu(hi_a, lo_a, alternative="greater")
N["h5"] = {"high_med": float(hi_a.median()), "low_med": float(lo_a.median()), "n_high": int(len(hi_a)),
           "n_low": int(len(lo_a)), "p_one": float(u.pvalue),
           "p_two": float(stats.mannwhitneyu(hi_a, lo_a).pvalue),
           "q25_hi": float(hi_a.quantile(.25)), "q75_hi": float(hi_a.quantile(.75)),
           "q25_lo": float(lo_a.quantile(.25)), "q75_lo": float(lo_a.quantile(.75))}
nz = main.copy()
nz["nudge_k"] = pd.to_numeric(nz["nudge_k"], errors="coerce")
N["h4"] = {g: float(lost(nz[nz["nudgeGroup"] == g]["nudge_k"].median())) for g in ["standard", "hiddenZero"]}
N["h6_correct_share"] = float((pd.to_numeric(main["type1Score"], errors="coerce") == 0).mean())
N["type1_dist"] = pd.to_numeric(main["type1Score"], errors="coerce").value_counts().sort_index().to_dict()
json.dump(N, open(os.path.join(OUT, "numbers.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False,
          default=str)
print("Analysed: %d of %d unique responses" % (N["public_analysed"], N["unique_real"]))

# ---------------- design figure
fig = plt.figure(figsize=(3.35, 2.55))
ax = fig.add_axes([0.02, 0.62, 0.96, 0.37])
ax.set_xlim(-24, 66)
ax.set_ylim(-0.55, 2.0)
ax.axis("off")
for y, s, e, lab in [(1.45, 0, 30, "Version A"), (0.55, 30, 60, "Version B")]:
    ax.plot([0, 60], [y, y], color=GRIDC, lw=1, zorder=1)
    ax.plot([s, e], [y, y], color=INK2, lw=1.6, zorder=2)
    ax.scatter([s], [y], s=34, color=ORANGE, zorder=3)
    ax.scatter([e], [y], s=34, color=BLUE, zorder=3)
    ax.text(s, y + 0.2, "₹500", ha="center", fontsize=7.5, color=INK)
    ax.text(e, y + 0.2, "₹X", ha="center", fontsize=7.5, color=INK)
    ax.text((s + e) / 2, y - 0.33, "30-day wait", ha="center", fontsize=6.8, color=INK2)
    ax.text(-23, y, lab, ha="left", va="center", fontsize=7.5, color=INK, fontweight="bold")
for d in [0, 30, 60]:
    lab = "today" if d == 0 else "day %d" % d
    ax.plot([d, d], [-0.12, -0.02], color=INK2, lw=0.8)
    ax.text(d, -0.45, lab, ha="center", fontsize=6.8, color=INK2)
ax.plot([0, 60], [-0.07, -0.07], color=INK2, lw=0.6)

ax2 = fig.add_axes([0.17, 0.12, 0.8, 0.42])
offers = [875, 690, 595, 645, 620, 610]
choice = ["wait", "wait", "today", "wait", "wait", "today"]
lo, hi = 500, 1250
los, his = [], []
for o, c in zip(offers, choice):
    los.append(lo)
    his.append(hi)
    if c == "wait":
        hi = o
    else:
        lo = o
x = np.arange(1, 7)
ax2.bar(x, np.array(his) - np.array(los), bottom=los, width=0.5, color="#cde2fb", lw=0, zorder=1)
ax2.plot(x, offers, color=INK2, lw=1, zorder=2)
for xi, o, c in zip(x, offers, choice):
    col = BLUE
    if c == "today":
        col = ORANGE
    ax2.scatter([xi], [o], s=26, color=col, zorder=3, edgecolor="white", linewidth=0.8)
    if c == "today":
        ax2.text(xi, o - 38, "₹%d" % o, ha="center", va="top", fontsize=6.6, color=INK)
    else:
        ax2.text(xi, o + 38, "₹%d" % o, ha="center", va="bottom", fontsize=6.6, color=INK)
ax2.plot([0.6, 6.9], [615, 615], color=INK, lw=0.8, ls=(0, (3, 2)), zorder=2)
ax2.text(6.95, 615, "S = ₹615", va="center", ha="left", fontsize=6.8, color=INK)
ax2.set_xlim(0.6, 8.2)
ax2.set_ylim(440, 1290)
ax2.set_xticks(x)
ax2.set_xticklabels(["tap %d" % i for i in x], fontsize=6.6, color=INK2)
ax2.set_yticks([500, 875, 1250])
ax2.set_yticklabels(["₹500", "₹875", "₹1,250"], fontsize=6.6, color=INK2)
ax2.set_ylabel("Later offer ₹X", fontsize=6.8, color=INK2)
for s in ["top", "right"]:
    ax2.spines[s].set_visible(False)
ax2.spines["left"].set_color(INK2)
ax2.spines["bottom"].set_color(INK2)
ax2.tick_params(length=0)
ax2.scatter([], [], s=26, color=BLUE, label="chose to wait")
ax2.scatter([], [], s=26, color=ORANGE, label="took ₹500 today")
ax2.legend(frameon=False, fontsize=6.6, loc="upper right", handletextpad=0.2, borderaxespad=0.1)
fig.savefig(os.path.join(OUT, "fig0_design.svg"))
plt.close(fig)

# ---------------- context figure, legend on top
rows = N["fig1"]
order = ["loss", "gain", "friend", "health"]
fig, ax = plt.subplots(figsize=(3.35, 2.3))
y = np.arange(len(order))
h = 0.36
for j, (study, col, lab) in enumerate([("main", BLUE, "Main survey (n = %d)" % len(main)), ("short", ORANGE, "Short survey (n = %d)" % len(prop))]):
    d = {r["ctx"]: r for r in rows if r["study"] == study}
    med = np.array([d[c]["med"] for c in order])
    lo_ = np.array([d[c]["lo"] for c in order])
    hi_ = np.array([d[c]["hi"] for c in order])
    yy = y - h / 2 + j * h
    ax.barh(yy, med, height=h - 0.05, color=col, label=lab, zorder=2)
    ax.errorbar(med, yy, xerr=[med - lo_, hi_ - med], fmt="none", ecolor=INK2, elinewidth=0.8, capsize=1.8, zorder=3)
    for yi, m, top in zip(yy, med, hi_):
        ax.text(max(top, m) + 1.2, yi, "%.0f%%" % m, va="center", fontsize=7, color=INK)
ax.set_yticks(y)
ax.set_yticklabels(["Fine", "Money gain", "Friend's money", "Health\n(main: healthy days;\nshort: flu days)"], fontsize=7.3,
                   color=INK)
ax.invert_yaxis()
ax.set_xlim(0, 60)
ax.xaxis.grid(True, color=GRIDC, linewidth=0.6)
ax.set_axisbelow(True)
ax.set_xlabel("Value lost to a 30-day wait (median person, %)", color=INK2, fontsize=7.3)
for s in ["top", "right", "left"]:
    ax.spines[s].set_visible(False)
ax.spines["bottom"].set_color(INK2)
ax.tick_params(colors=INK2, length=0)
ax.legend(frameon=False, fontsize=7, loc="lower center", bbox_to_anchor=(0.4, 1.0), ncol=2, handlelength=1.2,
          columnspacing=1.0, borderaxespad=0.1)
fig.tight_layout(pad=0.3)
fig.savefig(os.path.join(OUT, "fig1_context.svg"))
plt.close(fig)
