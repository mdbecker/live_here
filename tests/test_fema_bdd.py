"""BDD scenarios for the FEMA NRI source adapter (red before implementation)."""

import csv
import io
import tempfile
import unittest
import zipfile
from pathlib import Path

from live_here.factors.fema import (
    ALL_HAZARD_PREFIXES,
    CLIMATE_HAZARD_PREFIXES,
    hazard_burden_score,
    percentile_scores,
    read_nri_zip,
    resilience_score,
)


class FEMAAdapterBDD(unittest.TestCase):
    def test_given_nri_components_when_burden_is_calculated_then_weights_are_source_only(self):
        # 0.40*50 + 0.30*80 + 0.30*20 = 50; no workbook quantile mapping.
        self.assertAlmostEqual(hazard_burden_score(50, 80, 20), 50.0)

    def test_given_nri_components_when_resilience_is_calculated_then_inverse_risks_are_used(self):
        expected = 0.45 * 60 + 0.30 * (100 - 20) + 0.15 * (100 - 40) + 0.10 * (100 - 30)
        self.assertAlmostEqual(resilience_score(60, 20, 40, 30), expected)
        self.assertEqual(resilience_score(0, 200, -10, 300), 0.0)

    def test_given_missing_or_fema_sentinel_values_when_score_is_calculated_then_result_is_missing(self):
        self.assertIsNone(hazard_burden_score(None, 40, 50))
        self.assertIsNone(resilience_score(60, None, 40, 30))

    def test_given_nri_frequency_values_when_percentiles_are_calculated_then_ties_are_average(self):
        self.assertEqual(percentile_scores([1, 1, 3]), [0.25, 0.25, 1.0])

    def test_given_official_shaped_county_zip_when_read_then_rows_and_audit_are_returned(self):
        fields = [
            "STCOFIPS", "COUNTY", "COUNTYTYPE", "STATEABBRV", "POPULATION",
            "EAL_SCORE", "ALR_VRA_NPCTL", "ALR_NPCTL", "SOVI_SCORE", "RESL_SCORE",
        ]
        fields += [f"{prefix}_RISKS" for prefix in CLIMATE_HAZARD_PREFIXES]
        fields += [f"{prefix}_{suffix}" for prefix in ALL_HAZARD_PREFIXES for suffix in ("AFREQ", "EVNTS")]
        rows = []
        for fips, eal, alr, sovi, resl, cfld, hwav in (
            ("01001", "50", "80", "30", "60", "20", "40"),
            ("01003", "40", "20", "20", "70", "10", "30"),
        ):
            row = {field: "0" for field in fields}
            for field in (f"{prefix}_RISKS" for prefix in CLIMATE_HAZARD_PREFIXES):
                row[field] = ""
            row.update({"STCOFIPS": fips, "EAL_SCORE": eal, "ALR_VRA_NPCTL": alr,
                        "SOVI_SCORE": sovi, "RESL_SCORE": resl, "CFLD_RISKS": cfld,
                        "HWAV_RISKS": hwav, "CFLD_AFREQ": "1.5", "HWAV_AFREQ": "2.5",
                        "CFLD_EVNTS": "3", "HWAV_EVNTS": "4"})
            rows.append(row)
        payload = io.StringIO()
        writer = csv.DictWriter(payload, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
        with tempfile.TemporaryDirectory() as td:
            archive = Path(td) / "nri.zip"
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("NRI_Table_Counties.csv", payload.getvalue())
            parsed, audit = read_nri_zip(archive)
        self.assertEqual(set(parsed), {"01001", "01003"})
        self.assertEqual(audit["rows_read"], 2)
        self.assertAlmostEqual(parsed["01001"]["hazard_frequency_per_decade"], 40.0)
        self.assertAlmostEqual(parsed["01001"]["climate_hazard_risk_score"], 30.0)

    def test_given_missing_required_hazard_header_when_read_then_source_is_rejected(self):
        """Given an incomplete NRI schema, when read, then it cannot imply zero risk."""
        payload = io.StringIO()
        writer = csv.DictWriter(payload, fieldnames=["STCOFIPS", "EAL_SCORE", "ALR_VRA_NPCTL", "SOVI_SCORE", "RESL_SCORE"])
        writer.writeheader()
        writer.writerow({"STCOFIPS": "01001", "EAL_SCORE": "50", "ALR_VRA_NPCTL": "60", "SOVI_SCORE": "30", "RESL_SCORE": "70"})
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "nri.csv"
            source.write_text(payload.getvalue())
            with self.assertRaisesRegex(ValueError, "missing required NRI fields"):
                read_nri_zip(source)

    def test_given_non_applicable_hazard_blanks_when_read_then_audit_distinguishes_them_from_missing_headers(self):
        """Given published blank hazard cells, when read, then they are audited as non-applicable components."""
        fields = [
            "STCOFIPS", "EAL_SCORE", "ALR_VRA_NPCTL", "SOVI_SCORE", "RESL_SCORE",
            "CFLD_RISKS", "CWAV_RISKS", "DRGT_RISKS", "HWAV_RISKS", "HRCN_RISKS", "IFLD_RISKS", "SWND_RISKS", "WFIR_RISKS", "WNTW_RISKS",
        ]
        fields += [f"{prefix}_{suffix}" for prefix in (
            "AVLN", "CFLD", "CWAV", "DRGT", "ERQK", "HAIL", "HWAV", "HRCN", "ISTM", "IFLD", "LNDS", "LTNG", "SWND", "TRND", "TSUN", "VLCN", "WFIR", "WNTW"
        ) for suffix in ("AFREQ", "EVNTS")]
        row = {field: "0" for field in fields}
        row.update({"STCOFIPS": "01001", "CFLD_AFREQ": "", "CFLD_EVNTS": "", "CFLD_RISKS": ""})
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "nri.csv"
            with source.open("w", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=fields)
                writer.writeheader(); writer.writerow(row)
            parsed, audit = read_nri_zip(source)
        self.assertEqual(parsed["01001"]["hazard_frequency_per_decade"], 0.0)
        self.assertEqual(parsed["01001"]["climate_hazard_component_count"], 8)
        self.assertEqual(audit["non_applicable_frequency_components"], 1)
        self.assertEqual(audit["non_applicable_climate_risk_components"], 1)

    def test_given_sentinel_hazard_component_when_read_then_frequency_is_missing_not_zero(self):
        """Given an unavailable NRI component, when read, then burden eligibility is withheld."""
        fields = [
            "STCOFIPS", "EAL_SCORE", "ALR_VRA_NPCTL", "SOVI_SCORE", "RESL_SCORE",
            "CFLD_RISKS", "CWAV_RISKS", "DRGT_RISKS", "HWAV_RISKS", "HRCN_RISKS", "IFLD_RISKS", "SWND_RISKS", "WFIR_RISKS", "WNTW_RISKS",
        ]
        fields += [f"{prefix}_{suffix}" for prefix in (
            "AVLN", "CFLD", "CWAV", "DRGT", "ERQK", "HAIL", "HWAV", "HRCN", "ISTM", "IFLD", "LNDS", "LTNG", "SWND", "TRND", "TSUN", "VLCN", "WFIR", "WNTW"
        ) for suffix in ("AFREQ", "EVNTS")]
        row = {field: "0" for field in fields}
        row.update({"STCOFIPS": "01001", "CFLD_AFREQ": "-9999"})
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "nri.csv"
            with source.open("w", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=fields)
                writer.writeheader(); writer.writerow(row)
            parsed, audit = read_nri_zip(source)
        self.assertIsNone(parsed["01001"]["hazard_frequency_per_decade"])
        self.assertEqual(audit["unavailable_frequency_components"], 1)


if __name__ == "__main__":
    unittest.main()
