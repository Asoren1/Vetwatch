"""County centroids for the map view.

Each entry: ("ST", "county_name_lowercase") -> (latitude, longitude)

Sources: US Census TIGER county shapefiles, centroids computed once.
This is a *curated* set — counties most likely to appear in alerts from
our current sources (TAHC NWS/HPAI counties, key population counties
across AZ/CA/NM/NV/TX, the Pima reference county, the LA/San Mateo
counties where the H5 marine outbreak occurred).

To add a county: look up its centroid on Wikipedia (the "Coordinates"
field in the infobox) or any GIS source, and add a row below. Keep
the county name lowercase.

If a county appears in an alert but isn't in this table, the map falls
back to the state centroid and the alert gets a "(state-level)" marker.
"""

# State centroids — used as fallback when county isn't in the table below
STATE_CENTROIDS: dict[str, tuple[float, float]] = {
    "AZ": (34.17, -111.93),
    "CA": (36.78, -119.42),
    "NM": (34.41, -106.11),
    "NV": (38.81, -116.42),
    "TX": (31.05, -97.56),
}

# Bounding boxes for fitting the map to a state (south, west, north, east)
STATE_BOUNDS: dict[str, tuple[float, float, float, float]] = {
    "AZ": (31.33, -114.82, 37.00, -109.05),
    "CA": (32.53, -124.41, 42.01, -114.13),
    "NM": (31.33, -109.05, 37.00, -103.00),
    "NV": (35.00, -120.01, 42.00, -114.04),
    "TX": (25.84, -106.65, 36.50, -93.51),
}

# Format: (state_code, county_name_lower) -> (lat, lng)
COUNTY_CENTROIDS: dict[tuple[str, str], tuple[float, float]] = {
    # --- Texas (TAHC alert hotspots and major population centers) ---
    ("TX", "anderson"):     (31.81, -95.65),
    ("TX", "brazoria"):     (29.17, -95.43),
    ("TX", "briscoe"):      (34.53, -101.21),
    ("TX", "brooks"):       (27.03, -98.22),
    ("TX", "brown"):        (31.77, -98.99),
    ("TX", "cherokee"):     (31.84, -95.16),
    ("TX", "crockett"):     (30.72, -101.41),
    ("TX", "dallas"):       (32.78, -96.80),
    ("TX", "denton"):       (33.21, -97.12),
    ("TX", "duval"):        (27.68, -98.51),
    ("TX", "edwards"):      (29.99, -100.30),
    ("TX", "ellis"):        (32.34, -96.79),
    ("TX", "frio"):         (28.86, -99.10),
    ("TX", "gillespie"):    (30.31, -98.95),
    ("TX", "gonzales"):     (29.46, -97.49),
    ("TX", "hamilton"):     (31.71, -98.11),
    ("TX", "hardeman"):     (34.29, -99.74),
    ("TX", "harris"):       (29.86, -95.39),
    ("TX", "hood"):         (32.43, -97.83),
    ("TX", "hunt"):         (33.13, -96.08),
    ("TX", "kaufman"):      (32.60, -96.29),
    ("TX", "kerr"):         (30.06, -99.35),
    ("TX", "kimble"):       (30.49, -99.74),
    ("TX", "la salle"):     (28.35, -99.10),
    ("TX", "lamb"):         (34.06, -102.35),
    ("TX", "limestone"):    (31.55, -96.58),
    ("TX", "lubbock"):      (33.61, -101.82),
    ("TX", "mason"):        (30.72, -99.22),
    ("TX", "matagorda"):    (28.79, -95.99),
    ("TX", "maverick"):     (28.74, -100.31),
    ("TX", "midland"):      (31.87, -102.03),
    ("TX", "moore"):        (35.83, -101.89),
    ("TX", "parker"):       (32.78, -97.81),
    ("TX", "real"):         (29.83, -99.82),
    ("TX", "schleicher"):   (30.90, -100.54),
    ("TX", "shackelford"): (32.73, -99.35),
    ("TX", "shelby"):       (31.79, -94.13),
    ("TX", "sutton"):       (30.50, -100.54),
    ("TX", "tarrant"):      (32.78, -97.29),
    ("TX", "tom green"):    (31.40, -100.46),
    ("TX", "travis"):       (30.27, -97.74),
    ("TX", "trinity"):      (31.10, -95.13),
    ("TX", "uvalde"):       (29.36, -99.91),
    ("TX", "val verde"):    (29.89, -101.15),
    ("TX", "washington"):   (30.21, -96.40),
    ("TX", "webb"):         (27.76, -99.34),
    ("TX", "wichita"):      (33.99, -98.70),
    ("TX", "zavala"):       (28.86, -99.76),

    # --- Arizona ---
    ("AZ", "apache"):       (35.39, -109.49),
    ("AZ", "cochise"):      (31.88, -109.75),
    ("AZ", "coconino"):     (35.84, -111.77),
    ("AZ", "gila"):         (33.80, -110.81),
    ("AZ", "graham"):       (32.93, -109.89),
    ("AZ", "greenlee"):     (33.22, -109.24),
    ("AZ", "la paz"):       (33.73, -113.93),
    ("AZ", "maricopa"):     (33.35, -112.49),
    ("AZ", "mohave"):       (35.70, -113.75),
    ("AZ", "navajo"):       (35.40, -110.32),
    ("AZ", "pima"):         (32.10, -111.79),
    ("AZ", "pinal"):        (32.90, -111.34),
    ("AZ", "santa cruz"):   (31.52, -110.85),
    ("AZ", "yavapai"):      (34.60, -112.55),
    ("AZ", "yuma"):         (32.77, -113.91),

    # --- California (population centers + H5 marine outbreak counties) ---
    ("CA", "alameda"):      (37.65, -121.91),
    ("CA", "contra costa"): (37.92, -121.95),
    ("CA", "fresno"):       (36.76, -119.65),
    ("CA", "kings"):        (36.07, -119.82),
    ("CA", "los angeles"):  (34.20, -118.26),
    ("CA", "monterey"):     (36.24, -121.31),
    ("CA", "orange"):       (33.70, -117.76),
    ("CA", "riverside"):    (33.74, -115.99),
    ("CA", "sacramento"):   (38.45, -121.34),
    ("CA", "san bernardino"): (34.86, -116.18),
    ("CA", "san diego"):    (33.03, -116.74),
    ("CA", "san francisco"): (37.77, -122.42),
    ("CA", "san luis obispo"): (35.39, -120.45),
    ("CA", "san mateo"):    (37.42, -122.36),
    ("CA", "santa barbara"): (34.54, -120.04),
    ("CA", "santa clara"):  (37.23, -121.69),
    ("CA", "santa cruz"):   (37.05, -122.01),
    ("CA", "ventura"):      (34.36, -119.13),

    # --- New Mexico ---
    ("NM", "bernalillo"):   (35.05, -106.67),
    ("NM", "chaves"):       (33.36, -104.47),
    ("NM", "dona ana"):     (32.35, -106.83),
    ("NM", "lea"):          (32.79, -103.42),
    ("NM", "mckinley"):     (35.58, -108.27),
    ("NM", "san juan"):     (36.51, -108.32),
    ("NM", "santa fe"):     (35.50, -105.97),

    # --- Nevada ---
    ("NV", "carson city"):  (39.16, -119.74),
    ("NV", "clark"):        (36.21, -115.01),
    ("NV", "douglas"):      (38.91, -119.62),
    ("NV", "elko"):         (41.14, -115.36),
    ("NV", "washoe"):       (40.66, -119.65),
    ("NV", "lyon"):         (39.04, -119.18),
    ("NV", "nye"):          (38.04, -116.47),
}


def resolve_coordinates(state: str | None, county: str | None) -> tuple[float, float] | None:
    """Return (lat, lng) for an alert, or None for federal/no-location items.

    Order of resolution:
    1. (state, county) exact match
    2. (state) centroid fallback
    3. None — caller decides what to do (typically: don't plot)
    """
    if not state:
        return None
    if county:
        key = (state, county.lower().strip())
        if key in COUNTY_CENTROIDS:
            return COUNTY_CENTROIDS[key]
    return STATE_CENTROIDS.get(state)
