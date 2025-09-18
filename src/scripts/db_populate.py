import os

from collections.abc import Iterator
import geopandas as gpd
import pandas as pd
import sqlmodel
import numpy as np
import shapely
import fiona  # type: ignore
import json
import typing

import app.grid.domain as grid
import app.categories.domain as categories
import app.explorations.domain as explorations


CLASS_DICT = {
    "electric_grid": grid.GridDistributionLine,
    "mini-grids (points)": grid.MiniGrid,
    "centroids_buildings_20km": grid.Building,
    "polygons_buildings_20km": grid.Building,
    "gis_osm_roads_free_1": grid.Road,
}


##################################### GEOJSON DEFAULT FILES DATA ###################################


def clean_roads(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    gdf_clean = gdf.loc[
        :,
        [
            "osm_id",
            "code",
            "fclass",
            "ref",
            "oneway",
            "maxspeed",
            "layer",
            "bridge",
            "tunnel",
            "geometry",
        ],
    ]
    gdf_clean.columns = [
        "id_shp",
        "code",
        "road_type",
        "ref",
        "oneway",
        "maxspeed",
        "layer",
        "bridge",
        "tunnel",
        "pg_geography",
    ]
    gdf_clean["length_km"] = gdf_clean["pg_geography"].apply(  # type: ignore
        lambda g: g.length / 1000 if g else None  # type: ignore
    )
    gdf_clean["pg_geography"] = gdf_clean["pg_geography"].apply(  # type: ignore
        lambda g: g.wkt  # type: ignore
    )  # Convert to WKT for DB insertion

    return gdf_clean


def clean_grid_lines(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    gdf_clean = gdf.loc[
        :, ["id", "status", "vltg_kv", "classes", "adm1_name", "length_gau", "geometry"]
    ]
    gdf_clean.columns = [
        "id_shp",
        "status",
        "vltg_kv",
        "classes",
        "province",
        "length_km",
        "pg_geography",
    ]

    split_records: list[pd.Series] = []  # type: ignore
    for _, row in gdf_clean.iterrows():  # type: ignore
        geom: shapely.geometry.base.BaseGeometry = row["pg_geography"]  # type: ignore
        if isinstance(geom, shapely.geometry.MultiLineString):
            total_length = geom.length
            for line in geom.geoms:
                new_row: pd.Series = row.copy()  # type: ignore
                new_row["pg_geography"] = line
                new_row["length_km"] = (
                    row["length_km"] * (line.length / total_length) if total_length > 0 else 0
                )
                split_records.append(new_row)  # type: ignore
        else:
            split_records.append(row)  # type: ignore

    gdf_split = gpd.GeoDataFrame(split_records, geometry="pg_geography", crs=gdf.crs)
    gdf_split["pg_geography"] = gdf_split["pg_geography"].apply(  # type: ignore
        lambda g: g.wkt  # type: ignore
    )  # Convert to WKT for DB insertion

    return gdf_split


def clean_mini_grids(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    gdf = gdf.dropna(how="all")  # type: ignore
    gdf_clean = gdf.loc[
        :,
        [
            "Name",
            "Province",
            "Operator",
            "Power",
            "Unit_Power",
            "Estimated",
            "num_builds",
            "max_dist",
            "dist_grid",
            "dist_road",
            "Island",
            "start_date",
            "geometry",
        ],
    ]

    gdf_clean.columns = [
        "name",
        "province",
        "operator",
        "pv_power",
        "pv_power_units",
        "estimated_power",
        "num_buildings",
        "max_building_distance",
        "distance_to_grid",
        "distance_to_road",
        "is_island",
        "start_date",
        "pg_geography",
    ]

    gdf_clean["start_date"] = pd.to_datetime(gdf_clean["start_date"], errors="coerce")  # type: ignore
    gdf_clean["pg_geography"] = gdf_clean["pg_geography"].apply(  # type: ignore
        lambda geom: geom.wkt if geom is not None else None  # type: ignore
    )
    gdf_clean["status"] = grid.MinigridStatus.known_to_exist.value
    gdf_clean = gdf_clean[gdf_clean["pg_geography"].notnull()]
    return gdf_clean.replace({np.nan: None})  # type: ignore


def read_gdf_in_chunks(
    cent_path: str,
    cent_cols: list[str] | None = None,
    poly_path: str | None = None,
    poly_cols: list[str] | None = None,
    chunk_size: int = 200_000,
    include_geometry: bool = True,
) -> Iterator[gpd.GeoDataFrame]:
    # 1) Inspect cheaply without loading all features
    with fiona.open(cent_path) as src:  # type: ignore
        total = len(src)
        crs = src.crs_wkt or src.crs  # type: ignore

    # 2) Stream chunks
    for start in range(0, total, chunk_size):
        stop = min(start + chunk_size, total)
        cent_gdf = gpd.read_file(  # type: ignore
            cent_path,
            rows=slice(start, stop),
            ignore_geometry=not include_geometry,  # GeoPandas will return a DataFrame if True
        )

        # Set CRS if missing (only meaningful when geometry is present)
        if include_geometry and (crs is not None) and (getattr(cent_gdf, "crs", None) is None):
            cent_gdf = cent_gdf.set_crs(crs, allow_override=True)  # type: ignore[attr-defined]

        # Keep only requested columns (and geometry if present)
        if cent_cols is not None:
            keep = [c for c in cent_cols if c in cent_gdf.columns]  # type: ignore
            if include_geometry and "geometry" in cent_gdf.columns:  # type: ignore
                keep = keep
            cent_gdf = cent_gdf[keep]  # type: ignore

        poly_gdf = gpd.read_file(  # type: ignore
            poly_path,  # type: ignore
            rows=slice(start, stop),
            ignore_geometry=not include_geometry,  # type: ignore
        )

        # Set CRS if missing (only meaningful when geometry is present)
        if include_geometry and (crs is not None) and (getattr(poly_gdf, "crs", None) is None):  # type: ignore
            poly_gdf = poly_gdf.set_crs(crs, allow_override=True)  # type: ignore[attr-defined]

        # Keep only requested columns (and geometry if present)
        if cent_cols is not None:
            keep = [c for c in poly_cols if c in poly_gdf.columns]  # type: ignore
            if include_geometry and "geometry" in poly_gdf.columns:  # type: ignore
                keep = keep
            poly_gdf = poly_gdf[keep]  # type: ignore

        yield cent_gdf, poly_gdf  # type: ignore


def clean_building_centroids(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    gdf = gdf.iloc[:, :]

    gdf["id_shp"] = gdf["building_i"]
    gdf = gdf.dropna(subset=["id_shp"])  # type: ignore
    gdf["id_shp"] = pd.to_numeric(gdf["id_shp"], errors="coerce").astype("Int64")  # type: ignore
    gdf["has_electr"] = gdf["has_electr"].map({"True": True, "False": False})  # type: ignore

    gdf_clean = gdf.loc[
        :,
        [
            "id_shp",
            "Province",
            "electric_d",
            "has_electr",
            "category",
            "building_t",
            "dist_grid",
            "dist_road",
            "Island",
            "geometry",
            "area_m2",
        ],
    ].copy()

    gdf_clean.columns = [
        "id_shp",
        "province",
        "electric_demand",
        "has_electricity",
        "category",
        "building_type",
        "distance_to_grid",
        "distance_to_road",
        "is_island",
        "geometry",
        "surface",
    ]

    gdf_clean["pg_geography_centroid"] = gdf_clean["geometry"].apply(  # type: ignore
        lambda geom: geom.wkt if geom else None  # type: ignore
    )
    gdf_clean = gdf_clean.drop(columns="geometry")

    for col in ["distance_to_grid", "electric_demand", "surface"]:
        if col in gdf_clean.columns:
            gdf_clean[col] = gdf_clean[col].apply(  # type: ignore
                lambda x: float(str(x).replace(",", ".")) if isinstance(x, str) else x  # type: ignore
            )
            gdf_clean[col] = pd.to_numeric(gdf_clean[col], errors="coerce")  # type: ignore

    gdf_clean["is_island"] = gdf_clean["is_island"].map(  # type: ignore
        {True: True, False: False, "True": True, "False": False}
    )

    return gdf_clean.replace({np.nan: None})  # type: ignore


def clean_building_polygons(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    gdf = gdf.iloc[:, :]
    gdf = gdf.dropna(subset=["building_i"])  # type: ignore
    gdf["id_shp"] = pd.to_numeric(gdf["building_i"], errors="coerce").astype("Int64")  # type: ignore
    gdf_clean = gdf.loc[:, ["id_shp", "geometry"]].copy()
    gdf_clean["pg_geography"] = gdf_clean["geometry"].apply(lambda geom: geom.wkt if geom else None)  # type: ignore
    return gdf_clean.drop(columns="geometry").replace({np.nan: None})  # type: ignore


def populate_db(db_session: sqlmodel.Session) -> None:
    """It only populates previously empty tables."""

    raw = os.path.join(os.getcwd(), "src", "scripts", "raw_data")
    try:
        shp_files = {f[:-4]: f for f in os.listdir(raw) if f.endswith(".shp")}
    except FileNotFoundError as exp:
        print(f"FileNotFoundError captured: directory {exp.filename}")
        shp_files = {}

    files_by_model = {}
    for basename, model in CLASS_DICT.items():
        if basename in shp_files:
            files_by_model.setdefault(model, []).append(shp_files[basename])  # type: ignore

    for model, files in files_by_model.items():  # type: ignore
        try:
            if model.__tablename__ == "buildings":  # type: ignore
                if db_session.exec(sqlmodel.select(model).limit(1)).first():  # type: ignore
                    print("🏠 Buildings table already populated, skipping.")
                    continue

                if set(files) >= {"centroids_buildings_20km.shp", "polygons_buildings_20km.shp"}:  # type: ignore
                    cent_cols = [
                        "building_i",
                        "Province",
                        "electric_d",
                        "has_electr",
                        "category",
                        "building_t",
                        "dist_grid",
                        "dist_road",
                        "Island",
                        "area_m2",
                        "geometry",
                    ]
                    poly_cols = ["building_i", "geometry"]
                    total_inserted = 0
                    centroids_path = os.path.join(raw, "centroids_buildings_20km.shp")  # type: ignore
                    polygons_path = os.path.join(raw, "polygons_buildings_20km.shp")

                    for cent_gdf_chunk, poly_gdf_chunk in read_gdf_in_chunks(
                        cent_path=centroids_path,
                        cent_cols=cent_cols,
                        poly_path=polygons_path,
                        poly_cols=poly_cols,
                        chunk_size=200_000,
                        include_geometry=True,
                    ):
                        cent = clean_building_centroids(cent_gdf_chunk)  # type: ignore
                        poly = clean_building_polygons(poly_gdf_chunk)  # type: ignore

                        merged = pd.merge(  # type: ignore
                            cent, poly, on="id_shp", how="outer", suffixes=("", "_poly")
                        ).replace({np.nan: None})

                        records = merged.to_dict(orient="records")  # type: ignore

                        # Fast path: bulk_insert_mappings (no ORM object construction)
                        db_session.bulk_insert_mappings(model, records)  # type: ignore
                        db_session.commit()
                        total_inserted += len(records)
                        print(
                            f"✔️ Inserted {len(records)} buildings, total buildings {total_inserted}"
                        )

                else:
                    print("⚠️ Missing one or both building shapefiles, skipping.")
                continue

            if db_session.exec(sqlmodel.select(model).limit(1)).first():  # type: ignore
                print(f"⏭️ Skipping `{model.__tablename__}`: already populated.")  # type: ignore
                continue

            basename = os.path.splitext(files[0])[0]  # type: ignore
            gdf = gpd.read_file(os.path.join(raw, files[0]))  # type: ignore

            if basename == "electric_grid":
                clean = clean_grid_lines(gdf)
            elif basename == "mini-grids (points)":
                clean = clean_mini_grids(gdf)
            elif basename == "gis_osm_roads_free_1":
                clean = clean_roads(gdf)
            else:
                clean = gdf

            df = clean.replace({np.nan: None})  # type: ignore
            objs = [model(**rec) for rec in df.to_dict("records")]  # type: ignore
            db_session.bulk_save_objects(objs)  # type: ignore
            db_session.commit()
            print(f"✔️ Inserted `{model.__tablename__}`: {len(objs)} records.")  # type: ignore
        except FileNotFoundError as exp:
            print(f"FileNotFoundError captured: file {exp.filename}")


##################################### JSON DEFAULT DATA #####################################


def load_json_data(file_path: str) -> dict[str, typing.Any]:
    """Load data from JSON file."""
    with open(file_path, "r") as f:
        return json.load(f)


def populate_category_distribution(session: sqlmodel.Session, data: dict[str, typing.Any]):
    """Populate the Category Distribution table."""
    print("Populating Category Distribution...")

    # Check if data already exists
    if session.exec(sqlmodel.select(explorations.CategoryDistribution)).first():
        print("  Category Distribution data already exists, skipping.")
        return

    category_dist = explorations.CategoryDistribution(
        households=data["centroid_category_distribution"]["households"],
        public_services=data["centroid_category_distribution"]["public_services"],
        enterprises=data["centroid_category_distribution"]["enterprises"],
    )
    session.add(category_dist)
    session.commit()
    print("  Added category distribution data.")


def populate_household_data(session: sqlmodel.Session, data: dict[str, typing.Any]):
    """Populate the HouseholdData table."""
    print("Populating HouseholdData...")

    # Check if data already exists
    if session.exec(sqlmodel.select(categories.HouseholdData)).first():
        print("  HouseholdData already exists, skipping.")
        return

    for area_type, subcategories in data["households_subcategory_data"].items():
        for subcategory, values in subcategories.items():
            household_data = categories.HouseholdData(
                area_type=area_type,
                subcategory=subcategory,
                kwh_per_day=values["kwh_per_day"],
                distribution=values["distribution"],
            )
            session.add(household_data)
    session.commit()
    print(f"  Added household data for {area_type}.")  # pyright: ignore[reportPossiblyUnboundVariable]


def populate_enterprise_data(session: sqlmodel.Session, data: dict[str, typing.Any]):
    """Populate the EnterpriseData table."""
    print("Populating EnterpriseData...")

    # Check if data already exists
    if session.exec(sqlmodel.select(categories.EnterpriseData)).first():
        print("  EnterpriseData already exists, skipping.")
        return

    for area_type, subcategories in data["enterprise_subcategory_data"].items():
        for subcategory, values in subcategories.items():
            enterprise_data = categories.EnterpriseData(
                area_type=area_type,
                subcategory=subcategory,
                kwh_per_day=values["kwh_per_day"],
                distribution=values["distribution"],
            )
            session.add(enterprise_data)
    session.commit()
    print(f"  Added enterprise data for {area_type}.")  # pyright: ignore[reportPossiblyUnboundVariable]


def populate_public_service_data(session: sqlmodel.Session, data: dict[str, typing.Any]):
    """Populate the PublicServiceData table."""
    print("Populating PublicServiceData...")

    # Check if data already exists
    if session.exec(sqlmodel.select(categories.PublicServiceData)).first():
        print("  PublicServiceData already exists, skipping.")
        return

    for area_type, subcategories in data["public_services_subcategory_data"].items():
        for subcategory, values in subcategories.items():
            public_service_data = categories.PublicServiceData(
                area_type=area_type,
                subcategory=subcategory,
                kwh_per_day=values["kwh_per_day"],
                distribution=values["distribution"],
            )
            session.add(public_service_data)
    session.commit()
    print(f"  Added public service data for {area_type}.")  # pyright: ignore[reportPossiblyUnboundVariable]


def populate_household_hourly_profile(session: sqlmodel.Session, data: dict[str, typing.Any]):
    """Populate the HouseholdHourlyProfile table."""
    print("Populating HouseholdHourlyProfile...")

    # Check if data already exists
    if session.exec(sqlmodel.select(categories.HouseholdHourlyProfile)).first():
        print("  HouseholdHourlyProfile already exists, skipping.")
        return

    for area_type, subcategories in data["households_hourly_profile"].items():
        for subcategory, values in subcategories.items():
            # Skip if the structure doesn't match what we expect
            if not isinstance(values, dict) or "hourly_profile" not in values:
                continue

            household_profile = categories.HouseholdHourlyProfile(
                area_type=area_type,
                subcategory=subcategory,
                hourly_profile=values["hourly_profile"],  # pyright: ignore[reportUnknownArgumentType]
            )
            session.add(household_profile)
    session.commit()
    print("  Added household hourly profiles.")


def populate_enterprise_hourly_profile(session: sqlmodel.Session, data: dict[str, typing.Any]):
    """Populate the EnterpriseHourlyProfile table."""
    print("Populating EnterpriseHourlyProfile...")

    # Check if data already exists
    if session.exec(sqlmodel.select(categories.EnterpriseHourlyProfile)).first():
        print("  EnterpriseHourlyProfile already exists, skipping.")
        return

    for subcategory, values in data["enterprise_hourly_profiles"].items():
        enterprise_profile = categories.EnterpriseHourlyProfile(
            subcategory=subcategory, hourly_profile=values["hourly_profile"]
        )
        session.add(enterprise_profile)
    session.commit()
    print("  Added enterprise hourly profiles.")


def populate_public_service_hourly_profile(session: sqlmodel.Session, data: dict[str, typing.Any]):
    """Populate the PublicServiceHourlyProfile table."""
    print("Populating PublicServiceHourlyProfile...")

    # Check if data already exists
    if session.exec(sqlmodel.select(categories.PublicServiceHourlyProfile)).first():
        print("  PublicServiceHourlyProfile already exists, skipping.")
        return

    for subcategory, values in data["public_service_hourly_profile"].items():
        public_service_profile = categories.PublicServiceHourlyProfile(
            subcategory=subcategory, hourly_profile=values["hourly_profile"]
        )
        session.add(public_service_profile)
    session.commit()
    print("  Added public service hourly profiles.")


def populate_default_db(db_session: sqlmodel.Session) -> None:
    # Path to the JSON file
    json_file = os.path.join(
        os.path.join(os.getcwd(), "src", "scripts", "default_data", "db_data.json")
    )

    # Check if the file exists
    if not os.path.exists(json_file):
        raise FileNotFoundError(
            f"Error: Default data not loaded.. JSON file not found at {json_file}"
        )

    # Load the data
    print(f"Loading data from {json_file}...")
    data = load_json_data(json_file)

    populate_category_distribution(db_session, data)
    populate_household_data(db_session, data)
    populate_enterprise_data(db_session, data)
    populate_public_service_data(db_session, data)
    populate_household_hourly_profile(db_session, data)
    populate_enterprise_hourly_profile(db_session, data)
    populate_public_service_hourly_profile(db_session, data)

    print("Done! Database populated successfully.")
