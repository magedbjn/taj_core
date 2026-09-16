"""Concise engineering-maintenance Checklist seed data.

The source forms are ENG-PM-0001 through ENG-PM-0021.  This module keeps
business data free of Frappe imports so it can be validated outside a site.
Question wording is intentionally short and normalized rather than copied from
the paper forms sentence-for-sentence.
"""


def _pass_fail(question, *, severity="Medium", quality_impact=0):
    return {
        "question": question,
        "type": "Pass/Fail/NA",
        "is_required": 1,
        "quick_pass_allowed": 1,
        "issue_if_no": 1,
        "issue_severity": severity,
        "quality_impact": quality_impact,
        "require_failure_reason": 1,
        "require_follow_up": 1,
    }


def _float(question, minimum, maximum, *, severity="Medium", quality_impact=0):
    return {
        "question": question,
        "type": "Float",
        "answer_min_float": float(minimum),
        "answer_max_float": float(maximum),
        "is_required": 1,
        "quick_pass_allowed": 0,
        "issue_if_no": 1,
        "issue_severity": severity,
        "quality_impact": quality_impact,
        "require_failure_reason": 0,
        "require_follow_up": 1,
    }


def _select(question, options, *, required=1):
    return {
        "question": question,
        "type": "Single Select",
        "answer_select": "\n".join(options),
        "is_required": required,
        "quick_pass_allowed": 0,
        "issue_if_no": 0,
        "issue_severity": "Medium",
        "quality_impact": 0,
        "require_failure_reason": 0,
        "require_follow_up": 0,
    }


def _text(question, *, required=0):
    return {
        "question": question,
        "type": "Text",
        "is_required": required,
        "quick_pass_allowed": 0,
        "issue_if_no": 0,
        "issue_severity": "Low",
        "quality_impact": 0,
        "require_failure_reason": 0,
        "require_follow_up": 0,
    }


QUESTION_LIBRARY = {
    # Shared form metadata / food-factory closeout rule.
    "maintenance_reason": _select("Maintenance reason", ("Routine Maintenance", "Complaint", "Other")),
    "maintenance_notes": _text("Maintenance notes"),
    "area_cleaned_after_maintenance": _pass_fail(
        "Area cleaned after maintenance", severity="High", quality_impact=1
    ),

    # Shared utilities / general machine checks.
    "electrical_supply_220": _pass_fail("Electrical supply (220V)"),
    "electrical_supply_380": _pass_fail("Electrical supply (380V)"),
    "switches_controls": _pass_fail("Switches / controls condition"),
    "switches_touchscreen": _pass_fail("Switches & touch screen condition"),
    "machine_cleanliness": _pass_fail("Equipment cleanliness", severity="High", quality_impact=1),
    "sensors_condition": _pass_fail("Sensors condition"),
    "motor_condition": _pass_fail("Motor condition"),
    "bearings_condition": _pass_fail("Bearings condition"),
    "machine_base": _pass_fail("Machine base / feet condition"),
    "safety_features": _pass_fail("Safety guards / features", severity="High"),
    "belt_condition": _pass_fail("Belt condition"),
    "belt_tension": _pass_fail("Belt tension"),
    "chain_tension": _pass_fail("Chain tension"),
    "fasteners_connections": _pass_fail("Fasteners & connections condition"),
    "filters_strainers": _pass_fail("Filters / strainers condition"),
    "valves_condition": _pass_fail("Valves condition"),
    "temp_pressure_sensors": _pass_fail("Temperature & pressure sensors", severity="High"),
    "water_circulation_pump": _pass_fail("Water circulation pump"),

    # Numeric pressure checks from the source forms.
    "air_pressure_6_7": _float("Compressed air pressure (6-7 bar)", 6, 7),
    "air_pressure_4_4_5": _float("Compressed air pressure (4-4.5 bar)", 4, 4.5),
    "air_pressure_8_9": _float("Compressed air pressure (8-9 bar)", 8, 9),
    "air_pressure_3_4": _float("Compressed air pressure (3-4 bar)", 3, 4),
    "air_pressure_2_4": _float("Compressed air pressure (2-4 bar)", 2, 4),
    "steam_pressure_4_5": _float("Steam pressure (4-5 bar)", 4, 5),
    "steam_pressure_2_3": _float("Steam pressure (2-3 bar)", 2, 3),

    # ENG-PM-0001 SOLPAC.
    "wires_air_hoses": _pass_fail("Electrical wires & air hoses"),
    "air_service_unit": _pass_fail("Air service unit / filter"),
    "sensor_mounting": _pass_fail("Sensor mounting"),
    "sensor_heads_cleanliness": _pass_fail("Sensor heads cleanliness"),
    "air_lubricator_oil": _pass_fail("Air lubricator oil level"),
    "air_cylinders": _pass_fail("Air cylinders mounting"),
    "pneumatic_operation": _pass_fail("Pneumatic system operation"),

    # ENG-PM-0002 Anritsu.
    "machine_parts_condition": _pass_fail("Machine parts condition"),
    "removable_parts_mounting": _pass_fail("Removable parts mounting"),
    "air_unit_drainage": _pass_fail("Air unit drainage"),
    "conveyor_belt_adjustment": _pass_fail("Conveyor belt adjustment"),
    "scale_sensitivity": _pass_fail("Scale sensitivity / calibration", severity="High"),
    "scale_backlash": _pass_fail("Scale backlash"),

    # Retort / cooking systems.
    "soft_cooling_water": _pass_fail("Softened & cooling water supply", severity="High"),
    "chain_conveyor": _pass_fail("Chain conveyor condition"),
    "vessel_condition": _pass_fail("Vessel condition", severity="High"),
    "door_seals": _pass_fail("Door & seals condition", severity="High", quality_impact=1),
    "heater_condition": _pass_fail("Heater condition"),
    "hydraulic_system": _pass_fail("Hydraulic system condition"),
    "pot_condition": _pass_fail("Cooking pot condition", severity="High", quality_impact=1),
    "lid_condition": _pass_fail("Lid / cover condition"),
    "stirrer_drive": _pass_fail("Stirrer motor / bearing / chain"),

    # Cutting / preparation equipment.
    "cutter_blade": _pass_fail("Cutter blade condition", severity="High", quality_impact=1),
    "speed_regulator": _pass_fail("Speed regulator"),
    "motor_oil": _pass_fail("Motor oil level / condition"),
    "mincer_cutting_set": _pass_fail("Mincer blade / tube / disc", severity="High", quality_impact=1),
    "blender_blade": _pass_fail("Blender blade condition", severity="High", quality_impact=1),
    "slicer_disc": _pass_fail("Slicer disc condition", severity="High", quality_impact=1),
    "guide_rod_lubrication": _pass_fail("Guide rod lubrication"),
    "cubing_hydraulic_system": _pass_fail("Hydraulic pump / oil / filter / piston"),
    "blade_clearance": _pass_fail("Blade clearance", severity="High"),
    "grid_blades_knife": _pass_fail("Grid blades & slicer knife", severity="High", quality_impact=1),

    # Pumps / inspection equipment.
    "pump_connections": _pass_fail("Pump connections"),
    "pump_internals": _pass_fail("Diaphragm / seals / balls"),
    "pump_exhaust": _pass_fail("Pump exhaust"),
    "pipes_valves_air_connections": _pass_fail("Pipes / valves / air connections"),
    "metal_detector_sensitivity": _pass_fail(
        "Metal detector sensitivity test", severity="Critical", quality_impact=1
    ),
    "load_cell_sensitivity": _pass_fail("Load cell sensitivity test", severity="High"),
    "air_piston_condition": _pass_fail("Air piston condition"),

    # Packing / small equipment.
    "vacuum_pump_oil": _pass_fail("Vacuum pump oil level / condition"),
    "sealing_components": _pass_fail("Heater / silicone / Teflon condition", severity="High"),
    "electromagnetic_valve": _pass_fail("Electromagnetic valve condition"),
    "hand_blender_set": _pass_fail("Blades / washer / seals", severity="High", quality_impact=1),
    "chain_tension_lubrication": _pass_fail("Chain tension & lubrication"),
    "belt_bearings": _pass_fail("Belt & bearings condition"),

    # Printer / ventilation.
    "air_ink_filters": _pass_fail("Air & ink filters"),
    "pressure_pump": _pass_fail("Pressure pump condition"),
    "print_head": _pass_fail("Print head condition"),
    "fresh_exhaust_filters": _pass_fail("Fresh / exhaust air filters", severity="High", quality_impact=1),
    "hood_lights": _pass_fail("Hood lights"),
    "mechanical_lubrication": _pass_fail("Mechanical lubrication condition"),
    "oil_collector_cleanliness": _pass_fail("Oil collector cleanliness", severity="High", quality_impact=1),
}


_COMMON_END = ("area_cleaned_after_maintenance", "maintenance_notes")


def _template(code, name, *question_keys):
    return {
        "code": code,
        "template_name": name,
        "question_keys": ("maintenance_reason", *question_keys, *_COMMON_END),
    }


TEMPLATES = (
    _template(
        "ENG-PM-0001",
        "SOLPAC Machine Maintenance",
        "wires_air_hoses",
        "air_service_unit",
        "air_pressure_6_7",
        "sensor_mounting",
        "fasteners_connections",
        "sensor_heads_cleanliness",
        "air_lubricator_oil",
        "air_cylinders",
        "pneumatic_operation",
        "belt_tension",
        "chain_tension",
    ),
    _template(
        "ENG-PM-0002",
        "Anristu Machines Maintenance",
        "machine_parts_condition",
        "removable_parts_mounting",
        "air_pressure_4_4_5",
        "air_unit_drainage",
        "conveyor_belt_adjustment",
        "scale_sensitivity",
        "scale_backlash",
        "fasteners_connections",
    ),
    _template(
        "ENG-PM-0003",
        "Retort Sterilizer Maintenance",
        "electrical_supply_380",
        "switches_touchscreen",
        "air_pressure_8_9",
        "steam_pressure_4_5",
        "soft_cooling_water",
        "temp_pressure_sensors",
        "machine_cleanliness",
        "chain_conveyor",
        "filters_strainers",
        "vessel_condition",
        "valves_condition",
        "door_seals",
        "water_circulation_pump",
    ),
    _template(
        "ENG-PM-0004",
        "Mini Retort Maintenance",
        "electrical_supply_380",
        "switches_touchscreen",
        "air_pressure_8_9",
        "heater_condition",
        "soft_cooling_water",
        "temp_pressure_sensors",
        "machine_cleanliness",
        "filters_strainers",
        "vessel_condition",
        "valves_condition",
        "door_seals",
        "water_circulation_pump",
    ),
    _template(
        "ENG-PM-0005",
        "Cooking Kettles Maintenance",
        "electrical_supply_380",
        "switches_controls",
        "air_pressure_3_4",
        "steam_pressure_2_3",
        "temp_pressure_sensors",
        "machine_cleanliness",
        "hydraulic_system",
        "filters_strainers",
        "pot_condition",
        "valves_condition",
        "lid_condition",
        "stirrer_drive",
    ),
    _template(
        "ENG-PM-0006",
        "Bowl Cutter Maintenance",
        "electrical_supply_220",
        "switches_controls",
        "safety_features",
        "cutter_blade",
        "speed_regulator",
        "machine_cleanliness",
    ),
    _template(
        "ENG-PM-0007",
        "Meat Mincer Maintenance",
        "electrical_supply_220",
        "switches_controls",
        "motor_oil",
        "mincer_cutting_set",
        "bearings_condition",
        "machine_cleanliness",
    ),
    _template(
        "ENG-PM-0008",
        "Vegetable Peeler Maintenance",
        "electrical_supply_220",
        "switches_controls",
        "belt_condition",
        "machine_base",
        "safety_features",
        "machine_cleanliness",
    ),
    _template(
        "ENG-PM-0009",
        "Vegetable Blender Maintenance",
        "electrical_supply_220",
        "switches_controls",
        "motor_condition",
        "machine_base",
        "bearings_condition",
        "machine_cleanliness",
        "blender_blade",
    ),
    _template(
        "ENG-PM-0010",
        "Vegetable Slicer Maintenance",
        "electrical_supply_220",
        "switches_controls",
        "motor_condition",
        "slicer_disc",
        "bearings_condition",
        "machine_cleanliness",
    ),
    _template(
        "ENG-PM-0011",
        "Meat Cubing Maintenance",
        "electrical_supply_380",
        "switches_controls",
        "guide_rod_lubrication",
        "cubing_hydraulic_system",
        "motor_oil",
        "machine_cleanliness",
        "blade_clearance",
        "bearings_condition",
        "grid_blades_knife",
    ),
    _template(
        "ENG-PM-0012",
        "Air Operated Pump Maintenance",
        "air_pressure_2_4",
        "pump_connections",
        "pump_internals",
        "pump_exhaust",
        "machine_cleanliness",
    ),
    _template(
        "ENG-PM-0013",
        "Inline Metal Detector Maintenance",
        "air_pressure_2_4",
        "electrical_supply_220",
        "pipes_valves_air_connections",
        "metal_detector_sensitivity",
        "switches_controls",
        "machine_cleanliness",
    ),
    _template(
        "ENG-PM-0014",
        "Check-Weigher Maintenance",
        "electrical_supply_220",
        "air_pressure_2_4",
        "switches_controls",
        "belt_condition",
        "machine_base",
        "load_cell_sensitivity",
        "air_piston_condition",
        "machine_cleanliness",
    ),
    _template(
        "ENG-PM-0015",
        "Vacuum Packing Machine Maintenance",
        "electrical_supply_380",
        "vacuum_pump_oil",
        "sealing_components",
        "electromagnetic_valve",
        "switches_controls",
        "machine_cleanliness",
    ),
    _template(
        "ENG-PM-0016",
        "Hand Blender Maintenance",
        "electrical_supply_220",
        "hand_blender_set",
        "switches_controls",
        "machine_cleanliness",
    ),
    _template(
        "ENG-PM-0017",
        "Bin Lifter Maintenance",
        "electrical_supply_220",
        "chain_tension_lubrication",
        "sensors_condition",
        "switches_controls",
        "machine_cleanliness",
    ),
    _template(
        "ENG-PM-0018",
        "Conveyor Maintenance",
        "electrical_supply_220",
        "belt_bearings",
        "sensors_condition",
        "switches_controls",
        "machine_cleanliness",
    ),
    _template(
        "ENG-PM-0019",
        "Flattener Maintenance",
        "electrical_supply_220",
        "belt_bearings",
        "switches_controls",
        "machine_cleanliness",
    ),
    _template(
        "ENG-PM-0020",
        "Inject Printer Maintenance",
        "electrical_supply_220",
        "air_ink_filters",
        "sensors_condition",
        "pressure_pump",
        "print_head",
        "switches_controls",
        "machine_cleanliness",
    ),
    _template(
        "ENG-PM-0021",
        "Exhaust & Fresh Air Systems Maintenance",
        "electrical_supply_380",
        "fresh_exhaust_filters",
        "hood_lights",
        "mechanical_lubrication",
        "oil_collector_cleanliness",
    ),
)


def validate_seed_data():
    """Return human-readable structural errors for the static seed dataset."""
    errors = []
    codes = [row.get("code") for row in TEMPLATES]
    names = [row.get("template_name") for row in TEMPLATES]

    if len(TEMPLATES) != 21:
        errors.append(f"Expected 21 templates, found {len(TEMPLATES)}")
    if len(codes) != len(set(codes)):
        errors.append("Duplicate maintenance source codes")
    if len(names) != len(set(names)):
        errors.append("Duplicate maintenance template names")

    for template in TEMPLATES:
        keys = tuple(template.get("question_keys") or ())
        if len(keys) != len(set(keys)):
            errors.append(f"Duplicate questions in {template.get('template_name')}")
        missing = [key for key in keys if key not in QUESTION_LIBRARY]
        if missing:
            errors.append(f"Undefined questions in {template.get('template_name')}: {', '.join(missing)}")

    for key, spec in QUESTION_LIBRARY.items():
        if not str(spec.get("question") or "").strip():
            errors.append(f"Question text missing for {key}")
        if not str(spec.get("type") or "").strip():
            errors.append(f"Question type missing for {key}")
        if spec.get("type") == "Float":
            minimum = spec.get("answer_min_float")
            maximum = spec.get("answer_max_float")
            if minimum is not None and maximum is not None and minimum > maximum:
                errors.append(f"Invalid numeric range for {key}")

    return errors


# Non-destructive corrections for template settings found in the 2026-09-16
# exported test data review. These deliberately do not touch scheduling,
# questions, locations, or Asset assignment.
REVIEWED_TEMPLATE_REPAIRS = {
    "Vegetable Slicer Maintenance": {
        "department": "Maintenance - Taj",
    },
    "Cooking Kettles Maintenance": {
        "assignment_type": "Any User in Department",
        "assigned_user": None,
    },
    "Vacuum Packing Machine Maintenance": {
        "enable_worker_check": 0,
        "required_worker_count": 0,
        "default_worker_company": None,
        "default_worker_supplier": None,
        "worker_failure_reason_options": None,
    },
}
