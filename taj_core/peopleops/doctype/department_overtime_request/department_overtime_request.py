import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import get_datetime, getdate, now_datetime, add_days, add_to_date

class DepartmentOvertimeRequest(Document):
    def validate(self):
        self._calculate_requested_hours()
        self._validate_not_future()
        self._validate_overlaps_within_doc()
        self._validate_overlaps_across_docs()

    def before_submit(self):
        self._calculate_requested_hours()
        self._validate_not_future()
        self._validate_overlaps_within_doc()
        self._validate_overlaps_across_docs()

    def _to_dt(self, d, t):
        if not d or not t:
            return None
        t = str(t)
        if len(t) == 5:
            t += ":00"
        return get_datetime(f"{d} {t}")

    def _get_interval(self, overtime_date, from_time, to_time):
        start = self._to_dt(overtime_date, from_time)
        end = self._to_dt(overtime_date, to_time)
        if not start or not end:
            return None, None

        # cross midnight
        if end <= start:
            end = add_days(end, 1)

        return start, end

    def _calculate_requested_hours(self):
        for row in (self.get("department_overtime_request_line") or []):
            if not row.overtime_date or not row.from_time or not row.to_time:
                row.requested_hours = 0
                continue

            start, end = self._get_interval(row.overtime_date, row.from_time, row.to_time)
            if not start or not end:
                row.requested_hours = 0
                continue

            row.requested_hours = round((end - start).total_seconds() / 3600.0, 2)

    def _validate_not_future(self):
        now_dt = now_datetime()
        today = getdate(now_dt)

        for row in (self.get("department_overtime_request_line") or []):
            if not row.overtime_date:
                continue

            row_date = getdate(row.overtime_date)

            if row_date > today:
                frappe.throw(
                    _("Overtime date cannot be in the future. Date: {0}, Now: {1}")
                    .format(row.overtime_date, now_dt),
                    title=_("Validation Error"),
                )

            if row.from_time and row.to_time:
                start, end = self._get_interval(
                    row.overtime_date, row.from_time, row.to_time
                )
                if (start and start > now_dt) or (end and end > now_dt):
                    frappe.throw(
                        _("Overtime time cannot be in the future. Employee: {0}. Start: {1}, End: {2}, Now: {3}")
                        .format(row.employee or "", start, end, now_dt),
                        title=_("Validation Error"),
                    )

    def _validate_overlaps_within_doc(self):
        """Prevent overlaps داخل نفس المستند لنفس الموظف (إذا تكرر الموظف في عدة أسطر)."""
        rows = self.get("department_overtime_request_line") or []
        by_emp = {}

        for r in rows:
            if not r.employee or not r.overtime_date or not r.from_time or not r.to_time:
                continue

            start, end = self._get_interval(r.overtime_date, r.from_time, r.to_time)
            if not start or not end:
                continue

            by_emp.setdefault(r.employee, []).append((start, end, r))

        for emp, items in by_emp.items():
            items.sort(key=lambda x: x[0])
            for i in range(1, len(items)):
                prev_start, prev_end, prev_row = items[i - 1]
                cur_start, cur_end, cur_row = items[i]

                if cur_start < prev_end:
                    frappe.throw(
                        _("Overlap within the same document for Employee {0}: ({1} {2}-{3}) overlaps with ({4} {5}-{6}).")
                        .format(
                            emp,
                            prev_row.overtime_date, prev_row.from_time, prev_row.to_time,
                            cur_row.overtime_date, cur_row.from_time, cur_row.to_time
                        ),
                        title=_("Validation Error"),
                    )

    def _validate_overlaps_across_docs(self):
        """Prevent overlaps مع مستندات أخرى لنفس الموظف (Draft/Submitted) باستثناء الملغاة."""
        current_name = self.name or ""
        rows = self.get("department_overtime_request_line") or []

        for r in rows:
            if not r.employee or not r.overtime_date or not r.from_time or not r.to_time:
                continue

            start, end = self._get_interval(r.overtime_date, r.from_time, r.to_time)
            if not start or not end:
                continue

            # Cover cross-midnight scenarios: check same date + day before + day after
            d = getdate(r.overtime_date)
            dates = (
                add_to_date(d, days=-1),
                d,
                add_to_date(d, days=1),
            )

            conflicts = frappe.db.sql(
                """
                SELECT l.parent, l.overtime_date, l.from_time, l.to_time
                FROM `tabDepartment Overtime Request Line` l
                JOIN `tabDepartment Overtime Request` p ON p.name = l.parent
                WHERE l.employee = %(employee)s
                  AND l.overtime_date IN %(dates)s
                  AND p.docstatus = 1
                  AND l.parent != %(current)s
                """,
                {"employee": r.employee, "dates": tuple(dates), "current": current_name},
                as_dict=True,
            )

            for c in conflicts:
                c_start, c_end = self._get_interval(c.overtime_date, c.from_time, c.to_time)
                if not c_start or not c_end:
                    continue

                # Overlap rule: start < other_end AND other_start < end
                if start < c_end and c_start < end:
                    frappe.throw(
                        _("Overlap found for Employee {0}. Current: ({1} {2}-{3}) conflicts with {4}: ({5} {6}-{7}).")
                        .format(
                            r.employee,
                            r.overtime_date, r.from_time, r.to_time,
                            c.parent,
                            c.overtime_date, c.from_time, c.to_time,
                        ),
                        title=_("Validation Error"),
                    )
