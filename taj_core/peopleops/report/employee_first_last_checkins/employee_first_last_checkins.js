/* eslint-disable */
frappe.query_reports["Employee First Last Checkins"] = {
  filters: [
    {
      fieldname: "month",
      label: __("Month"),
      fieldtype: "Select",
      reqd: 1,
      options: [
        { value: 1, label: __("Jan") }, { value: 2, label: __("Feb") },
        { value: 3, label: __("Mar") }, { value: 4, label: __("Apr") },
        { value: 5, label: __("May") }, { value: 6, label: __("Jun") },
        { value: 7, label: __("Jul") }, { value: 8, label: __("Aug") },
        { value: 9, label: __("Sep") }, { value: 10, label: __("Oct") },
        { value: 11, label: __("Nov") }, { value: 12, label: __("Dec") },
      ],
      default: new Date().getMonth() + 1,
    },
    { fieldname: "year", label: __("Year"), fieldtype: "Select", reqd: 1 },
    { fieldname: "employee", label: __("Employee"), fieldtype: "Link", options: "Employee" },
    { fieldname: "group_by", label: __("Group By"), fieldtype: "Select", options: ["", "Branch", "Grade", "Department", "Designation"], default: "" },
    {
      fieldname: "show_horizontal",
      label: __("Show Horizontal View"),
      fieldtype: "Check",
      default: 0
    }
  ],

  onload: function () {
    // Use HRMS helper to populate years
    frappe.call({
      method: "hrms.hr.report.monthly_attendance_sheet.monthly_attendance_sheet.get_attendance_years",
      callback: function (r) {
        const year_filter = frappe.query_report.get_filter("year");
        const years = (r.message || "").toString();
        if (years) {
          year_filter.df.options = years;
          year_filter.df.default = years.split("\n")[0];
          year_filter.refresh();
          year_filter.set_input(year_filter.df.default);
        } else {
          const y = new Date().getFullYear();
          year_filter.df.options = String(y);
          year_filter.df.default = String(y);
          year_filter.refresh();
          year_filter.set_input(String(y));
        }
      },
    });
  },

  formatter: function (value, row, column, data, default_formatter) {
    value = default_formatter(value, row, column, data);

    const group_by = frappe.query_report.get_filter_value("group_by");
    const show_horizontal = frappe.query_report.get_filter_value("show_horizontal");
    
    // Bold group header rows (first data column)
    if (group_by && data && data[frappe.scrub(group_by)] && !data.employee && column.colIndex === 1) {
      return "<strong>" + value + "</strong>";
    }

    if (show_horizontal) {
      // تنسيق خلايا الأيام في العرض الأفقي
      if (column.fieldname && column.fieldname.startsWith('day_') && data) {
        const v = data[column.fieldname];
        if (v === "P" || v === "WFH") value = `<span style="color:green">${v}</span>`;
        else if (v === "A") value = `<span style="color:red">${v}</span>`;
        else if (v === "HD/A") value = `<span style="color:orange">${v}</span>`;
        else if (v === "HD/P") value = `<span style="color:#914EE3">${v}</span>`;
        else if (v === "L") value = `<span style="color:#3187D8">${v}</span>`;
        else if (v === "H" || v === "WO") value = `<span style="color:#878787">${v}</span>`;
        else if (v === "NP") value = `<span style="color:#f59e0b">${v}</span>`;
        else if (v && v !== "0.00") value = `<span style="color:green">${v}</span>`; // ساعات العمل
      }
    } else {
      // تنسيق الوضع العمودي
      if (column.fieldname === "span_hours" && data) {
        const v = data.span_hours;
        if (v === "P" || v === "WFH") value = `<span style="color:green">${v}</span>`;
        else if (v === "A") value = `<span style="color:red">${v}</span>`;
        else if (v === "HD/A") value = `<span style="color:orange">${v}</span>`;
        else if (v === "HD/P") value = `<span style="color:#914EE3">${v}</span>`;
        else if (v === "L") value = `<span style="color:#3187D8">${v}</span>`;
        else if (v === "H" || v === "WO") value = `<span style="color:#878787">${v}</span>`;
        else if (v === "NP") value = `<span style="color:#f59e0b">${v}</span>`;
      }

      // Highlight single checkin cases
      if ((column.fieldname === "check_in" || column.fieldname === "check_out") && data) {
        if ((data.check_in && !data.check_out) || (!data.check_in && data.check_out)) {
          value = `<span style="color:#f59e0b">${value}</span>`;
        }
      }
    }

    return value;
  },
};