"""The demo seed never shows the job's name to someone walking the demo case (23 Nov: every dossier ended
'Seed entry for the demo case (lx-demo).'), and retag rewrites what an older seed wrote."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
import demo_seed as seed  # noqa: E402

OLD = "Owner of Penn's Used Tools. Seed entry for the demo case (lx-demo)."


class DemoSeedLabel(unittest.TestCase):
    def test_label_names_no_job(self):
        self.assertNotIn("lx-", seed.SEED)
        self.assertEqual(seed.SEED, "Seed entry for the demo case.")
        with open(seed.__file__) as f:
            named = [line.strip() for line in f if "demo case (lx-" in line]
        self.assertEqual(named, ['OLD_SEED = "Seed entry for the demo case (lx-demo)"'])

    def test_retag_rewrites_every_old_label_through_the_item_routes(self):
        dossiers = [{"id": "d1", "display_name": "Gary Penn", "summary": OLD},
                    {"id": "d2", "display_name": "New", "summary": "Fine. " + seed.SEED}]
        details = {"d1": {"interviews": [{"id": "i1", "working_notes": "Proffer. Seed entry for the demo case (lx-demo)."}]}}
        tasks = [{"id": "t1", "title": "Subpoena", "description": "Gate log. Seed entry for the demo case (lx-demo)."}]
        notes = [{"id": "n1", "title": "Bay 4", "body": "Rent. Seed entry for the demo case (lx-demo)."}]
        theories = [{"id": "e1", "title": "T1", "version": 3, "body": "Bay 4. Seed entry for the demo case (lx-demo)."}]
        mandate = {"objective": "Defence. Seed entry for the demo case (lx-demo); all invented.",
                   "key_questions": ["Where?"], "perspective": "Defence", "out_of_scope": None}
        plan = seed.retag_plan(dossiers, details, tasks, notes, theories, mandate)
        paths = [(m, p) for _, m, p, _ in plan]
        self.assertEqual(paths, [
            ("PATCH", "/api/dossiers/d1"), ("PATCH", "/api/dossiers/d1/interviews/i1"),
            ("PATCH", f"/api/workspace/{seed.C}/tasks/t1"), ("PATCH", f"/api/notebook/{seed.C}/notes/n1"),
            ("PATCH", f"/api/workspace/{seed.C}/entries/e1"), ("POST", f"/api/workspace/{seed.C}/context/mandates")])
        self.assertEqual(plan[0][3], {"summary": "Owner of Penn's Used Tools. Seed entry for the demo case."})
        self.assertEqual(plan[4][3], {"body": "Bay 4. Seed entry for the demo case.", "expected_version": 3})
        self.assertEqual(plan[-1][3], {"objective": "Defence. Seed entry for the demo case; all invented.",
                                       "key_questions": ["Where?"], "perspective": "Defence"})
        for _, _, _, body in plan:
            self.assertNotIn("lx-demo", str(body))
        # A rerun after the rewrite finds nothing.
        self.assertEqual(seed.retag_plan(dossiers[1:], {}, [], [], [], None), [])


if __name__ == "__main__":
    unittest.main()
