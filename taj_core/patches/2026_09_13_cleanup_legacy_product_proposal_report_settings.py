import json

import frappe


LEGACY_DOCTYPE = "Product Proposal Trial Cooking"
TARGET_DOCTYPE = "Product Proposal"


def clean_user_settings(data):
    """
    Remove only a stale Product Proposal Report configuration that
    references the removed legacy Trial Cooking DocType.

    List, GridView and all other user settings are preserved.
    """
    try:
        settings = json.loads(data or "{}")
    except (TypeError, ValueError):
        return data, False

    report = settings.get("Report")

    if not report:
        return data, False

    report_json = json.dumps(
        report,
        ensure_ascii=False,
    )

    if LEGACY_DOCTYPE not in report_json:
        return data, False

    settings.pop("Report", None)

    return (
        json.dumps(
            settings,
            ensure_ascii=False,
        ),
        True,
    )


def execute():
    rows = frappe.db.sql(
        """
        SELECT user, doctype, data
        FROM `__UserSettings`
        WHERE doctype = %s
          AND data LIKE %s
        """,
        (
            TARGET_DOCTYPE,
            f"%{LEGACY_DOCTYPE}%",
        ),
        as_dict=True,
    )

    for row in rows:
        cleaned_data, changed = clean_user_settings(
            row.data
        )

        if not changed:
            continue

        frappe.db.sql(
            """
            UPDATE `__UserSettings`
            SET data = %s
            WHERE user = %s
              AND doctype = %s
            """,
            (
                cleaned_data,
                row.user,
                row.doctype,
            ),
        )
