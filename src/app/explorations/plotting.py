# pyright: reportAttributeAccessIssue=false
# pyright: reportUnknownMemberType=false
# pyright: reportArgumentType=false
# pyright: reportUnknownArgumentType=false
# pyright: reportOperatorIssue=false
# pyright: reportUnknownVariableType=false

import math

from branca.colormap import linear
import folium
from geoalchemy2.shape import to_shape
import sqlmodel

import app.db.core as db
import app.features.domain as features


def estimate_zoom_from_bounds(bounds: list[tuple[float, float]]) -> int:
    """
    Estimate folium zoom level based on bounding box diagonal.
    """
    if not bounds:
        return 6

    latitudes = [p[0] for p in bounds]
    longitudes = [p[1] for p in bounds]

    lat_diff = max(latitudes) - min(latitudes)
    lon_diff = max(longitudes) - min(longitudes)

    diagonal_deg = math.sqrt(lat_diff**2 + lon_diff**2)

    # Very rough zoom estimate based on diagonal span
    if diagonal_deg < 0.05:
        return 15
    elif diagonal_deg < 0.1:
        return 13
    elif diagonal_deg < 0.2:
        return 11
    elif diagonal_deg < 0.5:
        return 9
    elif diagonal_deg < 1:
        return 8
    elif diagonal_deg < 2:
        return 7
    else:
        return 6


def plot_buildings_and_grid_lines_with_distance(
    db: db.Session,
    centroids: list[tuple[float, float]],
    distances_km: list[float],
    discarded_centroids: list[tuple[float, float]],
    discarded_distances_km: list[float] | list[None] | None = None,
    zoom_start: int | None = None,
) -> folium.Map:
    """
    Plot buildings with color based on distance to grid and grid distribution lines.
    Discarded points shown in red with distance popup.

    Parameters
    ----------
    centroids : List[Tuple[float, float]]
        Coordinates of buildings satisfying the grid distance requirement.

    distances_km : List[float]
        Corresponding distances (in km) for centroids above.

    discarded_centroids : List[Tuple[float, float]]
        Coordinates of buildings too close to the grid.

    discarded_distances_km : List[float], optional
        Distances (in km) for discarded centroids.

    zoom_start : int, optional
        If provided, sets initial zoom. Otherwise calculated automatically.

    Returns
    -------
    folium.Map
        Folium map object.
    """
    all_points = centroids + discarded_centroids
    if not all_points:
        return folium.Map(location=[0, 0], zoom_start=2)

    lat_center = sum(lat for lat, _ in all_points) / len(all_points)
    lon_center = sum(lon for _, lon in all_points) / len(all_points)
    auto_zoom = zoom_start or estimate_zoom_from_bounds(all_points)

    m = folium.Map(location=(lat_center, lon_center), zoom_start=auto_zoom)

    # Color scale for distance
    if distances_km:
        colormap = linear.viridis.scale(min(distances_km), max(distances_km))
        colormap.caption = "Distance to Grid (km)"
        colormap.add_to(m)

        for (lat, lon), dist in zip(centroids, distances_km):
            folium.CircleMarker(
                location=(lat, lon),
                radius=4,
                color=colormap(dist),
                fill=True,
                fill_color=colormap(dist),
                fill_opacity=0.8,
                popup=f"{dist:.2f} km",
            ).add_to(m)

    # Discarded in red with popup
    if discarded_distances_km is None:
        discarded_distances_km = [None] * len(discarded_centroids)

    for (lat, lon), dist in zip(discarded_centroids, discarded_distances_km):
        popup_text = (
            f"Too close to grid: {dist:.2f} km" if dist is not None else "Too close to grid"
        )

        folium.CircleMarker(
            location=(lat, lon),
            radius=3,
            color="red",
            fill=True,
            fill_color="red",
            fill_opacity=0.7,
            popup=popup_text,
        ).add_to(m)

    # Grid distribution lines
    stmt = sqlmodel.select(features.GridDistributionLine.geometry)
    results = db.exec(stmt).all()
    for wkt in results:
        try:
            line = to_shape(wkt)
            coords = [(lat, lon) for lon, lat in line.coords]
            folium.PolyLine(locations=coords, color="blue", weight=1.2).add_to(m)
        except Exception:
            continue

    return m
