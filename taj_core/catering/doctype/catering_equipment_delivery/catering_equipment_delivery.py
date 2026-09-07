import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint


class CateringEquipmentDelivery(Document):
    def validate(self):
        self.validate_header()
        self.prepare_items()
        self.validate_available_qty()
        self.validate_serial_items()

    def before_submit(self):
        self.validate_available_qty(lock=True)
        self.validate_serial_items(lock=True)

    def on_submit(self):
        self.prepare_items()

        for row in self.items:
            if cint(row.has_serial_no):
                update_equipment_unit_as_delivered(
                    unit=row.serial_no,
                    center=self.center
                )

        self.status = "Delivered"

    def on_cancel(self):
        serials = sorted({
            row.serial_no
            for row in self.items
            if cint(row.has_serial_no) and row.serial_no
        })

        _get_equipment_units_for_update(serials)

        for row in self.items:
            if cint(row.has_serial_no) and row.serial_no:
                update_equipment_unit_as_available(row.serial_no)

    def validate_header(self):
        if not self.center:
            frappe.throw(_("Please select Center"))

        if not self.delivered_by:
            frappe.throw(_("Please select Delivered By"))

        if not self.receiver_name:
            frappe.throw(_("Please enter Receiver Name"))

        if not self.items:
            frappe.throw(_("Please add at least one item"))

    def prepare_items(self):
        for row in self.items:
            if not row.equipment:
                frappe.throw(_("Equipment is required in row {0}").format(row.idx))

            equipment = frappe.get_doc("Catering Equipment", row.equipment)

            if cint(equipment.disabled):
                frappe.throw(
                    _("Equipment {0} is disabled").format(row.equipment)
                )

            row.has_serial_no = cint(equipment.has_serial_no)

            if cint(equipment.has_serial_no):
                if not row.serial_no:
                    frappe.throw(
                        _("Serial No is required for equipment {0} in row {1}")
                        .format(row.equipment, row.idx)
                    )

                row.qty = 1
                row.delivered_qty = 1
                row.returned_qty = cint(row.returned_qty or 0)
                row.outstanding_qty = 1 - row.returned_qty

                if row.outstanding_qty < 0:
                    frappe.throw(
                        _("Returned Qty cannot be more than Delivered Qty in row {0}")
                        .format(row.idx)
                    )

            else:
                if row.serial_no:
                    row.serial_no = None

                if cint(row.qty) <= 0:
                    frappe.throw(
                        _("Qty must be greater than zero in row {0}")
                        .format(row.idx)
                    )

                row.delivered_qty = cint(row.qty)
                row.returned_qty = cint(row.returned_qty or 0)
                row.outstanding_qty = cint(row.delivered_qty) - cint(row.returned_qty)

                if row.outstanding_qty < 0:
                    frappe.throw(
                        _("Returned Qty cannot be more than Delivered Qty in row {0}")
                        .format(row.idx)
                    )

    def validate_available_qty(self, lock=False):
        """
        Validate non-serialized equipment quantity.
        Available Qty = Catering Equipment.total_qty - submitted outstanding qty.
        """

        required_qty_by_equipment = {}

        for row in self.items:
            if not row.equipment:
                continue

            equipment = frappe.get_doc("Catering Equipment", row.equipment)

            if cint(equipment.has_serial_no):
                continue

            required_qty_by_equipment.setdefault(row.equipment, 0)
            required_qty_by_equipment[row.equipment] += cint(row.qty)

        for equipment in sorted(required_qty_by_equipment):
            required_qty = required_qty_by_equipment[equipment]

            if lock:
                total_qty = _lock_equipment_for_update(
                    equipment
                )

                available_qty = _get_available_qty_current(
                    equipment=equipment,
                    total_qty=total_qty,
                    exclude_delivery=self.name,
                )
            else:
                available_qty = get_available_qty(
                    equipment=equipment,
                    exclude_delivery=self.name
                )

            if required_qty > available_qty:
                equipment_name = frappe.db.get_value(
                    "Catering Equipment",
                    equipment,
                    "equipment_name_arabic"
                ) or equipment

                frappe.throw(
                    _(
                        "Cannot deliver {0} of {1}. Available quantity is only {2}."
                    ).format(required_qty, equipment_name, available_qty),
                    title=_("Insufficient Quantity")
                )

    def validate_serial_items(self, lock=False):
        """
        Validate serialized equipment.
        Each serial/unit can only be delivered if status is Available.
        """

        used_serials = set()
        locked_units = {}

        if lock:
            serials = sorted({
                row.serial_no
                for row in self.items
                if cint(row.has_serial_no) and row.serial_no
            })

            locked_units = _get_equipment_units_for_update(
                serials
            )

        for row in self.items:
            if not cint(row.has_serial_no):
                continue

            if not row.serial_no:
                frappe.throw(
                    _("Serial No is required in row {0}").format(row.idx)
                )

            if row.serial_no in used_serials:
                frappe.throw(
                    _("Serial No {0} is repeated in the same delivery")
                    .format(row.serial_no)
                )

            used_serials.add(row.serial_no)

            if lock:
                unit = locked_units.get(
                    row.serial_no
                )

                if not unit:
                    frappe.throw(
                        _(
                            "Serial No {0} does not exist"
                        ).format(row.serial_no)
                    )
            else:
                unit = frappe.get_doc(
                    "Catering Equipment Unit",
                    row.serial_no
                )

            if unit.equipment != row.equipment:
                frappe.throw(
                    _("Serial No {0} does not belong to equipment {1}")
                    .format(row.serial_no, row.equipment)
                )

            if unit.status != "Available":
                frappe.throw(
                    _("Serial No {0} is not available. Current status is {1}")
                    .format(row.serial_no, unit.status)
                )


def _lock_equipment_for_update(equipment):
    rows = frappe.db.sql(
        """
        select
            name,
            total_qty
        from
            `tabCatering Equipment`
        where
            name = %s
        for update
        """,
        (equipment,),
        as_dict=True,
    )

    if not rows:
        frappe.throw(
            _(
                "Equipment {0} does not exist"
            ).format(equipment)
        )

    return cint(rows[0].total_qty)


def _get_equipment_units_for_update(serials):
    serials = sorted(
        set(serials or [])
    )

    if not serials:
        return {}

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

    return {
        row.name: row
        for row in rows
    }


def _get_available_qty_current(
    equipment,
    total_qty,
    exclude_delivery=None,
):
    exclude_condition = ""
    values = {
        "equipment": equipment,
    }

    if exclude_delivery:
        exclude_condition = (
            "and parent_doc.name "
            "!= %(exclude_delivery)s"
        )
        values["exclude_delivery"] = (
            exclude_delivery
        )

    rows = frappe.db.sql(
        f"""
        select
            item.outstanding_qty
        from
            `tabCatering Equipment Delivery Item` item
        inner join
            `tabCatering Equipment Delivery` parent_doc
        on
            parent_doc.name = item.parent
        where
            parent_doc.docstatus = 1
            and parent_doc.status not in (
                'Returned',
                'Closed'
            )
            and item.equipment = %(equipment)s
            and coalesce(
                item.has_serial_no,
                0
            ) = 0
            {exclude_condition}
        order by
            item.name
        for update
        """,
        values,
    )

    delivered_qty = sum(
        cint(row[0])
        for row in rows
    )

    return max(
        cint(total_qty) - delivered_qty,
        0,
    )


@frappe.whitelist()
def get_available_qty(equipment, exclude_delivery=None):
    """
    Available Qty for non-serialized equipment.

    total_qty from Catering Equipment
    minus outstanding_qty from submitted Catering Equipment Delivery documents.
    """

    if not equipment:
        return 0

    equipment_doc = frappe.get_doc(
        "Catering Equipment",
        equipment,
    )
    equipment_doc.check_permission("read")

    total_qty = cint(equipment_doc.total_qty or 0)

    filters = {
        "equipment": equipment
    }

    exclude_condition = ""
    values = {
        "equipment": equipment
    }

    if exclude_delivery:
        excluded_delivery_doc = frappe.get_doc(
            "Catering Equipment Delivery",
            exclude_delivery,
        )
        excluded_delivery_doc.check_permission("read")

        exclude_condition = "and parent_doc.name != %(exclude_delivery)s"
        values["exclude_delivery"] = exclude_delivery

    delivered_qty = frappe.db.sql(
        f"""
        select
            coalesce(sum(item.outstanding_qty), 0)
        from
            `tabCatering Equipment Delivery Item` item
        inner join
            `tabCatering Equipment Delivery` parent_doc
        on
            parent_doc.name = item.parent
        where
            parent_doc.docstatus = 1
            and parent_doc.status not in ('Returned', 'Closed')
            and item.equipment = %(equipment)s
            and coalesce(item.has_serial_no, 0) = 0
            {exclude_condition}
        """,
        values
    )[0][0]

    available_qty = total_qty - cint(delivered_qty)

    if available_qty < 0:
        available_qty = 0

    return available_qty


@frappe.whitelist()
def get_equipment_info(equipment):
    if not equipment:
        return {}

    doc = frappe.get_doc(
        "Catering Equipment",
        equipment,
    )
    doc.check_permission("read")

    return {
        "equipment": doc.name,
        "equipment_name_arabic": doc.equipment_name_arabic,
        "has_serial_no": cint(doc.has_serial_no),
        "total_qty": cint(doc.total_qty or 0),
        "available_qty": get_available_qty(doc.name),
        "disabled": cint(doc.disabled)
    }


def update_equipment_unit_as_delivered(unit, center):
    if not unit:
        return

    frappe.db.set_value(
        "Catering Equipment Unit",
        unit,
        {
            "status": "Delivered",
            "current_center": center
        }
    )


def update_equipment_unit_as_available(unit):
    if not unit:
        return

    frappe.db.set_value(
        "Catering Equipment Unit",
        unit,
        {
            "status": "Available",
            "current_center": None
        }
    )