# Task: Build Better Error Messaging System for Mimic

## Context
This is a multi-agent pipeline (category structure survey system) with 7 Claude-based agents orchestrated via prompts in `.claude/prompts/`. The only code file is `compute_aggregation.py`. Schemas live in `schemas/`.

## Problems
1. `compute_aggregation.py` has ZERO error handling — bare `open()`, no try/except, hardcoded paths, crashes with cryptic Python tracebacks on missing/malformed data
2. Agent prompts have validation gates but error reporting is vague — no structured error format
3. No standalone validation tool to diagnose issues between pipeline stages

## Deliverables

### 1. Refactor `compute_aggregation.py` with proper error handling
- Wrap all file reads in try/except with clear messages ("Missing file: output/personas.json — run BUILD_PERSONAS stage first")
- Validate JSON structure before processing (check required keys exist)
- Collect errors per section instead of crashing on first failure — run all sections, report all errors at the end
- Add a `--validate-only` flag that checks inputs without computing
- Add `--base-dir` flag so paths aren't hardcoded to `/Users/masonpereira/Desktop/...`
- Use colored terminal output for errors/warnings/success (red/yellow/green)
- Add progress indicators per section
- On any error, print a diagnostic summary at the end with:
  - Which sections succeeded
  - Which sections failed and WHY
  - Suggested fix for each failure

### 2. Create `validate_pipeline.py` — standalone validation script
- Takes a `--stage` argument (instrument, personas, responses, aggregation, analysis, report, all)
- For each stage, validates:
  - Required files exist
  - JSON parses correctly
  - Schema validation against `schemas/*.json`
  - Cross-file consistency checks (e.g., persona block IDs reference valid blocks, response entity IDs are in assigned blocks)
  - Conditional logic compliance (Q5→Q7, Q7→Q8, Q4→Q9, Q5→Q9)
- Output: structured diagnostic report with PASS/FAIL per check, with specific error details
- Use `jsonschema` library if available, fall back to manual checks if not
- Same `--base-dir` support

### 3. Update agent prompts with structured error reporting
Update these files in `.claude/prompts/`:
- `research-director.md` — Add a structured error report format that all validation failures must follow:
  ```
  ┌─ VALIDATION ERROR ─────────────────────────┐
  │ Stage: [STAGE_NAME]                         │
  │ Check: [specific check that failed]         │
  │ Expected: [what was expected]               │
  │ Got: [what was found]                       │
  │ File: [which file has the problem]          │
  │ Fix: [suggested remediation]                │
  └─────────────────────────────────────────────┘
  ```
  Also add: on retry failure, write a `pipeline_diagnostic.json` to `/output/` with all validation results
- `survey-administrator.md` — Add self-validation step before writing response file: enumerate all conditional logic checks, and if any fail, log the specific violation and attempt self-correction before writing
- `data-aggregator.md` — Add pre-flight validation of all input files with specific error messages for each missing/malformed file
- `instrument-builder.md` — Already has decent error handling, but add the structured error format

### 4. Create `output/pipeline_diagnostic.json` format
Define the schema for diagnostic output:
```json
{
  "pipeline_run_id": "timestamp",
  "domain": "name",
  "stages": {
    "BUILD_INSTRUMENT": {
      "status": "pass|fail|skipped",
      "checks": [
        {"name": "file_exists", "status": "pass", "detail": "..."},
        {"name": "json_valid", "status": "fail", "detail": "...", "fix": "..."}
      ],
      "duration_seconds": 0
    }
  },
  "summary": {
    "total_checks": 45,
    "passed": 43,
    "failed": 2,
    "errors": ["stage:check — detail"]
  }
}
```

## Constraints
- Keep all changes backward-compatible
- Don't change the pipeline logic or survey instrument
- Python 3.9+ compatible
- No new pip dependencies required (jsonschema optional)
- Test with missing files, malformed JSON, and schema violations

## Files to modify
- `compute_aggregation.py`
- `.claude/prompts/research-director.md`
- `.claude/prompts/survey-administrator.md`
- `.claude/prompts/data-aggregator.md`
- `.claude/prompts/instrument-builder.md`

## Files to create
- `validate_pipeline.py`
- `schemas/pipeline_diagnostic.schema.json`
