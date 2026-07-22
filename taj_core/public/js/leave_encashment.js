// Copyright (c) 2026, Taj and contributors
// For license information, please see license.txt

const TAJ_DEFAULT_EXPENSE_ACCOUNT =
	"2203010003 - Accrued annual vacation - Taj";

const TAJ_DEFAULT_PAYABLE_ACCOUNT =
	"1104020001 - Staff Cash Advance - Taj";


frappe.ui.form.on("Leave Encashment", {
	refresh(frm) {
		/*
		 * تعبئة الحسابات في المستندات المسودة القديمة
		 * إذا كان Pay Via Payment Entry مفعّلًا والحسابات فارغة.
		 *
		 * لا يتم استبدال أي حساب تم إدخاله أو تغييره يدويًا.
		 */
		if (
			frm.doc.docstatus === 0 &&
			frm.doc.pay_via_payment_entry === 1
		) {
			frm.trigger("taj_set_default_payment_accounts");
		}
	},

	pay_via_payment_entry(frm) {
		/*
		 * عند تفعيل Pay Via Payment Entry:
		 * تعبئة الحسابات الافتراضية إذا كانت فارغة.
		 */
		if (frm.doc.pay_via_payment_entry === 1) {
			frm.trigger("taj_set_default_payment_accounts");
		}
	},

	taj_encashment_calculation_method(frm) {
		/*
		 * إعادة حساب تعويض الإجازة عند تغيير طريقة الحساب.
		 *
		 * تستخدم الدالة القياسية الموجودة في Leave Encashment.
		 */
		if (
			frm.doc.docstatus === 0 &&
			frm.doc.employee &&
			frm.doc.leave_type
		) {
			frm.trigger("get_leave_details_for_encashment");
		}
	},

	async taj_set_default_payment_accounts(frm) {
		if (
			frm.doc.docstatus !== 0 ||
			frm.doc.pay_via_payment_entry !== 1
		) {
			return;
		}

		const values = {};

		/*
		 * لا يتم تغيير الحساب إذا كان يحتوي على قيمة،
		 * حتى يستطيع المستخدم تعديله يدويًا.
		 */
		if (!frm.doc.expense_account) {
			values.expense_account = TAJ_DEFAULT_EXPENSE_ACCOUNT;
		}

		if (!frm.doc.payable_account) {
			values.payable_account = TAJ_DEFAULT_PAYABLE_ACCOUNT;
		}

		if (Object.keys(values).length > 0) {
			await frm.set_value(values);
		}
	},
});