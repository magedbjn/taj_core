# license.py
import frappe
from frappe.model.document import Document
from frappe.utils import getdate, today, date_diff
from frappe import _

def get_license_status(days_difference, renew_days=0):
    """
    Calculate license status based on days difference and renew days
    
    Args:
        days_difference (int): Days until expiry
        renew_days (int): Days before expiry to show renew status
    
    Returns:
        str: License status ('Expired', 'Renew', 'Active')
    """
    if days_difference < 0:
        return 'Expired'
    elif 0 <= days_difference <= renew_days:
        return 'Renew'
    return 'Active'


class License(Document):
    def validate(self):
        """Validate license document before saving"""
        # Check if license type exists
        if not self.license_english:
            frappe.throw(_("License Type is required"))
        
        if not frappe.db.exists("License Type", self.license_english):
            frappe.throw(_("Selected License Type does not exist"))

        # Get license type with caching
        lt = frappe.get_cached_doc("License Type", self.license_english)
        
        # Check if license type is disabled
        if lt.disabled:
            frappe.throw(_("Selected License Type is disabled"))

        # Secure renew value
        try:
            self._renew_days = max(0, int(getattr(lt, "renew", 0) or 0))
        except (ValueError, TypeError):
            self._renew_days = 0

        # Handle no expiry licenses
        if getattr(lt, "no_expiry", 0):
            self.expiry_date = None
            self.status = "Active"

    def before_save(self):
        """Update license status before saving"""
        # Skip status calculation for no-expiry licenses
        lt = frappe.get_cached_doc("License Type", self.license_english)
        if getattr(lt, "no_expiry", 0):
            self.status = "Active"
            return
        self.update_license_status()

    def update_license_status(self):
        """Update the status based on expiry date"""
        if not self.expiry_date:
            return
            
        # Validate date format
        try:
            expiry_date = getdate(self.expiry_date)
            if expiry_date < getdate('1900-01-01'):
                frappe.throw(_("Invalid expiry date"))
        except Exception:
            frappe.throw(_("Invalid expiry date format"))

        try:
            today_date = getdate(today())
            expiry_date = getdate(self.expiry_date)
            days_difference = date_diff(expiry_date, today_date)

            # Get renew days from cache or attribute
            renew_days = getattr(self, "_renew_days", None)
            if renew_days is None:
                renew_days = frappe.get_cached_value('License Type', self.license_english, 'renew') or 0
                try:
                    renew_days = max(0, int(renew_days))
                except (ValueError, TypeError):
                    renew_days = 0

            new_status = get_license_status(days_difference, renew_days)
            if self.status != new_status:
                self.status = new_status
        except Exception as e:
            frappe.log_error(
                f"Error updating status for license {self.name}: {str(e)}",
                "License Status Update Error"
            )


def scheduled_status_update():
    """Scheduled bulk status update and renewal notifications"""
    updated_rows = update_status_bulk('License', filters={'status': ['!=', 'Expired']})
    for row in updated_rows:
        if row.get('status') == 'Renew':
            send_license_notification(row)


def update_status_bulk(doctype, filters=None, batch_size=500):
    """
    Bulk update license statuses with batch processing
    
    Args:
        doctype (str): Document type to update
        filters (dict): Filters for query
        batch_size (int): Number of records per batch
    
    Returns:
        list: Updated rows with status information
    """
    filters = filters or {}
    filters.setdefault('status', ['!=', 'Expired'])

    today_date = getdate(today())

    # Cache all license types
    license_types = {
        lt["name"]: {
            "no_expiry": lt.get("no_expiry") or 0,
            "renew": lt.get("renew") or 0
        }
        for lt in frappe.get_all("License Type", fields=["name", "no_expiry", "renew"])
    }

    updated_rows = []
    start = 0
    
    # Process in batches for better performance
    while True:
        docs = frappe.get_all(
            doctype,
            filters=filters,
            fields=['name', 'expiry_date', 'status', 'license_english'],
            limit_start=start,
            limit_page_length=batch_size
        )
        
        if not docs:
            break
            
        cases, names, params = [], [], []

        for doc in docs:
            lt_info = license_types.get(doc.get('license_english')) or {"no_expiry": 0, "renew": 0}

            # Handle no-expiry licenses
            if lt_info["no_expiry"]:
                if doc.get('status') != 'Active':
                    cases.append("WHEN %s THEN %s")
                    params.extend([doc['name'], 'Active'])
                    names.append(doc['name'])
                    updated_rows.append({
                        "name": doc['name'],
                        "license_english": doc['license_english'],
                        "status": 'Active'
                    })
                continue

            # Skip if no expiry date
            if not doc.get('expiry_date'):
                continue

            try:
                expiry_date = getdate(doc['expiry_date'])
                days_difference = date_diff(expiry_date, today_date)
                try:
                    renew_days = max(0, int(lt_info["renew"] or 0))
                except (ValueError, TypeError):
                    renew_days = 0

                new_status = get_license_status(days_difference, renew_days)

                if doc.get('status') != new_status:
                    cases.append("WHEN %s THEN %s")
                    params.extend([doc['name'], new_status])
                    names.append(doc['name'])
                    updated_rows.append({
                        "name": doc['name'],
                        "license_english": doc['license_english'],
                        "status": new_status
                    })
            except Exception as e:
                frappe.log_error(
                    f"Error processing license {doc.get('name')}: {str(e)}",
                    "Bulk License Status Update Error"
                )

        # Execute batch update
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
            
        start += batch_size

    if updated_rows:
        frappe.db.commit()
        frappe.logger().info(f"{len(updated_rows)} licenses updated in bulk for {doctype}")

    return updated_rows


def send_license_notification(row: dict):
    """
    Send notification for license renewal
    
    Args:
        row (dict): License data containing name, license_english, and status
    """
    license_type = frappe.get_cached_doc("License Type", row['license_english'])
    allowed_role = license_type.allowed_roles
    if not allowed_role:
        return

    # Get users with the allowed role
    has_roles = frappe.get_all(
        "Has Role",
        filters={"role": allowed_role},
        fields=["parent as user"],
        distinct=True
    )
    if not has_roles:
        return

    # Get all emails in one query - بدون استخدام pluck
    users = [hr["user"] for hr in has_roles]
    user_docs = frappe.get_all("User", 
        filters={"name": ["in", users]}, 
        fields=["email"]
    )
    emails = [u["email"] for u in user_docs if u.get("email")]

    if emails:
        subject = _("License {0} Renewal Reminder").format(row['name'])
        message = _(
            "The license {0} has reached the 'Renew' status. "
            "Please take the necessary action."
        ).format(row['name'])
        
        frappe.sendmail(
            recipients=emails, 
            subject=subject, 
            message=message
        )
        frappe.logger().info(f"Renewal notification sent for license {row['name']} to {len(emails)} users")