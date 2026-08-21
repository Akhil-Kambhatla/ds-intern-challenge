import argparse
import contextlib
import io
import math

import numpy as np
import pandas as pd
from scipy import stats

OUTPUT_WIDTH = 100
DEFAULT_DATA_PATH = "sample-data/product_usage_events.csv"
DEFAULT_CHANGE_DATE = "2026-08-04"

LABEL_COLUMNS = ["team", "workflow", "source"]
COUNT_COLUMNS = ["sessions", "completed", "accepted_output"]
NUMERIC_COLUMNS = [
    "sessions",
    "completed",
    "accepted_output",
    "flagged_for_review",
    "avg_minutes_saved",
    "median_confidence",
    "user_rating",
]
RANKED_METRICS = [
    "completed",
    "accepted_output",
    "flagged_for_review",
    "avg_minutes_saved",
    "median_confidence",
    "user_rating",
]
KNOWN_TEAMS = ["Sales", "Support", "Product"]
KNOWN_WORKFLOWS = ["Lead summary", "Reply draft", "Feedback clustering"]
KNOWN_SOURCES = ["email", "manual", "queue", "csv upload"]
EXPECTED_COMBINATIONS = [
    ("Sales", "Lead summary", "email"),
    ("Sales", "Lead summary", "manual"),
    ("Support", "Reply draft", "queue"),
    ("Support", "Reply draft", "manual"),
    ("Product", "Feedback clustering", "csv upload"),
    ("Product", "Feedback clustering", "manual"),
]
EXPECTED_ROWS_PER_DATE = len(EXPECTED_COMBINATIONS)
QUARANTINE_NOTE_KEYWORDS = ["duplicate", "demo", "test", "mid-day", "policy changed"]
QUARANTINE_REASON_WORDS = {
    "check 1": "a count is missing or impossible",
    "check 2": "accepted plus flagged exceed completed runs",
    "check 3": "the same row was exported twice",
    "check 4": "sessions far above a normal day",
    "check 5": "the note marks it as a known event",
}
TIER_LABELS = ["use", "use with care", "do not use"]
SESSION_SPIKE_MULTIPLE = 3.0
SESSION_FLAG_MULTIPLE = 2.0

METRIC_PROVENANCE = {
    "sessions": "observed",
    "completed": "observed",
    "accepted_output": "observed",
    "flagged_for_review": "observed",
    "avg_minutes_saved": "estimate",
    "median_confidence": "model reported",
    "user_rating": "user reported",
}
PROVENANCE_SCORE = {
    "observed": 1.00,
    "user reported": 0.50,
    "estimate": 0.35,
    "model reported": 0.20,
}
REFERENCE_SIGNAL = {
    "completed": "user_rating",
    "accepted_output": "user_rating",
    "flagged_for_review": "acceptance_rate",
    "avg_minutes_saved": "acceptance_rate",
    "median_confidence": "acceptance_rate",
    "user_rating": "acceptance_rate",
}
RATE_DENOMINATOR = {
    "completed": "sessions",
    "accepted_output": "completed",
    "flagged_for_review": "completed",
}
VARIATION_REFERENCE_CV = 0.20
MINIMUM_PAIRS_FOR_CORRELATION = 4
SENSITIVITY_TOLERANCE_POINTS = 1.0
DETECTABLE_DELTAS = [0.03, 0.05]
DEFAULT_MIN_EFFECT_POINTS = 3.0
LONG_HORIZON_DAYS = 30
TRUST_TIERS = [
    ("Trustworthy", 4.00),
    ("Use with care", 3.00),
    ("Do not build decisions on this", None),
]


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Weekly trust check for the SignalDesk usage export."
    )
    parser.add_argument("--data", default=DEFAULT_DATA_PATH)
    parser.add_argument("--change-date", default=DEFAULT_CHANGE_DATE)
    parser.add_argument("--min-effect", type=float, default=DEFAULT_MIN_EFFECT_POINTS)
    parser.add_argument("--detail", action="store_true")
    return parser.parse_args()


def print_section_header(number, title):
    print("")
    print("=" * OUTPUT_WIDTH)
    print("SECTION {0}: {1}".format(number, title))
    print("=" * OUTPUT_WIDTH)


def print_subheader(title):
    print("")
    print(title)
    print("-" * min(OUTPUT_WIDTH, len(title)))


def wrap_and_print(text, indent=None):
    if indent is None:
        indent = text[: len(text) - len(text.lstrip(" "))]
    available = max(20, OUTPUT_WIDTH - len(indent))
    words = []
    for word in text.split():
        while len(word) > available:
            words.append(word[:available])
            word = word[available:]
        words.append(word)
    line = indent
    for word in words:
        candidate = word if line.strip() == "" else line + " " + word
        if len(candidate) > OUTPUT_WIDTH:
            print(line)
            line = indent + word
        else:
            line = candidate if line.strip() != "" else indent + word
    if line.strip() != "":
        print(line)


def format_percent(value, decimals=1):
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "n/a"
    return "{0:.{1}f}%".format(100.0 * value, decimals)


def format_number(value, decimals=2):
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "n/a"
    return "{0:.{1}f}".format(value, decimals)


def load_raw_table(path):
    return pd.read_csv(path, dtype=str, keep_default_na=False, na_filter=False)


def describe_row(table, index):
    row = table.loc[index]
    return "line {0:>3}  {1}  {2:<20} {3:<11}".format(
        index + 2, row["date"], row["workflow"], row["source"]
    )


def print_row_with_note(table, index, note, indent="      "):
    descriptor = indent + describe_row(table, index)
    if note == "":
        print(descriptor.rstrip())
        return
    combined = descriptor + "  " + note
    if len(combined) <= OUTPUT_WIDTH:
        print(combined)
    else:
        print(descriptor.rstrip())
        wrap_and_print(note, indent + "    ")


def print_caught_rows(table, indexes, extra_by_index=None):
    for index in sorted(indexes):
        note = ""
        if extra_by_index is not None and index in extra_by_index:
            note = extra_by_index[index]
        print_row_with_note(table, index, note)


def match_known_value(raw_value, known_values):
    stripped = raw_value.strip()
    for known in known_values:
        if stripped.casefold() == known.casefold():
            return known
    return None


def normalize_label_columns(table):
    mismatches = []
    normalized = table.copy()
    known_by_column = {
        "team": KNOWN_TEAMS,
        "workflow": KNOWN_WORKFLOWS,
        "source": KNOWN_SOURCES,
    }
    for column in LABEL_COLUMNS:
        values = []
        for index, raw_value in table[column].items():
            canonical = match_known_value(raw_value, known_by_column[column])
            if canonical is None:
                mismatches.append((index, column, raw_value, None))
                values.append(raw_value.strip())
            else:
                if canonical != raw_value:
                    mismatches.append((index, column, raw_value, canonical))
                values.append(canonical)
        normalized[column] = values
    return normalized, mismatches


def coerce_numeric_columns(table):
    unparseable = []
    blanks = []
    coerced = table.copy()
    for column in table.columns:
        if column not in NUMERIC_COLUMNS:
            for index, raw_value in table[column].items():
                if raw_value.strip() == "":
                    blanks.append((index, column))
            continue
        values = []
        for index, raw_value in table[column].items():
            text = raw_value.strip()
            if text == "":
                blanks.append((index, column))
                values.append(np.nan)
                continue
            try:
                values.append(float(text))
            except ValueError:
                unparseable.append((index, column, text))
                values.append(np.nan)
        coerced[column] = values
    return coerced, unparseable, blanks


def find_arithmetic_violations(table):
    impossible = {}
    over_completed = {}
    for index, row in table.iterrows():
        sessions = row["sessions"]
        completed = row["completed"]
        accepted = row["accepted_output"]
        flagged = row["flagged_for_review"]
        reasons = []
        unusable = [column for column in COUNT_COLUMNS if pd.isna(row[column])]
        if unusable:
            reasons.append(
                "{0} missing, so the count arithmetic cannot be checked".format(
                    " and ".join(unusable)
                )
            )
        if pd.notna(accepted) and pd.notna(completed) and accepted > completed:
            reasons.append("accepted {0:.0f} > completed {1:.0f}".format(accepted, completed))
        if pd.notna(completed) and pd.notna(sessions) and completed > sessions:
            reasons.append("completed {0:.0f} > sessions {1:.0f}".format(completed, sessions))
        if reasons:
            impossible[index] = "; ".join(reasons)
        if pd.notna(accepted) and pd.notna(flagged) and pd.notna(completed):
            if accepted + flagged > completed:
                over_completed[index] = "accepted {0:.0f} + flagged {1:.0f} > completed {2:.0f}".format(
                    accepted, flagged, completed
                )
    return impossible, over_completed


def find_duplicate_groups(table):
    keys = table[["date", "team", "workflow", "source"]].agg(" | ".join, axis=1)
    duplicated_mask = keys.duplicated(keep=False)
    duplicates = {}
    for index in table.index[duplicated_mask]:
        duplicates[index] = ""
    group_sizes = keys.value_counts()
    for index in duplicates:
        duplicates[index] = "duplicate key, {0} copies of {1}".format(
            group_sizes[keys.loc[index]], keys.loc[index]
        )
    return duplicates


def find_session_spikes(table):
    quarantine = {}
    flagged = {}
    for index, row in table.iterrows():
        if pd.isna(row["sessions"]):
            continue
        peers = table[
            (table["workflow"] == row["workflow"])
            & (table["source"] == row["source"])
            & (table["date"] != row["date"])
        ]["sessions"].dropna()
        if len(peers) == 0:
            continue
        peer_median = float(np.median(peers))
        if peer_median <= 0:
            continue
        multiple = float(row["sessions"]) / peer_median
        note = "sessions {0:.0f} vs other-day median {1:.1f}, {2:.1f}x".format(
            row["sessions"], peer_median, multiple
        )
        if multiple >= SESSION_SPIKE_MULTIPLE:
            quarantine[index] = note
        elif multiple >= SESSION_FLAG_MULTIPLE:
            flagged[index] = note
    return quarantine, flagged


def find_note_keyword_rows(table):
    hits = {}
    for index, note in table["notes"].items():
        lowered = note.casefold()
        found = [keyword for keyword in QUARANTINE_NOTE_KEYWORDS if keyword in lowered]
        if found:
            hits[index] = "notes matched: " + ", ".join(found)
    return hits


def find_incomplete_dates(table):
    incomplete = []
    for date in sorted(table["date"].unique()):
        rows_for_date = table[table["date"] == date]
        if len(rows_for_date) >= EXPECTED_ROWS_PER_DATE:
            continue
        present = set(zip(rows_for_date["team"], rows_for_date["workflow"], rows_for_date["source"]))
        missing = [combo for combo in EXPECTED_COMBINATIONS if combo not in present]
        incomplete.append((date, len(rows_for_date), missing))
    return incomplete


def acceptance_rate(frame):
    completed_total = frame["completed"].sum()
    if completed_total <= 0:
        return float("nan")
    return float(frame["accepted_output"].sum() / completed_total)


def run_data_trust_report(raw_table, normalized_table):
    print_section_header(1, "DATA TRUST REPORT")
    wrap_and_print(
        "Arithmetic and structure checks run first and stand on their own. The notes keyword scan "
        "is a backstop only: it catches rows a human already knew were odd, and it will stop "
        "working the moment next week's notes are worded differently."
    )

    impossible, over_completed = find_arithmetic_violations(normalized_table)
    duplicates = find_duplicate_groups(normalized_table)
    spikes, spike_flags = find_session_spikes(normalized_table)
    note_hits = find_note_keyword_rows(normalized_table)

    print_subheader("Quarantine checks (row is excluded from every later section)")
    wrap_and_print(
        "  A row missing sessions, completed or accepted_output is quarantined by check 1 rather "
        "than flagged by check 8: without those three counts the arithmetic invariants cannot be "
        "verified and no rate in sections 3 and 4 can use the row. Missing values anywhere else "
        "only earn a flag."
    )

    print(
        "  [1] accepted > completed, completed > sessions, or a missing count: {0} row(s)".format(
            len(impossible)
        )
    )
    print_caught_rows(raw_table, impossible.keys(), impossible)
    print("  [2] accepted + flagged > completed: {0} row(s)".format(len(over_completed)))
    print_caught_rows(raw_table, over_completed.keys(), over_completed)
    print("  [3] duplicate date/team/workflow/source: {0} row(s)".format(len(duplicates)))
    print_caught_rows(raw_table, duplicates.keys(), duplicates)
    if duplicates:
        wrap_and_print(
            "Every copy in a duplicate group is quarantined, not just the later one, because "
            "nothing in the export says which copy is the real run.",
            "      ",
        )
    print(
        "  [4] sessions at or above {0:.0f}x the other-day median for the same workflow and "
        "source: {1} row(s)".format(SESSION_SPIKE_MULTIPLE, len(spikes))
    )
    print_caught_rows(raw_table, spikes.keys(), spikes)
    print(
        "  [5] notes keyword backstop ({0}): {1} row(s)".format(
            ", ".join(QUARANTINE_NOTE_KEYWORDS), len(note_hits)
        )
    )
    print_caught_rows(raw_table, note_hits.keys(), note_hits)

    quarantined = {}
    for source_name, hits in [
        ("check 1", impossible),
        ("check 2", over_completed),
        ("check 3", duplicates),
        ("check 4", spikes),
        ("check 5", note_hits),
    ]:
        for index in hits:
            quarantined.setdefault(index, []).append(source_name)

    arithmetic_only = [
        index
        for index, reasons in quarantined.items()
        if any(reason != "check 5" for reason in reasons)
    ]
    print("")
    print(
        "  Quarantined rows: {0}. Caught by an arithmetic or structure check independent of "
        "notes: {1}.".format(len(quarantined), len(arithmetic_only))
    )

    print_subheader("Flag checks (row stays in the analysis and is reported)")

    _, mismatches = normalize_label_columns(raw_table)
    print("  [6] label value outside the known list: {0} value(s)".format(len(mismatches)))
    for index, column, raw_value, canonical in mismatches:
        if canonical is None:
            note = "{0}='{1}' matches no known value, left as is".format(column, raw_value)
        else:
            note = "{0}='{1}' normalised to '{2}'".format(column, raw_value, canonical)
        print_row_with_note(raw_table, index, note)

    _, unparseable, blanks = coerce_numeric_columns(raw_table)
    print("  [7] numeric column holding a non-numeric value: {0} value(s)".format(len(unparseable)))
    for index, column, raw_value in unparseable:
        print_row_with_note(
            raw_table,
            index,
            "{0}='{1}' does not parse, treated as missing".format(column, raw_value),
        )
    print("  [8] missing values: {0} cell(s)".format(len(blanks)))
    for index, column in blanks:
        print_row_with_note(raw_table, index, "{0} is empty".format(column))

    incomplete_dates = find_incomplete_dates(normalized_table)
    print(
        "  [9] dates with fewer than {0} rows: {1} date(s)".format(
            EXPECTED_ROWS_PER_DATE, len(incomplete_dates)
        )
    )
    for date, row_count, missing in incomplete_dates:
        print("      {0}  has {1} rows, absent:".format(date, row_count))
        for team, workflow, source in missing:
            print("          {0} / {1} / {2}".format(team, workflow, source))

    print(
        "  [10] sessions at or above {0:.0f}x but below {1:.0f}x the other-day median: {2} "
        "row(s)".format(SESSION_FLAG_MULTIPLE, SESSION_SPIKE_MULTIPLE, len(spike_flags))
    )
    print_caught_rows(raw_table, spike_flags.keys(), spike_flags)
    if [index for index in spike_flags if index in duplicates]:
        wrap_and_print(
            "The demo row this week sits in this middle band and leaves the analysis only because "
            "the duplicate check caught it; on the spike check alone it would have been flagged "
            "and kept. The 2x and 3x boundaries are a judgment call rather than something the data "
            "derives, and a reader should know the verdict on that row rests on check 3.",
            "      ",
        )

    flagged_indexes = set()
    for index in spike_flags:
        flagged_indexes.add(index)
    for index, _, _, _ in mismatches:
        flagged_indexes.add(index)
    for index, _, _ in unparseable:
        flagged_indexes.add(index)
    for index, _ in blanks:
        flagged_indexes.add(index)

    clean_table = normalized_table.drop(index=list(quarantined.keys()))
    kept_flagged = sorted(flagged_indexes.intersection(set(clean_table.index)))

    print_subheader("Kept rows and sensitivity")
    print(
        "  Rows kept: {0} of {1} read. Rows quarantined: {2}. Kept rows carrying a flag: {3}.".format(
            len(clean_table), len(raw_table), len(quarantined), len(kept_flagged)
        )
    )

    rate_with_flagged = acceptance_rate(clean_table)
    rate_without_flagged = acceptance_rate(clean_table.drop(index=kept_flagged))
    movement_points = abs(rate_with_flagged - rate_without_flagged) * 100.0
    verdict = (
        "does not move enough to change any conclusion"
        if movement_points < SENSITIVITY_TOLERANCE_POINTS
        else "moves enough to change conclusions, treat the flagged rows as load bearing"
    )
    wrap_and_print(
        "  Overall acceptance rate with flagged rows in: {0}. With them out: {1}. Gap {2:.2f} "
        "points, which {3}.".format(
            format_percent(rate_with_flagged, 2),
            format_percent(rate_without_flagged, 2),
            movement_points,
            verdict,
        )
    )

    quarantine_reasons = {}
    for index, reasons in quarantined.items():
        ordered = [name for name in reasons if name != "check 5"] or reasons
        quarantine_reasons[index] = QUARANTINE_REASON_WORDS[ordered[0]]

    flag_notes = []
    for index, column, raw_value, _ in mismatches:
        if index in clean_table.index:
            flag_notes.append(
                "{0} '{1}' on {2}".format(column, raw_value, raw_table.loc[index, "date"])
            )
    for index, column, raw_value in unparseable:
        if index in clean_table.index:
            flag_notes.append(
                "{0} holds '{1}' on {2}".format(column, raw_value, raw_table.loc[index, "date"])
            )
    for index, column in blanks:
        if index in clean_table.index:
            flag_notes.append("{0} empty on {1}".format(column, raw_table.loc[index, "date"]))
    for index in spike_flags:
        if index in clean_table.index:
            flag_notes.append("session spike on {0}".format(raw_table.loc[index, "date"]))
    for date, row_count, _ in incomplete_dates:
        flag_notes.append("{0} has {1} of {2} rows".format(date, row_count, EXPECTED_ROWS_PER_DATE))

    return clean_table, kept_flagged, quarantined, incomplete_dates, quarantine_reasons, flag_notes


def group_label(workflow, source):
    return "{0} / {1}".format(workflow, source)


def spearman_with_size(first, second):
    paired = pd.DataFrame({"first": first, "second": second}).dropna()
    if len(paired) < MINIMUM_PAIRS_FOR_CORRELATION:
        return float("nan"), len(paired)
    if paired["first"].nunique() < 2 or paired["second"].nunique() < 2:
        return float("nan"), len(paired)
    correlation, _ = stats.spearmanr(paired["first"], paired["second"])
    return float(correlation), len(paired)


def add_derived_rates(table):
    derived = table.copy()
    derived["acceptance_rate"] = derived["accepted_output"] / derived["completed"]
    derived["completion_rate"] = derived["completed"] / derived["sessions"]
    derived["flag_rate"] = derived["flagged_for_review"] / derived["completed"]
    return derived


def coefficient_of_variation(values):
    usable = pd.Series(values).dropna()
    if len(usable) < 2 or usable.mean() == 0:
        return float("nan")
    return float(usable.std(ddof=1) / usable.mean())


def score_completeness(table, metric):
    return float(table[metric].notna().mean())


def score_variation(table, metric):
    per_group = []
    for _, group in table.groupby(["workflow", "source"]):
        value = coefficient_of_variation(group[metric])
        if not math.isnan(value):
            per_group.append(value)
    if not per_group:
        return 0.0, float("nan")
    mean_cv = float(np.mean(per_group))
    return float(min(1.0, mean_cv / VARIATION_REFERENCE_CV)), mean_cv


def event_contamination(clean_table, quarantined_table, metric):
    denominator = RATE_DENOMINATOR.get(metric)
    deviations = []
    for _, row in quarantined_table.iterrows():
        peers = clean_table[
            (clean_table["workflow"] == row["workflow"])
            & (clean_table["source"] == row["source"])
        ]
        if peers.empty or pd.isna(row[metric]):
            continue
        if denominator is None:
            value = float(row[metric])
            baseline = float(np.nanmedian(peers[metric]))
        else:
            if pd.isna(row[denominator]) or row[denominator] <= 0:
                continue
            value = float(row[metric] / row[denominator])
            baseline = float(np.nanmedian(peers[metric] / peers[denominator]))
        if math.isnan(baseline) or baseline == 0:
            continue
        deviations.append(abs(value / baseline - 1.0))
    if not deviations:
        return 0.0
    return float(min(1.0, max(deviations)))


def within_group_correlations(table, metric):
    reference = REFERENCE_SIGNAL[metric]
    correlations = []
    for (workflow, source), group in table.groupby(["workflow", "source"]):
        correlation, size = spearman_with_size(group[metric], group[reference])
        if not math.isnan(correlation):
            correlations.append((group_label(workflow, source), correlation, size))
    return reference, correlations


def score_agreement_and_sign_consistency(correlations):
    if not correlations:
        return 0.0, 0.0
    values = [correlation for _, correlation, _ in correlations]
    agreement = min(1.0, abs(float(np.mean(values))))
    positives = sum(1 for value in values if value > 0)
    negatives = sum(1 for value in values if value < 0)
    majority_share = max(positives, negatives) / float(len(values))
    sign_consistency = max(0.0, 2.0 * majority_share - 1.0)
    return agreement, sign_consistency


def tier_for_total(total):
    for name, bound in TRUST_TIERS:
        if bound is None or total >= bound:
            return name
    return TRUST_TIERS[-1][0]


def run_metric_trust_ranking(clean_table, quarantined_table, change_date):
    print_section_header(2, "METRIC TRUST RANKING")
    derived = add_derived_rates(clean_table)
    quarantined_derived = add_derived_rates(quarantined_table)
    wrap_and_print(
        "Scored on five criteria, each on a 0 to 1 scale, then summed. Nothing here is a hand "
        "placed ranking: change the data and the order changes. sessions is left out of the "
        "ranking because it is the exposure denominator rather than an outcome metric."
    )

    scores = []
    evidence_by_metric = {}
    for metric in RANKED_METRICS:
        completeness = score_completeness(clean_table, metric)
        provenance = METRIC_PROVENANCE[metric]
        provenance_score = PROVENANCE_SCORE[provenance]
        variation_score, mean_cv = score_variation(derived, metric)
        reference, correlations = within_group_correlations(derived, metric)
        agreement, sign_consistency = score_agreement_and_sign_consistency(correlations)
        contamination = event_contamination(derived, quarantined_derived, metric)
        direction = sign_consistency * (1.0 - contamination)
        total = completeness + provenance_score + direction + agreement + variation_score
        scores.append(
            {
                "metric": metric,
                "completeness": completeness,
                "provenance": provenance,
                "provenance_score": provenance_score,
                "direction": direction,
                "sign_consistency": sign_consistency,
                "contamination": contamination,
                "reference": reference,
                "agreement": agreement,
                "variation": variation_score,
                "mean_cv": mean_cv,
                "total": total,
            }
        )
        evidence_by_metric[metric] = (reference, correlations)

    scores.sort(key=lambda entry: entry["total"], reverse=True)

    print_subheader("Ranking")
    header = "{0:<4} {1:<20} {2:<16} {3:>6} {4:>6} {5:>6} {6:>6} {7:>6} {8:>7}".format(
        "rank", "metric", "provenance", "compl", "prov", "dir", "agree", "var", "total"
    )
    print("  " + header)
    print("  " + "-" * len(header))
    for position, entry in enumerate(scores, start=1):
        print(
            "  {0:<4} {1:<20} {2:<16} {3:>6.2f} {4:>6.2f} {5:>6.2f} {6:>6.2f} {7:>6.2f} {8:>7.2f}".format(
                position,
                entry["metric"],
                entry["provenance"],
                entry["completeness"],
                entry["provenance_score"],
                entry["direction"],
                entry["agreement"],
                entry["variation"],
                entry["total"],
            )
        )
    wrap_and_print(
        "  compl = share of clean rows with a usable value. prov = observed beats user reported "
        "beats estimate beats model reported. dir = sign consistency of the metric's within-group "
        "relationship, cut down by how far the metric swings in the rows tied to a known event. "
        "agree = strength of that relationship against an independent signal. var = whether the "
        "metric moves day to day within a group at all."
    )
    print("")
    previous_bound = None
    for name, bound in TRUST_TIERS:
        members = [entry["metric"] for entry in scores if tier_for_total(entry["total"]) == name]
        if bound is None:
            span = "total below {0:.2f}".format(previous_bound)
        elif previous_bound is None:
            span = "total {0:.2f} and above".format(bound)
        else:
            span = "total {0:.2f} to {1:.2f}".format(bound, previous_bound)
        wrap_and_print(
            "  {0} ({1}): {2}".format(name, span, ", ".join(members) if members else "none")
        )
        previous_bound = bound
    wrap_and_print(
        "  The gaps between adjacent ranks inside a tier are smaller than this scoring scheme can "
        "resolve, so the tier is the claim and the precise rank is not."
    )

    print_subheader("How direction clarity was computed")
    header = "{0:<20} {1:<16} {2:>10} {3:>14} {4:>8}".format(
        "metric", "compared with", "sign cons", "event swing", "dir"
    )
    print("  " + header)
    print("  " + "-" * len(header))
    for entry in scores:
        print(
            "  {0:<20} {1:<16} {2:>10.2f} {3:>14.2f} {4:>8.2f}".format(
                entry["metric"],
                entry["reference"],
                entry["sign_consistency"],
                entry["contamination"],
                entry["direction"],
            )
        )
    wrap_and_print(
        "  event swing is how far the metric moves, relative to its own group's normal level, in "
        "the rows quarantined in section 1. A metric that swings hard on a day whose note says the "
        "review policy changed does not have one clear meaning: a rise can be worse output, a "
        "stricter policy, or more careful users, and this week's data cannot separate them."
    )
    wrap_and_print(
        "  Those rows are quarantined everywhere else and used here on purpose: a row tied to a "
        "known event is evidence about what a metric means, not evidence about how the product "
        "performed, so it is excluded from every rate in sections 1, 3 and 4 and kept only for "
        "interpreting metric behaviour."
    )

    print_subheader("Evidence a: pooled Spearman, median_confidence vs acceptance rate")
    pooled_correlation, pooled_size = spearman_with_size(
        derived["median_confidence"], derived["acceptance_rate"]
    )
    print(
        "  rho = {0}   n = {1} clean rows pooled across every workflow and source".format(
            format_number(pooled_correlation), pooled_size
        )
    )

    print_subheader("Evidence b: the same Spearman within each workflow and source group")
    within_signs = []
    for (workflow, source), group in derived.groupby(["workflow", "source"]):
        correlation, size = spearman_with_size(group["median_confidence"], group["acceptance_rate"])
        print(
            "  {0:<34} rho = {1:>6}   n = {2}".format(
                group_label(workflow, source), format_number(correlation), size
            )
        )
        if not math.isnan(correlation):
            within_signs.append(correlation)
    wrap_and_print(
        "  Warning: these groups hold only six or seven rows each. Any single one of them is weak "
        "on its own. The reason to believe the pattern is that the direction repeats across "
        "groups, not that any one rho is large."
    )

    if within_signs and not math.isnan(pooled_correlation):
        disagreeing = sum(
            1 for value in within_signs if np.sign(value) != np.sign(pooled_correlation)
        )
        mean_within = float(np.mean(within_signs))
        print(
            "  mean within-group rho = {0} across {1} groups, versus pooled rho = {2}".format(
                format_number(mean_within), len(within_signs), format_number(pooled_correlation)
            )
        )
        if disagreeing >= len(within_signs) / 2.0:
            wrap_and_print(
                "  CONFOUNDED: the pooled rho ({0}) points the opposite way from {1} of {2} "
                "within-group rhos. The pooled figure is confounded by source: automated sources "
                "(email, queue, csv upload) carry both higher confidence and higher acceptance, so "
                "pooling them measures the source mix, not the model. Do not read the pooled "
                "number as evidence that confidence predicts quality.".format(
                    format_number(pooled_correlation), disagreeing, len(within_signs)
                )
            )
        else:
            wrap_and_print(
                "  The pooled rho ({0}) and {1} of {2} within-group rhos share a sign, so the "
                "pooled figure is not being flipped by source mix in this week's data. It is still "
                "a between-source comparison and should not be read as confidence predicting "
                "quality inside a source.".format(
                    format_number(pooled_correlation),
                    len(within_signs) - disagreeing,
                    len(within_signs),
                )
            )

    print_subheader("Evidence c: Spearman, median_confidence vs sessions")
    volume_correlation, volume_size = spearman_with_size(
        derived["median_confidence"], derived["sessions"]
    )
    print("  pooled: rho = {0}   n = {1}".format(format_number(volume_correlation), volume_size))
    perfect = 0
    group_count = 0
    for (workflow, source), group in derived.groupby(["workflow", "source"]):
        correlation, size = spearman_with_size(group["median_confidence"], group["sessions"])
        print(
            "  {0:<34} rho = {1:>6}   n = {2}".format(
                group_label(workflow, source), format_number(correlation), size
            )
        )
        if not math.isnan(correlation):
            group_count += 1
            if round(correlation, 2) >= 1.00:
                perfect += 1
    if perfect:
        wrap_and_print(
            "  {0} of {1} groups return exactly 1.00, which is weaker evidence than it looks. Both "
            "columns rise monotonically across seven consecutive days, and with six points a "
            "perfect rank correlation only needs neither column to dip. The honest reading is that "
            "confidence tracks the calendar and the traffic trend, not day to day output "
            "quality.".format(perfect, group_count)
        )
    wrap_and_print(
        "  Confidence tracking volume is a reason for suspicion: a quality signal should not rise "
        "simply because more runs happened that day."
    )

    print_subheader("Evidence d: coefficient of variation of avg_minutes_saved within each group")
    for (workflow, source), group in derived.groupby(["workflow", "source"]):
        value = coefficient_of_variation(group["avg_minutes_saved"])
        print(
            "  {0:<34} cv = {1:>6}   mean = {2:>6} minutes   n = {3}".format(
                group_label(workflow, source),
                format_number(value),
                format_number(group["avg_minutes_saved"].mean(), 1),
                int(group["avg_minutes_saved"].notna().sum()),
            )
        )

    print_subheader(
        "Evidence e: flag rate per completed by date, before the change on " + change_date
    )
    before_change = derived[derived["date"] < change_date]
    for workflow in KNOWN_WORKFLOWS:
        workflow_rows = before_change[before_change["workflow"] == workflow]
        if workflow_rows.empty:
            continue
        parts = []
        for date in sorted(workflow_rows["date"].unique()):
            day = workflow_rows[workflow_rows["date"] == date]
            completed_total = day["completed"].sum()
            rate = day["flagged_for_review"].sum() / completed_total if completed_total else np.nan
            parts.append("{0} {1}".format(date[-5:], format_percent(rate)))
        print("  {0:<22} {1}".format(workflow, "   ".join(parts)))
    wrap_and_print(
        "  A stable pre-change flag rate is the only reason the post-change flag rate would mean "
        "anything, and the policy change on the last day breaks that comparison for Reply draft."
    )

    return scores, pooled_correlation, within_signs


def run_weekly_health_summary(clean_table):
    print_section_header(3, "WEEKLY HEALTH SUMMARY")
    derived = add_derived_rates(clean_table)
    grouped = (
        derived.groupby(["workflow", "source"])[
            ["sessions", "completed", "accepted_output", "flagged_for_review"]
        ]
        .sum()
        .reset_index()
    )
    grouped["completion_rate"] = grouped["completed"] / grouped["sessions"]
    grouped["acceptance_of_completed"] = grouped["accepted_output"] / grouped["completed"]
    grouped["acceptance_of_sessions"] = grouped["accepted_output"] / grouped["sessions"]
    grouped["flag_rate"] = grouped["flagged_for_review"] / grouped["completed"]

    header = "{0:<33}{1:>6}{2:>6}{3:>6}{4:>6}{5:>8}{6:>11}{7:>11}{8:>11}".format(
        "Workflow / source",
        "sess",
        "cmpl",
        "acpt",
        "flag",
        "compl%",
        "acc/cmpl",
        "acc/sess",
        "flag/cmpl",
    )
    print("  " + header)
    print("  " + "-" * len(header))
    for workflow in KNOWN_WORKFLOWS:
        workflow_rows = grouped[grouped["workflow"] == workflow]
        for _, row in workflow_rows.iterrows():
            print(
                "  {0:<33}{1:>6.0f}{2:>6.0f}{3:>6.0f}{4:>6.0f}{5:>8}{6:>11}{7:>11}{8:>11}".format(
                    group_label(row["workflow"], row["source"]),
                    row["sessions"],
                    row["completed"],
                    row["accepted_output"],
                    row["flagged_for_review"],
                    format_percent(row["completion_rate"]),
                    format_percent(row["acceptance_of_completed"]),
                    format_percent(row["acceptance_of_sessions"]),
                    format_percent(row["flag_rate"]),
                )
            )
        totals = workflow_rows[
            ["sessions", "completed", "accepted_output", "flagged_for_review"]
        ].sum()
        print(
            "  {0:<33}{1:>6.0f}{2:>6.0f}{3:>6.0f}{4:>6.0f}{5:>8}{6:>11}{7:>11}{8:>11}".format(
                "  all sources (split shown above)",
                totals["sessions"],
                totals["completed"],
                totals["accepted_output"],
                totals["flagged_for_review"],
                format_percent(totals["completed"] / totals["sessions"]),
                format_percent(totals["accepted_output"] / totals["completed"]),
                format_percent(totals["accepted_output"] / totals["sessions"]),
                format_percent(totals["flagged_for_review"] / totals["completed"]),
            )
        )
        print("")

    lowest = grouped.loc[grouped["completion_rate"].idxmin()]
    wrap_and_print(
        "  The two acceptance denominators answer different questions. acc/cmpl asks whether a "
        "finished output was good; it hides every run that died before producing anything. "
        "acc/sess asks whether a user who started got something usable. The gap matters most for "
        "{0}, where completion is only {1}, so acc/cmpl of {2} falls to {3} once the failed runs "
        "are counted.".format(
            group_label(lowest["workflow"], lowest["source"]),
            format_percent(lowest["completion_rate"]),
            format_percent(lowest["acceptance_of_completed"]),
            format_percent(lowest["acceptance_of_sessions"]),
        )
    )

    print_subheader("Estimated minutes saved per workflow")
    minutes_by_workflow = {}
    for workflow in KNOWN_WORKFLOWS:
        workflow_rows = derived[derived["workflow"] == workflow]
        minutes = float((workflow_rows["accepted_output"] * workflow_rows["avg_minutes_saved"]).sum())
        minutes_by_workflow[workflow] = minutes
        print(
            "  {0:<22} {1:>9.0f} minutes   ({2:.1f} hours) from {3:.0f} accepted outputs".format(
                workflow,
                minutes,
                minutes / 60.0,
                workflow_rows["accepted_output"].sum(),
            )
        )
    wrap_and_print(
        "  Caveat: this is an estimate stacked on an estimate. avg_minutes_saved is self reported "
        "and directional only, and accepted_output is a rough quality proxy, so the product of the "
        "two carries both errors. Read the ordering between workflows, never the absolute number."
    )

    return grouped, minutes_by_workflow


def period_totals(frame):
    return {
        "completed": float(frame["completed"].sum()),
        "accepted": float(frame["accepted_output"].sum()),
        "sessions": float(frame["sessions"].sum()),
    }


def run_targets(clean_table, change_date, min_effect_points):
    print_section_header(4, "TARGETS")
    derived = add_derived_rates(clean_table)
    before = derived[derived["date"] < change_date]
    after = derived[derived["date"] >= change_date]

    print_subheader("Part one: mix adjusted comparison across the prompt change")
    wrap_and_print(
        "  Reference mix is each source's share of completed runs over the whole clean week. The "
        "adjusted rate asks what the before and after acceptance rate would have been if the "
        "source mix had been frozen at that reference."
    )
    print("")
    header = "{0:<22}{1:>10}{2:>10}{3:>9}{4:>10}{5:>10}{6:>9}{7:>12}".format(
        "Workflow", "raw bef", "raw aft", "raw chg", "adj bef", "adj aft", "adj chg", "mix effect"
    )
    print("  " + header)
    print("  " + "-" * len(header))
    mix_results = {}
    for workflow in KNOWN_WORKFLOWS:
        week_rows = derived[derived["workflow"] == workflow]
        week_completed = week_rows["completed"].sum()
        reference_mix = {}
        for source, source_rows in week_rows.groupby("source"):
            reference_mix[source] = float(source_rows["completed"].sum() / week_completed)
        adjusted = {}
        for label, period_rows in [("before", before), ("after", after)]:
            period_workflow = period_rows[period_rows["workflow"] == workflow]
            weighted_total = 0.0
            weight_used = 0.0
            for source, share in reference_mix.items():
                source_rows = period_workflow[period_workflow["source"] == source]
                completed_total = source_rows["completed"].sum()
                if completed_total <= 0:
                    continue
                rate = float(source_rows["accepted_output"].sum() / completed_total)
                weighted_total += share * rate
                weight_used += share
            adjusted[label] = weighted_total / weight_used if weight_used > 0 else float("nan")
        raw_before = acceptance_rate(before[before["workflow"] == workflow])
        raw_after = acceptance_rate(after[after["workflow"] == workflow])
        mix_effect = (adjusted["after"] - adjusted["before"]) - (raw_after - raw_before)
        mix_results[workflow] = {
            "raw_before": raw_before,
            "raw_after": raw_after,
            "adjusted_before": adjusted["before"],
            "adjusted_after": adjusted["after"],
            "mix_effect": mix_effect,
        }
        print(
            "  {0:<22}{1:>10}{2:>10}{3:>9}{4:>10}{5:>10}{6:>9}{7:>12}".format(
                workflow,
                format_percent(raw_before),
                format_percent(raw_after),
                "{0:+.1f}pt".format(100.0 * (raw_after - raw_before)),
                format_percent(adjusted["before"]),
                format_percent(adjusted["after"]),
                "{0:+.1f}pt".format(100.0 * (adjusted["after"] - adjusted["before"])),
                "{0:+.1f}pt".format(100.0 * mix_effect),
            )
        )
    print("")
    wrap_and_print(
        "  mix effect is adjusted change minus raw change: how many points of the raw movement "
        "were the source mix shifting rather than the prompt doing anything."
    )

    print_subheader("Part two: detectability")
    detectability = {}
    for workflow in KNOWN_WORKFLOWS:
        before_totals = period_totals(before[before["workflow"] == workflow])
        after_totals = period_totals(after[after["workflow"] == workflow])
        if before_totals["completed"] <= 0 or after_totals["completed"] <= 0:
            continue
        rate_before = before_totals["accepted"] / before_totals["completed"]
        rate_after = after_totals["accepted"] / after_totals["completed"]
        pooled = (before_totals["accepted"] + after_totals["accepted"]) / (
            before_totals["completed"] + after_totals["completed"]
        )
        band = 1.96 * math.sqrt(
            pooled
            * (1.0 - pooled)
            * (1.0 / before_totals["completed"] + 1.0 / after_totals["completed"])
        )
        observed = rate_after - rate_before
        inside = abs(observed) <= band
        after_days = after[after["workflow"] == workflow]["date"].nunique()
        completed_per_day = after_totals["completed"] / after_days if after_days else float("nan")
        requirements = []
        for delta in DETECTABLE_DELTAS:
            needed = 16.0 * pooled * (1.0 - pooled) / (delta * delta)
            days = needed / completed_per_day if completed_per_day else float("nan")
            requirements.append((delta, needed, days))
        detectability[workflow] = {
            "rate_before": rate_before,
            "rate_after": rate_after,
            "observed": observed,
            "band": band,
            "inside": inside,
            "pooled": pooled,
            "completed_per_day": completed_per_day,
            "requirements": requirements,
            "n_before": before_totals["completed"],
            "n_after": after_totals["completed"],
        }
        print("")
        print("  {0}".format(workflow))
        print(
            "    acceptance {0} -> {1}, observed change {2:+.1f} points on {3:.0f} then {4:.0f} "
            "completed runs".format(
                format_percent(rate_before),
                format_percent(rate_after),
                100.0 * observed,
                before_totals["completed"],
                after_totals["completed"],
            )
        )
        print(
            "    noise band +/- {0:.1f} points at 95 percent, observed change sits {1} it".format(
                100.0 * band, "INSIDE" if inside else "OUTSIDE"
            )
        )
        for delta, needed, days in requirements:
            print(
                "    a {0:.0f} point change needs {1:.0f} completed per period, about {2:.1f} "
                "days at {3:.0f} completed/day".format(
                    100.0 * delta, needed, days, completed_per_day
                )
            )

    print_subheader("Part three: levers, using the best result already achieved inside the product")
    grouped = (
        derived.groupby(["workflow", "source"])[["sessions", "completed", "accepted_output"]]
        .sum()
        .reset_index()
    )
    grouped["completion_rate"] = grouped["completed"] / grouped["sessions"]
    grouped["acceptance_rate"] = grouped["accepted_output"] / grouped["completed"]
    best_completion = float(grouped["completion_rate"].max())
    best_acceptance = float(grouped["acceptance_rate"].max())
    best_completion_group = grouped.loc[grouped["completion_rate"].idxmax()]
    best_acceptance_group = grouped.loc[grouped["acceptance_rate"].idxmax()]
    print(
        "  Best completion rate in the clean week: {0} at {1}".format(
            format_percent(best_completion),
            group_label(best_completion_group["workflow"], best_completion_group["source"]),
        )
    )
    print(
        "  Best acceptance rate in the clean week: {0} at {1}".format(
            format_percent(best_acceptance),
            group_label(best_acceptance_group["workflow"], best_acceptance_group["source"]),
        )
    )
    print("")
    opportunities = []
    for _, row in grouped.iterrows():
        target_completed = max(row["completed"], row["sessions"] * best_completion)
        gain_completion = max(0.0, (target_completed - row["completed"]) * row["acceptance_rate"])
        gain_acceptance = max(
            0.0, row["completed"] * (best_acceptance - row["acceptance_rate"])
        )
        gain_both = max(0.0, target_completed * best_acceptance - row["accepted_output"])
        opportunities.append(
            {
                "label": group_label(row["workflow"], row["source"]),
                "workflow": row["workflow"],
                "source": row["source"],
                "sessions": float(row["sessions"]),
                "completed": float(row["completed"]),
                "accepted": float(row["accepted_output"]),
                "completion_rate": float(row["completion_rate"]),
                "acceptance_rate": float(row["acceptance_rate"]),
                "gain_completion": gain_completion,
                "gain_acceptance": gain_acceptance,
                "gain_both": gain_both,
            }
        )
    opportunities.sort(key=lambda entry: entry["gain_both"], reverse=True)
    header = "{0:<33}{1:>9}{2:>9}{3:>9}{4:>12}{5:>12}{6:>10}".format(
        "Workflow / source",
        "acpt/wk",
        "compl%",
        "acc%",
        "+compl fix",
        "+acc fix",
        "+both",
    )
    print("  " + header)
    print("  " + "-" * len(header))
    for entry in opportunities:
        print(
            "  {0:<33}{1:>9.0f}{2:>9}{3:>9}{4:>12.1f}{5:>12.1f}{6:>10.1f}".format(
                entry["label"],
                entry["accepted"],
                format_percent(entry["completion_rate"]),
                format_percent(entry["acceptance_rate"]),
                entry["gain_completion"],
                entry["gain_acceptance"],
                entry["gain_both"],
            )
        )
    wrap_and_print(
        "  Gains are additional accepted outputs per week at this week's session volume. They are "
        "an upper bound: they assume a group can reach a rate another group already reaches, which "
        "different inputs may not allow."
    )

    print_subheader("Pre-registered thresholds, quotable as written")
    wrap_and_print(
        "  The bar is the minimum effect the team would act on, {0:.1f} points of acceptance, set "
        "with --min-effect. That is a business choice rather than something this data decides. The "
        "noise band is not the bar: it shrinks as data accumulates, so the band in part two "
        "describes today's sample only.".format(min_effect_points)
    )
    print("")
    margin = min_effect_points / 100.0
    thresholds = {}
    for workflow in KNOWN_WORKFLOWS:
        if workflow not in detectability:
            continue
        figures = detectability[workflow]
        target_rate = figures["rate_before"] + margin
        needed = 16.0 * figures["pooled"] * (1.0 - figures["pooled"]) / (margin * margin)
        days = (
            math.ceil(needed / figures["completed_per_day"])
            if figures["completed_per_day"]
            else float("nan")
        )
        thresholds[workflow] = {"target_rate": target_rate, "days": days, "margin": margin}
        wrap_and_print(
            '  "{0} counts as a win only if acceptance of completed runs holds at or above {1}, '
            "its pre-change rate of {2} plus the {3:.1f} point minimum effect worth acting on. "
            "Reading that needs about {4:.0f} days of clean post-change data at its current {5:.0f} "
            "completed runs a day, roughly {6:.0f} completed runs, and until that much clean "
            'post-change data exists the change cannot be called either way."'.format(
                workflow,
                format_percent(target_rate),
                format_percent(figures["rate_before"]),
                100.0 * margin,
                days,
                figures["completed_per_day"],
                needed,
            )
        )
        if days > LONG_HORIZON_DAYS:
            wrap_and_print(
                "  {0:.0f} days is longer than a month, so for {1} a rate comparison is the wrong "
                "instrument at current volume: the team should read a sample of outputs by hand "
                "instead.".format(days, workflow)
            )
        print("")

    return mix_results, detectability, opportunities, thresholds


def build_next_items(
    quarantined,
    quarantine_reasons,
    incomplete_dates,
    scores,
    pooled_correlation,
    within_signs,
    grouped_health,
    detectability,
    opportunities,
    thresholds,
):
    items = []

    if quarantined:
        first_index = sorted(quarantined.keys())[0]
        items.append(
            {
                "long": "{0} rows never reached the analysis. Ask the export owner two things: why "
                "2026-08-05 shipped the same Lead summary / email row twice, and whether the Reply "
                "draft / queue row on 2026-08-07 is a real day or half a day, since its accepted "
                "plus flagged exceeds its completed count, which is arithmetically impossible and "
                "needs no note to prove it.".format(len(quarantined)),
                "short": "Ask the export owner to account for the {0} dropped rows, starting with "
                "the one where {1}.".format(len(quarantined), quarantine_reasons[first_index]),
            }
        )

    inside_band = [name for name, figures in detectability.items() if figures["inside"]]
    if inside_band:
        first = inside_band[0]
        items.append(
            {
                "long": "{0} moved {1:+.1f} points across the prompt change and the noise band is "
                "+/- {2:.1f} points, so the move is indistinguishable from nothing. Do not report "
                "it as a result. Hold the pre-registered threshold for {3} and re-run this script "
                "once {4:.0f} days of clean post-change data exist.".format(
                    first,
                    100.0 * detectability[first]["observed"],
                    100.0 * detectability[first]["band"],
                    first,
                    thresholds[first]["days"] if first in thresholds else float("nan"),
                ),
                "short": "Do not report the {0:+.1f} point move on {1} as a result. Re-run once "
                "{2:.0f} days of clean post-change data exist.".format(
                    100.0 * detectability[first]["observed"],
                    first,
                    thresholds[first]["days"] if first in thresholds else float("nan"),
                ),
            }
        )

    bottom_metric = scores[-1]["metric"]
    if within_signs and not math.isnan(pooled_correlation):
        disagreeing = sum(
            1 for value in within_signs if np.sign(value) != np.sign(pooled_correlation)
        )
        items.append(
            {
                "long": "{0} ranks last on trust this week. The pooled correlation between "
                "median_confidence and acceptance disagrees in sign with {1} of {2} within-group "
                "correlations. Before anyone puts a confidence threshold into routing, pull a "
                "sample of high confidence rejected outputs and check by hand whether confidence "
                "tracks correctness or just tracks the source being automated.".format(
                    bottom_metric, disagreeing, len(within_signs)
                ),
                "short": "Before any {0} threshold reaches routing, hand check a sample of high "
                "confidence rejected outputs.".format(bottom_metric),
            }
        )
    else:
        items.append(
            {
                "long": "{0} ranks last on trust this week. Confirm with the owning team what it "
                "is actually measuring before it appears in any decision.".format(bottom_metric),
                "short": "Confirm with the owning team what {0} actually measures before it "
                "appears in any decision.".format(bottom_metric),
            }
        )

    lowest = grouped_health.loc[grouped_health["completion_rate"].idxmin()]
    items.append(
        {
            "long": "{0} has the worst completion rate at {1}, so roughly {2:.0f} sessions a week "
            "end with nothing to accept. Instrument what happens between session start and "
            "completion for that group; the acceptance rate on completed runs is currently hiding "
            "the whole failure.".format(
                group_label(lowest["workflow"], lowest["source"]),
                format_percent(lowest["completion_rate"]),
                lowest["sessions"] - lowest["completed"],
            ),
            "short": "Instrument session start to completion for {0}, where about {1:.0f} sessions "
            "a week end with nothing.".format(
                group_label(lowest["workflow"], lowest["source"]),
                lowest["sessions"] - lowest["completed"],
            ),
        }
    )

    if opportunities:
        top = opportunities[0]
        items.append(
            {
                "long": "The largest single lever is {0}: about {1:.0f} more accepted outputs a "
                "week if it reached both the best completion and best acceptance rate already "
                "achieved elsewhere in the product. Check whether those best-in-product rates come "
                "from an easier input mix before treating them as a target.".format(
                    top["label"], top["gain_both"]
                ),
                "short": "Check whether the best-in-product rates behind the {0:.0f} output upside "
                "on {1} come from an easier input mix.".format(top["gain_both"], top["label"]),
            }
        )

    if incomplete_dates:
        date, row_count, missing = incomplete_dates[0]
        missing_names = ", ".join(
            group_label(workflow, source) for _, workflow, source in missing
        )
        items.append(
            {
                "long": "{0} arrived with {1} rows instead of {2}. Absent: {3}. Confirm whether "
                "those runs did not happen or did not export, because the two answers change every "
                "{0} number in this report.".format(
                    date, row_count, EXPECTED_ROWS_PER_DATE, missing_names
                ),
                "short": "Confirm whether the {0} rows absent from {1} did not happen or did not "
                "export.".format(EXPECTED_ROWS_PER_DATE - row_count, date),
            }
        )

    return items[:4]


def print_what_to_check_next(items):
    print("=" * OUTPUT_WIDTH)
    print("WHAT TO CHECK NEXT")
    print("=" * OUTPUT_WIDTH)

    for position, item in enumerate(items, start=1):
        wrap_and_print("{0}. {1}".format(position, item["long"]), "   ")
        print("")


def tier_reason(entry):
    options = [
        (entry["direction"], "its direction is unclear on the rows tied to a known event"),
        (entry["agreement"], "it agrees only weakly with acceptance"),
        (entry["variation"], "it barely moves day to day"),
        (entry["provenance_score"], "it is not directly observed"),
    ]
    options.sort(key=lambda option: option[0])
    return options[0][1]


def print_summary(
    arguments,
    raw_table,
    clean_table,
    quarantined,
    quarantine_reasons,
    flag_notes,
    scores,
    pooled_correlation,
    within_signs,
    grouped_health,
    detectability,
    opportunities,
    thresholds,
    next_items,
):
    print(
        "{0}{1}{2}".format(
            "SIGNALDESK WEEKLY CHECK".ljust(33),
            "{0} to {1}".format(raw_table["date"].min(), raw_table["date"].max()).ljust(34),
            "{0} of {1} rows used".format(len(clean_table), len(raw_table)),
        )
    )

    print("")
    print("VERDICT")
    outside = [
        name
        for name in KNOWN_WORKFLOWS
        if name in detectability and not detectability[name]["inside"]
    ]
    if outside:
        figures = detectability[outside[0]]
        wrap_and_print(
            "  {0} moved {1} {2:.1f} points, outside its {3:.1f} point margin, so it is the one "
            "workflow the change on {4} can be called for.".format(
                outside[0],
                "up" if figures["observed"] > 0 else "down",
                abs(100.0 * figures["observed"]),
                100.0 * figures["band"],
                arguments.change_date,
            )
        )
    else:
        wrap_and_print(
            "  The change on {0} cannot be called either way: all {1} workflows moved less than "
            "their own margin of error.".format(arguments.change_date, len(detectability))
        )
    bottom_tier = [
        entry["metric"] for entry in scores if tier_for_total(entry["total"]) == TRUST_TIERS[-1][0]
    ]
    disagreeing = 0
    if within_signs and not math.isnan(pooled_correlation):
        disagreeing = sum(
            1 for value in within_signs if np.sign(value) != np.sign(pooled_correlation)
        )
    if "median_confidence" in bottom_tier and disagreeing >= len(within_signs) / 2.0:
        wrap_and_print(
            "  Do not report the median_confidence rise as evidence the change worked: it "
            "disagrees with acceptance in {0} of {1} groups and tracks traffic, not "
            "quality.".format(disagreeing, len(within_signs))
        )
    elif bottom_tier:
        wrap_and_print(
            "  Do not build decisions on {0}: it sits in the bottom trust tier this "
            "week.".format(", ".join(bottom_tier))
        )

    print("")
    print("DID THE PROMPT CHANGE WORK")
    print(
        "  {0:<22}{1:<20}{2:>9}{3:>10}{4:>12}".format(
            "workflow", "acceptance", "change", "margin", "readable"
        )
    )
    for workflow in KNOWN_WORKFLOWS:
        if workflow not in detectability:
            continue
        figures = detectability[workflow]
        print(
            "  {0:<22}{1:<20}{2:>9}{3:>10}{4:>12}".format(
                workflow,
                "{0} -> {1}".format(
                    format_percent(figures["rate_before"]), format_percent(figures["rate_after"])
                ),
                "{0:+.1f}pt".format(100.0 * figures["observed"]),
                "{0:.1f}pt".format(100.0 * figures["band"]),
                "no" if figures["inside"] else "yes",
            )
        )
    needed = ", ".join(
        "{0:.0f}".format(thresholds[workflow]["days"])
        for workflow in KNOWN_WORKFLOWS
        if workflow in thresholds
    )
    wrap_and_print(
        "  Clean days per period needed at a {0:.1f} point minimum effect: {1}, in the row order "
        "above.".format(arguments.min_effect, needed)
    )
    before_days = clean_table[clean_table["date"] < arguments.change_date]["date"].nunique()
    after_days = clean_table[clean_table["date"] >= arguments.change_date]["date"].nunique()
    print(
        "  This export holds {0} days before {1} and {2} after.".format(
            before_days, arguments.change_date, after_days
        )
    )

    print("")
    print("WHICH NUMBERS TO USE")
    for position, tier in enumerate(TRUST_TIERS):
        members = [entry for entry in scores if tier_for_total(entry["total"]) == tier[0]]
        if not members:
            continue
        names = ", ".join(entry["metric"] for entry in members)
        if position == 1:
            names = "{0}, {1}".format(names, tier_reason(members[0]))
        line = "  {0:<15}{1}".format(TIER_LABELS[position], names)
        if len(line) <= OUTPUT_WIDTH:
            print(line)
        else:
            wrap_and_print(line)

    print("")
    print("BIGGEST OPPORTUNITY, AND IT IS NOT THE PROMPT")
    top = opportunities[0]
    health_row = grouped_health[
        (grouped_health["workflow"] == top["workflow"])
        & (grouped_health["source"] == top["source"])
    ].iloc[0]
    wrap_and_print(
        "  {0} completes {1} of sessions: about {2:.0f} a week end with nothing.".format(
            top["label"], format_percent(top["completion_rate"]), top["sessions"] - top["completed"]
        )
    )
    wrap_and_print(
        "  Acceptance on completed runs reads {0} and hides them. On sessions started it is "
        "{1}.".format(
            format_percent(health_row["acceptance_of_completed"]),
            format_percent(health_row["acceptance_of_sessions"]),
        )
    )
    wrap_and_print(
        "  Lifting completion to the best rate in the product adds about {0:.0f} accepted outputs "
        "a week.".format(top["gain_completion"])
    )

    print("")
    print("EXPORT PROBLEMS TO RAISE WITH THE DATA OWNER")
    for index in sorted(quarantined.keys()):
        row = raw_table.loc[index]
        print(
            "  {0}  {1:<34}{2}".format(
                row["date"], group_label(row["workflow"], row["source"]), quarantine_reasons[index]
            )
        )
    if flag_notes:
        wrap_and_print(
            "  {0} more issues flagged and kept: {1}.".format(
                len(flag_notes), "; ".join(flag_notes)
            )
        )

    print("")
    print("DO THIS WEEK")
    for position, item in enumerate(next_items, start=1):
        wrap_and_print("{0}. {1}".format(position, item["short"]), "  ")

    print("")
    print("  Run with --detail for the checks, correlations and full health summary behind this.")


def main():
    arguments = parse_arguments()
    raw_table = load_raw_table(arguments.data)
    buffer = io.StringIO()

    with contextlib.redirect_stdout(buffer):
        print("=" * OUTPUT_WIDTH)
        print("SIGNALDESK WEEKLY CHECK")
        print("=" * OUTPUT_WIDTH)
        data_line = "  data file   : {0}".format(arguments.data)
        if len(data_line) <= OUTPUT_WIDTH:
            print(data_line)
        else:
            print("  data file   :")
            wrap_and_print(arguments.data, "      ")
        print("  change date : {0}".format(arguments.change_date))
        print("  rows read   : {0}".format(len(raw_table)))
        print("  date range  : {0} to {1}".format(raw_table["date"].min(), raw_table["date"].max()))

        normalized_table, _ = normalize_label_columns(raw_table)
        normalized_table, _, _ = coerce_numeric_columns(normalized_table)

        (
            clean_table,
            kept_flagged,
            quarantined,
            incomplete_dates,
            quarantine_reasons,
            flag_notes,
        ) = run_data_trust_report(raw_table, normalized_table)
        quarantined_table = normalized_table.loc[sorted(quarantined.keys())]
        scores, pooled_correlation, within_signs = run_metric_trust_ranking(
            clean_table, quarantined_table, arguments.change_date
        )
        grouped_health, _ = run_weekly_health_summary(clean_table)
        _, detectability, opportunities, thresholds = run_targets(
            clean_table, arguments.change_date, arguments.min_effect
        )

        next_items = build_next_items(
            quarantined,
            quarantine_reasons,
            incomplete_dates,
            scores,
            pooled_correlation,
            within_signs,
            grouped_health,
            detectability,
            opportunities,
            thresholds,
        )

        print("")
        print_what_to_check_next(next_items)

    print_summary(
        arguments,
        raw_table,
        clean_table,
        quarantined,
        quarantine_reasons,
        flag_notes,
        scores,
        pooled_correlation,
        within_signs,
        grouped_health,
        detectability,
        opportunities,
        thresholds,
        next_items,
    )

    if arguments.detail:
        print("")
        print(buffer.getvalue(), end="")


if __name__ == "__main__":
    main()
