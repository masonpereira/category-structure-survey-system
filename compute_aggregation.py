#!/usr/bin/env python3
"""
Data Aggregator - Category Structure Survey System
Computes all 13 aggregation sections and writes:
  - aggregated_results.json
  - data_tables.txt (ASCII box-drawing tables)
  - 8 CSV files in output/csv/

Usage:
  python compute_aggregation.py [--base-dir PATH] [--validate-only]

Flags:
  --base-dir PATH    Base directory (default: directory containing this script)
  --validate-only    Check all inputs without computing; print diagnostic and exit
"""

import json
import os
import csv
import math
import sys
import argparse
import time
from collections import defaultdict, Counter
from pathlib import Path

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

# ── Argument parsing ───────────────────────────────────────────────────────
parser = argparse.ArgumentParser(
    description="Category Structure Survey — Data Aggregator",
    formatter_class=argparse.RawDescriptionHelpFormatter,
)
parser.add_argument(
    "--base-dir",
    type=Path,
    default=None,
    help="Base directory containing input/ and output/ folders. "
         "Defaults to the directory of this script.",
)
parser.add_argument(
    "--validate-only",
    action="store_true",
    help="Validate all inputs and print a diagnostic report without computing.",
)
args = parser.parse_args()

# Resolve base directory
if args.base_dir is not None:
    BASE = args.base_dir.resolve()
else:
    BASE = Path(__file__).resolve().parent

INPUT = BASE / "input"
OUTPUT = BASE / "output"
RESPONSES_DIR = OUTPUT / "responses"
CSV_DIR = OUTPUT / "csv"

# ── Error collection infrastructure ────────────────────────────────────────
class AggregationError(Exception):
    """Raised for fatal errors that prevent a section from running."""

section_results = {}   # {section_name: "ok" | "skipped" | error_message}
all_errors = []        # [(section, message, fix_suggestion)]

def record_error(section, message, fix=""):
    all_errors.append((section, message, fix))
    section_results[section] = message
    print(red(f"  [ERROR] {message}"))
    if fix:
        print(yellow(f"  [FIX]   {fix}"))

def record_ok(section):
    if section not in section_results:
        section_results[section] = "ok"

def progress(msg):
    print(cyan(f"  ▶ {msg}"))

def section_header(num, title):
    print(f"\n{bold(f'Section {num}: {title}')}")

# ── Input validation helpers ────────────────────────────────────────────────
def load_json_file(path, label, fix_hint=""):
    """Load a JSON file with clear error messages. Returns parsed data or raises AggregationError."""
    if not path.exists():
        raise AggregationError(
            f"Missing file: {path.relative_to(BASE)} — {fix_hint or 'ensure the file exists'}"
        )
    if path.stat().st_size == 0:
        raise AggregationError(
            f"Empty file: {path.relative_to(BASE)} — file exists but contains no data"
        )
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as exc:
        raise AggregationError(
            f"Invalid JSON in {path.relative_to(BASE)} at line {exc.lineno}, col {exc.colno}: {exc.msg}"
        )
    return data

def check_required_keys(data, keys, context):
    """Verify required top-level keys exist in a dict."""
    missing = [k for k in keys if k not in data]
    if missing:
        raise AggregationError(
            f"{context}: missing required keys: {missing}"
        )

# ── PRE-FLIGHT VALIDATION ──────────────────────────────────────────────────
print(bold("\n╔══════════════════════════════════════════════════════════╗"))
print(bold(  "║     Category Structure Survey — Data Aggregator          ║"))
print(bold(  "╚══════════════════════════════════════════════════════════╝"))
print(f"  Base directory : {BASE}")
print(f"  Mode           : {'VALIDATE ONLY' if args.validate_only else 'FULL COMPUTATION'}")

print(bold("\n── Pre-flight validation ──────────────────────────────────"))

preflight_errors = []

def preflight_check(label, check_fn):
    """Run a single preflight check; collect results."""
    try:
        result = check_fn()
        if result is None or result is True:
            print(green(f"  [PASS] {label}"))
            return True
        else:
            msg = str(result)
            print(red(f"  [FAIL] {label}: {msg}"))
            preflight_errors.append((label, msg))
            return False
    except AggregationError as exc:
        print(red(f"  [FAIL] {label}: {exc}"))
        preflight_errors.append((label, str(exc)))
        return False
    except Exception as exc:
        msg = f"Unexpected error: {exc}"
        print(red(f"  [FAIL] {label}: {msg}"))
        preflight_errors.append((label, msg))
        return False

# Load core config files (fail fast if missing)
domain_config = None
personas_data = None
instrument = None

preflight_check(
    "input/domain_config.json exists and is valid JSON",
    lambda: load_json_file(INPUT / "domain_config.json", "domain_config",
                           "run the BUILD_INSTRUMENT stage first") and True
)
try:
    domain_config = load_json_file(
        INPUT / "domain_config.json", "domain_config",
        "run the BUILD_INSTRUMENT stage first"
    )
except AggregationError:
    domain_config = None

preflight_check(
    "output/personas.json exists and is valid JSON",
    lambda: load_json_file(OUTPUT / "personas.json", "personas",
                           "run the BUILD_PERSONAS stage first") and True
)
try:
    personas_data = load_json_file(
        OUTPUT / "personas.json", "personas",
        "run the BUILD_PERSONAS stage first"
    )
except AggregationError:
    personas_data = None

preflight_check(
    "output/instrument_registry.json exists and is valid JSON",
    lambda: load_json_file(OUTPUT / "instrument_registry.json", "instrument_registry",
                           "run the BUILD_INSTRUMENT stage first") and True
)
try:
    instrument = load_json_file(
        OUTPUT / "instrument_registry.json", "instrument_registry",
        "run the BUILD_INSTRUMENT stage first"
    )
except AggregationError:
    instrument = None

# Validate domain_config structure
if domain_config is not None:
    preflight_check(
        "domain_config.json has required keys",
        lambda: check_required_keys(
            domain_config,
            ["entity_master_list", "category_labels", "category_pairs", "entity_blocks", "domain"],
            "domain_config.json"
        ) or True
    )

# Validate personas structure
if personas_data is not None:
    preflight_check(
        "personas.json has required keys",
        lambda: check_required_keys(
            personas_data, ["personas"], "personas.json"
        ) or True
    )

# Check responses directory
def _check_responses_dir():
    if not RESPONSES_DIR.exists():
        raise AggregationError(
            f"Missing directory: output/responses/ — run the ADMINISTER_SURVEY stage first"
        )
    files = list(RESPONSES_DIR.glob("response_R*.json"))
    if not files:
        raise AggregationError(
            "No response files found in output/responses/ — run ADMINISTER_SURVEY stage first"
        )
    return True

preflight_check("output/responses/ directory exists with response files", _check_responses_dir)

# Validate each response file is valid JSON
response_file_errors = []
if RESPONSES_DIR.exists():
    def _check_all_responses():
        files = sorted(RESPONSES_DIR.glob("response_R*.json"))
        bad = []
        for fpath in files:
            try:
                load_json_file(fpath, fpath.name)
            except AggregationError as exc:
                bad.append(str(exc))
        if bad:
            raise AggregationError(f"{len(bad)} response file(s) have errors:\n    " + "\n    ".join(bad))
        return True
    preflight_check(f"All response files parse as valid JSON", _check_all_responses)

if preflight_errors:
    print(red(f"\n  {len(preflight_errors)} pre-flight check(s) FAILED."))
    if args.validate_only:
        print(red("\n── Validation failed — cannot proceed ──────────────────"))
        for label, msg in preflight_errors:
            print(f"  {red('✗')} {label}")
            print(f"      {msg}")
        sys.exit(1)
    else:
        print(yellow("  Continuing with available data; sections that need missing files will be skipped."))
else:
    print(green(f"\n  All pre-flight checks passed."))
    if args.validate_only:
        print(green("\n── Validation complete — all inputs OK ─────────────────"))
        sys.exit(0)

print()

# ── Build lookup structures ────────────────────────────────────────────────
# These may fail gracefully if domain_config is None
entity_labels = {}
category_labels = {}
all_entity_ids = []
all_category_ids = []
entity_blocks = {}
block_entities = {}
category_pairs = {}
all_pair_ids = []
persona_lookup = {}
persona_ids = []
block_respondents = defaultdict(list)
entity_exposed = defaultdict(set)
tier_respondents = defaultdict(list)
responses = {}
n_total = 0

try:
    entity_labels = {e["entity_id"]: e["label"] for e in domain_config["entity_master_list"]}
    category_labels = {c["category_id"]: c["label"] for c in domain_config["category_labels"]}
    all_entity_ids = sorted(entity_labels.keys(), key=lambda x: int(x[1:]))
    all_category_ids = sorted(category_labels.keys(), key=lambda x: int(x[1:]))

    for block in domain_config["entity_blocks"]:
        bid = block["block_id"]
        eids = block["entity_ids"]
        block_entities[bid] = set(eids)
        for eid in eids:
            entity_blocks.setdefault(eid, []).append(bid)

    for p in domain_config["category_pairs"]:
        category_pairs[p["pair_id"]] = (p["category_a_id"], p["category_b_id"])
    all_pair_ids = sorted(category_pairs.keys(), key=lambda x: int(x[1:]))

    persona_lookup = {p["persona_id"]: p for p in personas_data["personas"]}
    persona_ids = sorted(persona_lookup.keys(), key=lambda x: int(x[1:]))
    n_total = len(persona_ids)

    for pid, p in persona_lookup.items():
        block_respondents[p["assigned_block_id"]].append(pid)

    for pid, p in persona_lookup.items():
        bid = p["assigned_block_id"]
        for eid in block_entities.get(bid, set()):
            entity_exposed[eid].add(pid)

    for pid, p in persona_lookup.items():
        tier_respondents[p["expertise_tier"]].append(pid)

    for pid in persona_ids:
        fpath = RESPONSES_DIR / f"response_{pid}.json"
        try:
            responses[pid] = load_json_file(fpath, f"response_{pid}",
                                            f"re-run Survey Administrator for persona {pid}")
        except AggregationError as exc:
            record_error("LOAD_RESPONSES", str(exc),
                         f"Re-run the ADMINISTER_SURVEY stage for persona {pid}")

    if responses:
        print(green(f"  Loaded {len(responses)}/{n_total} response files."))
    else:
        print(red("  No responses loaded — cannot compute any sections."))

except Exception as exc:
    record_error("SETUP", f"Fatal error building lookup structures: {exc}",
                 "Check that domain_config.json and personas.json are complete and well-formed.")

# ── Helper functions ───────────────────────────────────────────────────────
def round3(x):
    return round(x, 3)

def round2(x):
    return round(x, 2)

def mean(vals):
    if not vals:
        return 0.0
    return sum(vals) / len(vals)

def std_dev(vals):
    if len(vals) < 2:
        return 0.0
    m = mean(vals)
    variance = sum((v - m) ** 2 for v in vals) / (len(vals) - 1)
    return math.sqrt(variance)

def safe_get(response, *keys, default=None):
    """Safely navigate nested dict keys; return default if any key is missing."""
    node = response
    for key in keys:
        if not isinstance(node, dict) or key not in node:
            return default
        node = node[key]
    return node

# ══════════════════════════════════════════════════════════════════════════
# SECTION 1: Entity Awareness (Q4) - Block-aware denominators
# ══════════════════════════════════════════════════════════════════════════
section_header(1, "Entity Awareness (Q4)")
entity_awareness = {}

try:
    progress("Computing block-aware recognition rates...")
    for eid in all_entity_ids:
        exposed = entity_exposed[eid]
        n_exposed = len(exposed)
        n_recognized = 0
        tier_rec = defaultdict(int)
        tier_exp = defaultdict(int)

        for pid in exposed:
            if pid not in responses:
                continue
            tier = persona_lookup[pid]["expertise_tier"]
            tier_exp[tier] += 1
            recognized_ids = safe_get(responses[pid], "responses", "Q4", "recognized_entity_ids", default=[])
            if eid in recognized_ids:
                n_recognized += 1
                tier_rec[tier] += 1

        rate = round3(n_recognized / n_exposed) if n_exposed > 0 else 0.0
        tier_rates = {}
        for t in ["casual", "professional", "insider"]:
            if tier_exp[t] > 0:
                tier_rates[t] = round3(tier_rec[t] / tier_exp[t])
            else:
                tier_rates[t] = None

        entity_awareness[eid] = {
            "entity_id": eid,
            "label": entity_labels[eid],
            "n_exposed": n_exposed,
            "n_recognized": n_recognized,
            "recognition_rate": rate,
            "tier_rates": tier_rates
        }

    print(green(f"  Done. {len(entity_awareness)} entities computed."))
    record_ok("Section 1: Entity Awareness")

except Exception as exc:
    record_error("Section 1: Entity Awareness",
                 f"Failed to compute entity awareness: {exc}",
                 "Check that all Q4 responses have 'recognized_entity_ids' arrays.")

# ══════════════════════════════════════════════════════════════════════════
# SECTION 2: Unaided Salience / Smith's S (Q2)
# ══════════════════════════════════════════════════════════════════════════
section_header(2, "Unaided Salience / Smith's S (Q2)")
entity_smiths = {}
category_unaided_terms = defaultdict(list)

try:
    progress("Building entity name → ID lookup...")

    label_to_entity = {}
    for eid, label in entity_labels.items():
        label_to_entity[label.lower()] = eid
        if "(" in label:
            parts = label.replace("(", "").replace(")", "").split()
            for part in parts:
                label_to_entity[part.lower()] = eid

    extra_mappings = {
        "bitcoin": "E001", "btc": "E001",
        "ethereum": "E002", "eth": "E002",
        "solana": "E003", "sol": "E003",
        "cardano": "E004", "ada": "E004",
        "avalanche": "E005", "avax": "E005",
        "polkadot": "E006", "dot": "E006",
        "near protocol": "E007", "near": "E007",
        "sui": "E008",
        "aptos": "E009",
        "cosmos": "E010", "atom": "E010",
        "algorand": "E011",
        "ton": "E012",
        "hedera": "E013",
        "fantom": "E014", "sonic": "E014", "fantom (sonic)": "E014",
        "tezos": "E015",
        "polygon": "E016", "matic": "E016",
        "arbitrum": "E017",
        "optimism": "E018",
        "zksync": "E019",
        "starknet": "E020",
        "base": "E021",
        "scroll": "E022",
        "mantle": "E023",
        "blast": "E024",
        "linea": "E025",
        "uniswap": "E026",
        "aave": "E027",
        "makerdao": "E028", "maker": "E028", "sky": "E028", "makerdao (sky)": "E028",
        "lido": "E029",
        "curve finance": "E030", "curve": "E030",
        "compound": "E031",
        "dydx": "E032",
        "gmx": "E033",
        "jupiter": "E034",
        "raydium": "E035",
        "1inch": "E036",
        "yearn finance": "E037", "yearn": "E037",
        "pendle": "E038",
        "synthetix": "E039",
        "convex finance": "E040", "convex": "E040",
        "eigenlayer": "E041",
        "coinbase": "E042",
        "binance": "E043",
        "kraken": "E044",
        "okx": "E045",
        "bybit": "E046",
        "gemini": "E047",
        "crypto.com": "E048",
        "kucoin": "E049",
        "bitfinex": "E050",
        "robinhood crypto": "E051", "robinhood": "E051",
        "opensea": "E052",
        "blur": "E053",
        "magic eden": "E054",
        "axie infinity": "E055", "axie": "E055",
        "immutable x": "E056", "immutable": "E056",
        "the sandbox": "E057", "sandbox": "E057",
        "decentraland": "E058",
        "chainlink": "E059", "link": "E059",
        "the graph": "E060",
        "filecoin": "E061",
        "arweave": "E062",
        "helium": "E063",
        "render network": "E064", "render": "E064",
        "tether": "E065", "usdt": "E065", "tether (usdt)": "E065",
        "circle": "E066", "usdc": "E066", "circle (usdc)": "E066",
        "metamask": "E067",
        "phantom": "E068",
        "ledger": "E069",
        "trezor": "E070",
        "wormhole": "E071",
        "layerzero": "E072",
        "monero": "E073",
        "zcash": "E074",
        "chainalysis": "E075",
        "nansen": "E076",
        "dune analytics": "E077", "dune": "E077",
        "ripple": "E078", "xrp": "E078", "ripple (xrp)": "E078",
        "litecoin": "E079", "ltc": "E079",
        "dogecoin": "E080", "doge": "E080",
        "shiba inu": "E081", "shib": "E081",
        "worldcoin": "E082",
        "celestia": "E083",
        "hyperliquid": "E084",
        "pyth network": "E085", "pyth": "E085",
        "ondo finance": "E086", "ondo": "E086",
        "ethena": "E087",
        "jito": "E088",
        "safe": "E089", "gnosis safe": "E089", "safe (gnosis safe)": "E089",
        "fireblocks": "E090",
    }

    def match_entity(mention):
        m = mention.strip().lower()
        if m in extra_mappings:
            return extra_mappings[m]
        if m in label_to_entity:
            return label_to_entity[m]
        for label_lower, eid in label_to_entity.items():
            if m in label_lower or label_lower in m:
                return eid
        return None

    progress("Computing Smith's S scores...")
    for eid in all_entity_ids:
        total_s = 0.0
        mention_count = 0
        tier_s = defaultdict(float)
        tier_n = defaultdict(int)

        for pid in persona_ids:
            if pid not in responses:
                continue
            tier = persona_lookup[pid]["expertise_tier"]
            tier_n[tier] += 1
            free_list = safe_get(responses[pid], "responses", "Q2", "free_list", default=[])
            L = len(free_list)
            for rank_idx, mention in enumerate(free_list):
                matched_eid = match_entity(mention)
                if matched_eid == eid:
                    R = rank_idx + 1
                    s_i = (L - R + 1) / L
                    total_s += s_i
                    tier_s[tier] += s_i
                    mention_count += 1
                    break

        smiths_s = round3(total_s / n_total) if n_total > 0 else 0.0
        mention_rate = round3(mention_count / n_total) if n_total > 0 else 0.0

        tier_smiths = {}
        for t in ["casual", "professional", "insider"]:
            if tier_n[t] > 0:
                tier_smiths[t] = round3(tier_s[t] / tier_n[t])
            else:
                tier_smiths[t] = 0.0

        entity_smiths[eid] = {
            "entity_id": eid,
            "label": entity_labels[eid],
            "smiths_s": smiths_s,
            "mention_count": mention_count,
            "mention_rate": mention_rate,
            "tier_smiths_s": tier_smiths
        }

    # Unaided category salience from Q3
    for pid in persona_ids:
        if pid not in responses:
            continue
        free_list = safe_get(responses[pid], "responses", "Q3", "free_list", default=[])
        for term in free_list:
            category_unaided_terms[term.lower()].append(pid)

    print(green(f"  Done. Smith's S computed for {len(entity_smiths)} entities."))
    record_ok("Section 2: Unaided Salience")

except Exception as exc:
    record_error("Section 2: Unaided Salience",
                 f"Failed to compute Smith's S: {exc}",
                 "Check that Q2 responses contain 'free_list' arrays.")

# ══════════════════════════════════════════════════════════════════════════
# SECTION 3: Category Recognition (Q5)
# ══════════════════════════════════════════════════════════════════════════
section_header(3, "Category Recognition (Q5)")
category_recognition = {}

try:
    progress("Computing category recognition rates...")
    for cid in all_category_ids:
        n_recognized = 0
        tier_rec = defaultdict(int)
        tier_n = defaultdict(int)

        for pid in persona_ids:
            if pid not in responses:
                continue
            tier = persona_lookup[pid]["expertise_tier"]
            tier_n[tier] += 1
            recognized = safe_get(responses[pid], "responses", "Q5", "recognized_category_ids", default=[])
            if cid in recognized:
                n_recognized += 1
                tier_rec[tier] += 1

        rate = round3(n_recognized / n_total) if n_total > 0 else 0.0
        tier_rates = {}
        for t in ["casual", "professional", "insider"]:
            if tier_n[t] > 0:
                tier_rates[t] = round3(tier_rec[t] / tier_n[t])
            else:
                tier_rates[t] = None

        category_recognition[cid] = {
            "category_id": cid,
            "label": category_labels[cid],
            "n_recognized": n_recognized,
            "recognition_rate": rate,
            "tier_rates": tier_rates
        }

    print(green(f"  Done. {len(category_recognition)} categories computed."))
    record_ok("Section 3: Category Recognition")

except Exception as exc:
    record_error("Section 3: Category Recognition",
                 f"Failed to compute category recognition: {exc}",
                 "Check that Q5 responses contain 'recognized_category_ids' arrays.")

# ══════════════════════════════════════════════════════════════════════════
# SECTION 4: Pair Comparison Consensus (Q6)
# ══════════════════════════════════════════════════════════════════════════
section_header(4, "Pair Comparison Consensus (Q6)")
pair_consensus = {}

try:
    progress("Computing pair comparison consensus...")
    for pair_id in all_pair_ids:
        cat_a, cat_b = category_pairs[pair_id]
        judgment_counts = Counter()
        tier_judgments = defaultdict(Counter)

        for pid in persona_ids:
            if pid not in responses:
                continue
            tier = persona_lookup[pid]["expertise_tier"]
            pair_judgments = safe_get(responses[pid], "responses", "Q6", "pair_judgments", default=[])
            for pj in pair_judgments:
                if pj.get("pair_id") == pair_id:
                    j = pj.get("judgment", "no_opinion")
                    judgment_counts[j] += 1
                    tier_judgments[tier][j] += 1
                    break

        opinionated_total = sum(v for k, v in judgment_counts.items() if k != "no_opinion")
        if opinionated_total > 0:
            best_judgment = None
            best_count = 0
            for j, c in judgment_counts.items():
                if j != "no_opinion" and c > best_count:
                    best_count = c
                    best_judgment = j
            consensus_pct = round3(best_count / opinionated_total)
            consensus = best_judgment if consensus_pct > 0.40 else "no_consensus"
        else:
            consensus = "no_consensus"
            consensus_pct = 0.0

        tier_consensus_data = {}
        for t in ["casual", "professional", "insider"]:
            tc = tier_judgments[t]
            t_opinionated = sum(v for k, v in tc.items() if k != "no_opinion")
            if t_opinionated > 0:
                t_best_j = None
                t_best_c = 0
                for j, c in tc.items():
                    if j != "no_opinion" and c > t_best_c:
                        t_best_c = c
                        t_best_j = j
                t_pct = round3(t_best_c / t_opinionated)
                tier_consensus_data[t] = {
                    "judgment": t_best_j if t_pct > 0.40 else "no_consensus",
                    "strength": t_pct,
                    "counts": dict(tc)
                }
            else:
                tier_consensus_data[t] = {"judgment": "no_consensus", "strength": 0.0, "counts": {}}

        pair_consensus[pair_id] = {
            "pair_id": pair_id,
            "category_a_id": cat_a,
            "category_a_label": category_labels.get(cat_a, cat_a),
            "category_b_id": cat_b,
            "category_b_label": category_labels.get(cat_b, cat_b),
            "judgment_counts": dict(judgment_counts),
            "opinionated_total": opinionated_total,
            "consensus_judgment": consensus,
            "consensus_strength": consensus_pct,
            "tier_consensus": tier_consensus_data
        }

    print(green(f"  Done. {len(pair_consensus)} pairs computed."))
    record_ok("Section 4: Pair Comparison Consensus")

except Exception as exc:
    record_error("Section 4: Pair Comparison Consensus",
                 f"Failed to compute pair consensus: {exc}",
                 "Check that Q6 responses contain 'pair_judgments' arrays with 'pair_id' and 'judgment' fields.")

# ══════════════════════════════════════════════════════════════════════════
# SECTION 5: Entity Placement (Q7, Q8)
# ══════════════════════════════════════════════════════════════════════════
section_header(5, "Entity Placement (Q7/Q8)")
entity_placement = {}

try:
    progress("Computing entity-to-category placements...")
    for eid in all_entity_ids:
        category_counts = Counter()
        primary_counts = Counter()
        n_placed = 0
        n_multi_placed = 0
        tier_placements = defaultdict(Counter)

        exposed = entity_exposed[eid]
        for pid in exposed:
            if pid not in responses:
                continue
            tier = persona_lookup[pid]["expertise_tier"]
            placements = safe_get(responses[pid], "responses", "Q7", "placements", default=[])
            for pl in placements:
                if pl.get("entity_id") == eid:
                    cats = pl.get("category_ids", [])
                    n_placed += 1
                    if len(cats) > 1:
                        n_multi_placed += 1
                    for cid in cats:
                        category_counts[cid] += 1
                        tier_placements[tier][cid] += 1
                    break

            primary_assignments = safe_get(responses[pid], "responses", "Q8", "primary_assignments", default=[])
            for pa in primary_assignments:
                if pa.get("entity_id") == eid:
                    primary_counts[pa["primary_category_id"]] += 1
                    break

        n_exposed = len(exposed)
        placement_rate = round3(n_placed / n_exposed) if n_exposed > 0 else 0.0

        if category_counts:
            plurality_cid = category_counts.most_common(1)[0][0]
            plurality_count = category_counts.most_common(1)[0][1]
            plurality_strength = round3(plurality_count / n_placed) if n_placed > 0 else 0.0
        else:
            plurality_cid = None
            plurality_count = 0
            plurality_strength = 0.0

        distribution = {}
        for cid, count in category_counts.most_common():
            distribution[cid] = {
                "count": count,
                "rate": round3(count / n_placed) if n_placed > 0 else 0.0
            }

        entity_placement[eid] = {
            "entity_id": eid,
            "label": entity_labels[eid],
            "n_exposed": n_exposed,
            "n_placed": n_placed,
            "placement_rate": placement_rate,
            "n_multi_placed": n_multi_placed,
            "plurality_category_id": plurality_cid,
            "plurality_category_label": category_labels.get(plurality_cid, None),
            "plurality_strength": plurality_strength,
            "category_distribution": distribution,
            "primary_assignment_counts": dict(primary_counts),
            "tier_placements": {t: dict(c) for t, c in tier_placements.items()}
        }

    print(green(f"  Done. {len(entity_placement)} entities computed."))
    record_ok("Section 5: Entity Placement")

except Exception as exc:
    record_error("Section 5: Entity Placement",
                 f"Failed to compute entity placement: {exc}",
                 "Check that Q7 responses contain 'placements' arrays and Q8 has 'primary_assignments'.")

# ══════════════════════════════════════════════════════════════════════════
# SECTION 6: Co-Placement Matrix
# ══════════════════════════════════════════════════════════════════════════
section_header(6, "Co-Placement Matrix")
co_placement = defaultdict(int)
co_placement_matrix = {}

try:
    progress("Building category co-placement matrix...")
    for pid in persona_ids:
        if pid not in responses:
            continue
        placements = safe_get(responses[pid], "responses", "Q7", "placements", default=[])
        for pl in placements:
            cats = pl.get("category_ids", [])
            if len(cats) > 1:
                for i in range(len(cats)):
                    for j in range(i + 1, len(cats)):
                        pair_key = tuple(sorted([cats[i], cats[j]]))
                        co_placement[pair_key] += 1

    for cid_a in all_category_ids:
        co_placement_matrix[cid_a] = {}
        for cid_b in all_category_ids:
            if cid_a == cid_b:
                co_placement_matrix[cid_a][cid_b] = 0
            else:
                pair_key = tuple(sorted([cid_a, cid_b]))
                co_placement_matrix[cid_a][cid_b] = co_placement.get(pair_key, 0)

    # Symmetry check
    violations = 0
    for cid_a in all_category_ids:
        for cid_b in all_category_ids:
            if co_placement_matrix[cid_a][cid_b] != co_placement_matrix[cid_b][cid_a]:
                violations += 1
    if violations > 0:
        print(yellow(f"  Warning: {violations} symmetry violation(s) detected in co-placement matrix."))
    else:
        print(green("  Matrix symmetry verified."))

    print(green(f"  Done. {len(co_placement)} co-placement pairs found."))
    record_ok("Section 6: Co-Placement Matrix")

except Exception as exc:
    record_error("Section 6: Co-Placement Matrix",
                 f"Failed to build co-placement matrix: {exc}",
                 "Check that Q7 placements have valid 'category_ids' arrays.")

# ══════════════════════════════════════════════════════════════════════════
# SECTION 7: Micro-Monopoly Results (Q9)
# ══════════════════════════════════════════════════════════════════════════
section_header(7, "Micro-Monopoly Results (Q9)")
micro_monopoly = {}

try:
    progress("Computing micro-monopoly category ownership and descriptors...")
    for eid in all_entity_ids:
        cat_selections = Counter()
        descriptors_by_cat = defaultdict(list)
        all_descriptors = []
        tier_selections = defaultdict(Counter)

        exposed = entity_exposed[eid]
        for pid in exposed:
            if pid not in responses:
                continue
            tier = persona_lookup[pid]["expertise_tier"]
            entries = safe_get(responses[pid], "responses", "Q9", "micro_monopoly_entries", default=[])
            for entry in entries:
                if entry.get("entity_id") == eid:
                    cid = entry.get("selected_category_id")
                    desc = entry.get("descriptor", "")
                    if cid:
                        cat_selections[cid] += 1
                        tier_selections[tier][cid] += 1
                    if desc:
                        if cid:
                            descriptors_by_cat[cid].append(desc)
                        all_descriptors.append(desc)
                    break

        total_selections = sum(cat_selections.values())
        if cat_selections:
            plurality_cid = cat_selections.most_common(1)[0][0]
            plurality_count = cat_selections.most_common(1)[0][1]
            consensus_strength = round3(plurality_count / total_selections) if total_selections > 0 else 0.0
        else:
            plurality_cid = None
            plurality_count = 0
            consensus_strength = 0.0

        cat_dist = {}
        for cid, count in cat_selections.most_common():
            cat_dist[cid] = {
                "count": count,
                "rate": round3(count / total_selections) if total_selections > 0 else 0.0,
                "descriptors": descriptors_by_cat[cid]
            }

        def cluster_descriptors(descs):
            if not descs:
                return {"representative": "", "all_descriptors": [], "cluster_count": 0}
            word_counts = Counter()
            for d in descs:
                words = set(d.lower().split())
                for w in words:
                    if len(w) > 2:
                        word_counts[w] += 1
            return {
                "representative": descs[0] if descs else "",
                "all_descriptors": descs,
                "cluster_count": len(descs),
                "common_terms": [w for w, c in word_counts.most_common(5)]
            }

        descriptor_clusters = {}
        for cid in cat_dist:
            descriptor_clusters[cid] = cluster_descriptors(descriptors_by_cat[cid])

        micro_monopoly[eid] = {
            "entity_id": eid,
            "label": entity_labels[eid],
            "total_selections": total_selections,
            "plurality_category_id": plurality_cid,
            "plurality_category_label": category_labels.get(plurality_cid, None),
            "consensus_strength": consensus_strength,
            "category_distribution": cat_dist,
            "descriptor_clusters": descriptor_clusters,
            "tier_selections": {t: dict(c) for t, c in tier_selections.items()}
        }

    print(green(f"  Done. {len(micro_monopoly)} entities processed."))
    record_ok("Section 7: Micro-Monopoly")

except Exception as exc:
    record_error("Section 7: Micro-Monopoly",
                 f"Failed to compute micro-monopoly results: {exc}",
                 "Check that Q9 responses contain 'micro_monopoly_entries' with 'entity_id', 'selected_category_id', and 'descriptor' fields.")

# ══════════════════════════════════════════════════════════════════════════
# SECTION 8: Depth Perception (Q10)
# ══════════════════════════════════════════════════════════════════════════
section_header(8, "Depth Perception (Q10)")
depth_perception = {}

try:
    progress("Computing category depth scores...")
    for cid in all_category_ids:
        scores = []
        tier_scores = defaultdict(list)

        for pid in persona_ids:
            if pid not in responses:
                continue
            tier = persona_lookup[pid]["expertise_tier"]
            depth_ratings = safe_get(responses[pid], "responses", "Q10", "depth_ratings", default=[])
            for dr in depth_ratings:
                if dr.get("category_id") == cid:
                    score = dr.get("depth_score")
                    if score is not None:
                        scores.append(score)
                        tier_scores[tier].append(score)
                    break

        depth_perception[cid] = {
            "category_id": cid,
            "label": category_labels[cid],
            "n_raters": len(scores),
            "mean_depth": round2(mean(scores)),
            "std_depth": round2(std_dev(scores)),
            "tier_means": {
                t: round2(mean(tier_scores[t])) if tier_scores[t] else None
                for t in ["casual", "professional", "insider"]
            },
            "tier_std": {
                t: round2(std_dev(tier_scores[t])) if len(tier_scores[t]) > 1 else None
                for t in ["casual", "professional", "insider"]
            }
        }

    print(green(f"  Done. {len(depth_perception)} categories scored."))
    record_ok("Section 8: Depth Perception")

except Exception as exc:
    record_error("Section 8: Depth Perception",
                 f"Failed to compute depth perception: {exc}",
                 "Check that Q10 responses contain 'depth_ratings' arrays with 'category_id' and 'depth_score'.")

# ══════════════════════════════════════════════════════════════════════════
# SECTION 9: Boundary Clarity (Q11)
# ══════════════════════════════════════════════════════════════════════════
section_header(9, "Boundary Clarity (Q11)")
boundary_clarity = {}

try:
    progress("Computing category boundary clarity scores...")
    for cid in all_category_ids:
        scores = []
        tier_scores = defaultdict(list)

        for pid in persona_ids:
            if pid not in responses:
                continue
            tier = persona_lookup[pid]["expertise_tier"]
            clarity_ratings = safe_get(responses[pid], "responses", "Q11", "clarity_ratings", default=[])
            for cr in clarity_ratings:
                if cr.get("category_id") == cid:
                    score = cr.get("clarity_score")
                    if score is not None:
                        scores.append(score)
                        tier_scores[tier].append(score)
                    break

        boundary_clarity[cid] = {
            "category_id": cid,
            "label": category_labels[cid],
            "n_raters": len(scores),
            "mean_clarity": round2(mean(scores)),
            "std_clarity": round2(std_dev(scores)),
            "tier_means": {
                t: round2(mean(tier_scores[t])) if tier_scores[t] else None
                for t in ["casual", "professional", "insider"]
            },
            "tier_std": {
                t: round2(std_dev(tier_scores[t])) if len(tier_scores[t]) > 1 else None
                for t in ["casual", "professional", "insider"]
            }
        }

    print(green(f"  Done. {len(boundary_clarity)} categories scored."))
    record_ok("Section 9: Boundary Clarity")

except Exception as exc:
    record_error("Section 9: Boundary Clarity",
                 f"Failed to compute boundary clarity: {exc}",
                 "Check that Q11 responses contain 'clarity_ratings' arrays with 'category_id' and 'clarity_score'.")

# ══════════════════════════════════════════════════════════════════════════
# SECTION 10: Structure Satisfaction (Q12)
# ══════════════════════════════════════════════════════════════════════════
section_header(10, "Structure Satisfaction (Q12)")
structure_satisfaction = {}

try:
    progress("Computing satisfaction scores...")
    satisfaction_scores = []
    tier_sat = defaultdict(list)
    satisfaction_explanations = []

    for pid in persona_ids:
        if pid not in responses:
            continue
        tier = persona_lookup[pid]["expertise_tier"]
        q12 = safe_get(responses[pid], "responses", "Q12", default={})
        score = q12.get("satisfaction_score")
        explanation = q12.get("explanation", "")
        if score is not None:
            satisfaction_scores.append(score)
            tier_sat[tier].append(score)
        if explanation:
            satisfaction_explanations.append({
                "persona_id": pid,
                "expertise_tier": tier,
                "score": score,
                "explanation": explanation
            })

    structure_satisfaction = {
        "n_respondents": len(satisfaction_scores),
        "mean_score": round2(mean(satisfaction_scores)),
        "std_score": round2(std_dev(satisfaction_scores)),
        "score_distribution": dict(Counter(satisfaction_scores)),
        "tier_means": {
            t: round2(mean(tier_sat[t])) if tier_sat[t] else None
            for t in ["casual", "professional", "insider"]
        },
        "tier_std": {
            t: round2(std_dev(tier_sat[t])) if len(tier_sat[t]) > 1 else None
            for t in ["casual", "professional", "insider"]
        },
        "explanations": satisfaction_explanations
    }

    print(green(f"  Done. {len(satisfaction_scores)} satisfaction scores collected."))
    record_ok("Section 10: Structure Satisfaction")

except Exception as exc:
    record_error("Section 10: Structure Satisfaction",
                 f"Failed to compute satisfaction scores: {exc}",
                 "Check that Q12 responses contain 'satisfaction_score' (1-7 integer).")

# ══════════════════════════════════════════════════════════════════════════
# SECTION 11: Open-Ended Themes (Q13)
# ══════════════════════════════════════════════════════════════════════════
section_header(11, "Open-Ended Themes (Q13)")
open_ended_analysis = {}

try:
    progress("Extracting open-ended response themes...")
    open_ended_responses = []
    for pid in persona_ids:
        if pid not in responses:
            continue
        tier = persona_lookup[pid]["expertise_tier"]
        q13 = safe_get(responses[pid], "responses", "Q13", default={})
        text = q13.get("open_ended_response", "")
        if text:
            open_ended_responses.append({
                "persona_id": pid,
                "expertise_tier": tier,
                "response": text
            })

    theme_keywords = {
        "missing_categories": ["missing", "need", "should be", "separate", "new category", "no category", "missing category", "add"],
        "too_granular": ["too many", "too granular", "too specific", "too much", "too detailed", "jargon", "confusing"],
        "overlapping_categories": ["overlap", "blurry", "blur", "unclear", "fuzzy", "hard to distinguish", "similar"],
        "emerging_trends": ["ai", "emerging", "new", "rwa", "real-world", "depin", "tokenization"],
        "hierarchy_issues": ["hierarchy", "subcategory", "parent", "child", "layer", "nesting"],
        "positive_feedback": ["good", "comprehensive", "covers", "reasonable", "well", "makes sense"],
    }

    themes = {}
    for theme_name, keywords in theme_keywords.items():
        matching = []
        for entry in open_ended_responses:
            text_lower = entry["response"].lower()
            if any(kw in text_lower for kw in keywords):
                matching.append(entry)
        themes[theme_name] = {
            "count": len(matching),
            "rate": round3(len(matching) / len(open_ended_responses)) if open_ended_responses else 0.0,
            "entries": matching
        }

    open_ended_analysis = {
        "total_responses": len(open_ended_responses),
        "themes": themes,
        "all_responses": open_ended_responses
    }

    print(green(f"  Done. {len(open_ended_responses)} responses analyzed across {len(themes)} themes."))
    record_ok("Section 11: Open-Ended Themes")

except Exception as exc:
    record_error("Section 11: Open-Ended Themes",
                 f"Failed to extract themes: {exc}",
                 "Check that Q13 responses contain 'open_ended_response' strings.")

# ══════════════════════════════════════════════════════════════════════════
# SECTION 12: CCT Eigenvalue Approximation
# ══════════════════════════════════════════════════════════════════════════
section_header(12, "CCT Eigenvalue Approximation")
cct_analysis = {}

try:
    progress("Computing pairwise agreement matrix...")
    agreement_scores = []

    for i in range(len(persona_ids)):
        for j in range(i + 1, len(persona_ids)):
            pid_a = persona_ids[i]
            pid_b = persona_ids[j]
            if pid_a not in responses or pid_b not in responses:
                continue

            bid_a = persona_lookup[pid_a]["assigned_block_id"]
            bid_b = persona_lookup[pid_b]["assigned_block_id"]
            shared = block_entities.get(bid_a, set()) & block_entities.get(bid_b, set())
            if not shared:
                continue

            placements_a = {}
            for pl in safe_get(responses[pid_a], "responses", "Q7", "placements", default=[]):
                if pl.get("entity_id") in shared:
                    placements_a[pl["entity_id"]] = set(pl.get("category_ids", []))

            placements_b = {}
            for pl in safe_get(responses[pid_b], "responses", "Q7", "placements", default=[]):
                if pl.get("entity_id") in shared:
                    placements_b[pl["entity_id"]] = set(pl.get("category_ids", []))

            both_placed = set(placements_a.keys()) & set(placements_b.keys())
            if not both_placed:
                continue

            agreements = []
            for eid in both_placed:
                cats_a = placements_a[eid]
                cats_b = placements_b[eid]
                union = cats_a | cats_b
                if union:
                    agreement = len(cats_a & cats_b) / len(union)
                    agreements.append(agreement)

            if agreements:
                agreement_scores.append(mean(agreements))

    progress("Computing tier-level agreement...")
    tier_pair_agreements = defaultdict(list)
    for i in range(len(persona_ids)):
        for j in range(i + 1, len(persona_ids)):
            pid_a = persona_ids[i]
            pid_b = persona_ids[j]
            if pid_a not in responses or pid_b not in responses:
                continue

            tier_a = persona_lookup[pid_a]["expertise_tier"]
            tier_b = persona_lookup[pid_b]["expertise_tier"]
            bid_a = persona_lookup[pid_a]["assigned_block_id"]
            bid_b = persona_lookup[pid_b]["assigned_block_id"]

            shared = block_entities.get(bid_a, set()) & block_entities.get(bid_b, set())
            if not shared:
                continue

            placements_a = {}
            for pl in safe_get(responses[pid_a], "responses", "Q7", "placements", default=[]):
                if pl.get("entity_id") in shared:
                    placements_a[pl["entity_id"]] = set(pl.get("category_ids", []))

            placements_b = {}
            for pl in safe_get(responses[pid_b], "responses", "Q7", "placements", default=[]):
                if pl.get("entity_id") in shared:
                    placements_b[pl["entity_id"]] = set(pl.get("category_ids", []))

            both_placed = set(placements_a.keys()) & set(placements_b.keys())
            if not both_placed:
                continue

            agreements = []
            for eid in both_placed:
                cats_a = placements_a[eid]
                cats_b = placements_b[eid]
                union = cats_a | cats_b
                if union:
                    agreements.append(len(cats_a & cats_b) / len(union))

            if agreements:
                pair_agreement = mean(agreements)
                if tier_a == tier_b:
                    tier_pair_agreements[f"within_{tier_a}"].append(pair_agreement)
                else:
                    key = f"between_{min(tier_a, tier_b)}_{max(tier_a, tier_b)}"
                    tier_pair_agreements[key].append(pair_agreement)

    if agreement_scores:
        overall_agreement = round3(mean(agreement_scores))
        agreement_std = round2(std_dev(agreement_scores))
        approx_ratio = round2(overall_agreement / (1 - overall_agreement)) if overall_agreement < 1.0 else 99.99
    else:
        overall_agreement = 0.0
        agreement_std = 0.0
        approx_ratio = 0.0

    cct_analysis = {
        "caveat": "CCT eigenvalue ratios are LLM-approximated using pairwise agreement heuristics, not formally computed via factor analysis. Results should be interpreted as directional indicators only.",
        "n_respondent_pairs": len(agreement_scores),
        "mean_pairwise_agreement": overall_agreement,
        "std_pairwise_agreement": agreement_std,
        "approx_eigenvalue_ratio": approx_ratio,
        "single_culture_indicated": approx_ratio >= 3.0,
        "tier_agreement": {
            k: {
                "n_pairs": len(v),
                "mean_agreement": round3(mean(v)),
                "std_agreement": round2(std_dev(v)) if len(v) > 1 else None
            }
            for k, v in tier_pair_agreements.items()
        }
    }

    print(green(f"  Done. {len(agreement_scores)} respondent pairs analyzed."))
    record_ok("Section 12: CCT Eigenvalue Approximation")

except Exception as exc:
    record_error("Section 12: CCT Eigenvalue Approximation",
                 f"Failed to compute CCT analysis: {exc}",
                 "Check that Q7 responses have valid 'placements' with 'entity_id' and 'category_ids'.")

# ══════════════════════════════════════════════════════════════════════════
# SECTION 13: Expertise Tier Breakdowns
# ══════════════════════════════════════════════════════════════════════════
section_header(13, "Expertise Tier Breakdowns")
expertise_summary = {}

try:
    progress("Computing per-tier summary statistics...")
    for tier in ["casual", "professional", "insider"]:
        tier_pids = [pid for pid in tier_respondents[tier] if pid in responses]
        n_tier = len(tier_pids)
        if n_tier == 0:
            print(yellow(f"  Warning: No {tier} respondents with loaded responses."))
            expertise_summary[tier] = {"n_respondents": 0}
            continue

        q4_counts = [len(safe_get(responses[pid], "responses", "Q4", "recognized_entity_ids", default=[])) for pid in tier_pids]
        q5_counts = [len(safe_get(responses[pid], "responses", "Q5", "recognized_category_ids", default=[])) for pid in tier_pids]
        q7_counts = [len(safe_get(responses[pid], "responses", "Q7", "placements", default=[])) for pid in tier_pids]
        multi_place_counts = [
            sum(1 for pl in safe_get(responses[pid], "responses", "Q7", "placements", default=[]) if len(pl.get("category_ids", [])) > 1)
            for pid in tier_pids
        ]
        q2_lengths = [len(safe_get(responses[pid], "responses", "Q2", "free_list", default=[])) for pid in tier_pids]
        q12_scores = [safe_get(responses[pid], "responses", "Q12", "satisfaction_score") for pid in tier_pids]
        q12_scores = [s for s in q12_scores if s is not None]
        q1_dist = Counter()
        for pid in tier_pids:
            opt = safe_get(responses[pid], "responses", "Q1", "selected_option")
            if opt:
                q1_dist[opt] += 1
        non_peer_counts = [
            sum(1 for pj in safe_get(responses[pid], "responses", "Q6", "pair_judgments", default=[]) if pj.get("judgment") != "peers")
            for pid in tier_pids
        ]

        expertise_summary[tier] = {
            "n_respondents": n_tier,
            "avg_entities_recognized": round2(mean(q4_counts)),
            "avg_categories_recognized": round2(mean(q5_counts)),
            "avg_entities_placed": round2(mean(q7_counts)),
            "avg_multi_placements": round2(mean(multi_place_counts)),
            "avg_free_list_length": round2(mean(q2_lengths)),
            "avg_satisfaction": round2(mean(q12_scores)) if q12_scores else None,
            "engagement_distribution": dict(q1_dist),
            "avg_non_peer_judgments": round2(mean(non_peer_counts)),
            "std_entities_recognized": round2(std_dev(q4_counts)),
            "std_categories_recognized": round2(std_dev(q5_counts)),
        }

    print(green(f"  Done. Tier summaries: {', '.join(f'{t}={expertise_summary[t][\"n_respondents\"]}' for t in expertise_summary)}."))
    record_ok("Section 13: Expertise Tier Breakdowns")

except Exception as exc:
    record_error("Section 13: Expertise Tier Breakdowns",
                 f"Failed to compute tier breakdowns: {exc}",
                 "Check that persona expertise_tier values are 'casual', 'professional', or 'insider'.")

# ══════════════════════════════════════════════════════════════════════════
# BUILD aggregated_results.json
# ══════════════════════════════════════════════════════════════════════════
print(bold("\n── Writing aggregated_results.json ────────────────────────"))

try:
    os.makedirs(OUTPUT, exist_ok=True)
    domain_name = safe_get(domain_config, "domain", "name") if domain_config else "unknown"

    aggregated = {
        "metadata": {
            "domain": domain_name,
            "n_respondents": n_total,
            "n_entities": len(all_entity_ids),
            "n_categories": len(all_category_ids),
            "n_pairs": len(all_pair_ids),
            "n_blocks": len(block_entities),
            "expertise_distribution": {
                "casual": len(tier_respondents["casual"]),
                "professional": len(tier_respondents["professional"]),
                "insider": len(tier_respondents["insider"])
            },
            "computation_notes": "All rates rounded to 3 decimal places. Means and standard deviations rounded to 2 decimal places. Entity awareness uses block-aware denominators (n_exposed, not n_total)."
        },
        "section_01_entity_awareness": {
            "description": "Aided entity recognition rates from Q4, with block-aware denominators",
            "entities": sorted(entity_awareness.values(), key=lambda x: x["recognition_rate"], reverse=True)
        },
        "section_02_unaided_salience": {
            "description": "Smith's S salience scores from Q2 free-list recall",
            "entities": sorted(entity_smiths.values(), key=lambda x: x["smiths_s"], reverse=True)
        },
        "section_03_category_recognition": {
            "description": "Aided category recognition rates from Q5",
            "categories": sorted(category_recognition.values(), key=lambda x: x["recognition_rate"], reverse=True)
        },
        "section_04_pair_comparison_consensus": {
            "description": "Category pair relationship judgments from Q6. Consensus requires >40% of opinionated responses.",
            "pairs": [pair_consensus[pid] for pid in all_pair_ids if pid in pair_consensus]
        },
        "section_05_entity_placement": {
            "description": "Entity-to-category placement from Q7/Q8. Includes plurality category and distribution.",
            "entities": sorted(entity_placement.values(), key=lambda x: x["placement_rate"], reverse=True)
        },
        "section_06_co_placement_matrix": {
            "description": "Symmetric matrix of co-placement counts. Cell (i,j) = number of entities placed in both category i and category j by any respondent.",
            "category_ids": all_category_ids,
            "matrix": co_placement_matrix
        },
        "section_07_micro_monopoly": {
            "description": "Category ownership and descriptor phrases from Q9. Includes consensus strength and descriptor clustering.",
            "entities": sorted(
                [v for v in micro_monopoly.values() if v["total_selections"] > 0],
                key=lambda x: x["consensus_strength"],
                reverse=True
            )
        },
        "section_08_depth_perception": {
            "description": "Perceived category depth ratings from Q10 (1-5 scale)",
            "categories": sorted(depth_perception.values(), key=lambda x: x["mean_depth"], reverse=True)
        },
        "section_09_boundary_clarity": {
            "description": "Perceived category boundary clarity from Q11 (1-5 scale)",
            "categories": sorted(boundary_clarity.values(), key=lambda x: x["mean_clarity"], reverse=True)
        },
        "section_10_structure_satisfaction": {
            "description": "Overall satisfaction with category structure from Q12 (1-7 scale)",
            **structure_satisfaction
        },
        "section_11_open_ended_themes": {
            "description": "Thematic analysis of open-ended responses from Q13",
            **open_ended_analysis
        },
        "section_12_cct_eigenvalue_approximation": {
            "description": "Approximate Cultural Consensus Theory analysis based on pairwise agreement from Q7 placements",
            **cct_analysis
        },
        "section_13_expertise_tier_breakdowns": {
            "description": "Summary statistics broken down by expertise tier",
            "tiers": expertise_summary
        }
    }

    with open(OUTPUT / "aggregated_results.json", "w", encoding="utf-8") as f:
        json.dump(aggregated, f, indent=2, ensure_ascii=False)
    print(green(f"  Written: output/aggregated_results.json"))
    record_ok("Output: aggregated_results.json")

except Exception as exc:
    record_error("Output: aggregated_results.json",
                 f"Failed to write aggregated_results.json: {exc}",
                 "Check write permissions on the output/ directory.")

# ══════════════════════════════════════════════════════════════════════════
# BUILD CSV files
# ══════════════════════════════════════════════════════════════════════════
print(bold("\n── Writing CSV files ───────────────────────────────────────"))

try:
    os.makedirs(CSV_DIR, exist_ok=True)
except OSError as exc:
    record_error("CSV Setup", f"Cannot create CSV directory {CSV_DIR}: {exc}",
                 "Check write permissions on the output/ directory.")

def write_csv(filename, headers, rows, section_name):
    try:
        fpath = CSV_DIR / filename
        with open(fpath, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(headers)
            for row in rows:
                w.writerow(row)
        print(green(f"  Written: output/csv/{filename}"))
        record_ok(f"CSV: {filename}")
    except Exception as exc:
        record_error(f"CSV: {filename}",
                     f"Failed to write {filename}: {exc}",
                     "Check write permissions on output/csv/.")

# 1. entity_awareness.csv
if entity_awareness:
    rows = []
    for ea in sorted(entity_awareness.values(), key=lambda x: x["recognition_rate"], reverse=True):
        rows.append([
            ea["entity_id"], ea["label"], ea["n_exposed"], ea["n_recognized"],
            ea["recognition_rate"],
            ea["tier_rates"].get("casual", ""),
            ea["tier_rates"].get("professional", ""),
            ea["tier_rates"].get("insider", "")
        ])
    write_csv("entity_awareness.csv",
              ["entity_id", "label", "n_exposed", "n_recognized", "recognition_rate",
               "casual_rate", "professional_rate", "insider_rate"],
              rows, "entity_awareness")

# 2. category_recognition.csv
if category_recognition:
    rows = []
    for cr in sorted(category_recognition.values(), key=lambda x: x["recognition_rate"], reverse=True):
        rows.append([
            cr["category_id"], cr["label"], cr["n_recognized"],
            cr["recognition_rate"],
            cr["tier_rates"].get("casual", ""),
            cr["tier_rates"].get("professional", ""),
            cr["tier_rates"].get("insider", "")
        ])
    write_csv("category_recognition.csv",
              ["category_id", "label", "n_recognized", "recognition_rate",
               "casual_rate", "professional_rate", "insider_rate"],
              rows, "category_recognition")

# 3. pair_comparison_consensus.csv
if pair_consensus:
    rows = []
    for pc in [pair_consensus[pid] for pid in all_pair_ids if pid in pair_consensus]:
        jc = pc["judgment_counts"]
        tc = pc["tier_consensus"]
        rows.append([
            pc["pair_id"], pc["category_a_id"], pc["category_a_label"],
            pc["category_b_id"], pc["category_b_label"],
            pc["consensus_judgment"], pc["consensus_strength"],
            jc.get("peers", 0), jc.get("A_contains_B", 0),
            jc.get("B_contains_A", 0), jc.get("no_opinion", 0),
            tc.get("casual", {}).get("judgment", ""),
            tc.get("professional", {}).get("judgment", ""),
            tc.get("insider", {}).get("judgment", "")
        ])
    write_csv("pair_comparison_consensus.csv",
              ["pair_id", "category_a_id", "category_a_label", "category_b_id", "category_b_label",
               "consensus_judgment", "consensus_strength", "peers_count", "A_contains_B_count",
               "B_contains_A_count", "no_opinion_count",
               "casual_judgment", "professional_judgment", "insider_judgment"],
              rows, "pair_comparison_consensus")

# 4. entity_placement.csv
if entity_placement:
    rows = []
    for ep in sorted(entity_placement.values(), key=lambda x: x["placement_rate"], reverse=True):
        rows.append([
            ep["entity_id"], ep["label"], ep["n_exposed"], ep["n_placed"],
            ep["placement_rate"], ep["n_multi_placed"],
            ep["plurality_category_id"] or "", ep["plurality_category_label"] or "",
            ep["plurality_strength"]
        ])
    write_csv("entity_placement.csv",
              ["entity_id", "label", "n_exposed", "n_placed", "placement_rate",
               "n_multi_placed", "plurality_category_id", "plurality_category_label",
               "plurality_strength"],
              rows, "entity_placement")

# 5. co_placement_matrix.csv
if co_placement_matrix:
    rows = []
    for cid_a in all_category_ids:
        row = [cid_a] + [co_placement_matrix[cid_a].get(cid_b, 0) for cid_b in all_category_ids]
        rows.append(row)
    write_csv("co_placement_matrix.csv",
              ["category_id"] + all_category_ids,
              rows, "co_placement_matrix")

# 6. micro_monopoly.csv
if micro_monopoly:
    rows = []
    for mm in sorted(
        [v for v in micro_monopoly.values() if v["total_selections"] > 0],
        key=lambda x: x["consensus_strength"], reverse=True
    ):
        plur_cid = mm["plurality_category_id"]
        top_desc = ""
        if plur_cid and plur_cid in mm.get("descriptor_clusters", {}):
            top_desc = mm["descriptor_clusters"][plur_cid].get("representative", "")
        rows.append([
            mm["entity_id"], mm["label"], mm["total_selections"],
            mm["plurality_category_id"] or "", mm["plurality_category_label"] or "",
            mm["consensus_strength"], top_desc
        ])
    write_csv("micro_monopoly.csv",
              ["entity_id", "label", "total_selections", "plurality_category_id",
               "plurality_category_label", "consensus_strength", "top_descriptor"],
              rows, "micro_monopoly")

# 7. depth_clarity.csv
if depth_perception and boundary_clarity:
    rows = []
    for cid in all_category_ids:
        dp = depth_perception.get(cid, {})
        bc = boundary_clarity.get(cid, {})
        rows.append([
            cid, category_labels.get(cid, cid),
            dp.get("n_raters", 0), dp.get("mean_depth", 0), dp.get("std_depth", 0),
            bc.get("n_raters", 0), bc.get("mean_clarity", 0), bc.get("std_clarity", 0),
            (dp.get("tier_means") or {}).get("casual", ""),
            (dp.get("tier_means") or {}).get("professional", ""),
            (dp.get("tier_means") or {}).get("insider", ""),
            (bc.get("tier_means") or {}).get("casual", ""),
            (bc.get("tier_means") or {}).get("professional", ""),
            (bc.get("tier_means") or {}).get("insider", "")
        ])
    write_csv("depth_clarity.csv",
              ["category_id", "label", "n_depth_raters", "mean_depth", "std_depth",
               "n_clarity_raters", "mean_clarity", "std_clarity",
               "casual_depth", "professional_depth", "insider_depth",
               "casual_clarity", "professional_clarity", "insider_clarity"],
              rows, "depth_clarity")

# 8. expertise_tier_summary.csv
if expertise_summary:
    rows = []
    for tier in ["casual", "professional", "insider"]:
        es = expertise_summary.get(tier, {})
        if es.get("n_respondents", 0) > 0:
            rows.append([
                tier, es.get("n_respondents", 0), es.get("avg_entities_recognized", ""),
                es.get("avg_categories_recognized", ""), es.get("avg_entities_placed", ""),
                es.get("avg_multi_placements", ""), es.get("avg_free_list_length", ""),
                es.get("avg_satisfaction", ""), es.get("avg_non_peer_judgments", "")
            ])
    write_csv("expertise_tier_summary.csv",
              ["tier", "n_respondents", "avg_entities_recognized", "avg_categories_recognized",
               "avg_entities_placed", "avg_multi_placements", "avg_free_list_length",
               "avg_satisfaction", "avg_non_peer_judgments"],
              rows, "expertise_tier_summary")

# ══════════════════════════════════════════════════════════════════════════
# BUILD data_tables.txt (ASCII box-drawing tables)
# ══════════════════════════════════════════════════════════════════════════
print(bold("\n── Writing data_tables.txt ─────────────────────────────────"))

try:
    lines = []

    def box_row(cells, widths):
        parts = []
        for cell, w in zip(cells, widths):
            s = str(cell)
            parts.append(" " + s.ljust(w - 2) + " ")
        return "\u2502" + "\u2502".join(parts) + "\u2502"

    def make_table(title, headers, rows, widths=None):
        result = []
        result.append("")
        result.append(f"{'=' * 80}")
        result.append(f"  {title}")
        result.append(f"{'=' * 80}")
        result.append("")

        if widths is None:
            widths = []
            for i, h in enumerate(headers):
                col_max = len(str(h))
                for row in rows:
                    if i < len(row):
                        col_max = max(col_max, len(str(row[i])))
                widths.append(col_max + 2)

        result.append("\u250c" + "\u252c".join("\u2500" * w for w in widths) + "\u2510")
        result.append(box_row(headers, widths))
        result.append("\u251c" + "\u253c".join("\u2500" * w for w in widths) + "\u2524")
        for row in rows:
            result.append(box_row(row, widths))
        result.append("\u2514" + "\u2534".join("\u2500" * w for w in widths) + "\u2518")
        return result

    # Table 1: Top 30 Entity Awareness
    if entity_awareness:
        ea_sorted = sorted(entity_awareness.values(), key=lambda x: x["recognition_rate"], reverse=True)[:30]
        ea_headers = ["Rank", "Entity", "n_exp", "n_rec", "Rate", "Casual", "Prof", "Insider"]
        ea_rows = []
        for i, ea in enumerate(ea_sorted):
            ea_rows.append([
                i + 1, f"{ea['entity_id']} {ea['label'][:20]}", ea["n_exposed"], ea["n_recognized"],
                ea["recognition_rate"],
                ea["tier_rates"].get("casual", "-") if ea["tier_rates"].get("casual") is not None else "-",
                ea["tier_rates"].get("professional", "-") if ea["tier_rates"].get("professional") is not None else "-",
                ea["tier_rates"].get("insider", "-") if ea["tier_rates"].get("insider") is not None else "-"
            ])
        lines.extend(make_table("TABLE 1: Entity Awareness (Top 30 by Recognition Rate, Q4)", ea_headers, ea_rows))

    # Table 2: Unaided Salience Top 20
    if entity_smiths:
        ss_sorted = sorted(entity_smiths.values(), key=lambda x: x["smiths_s"], reverse=True)[:20]
        ss_headers = ["Rank", "Entity", "Smith's S", "Mentions", "Rate", "Casual S", "Prof S", "Insider S"]
        ss_rows = []
        for i, ss in enumerate(ss_sorted):
            ss_rows.append([
                i + 1, f"{ss['entity_id']} {ss['label'][:20]}", ss["smiths_s"],
                ss["mention_count"], ss["mention_rate"],
                ss["tier_smiths_s"].get("casual", 0.0),
                ss["tier_smiths_s"].get("professional", 0.0),
                ss["tier_smiths_s"].get("insider", 0.0)
            ])
        lines.extend(make_table("TABLE 2: Unaided Salience - Smith's S (Top 20, Q2)", ss_headers, ss_rows))

    # Table 3: Category Recognition
    if category_recognition:
        cr_sorted = sorted(category_recognition.values(), key=lambda x: x["recognition_rate"], reverse=True)
        cr_headers = ["Rank", "Category", "n_rec", "Rate", "Casual", "Prof", "Insider"]
        cr_rows = []
        for i, cr in enumerate(cr_sorted):
            cr_rows.append([
                i + 1, f"{cr['category_id']} {cr['label'][:25]}", cr["n_recognized"],
                cr["recognition_rate"],
                cr["tier_rates"].get("casual", "-") if cr["tier_rates"].get("casual") is not None else "-",
                cr["tier_rates"].get("professional", "-") if cr["tier_rates"].get("professional") is not None else "-",
                cr["tier_rates"].get("insider", "-") if cr["tier_rates"].get("insider") is not None else "-"
            ])
        lines.extend(make_table("TABLE 3: Category Recognition (All Categories, Q5)", cr_headers, cr_rows))

    # Table 4: Pair Comparison Consensus
    if pair_consensus:
        pc_headers = ["Pair", "Cat A", "Cat B", "Consensus", "Strength", "Peers", "A>B", "B>A"]
        pc_rows = []
        for pid in all_pair_ids:
            if pid not in pair_consensus:
                continue
            pc = pair_consensus[pid]
            jc = pc["judgment_counts"]
            pc_rows.append([
                pid,
                f"{pc['category_a_id'][:4]}", f"{pc['category_b_id'][:4]}",
                pc["consensus_judgment"][:15], pc["consensus_strength"],
                jc.get("peers", 0), jc.get("A_contains_B", 0), jc.get("B_contains_A", 0)
            ])
        lines.extend(make_table("TABLE 4: Pair Comparison Consensus (Q6)", pc_headers, pc_rows))

    # Table 5: Entity Placement Top 30
    if entity_placement:
        ep_sorted = sorted(entity_placement.values(), key=lambda x: x["placement_rate"], reverse=True)[:30]
        ep_headers = ["Rank", "Entity", "n_exp", "n_pla", "Rate", "Multi", "Plurality Cat", "P.Str"]
        ep_rows = []
        for i, ep in enumerate(ep_sorted):
            pcat = f"{ep['plurality_category_id'] or ''} {(ep['plurality_category_label'] or '')[:15]}"
            ep_rows.append([
                i + 1, f"{ep['entity_id']} {ep['label'][:18]}", ep["n_exposed"], ep["n_placed"],
                ep["placement_rate"], ep["n_multi_placed"],
                pcat.strip()[:20], ep["plurality_strength"]
            ])
        lines.extend(make_table("TABLE 5: Entity Placement (Top 30, Q7/Q8)", ep_headers, ep_rows))

    # Table 6: Micro-Monopoly Top 30
    if micro_monopoly:
        mm_sorted = sorted(
            [v for v in micro_monopoly.values() if v["total_selections"] > 0],
            key=lambda x: x["consensus_strength"], reverse=True
        )[:30]
        mm_headers = ["Rank", "Entity", "Sel", "Plur Cat", "Cons.Str", "Top Descriptor"]
        mm_rows = []
        for i, mm in enumerate(mm_sorted):
            plur_cid = mm["plurality_category_id"]
            top_desc = ""
            if plur_cid and plur_cid in mm.get("descriptor_clusters", {}):
                top_desc = mm["descriptor_clusters"][plur_cid].get("representative", "")[:30]
            mm_rows.append([
                i + 1, f"{mm['entity_id']} {mm['label'][:16]}", mm["total_selections"],
                f"{mm['plurality_category_id'] or ''} {(mm['plurality_category_label'] or '')[:12]}",
                mm["consensus_strength"], top_desc
            ])
        lines.extend(make_table("TABLE 6: Micro-Monopoly Results (Top 30, Q9)", mm_headers, mm_rows))

    # Table 7: Depth & Clarity
    if depth_perception and boundary_clarity:
        dc_headers = ["Category", "n_D", "Depth", "SD_D", "n_C", "Clarity", "SD_C"]
        dc_rows = []
        for cid in all_category_ids:
            dp = depth_perception.get(cid, {})
            bc = boundary_clarity.get(cid, {})
            dc_rows.append([
                f"{cid} {category_labels.get(cid, cid)[:22]}",
                dp.get("n_raters", 0), dp.get("mean_depth", 0), dp.get("std_depth", 0),
                bc.get("n_raters", 0), bc.get("mean_clarity", 0), bc.get("std_clarity", 0)
            ])
        lines.extend(make_table("TABLE 7: Category Depth & Boundary Clarity (Q10/Q11)", dc_headers, dc_rows))

    # Table 8: Structure Satisfaction
    if structure_satisfaction:
        sat_headers = ["Metric", "Value"]
        sat_rows = [
            ["Mean Score (1-7)", structure_satisfaction.get("mean_score", "N/A")],
            ["Std Dev", structure_satisfaction.get("std_score", "N/A")],
            ["N Respondents", structure_satisfaction.get("n_respondents", 0)],
            ["Casual Mean", (structure_satisfaction.get("tier_means") or {}).get("casual", "N/A")],
            ["Professional Mean", (structure_satisfaction.get("tier_means") or {}).get("professional", "N/A")],
            ["Insider Mean", (structure_satisfaction.get("tier_means") or {}).get("insider", "N/A")],
        ]
        for score in sorted((structure_satisfaction.get("score_distribution") or {}).keys()):
            sat_rows.append([f"Score {score} count", structure_satisfaction["score_distribution"][score]])
        lines.extend(make_table("TABLE 8: Structure Satisfaction (Q12)", sat_headers, sat_rows))

    # Table 9: Expertise Tier Summary
    if expertise_summary:
        et_headers = ["Metric", "Casual", "Professional", "Insider"]
        et_rows = []
        for metric_key, metric_label in [
            ("n_respondents", "N Respondents"),
            ("avg_entities_recognized", "Avg Entities Recognized"),
            ("avg_categories_recognized", "Avg Categories Recognized"),
            ("avg_entities_placed", "Avg Entities Placed"),
            ("avg_multi_placements", "Avg Multi-Placements"),
            ("avg_free_list_length", "Avg Free List Length"),
            ("avg_satisfaction", "Avg Satisfaction (1-7)"),
            ("avg_non_peer_judgments", "Avg Non-Peer Judgments"),
        ]:
            et_rows.append([
                metric_label,
                expertise_summary.get("casual", {}).get(metric_key, "N/A"),
                expertise_summary.get("professional", {}).get(metric_key, "N/A"),
                expertise_summary.get("insider", {}).get(metric_key, "N/A")
            ])
        lines.extend(make_table("TABLE 9: Expertise Tier Summary", et_headers, et_rows))

    # Table 10: CCT Approximation
    if cct_analysis:
        cct_headers = ["Metric", "Value"]
        cct_rows = [
            ["N Respondent Pairs", cct_analysis.get("n_respondent_pairs", 0)],
            ["Mean Pairwise Agreement", cct_analysis.get("mean_pairwise_agreement", 0)],
            ["Std Pairwise Agreement", cct_analysis.get("std_pairwise_agreement", 0)],
            ["Approx Eigenvalue Ratio", cct_analysis.get("approx_eigenvalue_ratio", 0)],
            ["Single Culture Indicated", cct_analysis.get("single_culture_indicated", False)],
        ]
        for key, val in (cct_analysis.get("tier_agreement") or {}).items():
            cct_rows.append([f"{key} Mean Agreement", val.get("mean_agreement", "")])
            cct_rows.append([f"{key} N Pairs", val.get("n_pairs", "")])
        lines.extend(make_table("TABLE 10: CCT Eigenvalue Approximation (Q7-based)", cct_headers, cct_rows))

    # Table 11: Open-Ended Themes
    if open_ended_analysis:
        theme_headers = ["Theme", "Count", "Rate"]
        theme_rows = []
        for theme_name, theme_data in (open_ended_analysis.get("themes") or {}).items():
            theme_rows.append([theme_name, theme_data["count"], theme_data["rate"]])
        lines.extend(make_table("TABLE 11: Open-Ended Response Themes (Q13)", theme_headers, theme_rows))

    # Table 12: Co-Placement Matrix (top pairs)
    if co_placement:
        co_pairs_sorted = sorted(co_placement.items(), key=lambda x: x[1], reverse=True)[:20]
        cop_headers = ["Rank", "Category A", "Category B", "Co-Placement Count"]
        cop_rows = []
        for i, (pair_key, count) in enumerate(co_pairs_sorted):
            cid_a, cid_b = pair_key
            cop_rows.append([
                i + 1,
                f"{cid_a} {category_labels.get(cid_a, cid_a)[:20]}",
                f"{cid_b} {category_labels.get(cid_b, cid_b)[:20]}",
                count
            ])
        lines.extend(make_table("TABLE 12: Top Co-Placement Pairs (Q7)", cop_headers, cop_rows))

    lines.append("")
    lines.append("=" * 80)
    lines.append("  NOTES")
    lines.append("=" * 80)
    lines.append("")
    lines.append("- Entity awareness uses block-aware denominators (n_exposed, not n_total)")
    lines.append("- Smith's S formula: (1/n) * Sum[(L_i - R_i + 1) / L_i], non-mentioners contribute 0")
    lines.append("- Pair consensus: highest count if >40% of opinionated responses, else no_consensus")
    lines.append("- CCT eigenvalue ratios are LLM-approximated, not formally computed. Interpret as directional only.")
    lines.append("- All rates: 3 decimal places. Means/SDs: 2 decimal places. Counts: integer.")
    lines.append("")

    with open(OUTPUT / "data_tables.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(green(f"  Written: output/data_tables.txt"))
    record_ok("Output: data_tables.txt")

except Exception as exc:
    record_error("Output: data_tables.txt",
                 f"Failed to write data_tables.txt: {exc}",
                 "Check write permissions on the output/ directory.")

# ══════════════════════════════════════════════════════════════════════════
# FINAL DIAGNOSTIC SUMMARY
# ══════════════════════════════════════════════════════════════════════════
print(bold("\n╔══════════════════════════════════════════════════════════╗"))
print(bold(  "║               AGGREGATION DIAGNOSTIC SUMMARY            ║"))
print(bold(  "╚══════════════════════════════════════════════════════════╝"))

succeeded = [s for s, r in section_results.items() if r == "ok"]
failed = [(s, r) for s, r in section_results.items() if r != "ok"]

print(f"\n  {green('Succeeded')} ({len(succeeded)}):")
for s in succeeded:
    print(f"    {green('✓')} {s}")

if failed:
    print(f"\n  {red('Failed')} ({len(failed)}):")
    for s, err in failed:
        print(f"    {red('✗')} {s}")
        print(f"        {err}")
    print(f"\n  {yellow('Suggested fixes')}:")
    for section, message, fix in all_errors:
        if fix:
            print(f"    [{section}] {fix}")
    sys.exit(1)
else:
    print(f"\n  {green('All sections completed successfully.')}")
    print(f"\n  Output files:")
    print(f"    output/aggregated_results.json")
    print(f"    output/data_tables.txt")
    for csv_name in ["entity_awareness.csv", "category_recognition.csv",
                     "pair_comparison_consensus.csv", "entity_placement.csv",
                     "co_placement_matrix.csv", "micro_monopoly.csv",
                     "depth_clarity.csv", "expertise_tier_summary.csv"]:
        print(f"    output/csv/{csv_name}")
