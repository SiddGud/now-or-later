"""Model prediction: what the literature's discounting model predicts for both surveys.

NOT DATA. Simulated respondents who follow the quasi-hyperbolic (beta-delta) model
(Laibson 1997; McClure et al. 2004), run through the exact question logic of index.html (v3)
and proposal.html. Use it to compare your real results with what theory predicts.

Usage:
    py analysis/model_prediction.py            (60 simulated people, 2000 repeats)

Assumptions (all stated, change them below):
- Present bias: beta ~ Normal(0.85, 0.10), clipped to [0.5, 1.05].
- Patience: the 30-vs-60-day gain switch point is Rs 500 plus a lognormal extra (median Rs 100, so k about 0.0067/day).
- Sign effect: fines are discounted at a quarter of the gain rate (Thaler 1981).
- Self vs other: for a friend, k is 0.8 x own and beta is halfway to 1 (Albrecht et al. 2011).
- Health as a gain (headache-free days, main survey): k is 1.5 x money; as a cost (flu, proposal): like fines.
- Domain-specific patience (Chapman 1996): each person's k per context is scaled by a lognormal factor (sd 0.3 for a friend, 1.2 for fines and health).
- Each choice has noise: logistic with a scale of 3% of the amounts involved.
"""
import numpy as np
import pandas as pd
from scipy import stats

RNG = np.random.default_rng(1)
N_PEOPLE = 60
REPEATS = 2000
TRIALS = 6


def person():
    beta = float(np.clip(RNG.normal(0.85, 0.10), 0.5, 1.05))
    # Extra amount needed to wait 30 more days: always positive, median Rs 100
    ind_b = 500.0 + float(np.exp(RNG.normal(np.log(100), 0.6)))
    # Daily discount factor from the 30-vs-60 gain switch point: 500 = delta^30 * ind_b
    d30 = 500.0 / ind_b
    # Patience is domain-specific (Chapman 1996): each context gets its own personal multiplier on k
    m = {}
    # Money for a friend stays close to own money; fines and health vary much more on their own
    spread = {"gain": 0.0, "friend": 0.3, "loss": 1.2, "health_gain": 1.2, "health_cost": 1.2}
    for ctx in spread:
        m[ctx] = float(np.exp(RNG.normal(0.0, spread[ctx])))
    m["gain"] = 1.0
    return {"beta": beta, "d30": d30, "m": m}


def d30_for(p, ctx):
    # 30-day discount factor per context, from k multipliers
    k = 1.0 / p["d30"] - 1.0
    mult = {"gain": 1.0, "friend": 0.8, "loss": 0.25, "health_gain": 1.5, "health_cost": 0.25}[ctx]
    if "m" in p:
        mult = mult * p["m"][ctx]
    return 1.0 / (1.0 + mult * k)


def beta_for(p, ctx):
    if ctx == "friend":
        return (1.0 + p["beta"]) / 2.0
    return p["beta"]


# Real-world noise settings: NOISE scales the choice noise, SLIP is the chance of a random tap
NOISE = 1.0
SLIP = 0.0


def choose_later(gain_sooner_pv, gain_later_pv, scale):
    # A slip: the person taps either option at random
    if SLIP > 0 and RNG.random() < SLIP:
        return RNG.random() < 0.5
    # Noisy choice: probability of the later option rises with its advantage
    x = (gain_later_pv - gain_sooner_pv) / (scale * NOISE)
    return RNG.random() < 1.0 / (1.0 + np.exp(-x))


def adaptive(p, ctx, frame, V, lo, hi, step, cost):
    """Runs the app's bisection. frame A = today vs 30 days, B = 30 vs 60 days."""
    lo0, hi0 = lo, hi
    d30 = d30_for(p, ctx)
    b = beta_for(p, ctx)
    taps = []
    for _ in range(TRIALS):
        L = round((lo + hi) / 2.0 / step) * step
        if L >= hi and hi - step > lo:
            L = hi - step
        if L <= lo and lo + step < hi:
            L = lo + step
        if frame == "A":
            pv_soon = V
            pv_late = b * d30 * L
        else:
            pv_soon = b * d30 * V
            pv_late = b * d30 * d30 * L
        if cost:
            # For a cost, the option with the smaller present cost is better
            later = choose_later(-pv_soon, -pv_late, 0.03 * V)
            if later:
                lo = L
            else:
                hi = L
        else:
            later = choose_later(pv_soon, pv_late, 0.03 * V)
            if later:
                hi = L
            else:
                lo = L
        word = "sooner"
        if later:
            word = "later"
        taps.append((L, word))
    ind = (lo + hi) / 2.0
    return ind, (ind / V - 1.0) / 30.0, taps


def pair(p, amt_s, amt_l, t_s, t_l):
    """Fixed choice between amt_s at day t_s and amt_l at day t_l. Returns True for the later option."""
    daily = p["d30"] ** (1.0 / 30.0)

    def pv(a, t):
        if t == 0:
            return a
        return p["beta"] * daily ** t * a
    return choose_later(pv(amt_s, t_s), pv(amt_l, t_l), 0.03 * amt_s)


def main_survey(p):
    r = {}
    for frame in "AB":
        for ctx in ["gain", "loss", "friend"]:
            ind, k, _ = adaptive(p, ctx, frame, 500, 500, 1250, 5, ctx == "loss")
            r["%s_%s_k" % (frame, ctx)] = k
        ind, k, _ = adaptive(p, "health_gain", frame, 20, 20, 80, 1, False)
        r["%s_health_k" % frame] = k
    near_later = pair(p, 1000, 1100, 0, 7)
    far_later = pair(p, 1000, 1100, 28, 35)
    r["classic"] = (not near_later) and far_later
    r["reverse"] = near_later and (not far_later)
    return r


def proposal_survey(p):
    r = {}
    for ctx in ["gain", "loss", "friend"]:
        ind, k, _ = adaptive(p, ctx, "A", 500, 500, 1250, 5, ctx == "loss")
        r["A_%s_k" % ctx] = k
    ind, k, _ = adaptive(p, "health_cost", "A", 10, 10, 25, 1, True)
    r["A_health_k"] = k
    near_later = pair(p, 100, 110, 0, 1)
    far_later = pair(p, 100, 110, 30, 31)
    r["classic"] = (not near_later) and far_later
    r["reverse"] = near_later and (not far_later)
    return r


def pick(later, later_text, sooner_text):
    # Text of the chosen option
    if later:
        return later_text
    return sooner_text


def fmt4(x):
    return "%.4f" % x


def one_person_walkthrough():
    print("== One typical person (beta 0.85, gain switch point at 30-vs-60 days Rs 600, no choice noise) ==")
    global RNG
    keep = RNG
    p = {"beta": 0.85, "d30": 500.0 / 600.0}

    class NoNoise:
        def random(self):
            return 0.5
    RNG = NoNoise()
    for frame in "AB":
        for ctx, V, lo, hi, step, cost in [("gain", 500, 500, 1250, 5, False), ("loss", 500, 500, 1250, 5, True),
                                           ("friend", 500, 500, 1250, 5, False), ("health_gain", 20, 20, 80, 1, False)]:
            ind, k, taps = adaptive(p, ctx, frame, V, lo, hi, step, cost)
            print("  main %s_%-11s %s -> switch %.1f, k %.4f" % (frame, ctx, ", ".join("%g:%s" % t for t in taps), ind, k))
    ind, k, taps = adaptive(p, "health_cost", "A", 10, 10, 25, 1, True)
    print("  proposal flu        %s -> switch %.1f, k %.4f" % (", ".join("%g:%s" % t for t in taps), ind, k))
    print("  main classic pair:     near -> %s | far -> %s" % (pick(pair(p, 1000, 1100, 0, 7), "1100 in 1 week", "1000 today"),
                                                            pick(pair(p, 1000, 1100, 28, 35), "1100 in 5 weeks", "1000 in 4 weeks")))
    print("  proposal pair:         near -> %s | far -> %s" % (pick(pair(p, 100, 110, 0, 1), "110 tomorrow", "100 today"),
                                                            pick(pair(p, 100, 110, 30, 31), "110 in 31 days", "100 in 30 days")))
    RNG = keep


def summarise(name, runs, contexts, blocks):
    print("\n== %s: expected results for %d people (median over %d simulated studies, 90%% range) ==" % (name, N_PEOPLE, REPEATS))
    rows = []
    for key in ["classic_pct", "reverse_pct"] + ["med_%s_%s" % (b, c) for b in blocks for c in contexts] + \
               ["pct_kA_gt_kB_gain", "p_wilcoxon_gain", "p_friedman_A", "p_loss_vs_gain", "p_health_vs_gain"]:
        vals = [r[key] for r in runs if key in r]
        if vals:
            rows.append({"statistic": key, "expected": np.median(vals), "low_5pct": np.percentile(vals, 5), "high_95pct": np.percentile(vals, 95)})
    t = pd.DataFrame(rows)
    print(t.to_string(index=False, float_format=fmt4))
    for key, label in [("p_wilcoxon_gain", "A vs B present bias (gain)"), ("p_friedman_A", "contexts differ"),
                       ("p_loss_vs_gain", "loss k < gain k"), ("p_health_vs_gain", "health vs gain")]:
        vals = [r[key] for r in runs if key in r]
        if vals:
            print("Power (p < .05) for %-28s %.0f%%" % (label + ":", 100 * np.mean(np.array(vals) < 0.05)))


def study_stats(rs, contexts, blocks):
    df = pd.DataFrame(rs)
    out = {"classic_pct": 100 * df["classic"].mean(), "reverse_pct": 100 * df["reverse"].mean()}
    for b in blocks:
        for c in contexts:
            out["med_%s_%s" % (b, c)] = df["%s_%s_k" % (b, c)].median()
    if "B" in blocks:
        out["pct_kA_gt_kB_gain"] = 100 * (df["A_gain_k"] > df["B_gain_k"]).mean()
        out["p_wilcoxon_gain"] = stats.wilcoxon(df["A_gain_k"], df["B_gain_k"]).pvalue
    out["p_friedman_A"] = stats.friedmanchisquare(*[df["A_%s_k" % c] for c in contexts]).pvalue
    out["p_loss_vs_gain"] = stats.wilcoxon(df["A_loss_k"], df["A_gain_k"]).pvalue
    out["p_health_vs_gain"] = stats.wilcoxon(df["A_health_k"], df["A_gain_k"]).pvalue
    return out


if __name__ == "__main__":
    one_person_walkthrough()
    ctx = ["gain", "loss", "health", "friend"]
    main_runs = []
    prop_runs = []
    for _ in range(REPEATS):
        people = [person() for _ in range(N_PEOPLE)]
        main_runs.append(study_stats([main_survey(p) for p in people], ctx, "AB"))
        prop_runs.append(study_stats([proposal_survey(p) for p in people], ctx, "A"))
    summarise("Main survey", main_runs, ctx, "AB")
    summarise("Proposal survey", prop_runs, ctx, "A")
