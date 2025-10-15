# install.py

import click
import frappe

from taj_core import setup as setup_module
from taj_core.qc.doctype.visitor.visitor import create_new_visitor_notification


def after_install():
    try:
        click.secho("Setting up Taj Core...", fg="cyan")

        # 1) إنشاء الحقول
        setup_module.after_install()

        # 2) إنشاء Notification "New Visitor" (اختياري: لا نفشل التثبيت لو لم تتوفر)
        try:
            create_new_visitor_notification()
            click.secho("Created 'New Visitor' notification.", fg="green")
        except Exception as notify_err:
            # لا نرمي الاستثناء كي لا نفشل التثبيت بالكامل
            frappe.logger().warning(
                f"Optional step failed: create_new_visitor_notification: {notify_err}"
            )
            click.secho(
                "Warning: could not create 'New Visitor' notification (optional).",
                fg="yellow",
            )

        click.secho(
            "Thank you for installing Taj Core!", fg="green"
        )

    except Exception as e:
        # حدّث هذا الرابط إلى مستودعك الفعلي
        BUG_REPORT_URL = "https://github.com/magedbjn/taj_core/issues/new"
        click.secho(
            "Installation for Taj Core failed due to an error."
            " Please try re-installing the app or"
            f" report the issue on {BUG_REPORT_URL} if not resolved.",
            fg="bright_red",
        )
        raise e
