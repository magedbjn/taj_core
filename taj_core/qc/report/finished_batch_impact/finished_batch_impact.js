frappe.query_reports["Finished Batch Impact"] = {
  filters: [
    {
      fieldname: "supplier",
      label: __("Supplier"),
      fieldtype: "Link",
      options: "Supplier"
    },
    {
      fieldname: "raw_item",
      label: __("Raw Material Item"),
      fieldtype: "Link",
      options: "Item"
    },
    {
      fieldname: "from_date",
      label: __("From Date"),
      fieldtype: "Date",
      reqd: 1
    },
    {
      fieldname: "to_date",
      label: __("To Date"),
      fieldtype: "Date",
      reqd: 1
    },
    {
      fieldname: "limit",
      label: __("Limit"),
      fieldtype: "Int",
      default: 200
    }
  ],

  onload: function () {
    // default to last 3 months
    const today = frappe.datetime.get_today();
    const from_date = frappe.datetime.add_months(today, -3);

    if (!frappe.query_report.get_filter_value("from_date")) {
      frappe.query_report.set_filter_value("from_date", from_date);
    }
    if (!frappe.query_report.get_filter_value("to_date")) {
      frappe.query_report.set_filter_value("to_date", today);
    }
  },

  formatter: function (value, row, column, data, default_formatter) {
    value = default_formatter(value, row, column, data);
    if (!data) return value;

    // Click To Batch (Top) -> open Batch Traceability report (new tab)
    if (column.fieldname === "to_batch" && data.to_batch) {
      const bn = encodeURIComponent(data.to_batch);

      const url =
        `/app/query-report/Batch%20Traceability` +
        `?trace_type=Manufacturing` +
        `&batch=${bn}` +
        `&view_mode=Table+%28Printable%29`;

      return `<a href="${url}" target="_blank" style="font-weight:700;">
                ${frappe.utils.escape_html(data.to_batch)}
              </a>`;
    }

    return value;
  }
};
