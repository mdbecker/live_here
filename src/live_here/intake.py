"""Explicit reviewed incoming-file dispositions with immutable content identity."""
from pathlib import Path
from .io import sha256

DISPOSITIONS = {
    "CNBC_Quality-of-Life_Data_Research_Developer_Handoff.md": "deferred_research",
    "Retirement_Town_County_Ranking_Developer_Handoff.md": "historical_design",
    "County_Ranking_Model_Handoff_Summary.md": "historical_baseline_design",
    "Retirement_County_Ranking_Project_Developer_Handoff_Data_Quality_Gaps_Next_Steps.md": "quality_constraints",
    "County_Ranker_Project_Developer_Handoff.md": "governing_design",
    "update_walkability_and_rerun_mcmc(1).py": "source_port_script",
    "update_noaa_temperature_and_rerun_mcmc(1).py": "source_port_script",
    "update_noaa_multivariate_and_rerun_mcmc(1).py": "source_port_script",
    "update_cbp_and_rerun_mcmc(1).py": "source_port_script",
    "update_oews_trades_and_rerun_mcmc(1).py": "source_port_script",
    "update_usda_food_environment_and_rerun_mcmc(1).py": "source_port_script",
    "update_fema_nri_and_rerun_mcmc(1).py": "source_port_script",
    "update_drought_monitor_and_rerun_mcmc(1).py": "source_port_script",
    "update_transit_guardrail_and_rerun_mcmc(1).py": "source_port_script",
    "update_aqi_and_rerun_mcmc(1).py": "source_port_script",
    "update_zillow_housing_and_rerun_mcmc(1).py": "source_port_script",
    "fix_candidate_source_backed_fields_and_rerun(1).py": "historical_control_script",
    "update_proxy_reuse_and_rerun_mcmc(1).py": "deferred_proxy_script",
    "county_rankings_added_candidates_sourcefix_100k(1).xlsx": "historical_baseline_workbook",
    "added_candidate_sourcefix_rollup.csv": "historical_correction_audit",
    "county_rankings_with_preserved_woodland_estimate.xlsx": "exploratory_woodland_workbook",
    "oesm25all.zip": "source_archive",
    "oesm25st.zip": "source_archive",
    "oesm25ma.zip": "source_archive",
    "oesm25in4.zip": "source_archive",
}


def inspect_file(path):
    path = Path(path)
    if path.name not in DISPOSITIONS:
        raise ValueError(f"Incoming file has not been reviewed: {path.name}")
    return {"file": path.name, "sha256": sha256(path), "bytes": path.stat().st_size,
            "role": DISPOSITIONS[path.name], "design": "docs/design.md", "runtime_input": False}
