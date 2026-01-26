import sqlmodel
import sqlalchemy
from geoalchemy2 import Geometry
from geoalchemy2 import functions as geofunc
from typing import Any
from sqlalchemy.sql.elements import ColumnElement


import app.db.core as db
from app.features.domain import Building
from app.service_offgrid_planner.demand import calculate_demand, ElectricalDemand
from app.explorations.domain import generate_grid_input
from app.explorations.clustering import Cluster, ClusterBuilding

if __name__ == "__main__":
    # Given a set of centroids (Result from Michel code):
    mozambique_bbox = (
        38.803945,
        -13.966835,
        38.807348,
        -13.964998,
    )  # (38.777312,-13.983961,38.859709,-13.943647)  # (min_lon, min_lat, max_lon, max_lat)
    min_lon, min_lat, max_lon, max_lat = mozambique_bbox

    envelope = geofunc.ST_MakeEnvelope(min_lon, min_lat, max_lon, max_lat, 4326)
    centroid_geom: ColumnElement[Any] = sqlalchemy.cast(
        Building.pg_geography_centroid, Geometry(geometry_type="POINT", srid=4326)
    )

    with db.get_logging_session() as session:
        cluster_centroids: list[Building] = list(
            session.exec(
                sqlmodel.select(Building).where(geofunc.ST_Within(centroid_geom, envelope))
            ).all()
        )

        demand: ElectricalDemand = calculate_demand(cluster_centroids, session)

        first_building = cluster_centroids[0]
        cluster = Cluster(
            cluster_id=1,
            province="Test Province",
            num_buildings=len(cluster_centroids),
            estimated_microgrid_network_length=0.68,
            distance_to_main_road=2,
            distance_to_local_road=1,
            avg_surface=100,
            eps_meters=300,
            distance_to_grid=5,
            buildings=[
                ClusterBuilding(
                    building_id=building.id_shp if building.id_shp else nb,
                    building_type="public_service"
                    if building.building_type
                    and ("hospital" in building.building_type or "school" in building.building_type)
                    else "other",
                    surface=building.surface if building.surface else 0,
                    latitude=building.centroid_geography.coordinates.latitude
                    if building.centroid_geography
                    else 0.0,
                    longitude=building.centroid_geography.coordinates.longitude
                    if building.centroid_geography
                    else 0.0,
                )
                for nb, building in enumerate(cluster_centroids)
            ],
            pg_geography=first_building.pg_geography_centroid,  # type: ignore
        )

        grid_input = generate_grid_input(
            demand.total_annual_demand,
            cluster,
            demand.consumers_types,
            demand.existing_consumers,
        )
