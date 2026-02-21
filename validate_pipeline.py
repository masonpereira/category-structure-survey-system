#!/usr/bin/env python3
"""
Pipeline Validator - Category Structure Survey System

Validates pipeline artifacts at any stage.

Usage:
  python validate_pipeline.py [--stage STAGE] [--base-dir PATH]

Stages:
  instrument   Validate output/instrument_registry.json
  personas     Validate output/personas.json
  responses    Validate output/responses/*.json (conditional logic, block scoping)
  aggregation  Validate output/aggregated_results.json + CSVs
  analysis     Validate output/analysis.json
  report       Validate output/final_report.md + d3_taxonomy_tree.json
  all          Run all checks in sequence (default)

Exit codes:
  0 = all checks passed
  1 = one or more checks failed
"""

import json
import sys
import re
import argparse
from pathlib import Path
from collections import defaultdict

# ── Terminal color helpers ─────────────────────────────────────────────────
def _supports_color():
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()

USE_COLOR = _supports_color()

def _color(code, text):
    if USE_COLOR:
        return f"\033[{code}m{text}\033[0m"
    return text

def red(text):    return _color("31", text)
def yellow(text): return _color("33", text)
def green(text):  return _color("32", text)
def bold(text):   return _color("1",  text)
def cyan(text):   return _color("36", text)

# Try to import jsonschema; fall back to manual checks
try:
    import jsonschema
    HAS_JSONSCHEMA = True
except ImportError:
    HAS_JSONSCHEMA = False

# ── Argument parsing ───────────────────────────────────────────────────────
VALID_STAGES = ["instrument", "personas", "responses", "aggregation", "analysis", "report", "all"]

parser = argparse.ArgumentParser(
    description="Category Structure Survey — Pipeline Validator",
    formatter_class=argparse.RawDescriptionHelpFormatter,
    epilog=__doc__,
)
parser.add_argument(
    "--stage",
    choices=VALID_STAGES,
    default="all",
    help="Which stage to validate (default: all)",
)
parser.add_argument(
    "--base-dir",
    type=Path,
    default=None,
    help="Base directory containing input/ and output/ folders. "
         "Defaults to the directory of this script.",
)
args = parser.parse_args()

if args.base_dir is not None:
    BASE = args.base_dir.resolve()
else:
    BASE = Path(__file__).resolve().parent

INPUT = BASE / "input"
OUTPUT = BASE / "output"
SCHEMAS = BASE / "schemas"
RESPONSES_DIR = OUTPUT / "responses"
CSV_DIR = OUTPUT / "csv"

# ── Check infrastructure ────────────────────────────────────────────────────
checks_run = 0
checks_passed = 0
checks_failed = 0
check_results = []  # [(stage, name, "pass"|"fail"|"warn", detail)]

def check(stage, name, condition, detail="", fix="", warn_only=False):
    """Record a single check result."""
    global checks_run, checks_passed, checks_failed
    checks_run += 1
    if condition:
        checks_passed += 1
        status = "pass"
        print(f"  {green('[PASS]')} {name}")
        check_results.append((stage, name, "pass", detail or "OK"))
    else:
        if warn_only:
            status = "warn"
            print(f"  {yellow('[WARN]')} {name}")
            if detail:
                print(f"         {yellow(detail)}")
            if fix:
                print(f"         Fix: {fix}")
            check_results.append((stage, name, "warn", detail))
        else:
            checks_failed += 1
            status = "fail"
            print(f"  {red('[FAIL]')} {name}")
            if detail:
                print(f"         {red(detail)}")
            if fix:
                print(f"         Fix: {fix}")
            check_results.append((stage, name, "fail", detail))
    return condition

def section(title):
    print(f"\n{bold('── ' + title + ' ' + '─' * max(0, 55 - len(title)))}")

# ── JSON loading helper ─────────────────────────────────────────────────────
def load_json(path, stage, name_hint=""):
    label = name_hint or path.name
    if not path.exists():
        check(stage, f"{label} exists", False,
              f"File not found: {path.relative_to(BASE)}",
              f"Run the appropriate pipeline stage to generate this file.")
        return None
    if path.stat().st_size == 0:
        check(stage, f"{label} is non-empty", False,
              f"File is empty: {path.relative_to(BASE)}",
              "Re-run the stage that writes this file.")
        return None
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        check(stage, f"{label} parses as valid JSON", True)
        return data
    except json.JSONDecodeError as exc:
        check(stage, f"{label} parses as valid JSON", False,
              f"JSON parse error at line {exc.lineno}, col {exc.colno}: {exc.msg}",
              "Fix the malformed JSON in the file.")
        return None

def validate_schema(data, schema_path, stage, label):
    """Validate data against a JSON schema file if jsonschema is available."""
    if not HAS_JSONSCHEMA:
        check(stage, f"{label} schema validation", True,
              "(skipped — jsonschema not installed; run: pip install jsonschema)")
        return True
    schema_data = load_json(schema_path, stage, schema_path.name)
    if schema_data is None:
        return False
    try:
        jsonschema.validate(data, schema_data)
        check(stage, f"{label} passes schema validation", True)
        return True
    except jsonschema.ValidationError as exc:
        check(stage, f"{label} passes schema validation", False,
              f"Schema violation at {'.'.join(str(p) for p in exc.absolute_path)}: {exc.message}",
              "Fix the data structure to match the schema.")
        return False
    except jsonschema.SchemaError as exc:
        check(stage, f"{label} schema is valid", False,
              f"Schema file is itself invalid: {exc.message}")
        return False

# ══════════════════════════════════════════════════════════════════════════
# STAGE: INSTRUMENT
# ══════════════════════════════════════════════════════════════════════════
def validate_instrument():
    stage = "instrument"
    section("INSTRUMENT — output/instrument_registry.json")

    # 1. Load domain_config for cross-reference
    domain_config = load_json(INPUT / "domain_config.json", stage, "domain_config.json")
    instrument = load_json(OUTPUT / "instrument_registry.json", stage, "instrument_registry.json")
    if instrument is None:
        return

    # Schema validation
    validate_schema(instrument, SCHEMAS / "instrument_registry.schema.json", stage, "instrument_registry.json")

    # 2. Metadata checks
    meta = instrument.get("metadata", {})
    check(stage, "metadata.total_questions = 13",
          meta.get("total_questions") == 13,
          f"Got: {meta.get('total_questions')}",
          "Ensure the Instrument Builder sets total_questions = 13.")

    # 3. Exactly 13 questions
    questions = instrument.get("questions", [])
    check(stage, "Exactly 13 questions present",
          len(questions) == 13,
          f"Found {len(questions)} questions",
          "The instrument must have exactly 13 questions (Q1-Q13).")

    # 4. Question IDs Q1..Q13 in order
    expected_ids = [f"Q{i}" for i in range(1, 14)]
    actual_ids = [q.get("id") for q in questions]
    check(stage, "Question IDs are Q1..Q13 in order",
          actual_ids == expected_ids,
          f"Got: {actual_ids}",
          "Questions must be numbered Q1 through Q13 in sequence.")

    # 5. Valid question types
    valid_types = {"multiple_choice", "free_list", "checklist", "pair_comparison",
                   "entity_category_matrix", "conditional_assignment",
                   "micro_monopoly_grid", "scale", "open_ended"}
    for q in questions:
        qid = q.get("id", "?")
        qt = q.get("type", "")
        check(stage, f"{qid} has valid type ({qt})",
              qt in valid_types,
              f"Unknown type: '{qt}'",
              f"Fix {qid} type to one of: {sorted(valid_types)}")

    # 6. No unresolved placeholders
    def has_placeholders(obj):
        text = json.dumps(obj)
        return "{{" in text

    for q in questions:
        qid = q.get("id", "?")
        check(stage, f"{qid} has no unresolved {{{{...}}}} placeholders",
              not has_placeholders(q),
              "Found unresolved placeholders in question text",
              f"Re-run Instrument Builder with a complete domain_config.json.")

    # 7. Conditional logic
    q_by_id = {q["id"]: q for q in questions if "id" in q}
    for qid, expected_cond in [("Q7", "Q5"), ("Q8", "Q7"), ("Q9", "Q4")]:
        q = q_by_id.get(qid, {})
        actual = q.get("conditional_on")
        check(stage, f"{qid}.conditional_on = '{expected_cond}'",
              actual == expected_cond,
              f"Got: '{actual}'",
              f"Fix {qid}.conditional_on to '{expected_cond}'.")

    # 8. Q9 has required fields
    q9 = q_by_id.get("Q9", {})
    check(stage, "Q9 has entity_ids array",
          bool(q9.get("entity_ids")),
          "entity_ids array is missing or empty",
          "Ensure Instrument Builder populates Q9.entity_ids from all block entity IDs.")
    check(stage, "Q9 has category_ids array",
          bool(q9.get("category_ids")),
          "category_ids array is missing or empty")
    check(stage, "Q9 has descriptor_instruction",
          bool(q9.get("descriptor_instruction")),
          "descriptor_instruction string is missing")

    # 9. Cross-reference with domain_config
    if domain_config:
        dc_entity_ids = {e["entity_id"] for e in domain_config.get("entity_master_list", [])}
        dc_category_ids = {c["category_id"] for c in domain_config.get("category_labels", [])}
        q4 = q_by_id.get("Q4", {})
        q4_entities = set(q4.get("entity_ids", []))
        q5 = q_by_id.get("Q5", {})
        q5_categories = set(q5.get("category_ids", []))
        check(stage, "Q4 entity_ids match domain entity_master_list",
              q4_entities == dc_entity_ids,
              f"Difference: {q4_entities.symmetric_difference(dc_entity_ids)}" if q4_entities != dc_entity_ids else "")
        check(stage, "Q5 category_ids match domain category_labels",
              q5_categories == dc_category_ids,
              f"Difference: {q5_categories.symmetric_difference(dc_category_ids)}" if q5_categories != dc_category_ids else "")

# ══════════════════════════════════════════════════════════════════════════
# STAGE: PERSONAS
# ══════════════════════════════════════════════════════════════════════════
def validate_personas():
    stage = "personas"
    section("PERSONAS — output/personas.json")

    domain_config = load_json(INPUT / "domain_config.json", stage, "domain_config.json")
    personas_data = load_json(OUTPUT / "personas.json", stage, "personas.json")
    if personas_data is None:
        return

    validate_schema(personas_data, SCHEMAS / "personas.schema.json", stage, "personas.json")

    personas = personas_data.get("personas", [])

    # n_factor check
    if domain_config:
        n_factor = domain_config.get("n_factor", 0)
        check(stage, f"Exactly n_factor ({n_factor}) personas",
              len(personas) == n_factor,
              f"Found {len(personas)} personas",
              "Re-run Persona Builder with correct n_factor.")

    # Unique persona IDs
    persona_ids = [p.get("persona_id") for p in personas]
    check(stage, "All persona_ids are unique",
          len(persona_ids) == len(set(persona_ids)),
          f"Duplicate IDs: {[pid for pid in persona_ids if persona_ids.count(pid) > 1]}")

    # ID pattern
    pattern = re.compile(r"^R\d{3}$")
    bad_ids = [pid for pid in persona_ids if pid and not pattern.match(pid)]
    check(stage, "All persona_ids match R[0-9]{3}",
          not bad_ids,
          f"Bad IDs: {bad_ids}")

    # Required fields
    required_persona_fields = ["persona_id", "expertise_tier", "cognitive_style",
                                "response_style", "assigned_block_id"]
    for p in personas[:5]:  # spot-check first 5
        pid = p.get("persona_id", "?")
        missing = [f for f in required_persona_fields if f not in p]
        check(stage, f"{pid} has required fields",
              not missing,
              f"Missing: {missing}")

    # Expertise tier distribution
    if domain_config:
        dist = domain_config.get("expertise_distribution", {})
        total = len(personas)
        tier_counts = defaultdict(int)
        for p in personas:
            tier_counts[p.get("expertise_tier", "unknown")] += 1

        for tier in ["casual", "professional", "insider"]:
            expected_pct = dist.get(tier, 0)
            expected_n = round(total * expected_pct)
            actual_n = tier_counts[tier]
            check(stage, f"'{tier}' tier count within ±1 of expected ({expected_n})",
                  abs(actual_n - expected_n) <= 1,
                  f"Expected ~{expected_n}, got {actual_n}",
                  "Re-run Persona Builder to match expertise_distribution.")

    # Block assignment validity
    if domain_config:
        valid_block_ids = {b["block_id"] for b in domain_config.get("entity_blocks", [])}
        bad_blocks = [p.get("persona_id") for p in personas
                      if p.get("assigned_block_id") not in valid_block_ids]
        check(stage, "All assigned_block_ids reference valid blocks",
              not bad_blocks,
              f"Personas with invalid blocks: {bad_blocks[:5]}")

        # Block assignment balance
        block_counts = defaultdict(int)
        for p in personas:
            block_counts[p.get("assigned_block_id")] += 1
        if block_counts:
            min_count = min(block_counts.values())
            max_count = max(block_counts.values())
            check(stage, "Block assignments are balanced (differ by ≤1)",
                  max_count - min_count <= 1,
                  f"Block counts: {dict(block_counts)}",
                  "Re-run Persona Builder to balance block assignments.")

# ══════════════════════════════════════════════════════════════════════════
# STAGE: RESPONSES
# ══════════════════════════════════════════════════════════════════════════
def validate_responses():
    stage = "responses"
    section("RESPONSES — output/responses/response_R*.json")

    domain_config = load_json(INPUT / "domain_config.json", stage, "domain_config.json")
    personas_data = load_json(OUTPUT / "personas.json", stage, "personas.json")
    if personas_data is None or domain_config is None:
        return

    personas = {p["persona_id"]: p for p in personas_data.get("personas", [])}
    n_expected = len(personas)

    # Build block-entity map
    block_entities = {}
    for block in domain_config.get("entity_blocks", []):
        block_entities[block["block_id"]] = set(block["entity_ids"])

    # Check response files exist
    check(stage, "output/responses/ directory exists",
          RESPONSES_DIR.exists(),
          "Directory missing",
          "Run the ADMINISTER_SURVEY stage.")
    if not RESPONSES_DIR.exists():
        return

    response_files = sorted(RESPONSES_DIR.glob("response_R*.json"))
    check(stage, f"Exactly {n_expected} response files exist",
          len(response_files) == n_expected,
          f"Found {len(response_files)}, expected {n_expected}",
          "Re-run ADMINISTER_SURVEY to generate missing responses.")

    # Persona synthesis files
    synthesis_dir = OUTPUT / "persona_synthesis"
    synthesis_files = sorted(synthesis_dir.glob("persona_synthesis_R*.txt")) if synthesis_dir.exists() else []
    check(stage, f"Exactly {n_expected} persona synthesis files exist",
          len(synthesis_files) == n_expected,
          f"Found {len(synthesis_files)}, expected {n_expected}",
          "Re-run ADMINISTER_SURVEY to generate missing synthesis files.")

    # Validate each response
    response_errors = []
    conditional_violations = []

    for fpath in response_files:
        data = None
        try:
            with open(fpath, encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            response_errors.append(f"{fpath.name}: {exc}")
            continue

        pid = data.get("persona_id", fpath.stem.replace("response_", ""))
        resp = data.get("responses", {})

        # completion_status
        if data.get("completion_status") != "complete":
            response_errors.append(f"{fpath.name}: completion_status is '{data.get('completion_status')}', expected 'complete'")

        # All 13 questions present
        missing_qs = [f"Q{i}" for i in range(1, 14) if f"Q{i}" not in resp]
        if missing_qs:
            response_errors.append(f"{fpath.name}: missing questions {missing_qs}")

        # Block scoping: Q4 entities must be in assigned block
        persona = personas.get(pid, {})
        block_id = persona.get("assigned_block_id")
        block_set = block_entities.get(block_id, set()) if block_id else set()

        q4_recognized = set(resp.get("Q4", {}).get("recognized_entity_ids", []))
        out_of_block = q4_recognized - block_set
        if out_of_block and block_set:
            conditional_violations.append(
                f"{fpath.name}: Q4 contains entities outside assigned block {block_id}: {list(out_of_block)[:3]}"
            )

        # Q5 → Q7: Q7 categories must be in Q5
        q5_recognized = set(resp.get("Q5", {}).get("recognized_category_ids", []))
        q7_placements = resp.get("Q7", {}).get("placements", [])
        for pl in q7_placements:
            eid = pl.get("entity_id")
            cats = set(pl.get("category_ids", []))
            # Entity must be in Q4
            if eid not in q4_recognized:
                conditional_violations.append(
                    f"{fpath.name}: Q7 entity {eid} not in Q4 recognized_entity_ids"
                )
            # Categories must be in Q5
            bad_cats = cats - q5_recognized
            if bad_cats:
                conditional_violations.append(
                    f"{fpath.name}: Q7 entity {eid} uses categories not in Q5: {bad_cats}"
                )

        # Q7 → Q8: Q8 entities must have 2+ categories in Q7
        q7_multi_placed = {
            pl["entity_id"]
            for pl in q7_placements
            if len(pl.get("category_ids", [])) >= 2
        }
        q8_assignments = resp.get("Q8", {}).get("primary_assignments", [])
        for pa in q8_assignments:
            eid = pa.get("entity_id")
            if eid not in q7_multi_placed:
                conditional_violations.append(
                    f"{fpath.name}: Q8 entity {eid} was not multi-placed in Q7"
                )
            # Primary category must be in Q7 categories for this entity
            primary_cat = pa.get("primary_category_id")
            for pl in q7_placements:
                if pl.get("entity_id") == eid:
                    if primary_cat not in pl.get("category_ids", []):
                        conditional_violations.append(
                            f"{fpath.name}: Q8 primary_category {primary_cat} for {eid} "
                            f"not in Q7 categories {pl.get('category_ids', [])}"
                        )
                    break

        # Q4 → Q9 entity completeness: Q9 entities must equal Q4 recognized
        q9_entries = resp.get("Q9", {}).get("micro_monopoly_entries", [])
        q9_entity_ids = {e.get("entity_id") for e in q9_entries}
        q9_missing = q4_recognized - q9_entity_ids
        q9_extra = q9_entity_ids - q4_recognized
        if q9_missing:
            conditional_violations.append(
                f"{fpath.name}: Q9 missing entities that were in Q4: {list(q9_missing)[:3]}"
            )
        if q9_extra:
            conditional_violations.append(
                f"{fpath.name}: Q9 has extra entities not in Q4: {list(q9_extra)[:3]}"
            )

        # Q5 → Q9 category validity
        for entry in q9_entries:
            cat = entry.get("selected_category_id")
            if cat and cat not in q5_recognized:
                conditional_violations.append(
                    f"{fpath.name}: Q9 entry for {entry.get('entity_id')} uses category {cat} not in Q5"
                )

        # Q9 descriptor length (3-5 words)
        for entry in q9_entries:
            desc = entry.get("descriptor", "")
            word_count = len(desc.split()) if desc else 0
            if desc and not (3 <= word_count <= 5):
                conditional_violations.append(
                    f"{fpath.name}: Q9 descriptor for {entry.get('entity_id')} "
                    f"has {word_count} words (should be 3-5): '{desc[:40]}'"
                )

    check(stage, "All response files parse as valid JSON",
          not response_errors,
          f"{len(response_errors)} errors:\n    " + "\n    ".join(response_errors[:5]) if response_errors else "",
          "Fix or regenerate the malformed response files.")

    check(stage, "All conditional logic rules satisfied (Q5→Q7, Q7→Q8, Q4→Q9, Q5→Q9)",
          not conditional_violations,
          f"{len(conditional_violations)} violation(s):\n    " + "\n    ".join(conditional_violations[:5]) if conditional_violations else "",
          "Re-run Survey Administrator with error context; violations are listed above.")

# ══════════════════════════════════════════════════════════════════════════
# STAGE: AGGREGATION
# ══════════════════════════════════════════════════════════════════════════
def validate_aggregation():
    stage = "aggregation"
    section("AGGREGATION — output/aggregated_results.json + CSVs")

    aggregated = load_json(OUTPUT / "aggregated_results.json", stage, "aggregated_results.json")
    if aggregated is None:
        return

    validate_schema(aggregated, SCHEMAS / "aggregated_results.schema.json", stage, "aggregated_results.json")

    # data_tables.txt
    tables_path = OUTPUT / "data_tables.txt"
    check(stage, "output/data_tables.txt exists and is non-empty",
          tables_path.exists() and tables_path.stat().st_size > 0,
          "data_tables.txt is missing or empty",
          "Re-run the Data Aggregator.")

    # 8 CSV files
    required_csvs = [
        "entity_awareness.csv", "category_recognition.csv",
        "pair_comparison_consensus.csv", "entity_placement.csv",
        "co_placement_matrix.csv", "micro_monopoly.csv",
        "depth_clarity.csv", "expertise_tier_summary.csv"
    ]
    for csv_name in required_csvs:
        fpath = CSV_DIR / csv_name
        check(stage, f"output/csv/{csv_name} exists",
              fpath.exists() and fpath.stat().st_size > 0,
              f"Missing or empty: {fpath.relative_to(BASE)}",
              "Re-run the Data Aggregator.")

    # Section presence
    required_sections = [
        "section_01_entity_awareness", "section_02_unaided_salience",
        "section_03_category_recognition", "section_04_pair_comparison_consensus",
        "section_05_entity_placement", "section_06_co_placement_matrix",
        "section_07_micro_monopoly", "section_08_depth_perception",
        "section_09_boundary_clarity", "section_10_structure_satisfaction",
        "section_11_open_ended_themes", "section_12_cct_eigenvalue_approximation",
        "section_13_expertise_tier_breakdowns"
    ]
    for sec in required_sections:
        check(stage, f"{sec} present in aggregated_results.json",
              sec in aggregated,
              f"Missing section: {sec}",
              "Re-run Data Aggregator.")

    # Block-aware denominators spot-check
    section01 = aggregated.get("section_01_entity_awareness", {})
    entities = section01.get("entities", [])
    if entities:
        # Check that n_exposed != n_respondents for all entities (would indicate wrong denominator)
        n_respondents = aggregated.get("metadata", {}).get("n_respondents", 0)
        all_wrong = all(e.get("n_exposed") == n_respondents for e in entities[:10])
        check(stage, "Entity awareness uses block-aware denominators (n_exposed ≠ n_total for block-restricted entities)",
              not all_wrong,
              "All n_exposed values equal total respondents — block-aware denominator may not be applied",
              "Verify the aggregator uses n_exposed from block assignment, not total respondents.")

    # Co-placement matrix symmetry
    section06 = aggregated.get("section_06_co_placement_matrix", {})
    matrix = section06.get("matrix", {})
    cat_ids = section06.get("category_ids", [])
    violations = 0
    for cid_a in cat_ids:
        for cid_b in cat_ids:
            row_a = matrix.get(cid_a, {})
            row_b = matrix.get(cid_b, {})
            if row_a.get(cid_b) != row_b.get(cid_a):
                violations += 1
    check(stage, "Co-placement matrix is symmetric",
          violations == 0,
          f"{violations} symmetry violations found",
          "Re-run Data Aggregator; the co-placement matrix must be symmetric.")

    # CCT section and caveat
    section12 = aggregated.get("section_12_cct_eigenvalue_approximation", {})
    check(stage, "CCT section has approx_eigenvalue_ratio",
          "approx_eigenvalue_ratio" in section12,
          "approx_eigenvalue_ratio missing from CCT section")
    check(stage, "CCT section includes caveat text",
          bool(section12.get("caveat")),
          "CCT caveat is missing or empty",
          "Ensure Data Aggregator includes LLM-approximation caveat in CCT section.")

    # Micro-monopoly completeness: every entity recognized by any respondent should have an entry
    section07 = aggregated.get("section_07_micro_monopoly", {})
    mm_entities = {e.get("entity_id") for e in section07.get("entities", [])}
    check(stage, "Micro-monopoly results present (non-empty)",
          bool(mm_entities),
          "No micro-monopoly entities found",
          "Check that Q9 responses are non-empty and Data Aggregator computed section 7.")

    # Descriptor fields
    for entity in section07.get("entities", [])[:10]:
        eid = entity.get("entity_id", "?")
        # At minimum, descriptor_clusters should exist
        check(stage, f"Micro-monopoly entity {eid} has descriptor_clusters",
              "descriptor_clusters" in entity,
              "descriptor_clusters field missing",
              "Re-run Data Aggregator with updated Q9 descriptor aggregation.")

    # Expertise tier breakdowns
    section13 = aggregated.get("section_13_expertise_tier_breakdowns", {})
    tiers = section13.get("tiers", {})
    for tier in ["casual", "professional", "insider"]:
        check(stage, f"Tier breakdown present for '{tier}'",
              tier in tiers,
              f"'{tier}' tier missing from expertise breakdowns")

# ══════════════════════════════════════════════════════════════════════════
# STAGE: ANALYSIS
# ══════════════════════════════════════════════════════════════════════════
def validate_analysis():
    stage = "analysis"
    section("ANALYSIS — output/analysis.json")

    analysis = load_json(OUTPUT / "analysis.json", stage, "analysis.json")
    if analysis is None:
        return

    validate_schema(analysis, SCHEMAS / "analysis.schema.json", stage, "analysis.json")

    # 8 required deliverables
    required_deliverables = [
        "consensus_taxonomy_tree", "entity_placement_map", "micro_monopoly_dictionary",
        "awareness_rankings", "depth_map", "expertise_divergence_report",
        "recognition_gap_analysis", "cct_analysis"
    ]
    deliverables = analysis.get("deliverables", {})
    for d in required_deliverables:
        check(stage, f"Deliverable '{d}' present",
              d in deliverables,
              f"Missing deliverable: {d}",
              "Re-run Research Analyst to generate all 8 deliverables.")

    # 5-8 headline findings
    findings = analysis.get("headline_findings", [])
    check(stage, "5-8 headline findings present",
          5 <= len(findings) <= 8,
          f"Found {len(findings)} findings (expected 5-8)",
          "Re-run Research Analyst to generate 5-8 headline findings.")

    # Each finding has confidence_assessment and evidence
    for i, finding in enumerate(findings):
        fid = finding.get("id", f"finding_{i+1}")
        check(stage, f"{fid} has confidence_assessment",
              bool(finding.get("confidence_assessment")),
              "confidence_assessment missing or empty",
              "Every finding must include a confidence_assessment with tier_agreement, consensus_strength, cross_question_corroboration.")
        check(stage, f"{fid} has non-empty evidence array",
              bool(finding.get("evidence")),
              "evidence array is empty",
              "Every finding must cite specific data in the evidence array.")

    # 3-5 strategic implications
    implications = analysis.get("strategic_implications", [])
    check(stage, "3-5 strategic implications present",
          3 <= len(implications) <= 5,
          f"Found {len(implications)} implications (expected 3-5)",
          "Re-run Research Analyst to generate 3-5 strategic implications.")

    # Confidence methodology note
    check(stage, "confidence_methodology_note is present",
          bool(analysis.get("confidence_methodology_note")),
          "confidence_methodology_note missing",
          "Research Analyst must include confidence methodology explanation.")

    # CCT caveat in cct_analysis deliverable
    cct_deliverable = deliverables.get("cct_analysis", {})
    check(stage, "CCT deliverable includes caveat",
          bool(cct_deliverable.get("caveat") or cct_deliverable.get("approximation_note")),
          "CCT caveat/approximation_note missing from cct_analysis deliverable",
          "Research Analyst must include LLM-approximation caveat in CCT analysis.")

    # Micro-monopoly dictionary completeness
    mm_dict = deliverables.get("micro_monopoly_dictionary", {})
    entities_in_dict = mm_dict.get("entities", []) if isinstance(mm_dict, dict) else []
    check(stage, "Micro-monopoly dictionary is non-empty",
          bool(entities_in_dict),
          "micro_monopoly_dictionary has no entities",
          "Re-run Research Analyst; dictionary must cover all recognized entities.")

    # Each entity in micro_monopoly_dictionary has descriptor
    for entity in entities_in_dict[:10]:  # spot-check first 10
        eid = entity.get("entity_id", "?")
        check(stage, f"Micro-monopoly entity {eid} has descriptor field",
              bool(entity.get("descriptor")),
              "descriptor field missing or empty",
              "Every micro_monopoly_dictionary entry must have a descriptor.")
        check(stage, f"Micro-monopoly entity {eid} has descriptor_consensus_strength",
              "descriptor_consensus_strength" in entity,
              "descriptor_consensus_strength field missing")

# ══════════════════════════════════════════════════════════════════════════
# STAGE: REPORT
# ══════════════════════════════════════════════════════════════════════════
def validate_report():
    stage = "report"
    section("REPORT — output/final_report.md + d3_taxonomy_tree.json")

    report_path = OUTPUT / "final_report.md"
    check(stage, "output/final_report.md exists",
          report_path.exists(),
          "final_report.md not found",
          "Run the Report Writer agent.")

    if report_path.exists():
        report_text = report_path.read_text(encoding="utf-8")
        report_size = len(report_text)
        check(stage, "final_report.md is non-empty",
              report_size > 100,
              f"File appears empty or very small ({report_size} chars)")

        # Required sections
        required_sections = [
            "Executive Summary", "Methodology",
            "Consensus Taxonomy", "Entity Placement", "Micro-Monopoly",
            "Awareness", "Depth", "Expertise", "Recognition Gap", "CCT",
            "Key Finding", "Implication", "Appendix"
        ]
        for sec_name in required_sections:
            check(stage, f"Report contains '{sec_name}' section",
                  sec_name.lower() in report_text.lower(),
                  f"Section '{sec_name}' not found in report",
                  "Ensure Report Writer includes all required sections.")

        # Confidence callout boxes
        check(stage, "Report contains confidence callout boxes (┌─...─┐ pattern)",
              "┌─" in report_text or "┌──" in report_text,
              "No confidence callout boxes found",
              "Report Writer must include confidence assessments in callout box format.")

        # CCT caveat
        check(stage, "Report contains CCT caveat/approximation note",
              "approximate" in report_text.lower() or "lLM-approximated" in report_text.lower() or
              "directional" in report_text.lower(),
              "CCT approximation caveat not found in report",
              "Report must include explicit caveat about CCT eigenvalue approximation.")

        # Verbatim quotes / descriptors
        quote_count = report_text.count('"') + report_text.count('"') + report_text.count('"')
        check(stage, "Report contains ≥3 quoted descriptor phrases",
              quote_count >= 6,  # pairs of quotes
              f"Fewer than 3 quoted phrases found (quote count: {quote_count})",
              "Include at least 3 verbatim descriptor quotes in the report.")

    # D3 taxonomy tree
    d3_path = OUTPUT / "d3_taxonomy_tree.json"
    d3_tree = load_json(d3_path, stage, "d3_taxonomy_tree.json")
    if d3_tree is not None:
        # Check root name matches domain
        domain_config = load_json(INPUT / "domain_config.json", stage, "domain_config.json")
        if domain_config:
            domain_name = domain_config.get("domain", {}).get("name", "")
            root_name = d3_tree.get("name", "")
            check(stage, "D3 tree root name matches domain name",
                  domain_name.lower() in root_name.lower() or root_name.lower() in domain_name.lower(),
                  f"Domain: '{domain_name}', D3 root: '{root_name}'",
                  "Report Writer must set D3 tree root name to the domain name.")

        # All leaf nodes should have descriptor
        def collect_leaves(node):
            children = node.get("children", [])
            if not children:
                return [node]
            leaves = []
            for child in children:
                leaves.extend(collect_leaves(child))
            return leaves

        leaves = collect_leaves(d3_tree)
        check(stage, f"D3 tree contains leaf entities ({len(leaves)} found)",
              len(leaves) > 0,
              "D3 tree has no leaf nodes",
              "Report Writer must populate the D3 tree with entity leaves.")

        leaves_with_descriptor = [l for l in leaves if l.get("descriptor")]
        check(stage, "All D3 leaf nodes have descriptor field",
              len(leaves_with_descriptor) == len(leaves),
              f"{len(leaves) - len(leaves_with_descriptor)} leaves missing descriptor",
              "Every leaf in d3_taxonomy_tree.json must have a descriptor field.")

        leaves_with_strength = [l for l in leaves if "consensus_strength" in l]
        check(stage, "All D3 leaf nodes have consensus_strength field",
              len(leaves_with_strength) == len(leaves),
              f"{len(leaves) - len(leaves_with_strength)} leaves missing consensus_strength",
              "Every leaf in d3_taxonomy_tree.json must have a consensus_strength field.")

# ══════════════════════════════════════════════════════════════════════════
# MAIN EXECUTION
# ══════════════════════════════════════════════════════════════════════════
print(bold("\n╔══════════════════════════════════════════════════════════╗"))
print(bold(  "║     Category Structure Survey — Pipeline Validator       ║"))
print(bold(  "╚══════════════════════════════════════════════════════════╝"))
print(f"  Base directory : {BASE}")
print(f"  Stage          : {args.stage.upper()}")
if not HAS_JSONSCHEMA:
    print(yellow("  Note: jsonschema not installed — schema validation skipped. Install with: pip install jsonschema"))

stage_map = {
    "instrument": validate_instrument,
    "personas": validate_personas,
    "responses": validate_responses,
    "aggregation": validate_aggregation,
    "analysis": validate_analysis,
    "report": validate_report,
}

if args.stage == "all":
    for fn in stage_map.values():
        fn()
else:
    stage_map[args.stage]()

# ── Final Summary ─────────────────────────────────────────────────────────
print(bold("\n╔══════════════════════════════════════════════════════════╗"))
print(bold(  "║                 VALIDATION SUMMARY                      ║"))
print(bold(  "╚══════════════════════════════════════════════════════════╝"))
print(f"\n  Total checks : {checks_run}")
print(f"  {green('Passed')}       : {checks_passed}")
print(f"  {red('Failed')}       : {checks_failed}")

warns = [r for r in check_results if r[2] == "warn"]
if warns:
    print(f"  {yellow('Warnings')}     : {len(warns)}")

if checks_failed > 0:
    print(f"\n{red('  FAILED CHECKS:')}")
    for stage, name, status, detail in check_results:
        if status == "fail":
            print(f"  [{stage.upper()}] {red('✗')} {name}")
            if detail and detail != "OK":
                print(f"      {detail}")
    sys.exit(1)
else:
    print(f"\n  {green('All checks passed.')}")
    sys.exit(0)
