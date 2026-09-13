"""BDD scenarios for the source-only EPA transit adapter.

These scenarios intentionally precede the adapter and its acquisition command.
The expected behavior follows the recovered 50/30/10/10 EPA SLD composite and
the design rule that counties without source coverage remain missing.
"""

import csv
import struct
import tempfile
import unittest
import zipfile
from pathlib import Path

from live_here.factors.transit import (
    build_transit_rollup,
    transit_composite,
)
from scripts.gather_transit_data import EPA_TRANSIT_URL, SOURCE_VINTAGE


class TransitBDD(unittest.TestCase):
    def test_given_epa_release_when_source_metadata_is_loaded_then_url_and_vintage_are_pinned(self):
        # Given the latest transit dataset linked by EPA's Smart Location page
        # When acquisition metadata is loaded
        # Then the exact official endpoint and its historical observation vintage are explicit
        self.assertEqual(EPA_TRANSIT_URL, "https://edg.epa.gov/data/Public/OP/SLD/SLD_Trans45_DBF.zip")
        self.assertEqual(SOURCE_VINTAGE, "EPA Access to Jobs and Workers via Transit (2013 release)")

    def test_given_four_component_values_when_composite_is_calculated_then_weights_are_50_30_10_10(self):
        # Given EPA SLD component values on their documented 0..1 scale
        # When the county composite is calculated
        score = transit_composite(0.80, 0.60, 0.40, 0.20)
        # Then TrAccess, jobs, population and workers use 50/30/10/10 weights
        self.assertAlmostEqual(score, 64.0)

    def test_given_missing_component_when_composite_is_calculated_then_score_is_missing(self):
        # Given a county whose source row is incomplete
        # When the composite is calculated
        score = transit_composite(0.80, None, 0.40, 0.20)
        # Then missingness is preserved rather than changed to zero
        self.assertIsNone(score)

    def test_given_dbf_zip_when_rollup_is_built_then_block_groups_are_aggregated_by_fips(self):
        # Given a tiny DBF with two block groups in one county
        with tempfile.TemporaryDirectory() as td:
            archive = Path(td) / "transit.zip"
            _write_dbf_zip(archive, [
                {"GEOID10": "010010001001", "TrAccess_I": 0.8, "Pct_Jobs_b": 0.6, "Pct_Pop_by": 0.4, "Pct_Wrks_b": 0.2},
                {"GEOID10": "010010001002", "TrAccess_I": 0.4, "Pct_Jobs_b": 0.2, "Pct_Pop_by": 0.2, "Pct_Wrks_b": 0.4},
            ])
            # When the source archive is normalized
            rollup, audit = build_transit_rollup(archive)
            # Then the FIPS remains a string and county means are source-derived
            self.assertEqual(audit["records_read"], 2)
            self.assertEqual(rollup["01001"]["block_groups"], 2)
            self.assertAlmostEqual(rollup["01001"]["transit_score"], 48.0)

    def test_given_county_without_dbf_coverage_when_export_is_written_then_it_is_missing(self):
        # Given a county universe larger than the EPA source coverage
        with tempfile.TemporaryDirectory() as td:
            archive = Path(td) / "transit.zip"
            _write_dbf_zip(archive, [{"GEOID10": "010010001001", "TrAccess_I": 0.8, "Pct_Jobs_b": 0.6, "Pct_Pop_by": 0.4, "Pct_Wrks_b": 0.2}])
            rollup, _ = build_transit_rollup(archive)
            # When the source is inspected for another county
            # Then no fallback estimate is fabricated
            self.assertNotIn("01003", rollup)


def _write_dbf_zip(path, rows):
    fields = [("GEOID10", "C", 12, 0), ("TrAccess_I", "N", 10, 3),
              ("Pct_Jobs_b", "N", 10, 3), ("Pct_Pop_by", "N", 10, 3),
              ("Pct_Wrks_b", "N", 10, 3)]
    header_len = 32 + 32 * len(fields) + 1
    record_len = 1 + sum(field[2] for field in fields)
    data = bytearray(struct.pack("<BBBBIHH20x", 3, 126, 1, 1, len(rows), header_len, record_len))
    for name, kind, length, decimals in fields:
        desc = bytearray(32)
        desc[: len(name)] = name.encode("ascii")
        desc[11] = ord(kind)
        desc[16] = length
        desc[17] = decimals
        data.extend(desc)
    data.append(0x0D)
    for row in rows:
        record = bytearray(b" ")
        for name, kind, length, decimals in fields:
            value = row[name]
            text = str(value) if kind == "C" else f"{value:.{decimals}f}"
            record.extend(text.rjust(length).encode("ascii"))
        data.extend(record)
    data.append(0x1A)
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("SLD_Trans45.dbf", data)


if __name__ == "__main__":
    unittest.main()
