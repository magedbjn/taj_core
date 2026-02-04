// // department_overtime_request.js

// function _normalize_time(t) {
//   if (!t) return null;
//   if (typeof t === "string" && t.length === 5) return t + ":00";
//   return t;
// }

// function _to_date_obj(dt_str) {
//   // Converts "YYYY-MM-DD" or "YYYY-MM-DD HH:mm:ss" to JS Date object
//   return frappe.datetime.str_to_obj(dt_str);
// }

// function _row_has_future(row) {
//   const today_str = frappe.datetime.get_today();         // "YYYY-MM-DD"
//   const now_str = frappe.datetime.now_datetime();        // "YYYY-MM-DD HH:mm:ss"

//   if (!row.overtime_date) return false;

//   const row_date = _to_date_obj(row.overtime_date);
//   const today = _to_date_obj(today_str);
//   const now = _to_date_obj(now_str);

//   // Future date
//   if (row_date > today) return true;

//   // Same day -> check times
//   if (row.overtime_date === today_str) {
//     const ft = _normalize_time(row.from_time);
//     const tt = _normalize_time(row.to_time);
//     if (!ft || !tt) return false;

//     const start_str = frappe.datetime.combine_date_and_time(row.overtime_date, ft);
//     let end_str = frappe.datetime.combine_date_and_time(row.overtime_date, tt);

//     let start = _to_date_obj(start_str);
//     let end = _to_date_obj(end_str);

//     // cross midnight
//     if (end <= start) {
//       end_str = frappe.datetime.add_days(end_str, 1);
//       end = _to_date_obj(end_str);
//     }

//     return (start > now) || (end > now);
//   }

//   return false;
// }

// function _warn(row) {
//   if (_row_has_future(row)) {
//     frappe.msgprint({
//       title: __("Validation"),
//       indicator: "orange",
//       message: __("Overtime date/time cannot be in the future."),
//     });
//   }
// }

// frappe.ui.form.on("Department Overtime Request", {
//   validate(frm) {
//     // Block Save with clear message
//     (frm.doc.department_overtime_request_line || []).forEach(row => {
//       if (_row_has_future(row)) {
//         frappe.throw(__("Overtime date/time cannot be in the future. Employee: {0}", [row.employee || ""]));
//       }
//     });
//   }
// });

// frappe.ui.form.on("Department Overtime Request Line", {
//   overtime_date(frm, cdt, cdn) { _warn(locals[cdt][cdn]); },
//   from_time(frm, cdt, cdn) { _warn(locals[cdt][cdn]); },
//   to_time(frm, cdt, cdn) { _warn(locals[cdt][cdn]); },
// });
