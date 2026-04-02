frappe.query_reports["Global Stock Summary"] = {
	filters: [
		{
			fieldname: "items",
			label: __("Item"),
			fieldtype: "MultiSelectList",
			get_data: function (txt) {
				return frappe.db.get_link_options("Item", txt);
			}
		},
		{
			fieldname: "item_groups",
			label: __("Item Group"),
			fieldtype: "MultiSelectList",
			get_data: function (txt) {
				return frappe.db.get_link_options("Item Group", txt);
			}
		}
	]
};