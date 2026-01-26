import functools
import typing

import geojson_pydantic as geopydantic
import pydantic


class BoundingBox(pydantic.BaseModel):
    """A longitude/latitude bounding box, defined by means of the string ``bbox``.

    Values are in degrees using the reference system of GeoJSON (EPSG:4326).
    """

    bbox: str
    """String containing 4 floats separated by commas that represent xmin, ymin, xmax, ymax of a
    longitude/latitude bounding box in EPSG:4326 (degrees). Min must be strictly less than max in
    both dimensions.
    """

    @pydantic.model_validator(mode="after")
    def parse_and_cache(self) -> typing.Self:
        try:
            parts = self.parts
        except ValueError:
            raise ValueError("'bbox' must contain a comma-separated list of floats.")
        if len(parts) != 4:
            raise ValueError("Bounding box must contain exactly 4 comma-separated values.")
        min_lon, min_lat, max_lon, max_lat = parts
        if min_lon >= max_lon or min_lat >= max_lat:
            raise ValueError("Invalid bounding box coordinates: min must be less than max.")

        self._polygon = geopydantic.Polygon.from_bounds(min_lon, min_lat, max_lon, max_lat)

        return self

    @property
    def polygon(self) -> geopydantic.Polygon:
        return self._polygon

    @functools.cached_property
    def parts(self) -> list[float]:
        if '"' in self.bbox or "'" in self.bbox:
            self.bbox = self.bbox.replace('"', "").replace("'", "")
        return list(map(float, self.bbox.split(",")))
