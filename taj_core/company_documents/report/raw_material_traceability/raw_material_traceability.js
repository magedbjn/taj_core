frappe.query_reports["Raw Material Traceability"] = {
    "filters": [
        {
            "fieldname": "company",
            "label": __("Company"),
            "fieldtype": "Link",
            "options": "Company",
            "default": frappe.defaults.get_user_default("Company"),
            "reqd": 1,
            "width": 100
        },
        {
            "fieldname": "finished_product",
            "label": __("Finished Product"),
            "fieldtype": "Link", 
            "options": "Item",
            "width": 200,
            "get_query": function() {
                return {
                    "filters": {
                        "item_group": "Finished Goods"
                    }
                }
            },
            "on_change": function() {
                var finished_product = frappe.query_report.get_filter_value('finished_product');
                frappe.query_report.set_filter_value('finished_batch', '');
                if (finished_product) {
                    setTimeout(function() {
                        frappe.query_report.refresh();
                    }, 500);
                }
            }
        },
        {
            "fieldname": "finished_batch",
            "label": __("Batch"), 
            "fieldtype": "Link",
            "options": "Batch",
            "width": 200,
            "get_query": function() {
                var finished_product = frappe.query_report.get_filter_value('finished_product');
                if (finished_product) {
                    return {
                        "filters": {
                            "item": finished_product
                        }
                    };
                }
                return {
                    "filters": {
                        "item": "___NO_PRODUCT___"
                    }
                };
            },
            "on_change": function() {
                setTimeout(function() {
                    frappe.query_report.refresh();
                }, 300);
            }
        },
        {
            "fieldname": "from_date",
            "label": __("From Date"),
            "fieldtype": "Date",
            "default": frappe.datetime.add_days(frappe.datetime.get_today(), -30),
            "reqd": 1,
            "width": 100
        },
        {
            "fieldname": "to_date",
            "label": __("To Date"),
            "fieldtype": "Date", 
            "default": frappe.datetime.get_today(),
            "reqd": 1,
            "width": 100
        }
    ],

    "formatter": function(value, row, column, data, default_formatter) {
        value = default_formatter(value, row, column, data);
        
        // جعل الصفوف الرئيسية عريضة
        if (data && data.is_group) {
            value = $(`<span>${value}</span>`);
            var $value = $(value).css("font-weight", "bold");
            value = $value.wrap("<p></p>").parent().html();
        }
        
        return value;
    },

    "onload": function(report) {
        // إضافة تنسيق إضافي للصفوف
        report.wrapper.on("click", ".dt-cell, .dt-row", function() {
            setTimeout(function() {
                $('[data-is-group="1"]').css({
                    'background-color': '#f0f8ff',
                    'border-bottom': '2px solid #ddd'
                });
            }, 100);
        });
    }
};