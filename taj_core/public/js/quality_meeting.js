// Quality Meeting only. Loaded by taj_core doctype_js, not a Client Script record.
// Employee IDs remain stored in the child table; names are only for display.
frappe.ui.form.on("Quality Meeting Attendee", {
    async employee(frm, cdt, cdn) {
        const row = frappe.get_doc(cdt, cdn);
        const employee = row?.employee;

        // The name must never remain from a previously selected employee.
        await frappe.model.set_value(cdt, cdn, "employee_name", "");
        if (!employee) return;

        const existing = (frm.doc.taj_attendees || []).find(
            (other) => other.name !== cdn && other.employee === employee
        );
        if (existing) {
            await frappe.model.set_value(cdt, cdn, "employee", "");
            frappe.msgprint({
                title: __("Duplicate Attendee"),
                message: __("Employee {0} is already in Attendees (rows {1} and {2}).", [
                    employee, existing.idx, row.idx
                ]),
                indicator: "orange",
            });
            return;
        }

        try {
            const result = await frappe.call({
                method: "taj_core.qc.quality_meeting.get_attendee_name",
                args: {
                    employee,
                    meeting: frm.is_new() ? "" : frm.doc.name,
                },
            });
            const current = frappe.get_doc(cdt, cdn);
            if (!current || current.employee !== employee) return;
            if (!result?.message) {
                await frappe.model.set_value(cdt, cdn, "employee", "");
                return;
            }
            await frappe.model.set_value(cdt, cdn, "employee_name", result.message);
            frm.refresh_field("taj_attendees");
        } catch (error) {
            // Permission/invalid employee errors are reported by frappe.call.
            const current = frappe.get_doc(cdt, cdn);
            if (current && current.employee === employee) {
                await frappe.model.set_value(cdt, cdn, "employee", "");
            }
        }
    },
});
