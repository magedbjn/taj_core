frappe.query_reports["Production Manager Smart"] = {
  filters: [
    {
      fieldname: "production_plan",
      label: __("Production Plan"),
      fieldtype: "Link",
      options: "Production Plan",
      reqd: 1
    },
    {
      fieldname: "product_type",
      label: __("Product Type"),
      fieldtype: "Select",
      options: "Final Product\nPreparation\nAll",
      default: "Final Product"
    }
  ],

  formatter: function (value, row, column, data, default_formatter) {
    value = default_formatter(value, row, column, data);

    if (!data) return value;

    if (["required_qty", "produced_qty", "loss_qty", "variance_qty"].includes(column.fieldname)) {
      let num = flt(data[column.fieldname]);

      let formatted = (Math.floor(num) === num)
        ? num.toLocaleString(undefined, { maximumFractionDigits: 0 })
        : num.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });

      if (column.fieldname === "variance_qty") {
        let color = "#6b7280";
        if (num > 0) color = "green";
        else if (num < 0) color = "red";

        return `<span style="font-weight:700;color:${color};">${formatted}</span>`;
      }

      return `<span style="font-weight:600;">${formatted}</span>`;
    }

    if (column.fieldname === "status") {
      const color_map = {
        "Completed": "green",
        "In Process": "orange",
        "Not Started": "gray",
        "Draft": "#6b7280",
        "Stopped": "#b45309",
        "Closed": "#7c3aed"
      };

      const color = color_map[data.status] || "gray";
      value = `<span style="font-weight:600;color:${color};">${value}</span>`;
    }

    return value;
  }
};