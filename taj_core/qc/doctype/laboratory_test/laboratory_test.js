// Copyright (c) 2024, MAged BAjandooh and contributors
// For license information, please see license.txt

frappe.ui.form.on("Laboratory Test", {
	item:function(frm) {
		frm.set_query("item", function () {
			return {
				filters: {
					disabled: 0,
				},
			};
		});
	},
});
