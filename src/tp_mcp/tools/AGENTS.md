<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-06-30 | Updated: 2026-06-30 -->

# tools

## Purpose
One file per tool handler — 52 tools total. Each file contains one or more async handler functions that accept named arguments, call `TPClient`, and return a plain dict result. The `__init__.py` re-exports all handlers; `server.py` imports them and registers them in the `TOOLS` list and `_TOOL_HANDLERS` dispatch map.

## Key Files

| File | Description |
|------|-------------|
| `__init__.py` | Barrel re-export of all 52 tool handlers |
| `_validation.py` | Shared Pydantic input validation helpers used across multiple tools |
| `workouts.py` | `tp_get_workouts`, `tp_create_workout`, `tp_update_workout`, `tp_delete_workout`, `tp_copy_workout`, `tp_reorder_workouts`, `tp_unpair_workout`, `tp_pair_workout`, `tp_get_workout`, `tp_get_workout_comments`, `tp_add_workout_comment`. Also defines `SPORT_TYPE_MAP` used by `server.py` for enum validation |
| `analyze.py` | `tp_analyze_workout` — fetches time-series data, computes zones/laps/metrics, saves full JSON to disk |
| `atp.py` | `tp_get_atp` — annual training plan (weekly TSS targets, training periods, races) |
| `auth_status.py` | `tp_auth_status` — checks stored credential validity |
| `availability.py` | `tp_get_availability`, `tp_create_availability`, `tp_delete_availability` |
| `equipment.py` | `tp_get_equipment`, `tp_create_equipment`, `tp_update_equipment`, `tp_delete_equipment` |
| `events_calendar.py` | `tp_get_events`, `tp_get_focus_event`, `tp_get_next_event`, `tp_create_event`, `tp_update_event`, `tp_delete_event` |
| `fitness.py` | `tp_get_fitness` — CTL/ATL/TSB fitness trend |
| `library.py` | `tp_get_libraries`, `tp_get_library_items`, `tp_get_library_item`, `tp_create_library`, `tp_delete_library`, `tp_create_library_item`, `tp_update_library_item`, `tp_schedule_library_workout` |
| `metrics.py` | `tp_log_metrics`, `tp_get_metrics`, `tp_get_nutrition` |
| `notes.py` | `tp_create_note`, `tp_delete_note`, `tp_get_note`, `tp_get_notes`, `tp_update_note`, `tp_get_note_comments`, `tp_add_note_comment` |
| `peaks.py` | `tp_get_peaks`, `tp_get_workout_prs` |
| `profile.py` | `tp_get_profile`, `tp_list_athletes` |
| `refresh_auth.py` | `tp_refresh_auth` — extracts fresh cookie from browser and stores it |
| `settings.py` | `tp_get_athlete_settings`, `tp_update_ftp`, `tp_update_hr_zones`, `tp_update_speed_zones`, `tp_update_nutrition`, `tp_get_pool_length_settings` |
| `structure.py` | `tp_validate_structure` — validates interval structure JSON without creating a workout |
| `weekly_summary.py` | `tp_get_weekly_summary` — combined workout + fitness view for a calendar week |
| `workout_files.py` | `tp_upload_workout_file`, `tp_download_workout_file`, `tp_delete_workout_file` |
| `workout_types.py` | `tp_get_workout_types` — lists all sport types and subtypes with IDs |

## For AI Agents

### Working In This Directory
- **One tool = one file.** New tools get a new file; never add to an existing file unless you're adding a closely related tool in the same domain grouping (e.g. notes CRUD all live in `notes.py`).
- After creating a new tool file: add its import to `__init__.py`, register it in `server.py` `TOOLS` list and `@_handler` decorator, create `tests/test_tools/test_<name>.py`.
- `SPORT_TYPE_MAP` in `workouts.py` is the single source of truth for sport enum values — `server.py` imports it for tool schema validation.
- The `athlete_override` context variable (set in `server.py` before dispatch) is read by `TPClient` — tools do not need to handle athlete routing themselves.
- Field name gotcha: list endpoint returns `title`; detail endpoint returns `workoutTitle`. The `WorkoutSummary` Pydantic model in `client/models.py` handles this via `field_validator`.

### Testing Requirements
```bash
python3 -m pytest tests/test_tools/ -v
python3 -m pytest tests/test_tools/test_workouts.py -v  # Specific tool
```
- Each tool test file mocks `TPClient` and `get_credential`.
- Test happy path + at least one error case (e.g. 404, auth expiry).

### Common Patterns
- Return `{"success": True, ...data}` on success.
- Return `{"isError": True, "error_code": "...", "message": "..."}` on failure.
- Use `_validation.py` helpers for shared input validation (dates, sport types).
- All handlers are `async def` and receive named keyword arguments from `server.py` dispatch.

## Dependencies

### Internal
- `client/http.py` — `TPClient` for all API calls
- `client/context.py` — `athlete_override` context var (read, not set)
- `_validation.py` — shared validation helpers

### External
- `pydantic>=2.0.0` (via `_validation.py` and `client/models.py`)

<!-- MANUAL: -->
