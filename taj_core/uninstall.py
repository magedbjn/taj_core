# uninstall.py

import click
from taj_core import setup as setup_module


def before_uninstall():
    try:
        click.secho("Removing customizations created by Taj Core...", fg="cyan")

        # يحذف الحقول مع استثناء الحقول المحمية كما هو معرّف داخل setup.before_uninstall
        setup_module.before_uninstall()

    except Exception as e:
        # حدّث هذا الرابط إلى مستودعك الفعلي
        BUG_REPORT_URL = "https://github.com/magedbjn/taj_core/issues/new"
        click.secho(
            "Removing customizations for Taj Core failed due to an error."
            " Please try again or"
            f" report the issue on {BUG_REPORT_URL} if not resolved.",
            fg="bright_red",
        )
        raise e

    click.secho(
        "Taj Core customizations have been removed successfully...", fg="green"
    )
