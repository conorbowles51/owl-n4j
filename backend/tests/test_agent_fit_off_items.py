"""lx-agentquick G: an agent-fit item that is off has an owner, a reason and a next-measurement date that has not
passed. Fails on the code before: nothing recorded why an item was off or when it would be measured again."""
import datetime
import unittest

from services.agent import fit


class OffItems(unittest.TestCase):
    def test_every_item_is_on_or_has_an_owner_a_reason_and_a_future_date(self):
        for item in fit.ITEMS:
            if item in fit.ON_BY_DEFAULT:
                continue
            self.assertIn(item, fit.OFF_ITEMS, "item %s is off with no owner, reason and date" % item)
            owner, reason, date = fit.OFF_ITEMS[item]
            self.assertTrue(owner.strip(), item)
            self.assertGreater(len(reason.strip()), 20, item)
            when = datetime.date.fromisoformat(date)
            self.assertGreaterEqual(when, datetime.date.today(),
                                    "item %s: its next measurement date %s has passed; measure it or move the date "
                                    "with the result" % (item, date))

    def test_an_item_that_is_on_is_not_listed_as_off(self):
        for item in fit.ON_BY_DEFAULT:
            self.assertNotIn(item, fit.OFF_ITEMS)


if __name__ == "__main__":
    unittest.main()
