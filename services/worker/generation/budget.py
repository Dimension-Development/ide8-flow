"""Provider-neutral, synchronous guard for an injected ``client.messages.create``.

Example::

    ledger = BudgetLedger(10, on_snapshot=atomic_json_writer(output / 'budget.json'))
    client = BudgetedClient(sdk_client, ledger,
                            estimate_cost=conservative_request_maximum,
                            actual_cost=price_response_usage)

The estimator receives the request kwargs and MUST bound all billable input,
output and provider-specific charges. The accounting callback receives
``(response, request)``. Both return finite nonnegative USD values. This module
does not guess prices or tokenize prompts. Disable SDK retries in the caller:
one reservation covers one dispatch, not hidden repeated requests. Streaming is
rejected because its final usage cannot be reconciled synchronously.

Cancellation prevents subsequent dispatches; calls already admitted may finish.
Unknown outcomes retain their entire reservation and cancel further work.
An underestimated response is recorded at its actual cost and stops the batch;
no local guard can retroactively prevent an incorrect estimate from overspending.
Snapshot callbacks run serially under the ledger lock, must not reenter the
ledger, and must succeed before a reserved request can be dispatched. Snapshots
contain accounting metadata, never prompts, images, credentials or responses.
"""

import copy
import json
import os
import tempfile
import threading
from decimal import Decimal, InvalidOperation
from pathlib import Path
from types import SimpleNamespace


class BudgetStop(RuntimeError):
    """The batch must stop before making another paid request."""


class BudgetCancelled(BudgetStop):
    pass


class BudgetExceeded(BudgetStop):
    pass


class BudgetEstimateExceeded(BudgetStop):
    pass


class BudgetPersistenceError(BudgetStop):
    pass


def _usd(value):
    if isinstance(value, bool):
        raise ValueError('USD must be a finite nonnegative number')
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError('USD must be a finite nonnegative number') from None
    if not number.is_finite() or number < 0:
        raise ValueError('USD must be a finite nonnegative number')
    return number


def atomic_json_writer(path):
    """Return a snapshot callback that atomically replaces one JSON file.

    The caller chooses the output location. Parent directories are created on
    first write; a failed write leaves the previous complete snapshot intact.
    """
    path = Path(path)

    def write(snapshot):
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8',
                                             dir=path.parent, delete=False) as out:
                temporary = out.name
                json.dump(snapshot, out, indent=2, allow_nan=False)
                out.write('\n')
                out.flush()
                os.fsync(out.fileno())
            os.replace(temporary, path)
            temporary = None
        finally:
            if temporary is not None:
                os.unlink(temporary)

    return write


class BudgetLedger:
    """One shared reservation ledger for every concurrent client in a batch.

    Keep this object alive for the entire batch. JSON snapshots are an audit
    record, not an automatic resume mechanism; do not restart with a fresh
    allowance after uncertain or partially completed work.
    """

    def __init__(self, limit_usd, *, on_snapshot=None):
        self._limit = _usd(limit_usd)
        self._lock = threading.Lock()
        self._on_snapshot = on_snapshot
        self._cancelled = False
        self._reason = None
        self._calls = []
        self._publish()

    def _totals(self):
        spent = sum((c['actual'] for c in self._calls
                     if c['actual'] is not None), Decimal(0))
        reserved = sum((c['estimate'] for c in self._calls
                        if c['actual'] is None), Decimal(0))
        return spent, reserved

    def _snapshot(self):
        spent, reserved = self._totals()
        return {
            'limit_usd': float(self._limit), 'spent_usd': float(spent),
            'reserved_usd': float(reserved),
            'available_usd': float(max(Decimal(0), self._limit - spent - reserved)),
            'cancelled': self._cancelled, 'reason': self._reason,
            'calls': [{
                'id': c['id'], 'model': c['model'], 'status': c['status'],
                'reserved_usd': float(c['estimate']),
                'actual_usd': float(c['actual']) if c['actual'] is not None else None,
            } for c in self._calls],
        }

    def snapshot(self):
        with self._lock:
            return self._snapshot()

    def _publish(self):
        if self._on_snapshot is not None:
            try:
                self._on_snapshot(copy.deepcopy(self._snapshot()))
            except Exception as exc:
                self._cancelled = True
                self._reason = 'budget snapshot persistence failed'
                raise BudgetPersistenceError(self._reason) from exc

    def cancel(self, reason='cancelled by operator'):
        with self._lock:
            self._cancelled = True
            self._reason = reason
            self._publish()

    def reserve(self, estimate_usd, *, model=None):
        estimate = _usd(estimate_usd)
        with self._lock:
            if self._cancelled:
                raise BudgetCancelled(self._reason)
            spent, reserved = self._totals()
            if spent + reserved + estimate > self._limit:
                self._cancelled = True
                self._reason = 'request reservation exceeds remaining batch budget'
                self._publish()
                raise BudgetExceeded(self._reason)
            request_id = len(self._calls) + 1
            self._calls.append({'id': request_id, 'model': model,
                                'estimate': estimate, 'actual': None,
                                'status': 'reserved'})
            self._publish()
            return request_id

    def _pending(self, request_id):
        if (not isinstance(request_id, int) or isinstance(request_id, bool)
                or not 1 <= request_id <= len(self._calls)):
            raise ValueError('unknown reservation')
        call = self._calls[request_id - 1]
        if call['status'] != 'reserved':
            raise ValueError('reservation already finalized')
        return call

    def uncertain(self, request_id):
        """Retain a reservation when dispatch/accounting has unknown results."""
        with self._lock:
            call = self._pending(request_id)
            call['status'] = 'uncertain'
            self._cancelled = True
            self._reason = 'request outcome or usage is uncertain'
            self._publish()

    def settle(self, request_id, actual_usd):
        actual = _usd(actual_usd)
        with self._lock:
            call = self._pending(request_id)
            call['actual'] = actual
            call['status'] = 'settled'
            underestimated = actual > call['estimate']
            if underestimated:
                self._cancelled = True
                self._reason = 'actual request cost exceeded its reservation'
            self._publish()
            if underestimated:
                raise BudgetEstimateExceeded(self._reason)


class BudgetedClient:
    """Minimal injected client exposing a guarded ``messages.create`` method."""

    def __init__(self, client, ledger, *, estimate_cost, actual_cost):
        self._client = client
        self.ledger = ledger
        self._estimate_cost = estimate_cost
        self._actual_cost = actual_cost
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **request):
        if request.get('stream'):
            raise ValueError('budget guard requires non-streaming responses')
        request_id = self.ledger.reserve(self._estimate_cost(request),
                                         model=request.get('model'))
        try:
            response = self._client.messages.create(**request)
            actual = _usd(self._actual_cost(response, request))
        except BaseException:
            # Even KeyboardInterrupt may arrive after dispatch. Do not release
            # an allowance unless usage has been positively reconciled.
            self.ledger.uncertain(request_id)
            raise
        self.ledger.settle(request_id, actual)
        return response
