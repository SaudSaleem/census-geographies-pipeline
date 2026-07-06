import json
from pathlib import Path

from django.contrib.gis.geos import GEOSGeometry, MultiPolygon, Polygon
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import DataSource, GeoFeature

DEFAULT_GEOJSON_PATH = Path("geo_test/state_based_geographies.geojson")


def parse_shape(geometry):
    shape = GEOSGeometry(json.dumps(geometry), srid=4326)

    if isinstance(shape, Polygon):
        return MultiPolygon(shape, srid=4326)

    if isinstance(shape, MultiPolygon):
        return shape

    raise ValueError(f"Expected Polygon or MultiPolygon, got {shape.geom_type}")


class Command(BaseCommand):
    help = "Import normalized geographic boundary features from GeoJSON."

    def add_arguments(self, parser):
        parser.add_argument(
            "--geojson-path",
            default=str(DEFAULT_GEOJSON_PATH),
            help="Path to normalized GeoJSON file.",
        )
        parser.add_argument(
            "--source-name",
            default="Census TIGER/Line",
            help="Data source display name.",
        )
        parser.add_argument(
            "--source-url",
            default="https://www.census.gov/",
            help="Data source URL.",
        )
        parser.add_argument(
            "--source-version",
            default="2025",
            help="Data source version/year.",
        )
        parser.add_argument(
            "--source-license",
            default="Public domain",
            help="Data source license.",
        )
        parser.add_argument(
            "--deactivate-missing",
            action="store_true",
            help="Deactivate existing source features not present in this import file.",
        )

    def handle(self, *args, **options):
        geojson_path = Path(options["geojson_path"])

        if not geojson_path.exists():
            raise CommandError(f"GeoJSON file does not exist: {geojson_path}")

        with geojson_path.open() as file:
            geojson = json.load(file)

        features = geojson.get("features", [])
        if not features:
            raise CommandError(f"No features found in: {geojson_path}")

        source, _ = DataSource.objects.get_or_create(
            name=options["source_name"],
            version=options["source_version"],
            defaults={
                "source_url": options["source_url"],
                "license": options["source_license"],
            },
        )

        imported_keys = set()
        created_count = 0
        updated_count = 0

        with transaction.atomic():
            for feature in features:
                properties = feature.get("properties") or {}
                shape = parse_shape(feature.get("geometry"))

                external_id = properties["external_id"]
                geography_type = properties["geography_type"]
                imported_keys.add((external_id, geography_type))

                _, created = GeoFeature.objects.update_or_create(
                    source=source,
                    external_id=external_id,
                    geography_type=geography_type,
                    defaults={
                        "name": properties["name"],
                        "full_name": properties.get("full_name") or "",
                        "subtype": properties.get("subtype") or GeoFeature.Subtype.UNKNOWN,
                        "state_code": properties.get("state_code") or "",
                        "shape": shape,
                        "properties_json": properties.get("properties_json") or {},
                        "is_active": properties.get("is_active", True),
                    },
                )

                if created:
                    created_count += 1
                else:
                    updated_count += 1

            deactivated_count = 0
            if options["deactivate_missing"]:
                existing_features = GeoFeature.objects.filter(source=source, is_active=True)
                for geo_feature in existing_features.only("external_id", "geography_type"):
                    key = (geo_feature.external_id, geo_feature.geography_type)
                    if key not in imported_keys:
                        geo_feature.is_active = False
                        geo_feature.save(update_fields=["is_active", "updated_at"])
                        deactivated_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                "Geo import complete: "
                f"{created_count} created, "
                f"{updated_count} updated, "
                f"{deactivated_count} deactivated."
            )
        )
