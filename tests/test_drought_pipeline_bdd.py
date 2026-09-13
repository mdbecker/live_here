import unittest

from live_here.pipeline import SUPPORTED


class DroughtPipelineBDD(unittest.TestCase):
    def test_given_a_source_only_drought_adapter_when_pipeline_capabilities_are_checked_then_drought_is_supported(self):
        self.assertIn("drought", SUPPORTED)


if __name__ == "__main__":
    unittest.main()
