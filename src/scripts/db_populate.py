import os
import geopandas as gpd
import pandas as pd
import sqlmodel
import numpy as np
import shapely

import app.grid.domain as grid


CLASS_DICT = {
    "electric_grid": grid.GridDistributionLine,
    "mini-grids (points)": grid.MiniGrid,
    "centroids_buildings_20km": grid.Building,
    "polygons_buildings_20km": grid.Building,
}


### Cleaning functions
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


def clean_building_centroids(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    gdf = gdf.iloc[:120000, :]

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
    gdf = gdf.iloc[:120000, :]
    gdf = gdf.dropna(subset=["building_i"])  # type: ignore
    gdf["id_shp"] = pd.to_numeric(gdf["building_i"], errors="coerce").astype("Int64")  # type: ignore
    gdf_clean = gdf.loc[:, ["id_shp", "geometry"]].copy()
    gdf_clean["pg_geography"] = gdf_clean["geometry"].apply(lambda geom: geom.wkt if geom else None)  # type: ignore
    return gdf_clean.drop(columns="geometry").replace({np.nan: None})  # type: ignore


def populate_db(db_session: sqlmodel.Session) -> None:
    raw = os.path.join(os.getcwd(), "src", "scripts", "raw_data")
    shp_files = {f[:-4]: f for f in os.listdir(raw) if f.endswith(".shp")}
    files_by_model = {}
    for basename, model in CLASS_DICT.items():
        if basename in shp_files:
            files_by_model.setdefault(model, []).append(shp_files[basename])  # type: ignore

    for model, files in files_by_model.items():  # type: ignore
        if model.__tablename__ == "buildings":  # type: ignore
            if db_session.exec(sqlmodel.select(model).limit(1)).first():  # type: ignore
                print("🏠 Buildings table already populated, skipping.")
                continue

            if set(files) >= {"centroids_buildings_20km.shp", "polygons_buildings_20km.shp"}:  # type: ignore
                cent = clean_building_centroids(
                    gpd.read_file(os.path.join(raw, "centroids_buildings_20km.shp"))  # type: ignore
                )
                poly = clean_building_polygons(
                    gpd.read_file(os.path.join(raw, "polygons_buildings_20km.shp"))  # type: ignore
                )

                merged = pd.merge(  # type: ignore
                    cent, poly, on="id_shp", how="outer", suffixes=("", "_poly")
                ).replace({np.nan: None})

                objs = [model(**rec) for rec in merged.to_dict("records")]  # type: ignore
                db_session.bulk_save_objects(objs)  # type: ignore
                db_session.commit()
                print(f"✔️ Inserted {len(objs)} buildings.")  # type: ignore
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
        else:
            clean = gdf

        df = clean.replace({np.nan: None})  # type: ignore
        objs = [model(**rec) for rec in df.to_dict("records")]  # type: ignore
        db_session.bulk_save_objects(objs)  # type: ignore
        db_session.commit()
        print(f"✔️ Inserted `{model.__tablename__}`: {len(objs)} records.")  # type: ignore
