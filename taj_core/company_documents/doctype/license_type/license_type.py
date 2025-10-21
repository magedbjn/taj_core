# license_type.py
import frappe
from frappe.model.document import Document
from frappe.utils import today, getdate
from frappe import _

class LicenseType(Document):
	def on_update(self):
		no_expiry = self.has_value_changed("no_expiry")

		if no_expiry:
			propagate_no_expiry_change(
					license_type_name=self.name,
					new_no_expiry=self.no_expiry
				)


def propagate_no_expiry_change(license_type_name: str, new_no_expiry: int):
    today_date = getdate(today())

    # تحديث واحد يضبط no_expiry + expiry_date حسب الانتقال
    frappe.db.sql("""
        UPDATE `tabLicense`
        SET
            `no_expiry` = %(new)s,
            `expiry_date` = CASE
                WHEN %(new)s = 1 THEN NULL
                WHEN %(new)s = 0 THEN %(today)s
                ELSE `expiry_date`
            END
        WHERE `license_english` = %(lt)s
    """, {
        "new": int(new_no_expiry),
        "today": today_date,
        "lt": license_type_name,
    })

    frappe.db.commit()