# install.py

import click
import frappe
from taj_core import setup as setup_module

def after_install():
    try:
        click.secho("🚀 Setting up Taj Core...", fg="cyan")
        
        # 1) إنشاء الحقول
        setup_module.after_install()
        
        # 2) إنشاء الإشعار (اختياري)
        create_visitor_notification_safely()
        
        click.secho("🎉 Thank you for installing Taj Core!", fg="green")
        
    except Exception as e:
        handle_installation_error(e)

def after_migrate():
    """يُستدعى بعد كل bench migrate"""
    try:
        click.secho("🔄 Verifying Taj Core customizations...", fg="blue")
        setup_module.after_migrate()
        click.secho("✅ Taj Core custom fields verified successfully", fg="green")
    except Exception as e:
        handle_migration_error(e)

def create_visitor_notification_safely():
    """ينشئ إشعار الزائر مع معالجة آمنة للأخطاء"""
    try:
        from taj_core.qc.doctype.visitor.visitor import create_new_visitor_notification
        create_new_visitor_notification()
        click.secho("✅ Created 'New Visitor' notification", fg="green")
    except ImportError as e:
        frappe.logger().warning(f"Visitor module not available: {e}")
    except Exception as e:
        frappe.logger().warning(f"Could not create visitor notification: {e}")
        click.secho("⚠️ Could not create 'New Visitor' notification (optional)", fg="yellow")

def handle_installation_error(error):
    BUG_REPORT_URL = "https://github.com/magedbjn/taj_core/issues/new"
    frappe.log_error(f"Taj Core Installation Failed: {str(error)}")
    click.secho(
        f"❌ Installation failed: {str(error)}\n"
        f"Please report the issue on {BUG_REPORT_URL}",
        fg="red"
    )
    raise error

def handle_migration_error(error):
    BUG_REPORT_URL = "https://github.com/magedbjn/taj_core/issues/new"
    frappe.log_error(f"Taj Core Migration Failed: {str(error)}")
    click.secho(
        f"❌ Migration failed: {str(error)}\n"
        f"Please report the issue on {BUG_REPORT_URL}",
        fg="red"
    )
    # لا ترفع الخطأ في الميجرشن كي لا تعطل النظام كاملاً
    frappe.db.rollback()