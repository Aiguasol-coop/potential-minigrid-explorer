import typing

import geoalchemy2
import geoalchemy2.shape
import geojson_pydantic as geopydantic
import pydantic
import sqlalchemy
import sqlmodel


def _point_to_database(geography: geopydantic.Point) -> str:
    return geography.wkt


def _point_from_database(pg_geography: str) -> geopydantic.Point:
    return geopydantic.Point(
        **geoalchemy2.shape.to_shape(
            typing.cast(geoalchemy2.WKTElement, pg_geography)
        ).__geo_interface__
    )


def _polygon_to_database(geography: geopydantic.Polygon) -> str:
    return geography.wkt


def _multipolygon_to_database(geography: geopydantic.MultiPolygon) -> str:
    return geography.wkt


def _linestring_to_database(geography: geopydantic.LineString) -> str:
    return geography.wkt


def _polygon_from_database(pg_geography: str) -> geopydantic.Polygon:
    return geopydantic.Polygon(
        **geoalchemy2.shape.to_shape(
            typing.cast(geoalchemy2.WKTElement, pg_geography)
        ).__geo_interface__
    )


def _multipolygon_from_database(pg_geography: str) -> geopydantic.MultiPolygon:
    return geopydantic.MultiPolygon(
        **geoalchemy2.shape.to_shape(
            typing.cast(geoalchemy2.WKTElement, pg_geography)
        ).__geo_interface__
    )


def _linestring_from_database(pg_geography: str) -> geopydantic.LineString:
    return geopydantic.LineString(
        **geoalchemy2.shape.to_shape(
            typing.cast(geoalchemy2.WKTElement, pg_geography)
        ).__geo_interface__
    )


class HasPointAttribute(sqlmodel.SQLModel):
    geography: geopydantic.Point

    @property
    def pg_geography(self) -> str:
        return _point_to_database(self.geography)


class HasPointColumn(sqlmodel.SQLModel):
    pg_geography: str = sqlmodel.Field(
        sa_column=sqlalchemy.Column(geoalchemy2.Geography(geometry_type="POINT", srid=4326)),
    )

    @pydantic.computed_field()
    @property
    def geography(self) -> geopydantic.Point:
        return _point_from_database(self.pg_geography)


class HasPolygonAttribute(sqlmodel.SQLModel):
    geography: geopydantic.Polygon

    @property
    def pg_geography(self) -> str:
        return _polygon_to_database(self.geography)


class HasPolygonColumn(sqlmodel.SQLModel):
    pg_geography: str = sqlmodel.Field(
        sa_column=sqlalchemy.Column(geoalchemy2.Geography(geometry_type="POLYGON", srid=4326)),
    )

    @pydantic.computed_field()
    @property
    def geography(self) -> geopydantic.Polygon:
        return _polygon_from_database(self.pg_geography)


class HasPointAndMultipolygonColumn(sqlmodel.SQLModel):
    pg_geography: str = sqlmodel.Field(
        sa_column=sqlalchemy.Column(geoalchemy2.Geography(geometry_type="MULTIPOLYGON", srid=4326)),
    )

    pg_geography_centroid: str = sqlmodel.Field(
        sa_column=sqlalchemy.Column(geoalchemy2.Geography(geometry_type="POINT", srid=4326)),
    )

    @pydantic.computed_field()
    @property
    def geography(self) -> geopydantic.MultiPolygon:
        return _multipolygon_from_database(self.pg_geography)

    @pydantic.computed_field()
    @property
    def centroid_geography(self) -> geopydantic.Point:
        return _point_from_database(self.pg_geography_centroid)


class HasPointAndMultipolygonAttribute(sqlmodel.SQLModel):
    geography: geopydantic.MultiPolygon
    centroid_geography: geopydantic.Point

    @property
    def pg_geography(self) -> str:
        return _multipolygon_to_database(self.geography)

    @property
    def pg_centroid_geography(self) -> str:
        return _point_to_database(self.centroid_geography)


class HasLinestringColumn(sqlmodel.SQLModel):
    pg_geography: str = sqlmodel.Field(
        sa_column=sqlalchemy.Column(geoalchemy2.Geography(geometry_type="LINESTRING", srid=4326)),
    )

    @pydantic.computed_field()
    @property
    def geography(self) -> geopydantic.LineString:
        return _linestring_from_database(self.pg_geography)


class HasLinestringAttribute(sqlmodel.SQLModel):
    geography: geopydantic.LineString

    @property
    def pg_geography(self) -> str:
        return _linestring_to_database(self.geography)
