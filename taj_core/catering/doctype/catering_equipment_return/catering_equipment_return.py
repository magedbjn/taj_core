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
        self.lock_return_resources(
            validate_delivery=True
        )
        self.validate_against_current_delivery()

    def on_submit(self):
        self.apply_return()
        update_delivery_status(self.delivery)

    def before_cancel(self):
        self.validate_bulk_cancel_capacity()
        self.lock_return_resources()

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

    def lock_return_resources(
        self,
        validate_delivery=False,
    ):
        delivery_rows = frappe.db.sql(
            """
            select
                name,
                docstatus,
                status
            from
                `tabCatering Equipment Delivery`
            where
                name = %s
            for update
            """,
            (self.delivery,),
            as_dict=True,
        )

        if not delivery_rows:
            frappe.throw(_("Delivery not found"))

        delivery = delivery_rows[0]

        if validate_delivery:
            if delivery.docstatus != 1:
                frappe.throw(
                    _(
                        "Only submitted deliveries "
                        "can be returned"
                    )
                )

            if delivery.status == "Closed":
                frappe.throw(
                    _(
                        "This delivery is closed "
                        "and cannot be returned"
                    )
                )

        delivery_item_names = sorted({
            row.delivery_item
            for row in self.items
            if row.delivery_item
        })

        locked_delivery_items = {}

        if delivery_item_names:
            placeholders = ", ".join(
                ["%s"] * len(delivery_item_names)
            )

            rows = frappe.db.sql(
                f"""
                select
                    name,
                    parent,
                    equipment,
                    serial_no,
                    delivered_qty,
                    returned_qty,
                    outstanding_qty
                from
                    `tabCatering Equipment Delivery Item`
                where
                    parent = %s
                    and name in ({placeholders})
                order by
                    name
                for update
                """,
                tuple(
                    [self.delivery]
                    + delivery_item_names
                ),
                as_dict=True,
            )

            locked_delivery_items = {
                row.name: row
                for row in rows
            }

        serials = sorted({
            row.serial_no
            for row in self.items
            if cint(row.has_serial_no)
            and row.serial_no
        })

        locked_units = {}

        if serials:
            placeholders = ", ".join(
                ["%s"] * len(serials)
            )

            rows = frappe.db.sql(
                f"""
                select
                    name,
                    equipment,
                    status
                from
                    `tabCatering Equipment Unit`
                where
                    name in ({placeholders})
                order by
                    name
                for update
                """,
                tuple(serials),
                as_dict=True,
            )

            locked_units = {
                row.name: row
                for row in rows
            }

        self.flags.locked_delivery_items = (
            locked_delivery_items
        )
        self.flags.locked_equipment_units = (
            locked_units
        )

    def validate_against_current_delivery(self):
        """
        Re-check locked Delivery rows before submit.
        """
        locked_delivery_items = (
            self.flags.get("locked_delivery_items")
            or {}
        )
        locked_units = (
            self.flags.get("locked_equipment_units")
            or {}
        )

        for row in self.items:
            delivery_item = locked_delivery_items.get(
                row.delivery_item
            )

            if not delivery_item:
                frappe.throw(
                    _(
                        "Delivery Item {0} could not be locked"
                    ).format(row.delivery_item)
                )

            if delivery_item.parent != self.delivery:
                frappe.throw(
                    _(
                        "Row {0} does not belong to "
                        "the selected Delivery"
                    ).format(row.idx)
                )

            current_outstanding_qty = cint(
                delivery_item.outstanding_qty
            )

            if cint(row.return_qty) > current_outstanding_qty:
                frappe.throw(
                    _(
                        "Cannot return {0} of {1}. "
                        "Current outstanding quantity "
                        "is only {2}."
                    ).format(
                        cint(row.return_qty),
                        row.equipment_name_arabic
                        or row.equipment,
                        current_outstanding_qty,
                    ),
                    title=_("Invalid Return Qty"),
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

                unit = locked_units.get(
                    row.serial_no
                )

                unit_status = (
                    unit.status
                    if unit
                    else None
                )

                if unit_status != "Delivered":
                    frappe.throw(
                        _(
                            "Serial No {0} is not "
                            "currently delivered. "
                            "Current status is {1}"
                        ).format(
                            row.serial_no,
                            unit_status,
                        )
                    )

    def apply_return(self):
        locked_delivery_items = (
            self.flags.get("locked_delivery_items")
            or {}
        )

        for row in self.items:
            delivery_item = locked_delivery_items.get(
                row.delivery_item
            )

            if not delivery_item:
                frappe.throw(
                    _(
                        "Delivery Item {0} could not be locked"
                    ).format(row.delivery_item)
                )

            new_returned_qty = (
                cint(delivery_item.returned_qty)
                + cint(row.return_qty)
            )

            new_outstanding_qty = (
                cint(delivery_item.delivered_qty)
                - new_returned_qty
            )

            if new_outstanding_qty < 0:
                frappe.throw(
                    _(
                        "Returned quantity cannot exceed "
                        "delivered quantity for {0}"
                    ).format(
                        row.equipment_name_arabic
                        or row.equipment
                    )
                )

            frappe.db.set_value(
                "Catering Equipment Delivery Item",
                row.delivery_item,
                {
                    "returned_qty": new_returned_qty,
                    "outstanding_qty": new_outstanding_qty,
                },
                update_modified=False,
            )

            delivery_item.returned_qty = (
                new_returned_qty
            )
            delivery_item.outstanding_qty = (
                new_outstanding_qty
            )

            if cint(row.has_serial_no) and row.serial_no:
                frappe.db.set_value(
                    "Catering Equipment Unit",
                    row.serial_no,
                    {
                        "status": "Available",
                        "current_center": None,
                    },
                    update_modified=False,
                )

    def validate_bulk_cancel_capacity(self):
        required_by_equipment = {}

        for row in self.items:
            if cint(row.has_serial_no):
                continue
            if not row.equipment:
                continue

            required_by_equipment[row.equipment] = (
                cint(required_by_equipment.get(row.equipment, 0))
                + cint(row.return_qty)
            )

        if not required_by_equipment:
            return

        from taj_core.catering.doctype.catering_equipment_delivery.catering_equipment_delivery import (
            _get_available_qty_current,
            _lock_equipment_for_update,
        )

        for equipment in sorted(required_by_equipment):
            total_qty = _lock_equipment_for_update(equipment)
            available_qty = _get_available_qty_current(
                equipment=equipment,
                total_qty=total_qty,
            )
            required_qty = cint(required_by_equipment[equipment])

            if required_qty > available_qty:
                frappe.throw(
                    _(
                        "Cannot cancel this return for {0}. "
                        "Reopening {1} unit(s) requires free capacity, "
                        "but only {2} unit(s) are currently available."
                    ).format(
                        equipment,
                        required_qty,
                        available_qty,
                    )
                )

    def reverse_return(self):
        locked_delivery_items = (
            self.flags.get("locked_delivery_items")
            or {}
        )
        locked_units = (
            self.flags.get("locked_equipment_units")
            or {}
        )

        for row in self.items:
            delivery_item = locked_delivery_items.get(
                row.delivery_item
            )

            if not delivery_item:
                frappe.throw(
                    _(
                        "Delivery Item {0} could not be locked"
                    ).format(row.delivery_item)
                )

            if cint(row.has_serial_no) and row.serial_no:
                unit = locked_units.get(
                    row.serial_no
                )

                unit_status = (
                    unit.status
                    if unit
                    else None
                )

                if unit_status != "Available":
                    frappe.throw(
                        _(
                            "Cannot cancel return. "
                            "Serial No {0} is not Available now."
                        ).format(row.serial_no)
                    )

            new_returned_qty = (
                cint(delivery_item.returned_qty)
                - cint(row.return_qty)
            )

            if new_returned_qty < 0:
                new_returned_qty = 0

            new_outstanding_qty = (
                cint(delivery_item.delivered_qty)
                - new_returned_qty
            )

            frappe.db.set_value(
                "Catering Equipment Delivery Item",
                row.delivery_item,
                {
                    "returned_qty": new_returned_qty,
                    "outstanding_qty": new_outstanding_qty,
                },
                update_modified=False,
            )

            delivery_item.returned_qty = (
                new_returned_qty
            )
            delivery_item.outstanding_qty = (
                new_outstanding_qty
            )

            if cint(row.has_serial_no) and row.serial_no:
                frappe.db.set_value(
                    "Catering Equipment Unit",
                    row.serial_no,
                    {
                        "status": "Delivered",
                        "current_center": self.center,
                    },
                    update_modified=False,
                )


@frappe.whitelist()
def get_delivery_items(delivery):
    if not delivery:
        return {
            "center": None,
            "items": []
        }

    delivery_doc = frappe.get_doc(
        "Catering Equipment Delivery",
        delivery,
    )
    delivery_doc.check_permission("read")

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

    rows = frappe.db.sql(
        """
        select
            delivered_qty,
            returned_qty,
            outstanding_qty
        from
            `tabCatering Equipment Delivery Item`
        where
            parent = %s
        order by
            name
        for update
        """,
        (delivery,),
        as_dict=True,
    )

    total_delivered = sum(
        cint(row.delivered_qty)
        for row in rows
    )
    total_returned = sum(
        cint(row.returned_qty)
        for row in rows
    )
    total_outstanding = sum(
        cint(row.outstanding_qty)
        for row in rows
    )

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
        update_modified=False,
    )
