const QUANTITY_BY_PERIOD_MONTHS = [
	"Jan", "Feb", "Mar", "Apr", "May", "Jun",
	"Jul", "Aug", "Sep", "Oct", "Nov", "Dec"
];

frappe.query_reports["Quantity by Period"] = {
	tree: true,
	name_field: "node_name",
	parent_field: "parent_node",
	initial_depth: 2,

	onload(report) {
		report.page.add_inner_button(__("Collapse All"), () => {
			this.toggle_all_nodes(report, "collapse");
		});

		report.page.add_inner_button(__("Expand All"), () => {
			this.toggle_all_nodes(report, "expand");
		});
	},

	toggle_all_nodes(report, action) {
		const dt = report.datatable;
		const settings = frappe.query_reports["Quantity by Period"];

		settings.initial_depth = action === "collapse" ? 0 : 99;

		if (dt && dt.rowmanager) {
			const methods = action === "collapse"
				? ["collapseAllNodes", "collapse_all_nodes"]
				: ["expandAllNodes", "expand_all_nodes"];

			for (const method of methods) {
				if (typeof dt.rowmanager[method] === "function") {
					dt.rowmanager[method]();
					dt.refresh();
					return;
				}
			}
		}

		report.refresh();
	},

	filters: [
		{
			fieldname: "item_groups",
			label: __("Item Group"),
			fieldtype: "MultiSelectList",
			get_data: function (txt) {
				return frappe.db.get_link_options("Item Group", txt);
			}
		},
		{
			fieldname: "date_filter_type",
			label: __("Date Filter"),
			fieldtype: "Select",
			options: "Custom\nMonthly\nYearly",
			default: "Monthly",
			reqd: 1
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.month_start(),
			depends_on: "eval:doc.date_filter_type=='Custom'"
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.month_end(),
			depends_on: "eval:doc.date_filter_type=='Custom'"
		},
		{
			fieldname: "month",
			label: __("Month"),
			fieldtype: "Select",
			options: QUANTITY_BY_PERIOD_MONTHS.join("\n"),
			default: QUANTITY_BY_PERIOD_MONTHS[new Date().getMonth()],
			depends_on: "eval:doc.date_filter_type=='Monthly'"
		},
		{
			fieldname: "month_year",
			label: __("Year"),
			fieldtype: "Int",
			default: new Date().getFullYear(),
			depends_on: "eval:doc.date_filter_type=='Monthly'"
		},
		{
			fieldname: "year_option",
			label: __("Year"),
			fieldtype: "Select",
			options: "This Year\nLast Year",
			default: "This Year",
			depends_on: "eval:doc.date_filter_type=='Yearly'"
		},
		{
			fieldname: "transaction_scope",
			label: __("Transaction Scope"),
			fieldtype: "Select",
			options: "All\nPurchased Materials\nManufactured Items",
			default: "All",
			reqd: 1
		},
		{
			fieldname: "unit",
			label: __("Unit"),
			fieldtype: "Select",
			options: "Kg\nTon",
			default: "Kg",
			reqd: 1
		}
	],

	formatter(value, row, column, data, default_formatter) {
		if (column.fieldname === "node_name") {
			column.is_tree = true;
			column.df = column.df || {};
			column.df.is_tree = true;
		}

		let formatted = default_formatter(value, row, column, data);

		if (data && data.is_error_row) {
			formatted = `<span style="color:#d9534f;font-weight:600;">${formatted || ""}</span>`;
		}

		if (data && (data.is_group_row || data.is_total_row)) {
			formatted = `<b>${formatted || ""}</b>`;
		}

		return formatted;
	}
};