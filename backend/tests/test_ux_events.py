"""Phone screen instrumentation (07 section 10.2): only allowed fields are stored, funnels count them.

Pins: an event with any field outside ux_event_fields.json is refused whole (never trimmed); strings are
accepted only from fixed vocabularies, so a name, number, message text, address, coordinate or query string
cannot be stored; accepted events are recorded as ``ux_event`` activity and kept out of the activity list
unless asked for; funnels hold counts and milliseconds only.
"""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import TestCase

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from postgres.models.activity_event import ActivityEvent
from services import activity_trail, ux_events

CASE_MATERIAL = ['Jordan Avery', '+12025550143', 'meet at the dock at 9', '12 Harbour Road', '40.7128,-74.0060',
                 'EXH-0042', 'select * from x', 'jordan@example.com']


class Validation(TestCase):
    def test_every_event_has_types_for_its_fields_and_required_is_a_subset(self):
        types = ux_events.FIELDS['field_types']
        for kind, fields in ux_events.FIELDS['events'].items():
            for f in fields:
                self.assertIn(f, types, kind)
            self.assertLessEqual(set(ux_events.FIELDS['required'][kind]), set(fields), kind)

    def test_a_good_event_is_kept(self):
        self.assertEqual(ux_events.clean({'event': 'journey_complete', 'journey': 'J-3', 'ms': 41234.56, 'actions': 7}),
                         {'event': 'journey_complete', 'journey': 'J-3', 'ms': 41234.6, 'actions': 7})

    def test_unknown_fields_and_events_are_refused_whole(self):
        for bad in ({'event': 'journey_start', 'journey': 'J-1', 'screen': 'phones', 'query': 'x'},
                    {'event': 'page_text', 'text': 'x'}, {'journey': 'J-1'}, 'journey_start',
                    {'event': 'journey_start', 'journey': 'J-1'}):
            with self.assertRaises(ux_events.Refused, msg=repr(bad)):
                ux_events.clean(bad)

    def test_no_case_material_can_pass_in_any_field(self):
        for kind, fields in ux_events.FIELDS['events'].items():
            base = {'event': kind}
            for f in fields:
                for value in CASE_MATERIAL:
                    with self.assertRaises(ux_events.Refused, msg=f'{kind}.{f}={value}'):
                        ux_events.clean({**base, f: value})

    def test_numbers_are_bounded_and_booleans_are_strict(self):
        for bad in ({'event': 'wait', 'screen': 'phones', 'ms': -1, 'panel': True},
                    {'event': 'wait', 'screen': 'phones', 'ms': float('inf'), 'panel': True},
                    {'event': 'wait', 'screen': 'phones', 'ms': 10, 'panel': 1},
                    {'event': 'collect', 'target_kind': 'dossier', 'count': True},
                    {'event': 'collect', 'target_kind': 'dossier', 'count': 2.5},
                    {'event': 'review_item', 'queue': 'readings', 'decision_kind': 'confirm', 'ms': 5,
                     'extraction_id': 'not-an-id'}):
            with self.assertRaises(ux_events.Refused, msg=repr(bad)):
                ux_events.clean(bad)

    def test_the_frontend_schema_is_the_same_list(self):
        ts = (Path(__file__).resolve().parents[2] / 'frontend_v2' / 'src' / 'lib' / 'ux-event-fields.json')
        self.assertEqual(json.loads(ts.read_text()), ux_events.FIELDS)


class Recording(TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://')
        ActivityEvent.__table__.create(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self.token = activity_trail._context.set(dict(address='203.0.113.7', user_agent='Mozilla/5.0 Test',
                                                     session_ref='0123456789abcdef', origin=None, path='/x'))

    def tearDown(self):
        activity_trail._context.reset(self.token)
        self.db.close()

    def test_accepted_events_are_recorded_with_session_and_kept_out_of_the_activity_list(self):
        out = ux_events.record([
            {'event': 'journey_start', 'journey': 'J-1', 'screen': 'phones'},
            {'event': 'journey_start', 'journey': 'J-1', 'screen': 'Jordan Avery'},
            {'event': 'search_empty', 'screen': 'search', 'query': 'meet at the dock'},
        ], user=None, case_id=None, db=self.db)
        self.assertEqual(out, {'accepted': 1, 'refused': 2})
        [row] = self.db.query(ActivityEvent).all()
        self.assertEqual((row.action, row.session_ref, row.user_agent), ('ux_event', '0123456789abcdef', 'Mozilla/5.0 Test'))
        self.assertEqual(row.details, {'event': 'journey_start', 'journey': 'J-1', 'screen': 'phones'})
        self.assertEqual(activity_trail.list_events(self.db)['total'], 0)
        self.assertEqual(activity_trail.list_events(self.db, action='ux_event')['total'], 1)
        stored = json.dumps([r.details for r in self.db.query(ActivityEvent)])
        for value in CASE_MATERIAL:
            self.assertNotIn(value, stored)

    def test_more_than_the_limit_is_counted_as_refused_not_dropped_silently(self):
        out = ux_events.record([{'event': 'search_empty', 'screen': 'search'}] * 60, user=None, case_id=None, db=self.db)
        self.assertEqual(out, {'accepted': 50, 'refused': 10})

    def test_funnels_count_starts_steps_completions_and_waits(self):
        now = datetime.now(timezone.utc)
        rows = [
            {'event': 'journey_start', 'journey': 'J-3', 'screen': 'conversations'},
            {'event': 'journey_start', 'journey': 'J-3', 'screen': 'conversations'},
            {'event': 'journey_step', 'journey': 'J-3', 'step': 1},
            {'event': 'journey_step', 'journey': 'J-3', 'step': 2},
            {'event': 'journey_complete', 'journey': 'J-3', 'ms': 30000},
            {'event': 'journey_abandon', 'journey': 'J-3', 'step': 2},
            {'event': 'journey_start', 'journey': 'J-10', 'screen': 'phone-review'},
            {'event': 'wait', 'screen': 'phones', 'ms': 2500, 'panel': False},
            {'event': 'wait', 'screen': 'phones', 'ms': 2500, 'panel': True},
            {'event': 'left_before_data', 'screen': 'phones', 'ms': 900},
            {'event': 'collect', 'target_kind': 'dossier', 'count': 12},
            {'event': 'review_item', 'queue': 'readings', 'decision_kind': 'confirm', 'ms': 4000},
        ]
        for d in rows:
            self.db.add(ActivityEvent(action='ux_event', at=now, details=d))
        self.db.add(ActivityEvent(action='ux_event', at=now - timedelta(days=30),
                                  details={'event': 'journey_start', 'journey': 'J-3', 'screen': 'phones'}))
        self.db.commit()
        f = ux_events.funnels(self.db, 14)
        self.assertEqual([j['journey'] for j in f['journeys']], ['J-3', 'J-10'])
        j3 = f['journeys'][0]
        self.assertEqual((j3['started'], j3['completed'], j3['abandoned'], j3['median_ms']), (2, 1, 1, 30000))
        self.assertEqual(j3['steps'], [{'step': 1, 'reached': 1}, {'step': 2, 'reached': 1}])
        self.assertEqual(f['waits'], {'over_2s': 2, 'over_2s_without_panel': 1, 'left_before_data': 1})
        self.assertEqual(f['collect'], {'actions': 1, 'records': 12})
        self.assertEqual(f['review_median_ms'], {'readings': 4000})


class PhoneRouteTiming(TestCase):
    """07 10.2: route timing extends below /cases/:id/<view>, so phone sub-pages are not "other"."""

    def test_phone_pages_are_accepted_page_names_and_match_the_frontend(self):
        import re
        from services import request_speed as rs
        for page in rs.PHONE_PAGES:
            self.assertIn(f'case/{page}', rs.PAGES)
        source = (Path(__file__).resolve().parents[2] / 'frontend_v2/src/lib/route-speed.ts').read_text()
        types = set(re.findall(r'"([a-z-]+)"', re.search(r'PHONE_RECORD_TYPES = new Set\(\[(.*?)\]\)', source, re.S).group(1)))
        self.assertEqual(types, set(rs.PHONE_RECORD_TYPES))
        named = set(re.findall(r'"(case/phone[a-z/-]*)"', source)) | {
            f'case/phones-prototype/{v}' for v in re.findall(r'"([a-z-]+)"', re.search(
                r'PROTOTYPE_VIEWS = new Set\(\[(.*?)\]\)', source, re.S).group(1))}
        named |= {f'case/{v}' for v in ('phone-review', 'phone-patterns')}
        self.assertLessEqual(named, rs.PAGES)
