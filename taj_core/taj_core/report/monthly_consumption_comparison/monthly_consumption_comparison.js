frappe.query_reports["Monthly Consumption Comparison"] = {
    "filters": [
        {
            "fieldname": "supplier",
            "label": __("Supplier"),
            "fieldtype": "Select",
            "options": [
                "",
                "Water Distribution - Aquaphor",
                "Saudi Electricity Company"
            ],
            "reqd": 1
        },
        {
            "fieldname": "period",
            "label": __("Period"),
            "fieldtype": "Select",
            "options": [
                "3 Months",
                "6 Months",
                "9 Months",
                "12 Months"
            ],
            "default": "12 Months"
        }
    ],

    formatter: function (value, row, column, data, default_formatter) {
        value = default_formatter(value, row, column, data);
        // السماح بالتفاف النص وتوسيع الخلية
        return `<div style="white-space: normal; word-wrap: break-word;">${value}</div>`;
    }
};
