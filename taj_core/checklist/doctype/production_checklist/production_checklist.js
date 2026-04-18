// Copyright (c) 2026, Maged Bajandooh and contributors
// For license information, please see license.txt

frappe.ui.form.on("Production Checklist", {
	setup: function (frm) {
		frm.set_query("reference_name", function (doc) {
			let filters = { docstatus: ["!=", 2] };

			if (doc.company) {
				filters["company"] = doc.company;
			}

			return {
				filters: filters,
			};
		});
    },

    production_checklist_template: function (frm) {
		if (frm.doc.quality_inspection_template) {
			return frm.call({
				method: "get_item_specification_details",
				doc: frm.doc,
				callback: function () {
					refresh_field("readings");
				},
			});
		}
	},
});

