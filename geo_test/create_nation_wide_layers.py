import json
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import MultiPolygon, Polygon


BASE_DIR = Path(__file__).resolve().parent.parent
NATION_WIDE_DIR = BASE_DIR / "nation_wide"
OUTPUT_PATH = NATION_WIDE_DIR / "nation_wide_geographies.geojson"

OUTPUT_CRS = "EPSG:4326"
AREA_CRS = "EPSG:2163"
SOURCE_KEY = "census_tiger_line_2025"
ACTIVE_STATE_CODES = {"NY", "NJ"}

INPUT_LAYERS = {
    "states": NATION_WIDE_DIR / "states" / "tl_2025_us_state.shp",
    "counties": NATION_WIDE_DIR / "counties" / "tl_2025_us_county.shp",
    "zipcodes": NATION_WIDE_DIR / "zipcodes" / "tl_2025_us_zcta520.shp",
    "urban_areas": NATION_WIDE_DIR / "urban_areas" / "tl_2025_us_uac20.shp",
}

GEOGRAPHY_TYPES = {
    "state": 1,
    "county": 2,
    "urban_area": 6,
    "zip_code": 8,
}

SUBTYPES = {
    "unknown": 0,
    "state": 40,
    "Urban Area": 41,
}

NORMALIZED_COLUMNS = [
    "source_key",
    "external_id",
    "name",
    "full_name",
    "geography_type",
    "subtype",
    "state_code",
    "properties_json",
    "is_active",
    "geometry",
]


def extract_polygons(geometry):
    if isinstance(geometry, Polygon):
        return [geometry]

    if isinstance(geometry, MultiPolygon):
        return list(geometry.geoms)

    if hasattr(geometry, "geoms"):
        polygons = []
        for part in geometry.geoms:
            polygons.extend(extract_polygons(part))
        return polygons

    return []


def to_multipolygon(geometry):
    polygons = extract_polygons(geometry)
    return MultiPolygon(polygons) if polygons else None


def clean_value(value):
    if isinstance(value, dict):
        return {key: clean_value(item) for key, item in value.items()}

    if isinstance(value, list):
        return [clean_value(item) for item in value]

    if pd.isna(value):
        return None

    if hasattr(value, "item"):
        return value.item()

    return value


def build_properties(row, fields):
    properties = {"source_layer": row["source_layer"]}

    for output_name, source_field in fields.items():
        if source_field in row:
            properties[output_name] = clean_value(row[source_field])

    if "intersecting_state_codes" in row:
        properties["intersecting_state_codes"] = clean_value(row["intersecting_state_codes"])

    return properties


def belongs_to_active_state(row):
    intersecting_state_codes = row.get("intersecting_state_codes")

    if isinstance(intersecting_state_codes, list) and intersecting_state_codes:
        return bool(ACTIVE_STATE_CODES.intersection(intersecting_state_codes))

    return row["state_code"] in ACTIVE_STATE_CODES


def clean_geometry(gdf):
    gdf = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty].copy()
    gdf.geometry = gdf.geometry.make_valid()
    gdf.geometry = gdf.geometry.apply(to_multipolygon)
    return gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty].copy()


def read_layer(label, path):
    print(f"reading {label} from {path}")

    if not path.exists():
        raise FileNotFoundError(f"Missing shapefile: {path}")

    gdf = gpd.read_file(path)
    print(f"{label} rows: {len(gdf)}")
    return clean_geometry(gdf.to_crs(OUTPUT_CRS))


def add_spatial_state_codes(features, states):
    features = features.reset_index(drop=True).copy()
    features["feature_index"] = features.index
    states_for_join = states[["STUSPS", "geometry"]].reset_index(drop=True).copy()

    features_projected = features[["feature_index", "geometry"]].to_crs(AREA_CRS)
    states_projected = states_for_join.to_crs(AREA_CRS)

    matches = gpd.sjoin(features_projected, states_projected, how="left", predicate="intersects")
    matches = matches[matches["index_right"].notna()].copy()

    if matches.empty:
        features["state_code"] = ""
        features["intersecting_state_codes"] = [[] for _ in range(len(features))]
        return features.drop(columns="feature_index")

    state_geometries = states_projected.geometry
    matches["overlap_area"] = [
        geometry.intersection(state_geometries.loc[state_index]).area
        for geometry, state_index in zip(matches.geometry, matches["index_right"])
    ]
    matches = matches[matches["overlap_area"] > 0].copy()

    if matches.empty:
        features["state_code"] = ""
        features["intersecting_state_codes"] = [[] for _ in range(len(features))]
        return features.drop(columns="feature_index")

    primary_states = (
        matches.sort_values(["feature_index", "overlap_area"], ascending=[True, False])
        .drop_duplicates("feature_index")
        .set_index("feature_index")["STUSPS"]
    )
    intersecting_states = matches.groupby("feature_index")["STUSPS"].agg(
        lambda codes: sorted(set(codes.dropna()))
    )

    features["state_code"] = features["feature_index"].map(primary_states).fillna("")
    features["intersecting_state_codes"] = features["feature_index"].map(intersecting_states)
    features["intersecting_state_codes"] = features["intersecting_state_codes"].apply(
        lambda codes: codes if isinstance(codes, list) else []
    )

    missing_count = (features["state_code"] == "").sum()
    if missing_count:
        print(f"warning: {missing_count} features did not intersect any state polygon")

    return features.drop(columns="feature_index")


def prepare_states(gdf):
    states = gdf.copy()
    states["source_layer"] = "states"
    states["source_key"] = SOURCE_KEY
    states["external_id"] = states["GEOID"]
    states["name"] = states["NAME"]
    states["full_name"] = states["NAME"]
    states["geography_type"] = GEOGRAPHY_TYPES["state"]
    states["subtype"] = SUBTYPES["state"]
    states["state_code"] = states["STUSPS"]
    states["properties_json"] = states.apply(
        lambda row: build_properties(
            row,
            {
                "statefp": "STATEFP",
                "statens": "STATENS",
                "geoidfq": "GEOIDFQ",
                "mtfcc": "MTFCC",
                "region": "REGION",
                "division": "DIVISION",
                "aland": "ALAND",
                "awater": "AWATER",
            },
        ),
        axis=1,
    )
    states["is_active"] = states.apply(belongs_to_active_state, axis=1)
    return states[NORMALIZED_COLUMNS]


def prepare_counties(gdf, statefp_to_code):
    counties = gdf.copy()
    counties["source_layer"] = "counties"
    counties["source_key"] = SOURCE_KEY
    counties["external_id"] = counties["GEOID"]
    counties["name"] = counties["NAME"]
    counties["full_name"] = counties["NAMELSAD"]
    counties["geography_type"] = GEOGRAPHY_TYPES["county"]
    counties["subtype"] = SUBTYPES["unknown"]
    counties["state_code"] = counties["STATEFP"].map(statefp_to_code).fillna("")
    counties["properties_json"] = counties.apply(
        lambda row: build_properties(
            row,
            {
                "statefp": "STATEFP",
                "countyfp": "COUNTYFP",
                "countyns": "COUNTYNS",
                "geoidfq": "GEOIDFQ",
                "mtfcc": "MTFCC",
                "lsad": "LSAD",
                "classfp": "CLASSFP",
                "aland": "ALAND",
                "awater": "AWATER",
            },
        ),
        axis=1,
    )
    counties["is_active"] = counties.apply(belongs_to_active_state, axis=1)
    return counties[NORMALIZED_COLUMNS]


def prepare_zipcodes(gdf, states):
    zipcodes = add_spatial_state_codes(gdf, states)
    zipcodes["source_layer"] = "zipcodes"
    zipcodes["source_key"] = SOURCE_KEY
    zipcodes["external_id"] = zipcodes["GEOID20"]
    zipcodes["name"] = zipcodes["ZCTA5CE20"]
    zipcodes["full_name"] = "ZIP Code Tabulation Area " + zipcodes["ZCTA5CE20"]
    zipcodes["geography_type"] = GEOGRAPHY_TYPES["zip_code"]
    zipcodes["subtype"] = SUBTYPES["unknown"]
    zipcodes["properties_json"] = zipcodes.apply(
        lambda row: build_properties(
            row,
            {
                "zcta5ce": "ZCTA5CE20",
                "geoidfq": "GEOIDFQ20",
                "mtfcc": "MTFCC20",
                "classfp": "CLASSFP20",
                "aland": "ALAND20",
                "awater": "AWATER20",
            },
        ),
        axis=1,
    )
    zipcodes["is_active"] = zipcodes.apply(belongs_to_active_state, axis=1)
    return zipcodes[NORMALIZED_COLUMNS]


def prepare_urban_areas(gdf, states):
    urban_areas = add_spatial_state_codes(gdf, states)
    urban_areas["source_layer"] = "urban_areas"
    urban_areas["source_key"] = SOURCE_KEY
    urban_areas["external_id"] = urban_areas["GEOID20"]
    urban_areas["name"] = urban_areas["NAME20"]
    urban_areas["full_name"] = urban_areas["NAMELSAD20"]
    urban_areas["geography_type"] = GEOGRAPHY_TYPES["urban_area"]
    urban_areas["subtype"] = SUBTYPES["Urban Area"]
    urban_areas["properties_json"] = urban_areas.apply(
        lambda row: build_properties(
            row,
            {
                "uace": "UACE20",
                "geoidfq": "GEOIDFQ20",
                "mtfcc": "MTFCC20",
                "lsad": "LSAD20",
                "aland": "ALAND20",
                "awater": "AWATER20",
            },
        ),
        axis=1,
    )
    urban_areas["is_active"] = urban_areas.apply(belongs_to_active_state, axis=1)
    return urban_areas[NORMALIZED_COLUMNS]


def write_geojson(output_path, layers):
    total_features = 0
    first_feature = True

    with output_path.open("w") as output_file:
        output_file.write('{"type":"FeatureCollection","features":[\n')

        for layer in layers:
            for feature in layer.iterfeatures(na="null"):
                if not first_feature:
                    output_file.write(",\n")

                json.dump(feature, output_file)
                first_feature = False
                total_features += 1

        output_file.write("\n]}\n")

    return total_features


def main():
    layers = {label: read_layer(label, path) for label, path in INPUT_LAYERS.items()}

    states_source = layers["states"]
    statefp_to_code = dict(zip(states_source["STATEFP"], states_source["STUSPS"]))

    print("\npreparing normalized layers...")
    states = prepare_states(states_source)
    counties = prepare_counties(layers["counties"], statefp_to_code)
    zipcodes = prepare_zipcodes(layers["zipcodes"], states_source)
    urban_areas = prepare_urban_areas(layers["urban_areas"], states_source)

    print("\nmerge inputs:")
    print(f"states: {len(states)}")
    print(f"counties: {len(counties)}")
    print(f"zipcodes: {len(zipcodes)}")
    print(f"urban_areas: {len(urban_areas)}")

    total_features = write_geojson(OUTPUT_PATH, [states, counties, zipcodes, urban_areas])

    print("\ncreated nationwide combined GeoJSON:")
    print(OUTPUT_PATH)
    print(f"total output features: {total_features}")


if __name__ == "__main__":
    main()
