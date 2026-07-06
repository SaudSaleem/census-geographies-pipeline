from pathlib import Path

import geopandas as gpd
import pandas as pd


BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_CRS = "EPSG:4326"

INPUT_FILES = [
    BASE_DIR / "geo_test" / "state_based_geographies.geojson",
    BASE_DIR / "nation_wide" / "nation_wide_geographies.geojson",
]
OUTPUT_PATH = BASE_DIR / "geographies.geojson"

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


def read_geographies(path):
    print(f"reading {path}")

    if not path.exists():
        raise FileNotFoundError(f"Missing input GeoJSON: {path}")

    gdf = gpd.read_file(path)
    missing_columns = set(NORMALIZED_COLUMNS) - set(gdf.columns)

    if missing_columns:
        missing = ", ".join(sorted(missing_columns))
        raise ValueError(f"{path} is missing required columns: {missing}")

    if gdf.crs is None:
        gdf = gdf.set_crs(OUTPUT_CRS)
    else:
        gdf = gdf.to_crs(OUTPUT_CRS)

    print(f"rows: {len(gdf)}")
    return gdf[NORMALIZED_COLUMNS]


geographies = [read_geographies(path) for path in INPUT_FILES]
combined = gpd.GeoDataFrame(
    pd.concat(geographies, ignore_index=True),
    crs=OUTPUT_CRS,
)

combined.to_file(OUTPUT_PATH, driver="GeoJSON")

print("\ncreated merged GeoJSON:")
print(OUTPUT_PATH)
print(f"total output features: {len(combined)}")
print("\ngeography type counts:")
print(combined["geography_type"].value_counts().sort_index())
print("\nstate counts:")
print(combined["state_code"].value_counts().sort_index())
