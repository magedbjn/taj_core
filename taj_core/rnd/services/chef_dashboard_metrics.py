"""Pure aggregation helpers for the R&D Chef Dashboard.

This module deliberately has no Frappe imports so the reporting rules can be
verified with fast unit tests. Database access belongs to the Page controller.
"""

from collections import Counter, defaultdict
from datetime import date, datetime
from statistics import mean


def _as_date(value):
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _in_range(value, from_date, to_date):
    value = _as_date(value)
    return bool(value and from_date <= value <= to_date)


def _is_final_approved(trial):
    return trial.get("status") == "Approved" and bool(int(trial.get("is_final_trial") or 0))


def _approval_date(trial):
    if trial.get("status") != "Approved":
        return None
    return _as_date(trial.get("approved_on")) or _as_date(trial.get("posting_date"))


def _trial_matches(trial, trial_user=None, product_proposal=None, status=None):
    if trial_user and trial.get("trial_user") != trial_user:
        return False
    if product_proposal and trial.get("product_proposal") != product_proposal:
        return False
    if status and trial.get("status") != status:
        return False
    return True


def _ranked_series(counter, limit=None):
    rows = sorted(counter.items(), key=lambda item: (-item[1], str(item[0]).lower()))
    if limit:
        rows = rows[:limit]
    return [{"label": label, "value": value} for label, value in rows]


def _period_key(value, granularity):
    value = _as_date(value)
    if granularity == "month":
        return value.strftime("%Y-%m")
    return value.isoformat()


def _round_mean(values):
    if not values:
        return 0.0
    return round(mean(values), 1)


def build_dashboard_metrics(
    trials,
    runs,
    from_date,
    to_date,
    trial_user=None,
    product_proposal=None,
    status=None,
):
    """Build KPI, chart, and detail data for the Chef Dashboard.

    ``trials`` must contain all permission-visible Trial history because product
    approval state and time/trial counts to approval are historical measures.
    Period filtering is applied inside this function.
    """
    from_date = _as_date(from_date)
    to_date = _as_date(to_date)
    if not from_date or not to_date:
        raise ValueError("from_date and to_date are required")
    if from_date > to_date:
        raise ValueError("from_date cannot be after to_date")

    trials = [dict(row) for row in (trials or [])]
    runs = [dict(row) for row in (runs or [])]
    trial_by_name = {row.get("name"): row for row in trials if row.get("name")}

    matching_trials = [
        row
        for row in trials
        if _trial_matches(row, trial_user, product_proposal, status)
    ]
    period_trials = [
        row
        for row in matching_trials
        if _in_range(row.get("posting_date"), from_date, to_date)
    ]
    period_approvals = [
        row
        for row in matching_trials
        if _in_range(_approval_date(row), from_date, to_date)
    ]

    period_runs = []
    for run in runs:
        parent = trial_by_name.get(run.get("parent"))
        if not parent:
            continue
        if not _trial_matches(parent, trial_user, product_proposal, status):
            continue
        if _in_range(run.get("run_date"), from_date, to_date):
            period_runs.append(run)

    worked_products = {
        row.get("product_proposal")
        for row in period_trials
        if row.get("product_proposal")
    }
    worked_products.update(
        trial_by_name[run["parent"]].get("product_proposal")
        for run in period_runs
        if run.get("parent") in trial_by_name
        and trial_by_name[run["parent"]].get("product_proposal")
    )
    worked_products.update(
        row.get("product_proposal")
        for row in period_approvals
        if row.get("product_proposal")
    )

    historically_approved_products = {
        row.get("product_proposal")
        for row in trials
        if row.get("product_proposal") and _is_final_approved(row)
    }

    history_by_product = defaultdict(list)
    for row in trials:
        if row.get("product_proposal") and _as_date(row.get("posting_date")):
            history_by_product[row["product_proposal"]].append(row)

    under_development = set()
    for proposal in worked_products:
        history = history_by_product.get(proposal, [])
        if not history:
            under_development.add(proposal)
            continue

        latest = max(
            history,
            key=lambda row: (
                int(row.get("trial_no") or 0),
                _as_date(row.get("posting_date")) or date.min,
                str(row.get("name") or ""),
            ),
        )
        has_current_final = proposal in historically_approved_products
        if _is_final_approved(latest):
            continue
        if latest.get("status") == "Rejected" and has_current_final:
            continue
        under_development.add(proposal)

    qualifying_finals = [row for row in period_approvals if _is_final_approved(row)]
    trials_to_approval_values = []
    days_to_approval_values = []
    trials_to_approval_rows = []

    for final in qualifying_finals:
        final_date = _approval_date(final)
        history = [
            row
            for row in history_by_product.get(final.get("product_proposal"), [])
            if _as_date(row.get("posting_date")) <= final_date
        ]
        if not history:
            continue

        first_date = min(_as_date(row.get("posting_date")) for row in history)
        trial_count = len(history)
        elapsed_days = (final_date - first_date).days
        trials_to_approval_values.append(trial_count)
        days_to_approval_values.append(elapsed_days)
        trials_to_approval_rows.append(
            {
                "label": final.get("product_name") or final.get("product_proposal"),
                "value": trial_count,
                "product_proposal": final.get("product_proposal"),
            }
        )

    trials_to_approval_rows.sort(
        key=lambda row: (-row["value"], str(row["label"]).lower())
    )
    trials_to_approval_rows = trials_to_approval_rows[:10]

    trials_by_developer = Counter(
        row.get("trial_user") or "Unassigned" for row in period_trials
    )
    approved_by_developer = Counter(
        row.get("trial_user") or "Unassigned"
        for row in period_approvals
    )
    runs_by_developer = Counter(
        trial_by_name[run["parent"]].get("trial_user") or "Unassigned"
        for run in period_runs
        if run.get("parent") in trial_by_name
    )

    product_trial_counts = Counter()
    product_labels = {}
    for row in period_trials:
        proposal = row.get("product_proposal")
        if not proposal:
            continue
        product_trial_counts[proposal] += 1
        product_labels[proposal] = row.get("product_name") or proposal

    trials_by_product = [
        {
            "label": product_labels.get(proposal, proposal),
            "value": count,
            "product_proposal": proposal,
        }
        for proposal, count in sorted(
            product_trial_counts.items(),
            key=lambda item: (-item[1], str(product_labels.get(item[0], item[0])).lower()),
        )[:10]
    ]

    span_days = (to_date - from_date).days + 1
    granularity = "day" if span_days <= 62 else "month"
    activity = defaultdict(lambda: {"trials": 0, "final_approved": 0})
    approved_over_time = Counter()
    for row in period_trials:
        period = _period_key(row.get("posting_date"), granularity)
        activity[period]["trials"] += 1

    for row in qualifying_finals:
        period = _period_key(_approval_date(row), granularity)
        activity[period]["final_approved"] += 1
        approved_over_time[period] += 1

    development_activity = [
        {
            "period": period,
            "trials": values["trials"],
            "final_approved": values["final_approved"],
        }
        for period, values in sorted(activity.items())
    ]
    approved_products_over_time = [
        {"period": period, "value": value}
        for period, value in sorted(approved_over_time.items())
    ]

    runs_by_trial = defaultdict(list)
    for run in period_runs:
        runs_by_trial[run.get("parent")].append(run)

    detail_trial_names = (
        {row.get("name") for row in period_trials if row.get("name")}
        | {row.get("name") for row in period_approvals if row.get("name")}
        | {run.get("parent") for run in period_runs if run.get("parent")}
    )

    details = []
    for trial_name in detail_trial_names:
        trial = trial_by_name.get(trial_name)
        if not trial:
            continue
        trial_runs = runs_by_trial.get(trial_name, [])
        latest_run_date = max(
            (_as_date(row.get("run_date")) for row in trial_runs if row.get("run_date")),
            default=None,
        )
        details.append(
            {
                "product_proposal": trial.get("product_proposal"),
                "product_name": trial.get("product_name") or trial.get("product_proposal"),
                "trial": trial.get("name"),
                "trial_no": trial.get("trial_no"),
                "trial_title": trial.get("trial_title"),
                "trial_user": trial.get("trial_user") or "Unassigned",
                "posting_date": _as_date(trial.get("posting_date")).isoformat()
                if trial.get("posting_date")
                else "",
                "approved_on": _approval_date(trial).isoformat()
                if _approval_date(trial)
                else "",
                "status": trial.get("status") or "",
                "is_final_trial": bool(int(trial.get("is_final_trial") or 0)),
                "cooking_runs_in_period": len(trial_runs),
                "latest_run_date": latest_run_date.isoformat() if latest_run_date else "",
            }
        )

    def detail_sort_key(row):
        activity_date = max(
            row.get("latest_run_date") or "",
            row.get("approved_on") or "",
            row.get("posting_date") or "",
        )
        return (activity_date, row.get("trial") or "")

    details.sort(key=detail_sort_key, reverse=True)

    return {
        "kpis": {
            "products_worked_on": len(worked_products),
            "trials": len(period_trials),
            "cooking_runs": len(period_runs),
            "final_approved": len(qualifying_finals),
            "under_development": len(under_development),
            "avg_trials_to_approval": _round_mean(trials_to_approval_values),
            "avg_days_to_approval": _round_mean(days_to_approval_values),
        },
        "charts": {
            "trials_by_developer": _ranked_series(trials_by_developer),
            "approved_trials_by_developer": _ranked_series(approved_by_developer),
            "cooking_runs_by_developer": _ranked_series(runs_by_developer),
            "product_status": [
                {
                    "label": "Approved",
                    "value": len(worked_products - under_development),
                },
                {"label": "Under Development", "value": len(under_development)},
            ],
            "trials_by_product": trials_by_product,
            "activity_granularity": granularity,
            "development_activity": development_activity,
            "approved_products_over_time": approved_products_over_time,
            "trials_to_approval": trials_to_approval_rows,
        },
        "details": details,
    }
