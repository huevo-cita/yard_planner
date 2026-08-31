"""Shared engine for the yard survey and design system.

Every module here is yard-agnostic. All per-yard facts live in the yard's own
JSON files under ~/personal/garden/<slug>/, and nothing in this package should
ever hard-code a location, a dimension, or a plant.

    yards         locating yards, loading and saving their files
    solar         solar position, day length, solar-to-clock conversion
    siteschema    the site.json shape, provenance tags, validation, migration
    sunmodel      the year-round shade model
    drawsite      architectural plan, elevation and section drawings
    drawbeds      to-scale planting maps
    parcel        address to lot geometry and neighbouring buildings
    lidar         USGS 3DEP point clouds to measured tree and building heights
    photomeasure  measuring from photographs with a known scale reference
    soil          USDA soil survey lookup
    climate       hardiness zone, frost dates, monthly normals
    gaps          what is missing, ranked by how much it changes the answer
    doubts        the doubts that would change the answer, and the gate on them
    bom           bill of materials, netted against what is already on site
    builddoc      markdown to docx for anything that needs printing
"""

__all__ = [
    "yards", "solar", "siteschema", "sunmodel", "drawsite", "drawbeds",
    "parcel", "lidar", "photomeasure", "soil", "climate", "gaps", "doubts",
    "bom", "builddoc",
]
