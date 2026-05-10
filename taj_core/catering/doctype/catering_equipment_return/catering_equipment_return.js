frappe.ui.form.on("Catering Equipment Return", {
    refresh(frm) {
        frm.set_query("delivery", function() {
            return {
                filters: {
                    docstatus: 1
                }
            };
        });

        frm.set_query("serial_no", "items", function(doc, cdt, cdn) {
            let row = locals[cdt][cdn];

            return {
                filters: {
                    equipment: row.equipment
                }
            };
        });
    },

    delivery(frm) {
        if (!frm.doc.delivery) {
            frm.clear_table("items");
            frm.set_value("center", "");
            frm.refresh_field("items");
            return;
        }

        frappe.call({
            method: "your_app.your_app.catering.doctype.catering_equipment_return.catering_equipment_return.get_delivery_items",
            args: {
                delivery: frm.doc.delivery
            },
            callback: function(r) {
                if (!r.message) {
                    return;
                }

                frm.clear_table("items");

                frm.set_value("center", r.message.center);

                (r.message.items || []).forEach(function(item) {
                    let row = frm.add_child("items");

                    row.delivery_item = item.delivery_item;
                    row.equipment = item.equipment;
                    row.equipment_name_arabic = item.equipment_name_arabic;
                    row.has_serial_no = item.has_serial_no;
                    row.serial_no = item.serial_no;
                    row.delivered_qty = item.delivered_qty;
                    row.already_returned_qty = item.already_returned_qty;
                    row.outstanding_qty = item.outstanding_qty;
                    row.return_qty = item.return_qty;
                });

                frm.refresh_field("items");

                if (!r.message.items || r.message.items.length === 0) {
                    frappe.msgprint(__("There are no outstanding items to return for this Delivery."));
                }
            }
        });
    },

    validate(frm) {
        if (!frm.doc.delivery) {
            frappe.throw(__("Please select Delivery"));
        }

        if (!frm.doc.items || frm.doc.items.length === 0) {
            frappe.throw(__("Please add return items"));
        }

        frm.doc.items.forEach(function(row) {
            if (!row.delivery_item) {
                frappe.throw(__("Delivery Item reference is missing in row {0}. Please reload items from Delivery.", [row.idx]));
            }

            if (!row.equipment) {
                frappe.throw(__("Equipment is required in row {0}", [row.idx]));
            }

            if (!row.return_qty || row.return_qty <= 0) {
                frappe.throw(__("Return Qty must be greater than zero in row {0}", [row.idx]));
            }

            if (row.return_qty > row.outstanding_qty) {
                frappe.throw(__("Return Qty cannot be greater than Outstanding Qty in row {0}", [row.idx]));
            }

            if (row.has_serial_no && row.return_qty !== 1) {
                frappe.throw(__("Return Qty must be 1 for serialized equipment in row {0}", [row.idx]));
            }
        });
    }
});


frappe.ui.form.on("Catering Equipment Return Item", {
    return_qty(frm, cdt, cdn) {
        let row = locals[cdt][cdn];

        if (!row.return_qty) {
            return;
        }

        if (row.return_qty <= 0) {
            frappe.model.set_value(cdt, cdn, "return_qty", 1);
            frappe.throw(__("Return Qty must be greater than zero"));
        }

        if (row.return_qty > row.outstanding_qty) {
            frappe.model.set_value(cdt, cdn, "return_qty", row.outstanding_qty);
            frappe.throw(__("Return Qty cannot be greater than Outstanding Qty"));
        }

        if (row.has_serial_no && row.return_qty !== 1) {
            frappe.model.set_value(cdt, cdn, "return_qty", 1);
            frappe.throw(__("Return Qty must be 1 for serialized equipment"));
        }
    }
});