"""Croissant metadata validation using mlcroissant."""
import json
import traceback
import mlcroissant as mlc


def validate(json_string: str) -> list:
    """Validate JSON string. Returns list of (stage, passed, message, status) tuples."""
    results = []

    # Stage 1: JSON
    try:
        json_data = json.loads(json_string)
        results.append(("JSON Format", True, "Valid JSON.", "pass"))
    except json.JSONDecodeError as e:
        results.append(("JSON Format", False, f"Invalid JSON: {e}", "error"))
        return results

    # Stage 2: Croissant schema
    try:
        dataset = mlc.Dataset(jsonld=json_data)
        results.append(("Croissant Schema", True, "Passes Croissant validation.", "pass"))
    except Exception as e:
        results.append(("Croissant Schema", False, f"Failed: {e}\n{traceback.format_exc()}", "error"))
        return results

    # Stage 3: Record generation
    try:
        record_sets = dataset.metadata.record_sets
        if not record_sets:
            results.append(("Records", True, "No record sets to validate.", "pass"))
            return results

        for rs in record_sets:
            try:
                for i, _ in enumerate(dataset.records(record_set=rs.uuid)):
                    if i == 0:
                        break
                results.append(("Records", True, f"Record set '{rs.uuid}' OK.", "pass"))
            except Exception as e:
                results.append(("Records", False, f"Record set '{rs.uuid}' failed: {e}", "warning"))
                return results
    except Exception as e:
        results.append(("Records", False, f"Unexpected error: {e}", "error"))

    return results
