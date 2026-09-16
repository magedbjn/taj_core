frappe.query_reports["External Workforce Attendance"] = {
    filters: [
        {
            fieldname: "from_date",
            label: __("From Date"),
            fieldtype: "Date",
            default: frappe.datetime.add_days(frappe.datetime.get_today(), -30),
            reqd: 1
        },
        {
            fieldname: "to_date",
            label: __("To Date"),
            fieldtype: "Date",
            default: frappe.datetime.get_today(),
            reqd: 1
        },
        {
            fieldname: "department",
            label: __("Department"),
            fieldtype: "Link",
            options: "Department"
        },
        {
            fieldname: "supplier",
            label: __("Supplier"),
            fieldtype: "Link",
            options: "Supplier"
        },
        {
            fieldname: "company_name",
            label: __("Worker Company"),
            fieldtype: "Data"
        },
        {
            fieldname: "external_worker",
            label: __("External Worker"),
            fieldtype: "Link",
            options: "Checklist External Worker"
        },
        {
            fieldname: "presence_status",
            label: __("Presence"),
            fieldtype: "Select",
            options: "\nPresent\nAbsent"
        }
    ]
};
