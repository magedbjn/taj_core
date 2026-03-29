frappe.ui.form.on("Laboratory Test", {
	refresh(frm) {
		frm.set_query("item", () => {
			const filters = { disabled: 0 };

			if (
				frm.doc.test_for === "Production" &&
				frm.doc.section_break_ksom === "Finished Product"
			) {
				filters.item_group = "Finished Goods";
			}

			return { filters };
		});

		frm.trigger("set_batch_query");
	},

	set_batch_query(frm) {
		frm.set_query("batch_no_link", () => {
			if (!frm.doc.item) {
				return {
					filters: {
						name: ["=", ""]
					}
				};
			}

			return {
				filters: {
					item: frm.doc.item
				}
			};
		});
	},

	test_for(frm) {
		frm.set_value("item", null);
		frm.set_value("batch_no_link", null);
	},

	section_break_ksom(frm) {
		frm.set_value("item", null);
		frm.set_value("batch_no_link", null);
	},

	item(frm) {
		frm.set_value("batch_no_link", null);
		frm.trigger("set_batch_query");
	}
});