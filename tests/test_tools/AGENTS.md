<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-06-30 | Updated: 2026-06-30 -->

# test_tools

## Purpose
One test file per tool domain, covering all 52 tool handlers. Tests mock the TP API at the `TPClient` level — no real HTTP calls. Each file tests the happy path plus key error cases (auth expiry, 404, validation failure).

## Key Files

| File | Description |
|------|-------------|
| `__init__.py` | Package marker |
| `test_workouts.py` | Tests for workout CRUD, copy, reorder, pair/unpair, comments |
| `test_analyze.py` | Tests for `tp_analyze_workout` — metrics, zones, laps, JSON file output |
| `test_atp_and_summary.py` | Tests for `tp_get_atp` and `tp_get_weekly_summary` |
| `test_auth_status.py` | Tests for `tp_auth_status` |
| `test_coach_support.py` | Tests for coach account athlete targeting via `athlete_override` |
| `test_equipment.py` | Tests for equipment CRUD |
| `test_events.py` | Tests for event CRUD |
| `test_events_notes_list.py` | Tests for notes listing and filtering |
| `test_fitness.py` | Tests for `tp_get_fitness` — CTL/ATL/TSB |
| `test_library.py` | Tests for workout library CRUD and scheduling |
| `test_metrics.py` | Tests for health metrics logging and retrieval |
| `test_new_workouts.py` | Tests for new workout creation edge cases |
| `test_peaks.py` | Tests for `tp_get_peaks` and `tp_get_workout_prs` |
| `test_prepare_compute.py` | Tests for interval structure computation |
| `test_prepare_compute_realistic.py` | Realistic multi-block interval structure tests |
| `test_refresh_auth_security.py` | Tests for `tp_refresh_auth` — cookie extraction security |
| `test_settings.py` | Tests for athlete settings: FTP, HR zones, pace zones |
| `test_structure.py` | Tests for `tp_validate_structure` |
| `test_validation.py` | Tests for `_validation.py` shared input validators |
| `test_workout_files.py` | Tests for file upload, download, delete |
| `test_workout_types.py` | Tests for `tp_get_workout_types` |

## For AI Agents

### Working In This Directory
- New tool → new test file named `test_<tool_module>.py`.
- Use `mock_credential` fixture from root `conftest.py` to avoid real auth.
- Mock `TPClient` at `tp_mcp.client.http.TPClient` or patch the specific method called.
- Always test: happy path, auth error (401), not-found (404), and at least one validation error.
- `test_coach_support.py` tests the `athlete_override` context var injection — run it when modifying dispatch logic in `server.py`.

### Testing Requirements
```bash
python3 -m pytest tests/test_tools/ -v
python3 -m pytest tests/test_tools/test_workouts.py -v   # Single domain
```

## Dependencies

### Internal
- `src/tp_mcp/tools/` — modules under test
- `src/tp_mcp/client/` — mocked in tests

<!-- MANUAL: -->
