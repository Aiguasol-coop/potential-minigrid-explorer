import sqlmodel
import sqlalchemy
from geoalchemy2 import Geometry
from geoalchemy2 import functions as geofunc
from typing import Any
from sqlalchemy.sql.elements import ColumnElement
import pydantic
import pandas as pd
import datetime

import app.db.core as db
from app.features.domain import Building
import app.profiles.domain as profiles
import app.explorations.domain as explorations


class ElectricalDemand(pydantic.BaseModel):
    area_type: str
    total_annual_demand: float
    hourly_annual_demand: dict[str, float]


class ExistingPublicBuilding(pydantic.BaseModel):
    num_hospitals: int
    num_hospital_first: int
    num_hospital_primary: int
    num_hospital_secondary: int

    num_schools: int
    num_school_primary: int
    num_school_secondary: int

    def get(self, key: str, default: int = 0) -> int:
        """Get the value of a key, returning default if the key does not exist."""
        return getattr(self, key, default)


CLASS_CONVERSION = {
    # 30-60 beds
    #
    # Low/moderate energy requirements. Lighting during evening hours and maintaining the cold chain
    # for vaccines, blood, and other medical supplies
    "Health_Clinic": "hospital_first",
    # No beds other than for emergencies/ maternity care
    #
    # Low energy requirements. Typically located in a remote setting with limited services and a
    # small staff. Typically operates weekdays
    "Health_CHPS": "hospital_primary",
    # 60-120 beds
    #
    #  Moderate energy requirements. May accommodate sophisticated diagnostic medical equipment
    "Health_Health Centre": "hospital_secondary",
    "Education_Primary School": "school_primary",
    "Education_Secondary School": "school_secondary",
}


def get_keys_from_value(d: dict[str, str], value: str) -> str:
    keys = [k for k, v in d.items() if v == value]
    return keys[0] if keys else ""


def convert_hourly_demand_to_df(hourly_demand_dict: dict[str, dict[str, float]]) -> pd.DataFrame:
    # Create empty DataFrame
    df = pd.DataFrame()

    # For each subcategory in the hourly demand dictionary
    for subcategory, time_data in hourly_demand_dict.items():
        # Create a Series for this subcategory
        series = pd.Series(time_data, name=subcategory)

        # Add the Series as a column to the DataFrame
        df[subcategory] = series

    # Convert time strings to proper time index
    # Extract hours from time strings like "0:00-1:00"
    df.index = pd.Index([int(time.split(":")[0]) for time in df.index])

    return df


def classify_area_type(df_centroids: pd.DataFrame) -> str:
    mean_dist_to_road_km = df_centroids["distance_to_road"].mean() / 1000
    return "periurban" if mean_dist_to_road_km < 5 else "isolated"


def get_theoretical_distribution(df_centroids: pd.DataFrame, session: db.Session) -> dict[str, int]:
    category_distribution_obj = session.exec(
        sqlmodel.select(explorations.CategoryDistribution)
    ).first()
    if not category_distribution_obj:
        raise ValueError("No CategoryDistribution data found in the database.")

    centroid_category_distribution = category_distribution_obj.model_dump()

    theoretical = {
        "public_services": round(
            centroid_category_distribution["public_services"] * df_centroids.shape[0]
        ),
        "enterprises": round(centroid_category_distribution["enterprises"] * df_centroids.shape[0]),
        "households": round(centroid_category_distribution["households"] * df_centroids.shape[0]),
    }

    total_theoretical = sum(theoretical.values())
    total_centroids = df_centroids.shape[0]

    if total_theoretical != total_centroids:
        difference = total_centroids - total_theoretical
        theoretical["households"] += difference

    return theoretical


def build_demand(
    subcategory_data_dict: dict[str, dict[str, float]],
    total_count: int,
    existing_categories: ExistingPublicBuilding | None = None,
) -> dict[str, dict[str, float]]:
    demand: dict[str, dict[str, float]] = {}
    for subcategory, data in subcategory_data_dict.items():
        demand[subcategory] = {
            "kwh_per_day": data["kwh_per_day"],
            "consumers": round(data["distribution"] * total_count),
        }

    if existing_categories:
        existing_public: dict[str, int] = {}
        for building_type, c in existing_categories.model_dump().items():
            if c > 0 and building_type not in ["num_hospitals", "num_schools"]:
                mapped = get_keys_from_value(CLASS_CONVERSION, building_type.replace("num_", ""))
                existing_public[mapped] = c
        for sub, c in existing_public.items():
            if sub in demand:
                demand[sub]["consumers"] = max(demand[sub]["consumers"], c)

    return demand


def adjust_distribution(
    category_demand: dict[str, dict[str, float]],
    category_distribution: dict[str, dict[str, float]],
    theoretical_category_consumers: int,
    total_category_consumers: int,
):
    diff = theoretical_category_consumers - total_category_consumers
    if diff == 0:
        return category_demand

    # Sort categories by probability
    sorted_categories = sorted(
        category_distribution.items(), key=lambda kv: kv[1].get("distribution", 0), reverse=True
    )

    remaining = diff
    while remaining > 0:
        # Candidates = first try with 0-consumer categories
        candidates = [cat for cat, _ in sorted_categories if category_demand[cat]["consumers"] == 0]

        # If none left, use all categories
        if not candidates:
            candidates = [cat for cat, _ in sorted_categories]

        # Distribute 1-by-1 to avoid dumping all in one
        for cat in candidates:
            if remaining == 0:
                break
            category_demand[cat]["consumers"] += 1
            remaining -= 1

    return category_demand


def expand_hourly(
    daily_demand: dict[str, float],
    session: db.Session,
    ProfileModel: type[profiles.HouseholdHourlyProfile]
    | type[profiles.EnterpriseHourlyProfile]
    | type[profiles.PublicServiceHourlyProfile],
    area_type: str | None = None,
) -> dict[str, dict[str, float]]:
    result: dict[str, dict[str, float]] = {}
    for subcategory in daily_demand.keys():
        result[subcategory] = {}
        query = sqlmodel.select(ProfileModel).where(ProfileModel.subcategory == subcategory)
        if area_type and ProfileModel is profiles.HouseholdHourlyProfile:
            query = query.where(ProfileModel.area_type == area_type)

        profile_obj: (
            profiles.HouseholdHourlyProfile
            | profiles.EnterpriseHourlyProfile
            | profiles.PublicServiceHourlyProfile
        ) = session.exec(query).one()
        profile: dict[str, float] = profile_obj.hourly_profile

        for time, coef in profile.items():
            result[subcategory][time] = coef * daily_demand[subcategory]
    return result


def build_annual_demand(
    household_hourly: dict[str, dict[str, float]],
    enterprise_hourly: dict[str, dict[str, float]],
    public_service_hourly: dict[str, dict[str, float]],
    area_type: str,
) -> ElectricalDemand:
    households_df = convert_hourly_demand_to_df(household_hourly)
    enterprises_df = convert_hourly_demand_to_df(enterprise_hourly)
    public_services_df = convert_hourly_demand_to_df(public_service_hourly)

    daily_hourly_demand = (
        households_df.add(enterprises_df, fill_value=0)  # pyright: ignore[reportUnknownMemberType]
        .add(public_services_df, fill_value=0)  # pyright: ignore[reportUnknownMemberType]
        .sum(axis=1)  # type: ignore
    )

    year = datetime.datetime.now().year
    date_range = pd.date_range(start=f"1/1/{year}", periods=365 * 24, freq="h")

    hourly_annual_demand = pd.Series(index=date_range)
    for day in range(365):
        for hour in range(24):
            hourly_annual_demand.iloc[day * 24 + hour] = daily_hourly_demand[hour]

    hourly_annual_demand.index = hourly_annual_demand.index.strftime("%Y-%m-%d %H:%M:%S")  # type: ignore
    hourly_annual_demand_dict = hourly_annual_demand.to_dict()  # type: ignore

    return ElectricalDemand(
        area_type=area_type,
        total_annual_demand=float(hourly_annual_demand.sum()),
        hourly_annual_demand=hourly_annual_demand_dict,
    )


def calculate_demand(cluster_centroids: list[Building], session: db.Session) -> ElectricalDemand:
    df_centroids = pd.DataFrame(
        [
            centroid.model_dump(
                exclude={"geography", "pg_geography", "pg_geography_centroid", "geography_centroid"}
            )
            for centroid in cluster_centroids
        ]
    )

    area_type = classify_area_type(df_centroids)

    theoretical_distribution = get_theoretical_distribution(df_centroids, session)

    existing_categories: ExistingPublicBuilding = ExistingPublicBuilding(
        num_hospitals=len(df_centroids[df_centroids["building_type"] == "hospital"]),
        num_hospital_first=len(
            df_centroids[
                (df_centroids["building_type"] == "hospital")
                & (df_centroids["category"] == "First")
            ]
        ),
        num_hospital_primary=len(
            df_centroids[
                (df_centroids["building_type"] == "hospital")
                & (df_centroids["category"] == "Primary")
            ]
        ),
        num_hospital_secondary=len(
            df_centroids[
                (df_centroids["building_type"] == "hospital")
                & (df_centroids["category"] == "Secondary")
            ]
        ),
        num_schools=len(df_centroids[df_centroids["building_type"] == "school"]),
        num_school_primary=len(
            df_centroids[
                (df_centroids["building_type"] == "school")
                & (df_centroids["category"] == "primary")
            ]
        ),
        num_school_secondary=len(
            df_centroids[
                (df_centroids["building_type"] == "school")
                & (df_centroids["category"] == "secondary")
            ]
        ),
    )

    current_public_services = existing_categories.num_hospitals + existing_categories.num_schools
    if current_public_services > theoretical_distribution["public_services"]:
        exceeding = current_public_services - theoretical_distribution["public_services"]
        theoretical_distribution["public_services"] = current_public_services
        if theoretical_distribution["enterprises"] > exceeding:
            theoretical_distribution["enterprises"] -= exceeding
        else:
            still_exceeding = exceeding - theoretical_distribution["enterprises"]
            theoretical_distribution["enterprises"] = 0
            theoretical_distribution["households"] = max(
                0, theoretical_distribution["households"] - still_exceeding
            )

    households_subcategory_data = list(
        session.exec(
            sqlmodel.select(profiles.HouseholdData).where(
                profiles.HouseholdData.area_type == area_type
            )
        ).all()
    )
    households_subcategory_data_dict = {
        sub.subcategory: sub.as_dict for sub in households_subcategory_data
    }

    enterprise_subcategory_data = list(
        session.exec(
            sqlmodel.select(profiles.EnterpriseData).where(
                profiles.EnterpriseData.area_type == area_type
            )
        ).all()
    )
    enterprise_subcategory_data_dict = {
        sub.subcategory: sub.as_dict for sub in enterprise_subcategory_data
    }

    public_services_subcategory_data = list(
        session.exec(
            sqlmodel.select(profiles.PublicServiceData).where(
                profiles.PublicServiceData.area_type == area_type
            )
        ).all()
    )
    public_services_subcategory_data_dict = {
        sub.subcategory: sub.as_dict for sub in public_services_subcategory_data
    }

    household_demand = build_demand(
        households_subcategory_data_dict, theoretical_distribution["households"]
    )
    enterprise_demand = build_demand(
        enterprise_subcategory_data_dict, theoretical_distribution["enterprises"]
    )
    public_service_demand = build_demand(
        public_services_subcategory_data_dict,
        theoretical_distribution["public_services"],
        existing_categories,
    )

    total_households = int(sum(d["consumers"] for d in household_demand.values()))
    total_enterprises = int(sum(d["consumers"] for d in enterprise_demand.values()))
    total_public = int(sum(d["consumers"] for d in public_service_demand.values()))

    household_demand = adjust_distribution(
        household_demand,
        households_subcategory_data_dict,
        theoretical_distribution["households"],
        total_households,
    )
    enterprise_demand = adjust_distribution(
        enterprise_demand,
        enterprise_subcategory_data_dict,
        theoretical_distribution["enterprises"],
        total_enterprises,
    )
    public_service_demand = adjust_distribution(
        public_service_demand,
        public_services_subcategory_data_dict,
        theoretical_distribution["public_services"],
        total_public,
    )

    total_household_daily = {
        s: d["kwh_per_day"] * d["consumers"] for s, d in household_demand.items()
    }
    total_enterprise_daily = {
        s: d["kwh_per_day"] * d["consumers"] for s, d in enterprise_demand.items()
    }
    total_public_daily = {
        s: d["kwh_per_day"] * d["consumers"] for s, d in public_service_demand.items()
    }

    total_household_hourly = expand_hourly(
        total_household_daily, session, profiles.HouseholdHourlyProfile, area_type
    )
    total_enterprise_hourly = expand_hourly(
        total_enterprise_daily, session, profiles.EnterpriseHourlyProfile
    )
    total_public_service_hourly = expand_hourly(
        total_public_daily, session, profiles.PublicServiceHourlyProfile
    )

    result = build_annual_demand(
        total_household_hourly, total_enterprise_hourly, total_public_service_hourly, area_type
    )

    return result


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

        print(f"Hourly Annual Demand: {demand.hourly_annual_demand}")
        print(f"Total Annual Demand: {demand.total_annual_demand}")
