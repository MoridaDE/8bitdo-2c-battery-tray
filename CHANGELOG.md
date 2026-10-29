# Changelog

## v1.1.0 — 2026-10-29

### Added
- **Self-learning discharge runtime** from Bluetooth sync anchors.
  Between two stabilized BT `%` readings, the tray measures connected
  drain time (dongle linked, not charging) and updates a learned
  full→empty curve (`drain_hours`), EMA-smoothed and clamped to 8–35 h
  (default still 18 h).
- Persisted learning artifacts: `drain_hours`, `drain_samples.json`.
- Estimate file now stores drain accumulator seconds
  (`percentage timestamp drain_accum_s`).
- Tooltip shows the active Entladekurve (`Standard` vs `gelernt`).

### Notes
- USB charge-time learning (`charge_hours` from BT samples) was already
  present; this release adds the matching discharge-side learning.
- Live `%` over the 2.4 GHz receiver remains an open goal (unchanged).

## v1.0.0 — 2026-10-17

Initial release: BT GATT battery + USB charge estimate + 2.4 GHz estimate.
