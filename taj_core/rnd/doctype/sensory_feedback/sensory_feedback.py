import frappe
from frappe.model.document import Document
from frappe.utils import today, getdate, formatdate

class SensoryFeedback(Document):
    pass


def sync_to_product_proposal(doc: "SensoryFeedback", method=None):
    """Push webform submission into Product Proposal's child table (pp_sensory_evaluation)."""
    # 1) تحقّق من وجود الرابط إلى Product Proposal
    item_name = (doc.item or "").strip()
    if not item_name:
        # لا يوجد هدف نضيف له الصف
        return

    if not frappe.db.exists("Product Proposal", item_name):
        # اسم غير صحيح/غير موجود، نتجاهل بصمت
        return

    # 2) جهّز القيم
    eval_date = doc.evaluation_date or today()
    try:
        # طيّع التنسيق لو أُرسِل كنص
        eval_date = getdate(eval_date)
        # جدول الطفل عندك الحقل evaluation_date = Data (مش Date)
        # لذلك نخزّنها كنص منسّق YYYY-MM-DD أو حسب تفضيلك:
        eval_date_str = formatdate(eval_date, "yyyy-MM-dd")
    except Exception:
        eval_date_str = eval_date  # fallback

    row_values = {
        "evaluation_date": eval_date_str,
        "appearance": doc.appearance,
        "texture": doc.texture,
        "taste": doc.taste,
        "spicy": doc.spicy,
    }

    # 3) أضِف الصف إلى جدول الطفل واحفظ
    pp = frappe.get_doc("Product Proposal", item_name)
    pp.append("pp_sensory_evaluation", row_values)

    # بما أن الـ Web Form يسمح بالـ anonymous، نخزّن مع تجاهل الصلاحيات
    pp.save(ignore_permissions=True)
    frappe.db.commit()

