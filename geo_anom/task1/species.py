"""
Registry animal_type -> species group.

The MDE registry's animal_type values are raw Socrata column names
("chickens_not_laying_hens", "swine_55_lbs", ...). Every output of this
pipeline carries both the raw value and one of the groups below, so the KMZ
and the supply step agree on what a building is.

Species comes from the registry permit the tile was pulled for -- the
detector itself does not classify species. A building in a "dairy" tile is a
building near a dairy permit, not a building the model recognised as a
dairy barn.
"""

from __future__ import annotations

GROUP_BY_ANIMAL_TYPE = {
    "chickens_not_laying_hens": "broiler",
    "laying_hens_dry_manure": "poultry_other",
    "turkeys": "poultry_other",
    "ducks_liquid_manure": "poultry_other",
    "swine_55_lbs": "swine",
    "cattle_includes_heifers": "beef",
    "dairy_cattle": "dairy",
    "horses": "excluded",  # not a Task 1 target; known racetrack false positives
}

# group -> (label, RGB). Colors match scripts/build_field_kmz.py so the two
# KMZs read the same way side by side.
GROUPS = {
    "broiler":       ("Poultry house (broiler)", (44, 140, 60)),
    "poultry_other": ("Layers / turkeys / ducks", (27, 163, 156)),
    "swine":         ("Swine barn", (214, 64, 159)),
    "beef":          ("Beef barn", (139, 90, 43)),
    "dairy":         ("Dairy barn", (47, 111, 222)),
    "unknown":       ("No animal type on file", (122, 122, 122)),
    "excluded":      ("Excluded (not a Task 1 species)", (192, 57, 43)),
}


def species_group(animal_type: str | None) -> str:
    if not animal_type:
        return "unknown"
    return GROUP_BY_ANIMAL_TYPE.get(animal_type, "unknown")
