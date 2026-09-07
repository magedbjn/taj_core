import click
import frappe


BUG_REPORT_URL = "https://github.com/magedbjn/taj_core/issues/new"


def after_install():
    try:
        click.secho("Setting up Taj Core...", fg="cyan")
        create_visitor_notification_safely()
        click.secho("Taj Core installed successfully", fg="green")
    except Exception as error:
        handle_installation_error(error)


def create_visitor_notification_safely():
    try:
        from taj_core.qc.doctype.visitor.visitor import (
            create_new_visitor_notification,
        )

        create_new_visitor_notification()
        click.secho("Created 'New Visitor' notification", fg="green")
    except ImportError as error:
        frappe.logger().warning(
            f"Visitor module not available: {error}"
        )
    except Exception as error:
        frappe.logger().warning(
            f"Could not create visitor notification: {error}"
        )
        click.secho(
            "Could not create 'New Visitor' notification (optional)",
            fg="yellow",
        )


def handle_installation_error(error):
    frappe.log_error(
        f"Taj Core Installation Failed: {error}"
    )
    click.secho(
        "Taj Core installation failed: "
        f"{error}\nPlease report the issue on {BUG_REPORT_URL}",
        fg="red",
    )
    raise error
