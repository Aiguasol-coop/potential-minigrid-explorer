# pyright: reportAttributeAccessIssue=false
# pyright: reportUnknownMemberType=false
# pyright: reportArgumentType=false
# pyright: reportUnknownArgumentType=false
# pyright: reportOperatorIssue=false
# pyright: reportUnknownVariableType=false

from collections.abc import Sequence
from datetime import datetime
from itertools import combinations
import os

from geopy.distance import geodesic, great_circle  # pyright: ignore[reportMissingTypeStubs]
import pandas as pd
import sqlmodel
from sklearn.cluster import DBSCAN

import app.db.core as db
import app.features.domain as features
from app.explorations.plotting import plot_buildings_and_grid_lines_with_distance


# PARAMETERS
EPS_VALUE = 300
DIAMETER_KM = 5
GRID_DISTANCES = [20, 40, 60, 80, 100, 120]  # Only 60 will be used in this script
MIN_BUILDINGS = 100
MATCH_DISTANCE_KM = 5
PROVINCES = [  # Adjacent number is the building count
    "Cabo Delga",  # 449720
    # "Gaza",  # 83771
    # "Inhambane",  # 99401
    # "Manica",  # 97937
    # "Maputo",  # 9648
    # "Maputo Cit",  # 2200
    # "Nampula",  # 686715
    # "Niassa",  # 318785
    # "Sofala",  # 91996
    # "Tete",  # 515487
    # "Zambezia",  # 540639
]


def cluster_buildings(
    centroids: list[tuple[float, float]],
    eps_meters: float = 300,
    min_samples: int = 100,
    max_diameter: float = 5000,
) -> tuple[
    dict[int, list[tuple[float, float]]],
    dict[int, list[tuple[float, float]]],
    list[tuple[float, float]],
]:
    """
    Cluster building centroids using DBSCAN and filter by maximum cluster diameter.
    This function performs spatial clustering using the DBSCAN algorithm, with additional
    filtering to ensure that each resulting cluster meets a specified maximum diameter
    (maximum distance between any two points in the cluster). Outliers and discarded clusters
    are also returned for further analysis or cleanup.
    Parameters
    ----------
    centroids : List[Tuple[float, float]]
        A list of building centroid coordinates as (latitude, longitude) pairs.
    eps_meters : float, optional
        The maximum distance (in meters) between neighboring points for them to be considered
        part of the same cluster in DBSCAN. Default is 1000 meters.
    min_samples : int, optional
        The minimum number of points required to form a cluster in DBSCAN. Default is 5.
    max_diameter : float, optional
        The maximum allowed distance (in meters) between the two farthest points within
        a cluster. Clusters exceeding this diameter are discarded. Default is 2000 meters.
    Returns
    -------
    valid_clusters : Dict[int, List[Tuple[float, float]]]
        A dictionary of cluster_id to list of centroids for clusters that passed
        both the DBSCAN criteria and the diameter constraint.

    discarded_clusters : Dict[int, List[Tuple[float, float]]]
        A dictionary of cluster_id to list of centroids for clusters that were
        created by DBSCAN but failed the diameter filter.

    outlier_centroids : List[Tuple[float, float]]
        A list of centroid coordinates that were classified as noise by DBSCAN
        (i.e., not included in any cluster).
    """
    clusters = {}
    valid_clusters = {}
    discarded_clusters = {}
    outlier_centroids = []

    if len(centroids) == 0:
        return valid_clusters, discarded_clusters, outlier_centroids

    # Convert distance from meters to degrees (approximation)
    eps_deg = eps_meters / 111000
    # Run DBSCAN clustering
    dbscan = DBSCAN(eps=eps_deg, min_samples=min_samples, metric="euclidean")
    labels = dbscan.fit_predict(centroids)
    # Organize points into clusters and outliers
    for idx, label in enumerate(labels):
        if label == -1:
            outlier_centroids.append(centroids[idx])
        else:
            clusters.setdefault(label, []).append(centroids[idx])
    # Filter clusters by maximum diameter
    for label, points in clusters.items():
        if len(points) < 2:
            discarded_clusters[label] = points
            continue
        max_dist = max(great_circle(p1, p2).meters for p1, p2 in combinations(points, 2))
        if max_dist <= max_diameter:
            valid_clusters[label] = points
        else:
            discarded_clusters[label] = points
    return valid_clusters, discarded_clusters, outlier_centroids


def get_buildings_by_distance_from_grid(
    min_grid_distance_km: float,
    province: str = None,
    plot: bool = False,
):  # -> tuple[list[tuple[float, float]], list[tuple[float, float]]]:
    """
    Retrieve building centroids that are farther than a specified distance from the grid, optionally
    filtered by province.

    Parameters
        min_grid_distance_km : float
        Minimum allowed distance from grid (in km).
        province : str, optional
            If provided, filters buildings by province name.
        plot : bool
            Whether to generate a distance-to-grid folium plot.
    Returns
        Tuple of valid and discarded centroids.
    """
    min_distance_meters = min_grid_distance_km * 1000
    centroids, distances_km = [], []
    discarded_centroids, discarded_distances_km = [], []

    with db.get_logging_session() as session:
        stmt = sqlmodel.select(features.Building).where(
            features.Building.distance_to_grid >= min_distance_meters
            if features.Building.distance_to_grid is not None
            else True,
        )
        if province:
            stmt = stmt.where(features.Building.province == province)
        results = session.exec(stmt).all()
        num_centroids = 0
        for building in results:
            if building.centroid_geography:
                num_centroids += 1
                coords = building.centroid_geography
                try:
                    # TODO: Check if lat,lon is the order we need
                    centroids.append((coords.coordinates.latitude, coords.coordinates.longitude))
                    distances_km.append(building.distance_to_grid / 1000.0)  # type: ignore
                except Exception:
                    continue
        if plot:
            discarded_stmt = sqlmodel.select(features.Building).where(
                features.Building.distance_to_grid < min_distance_meters
                if features.Building.distance_to_grid is not None
                else False,
            )
            if province:
                discarded_stmt = discarded_stmt.where(features.Building.province == province)
            discarded_results = session.exec(discarded_stmt).all()
            for building in discarded_results:
                if building.centroid_geography:
                    coords = building.centroid_geography
                    try:
                        discarded_centroids.append((coords.y, coords.x))
                        discarded_distances_km.append(building.distance_to_grid / 1000.0)  # type: ignore
                    except Exception:
                        continue

            map_obj = plot_buildings_and_grid_lines_with_distance(
                db,
                centroids=centroids,
                distances_km=distances_km,
                discarded_centroids=discarded_centroids,
                discarded_distances_km=discarded_distances_km,
                zoom_start=None,
            )
            map_obj.save(
                os.path.join(os.getcwd(), "plots", f"centroids_distance_{province or 'all'}.html")
            )
    return centroids, [
        {
            "building_id": b.id_shp,
            "distance_to_road": b.distance_to_road,
            "is_island": b.is_island,
            "building_type": b.building_type,
            "surface": b.surface,
            "dist_grid": b.distance_to_grid,
        }
        for b in results
        if b.centroid_geography
    ]


def get_existing_mini_grids() -> Sequence[features.MiniGrid]:
    with db.get_logging_session() as session:
        mini_grids = session.exec(
            sqlmodel.select(features.MiniGrid).where(
                features.MiniGrid.status == features.MinigridStatus.known_to_exist
            )
        ).all()
    return mini_grids


# TODO: return distance to relevant roads (some tests may be needed to select the appropiate road
# type)

# Number of road segments by type:
# path	170685
# residential	165036
# unclassified	101518
# track	94496
# service	10292
# footway	4977
# tertiary	4651
# secondary	2661
# trunk	1585
# primary	1523


def generate_clusters_only():
    print("🔄 Initializing database and retrieving data...")
    mini_grids = get_existing_mini_grids()

    # TODO: following commented out variable not used, check if necessary
    # grid_lines = get_grid_lines()
    cluster_records = []
    centroid_records = []

    for grid_distance in [60]:  # only grid distance 60 km
        print(f"\n🌍 Grid distance ≥ {grid_distance} km")
        all_centroids = []

        for province in PROVINCES:
            # Retrieve building centroids and associated info from DB
            centroids, buildings_info = get_buildings_by_distance_from_grid(
                min_grid_distance_km=grid_distance, province=province
            )

            print(f"🔍 Province: {province}")
            print(f"   Total returned buildings: {len(centroids)}")

            valid_count = 0

            # TODO: the filtering by distance to road < 1 km can probably be removed (ask Azimut)
            # Filter centroids: keep islands always, others must be < 1 km to road
            for (lat, lon), info in zip(centroids, buildings_info):
                if info is None:
                    continue

                is_island = info.get("is_island", False)
                dist_road = info.get("distance_to_road", 999999)

                if is_island or dist_road < 1000:
                    all_centroids.append(
                        {
                            "lat": lat,
                            "lon": lon,
                            "province": province,
                            "id_shp": info.get("building_id"),
                            "building_type": info.get("building_type"),
                            "surface": info.get("surface"),
                            "dist_grid": info.get("dist_grid"),
                            "dist_road": dist_road,
                        }
                    )
                    valid_count += 1

            print(f"   ✅ Valid after filtering: {valid_count}")

        print(f"✅ Total filtered centroids: {len(all_centroids)}")

        # Prepare coordinates for clustering
        coords_only = [(c["lat"], c["lon"]) for c in all_centroids]

        valid_clusters, _discarded_clusters, _outliers = cluster_buildings(
            coords_only,
            eps_meters=EPS_VALUE,
            min_samples=MIN_BUILDINGS,
            max_diameter=DIAMETER_KM * 1000,
        )

        cluster_id_counter = 1
        for _cluster_id, cluster_points in valid_clusters.items():
            clat = sum(lat for lat, _ in cluster_points) / len(cluster_points)
            clon = sum(lon for _, lon in cluster_points) / len(cluster_points)

            # Skip clusters too close to existing mini-grids
            too_close = any(
                geodesic(
                    (clat, clon),
                    (mg.geography.coordinates.latitude, mg.geography.coordinates.longitude),
                ).km
                < MATCH_DISTANCE_KM
                for mg in mini_grids
            )
            if too_close:
                continue

            # Calculate average surface and road distance for the cluster
            members = [i for i, pt in enumerate(coords_only) if pt in cluster_points]
            surfaces = [
                all_centroids[i]["surface"]
                for i in members
                if all_centroids[i]["surface"] is not None
            ]
            avg_surface = sum(surfaces) / len(surfaces) if surfaces else 0

            cluster_records.append(
                {
                    "cluster_id": cluster_id_counter,
                    "latitude": clat,
                    "longitude": clon,
                    "province": all_centroids[members[0]]["province"],
                    "num_buildings": len(members),
                    "distance_to_grid_m": all_centroids[members[0]]["dist_grid"],
                    "avg_distance_to_road_m": sum(all_centroids[i]["dist_road"] for i in members)
                    / len(members),
                    "avg_surface": avg_surface,
                    "eps_meters": EPS_VALUE,
                    "diameter_km": DIAMETER_KM,
                    "grid_distance_km": grid_distance,
                }
            )

            # Add building-level information per cluster
            for i in members:
                centroid_records.append(
                    {
                        "cluster_id": cluster_id_counter,
                        "id_shp": all_centroids[i]["id_shp"],
                        "building_type": all_centroids[i]["building_type"],
                        "surface": all_centroids[i]["surface"],
                        "latitude": all_centroids[i]["lat"],
                        "longitude": all_centroids[i]["lon"],
                    }
                )

            cluster_id_counter += 1

    # Save results to CSV files
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    os.makedirs("outputs", exist_ok=True)
    pd.DataFrame(cluster_records).to_csv(f"outputs/filtered_clusters_{timestamp}.csv", index=False)
    pd.DataFrame(centroid_records).to_csv(
        f"outputs/centroids_per_cluster_{timestamp}.csv", index=False
    )
    print("\n📁 Clustering results saved.")


if __name__ == "__main__":
    generate_clusters_only()
