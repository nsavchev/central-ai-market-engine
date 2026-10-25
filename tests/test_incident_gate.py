"""A11.15.14 fail-closed incident identity boundary for FIX staging."""
import sqlite3
import unittest
from test_fix_staging_integration import FixStagingIntegrationTests


class IncidentGateTests(FixStagingIntegrationTests):
    def test_missing_incident_rejected_without_reservation(self):
        with sqlite3.connect(self.path) as db:
            db.execute("DELETE FROM fix_incidents")
        self.assertEqual(self.stage_child()["reason"], "INCIDENT_NOT_AUTHORIZED")
        self.assertEqual(self.counts(), (0, 0, 0, (0, 0)))

    def test_terminal_incident_rejected(self):
        with sqlite3.connect(self.path) as db:
            db.execute("UPDATE fix_incidents SET status='ESCALATED'")
        self.assertEqual(self.stage_child()["reason"], "INCIDENT_NOT_AUTHORIZED")
        self.assertEqual(self.counts(), (0, 0, 0, (0, 0)))

    def test_wrong_incident_source_rejected(self):
        with sqlite3.connect(self.path) as db:
            db.execute("UPDATE fix_incidents SET source_task_id='unrelated'")
        self.assertEqual(self.stage_child()["reason"], "INCIDENT_NOT_AUTHORIZED")
        self.assertEqual(self.counts(), (0, 0, 0, (0, 0)))

    def test_registered_incident_accepted(self):
        self.assertTrue(self.stage_child()["staged"])


if __name__ == "__main__":
    unittest.main()
