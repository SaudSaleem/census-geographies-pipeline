from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import MultiPolygon, Polygon


BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = Path(__file__).resolve().parent

STATE_INPUT_LAYERS = {
    "NY": {
        "places": BASE_DIR / "NY" / "places" / "tl_2025_36_place.shp",
        "county_subdivisions": BASE_DIR / "NY" / "county_subdivision" / "tl_2025_36_cousub.shp",
        "school_districts": BASE_DIR / "NY" / "school_districts" / "tl_2025_36_unsd.shp",
    },
    "NJ": {
        "places": BASE_DIR / "NJ" / "places" / "tl_2025_34_place.shp",
        "county_subdivisions": BASE_DIR / "NJ" / "county_subdivision" / "tl_2025_34_cousub.shp",
        "school_districts": BASE_DIR / "NJ" / "school_districts" / "tl_2025_34_unsd.shp",
    },
}

OUTPUT_CRS = "EPSG:4326"
SOURCE_KEY = "census_tiger_line_2025"

GEOGRAPHY_TYPES = {
    "county": 2,
    "county_subdivision": 3,
    "place": 4,
    "school_district": 5,
    "neighborhood": 7,
    "zip_code": 8,
}

SUBTYPES = {
    "unknown": 0,
    "city": 10,
    "village": 11,
    "CDP": 12,
    "borough": 13,
    "town": 20,
    "Reservation": 21,
    "UT": 22,
    "defined": 23,
    "Central School District": 30,
    "City School District": 31,
    "Union Free School District": 32,
    "Common School District": 33,
    "School District": 34,
    "neighborhood": 42,
    "Other": 999,
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


def print_layer_info(label, gdf):
    print(f"\n{label}")
    print(f"rows: {len(gdf)}")
    print(f"crs: {gdf.crs}")
    print(f"columns: {list(gdf.columns)}")
    print(gdf.drop(columns="geometry").head(5).to_string(index=False))


def print_geometric_names(label, gdf):
    print(f"\n{label} geometry/category names:")

    if "NAMELSAD" in gdf.columns:
        type_names = gdf["NAMELSAD"].str.split().str[-1]
        print(type_names.value_counts().sort_index().to_string())
        print("all type names:")
        print(", ".join(sorted(type_names.dropna().unique())))
        return

    if label == "school_districts":
        district_types = gdf["NAME"].apply(get_school_district_type)
        print(district_types.value_counts().sort_index().to_string())
        print("all district type names:")
        print(", ".join(sorted(district_types.dropna().unique())))
        return

    print("No type/name column found for this layer.")


def get_school_district_type(name):
    if pd.isna(name):
        return None

    district_type_patterns = [
        "Central High School District",
        "Union Free School District",
        "Central School District",
        "Common School District",
        "City School District",
        "School District",
    ]

    for district_type in district_type_patterns:
        if name.endswith(district_type):
            return district_type

    return "Other"


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

    return properties


def clean_geometry(gdf):
    gdf = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty].copy()
    gdf.geometry = gdf.geometry.make_valid()
    gdf.geometry = gdf.geometry.apply(to_multipolygon)
    return gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty].copy()


def read_layer(state_code, label, path):
    print(f"reading {state_code} {label} from {path}")

    if not path.exists():
        raise FileNotFoundError(f"Missing {state_code} {label} shapefile: {path}")

    gdf = gpd.read_file(path)
    print_layer_info(f"{state_code} {label}", gdf)
    print_geometric_names(label, gdf)
    return clean_geometry(gdf.to_crs(OUTPUT_CRS))


def prepare_places(gdf, state_code):
    places = gdf.copy()
    places["source_layer"] = "places"
    places["source_key"] = SOURCE_KEY
    places["external_id"] = places["GEOID"]
    places["name"] = places["NAME"]
    places["full_name"] = places["NAMELSAD"]
    places["geography_type"] = GEOGRAPHY_TYPES["place"]
    places["subtype"] = places["NAMELSAD"].str.split().str[-1].map(SUBTYPES)
    places["state_code"] = state_code
    places["properties_json"] = places.apply(
        lambda row: build_properties(
            row,
            {
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
    places["is_active"] = True
    return places[NORMALIZED_COLUMNS]


def prepare_county_subdivisions(gdf, state_code):
    county_subdivisions = gdf.copy()
    county_subdivisions["source_layer_subtype"] = county_subdivisions["NAMELSAD"].str.split().str[-1]
    county_subdivisions = county_subdivisions[county_subdivisions["source_layer_subtype"] != "city"].copy()
    county_subdivisions["source_layer"] = "county_subdivisions"
    county_subdivisions["source_key"] = SOURCE_KEY
    county_subdivisions["external_id"] = county_subdivisions["GEOID"]
    county_subdivisions["name"] = county_subdivisions["NAME"]
    county_subdivisions["full_name"] = county_subdivisions["NAMELSAD"]
    county_subdivisions["geography_type"] = GEOGRAPHY_TYPES["county_subdivision"]
    county_subdivisions["subtype"] = county_subdivisions["source_layer_subtype"].map(SUBTYPES)
    county_subdivisions["state_code"] = state_code
    county_subdivisions["properties_json"] = county_subdivisions.apply(
        lambda row: build_properties(
            row,
            {
                "geoidfq": "GEOIDFQ",
                "mtfcc": "MTFCC",
                "lsad": "LSAD",
                "classfp": "CLASSFP",
                "countyfp": "COUNTYFP",
                "aland": "ALAND",
                "awater": "AWATER",
            },
        ),
        axis=1,
    )
    county_subdivisions["is_active"] = True
    return county_subdivisions[NORMALIZED_COLUMNS]


def prepare_school_districts(gdf, state_code):
    school_districts = gdf.copy()
    school_districts["source_layer_subtype"] = school_districts["NAME"].apply(get_school_district_type)
    school_districts["source_layer"] = "school_districts"
    school_districts["source_key"] = SOURCE_KEY
    school_districts["external_id"] = school_districts["GEOID"]
    school_districts["name"] = school_districts["NAME"]
    school_districts["full_name"] = school_districts["NAME"]
    school_districts["geography_type"] = GEOGRAPHY_TYPES["school_district"]
    school_districts["subtype"] = school_districts["source_layer_subtype"].map(SUBTYPES)
    school_districts["state_code"] = state_code
    school_districts["properties_json"] = school_districts.apply(
        lambda row: build_properties(
            row,
            {
                "geoidfq": "GEOIDFQ",
                "mtfcc": "MTFCC",
                "lsad": "LSAD",
                "lea": "UNSDLEA",
                "low_grade": "LOGRADE",
                "high_grade": "HIGRADE",
                "aland": "ALAND",
                "awater": "AWATER",
            },
        ),
        axis=1,
    )
    school_districts["is_active"] = True
    return school_districts[NORMALIZED_COLUMNS]


prepared_state_layers = []

for state_code, input_layers in STATE_INPUT_LAYERS.items():
    layers = {
        label: read_layer(state_code, label, path)
        for label, path in input_layers.items()
    }

    print(f"\npreparing {state_code} layers for merge...")
    places = prepare_places(layers["places"], state_code)
    county_subdivisions = prepare_county_subdivisions(
        layers["county_subdivisions"],
        state_code,
    )
    school_districts = prepare_school_districts(layers["school_districts"], state_code)

    print(f"\n{state_code} merge inputs after filtering:")
    print(f"places: {len(places)}")
    print(f"county_subdivisions without city rows: {len(county_subdivisions)}")
    print(f"school_districts: {len(school_districts)}")

    prepared_state_layers.append(
        {
            "state_code": state_code,
            "places": places,
            "county_subdivisions": county_subdivisions,
            "school_districts": school_districts,
        }
    )

combined = gpd.GeoDataFrame(
    pd.concat(
        [
            state_layers[layer_name]
            for state_layers in prepared_state_layers
            for layer_name in ("places", "county_subdivisions", "school_districts")
        ],
        ignore_index=True,
    ),
    crs=OUTPUT_CRS,
)
combined = clean_geometry(combined)

output_path = OUTPUT_DIR / "state_based_geographies.geojson"
combined.to_file(output_path, driver="GeoJSON")

print("\ncreated merged GeoJSON:")
print(output_path)
print(f"total output features: {len(combined)}")
print("\ngeography type counts:")
print(combined["geography_type"].value_counts().sort_index())
print("\nstate counts:")
print(combined["state_code"].value_counts().sort_index())
