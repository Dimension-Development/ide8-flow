"""No-network budget regressions for bounded studio benchmark runs."""

import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from generation.budget import (BudgetCancelled, BudgetExceeded,
                               BudgetEstimateExceeded, BudgetLedger,
                               BudgetPersistenceError, BudgetedClient,
                               atomic_json_writer)


class FakeClient:
    def __init__(self, create=None):
        self.calls = []
        self.create = create or (lambda **kwargs: SimpleNamespace(cost=0.2))
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        return self.create(**kwargs)


def guarded(ledger, client=None, estimate=0.4, actual=None):
    return BudgetedClient(client or FakeClient(), ledger,
                          estimate_cost=lambda request: estimate,
                          actual_cost=actual or (lambda response, request: response.cost))


class BudgetTests(unittest.TestCase):
    def test_reconciles_and_releases_unused_reservation(self):
        ledger = BudgetLedger(1)
        original = FakeClient()
        client = guarded(ledger, original)
        response = client.messages.create(model='test', max_tokens=100)
        self.assertEqual(response.cost, .2)
        self.assertEqual(original.calls, [{'model': 'test', 'max_tokens': 100}])
        self.assertEqual(ledger.snapshot()['spent_usd'], .2)
        self.assertEqual(ledger.snapshot()['reserved_usd'], 0)
        self.assertEqual(ledger.snapshot()['available_usd'], .8)

    def test_exact_decimal_boundary_is_admitted(self):
        ledger = BudgetLedger(.3)
        for _ in range(3):
            reservation = ledger.reserve(.1)
            ledger.settle(reservation, .1)
        self.assertEqual(ledger.snapshot()['spent_usd'], .3)
        self.assertEqual(ledger.snapshot()['available_usd'], 0)

    def test_over_budget_never_dispatches_and_stops_subsequent_calls(self):
        ledger = BudgetLedger(.3)
        original = FakeClient()
        with self.assertRaises(BudgetExceeded):
            guarded(ledger, original).messages.create(model='test')
        with self.assertRaises(BudgetCancelled):
            guarded(ledger, original, estimate=.1).messages.create(model='test')
        self.assertEqual(original.calls, [])

    def test_cancel_prevents_new_dispatch_and_preserves_inflight_accounting(self):
        ledger = BudgetLedger(1)
        entered, release = threading.Event(), threading.Event()

        def slow(**kwargs):
            entered.set()
            self.assertTrue(release.wait(5))
            return SimpleNamespace(cost=.2)

        original = FakeClient(slow)
        client = guarded(ledger, original)
        errors = []

        def run():
            try:
                client.messages.create(model='test')
            except BaseException as exc:
                errors.append(exc)

        thread = threading.Thread(target=run)
        thread.start()
        try:
            self.assertTrue(entered.wait(5))
            ledger.cancel()
            with self.assertRaises(BudgetCancelled):
                client.messages.create(model='test')
        finally:
            release.set()
            thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(len(original.calls), 1)
        self.assertEqual(ledger.snapshot()['spent_usd'], .2)

    def test_concurrent_reservations_cannot_oversubscribe(self):
        ledger = BudgetLedger(.5)
        barrier = threading.Barrier(8)
        admitted, rejected = [], []

        def run():
            barrier.wait(5)
            try:
                admitted.append(ledger.reserve(.3))
            except (BudgetExceeded, BudgetCancelled) as exc:
                rejected.append(exc)

        threads = [threading.Thread(target=run) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(5)
        self.assertEqual(len(admitted), 1)
        self.assertEqual(len(rejected), 7)
        self.assertEqual(ledger.snapshot()['reserved_usd'], .3)

    def test_ambiguous_exception_retains_full_reservation(self):
        def fail(**kwargs):
            raise TimeoutError('response lost')

        ledger = BudgetLedger(1)
        original = FakeClient(fail)
        client = guarded(ledger, original)
        with self.assertRaises(TimeoutError):
            client.messages.create(model='test')
        snapshot = ledger.snapshot()
        self.assertEqual(snapshot['reserved_usd'], .4)
        self.assertEqual(snapshot['spent_usd'], 0)
        self.assertEqual(snapshot['calls'][0]['status'], 'uncertain')
        with self.assertRaises(BudgetCancelled):
            client.messages.create(model='test')
        self.assertEqual(len(original.calls), 1)

    def test_missing_or_invalid_usage_retains_reservation(self):
        for invalid in (None, float('nan'), float('inf'), -1, True):
            ledger = BudgetLedger(1)
            client = guarded(ledger, actual=lambda response, request: invalid)
            with self.assertRaises(ValueError):
                client.messages.create(model='test')
            self.assertTrue(ledger.snapshot()['cancelled'])
            self.assertEqual(ledger.snapshot()['reserved_usd'], .4)

    def test_underestimate_records_actual_cost_and_stops(self):
        ledger = BudgetLedger(.5)
        original = FakeClient(lambda **kwargs: SimpleNamespace(cost=.6))
        with self.assertRaises(BudgetEstimateExceeded):
            guarded(ledger, original).messages.create(model='test')
        snapshot = ledger.snapshot()
        self.assertEqual(snapshot['spent_usd'], .6)
        self.assertEqual(snapshot['reserved_usd'], 0)
        self.assertTrue(snapshot['cancelled'])

    def test_invalid_estimates_and_streaming_do_not_dispatch(self):
        original = FakeClient()
        for invalid in (None, -1, float('inf'), float('nan'), True):
            with self.assertRaises(ValueError):
                guarded(BudgetLedger(1), original, estimate=invalid).messages.create()
        with self.assertRaises(ValueError):
            guarded(BudgetLedger(1), original).messages.create(stream=True)
        self.assertEqual(original.calls, [])

    def test_snapshot_failure_before_dispatch_fails_closed(self):
        writes = []

        def save(snapshot):
            writes.append(snapshot)
            if len(writes) > 1:
                raise OSError('disk full')

        ledger = BudgetLedger(1, on_snapshot=save)
        original = FakeClient()
        with self.assertRaises(BudgetPersistenceError):
            guarded(ledger, original).messages.create(model='test')
        self.assertEqual(original.calls, [])
        self.assertTrue(ledger.snapshot()['cancelled'])
        self.assertEqual(ledger.snapshot()['reserved_usd'], .4)

    def test_atomic_snapshot_excludes_request_content(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'audit' / 'budget.json'
            ledger = BudgetLedger(1, on_snapshot=atomic_json_writer(path))
            guarded(ledger).messages.create(model='test', messages=['private brief'])
            snapshot = json.loads(path.read_text())
            self.assertEqual(snapshot, ledger.snapshot())
            self.assertNotIn('private brief', path.read_text())
            self.assertEqual(list(path.parent.iterdir()), [path])

    def test_reservations_cannot_be_settled_twice(self):
        ledger = BudgetLedger(1)
        request_id = ledger.reserve(.4)
        ledger.settle(request_id, .2)
        with self.assertRaises(ValueError):
            ledger.settle(request_id, .1)
        self.assertEqual(ledger.snapshot()['spent_usd'], .2)


if __name__ == '__main__':
    unittest.main()
