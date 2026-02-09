import re
import frappe

MODULE_NAME = "Slnee"

# كلمات مفتاحية تساعدنا نلقط أي بقايا مرتبطة (بدون ما نحذف قياسي)
KEYWORDS = [
    "Slnee",
    "Store Item",
    "Wordpress",
    "Intern Sales Order",
    "Employee Deduction",
    "Expenses",
]

# لو تحب تبقي أسماء معينة "تتأكد" منها أيضًا (اختياري)
EXPLICIT_TARGETS = {
    "Store Item",
    "Store Item Item",
    "Store Item List",
    "Store Item Attribute",
    "Wordpress Store",
    "Employee Deduction",
    "Expenses",
    "Intern Sales Order Item",
    "Intern Sales Order ITem",  # لو ظهرت عندك بالخطأ
}

def _sanitize_table_name(name: str) -> str:
    # حماية بسيطة ضد backticks
    return name.replace("`", "")

def _table_exists(table_name: str) -> bool:
    return bool(
        frappe.db.sql(
            """
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = DATABASE()
              AND table_name = %s
            LIMIT 1
            """,
            (table_name,),
        )
    )

def _get_targets() -> list[str]:
    targets = set(EXPLICIT_TARGETS)

    # 1) أي DocType ما زال موجود وموديوله Slnee (لو فيه بقايا)
    try:
        targets.update(
            frappe.get_all("DocType", filters={"module": MODULE_NAME}, pluck="name")
        )
    except Exception:
        pass

    # 2) أي "Orphan parent" في DocField اسمه يحتوي أي Keyword (والـ DocType غير موجود في tabDocType)
    likes = " OR ".join(["df.parent LIKE %s"] * len(KEYWORDS))
    params = tuple(f"%{k}%" for k in KEYWORDS)

    rows = frappe.db.sql(
        f"""
        SELECT DISTINCT df.parent
        FROM `tabDocField` df
        LEFT JOIN `tabDocType` dt ON dt.name = df.parent
        WHERE dt.name IS NULL
          AND ({likes})
        """,
        params,
        as_list=True,
    )
    targets.update(r[0] for r in rows)

    return sorted(t for t in targets if t)

def _cleanup_references(name: str) -> None:
    # مراجع تسبب DocType ... not found
    frappe.db.sql("DELETE FROM `tabUser Permission` WHERE allow=%s OR applicable_for=%s", (name, name))
    frappe.db.sql("DELETE FROM `tabProperty Setter` WHERE doc_type=%s OR value=%s", (name, name))
    frappe.db.sql("DELETE FROM `tabCustom Field` WHERE dt=%s OR options=%s", (name, name))
    frappe.db.sql("DELETE FROM `tabSeries` WHERE name LIKE %s", (f"{name}%",))

def _cleanup_orphan_metadata(name: str) -> None:
    # بقايا Metadata
    frappe.db.sql("DELETE FROM `tabDocField` WHERE parent=%s", (name,))
    frappe.db.sql("DELETE FROM `tabDocPerm`  WHERE parent=%s", (name,))
    frappe.db.sql("DELETE FROM `tabSingles`  WHERE doctype=%s", (name,))

def _drop_table_if_exists_for_doctype(name: str) -> None:
    table_name = _sanitize_table_name(f"tab{name}")
    if _table_exists(table_name):
        # DDL لازم sql_ddl لتجنب ImplicitCommitError أثناء migrate
        frappe.db.sql_ddl(f"DROP TABLE IF EXISTS `{table_name}`")

def _safe_delete_doctype_if_custom_or_slnee(name: str) -> None:
    """
    إذا DocType موجود فعلاً:
    - نحذفه فقط لو custom=1 أو module=Slnee
    - غير كذا (قياسي) نتجاهله 100%
    """
    if not frappe.db.exists("DocType", name):
        return

    meta = frappe.get_cached_value("DocType", name, ["module", "custom"], as_dict=True)
    is_custom = bool(meta.get("custom"))
    is_slnee = (meta.get("module") == MODULE_NAME)

    if not (is_custom or is_slnee):
        frappe.logger().info(f"[slnee_cleanup] Skip core/standard DocType: {name} (module={meta.get('module')}, custom={meta.get('custom')})")
        return

    # الأفضل حذف الـ DocType نفسه عبر Frappe (ينظف أكثر)
    try:
        frappe.delete_doc("DocType", name, force=1, ignore_permissions=True)
        frappe.logger().info(f"[slnee_cleanup] Deleted DocType via framework: {name}")
    except Exception as e:
        # لو فشل لأي سبب، نرجع لتنظيف يدوي (بدون لمس قياسي)
        frappe.logger().warning(f"[slnee_cleanup] delete_doc failed for {name}; fallback cleanup. err={e}")
        _cleanup_references(name)
        _cleanup_orphan_metadata(name)
        _drop_table_if_exists_for_doctype(name)

def execute():
    frappe.logger().info("[slnee_cleanup] Starting deep cleanup...")

    # 0) حذف أي Records عامة لها module=Slnee (آمن لأن module غير قياسي عندكم)
    # استخدم has_column عشان ما يتكسر لو جدول ما عنده عمود module
    module_tables = [
        ("Report", "module"),
        ("Dashboard Chart", "module"),
        ("Workspace", "module"),
        ("Page", "module"),
        ("Print Format", "module"),
        ("Client Script", "module"),
        ("Server Script", "module"),
        ("Module Def", "module_name"),
    ]
    for dt, col in module_tables:
        try:
            if frappe.db.has_column(dt, col):
                frappe.db.sql(f"DELETE FROM `tab{dt}` WHERE `{col}`=%s", (MODULE_NAME,))
        except Exception:
            pass

    # 1) أهداف التنظيف
    targets = _get_targets()

    # 2) نظّف كل هدف:
    for name in targets:
        # أولًا نظّف المراجع (حتى لو Orphan)
        _cleanup_references(name)

        # لو DocType موجود: احذفه فقط لو Custom أو Module=Slnee
        if frappe.db.exists("DocType", name):
            _safe_delete_doctype_if_custom_or_slnee(name)
            continue

        # لو غير موجود: هذا Orphan → امسح Metadata + Drop Table
        _cleanup_orphan_metadata(name)
        _drop_table_if_exists_for_doctype(name)

        frappe.logger().info(f"[slnee_cleanup] Cleaned orphan: {name}")

    frappe.db.commit()
    frappe.logger().info("[slnee_cleanup] Done.")
