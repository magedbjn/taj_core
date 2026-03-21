# Copyright (c) 2026, Maged Bajandooh and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class ProductionPlanSubAssemblySplit(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		assembly_qty: DF.Float
		merge_group_id: DF.Data | None
		merged_sub_assembly_item: DF.Data | None
		parent: DF.Data
		parentfield: DF.Data
		parenttype: DF.Data
		source_assembly_item: DF.Link | None
		source_fg_bom_no: DF.Link | None
		source_fg_item_code: DF.Link | None
		source_sub_assembly_item: DF.Data | None
		sub_assembly_bom_no: DF.Link | None
		sub_assembly_item_code: DF.Link | None
		sub_assembly_qty: DF.Float
	# end: auto-generated types
	pass
