# Final Cleanup And Defect Audit Report

## Summary

This final pass prioritized safety. No files were deleted and no files were
moved to archive. The audit found several generated/temp artifacts that are
reasonable cleanup candidates, but moving them automatically is unnecessary for
submission because `pytest.ini` now prevents pytest from scanning old temp
folders, and the reliable test suite passes.

## Defects And Fixes

| Severity | Path | Issue | Risk | Safest Fix | Status |
| --- | --- | --- | --- | --- | --- |
| MEDIUM | `src/data/` | Potential roads had no named recommendation API. | Feature appeared partial in project report. | Added standalone heuristic helper with tests. | Fixed |
| MEDIUM | `README.md` | Test command used raw `pytest -q` and old 110-test count. | Could confuse grading/demo because root pytest previously scanned inaccessible temp folders. | Updated README to reliable venv command and current 145-test count. | Fixed |
| MEDIUM | repository root | No pytest discovery config. | Raw pytest could collect stale temp folders. | Added `pytest.ini` with `testpaths=tests` and temp-folder excludes. | Fixed |
| MEDIUM | `src/simulation/framework.py` | Default simulation graph loader still uses legacy `build_graph()`, so CLI Medical emergency dispatch can fail unless caller passes `build_emergency_graph()`. | Could confuse a Medical emergency simulation demo. | Keep backward compatibility; document opt-in emergency graph for Medical simulation. | Reported only |
| LOW | `app.py` | `/healthz` docstring references `pytest -q`. | Cosmetic wording; with `pytest.ini`, root pytest is now safe when dependencies are installed. | No code change needed. | Reported only |

## Cleanup Candidates

| Candidate | Reason | Evidence | Risk | Recommended Action |
| --- | --- | --- | --- | --- |
| `.pytest_cache/` | Generated pytest cache. | Not imported or referenced by app/tests. | Low | Safe to archive/delete after submission if desired. |
| `__pycache__/` folders | Generated Python bytecode cache. | Recreated automatically. | Low | Safe to archive/delete after submission if desired. |
| `.tmp/` | Temporary workspace output. | Name and location indicate temp output. | Low | Archive only if disk cleanup is needed. |
| `pytest-tmp/` | Old test temp artifact; access denied during raw scans. | Previous root `pytest -q` failed while scanning it. | Medium | Leave in place for now; `pytest.ini` mitigates test discovery risk. |
| `tmp-open/`, `tmp-open2/` | Old pip/temp folders; access denied during raw scans. | Previous root scans hit permission errors. | Medium | Leave in place for now; archive manually only if permissions allow. |
| `node-app-tmp/` | Generated app server logs and screenshots. | Contains server `.log` files and QA images. | Low/Medium | Optional archive after submission; not needed for tests. |
| `node-pytest-tmp/` | Generated test DB/model artifacts. | Contains old `test.db` and `model.joblib` outputs. | Low/Medium | Optional archive after submission; not needed for current tests. |
| `_kbs_pptx_pkg/` | Extracted PowerPoint package, unrelated to CairoFlow runtime. | Not referenced by app/tests; generated from PPTX packaging. | Medium | Report only; do not move automatically because it may be user reference material. |
| `KBS_Closing_Slides.pptx`, `build_closing_slides.py`, `image1.jpeg`, `image2.jpeg` | Presentation artifacts not referenced by CairoFlow runtime. | Only `build_closing_slides.py` references the images/PPTX. | Medium | Report only; likely unrelated but may be user-owned deliverables. |
| `.venv-clean/` | Duplicate local virtual environment. | Not referenced by project code. | Medium | Do not archive automatically; local environment folders are user-managed. |

## Files Deliberately Kept

- `data/raw/*.csv`: original dataset, source of truth.
- `data/cairo.db`: seeded SQLite database used by the app; regenerable but
  useful for demo startup.
- `data/traffic_model.joblib`: ML model cache used by traffic predictor.
- `assets/*`: referenced by app layout, MapLibre iframe, or README.
- `docs/*`: current documentation and verification reports.
- `tests/*`: current passing test suite.

## Archive Actions

No files were moved to `archive/cleanup_20260511/`.

Reason: the candidates are either generated caches that do not affect the
configured test suite, inaccessible old temp folders, or possibly user-owned
presentation artifacts. Reporting them is safer than moving them during the
final submission pass.

## Safety Checks

- Raw CSV files were hashed before the pass and checked again after final tests.
- Reliable full test command remains `.\.venv\Scripts\python.exe -m pytest -q tests`.
- App import smoke check passed.

