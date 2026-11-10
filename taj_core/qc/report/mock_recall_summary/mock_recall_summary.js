frappe.query_reports["Mock Recall Summary"] = {filters: [
  {fieldname:"company", label:__("Company"), fieldtype:"Link", options:"Company"},
  {fieldname:"from_date", label:__("From Date"), fieldtype:"Date"},
  {fieldname:"to_date", label:__("To Date"), fieldtype:"Date"},
  {fieldname:"scenario_type", label:__("Scenario"), fieldtype:"Select", options:"\nFinished Product\nRaw Material\nPreparation\nPackaging Material"},
  {fieldname:"status", label:__("Status"), fieldtype:"Select", options:"\nDraft\nTraced\nUnder Review\nClosed"},
  {fieldname:"item_code", label:__("Item"), fieldtype:"Link", options:"Item"},
  {fieldname:"batch_no", label:__("Batch"), fieldtype:"Link", options:"Batch"},
  {fieldname:"result", label:__("Assessment"), fieldtype:"Select", options:"\nNot Evaluated\nPassed\nFailed"}
]};
