"""Canonical GMP checklist catalog derived from the supplied v2 workbook.

Every source workbook row is represented. Repeated or area-only variants reuse
one canonical Checklist Question across templates; compound rows may map to two
questions only when the failure types/actions are materially different.

This module has no Frappe imports so the catalog can be validated in isolation.
"""

import hashlib
import re

from taj_core.checklist.gmp_source_catalog import GMP_SOURCE_ROWS
from taj_core.checklist.rules import parse_weeks_of_month


def _q(
    question,
    group,
    reference,
    *,
    severity="Medium",
    quality_impact=0,
    affected_items=None,
    issue_types=None,
    legacy_questions=None,
):
    iso_reference = str(reference or "").strip()
    if iso_reference.startswith("ISO 22000 "):
        iso_reference = iso_reference[len("ISO 22000 "):].strip()

    affected_items = [str(value).strip() for value in (affected_items or []) if str(value).strip()]
    issue_types = [str(value).strip() for value in (issue_types or []) if str(value).strip()]
    legacy_questions = [str(value).strip() for value in (legacy_questions or []) if str(value).strip()]

    return {
        "question": question,
        "question_group": group,
        "standard_reference": reference,
        "standards": [
            {"standard": "GMP", "reference": ""},
            {"standard": "ISO 22000", "reference": iso_reference},
        ],
        "issue_severity": severity,
        "quality_impact": int(bool(quality_impact)),
        # GMP failures should be auditable, but the extra fields only appear on Fail.
        "require_failure_reason": 0,
        "require_failure_note": 1,
        "require_failure_photo": 0,
        "allow_no_photo_with_reason": 0,
        "require_affected_item": int(bool(affected_items)),
        "affected_item_options": "\n".join(affected_items),
        "require_issue_type": int(bool(issue_types)),
        "issue_type_options": "\n".join(issue_types),
        "legacy_questions": legacy_questions,
    }


GMP_QUESTIONS = {
    # Facilities & housekeeping
    "facility_cleanliness": _q(
        "Floors, walls, ceilings, doors, light fixtures and other area surfaces are visibly clean.",
        "Facilities & Housekeeping",
        "ISO 22000 7.1.3 / 8.2.4(a),(i)",
        affected_items=["Floor", "Wall", "Ceiling", "Door", "Light Fixture", "Drain", "Rack", "Other Surface"],
        issue_types=["Cleaning", "Stain / Residue", "Other"],
    ),
    "facility_condition": _q(
        "Floors, walls, ceilings, doors, light fixtures and other area structures are in good condition.",
        "Facilities & Housekeeping",
        "ISO 22000 7.1.3 / 8.2.4(a)",
        affected_items=["Floor", "Wall", "Ceiling", "Door", "Light Fixture", "Drain", "Rack", "Other Structure"],
        issue_types=["Damage", "Crack / Breakage", "Electrical", "Corrosion", "Other"],
    ),
    "area_dry_no_water": _q(
        "The area is free from standing water, leaks and excessive condensation.",
        "Facilities & Housekeeping",
        "ISO 22000 7.1.4 / 8.2.4(i)",
        severity="High",
        quality_impact=1,
    ),
    "area_free_clutter": _q(
        "The area is free from unnecessary materials and uncontrolled waste.",
        "Facilities & Housekeeping",
        "ISO 22000 7.1.4 / 8.2.4(d),(i)",
    ),
    "incubation_dust_debris": _q(
        "Walls, light fixtures, racks and floors are free from dust and accumulated debris.",
        "Cleaning & Chemicals",
        "ISO 22000 8.2.4(i)",
        legacy_questions=[
            "Are walls, lights/light fixtures, racks and floors free from dust and accumulated debris?"
        ],
    ),
    "freezer_frost": _q(
        "The freezer is free from excessive ice or frost accumulation.",
        "Facilities & Housekeeping",
        "ISO 22000 7.1.4 / 8.2.4(i)",
        severity="High",
    ),
    "ventilation_effective": _q(
        "Ventilation and extraction systems are visibly clean and operating effectively.",
        "Facilities & Housekeeping",
        "ISO 22000 7.1.4 / 8.2.4(c)",
        affected_items=["Ventilation Unit", "Extractor", "Duct / Grille"],
        issue_types=["Cleaning", "Not Operating", "Poor Airflow", "Damage", "Other"],
        legacy_questions=["Ventilation and extraction systems are clean and functioning adequately."],
    ),
    "dispatch_hygiene": _q(
        "Loading and dispatch areas are clean and protected from contamination.",
        "Facilities & Housekeeping",
        "ISO 22000 8.2.4(g),(i)",
        severity="High",
        quality_impact=1,
    ),

    # Storage & traceability
    "storage_off_floor_clearance": _q(
        "Materials and products are stored off the floor on suitable racks or pallets.",
        "Storage & Traceability",
        "ISO 22000 8.2.4(g)",
        legacy_questions=["Materials and products are stored off the floor with enough clearance for cleaning, inspection and airflow."],
    ),
    "products_covered": _q(
        "Stored materials and products are covered or sealed and protected from contamination.",
        "Storage & Traceability",
        "ISO 22000 8.2.4(g)",
        severity="High",
        quality_impact=1,
    ),
    "items_identified": _q(
        "Stored products and batches are clearly labelled and identifiable.",
        "Storage & Traceability",
        "ISO 22000 8.3 / 8.2.4(g)",
        severity="High",
        quality_impact=1,
        legacy_questions=["Stored materials, products and intermediate items are clearly labelled and identifiable."],
    ),
    "opened_material_date": _q(
        "Opened raw materials carry the required opening or date identification.",
        "Storage & Traceability",
        "ISO 22000 8.3 / 8.2.4(g)",
    ),
    "batch_separation": _q(
        "Different product batches are arranged to prevent mix-up.",
        "Storage & Traceability",
        "ISO 22000 8.2.4(g)",
        severity="High",
        quality_impact=1,
    ),
    "damaged_packs_segregated": _q(
        "Leaking or damaged packs are segregated from acceptable product.",
        "Storage & Traceability",
        "ISO 22000 8.2.4(g),(h)",
        severity="High",
        quality_impact=1,
    ),
    "not_below_cooling_unit": _q(
        "Materials are not stored directly below cooling units where condensate could contaminate them.",
        "Storage & Traceability",
        "ISO 22000 8.2.4(g),(h)",
        severity="High",
        quality_impact=1,
    ),

    # Cross-contamination & product protection
    "allergens_segregated": _q(
        "Allergenic materials are clearly identified and segregated.",
        "Cross-contamination & Product Protection",
        "ISO 22000 8.2.4(h)",
        severity="Critical",
        quality_impact=1,
    ),
    "raw_rte_segregated": _q(
        "Raw materials are adequately segregated from cooked or ready-to-eat materials.",
        "Cross-contamination & Product Protection",
        "ISO 22000 8.2.4(h)",
        severity="Critical",
        quality_impact=1,
    ),
    "colour_coded_tools": _q(
        "Colour-coded or dedicated cleaning tools are used in the correct area where required.",
        "Cross-contamination & Product Protection",
        "ISO 22000 8.2.4(h),(i)",
        severity="High",
        quality_impact=1,
        legacy_questions=["Colour-coded or dedicated utensils and cleaning tools are used in the correct area where required."],
    ),
    "no_overhead_dripping": _q(
        "There is no excessive condensation or dripping above exposed food.",
        "Cross-contamination & Product Protection",
        "ISO 22000 7.1.4 / 8.2.4(h)",
        severity="Critical",
        quality_impact=1,
    ),
    "exposed_product_protected": _q(
        "Exposed products are protected from dust, splash, contact and other environmental contamination.",
        "Cross-contamination & Product Protection",
        "ISO 22000 8.2.4(h)",
        severity="Critical",
        quality_impact=1,
        affected_items=["Exposed Product", "Product Cover / Guard", "Work Area"],
        issue_types=["Dust", "Splash", "Unprotected Contact", "Other Contamination Risk"],
        legacy_questions=["Exposed products are protected from environmental contamination."],
    ),

    # Cleaning & chemicals
    "food_contact_sanitized": _q(
        "Food-contact surfaces are clean and sanitized before use and whenever required by the cleaning program.",
        "Cleaning & Chemicals",
        "ISO 22000 8.2.4(e),(i)",
        severity="Critical",
        quality_impact=1,
        affected_items=["Work Surface", "Utensil", "Equipment Food-Contact Surface", "Container"],
        issue_types=["Cleaning", "Sanitizing", "Residue / Contamination", "Other"],
        legacy_questions=["Food-contact surfaces are clean and sanitized when the area is not in active production."],
    ),
    "cleaning_tools_hygienic": _q(
        "Cleaning tools are visibly clean, intact and stored in designated hygienic locations.",
        "Cleaning & Chemicals",
        "ISO 22000 8.2.4(i)",
        affected_items=["Cleaning Tool", "Tool Storage"],
        issue_types=["Cleaning", "Damage", "Storage", "Other"],
        legacy_questions=[
            "Cleaning tools are visibly clean, intact and stored hygienically off the floor.",
            "Cleaning tools are clean, intact, stored hygienically and kept off the floor.",
        ],
    ),
    "chemicals_controlled": _q(
        "Cleaning chemicals are correctly labelled and stored in designated locations away from food or product.",
        "Cleaning & Chemicals",
        "ISO 22000 8.2.4(h),(i)",
        severity="High",
        quality_impact=1,
        legacy_questions=["Cleaning chemicals are correctly labelled, closed, in approved containers and stored away from food or product."],
    ),
    "waste_spills_controlled": _q(
        "Waste, food residues and spillages are removed and controlled without accumulation.",
        "Cleaning & Chemicals",
        "ISO 22000 8.2.4(d),(i)",
        severity="High",
        quality_impact=1,
    ),

    # Pest control
    "external_entry_protected": _q(
        "Air curtains and/or plastic strip curtains, where installed, are clean, intact, correctly positioned and functioning effectively.",
        "Pest Control",
        "ISO 22000 7.1.3 / 8.2.4(a),(d)",
        severity="High",
        legacy_questions=["External access doors, air curtains and strip curtains are closed or effective where installed and prevent pest entry."],
    ),
    "pest_devices_effective": _q(
        "Fly catcher units, where installed, are clean, operational, appropriately positioned and free from excessive insect accumulation.",
        "Pest Control",
        "ISO 22000 8.2.4(d)",
        severity="High",
        legacy_questions=["Pest control devices are intact, accessible, clean and operational where installed."],
    ),
    "pest_evidence_absent": _q(
        "The area is free from insects, rodents, droppings and other pest evidence.",
        "Pest Control",
        "ISO 22000 8.2.4(d)",
        severity="Critical",
        quality_impact=1,
    ),

    # Equipment / foreign material
    "equipment_condition": _q(
        "Equipment, utensils, racks, pallets, containers and handling items are intact and free from rust, corrosion, pitting or flaking surfaces.",
        "Equipment & Foreign Material",
        "ISO 22000 8.2.4(e),(g),(h)",
        severity="High",
        quality_impact=1,
        affected_items=["Equipment", "Utensil", "Rack", "Shelf", "Pallet", "Container", "Trolley", "Retort Basket", "Other Handling Item"],
        issue_types=["Damage", "Rust / Corrosion", "Pitting / Flaking", "Other"],
        legacy_questions=[
            "Equipment, utensils, racks, pallets and containers are visibly clean, intact and free from rust, corrosion, pitting or flaking surfaces.",
            "Equipment, utensils, racks, pallets and containers are clean, intact and free from rust, corrosion, pitting or flaking surfaces.",
        ],
    ),
    "foreign_material_risk_absent": _q(
        "The area is free from uncontrolled glass, brittle plastic, loose metal and other foreign-material risks.",
        "Equipment & Foreign Material",
        "ISO 22000 8.2.4(e),(h)",
        severity="Critical",
        quality_impact=1,
    ),

    # Personnel / packaging
    "personnel_hygiene": _q(
        "Personnel comply with required hand hygiene and protective clothing/PPE practices.",
        "Personnel Hygiene",
        "ISO 22000 8.2.4(j)",
        severity="Critical",
        quality_impact=1,
        affected_items=["Hand Hygiene", "Hair Cover", "Face Mask", "Gloves", "Protective Clothing / PPE", "Jewelry / Personal Items"],
        issue_types=["Missing", "Incorrect Use", "Hygiene Non-compliance", "Other"],
        legacy_questions=["Personnel follow required hand hygiene and protective clothing practices."],
    ),
    "packaging_hygiene": _q(
        "Trays, pouches, lids and other packaging materials are stored and handled hygienically.",
        "Packaging & Handling",
        "ISO 22000 8.2.4(f),(g)",
        severity="High",
        quality_impact=1,
    ),
}


# Additional canonical requirements from the full workbook. These were omitted
# from the first lean trial but are kept now because the approved rule is:
# include every source requirement and remove only repetition/area-only variants.
GMP_QUESTIONS.update({
    "receiving_doors_protected": _q(
        "Receiving doors are kept closed when not in use and protected against pest entry.",
        "Pest Control",
        "ISO 22000 8.2.4(d)",
        severity="High",
        affected_items=["Receiving Door", "Door Seal / Gap", "Pest Barrier"],
        issue_types=["Left Open", "Gap / Seal Damage", "Missing Pest Barrier", "Other"],
    ),
    "rodent_traps_effective": _q(
        "Rodent trap boxes, where installed, are present at designated locations, intact, secured and unobstructed.",
        "Pest Control",
        "ISO 22000 8.2.4(d)",
        severity="High",
        affected_items=["Rodent Trap Box"],
        issue_types=["Missing", "Damaged", "Not Secured", "Obstructed", "Wrong Location", "Other"],
    ),
    "pest_trap_identification": _q(
        "Pest trap labels and identification numbers are present, legible, correct and match the approved pest-control layout.",
        "Pest Control",
        "ISO 22000 8.2.4(d)",
        severity="High",
        affected_items=["Pest Trap Label / ID"],
        issue_types=["Missing", "Unreadable", "Incorrect ID", "Layout Mismatch", "Other"],
    ),
    "pest_monitoring_points": _q(
        "Pest monitoring points, where installed, are intact, accessible and correctly identified.",
        "Pest Control",
        "ISO 22000 8.2.4(d)",
        severity="High",
    ),
    "non_designated_equipment_absent": _q(
        "The area is free from equipment or tools not designated for use in that area.",
        "Equipment & Foreign Material",
        "ISO 22000 8.2.4(e),(h)",
        severity="High",
        affected_items=["Equipment", "Tool", "Utensil", "Other"],
        issue_types=["Wrong Area", "Cross-contamination Risk", "Other"],
    ),
    "equipment_cleanliness": _q(
        "Equipment, utensils, racks, containers, trolleys and other handling items are visibly clean, intact and free from contamination.",
        "Equipment & Foreign Material",
        "ISO 22000 8.2.4(e),(i)",
        severity="High",
        quality_impact=1,
        affected_items=["Equipment", "Utensil", "Rack", "Container", "Trolley", "Retort Basket", "Other Handling Item"],
        issue_types=["Cleaning", "Residue / Contamination", "Other"],
    ),
    "chemicals_approved_containers": _q(
        "Cleaning chemicals are correctly labelled and kept in approved containers.",
        "Cleaning & Chemicals",
        "ISO 22000 8.2.4(h),(i)",
        severity="High",
        quality_impact=1,
    ),
    "chemical_container_integrity": _q(
        "Chemical containers are closed, intact and leak-free, and chemicals are not transferred into unlabelled containers.",
        "Cleaning & Chemicals",
        "ISO 22000 8.2.4(h)",
        severity="High",
        quality_impact=1,
    ),
    "colour_coded_utensils": _q(
        "Colour-coded utensils and cutting boards are used correctly where applicable.",
        "Cross-contamination & Product Protection",
        "ISO 22000 8.2.4(h)",
        severity="High",
        quality_impact=1,
    ),
    "cleaning_tools_off_floor": _q(
        "Cleaning tools and hoses are stored off the floor after use and allowed to dry hygienically where applicable.",
        "Cleaning & Chemicals",
        "ISO 22000 8.2.4(i)",
        affected_items=["Cleaning Tool", "Hose", "Tool Rack / Holder"],
        issue_types=["Stored on Floor", "Not Drying Hygienically", "Storage", "Other"],
    ),
    "cleaning_tools_separate_finished": _q(
        "Cleaning tools are stored separately from finished products.",
        "Cross-contamination & Product Protection",
        "ISO 22000 8.2.4(h),(i)",
        severity="High",
        quality_impact=1,
    ),
    "raw_material_identification": _q(
        "Raw materials are clearly labelled and identifiable with required item and batch/lot information.",
        "Storage & Traceability",
        "ISO 22000 8.3 / 8.2.4(g)",
        severity="High",
        quality_impact=1,
    ),
    "intermediate_identification": _q(
        "Sub-processed, intermediate and cooked items are clearly labelled and identifiable with required product and batch/date information.",
        "Storage & Traceability",
        "ISO 22000 8.3 / 8.2.4(g)",
        severity="High",
        quality_impact=1,
    ),
    "unidentified_items_absent": _q(
        "Unidentified or incorrectly labelled materials and products are absent from controlled storage areas.",
        "Storage & Traceability",
        "ISO 22000 8.3",
        severity="High",
        quality_impact=1,
    ),
    "storage_clearance": _q(
        "Adequate clearance is maintained around stored materials and products for cleaning, inspection, airflow and pest inspection as applicable.",
        "Storage & Traceability",
        "ISO 22000 8.2.4(d),(g)",
    ),
    "storage_orderly": _q(
        "Stored products are arranged orderly to prevent obstruction and support hygienic handling.",
        "Storage & Traceability",
        "ISO 22000 8.2.4(g)",
    ),
    "storage_area_clean_dry": _q(
        "Storage areas are clean, dry and free from leaks or excessive condensation.",
        "Facilities & Housekeeping",
        "ISO 22000 7.1.4 / 8.2.4(i)",
        severity="High",
        quality_impact=1,
    ),
    "waste_bins_hygienic": _q(
        "Waste bins are clean, controlled and emptied regularly.",
        "Cleaning & Chemicals",
        "ISO 22000 8.2.4(d)",
        severity="High",
    ),
    "retort_housekeeping": _q(
        "The retort area is free from standing water, debris and uncontrolled waste.",
        "Facilities & Housekeeping",
        "ISO 22000 8.2.4(d),(i)",
        severity="High",
        quality_impact=1,
    ),
})


AREA_WEEKS = {
    "Receiving": "1,3",
    "Dry Store": "1,3",
    "Chiller": "1,3",
    "Freezer": "1,3",
    "Preparation Area": "2,4",
    "Cooking Area": "2,4",
    "Filling & Retort Area": "2,4",
    "Incubation Area": "1,3",
    "Finished Goods Area": "1,3",
}


def _source_fallback_key(question):
    normalized = re.sub(r"[^a-z0-9]+", "_", str(question or "").lower()).strip("_")
    digest = hashlib.sha1(str(question or "").encode("utf-8")).hexdigest()[:8]
    return f"source_{normalized[:48]}_{digest}"


def _source_group(category):
    category = str(category or "").strip()
    low = category.lower()
    if "pest" in low:
        return "Pest Control"
    if any(token in low for token in ("building", "hygiene & sanitation", "hygiene & facilities", "housekeeping", "utilities")):
        return "Facilities & Housekeeping"
    if any(token in low for token in ("storage", "identification", "traceability")):
        return "Storage & Traceability"
    if "personnel" in low:
        return "Personnel Hygiene"
    if "packaging" in low:
        return "Packaging & Handling"
    if any(token in low for token in ("cleaning", "chemical", "waste")):
        return "Cleaning & Chemicals"
    if any(token in low for token in ("cross-contamination", "contamination prevention")):
        return "Cross-contamination & Product Protection"
    if any(token in low for token in ("equipment", "foreign material")):
        return "Equipment & Foreign Material"
    if "dispatch" in low:
        return "Facilities & Housekeeping"
    return category or "GMP"


def _source_reference(row):
    clause = str(row.get("iso_clause") or "").strip()
    return f"ISO 22000 {clause}" if clause else "ISO 22000"


def _canonical_keys_for_source(row):
    """Map one workbook row to canonical question keys.

    The mapping is intentionally conservative: only exact/area-only variants
    and clearly compound rows are consolidated. Anything not covered here is
    retained as its own source-derived canonical question.
    """
    q = str(row.get("question") or "").strip()
    low = q.lower()

    # Building rows combine cleanliness and physical condition in Excel. Split
    # those two because they can create different corrective actions.
    if low.startswith("are floors, walls") and "clean" in low:
        return ("facility_cleanliness", "facility_condition")
    if "incubation room clean, dry and structurally maintained" in low:
        return ("facility_cleanliness", "area_dry_no_water", "facility_condition")

    if "receiving area free from standing water, waste and unnecessary materials" in low:
        return ("area_dry_no_water", "area_free_clutter")
    if ("store clean, dry and free from leakage or condensation" in low
            or "warehouse clean, dry and free from leaks or condensation" in low):
        return ("storage_area_clean_dry",)
    if "chiller free from excessive condensation, leaks and standing water" in low:
        return ("area_dry_no_water",)
    if "retort area free from standing water, debris and uncontrolled waste" in low:
        return ("retort_housekeeping",)
    if "area clean and free from unnecessary materials" in low:
        return ("area_free_clutter",)

    if "walls, lights/light fixtures, racks and floors free from dust and accumulated debris" in low:
        return ("incubation_dust_debris",)

    if "receiving doors kept closed" in low:
        return ("receiving_doors_protected",)
    if "air curtain units" in low:
        return ("external_entry_protected",)
    if "equipment or tools not designated" in low:
        return ("non_designated_equipment_absent",)

    if "fly catcher" in low:
        return ("pest_devices_effective",)
    if "rodent trap boxes" in low:
        return ("rodent_traps_effective",)
    if "pest trap labels/identification numbers" in low:
        return ("pest_trap_identification",)
    if "pest monitoring points" in low:
        return ("pest_monitoring_points",)
    if ("pest evidence" in low or "pest activity or evidence" in low
            or "insects, rodents" in low):
        return ("pest_evidence_absent",)

    if "free from rust" in low or "free from rust, corrosion" in low:
        return ("equipment_condition",)
    if "utensils and equipment clean, intact and free from contamination" in low:
        return ("equipment_cleanliness",)
    if "retort baskets, trolleys and handling equipment clean and maintained" in low:
        return ("equipment_cleanliness",)

    if low.startswith("are cleaning tools clean") or low.startswith("are cleaning tools clean and properly stored"):
        return ("cleaning_tools_hygienic",)
    if "cleaning tools stored separately from finished products" in low:
        return ("cleaning_tools_separate_finished",)
    if ("cleaning tools stored off the floor" in low
            or "hoses and cleaning tools stored off the floor" in low):
        return ("cleaning_tools_off_floor",)
    if "cleaning tools" in low and ("colour-coded" in low or "color-coded" in low or "dedicated" in low):
        return ("colour_coded_tools",)
    if "colour-coded utensils and cutting boards" in low:
        return ("colour_coded_utensils",)

    if "chemical containers" in low:
        return ("chemical_container_integrity",)
    if "cleaning chemicals correctly labelled and kept in approved containers" in low:
        return ("chemicals_approved_containers",)
    if "chemicals stored away from food and food-contact equipment" in low:
        return ("chemicals_controlled",)
    if "cleaning chemicals" in low or "cleaning chemicals correctly" in low:
        keys = ["chemicals_controlled"]
        if "closed" in low:
            keys.append("chemical_container_integrity")
        return tuple(keys)

    if "raw and cooked/rte materials" in low:
        return ("raw_rte_segregated",)
    if "raw and cooked/rte materials adequately separated" in low:
        return ("raw_rte_segregated",)
    if "allergenic materials" in low:
        return ("allergens_segregated",)
    if "colour-coded utensils and cutting boards" in low:
        return ("colour_coded_utensils",)
    if "excessive condensation or dripping above exposed food" in low:
        return ("no_overhead_dripping",)
    if "exposed products protected from environmental contamination" in low:
        return ("exposed_product_protected",)
    if "glass, brittle plastic, loose metal" in low:
        return ("foreign_material_risk_absent",)

    if "food-contact surfaces" in low and ("clean" in low or "cleaned" in low):
        return ("food_contact_sanitized",)
    if "waste bins clean, controlled and emptied regularly" in low:
        return ("waste_bins_hygienic",)
    if "spills and food residues removed promptly" in low:
        return ("waste_spills_controlled",)
    if "waste, food residues and spillages removed promptly" in low:
        return ("waste_spills_controlled",)

    if "raw materials clearly labelled" in low:
        return ("raw_material_identification",)
    if "opened raw materials labelled" in low:
        return ("opened_material_date",)
    if (("sub-processed" in low or "intermediate" in low or "sub-processed/cooked" in low)
            and ("labelled" in low or "identifiable" in low)):
        return ("intermediate_identification",)
    if "unidentified" in low and ("absent" in low or "incorrectly labelled" in low):
        return ("unidentified_items_absent",)
    if "products/batches clearly labelled" in low or "stored finished products clearly labelled" in low:
        return ("items_identified",)

    if "different batches arranged to prevent mix-up" in low:
        return ("batch_separation",)
    if "leaking or damaged packs" in low or "damaged cartons, trays or pouches" in low:
        return ("damaged_packs_segregated",)
    if "material store directly under the chilling unit" in low:
        return ("not_below_cooling_unit",)

    if "materials stored off the floor with adequate clearance" in low:
        return ("storage_off_floor_clearance", "storage_clearance")
    if "products stored off the floor and arranged to allow cleaning access" in low:
        return ("storage_off_floor_clearance", "storage_clearance")
    if "finished products stored off the floor and protected from contamination" in low:
        return ("storage_off_floor_clearance", "products_covered")
    if "adequate space maintained around stored products" in low:
        return ("storage_clearance",)
    if "products stored orderly with sufficient clearance" in low:
        return ("storage_orderly", "storage_clearance")
    if "adequate clearance maintained around pallets" in low:
        return ("storage_clearance",)
    if ("materials properly covered or sealed" in low
            or "stored products properly covered and protected" in low
            or "products properly wrapped, covered and protected" in low):
        return ("products_covered",)

    if "excessive ice or frost accumulation" in low:
        return ("freezer_frost",)
    if "ventilation and extraction systems" in low:
        return ("ventilation_effective",)
    if ("employees following personal hygiene" in low
            or "operators following required hand hygiene" in low):
        return ("personnel_hygiene",)
    if "trays, pouches and lids stored and handled hygienically" in low:
        return ("packaging_hygiene",)
    if "loading and dispatch areas" in low:
        return ("dispatch_hygiene",)

    return (_source_fallback_key(q),)


def _add_source_fallback_questions():
    fallback_rows = {}
    for row in GMP_SOURCE_ROWS:
        for key in _canonical_keys_for_source(row):
            if key.startswith("source_"):
                fallback_rows.setdefault(key, []).append(row)

    for key, rows in fallback_rows.items():
        first = rows[0]
        clauses = []
        for row in rows:
            clause = str(row.get("iso_clause") or "").strip()
            if clause and clause not in clauses:
                clauses.append(clause)
        reference = "ISO 22000 " + " / ".join(clauses)
        GMP_QUESTIONS[key] = _q(
            str(first.get("question") or "").strip(),
            _source_group(first.get("category")),
            reference,
        )


_add_source_fallback_questions()


GMP_SOURCE_COVERAGE = {}
for _row in GMP_SOURCE_ROWS:
    _row_id = (_row["area"], _row["source_no"])
    GMP_SOURCE_COVERAGE[_row_id] = tuple(_canonical_keys_for_source(_row))


GMP_TEMPLATES = {}
for _area, _weeks in AREA_WEEKS.items():
    _question_keys = []
    for _row in GMP_SOURCE_ROWS:
        if _row["area"] != _area:
            continue
        for _key in GMP_SOURCE_COVERAGE[(_area, _row["source_no"])]:
            if _key not in _question_keys:
                _question_keys.append(_key)
    GMP_TEMPLATES[f"GMP - {_area}"] = {
        "periodicity": "Weeks of Month",
        "weeks_of_month": _weeks,
        "questions": _question_keys,
    }


def validate_gmp_catalog():
    """Return human-readable catalog validation errors; empty means valid."""
    errors = []
    seen_texts = set()

    for key, item in GMP_QUESTIONS.items():
        text = str(item.get("question") or "").strip()
        group = str(item.get("question_group") or "").strip()
        reference = str(item.get("standard_reference") or "").strip()
        standards = list(item.get("standards") or [])

        if not key:
            errors.append("Question key cannot be blank")
        if not text:
            errors.append(f"{key}: question text is required")
        elif text in seen_texts:
            errors.append(f"{key}: duplicate question text")
        else:
            seen_texts.add(text)
        if not group:
            errors.append(f"{key}: question_group is required")
        if not reference:
            errors.append(f"{key}: standard_reference is required")
        standard_names = [str(row.get("standard") or "").strip() for row in standards]
        if "GMP" not in standard_names:
            errors.append(f"{key}: GMP standard classification is required")
        if "ISO 22000" not in standard_names:
            errors.append(f"{key}: ISO 22000 standard classification is required")
        if len(standard_names) != len(set(standard_names)):
            errors.append(f"{key}: duplicate standard classification")
        for row in standards:
            if not str(row.get("standard") or "").strip():
                errors.append(f"{key}: standard name is required")
        if item.get("issue_severity") not in {"Low", "Medium", "High", "Critical"}:
            errors.append(f"{key}: invalid issue_severity")
        if item.get("require_affected_item") and not str(item.get("affected_item_options") or "").strip():
            errors.append(f"{key}: affected_item_options are required")
        if item.get("require_issue_type") and not str(item.get("issue_type_options") or "").strip():
            errors.append(f"{key}: issue_type_options are required")

    source_ids = set()
    for row in GMP_SOURCE_ROWS:
        row_id = (row.get("area"), row.get("source_no"))
        if row_id in source_ids:
            errors.append(f"Duplicate source row id: {row_id}")
        source_ids.add(row_id)
        keys = tuple(GMP_SOURCE_COVERAGE.get(row_id) or ())
        if not keys:
            errors.append(f"Unmapped source row: {row_id}")
        for key in keys:
            if key not in GMP_QUESTIONS:
                errors.append(f"{row_id}: unknown canonical key {key}")

    for template_name, template in GMP_TEMPLATES.items():
        if not template_name.startswith("GMP - "):
            errors.append(f"{template_name}: catalog-owned template name must start with GMP -")
        if template.get("periodicity") != "Weeks of Month":
            errors.append(f"{template_name}: periodicity must be Weeks of Month")
        try:
            parse_weeks_of_month(template.get("weeks_of_month"))
        except ValueError as exc:
            errors.append(f"{template_name}: {exc}")

        question_keys = list(template.get("questions") or [])
        if len(question_keys) != len(set(question_keys)):
            errors.append(f"{template_name}: duplicate question key")
        for key in question_keys:
            if key not in GMP_QUESTIONS:
                errors.append(f"{template_name}: unknown question key {key}")

    if set(GMP_TEMPLATES) != {f"GMP - {area}" for area in AREA_WEEKS}:
        errors.append("GMP template areas do not match source workbook areas")

    return errors
