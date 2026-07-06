from django.contrib.gis.db import models

class DataSource(models.Model):
    name = models.CharField(max_length=255)
    source_url = models.URLField(max_length=1000, blank=True)
    version = models.CharField(max_length=64, blank=True)
    license = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} {self.version}".strip()


class GeoFeature(models.Model):
    class GeographyType(models.IntegerChoices):
        UNKNOWN = 0, "Unknown"
        STATE = 1, "State"
        COUNTY = 2, "County"
        COUNTY_SUBDIVISION = 3, "County Subdivision"
        PLACE = 4, "Place"
        SCHOOL_DISTRICT = 5, "School District"
        URBAN_AREA = 6, "Urban Area"
        NEIGHBORHOOD = 7, "Neighborhood"
        ZIP_CODE = 8, "Zip Code"

    class Subtype(models.IntegerChoices):
        UNKNOWN = 0, "Unknown"

        # Places
        CITY = 10, "City"
        VILLAGE = 11, "Village"
        CDP = 12, "CDP"
        BOROUGH = 13, "Borough"

        # County subdivisions
        TOWN = 20, "Town"
        RESERVATION = 21, "Reservation"
        UNORGANIZED_TERRITORY = 22, "Unorganized Territory"
        COUNTY_SUBDIVISION_DEFINED = 23, "County Subdivision Defined"

        # School districts
        CENTRAL_SCHOOL_DISTRICT = 30, "Central School District"
        CITY_SCHOOL_DISTRICT = 31, "City School District"
        UNION_FREE_SCHOOL_DISTRICT = 32, "Union Free School District"
        COMMON_SCHOOL_DISTRICT = 33, "Common School District"
        SCHOOL_DISTRICT = 34, "School District"

        # Other geography types
        STATE = 40, "State"
        URBAN_AREA = 41, "Urban Area"
        NEIGHBORHOOD = 42, "Neighborhood"

        OTHER = 999, "Other"

    source = models.ForeignKey(
        DataSource,
        on_delete=models.PROTECT,
        related_name="geo_features",
    )
    external_id = models.CharField(
        max_length=128,
        help_text="Source-specific identifier, e.g. Census GEOID.",
    )
    name = models.CharField(max_length=255)
    full_name = models.CharField(max_length=255, blank=True)
    geography_type = models.PositiveSmallIntegerField(choices=GeographyType.choices)
    subtype = models.PositiveSmallIntegerField(choices=Subtype.choices, default=Subtype.UNKNOWN)
    state_code = models.CharField(max_length=2, blank=True)
    shape = models.MultiPolygonField(srid=4326)

    properties_json = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["geography_type", "subtype"]),
            models.Index(fields=["is_active"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["source", "external_id", "geography_type"],
                name="unique_geo_feature_per_source_external_id_type",
            ),
        ]

    def __str__(self):
        return self.full_name or self.name
