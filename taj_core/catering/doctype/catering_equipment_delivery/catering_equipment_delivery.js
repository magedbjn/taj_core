frappe.ui.form.on("Catering Equipment Delivery", {
    refresh(frm) {
        frm.set_query("serial_no", "items", function(doc, cdt, cdn) {
            let row = locals[cdt][cdn];

            if (!row.equipment) {
                return {
                    filters: {
                        status: "Available"
                    }
                };
            }

            return {
                filters: {
                    equipment: row.equipment,
                    status: "Available"
                }
            };
        });
    },

    validate(frm) {
        if (!frm.doc.items || frm.doc.items.length === 0) {
            frappe.throw(__("Please add at least one item"));
        }

        frm.doc.items.forEach(function(row) {
            if (!row.equipment) {
                frappe.throw(__("Equipment is required in row {0}", [row.idx]));
            }

            if (row.has_serial_no) {
                row.qty = 1;
                row.delivered_qty = 1;
                row.outstanding_qty = 1 - (row.returned_qty || 0);

                if (!row.serial_no) {
                    frappe.throw(__("Serial No is required in row {0}", [row.idx]));
                }
            } else {
                if (!row.qty || row.qty <= 0) {
                    frappe.throw(__("Qty must be greater than zero in row {0}", [row.idx]));
                }

                row.delivered_qty = row.qty;
                row.outstanding_qty = row.delivered_qty - (row.returned_qty || 0);
            }
        });
    }
});


frappe.ui.form.on("Catering Equipment Delivery Item", {
    equipment(frm, cdt, cdn) {
        let row = locals[cdt][cdn];

        if (!row.equipment) {
            return;
        }

        frappe.call({
            method: "taj_core.catering.doctype.catering_equipment_delivery.catering_equipment_delivery.get_equipment_info",
            args: {
                equipment: row.equipment
            },
            callback: function(r) {
                if (!r.message) {
                    return;
                }

                let info = r.message;

                frappe.model.set_value(cdt, cdn, "equipment_name_arabic", info.equipment_name_arabic);
                frappe.model.set_value(cdt, cdn, "has_serial_no", info.has_serial_no);

                if (info.disabled) {
                    frappe.throw(__("This equipment is disabled"));
                }

                if (info.has_serial_no) {
                    frappe.model.set_value(cdt, cdn, "qty", 1);
                    frappe.model.set_value(cdt, cdn, "delivered_qty", 1);
                    frappe.model.set_value(cdt, cdn, "returned_qty", 0);
                    frappe.model.set_value(cdt, cdn, "outstanding_qty", 1);
                } else {
                    frappe.model.set_value(cdt, cdn, "serial_no", "");
                    frappe.model.set_value(cdt, cdn, "delivered_qty", row.qty || 0);
                    frappe.model.set_value(cdt, cdn, "returned_qty", 0);
                    frappe.model.set_value(cdt, cdn, "outstanding_qty", row.qty || 0);

                    frappe.show_alert({
                        message: __("Available Qty: {0}", [info.available_qty]),
                        indicator: "blue"
                    });
                }

                frm.refresh_field("items");
            }
        });
    },

    qty(frm, cdt, cdn) {
        let row = locals[cdt][cdn];

        if (row.has_serial_no) {
            frappe.model.set_value(cdt, cdn, "qty", 1);
            frappe.model.set_value(cdt, cdn, "delivered_qty", 1);
            frappe.model.set_value(cdt, cdn, "outstanding_qty", 1 - (row.returned_qty || 0));
            return;
        }

        let qty = row.qty || 0;
        let returned_qty = row.returned_qty || 0;

        frappe.model.set_value(cdt, cdn, "delivered_qty", qty);
        frappe.model.set_value(cdt, cdn, "outstanding_qty", qty - returned_qty);
    },

    returned_qty(frm, cdt, cdn) {
        let row = locals[cdt][cdn];

        let delivered_qty = row.delivered_qty || 0;
        let returned_qty = row.returned_qty || 0;

        if (returned_qty > delivered_qty) {
            frappe.model.set_value(cdt, cdn, "returned_qty", delivered_qty);
            frappe.throw(__("Returned Qty cannot be more than Delivered Qty"));
        }

        frappe.model.set_value(cdt, cdn, "outstanding_qty", delivered_qty - returned_qty);
    },

    serial_no(frm, cdt, cdn) {
        let row = locals[cdt][cdn];

        if (row.serial_no) {
            frappe.model.set_value(cdt, cdn, "qty", 1);
            frappe.model.set_value(cdt, cdn, "delivered_qty", 1);
            frappe.model.set_value(cdt, cdn, "returned_qty", 0);
            frappe.model.set_value(cdt, cdn, "outstanding_qty", 1);
        }
    }
});