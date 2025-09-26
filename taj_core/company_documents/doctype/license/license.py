import frappe
from frappe.model.document import Document
from frappe.utils import getdate, today, date_diff, nowdate
from frappe import _

def get_license_status(days_difference, renew_days=0):
    """Returns the status of a license based on days_difference and renew_days."""
    if days_difference < 0:
        return 'Expired'
    elif 0 <= days_difference <= renew_days:
        return 'Renew'
    return 'Active'


class License(Document):
    """License doctype logic. Updates status before saving."""
    def before_save(self):
        self.update_license_status()

    def update_license_status(self):
        if not self.expiry_date:
            return
        try:
            today_date = getdate(today())
            expiry_date = getdate(self.expiry_date)
            days_difference = date_diff(expiry_date, today_date)
            renew_days = frappe.get_cached_value('License Type', self.license_english, 'renew') or 0

            new_status = get_license_status(days_difference, renew_days)
            if self.status != new_status:
                self.status = new_status
        except Exception as e:
            frappe.log_error(f"Error updating status for license {self.name}: {str(e)}",
                             "License Status Update Error")


def scheduled_status_update():
    """Scheduled task to update all non-expired licenses in bulk and send notifications."""
    updated_docs = update_status_bulk('License', filters={'status': ['!=', 'Expired']})
    
    for doc in updated_docs:
        if doc.status == 'Renew':
            send_license_notification(doc)


def update_status_bulk(doctype, filters=None):
    """Bulk update license status and return updated docs."""
    filters = filters or {}
    filters.setdefault('status', ['!=', 'Expired'])

    today_date = getdate(today())
    docs = frappe.get_all(
        doctype,
        filters=filters,
        fields=['name', 'expiry_date', 'status', 'license_english']
    )

    cases = []
    names = []
    params = []
    updated_docs = []

    for doc in docs:
        if not doc.get('expiry_date'):
            continue
        try:
            expiry_date = getdate(doc.expiry_date)
            days_difference = date_diff(expiry_date, today_date)
            renew_days = frappe.get_cached_value('License Type', doc.get('license_english'), 'renew') or 0
            new_status = get_license_status(days_difference, renew_days)

            if doc.get('status') != new_status:
                # بناء CASE مع placeholders
                cases.append("WHEN %s THEN %s")
                params.extend([doc['name'], new_status])
                names.append(doc['name'])

                # حفظ doc محدث مع الحالة الجديدة
                doc['status'] = new_status
                updated_docs.append(frappe.get_doc(doctype, doc['name']))
        except Exception as e:
            frappe.log_error(f"Error processing license {doc.get('name')}: {str(e)}",
                             "Bulk License Status Update Error")

    if cases:
        case_sql = " ".join(cases)
        placeholders = ", ".join(["%s"] * len(names))
        params.extend(names)

        sql = f"""
            UPDATE `tab{doctype}`
            SET `status` = CASE `name`
                {case_sql}
            END
            WHERE `name` IN ({placeholders})
        """
        frappe.db.sql(sql, params)
        frappe.db.commit()
        frappe.logger().info(f"{len(names)} licenses updated in bulk for {doctype}")

    return updated_docs

def send_license_notification(doc):
    """Send notification to Allowed Role via Telegram or Email"""
    license_type = frappe.get_doc("License Type", doc.license_english)
    allowed_role = license_type.allowed_roles  # now it's a single role (Link field)

    users_to_notify = frappe.get_all(
        "User",
        filters={"enabled": 1},
        fields=["name", "email"]
    )

    for user in users_to_notify:
        roles = frappe.get_roles(user['name'])
        if allowed_role in roles:
            subject = _("License {0} Renewal Reminder").format(doc.name)
            message = _("The license {0} has reached the 'Renew' status. Please take the necessary action.").format(doc.name)

            frappe.sendmail(
                recipients=user['email'],
                subject=subject,
                message=message
            )

