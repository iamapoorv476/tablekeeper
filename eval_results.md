# Eval results

Run: 2026-09-05 01:22

**9/9 passed**

| Case | Result | Detail |
|---|---|---|
| Books into the smallest table that fits | ✓ pass | booked table with 2 seats, guest_name persisted correctly |
| Falls back to a larger table once small ones are full | ✓ pass | correctly fell back to a 4-seat table |
| Alternatives offered when full are actually free | ✓ pass | 1 alternative(s) offered, all independently verified free |
| create_reservation re-checks availability, refuses a stale slot | ✓ pass | correctly refused, no phantom booking, next_step present |
| modify_reservation never claims success when it can't resolve the booking | ✓ pass | correctly refused with explicit anti-false-success guidance |
| modify_reservation updates the slot without losing the guest's name | ✓ pass | time updated, guest_name preserved |
| request_callback auto-links an existing guest by phone number | ✓ pass | callback correctly linked to the existing guest record |
| Party bigger than any table returns unavailable, never a fake fit | ✓ pass | correctly reported unavailable with no fabricated table |
| A malformed tool call doesn't break other calls in the same batch | ✓ pass | malformed call errored cleanly, valid call in the same batch still succeeded |
