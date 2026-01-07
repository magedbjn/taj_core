frappe.query_reports["Batch Traceability"] = {
  filters: [
    {
      fieldname: "trace_type",
      label: __("Trace Type"),
      fieldtype: "Select",
      options: ["Manufacturing", "Sold"],
      default: "Manufacturing",
      reqd: 1,
      on_change: function () {
        const trace_type = frappe.query_report.get_filter_value("trace_type") || "Manufacturing";

        if (trace_type === "Manufacturing") {
          frappe.query_report.set_filter_value("view_mode", "Table (Printable)");
          frappe.query_report.toggle_filter_display("view_mode", false);
          frappe.query_report.toggle_filter_display("include_bundle", false);
        } else {
          frappe.query_report.toggle_filter_display("view_mode", true);
          frappe.query_report.toggle_filter_display("include_bundle", true);
        }

        frappe.query_report.refresh();
      }
    },
    {
      fieldname: "batch",
      label: __("BATCH"),
      fieldtype: "Link",
      options: "Batch",
      reqd: 1
    },
    {
      fieldname: "view_mode",
      label: __("View Mode"),
      fieldtype: "Select",
      options: ["Table (Printable)", "Tree (Expandable)"],
      default: "Table (Printable)",
      depends_on: "eval:doc.trace_type === 'Manufacturing'"
    },
    {
      fieldname: "include_bundle",
      label: __("Include Bundle Batches"),
      fieldtype: "Check",
      default: 0,
      depends_on: "eval:doc.trace_type === 'Manufacturing'",
      on_change: function () {
        frappe.query_report.refresh();
      }
    }
  ],

  onload: function () {
    const trace_type = frappe.query_report.get_filter_value("trace_type") || "Manufacturing";
    if (trace_type === "Sold") {
      frappe.query_report.toggle_filter_display("view_mode", false);
      frappe.query_report.toggle_filter_display("include_bundle", false);
    }
  },

  formatter: function (value, row, column, data, default_formatter) {
    value = default_formatter(value, row, column, data);
    if (!data) return value;

    // ✅ open Sales DocNo in new tab
    if (column.fieldname === "sales_docname" && data.sales_doctype && data.sales_docname) {
      const doctype = data.sales_doctype;
      const docname = data.sales_docname;
      const url = `/app/${frappe.router.slug(doctype)}/${docname}`;
      return `<a href="${url}" target="_blank" style="font-weight:700;">
                ${frappe.utils.escape_html(docname)}
              </a>`;
    }

    // ✅ Yellow sibling rows: show QTY + UOM + Batch
    if (data.is_bundle_sibling === 1) {
      const bg = "background:#fff59d !important;";
      const pad = "padding:6px 10px;";
      const noBorder = "border-color:#fff59d !important;";
      const keep = ["qty", "uom", "batch_no"];

      if (keep.includes(column.fieldname)) {
        return `<div style="${bg}${pad}${noBorder} font-weight:800;">${value}</div>`;
      }
      return `<div style="${bg}${pad}${noBorder}">&nbsp;</div>`;
    }

    const trace_type = frappe.query_report.get_filter_value("trace_type") || "Manufacturing";
    const view_mode = frappe.query_report.get_filter_value("view_mode") || "Table (Printable)";

    // Sold: keep default formatting
    if (trace_type === "Sold") return value;

    // Tree: keep default formatting (bundle siblings already handled)
    if (view_mode === "Tree (Expandable)") return value;

    // Color by Item Type (Table only)
    if (data.item_type && data.item_code) {
      let bg = "";
      if (data.item_type === "Finished") bg = "#e8f5e9";
      else if (data.item_type === "Sub BOM") bg = "#e3f2fd";
      else if (data.item_type === "Raw Material") bg = "#fff3e0";
      else if (data.item_type === "Packaging") bg = "#f5f5f5";

      if (bg) {
        return `<div style="background:${bg}; padding:6px 10px;">${value}</div>`;
      }
    }

    // extra batch lines
    if (data.is_batch_line === 1) {
      return `<div style="background:#fafafa; padding:6px 10px; font-weight:600;">${value}</div>`;
    }

    return value;
  }
};
