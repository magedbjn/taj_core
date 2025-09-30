import frappe
from frappe import _

def raw_material_specification(doc, method=None):
    if frappe.flags.get("in_rms_update"):
        return

    # إذا الصنف لا يستخدم في المشتريات أو التصنيع، لا نتحقق
    if not (doc.is_purchase_item or doc.include_item_in_manufacturing):
        return

    # بما أن كل صنف له سجل واحد فقط → نستخدم get_value مباشرة
    status = frappe.db.get_value("Raw Material Specification", {"item_code": doc.name}, "status")

    if status == "Rejected":
        frappe.throw(_(
            "Item {0} cannot be used for Purchasing or Manufacturing because its "
            "Raw Material Specification has been <b>Rejected</b>."
        ).format(frappe.bold(doc.name)))
