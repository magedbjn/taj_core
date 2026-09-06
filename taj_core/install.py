# install.py

import click
import frappe
from taj_core import setup as setup_module

BUG_REPORT_URL = "https://github.com/magedbjn/taj_core/issues/new"

# ---------- Helpers ----------
def ensure_module(module_name: str, app_name: str = None):
    """تأكد من وجود Module Def بنفس الاسم (مهم قبل ربط الـ Workspace)."""
    if not module_name:
        return
    if not frappe.db.exists("Module Def", module_name):
        doc = frappe.get_doc({
            "doctype": "Module Def",
            "module_name": module_name,
            # (اختياري) اربط التطبيق لو تبغى
            **({"app_name": app_name} if app_name else {})
        })
        doc.insert(ignore_permissions=True)

def ensure_workspace(name, module=None, public=True, hidden=False, label=None):
    """ينشئ/يحدّث Workspace بشكل آمن وقابل للإعادة."""
    # تأكد من وجود الموديول أولاً
    if module:
        ensure_module(module)

    exists = frappe.db.exists("Workspace", name)
    if not exists:
        ws = frappe.get_doc({
            "doctype": "Workspace",
            "name": name,                  # المفتاح الأساسي (لا نعيد تسميته هنا)
            "title": label or name,        # العنوان الظاهر للمستخدم
            "public": public,
            "for_user": "",
            "module": module,
            "hidden": hidden,
        })
        ws.insert(ignore_permissions=True)
        return True

    ws = frappe.get_doc("Workspace", name)
    changed = False

    if module is not None and ws.get("module") != module:
        ws.module = module
        changed = True

    # تأكد من الوضعية
    if ws.get("public") != public:
        ws.public = public
        changed = True

    if ws.get("hidden") != hidden:
        ws.hidden = hidden
        changed = True

    # حدّث العنوان الظاهر لو طلبت label
    if label and ws.get("title") != label:
        ws.title = label
        changed = True

    if changed:
        ws.save(ignore_permissions=True)
    return changed

# ---------- Lifecycle ----------
def after_install():
    try:
        click.secho("🚀 Setting up Taj Core...", fg="cyan")
        setup_module.after_install()
        create_visitor_notification_safely()
        click.secho("🎉 Thank you for installing Taj Core!", fg="green")
    except Exception as e:
        handle_installation_error(e)

def after_migrate():
    """يُستدعى بعد كل bench migrate (على Frappe Cloud أثناء الـ Deploy عند وجود هجرة)."""
    try:
        click.secho("🔄 Verifying Taj Core customizations...", fg="blue")
        setup_module.after_migrate()
        click.secho("✅ Taj Core custom fields verified successfully", fg="green")

        # ثبّت Workspaces المطلوبة
        # ensure_workspace(name="QC",          module="QC",                 label="QC")
        # ensure_workspace(name="RND",         module="RND",                label="R&D")
        # ensure_workspace(name="Engineering", module="Engineering",        label="Engineering")
        # ensure_workspace(name="Documents",   module="Company Documents",  label="Documents")
        # frappe.db.commit()
        # click.secho("✅ Workspaces verified/created successfully", fg="green")

    except Exception as e:
        handle_migration_error(e)

# ---------- Optional Objects ----------
def create_visitor_notification_safely():
    try:
        from taj_core.qc.doctype.visitor.visitor import create_new_visitor_notification
        create_new_visitor_notification()
        click.secho("✅ Created 'New Visitor' notification", fg="green")
    except ImportError as e:
        frappe.logger().warning(f"Visitor module not available: {e}")
    except Exception as e:
        frappe.logger().warning(f"Could not create visitor notification: {e}")
        click.secho("⚠️ Could not create 'New Visitor' notification (optional)", fg="yellow")

# ---------- Error Handling ----------
def handle_installation_error(error):
    frappe.log_error(f"Taj Core Installation Failed: {str(error)}")
    click.secho(
        f"❌ Installation failed: {str(error)}\nPlease report the issue on {BUG_REPORT_URL}",
        fg="red"
    )
    raise error

def handle_migration_error(error):
    frappe.log_error(f"Taj Core Migration Failed: {str(error)}")
    click.secho(
        f"❌ Migration failed: {str(error)}\nPlease report the issue on {BUG_REPORT_URL}",
        fg="red"
    )
    frappe.db.rollback()
    raise error
