frappe.query_reports["Production Plan Period Hierarchy"] = {
	tree: true,
	name_field: "label",
	initial_depth: 10,

	onload: function (report) {
		toggle_planning_view_filters(report);
		add_expand_collapse_buttons(report);
	},

	after_datatable_render: function (datatable, report) {
		toggle_planning_view_filters(report || frappe.query_report);
		add_expand_collapse_buttons(report || frappe.query_report);
	},

	filters: [
		{
			fieldname: "production_plan",
			label: __("Production Plan"),
			fieldtype: "Link",
			options: "Production Plan",
			reqd: 1,
			get_query: function () {
				return {
					query: "taj_core.taj_core.report.production_plan_period_hierarchy.production_plan_period_hierarchy.production_plan_query"
				};
			}
		},
		{
			fieldname: "period_bucket",
			label: __("Period Bucket"),
			fieldtype: "Select",
			options: "None\nWeek\n2 Weeks\n3 Weeks\nMonth",
			default: "None"
		},
		{
			fieldname: "planning_view",
			label: __("Planning View"),
			fieldtype: "Select",
			options: "Production\nRaw Materials",
			default: "Production",
			on_change: function () {
				const report = frappe.query_report;
				toggle_planning_view_filters(report);
				report.refresh();
			}
		},
		{
			fieldname: "sub_assembly_items",
			label: __("Sub Assemble Items"),
			fieldtype: "MultiSelectList",
			get_data: function (txt) {
				const production_plan = frappe.query_report.get_filter_value("production_plan");
				if (!production_plan) {
					return [];
				}

				return frappe.xcall(
					"taj_core.taj_core.report.production_plan_period_hierarchy.production_plan_period_hierarchy.get_sub_assembly_item_options",
					{
						txt: txt,
						production_plan: production_plan
					}
				);
			}
		},
		{
			fieldname: "group_assemble_items",
			label: __("Group Assemble Items"),
			fieldtype: "Check",
			default: 1
		},
		{
			fieldname: "group_sub_assemble_items",
			label: __("Group Sub Assemble Items"),
			fieldtype: "Check",
			default: 1
		},
		{
			fieldname: "group_raw_materials",
			label: __("Group Raw Materials"),
			fieldtype: "Check",
			default: 1
		}
	],

	formatter: function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);

		if (!data) {
			return value;
		}

		if (column.fieldname === "label") {
			const indent = Number(data.indent || 0) * 18;
			value = `<span style="padding-left:${indent}px">${value}</span>`;

			if (data.row_type === "Period") {
				value = `<span style="font-weight:700">${value}</span>`;
			}

			if (data.row_type === "Assemble Item" || data.row_type === "Sub Assemble Item") {
				value = `<span style="font-weight:600">${value}</span>`;
			}
		}

		if (data.row_type === "Period" && column.fieldname !== "label") {
			return "";
		}

		return value;
	}
};


function toggle_planning_view_filters(report) {
	const planning_view = report.get_filter_value("planning_view");
	const is_raw_materials = planning_view === "Raw Materials";

	// حسب الشكل الذي طلبته أنت
	report.toggle_filter_display("group_assemble_items", is_raw_materials);
	report.toggle_filter_display("group_sub_assemble_items", is_raw_materials);
	report.toggle_filter_display("group_raw_materials", !is_raw_materials);
}


function add_expand_collapse_buttons(report) {
	if (report._expand_collapse_buttons_added) {
		return;
	}

	report.page.add_inner_button(__("Expand All"), function () {
		const dt = report.datatable;
		if (dt && dt.rowmanager && dt.rowmanager.expandAllNodes) {
			dt.rowmanager.expandAllNodes();
		} else {
			frappe.show_alert({ message: __("Expand All is not supported in this version"), indicator: "orange" });
		}
	});

	report.page.add_inner_button(__("Collapse All"), function () {
		const dt = report.datatable;
		if (dt && dt.rowmanager && dt.rowmanager.collapseAllNodes) {
			dt.rowmanager.collapseAllNodes();
		} else {
			frappe.show_alert({ message: __("Collapse All is not supported in this version"), indicator: "orange" });
		}
	});

	report._expand_collapse_buttons_added = true;
}