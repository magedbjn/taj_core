function get_current_year() {
  return String(new Date().getFullYear());
}

function get_current_month_name() {
  const months = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"
  ];
  return months[new Date().getMonth()];
}

function toggle_month_visibility() {
  const year = frappe.query_report.get_filter_value("year");
  const month_filter = frappe.query_report.get_filter("month");

  if (year === "All") {
    // hide month and force month=All
    month_filter.df.hidden = 1;
    frappe.query_report.set_filter_value("month", "All");
  } else {
    // show month; if it is All, set it to current month by default for better UX
    month_filter.df.hidden = 0;
    const current = frappe.query_report.get_filter_value("month");
    if (!current || current === "All") {
      frappe.query_report.set_filter_value("month", get_current_month_name());
    }
  }

  month_filter.refresh();
}

frappe.query_reports["Scheduled Payments"] = {
  filters: [
    { fieldname: "company", label: "Company", fieldtype: "Link", options: "Company", hidden: 1 },
    {
      fieldname: "transaction_type",
      label: "Type",
      fieldtype: "Select",
      options: ["Purchases", "Sales"].join("\n"),
      default: "Purchases",
      reqd: 1,
      on_change: () => {
        const t = frappe.query_report.get_filter_value("transaction_type");
        const supplier = frappe.query_report.get_filter("supplier");
        const customer = frappe.query_report.get_filter("customer");

        if (t === "Purchases") {
          supplier.df.hidden = 0;
          customer.df.hidden = 1;
          frappe.query_report.set_filter_value("customer", null);
        } else {
          supplier.df.hidden = 1;
          customer.df.hidden = 0;
          frappe.query_report.set_filter_value("supplier", null);
        }

        supplier.refresh();
        customer.refresh();
        frappe.query_report.refresh();
      }
    },

    { fieldname: "supplier", label: "Supplier", fieldtype: "Link", options: "Supplier" },
    { fieldname: "customer", label: "Customer", fieldtype: "Link", options: "Customer", hidden: 1 },

    {
      fieldname: "year",
      label: "Year",
      fieldtype: "Select",
      options: (() => {
        const y = new Date().getFullYear();
        return ["All", String(y), String(y + 1)].join("\n");
      })(),
      default: get_current_year(),   // ✅ السنة الحالية افتراضيًا
      reqd: 0,
      on_change: () => {
        toggle_month_visibility();
        frappe.query_report.refresh();
      }
    },

    {
      fieldname: "month",
      label: "Month",
      fieldtype: "Select",
      options: [
        "All",
        "Jan", "Feb", "Mar", "Apr", "May", "Jun",
        "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"
      ].join("\n"),
      default: get_current_month_name(),  // ✅ الشهر الحالي افتراضيًا
      on_change: () => frappe.query_report.refresh()
    }
  ],

  onload: function(report) {
    // ensure correct supplier/customer visibility
    const t = report.get_filter_value("transaction_type");
    if (t === "Sales") {
      report.set_filter_value("transaction_type", "Purchases");
      report.set_filter_value("transaction_type", "Sales");
    }

    // apply initial month hide/show based on year default
    toggle_month_visibility();
  }
};
