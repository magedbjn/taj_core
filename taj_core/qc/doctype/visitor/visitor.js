frappe.ui.form.on('Visitor', {
    onload: function(frm) {
        // اجعل كل الحقول قراءة فقط
        frm.fields.forEach(function(field) {
            // استثناء الحقول المطلوبة لتظل قابلة للتعديل
            if (!(field.df.fieldtype === "Section Break" || field.df.fieldname === "status")) {
                frm.set_df_property(field.df.fieldname, "read_only", 1);
            }
        });
        frm.refresh_fields();
    }
});
