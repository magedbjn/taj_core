import frappe


def execute():
    doctype = "Checklist Answer"

    if not frappe.db.exists("DocType", doctype):
        return

    required_columns = (
        "taken_by",
        "source_due_date",
        "generation_key",
    )

    if not all(
        frappe.db.has_column(doctype, fieldname)
        for fieldname in required_columns
    ):
        return

    # Preserve the original checklist cycle date for old records.
    frappe.db.sql("""
        UPDATE `tabChecklist Answer`
        SET `source_due_date` = `posting_date`
        WHERE `source_due_date` IS NULL
          AND `posting_date` IS NOT NULL
    """)

    # Rebuild the same key produced by build_generation_key():
    # template::YYYY-MM-DD
    frappe.db.sql("""
        UPDATE `tabChecklist Answer`
        SET `generation_key` =
            CONCAT(`template`, '::', `source_due_date`)
        WHERE (
            `generation_key` IS NULL
            OR `generation_key` = ''
        )
          AND `template` IS NOT NULL
          AND `template` != ''
          AND `source_due_date` IS NOT NULL
    """)

    # Historical completed/answered checklists should retain
    # their effective claimant.
    frappe.db.sql("""
        UPDATE `tabChecklist Answer`
        SET `taken_by` = `answer_by`
        WHERE (
            `taken_by` IS NULL
            OR `taken_by` = ''
        )
          AND `answer_by` IS NOT NULL
          AND `answer_by` != ''
    """)

    frappe.clear_cache(doctype=doctype)
