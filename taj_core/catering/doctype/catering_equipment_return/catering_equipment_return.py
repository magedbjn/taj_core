import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint


class CateringEquipmentReturn(Document):
    def validate(self):
        self.validate_header()
        self.set_center_from_delivery()
        self.validate_items()

    def before_submit(self):
        self.validate_against_current_delivery()

    def on_submit(self):
        self.apply_return()
        update_delivery_status(self.delivery)

    def on_cancel(self):
        self.reverse_return()
        update_delivery_status(self.delivery)

    def validate_header(self):
        if not self.delivery:
            frappe.throw(_("Please select Delivery"))

        delivery = frappe.db.get_value(
            "Catering Equipment Delivery",
            self.delivery,
            ["docstatus", "status", "center"],
            as_dict=True
        )

        if not delivery:
            frappe.throw(_("Delivery not found"))

        if delivery.docstatus != 1:
            frappe.throw(_("Only submitted deliveries can be returned"))

        if delivery.status == "Closed":
            frappe.throw(_("This delivery is closed and cannot be returned"))

        if not self.returned_by_name:
            frappe.throw(_("Please enter Returned By Name"))

        if not self.received_by:
            frappe.throw(_("Please select Received By"))

        if not self.items:
            frappe.throw(_("Please add return items"))

    def set_center_from_delivery(self):
        if self.delivery:
            self.center = frappe.db.get_value(
                "Catering Equipment Delivery",
                self.delivery,
                "center"
            )

    def validate_items(self):
        for row in self.items:
            if not row.delivery_item:
                frappe.throw(
                    _("Delivery Item reference is missing in row {0}. Please reload items from Delivery.")
                    .format(row.idx)
                )

            if not row.equipment:
                frappe.throw(_("Equipment is required in row {0}").format(row.idx))

            if cint(row.return_qty) <= 0:
                frappe.throw(
                    _("Return Qty must be greater than zero in row {0}")
                    .format(row.idx)
                )

            if cint(row.return_qty) > cint(row.outstanding_qty):
                frappe.throw(
                    _("Return Qty cannot be greater than Outstanding Qty in row {0}")
                    .format(row.idx)
                )

            if cint(row.has_serial_no):
                if not row.serial_no:
                    frappe.throw(
                        _("Serial No is required in row {0}")
                        .format(row.idx)
                    )

                if cint(row.return_qty) != 1:
                    frappe.throw(
                        _("Return Qty must be 1 for serialized equipment in row {0}")
                        .format(row.idx)
                    )
            else:
                row.serial_no = None

    def validate_against_current_delivery(self):
        """
        Re-check directly from submitted Delivery before submit.
        This prevents returning more than the current outstanding quantity.
        """

        for row in self.items:
            delivery_item = frappe.get_doc(
                "Catering Equipment Delivery Item",
                row.delivery_item
            )

            if delivery_item.parent != self.delivery:
                frappe.throw(
                    _("Row {0} does not belong to the selected Delivery")
                    .format(row.idx)
                )

            current_outstanding_qty = cint(delivery_item.outstanding_qty)

            if cint(row.return_qty) > current_outstanding_qty:
                frappe.throw(
                    _(
                        "Cannot return {0} of {1}. Current outstanding quantity is only {2}."
                    ).format(
                        cint(row.return_qty),
                        row.equipment_name_arabic or row.equipment,
                        current_outstanding_qty
                    ),
                    title=_("Invalid Return Qty")
                )

            if delivery_item.equipment != row.equipment:
                frappe.throw(
                    _("Equipment mismatch in row {0}")
                    .format(row.idx)
                )

            if cint(row.has_serial_no):
                if delivery_item.serial_no != row.serial_no:
                    frappe.throw(
                        _("Serial No mismatch in row {0}")
                        .format(row.idx)
                    )

                unit_status = frappe.db.get_value(
                    "Catering Equipment Unit",
                    row.serial_no,
                    "status"
                )

                if unit_status != "Delivered":
                    frappe.throw(
                        _("Serial No {0} is not currently delivered. Current status is {1}")
                        .format(row.serial_no, unit_status)
                    )

    def apply_return(self):
        for row in self.items:
            delivery_item = frappe.get_doc(
                "Catering Equipment Delivery Item",
                row.delivery_item
            )

            new_returned_qty = cint(delivery_item.returned_qty) + cint(row.return_qty)
            new_outstanding_qty = cint(delivery_item.delivered_qty) - new_returned_qty

            if new_outstanding_qty < 0:
                frappe.throw(
                    _("Returned quantity cannot exceed delivered quantity for {0}")
                    .format(row.equipment_name_arabic or row.equipment)
                )

            frappe.db.set_value(
                "Catering Equipment Delivery Item",
                row.delivery_item,
                {
                    "returned_qty": new_returned_qty,
                    "outstanding_qty": new_outstanding_qty
                },
                update_modified=False
            )

            if cint(row.has_serial_no) and row.serial_no:
                frappe.db.set_value(
                    "Catering Equipment Unit",
                    row.serial_no,
                    {
                        "status": "Available",
                        "current_center": None
                    },
                    update_modified=False
                )

    def reverse_return(self):
        for row in self.items:
            delivery_item = frappe.get_doc(
                "Catering Equipment Delivery Item",
                row.delivery_item
            )

            if cint(row.has_serial_no) and row.serial_no:
                unit_status = frappe.db.get_value(
                    "Catering Equipment Unit",
                    row.serial_no,
                    "status"
                )

                if unit_status != "Available":
                    frappe.throw(
                        _("Cannot cancel return. Serial No {0} is not Available now.")
                        .format(row.serial_no)
                    )

            new_returned_qty = cint(delivery_item.returned_qty) - cint(row.return_qty)

            if new_returned_qty < 0:
                new_returned_qty = 0

            new_outstanding_qty = cint(delivery_item.delivered_qty) - new_returned_qty

            frappe.db.set_value(
                "Catering Equipment Delivery Item",
                row.delivery_item,
                {
                    "returned_qty": new_returned_qty,
                    "outstanding_qty": new_outstanding_qty
                },
                update_modified=False
            )

            if cint(row.has_serial_no) and row.serial_no:
                frappe.db.set_value(
                    "Catering Equipment Unit",
                    row.serial_no,
                    {
                        "status": "Delivered",
                        "current_center": self.center
                    },
                    update_modified=False
                )


@frappe.whitelist()
def get_delivery_items(delivery):
    if not delivery:
        return {
            "center": None,
            "items": []
        }

    delivery_doc = frappe.get_doc("Catering Equipment Delivery", delivery)

    if delivery_doc.docstatus != 1:
        frappe.throw(_("Please select a submitted Delivery"))

    if delivery_doc.status == "Closed":
        frappe.throw(_("This Delivery is closed"))

    items = []

    for row in delivery_doc.items:
        outstanding_qty = cint(row.outstanding_qty)

        if outstanding_qty <= 0:
            continue

        items.append({
            "delivery_item": row.name,
            "equipment": row.equipment,
            "equipment_name_arabic": row.equipment_name_arabic,
            "has_serial_no": cint(row.has_serial_no),
            "serial_no": row.serial_no,
            "delivered_qty": cint(row.delivered_qty),
            "already_returned_qty": cint(row.returned_qty),
            "outstanding_qty": outstanding_qty,
            "return_qty": outstanding_qty
        })

    return {
        "center": delivery_doc.center,
        "items": items
    }


def update_delivery_status(delivery):
    if not delivery:
        return

    totals = frappe.db.sql(
        """
        select
            coalesce(sum(delivered_qty), 0) as total_delivered,
            coalesce(sum(returned_qty), 0) as total_returned,
            coalesce(sum(outstanding_qty), 0) as total_outstanding
        from
            `tabCatering Equipment Delivery Item`
        where
            parent = %s
        """,
        delivery,
        as_dict=True
    )[0]

    total_delivered = cint(totals.total_delivered)
    total_returned = cint(totals.total_returned)
    total_outstanding = cint(totals.total_outstanding)

    if total_delivered <= 0:
        status = "Delivered"
    elif total_outstanding <= 0:
        status = "Returned"
    elif total_returned > 0:
        status = "Partially Returned"
    else:
        status = "Delivered"

    frappe.db.set_value(
        "Catering Equipment Delivery",
        delivery,
        "status",
        status,
        update_modified=False
    )