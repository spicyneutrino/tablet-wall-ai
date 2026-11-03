"""Cheap checks for entry-evidence classification, independent of browser startup."""
import unittest
from experience_acceptance import entry_findings


class EntryEvidenceTests(unittest.TestCase):
    def test_visible_content_is_not_tied_to_fixture_count(self):
        self.assertEqual(entry_findings({"overflow":False,"targets":[{"selector":"gallery","elements":[{"inViewport":True,"centerOccluded":False}]}]}), [])

    def test_absent_and_occluded_targets_are_reported(self):
        metrics={"overflow":True,"targets":[{"selector":"show","elements":[]},{"selector":"roster","elements":[{"inViewport":True,"centerOccluded":True}]}]}
        self.assertEqual(entry_findings(metrics), ["horizontal overflow","show absent or occluded at entry","roster absent or occluded at entry"])

    def test_below_fold_target_fails_entry(self):
        self.assertEqual(len(entry_findings({"overflow":False,"targets":[{"selector":"identify","elements":[{"inViewport":False,"centerOccluded":False}]}]})),1)


if __name__ == "__main__":
    unittest.main()
