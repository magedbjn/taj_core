NUMERIC_SNAPSHOT_FIELDS = frozenset(
    {
        "weight",
        "total_weight_cook",
        "salt",
        "brix",
        "ph",
        "viscosity",
        "rpm",
        "temperature",
    }
)


def normalize_snapshot_value(fieldname, value):
    if fieldname in NUMERIC_SNAPSHOT_FIELDS:
        if value in (None, ""):
            return 0.0
        return float(value)

    return "" if value is None else str(value)


def snapshot_values_equal(fieldname, current, previous):
    return normalize_snapshot_value(fieldname, current) == normalize_snapshot_value(
        fieldname, previous
    )
