// Copyright (c) 2024, MAged BAjandooh and contributors
// For license information, please see license.txt

frappe.ui.form.on("Laboratory Test", {
	refresh(frm) {
		frm.set_query("item", () => {
			// فلتر ثابت دائمًا
			const filters = { disabled: 0 };

			// فلتر إضافي فقط في حالة: Production + Finished Product
			if (
				frm.doc.test_for === "Production" &&
				frm.doc.section_break_ksom === "Finished Product"
			) {
				filters.item_group = "Finished Goods";
			}

			return { filters };
		});
	},

	// (اختياري) لما تتغير القيم، خَلّي المستخدم يختار Item من جديد
	test_for(frm) {
		frm.set_value("item", null);
	},
	section_break_ksom(frm) {
		frm.set_value("item", null);
	},

	// item:function(frm) {
	// 	frm.set_query("item", function () {
	// 		return {
	// 			filters: {
	// 				disabled: 0,
	// 			},
	// 		};
	// 	});
	// },
});
