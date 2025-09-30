// Copyright (c) 2024, MAged BAjandooh and contributors
// For license information, please see license.txt

frappe.ui.form.on("Raw Material Specification", {
	setup:function(frm) {
		frm.set_query("item_code", function () {
			return {
				filters: [
					["Item", "item_group", "descendants of", "Raw Material"]
				]	
			}
		});
	},
	
	shelf_life: function(frm) {
		if(frm.doc.shelf_life == 0){
			frm.set_value("expiry_date", null);
		}else if(frm.doc.shelf_life >= 4 && frm.doc.shelf_life <= 7){
			frm.set_value("expiry_date", 4);
		}else if(frm.doc.shelf_life >= 20 && frm.doc.shelf_life <= 30){
			frm.set_value("expiry_date", 20);
		}else if(frm.doc.shelf_life >= 75 && frm.doc.shelf_life <= 90){
			frm.set_value("expiry_date", 75);
		}else if(frm.doc.shelf_life >= 150 && frm.doc.shelf_life <= 180){
			frm.set_value("expiry_date", 150);
		}else if(frm.doc.shelf_life >= 300 && frm.doc.shelf_life <= 365){
			frm.set_value("expiry_date", 300);
		}else if(frm.doc.shelf_life > 365){
			frm.set_value("expiry_date", 90);
		}
	},
	
	expiry_date: function(frm){
		if(frm.doc.expiry_date > frm.doc.shelf_life){
			frm.set_value("expiry_date", "");
			frappe.throw({
					message: "Expiry Date Upon Receiving greater than Shelf Life.",
					indicator: "red",
					title: __("Invalid entry"),
			});
			
		}
	}
});


		