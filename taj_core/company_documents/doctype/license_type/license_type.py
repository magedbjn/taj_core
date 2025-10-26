# license_type.py
import frappe
from frappe.model.document import Document
from frappe.utils import today, getdate
from frappe import _

class LicenseType(Document):
    def on_update(self):
        # في حال تغيّر no_expiry: طبّق التعديلات على الحقول/التواريخ والحالة
        if self.has_value_changed("no_expiry"):
            propagate_no_expiry_change(
                license_type_name=self.name,
                new_no_expiry=int(self.no_expiry or 0)
            )

        # في حال تغيّر renew: أعد حساب الحالة لكل التراخيص ذات الانتهاء
        if self.has_value_changed("renew"):
            propagate_renew_change(
                license_type_name=self.name,
                new_renew=int(self.renew or 0)
            )


def propagate_no_expiry_change(license_type_name: str, new_no_expiry: int):
    """توحيد تحديث no_expiry و expiry_date (والحالة) دفعة واحدة عند تغيّر no_expiry."""
    today_date = getdate(today())

    # إذا no_expiry=1: اجعل expiry_date = NULL واجعل الحالة Active
    # إذا no_expiry=0: عيّن expiry_date = اليوم (كما طلبت سابقًا) واترك الحالة كما هي (سيُعاد حسابها لاحقًا بالمجدولة أو يدويًا)
    frappe.db.sql("""
        UPDATE `tabLicense`
        SET
            `no_expiry` = %(new)s,
            `expiry_date` = CASE
                WHEN %(new)s = 1 THEN NULL
                WHEN %(new)s = 0 THEN %(today)s
                ELSE `expiry_date`
            END,
            `status` = CASE
                WHEN %(new)s = 1 THEN 'Active'   -- التراخيص بلا انتهاء دائماً Active
                ELSE `status`
            END
        WHERE `license_english` = %(lt)s
    """, {
        "new": int(new_no_expiry),
        "today": today_date,
        "lt": license_type_name,
    })

    frappe.db.commit()

def propagate_renew_change(license_type_name: str, new_renew: int):
    """
    عند تغيّر نافذة التجديد (renew)، أعد حساب الحالة للتراخيص التي لها انتهاء فقط (no_expiry=0).
    لا يتم إرسال تنبيهات هنا؛ الإشعارات تتم عبر المجدولة فقط.
    """
    renew = max(0, int(new_renew or 0))

    # منطق الحالة نفسه الموجود لديك:
    #   DATEDIFF(expiry_date, CURDATE()) < 0          -> 'Expired'
    #   BETWEEN 0 AND renew                           -> 'Renew'
    #   غير ذلك                                       -> 'Active'
    #
    # نتجنّب التغيير للتراخيص بلا انتهاء أو بلا تاريخ.
    frappe.db.sql("""
        UPDATE `tabLicense` l
        SET l.status = CASE
            WHEN l.no_expiry = 1 OR l.expiry_date IS NULL THEN l.status
            WHEN DATEDIFF(l.expiry_date, CURDATE()) < 0 THEN 'Expired'
            WHEN DATEDIFF(l.expiry_date, CURDATE()) BETWEEN 0 AND %(renew)s THEN 'Renew'
            ELSE 'Active'
        END
        WHERE l.license_english = %(lt)s
          AND l.no_expiry = 0
    """, {"renew": renew, "lt": license_type_name})

    frappe.db.commit()