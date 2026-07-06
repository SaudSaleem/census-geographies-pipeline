# City Geographies Pipeline

Builds normalized GeoJSON boundary datasets from Census TIGER/Line shapefiles. The pipeline combines nationwide geography layers with NY/NJ state-specific layers into one final `geographies.geojson` file.

## Data Sources

The raw shapefile folders are intentionally ignored by Git because they are large generated/source-data assets:

- `NY/`
- `NJ/`
- `nation_wide/`

Expected state-based inputs:

- `NY/places/tl_2025_36_place.shp`
- `NY/county_subdivision/tl_2025_36_cousub.shp`
- `NY/school_districts/tl_2025_36_unsd.shp`
- `NJ/places/tl_2025_34_place.shp`
- `NJ/county_subdivision/tl_2025_34_cousub.shp`
- `NJ/school_districts/tl_2025_34_unsd.shp`

Expected nationwide inputs:

- `nation_wide/states/tl_2025_us_state.shp`
- `nation_wide/counties/tl_2025_us_county.shp`
- `nation_wide/zipcodes/tl_2025_us_zcta520.shp`
- `nation_wide/urban_areas/tl_2025_us_uac20.shp`

## Scripts

- `geo_test/create_state_based_layers.py` creates `geo_test/state_based_geographies.geojson` from NY/NJ places, county subdivisions, and school districts.
- `geo_test/create_nation_wide_layers.py` creates `nation_wide/nation_wide_geographies.geojson` from states, counties, ZIP codes, and urban areas.
- `geo_test/merge_geographies.py` merges both generated GeoJSON files into root `geographies.geojson`.

## Run Order

```bash
python3 geo_test/create_state_based_layers.py
python3 geo_test/create_nation_wide_layers.py
python3 geo_test/merge_geographies.py
```

The final `geographies.geojson` output is also ignored by Git.
