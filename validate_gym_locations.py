import csv
import re
from collections import defaultdict
from pathlib import Path


DATASETS = [
    ("PureGym", Path("puregym_locations.csv"), Path("puregym_locations_geocoded.csv")),
    ("The Gym Group", Path("gymgroup_locations.csv"), Path("gymgroup_locations_geocoded.csv")),
]
REPORT_PATH = Path("gym_validation_report.md")


def normalize_address(address: str) -> str:
    lowered = address.lower().strip()
    lowered = re.sub(r"[^a-z0-9]+", " ", lowered)
    return re.sub(r"\s+", " ", lowered).strip()


def load_csv(path: Path):
    with path.open(mode="r", encoding="utf-8") as file_handle:
        return list(csv.DictReader(file_handle))


def build_geocode_lookup(rows):
    geocoded_rows = defaultdict(list)
    for row in rows:
        geocoded_rows[(row["office_name"], row["gym_name"])].append(row)
    return geocoded_rows


def audit_dataset(brand: str, source_path: Path, geocoded_path: Path):
    source_rows = load_csv(source_path)
    geocode_lookup = build_geocode_lookup(load_csv(geocoded_path)) if geocoded_path.exists() else {}

    grouped = defaultdict(list)
    for row in source_rows:
        grouped[row["gym_name"]].append(row)

    flagged = []
    for gym_name, rows in sorted(grouped.items()):
        normalized_addresses = defaultdict(list)
        for row in rows:
            normalized_addresses[normalize_address(row["gym_address"])].append(row)

        if len(normalized_addresses) <= 1:
            continue

        variants = []
        for variant_rows in normalized_addresses.values():
            sample = variant_rows[0]
            offices = sorted({row["office_name"] for row in variant_rows})
            geocoded_matches = []
            for row in variant_rows:
                geocoded_matches.extend(geocode_lookup.get((row["office_name"], row["gym_name"]), []))

            coordinates = sorted(
                {
                    (match.get("gym_latitude", ""), match.get("gym_longitude", ""))
                    for match in geocoded_matches
                    if match.get("gym_latitude") and match.get("gym_longitude")
                }
            )
            variants.append(
                {
                    "address": sample["gym_address"],
                    "offices": offices,
                    "coordinates": coordinates,
                    "rows": len(variant_rows),
                }
            )

        flagged.append(
            {
                "brand": brand,
                "gym_name": gym_name,
                "variant_count": len(variants),
                "variants": sorted(variants, key=lambda item: (-item["rows"], item["address"])),
            }
        )

    return {"brand": brand, "row_count": len(source_rows), "unique_gyms": len(grouped), "flagged": flagged}


def render_report(audits):
    lines = ["# Gym Location Validation Report", ""]
    for audit in audits:
        lines.append(f"## {audit['brand']}")
        lines.append("")
        lines.append(f"- Rows audited: {audit['row_count']}")
        lines.append(f"- Unique gym names: {audit['unique_gyms']}")
        lines.append(f"- Gym names with multiple address variants: {len(audit['flagged'])}")
        lines.append("")

        if not audit["flagged"]:
            lines.append("No inconsistent gym names found.")
            lines.append("")
            continue

        for item in audit["flagged"]:
            lines.append(f"### {item['gym_name']}")
            lines.append("")
            lines.append(f"Address variants found: {item['variant_count']}")
            lines.append("")
            for variant in item["variants"]:
                offices = ", ".join(variant["offices"])
                lines.append(f"- Address: {variant['address']}")
                lines.append(f"  Rows: {variant['rows']}")
                lines.append(f"  Offices: {offices}")
                if variant["coordinates"]:
                    coordinate_text = ", ".join(f"({lat}, {lon})" for lat, lon in variant["coordinates"])
                    lines.append(f"  Geocoded coordinates: {coordinate_text}")
                else:
                    lines.append("  Geocoded coordinates: none")
                lines.append("")

    REPORT_PATH.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def main():
    audits = [audit_dataset(brand, source_path, geocoded_path) for brand, source_path, geocoded_path in DATASETS]
    render_report(audits)

    for audit in audits:
        print(
            f"{audit['brand']}: {len(audit['flagged'])} inconsistent gym names out of {audit['unique_gyms']} unique gyms"
        )
    print(f"Validation report written to {REPORT_PATH}")


if __name__ == "__main__":
    main()