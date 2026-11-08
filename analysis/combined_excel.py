"""One-row-per-person Excel of real responses plus the synthetic test respondents.

Usage:
    py analysis/combined_excel.py real_plus_synthetic.csv out.xlsx

Sheets: Read me, Summary, Main survey, Short survey, Every answer (each tap with its time).
Test plays and lab benchmark plays are left out. UPI IDs, device and note columns are removed.
"""
import json
import sys

import pandas as pd
from openpyxl.styles import Font, PatternFill


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    src, out = sys.argv[1], sys.argv[2]
    d = pd.read_csv(src)
    d["test"] = d["test"].fillna("no")
    d = d[d["test"].isin(["no", "synthetic"])].copy()
    d = d.sort_values("receivedAt").drop_duplicates("id", keep="first")
    source = pd.Series("Real", index=d.index)
    source[d["test"] == "synthetic"] = "Synthetic"
    d.insert(0, "Source", source)
    # UPI IDs were promised for paying winners only
    d = d.drop(columns=["upi", "device", "note", "test"], errors="ignore")
    survey = d["survey"].fillna("main")
    taps = []
    for i, r in d.iterrows():
        try:
            tl = json.loads(r["trialsJSON"])
        except (TypeError, ValueError):
            continue
        form = "Main survey"
        if survey[i] == "proposal":
            form = "Short survey"
        for n, t in enumerate(tl):
            answer = t.get("choice", t.get("value", ""))
            taps.append({"Source": r["Source"], "Form": form, "Person": r["id"], "Tap": n + 1, "Question": t.get("step"),
                         "Offer shown": t.get("offer", ""), "Answer": answer, "Time (ms)": t.get("rt")})
    main_df = d[survey != "proposal"].drop(columns=["survey", "year", "field", "reverseFlip", "trialsJSON"], errors="ignore")
    prop_df = d[survey == "proposal"].dropna(axis=1, how="all").drop(columns=["trialsJSON"], errors="ignore")
    summary = pd.DataFrame({
        "Form": ["Main survey", "Main survey", "Short survey", "Short survey"],
        "Source": ["Real", "Synthetic", "Real", "Synthetic"],
        "People": [int((main_df["Source"] == "Real").sum()), int((main_df["Source"] == "Synthetic").sum()),
                   int((prop_df["Source"] == "Real").sum()), int((prop_df["Source"] == "Synthetic").sum())]})
    notes = pd.DataFrame({"Read me": [
        "Combined data: real responses plus synthetic test respondents (Source column). Synthetic rows are not research data.",
        "Main survey and Short survey sheets: one row per person, same columns as the Google Sheet.",
        "Every answer sheet: each tap in order, with the offer shown, the answer and the response time in milliseconds.",
        "Excluded: test plays and lab benchmark plays. Removed columns: UPI ID (used only to pay winners), device, note.",
        "Real rows are all responses received; the analysis additionally removes careless responders."]})
    shade = PatternFill("solid", fgColor="EEF3FB")
    with pd.ExcelWriter(out, engine="openpyxl") as xw:
        notes.to_excel(xw, sheet_name="Read me", index=False)
        summary.to_excel(xw, sheet_name="Summary", index=False)
        main_df.to_excel(xw, sheet_name="Main survey", index=False)
        prop_df.to_excel(xw, sheet_name="Short survey", index=False)
        pd.DataFrame(taps).to_excel(xw, sheet_name="Every answer", index=False)
        for ws in xw.book.worksheets:
            for c in ws[1]:
                c.font = Font(bold=True)
            for col in ws.columns:
                width = max(len(str(c.value or "")) for c in list(col)[:200])
                ws.column_dimensions[col[0].column_letter].width = min(48, max(9, width + 2))
            ws.freeze_panes = "B2"
            # Light shading on synthetic rows
            if ws.title in ("Main survey", "Short survey", "Every answer"):
                for row in ws.iter_rows(min_row=2):
                    if row[0].value == "Synthetic":
                        for c in row:
                            c.fill = shade
    print(summary.to_string(index=False))
    print("Saved", out)


if __name__ == "__main__":
    main()
