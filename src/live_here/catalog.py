"""V1 scope. Unimplemented factors are explicit, never silently synthesized."""

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Factor:
    id: str
    label: str
    unit: str
    higher_is_better: bool
    source: str
    status: str = "awaiting_source_and_port"


FACTORS = {
    f.id: f for f in (
        Factor("heat", "Expected days with maximum temperature >=90 F", "days/year", False, "NOAA normals", "csv_adapter_validated_on_2006_2020_release"),
        Factor("cold", "Expected days with maximum temperature <50 F", "days/year", False, "NOAA normals", "csv_adapter_validated_on_2006_2020_release"),
        Factor("snowfall", "Annual snowfall", "feet/year", False, "NOAA normals", "csv_adapter_validated_on_2006_2020_release"),
        Factor("drought", "D1+ drought frequency", "days/year", False, "US Drought Monitor", "csv_adapter_validated_on_latest_complete_10_year_window"),
        Factor("aqi", "Annualized days with AQI >=101", "days/year", False, "EPA AirData", "csv_adapter_validated_on_2023_2024_release"),
        Factor("walkability", "Population-weighted National Walkability Index", "index_1_20", True, "EPA NWI", "csv_adapter_validated_on_2021_release"),
        Factor("transit", "Transit access", "index_0_100", True, "EPA Access to Jobs and Workers via Transit", "csv_adapter_validated_on_EPA_Trans45_2013_release"),
        Factor("groceries", "Grocery availability with access adjustment", "stores/10k residents", True, "Census CBP + USDA Food Environment Atlas", "csv_adapter_validated_on_CBP_2023_USDA_FEA_2025"),
        Factor("specialty_groceries", "Specialty grocery proxy / lower-bound stores", "stores", True, "Archived specialty-grocery screening workbook", "xlsx_adapter_validated_on_1020_municipality_screening"),
        Factor("tradespeople", "Specialty-trade employment with occupation adjustment", "jobs/1k residents", True, "Census CBP + BLS OEWS", "csv_adapter_validated_on_CBP_2023_OEWS_May_2025"),
        Factor("housing", "Three-bedroom ZHVI", "USD", False, "Zillow", "csv_adapter_validated_on_current_county_three_bedroom_ZHVI"),
        Factor("hazard_burden", "FEMA hazard burden", "index_0_100", False, "FEMA NRI", "csv_adapter_validated_on_FEMA_NRI_v1.20_2025"),
        Factor("resilience", "FEMA-based resilience", "index_0_100", True, "FEMA NRI", "csv_adapter_validated_on_FEMA_NRI_v1.20_2025"),
    )
}

DEFERRED = (
    "academic_medical_centers", "college_students", "homelessness", "noise",
    "popular_vote_closeness", "party_affiliation_distance", "airport_access",
    "outdoor_recreation", "trees",
)


def catalog():
    return {"v1": [asdict(f) for f in FACTORS.values()], "deferred": DEFERRED,
            "exploratory": ["preserved_woodland"], "production_ready": False}
