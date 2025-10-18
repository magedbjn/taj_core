// File: supplier_qualification_list.js
// frappe.listview_settings['Supplier Qualification'] = {
//     get_indicator: function(doc) {
//         var colors = {
//             'Approved': 'green',
//             'Partially Approved': 'orange', 
//             'Request Approval': 'blue',
//             'Rejected': 'red'
//         };
//         return [__(doc.approval_status), colors[doc.approval_status], "status,=," + doc.approval_status];
//     }
// };