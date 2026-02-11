#!/usr/bin/env python3
"""
Data Aggregator - Category Structure Survey System
Computes all 13 aggregation sections and writes:
  - aggregated_results.json
  - data_tables.txt (ASCII box-drawing tables)
  - 8 CSV files in output/csv/
"""

import json
import os
import csv
import math
from collections import defaultdict, Counter
from pathlib import Path

BASE = Path("/Users/masonpereira/Desktop/category-structure-survey-system")
INPUT = BASE / "input"
OUTPUT = BASE / "output"
RESPONSES_DIR = OUTPUT / "responses"
CSV_DIR = OUTPUT / "csv"

# ── Load config files ──────────────────────────────────────────────────────
with open(INPUT / "domain_config.json") as f:
    domain_config = json.load(f)

with open(OUTPUT / "personas.json") as f:
    personas_data = json.load(f)

with open(OUTPUT / "instrument_registry.json") as f:
    instrument = json.load(f)

# ── Build lookup structures ────────────────────────────────────────────────
entity_labels = {e["entity_id"]: e["label"] for e in domain_config["entity_master_list"]}
category_labels = {c["category_id"]: c["label"] for c in domain_config["category_labels"]}
all_entity_ids = sorted(entity_labels.keys(), key=lambda x: int(x[1:]))
all_category_ids = sorted(category_labels.keys(), key=lambda x: int(x[1:]))

# Block definitions
entity_blocks = {}
block_entities = {}
for block in domain_config["entity_blocks"]:
    bid = block["block_id"]
    eids = block["entity_ids"]
    block_entities[bid] = set(eids)
    for eid in eids:
        entity_blocks.setdefault(eid, []).append(bid)

# Category pairs
category_pairs = {}
for p in domain_config["category_pairs"]:
    category_pairs[p["pair_id"]] = (p["category_a_id"], p["category_b_id"])
all_pair_ids = sorted(category_pairs.keys(), key=lambda x: int(x[1:]))

# Persona lookup
persona_lookup = {p["persona_id"]: p for p in personas_data["personas"]}
persona_ids = sorted(persona_lookup.keys(), key=lambda x: int(x[1:]))

# Block-to-respondents mapping
block_respondents = defaultdict(list)
for pid, p in persona_lookup.items():
    block_respondents[p["assigned_block_id"]].append(pid)

# Entity -> set of respondent IDs who were exposed
entity_exposed = defaultdict(set)
for pid, p in persona_lookup.items():
    bid = p["assigned_block_id"]
    for eid in block_entities[bid]:
        entity_exposed[eid].add(pid)

# Tier groupings
tier_respondents = defaultdict(list)
for pid, p in persona_lookup.items():
    tier_respondents[p["expertise_tier"]].append(pid)

# ── Load all responses ─────────────────────────────────────────────────────
responses = {}
for pid in persona_ids:
    fpath = RESPONSES_DIR / f"response_{pid}.json"
    with open(fpath) as f:
        responses[pid] = json.load(f)

# ── Helper functions ───────────────────────────────────────────────────────
def round3(x):
    """Round to 3 decimal places (rates, Smith's S)."""
    return round(x, 3)

def round2(x):
    """Round to 2 decimal places (means, std devs)."""
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

# ══════════════════════════════════════════════════════════════════════════
# SECTION 1: Entity Awareness (Q4) - Block-aware denominators
# ══════════════════════════════════════════════════════════════════════════
print("Computing Section 1: Entity Awareness...")

entity_awareness = {}
for eid in all_entity_ids:
    exposed = entity_exposed[eid]
    n_exposed = len(exposed)
    n_recognized = 0
    tier_rec = defaultdict(int)
    tier_exp = defaultdict(int)

    for pid in exposed:
        tier = persona_lookup[pid]["expertise_tier"]
        tier_exp[tier] += 1
        recognized_ids = responses[pid]["responses"]["Q4"]["recognized_entity_ids"]
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

# ══════════════════════════════════════════════════════════════════════════
# SECTION 2: Unaided Salience / Smith's S (Q2)
# ══════════════════════════════════════════════════════════════════════════
print("Computing Section 2: Unaided Salience (Smith's S)...")

# Normalize free-list mentions to entity IDs
label_to_entity = {}
for eid, label in entity_labels.items():
    label_to_entity[label.lower()] = eid
    # Handle common variations
    if "(" in label:
        # e.g., "Tether (USDT)" -> also match "Tether", "USDT"
        parts = label.replace("(", "").replace(")", "").split()
        for part in parts:
            label_to_entity[part.lower()] = eid

# Additional common name mappings
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
    """Match a free-list mention to an entity ID."""
    m = mention.strip().lower()
    if m in extra_mappings:
        return extra_mappings[m]
    if m in label_to_entity:
        return label_to_entity[m]
    # Try partial matching
    for label_lower, eid in label_to_entity.items():
        if m in label_lower or label_lower in m:
            return eid
    return None

# Compute Smith's S for each entity
n_total = len(persona_ids)
entity_smiths = {}

for eid in all_entity_ids:
    total_s = 0.0
    mention_count = 0
    tier_s = defaultdict(float)
    tier_n = defaultdict(int)

    for pid in persona_ids:
        tier = persona_lookup[pid]["expertise_tier"]
        tier_n[tier] += 1
        free_list = responses[pid]["responses"]["Q2"]["free_list"]
        L = len(free_list)
        found = False
        for rank_idx, mention in enumerate(free_list):
            matched_eid = match_entity(mention)
            if matched_eid == eid:
                R = rank_idx + 1  # 1-based rank
                s_i = (L - R + 1) / L
                total_s += s_i
                tier_s[tier] += s_i
                mention_count += 1
                found = True
                break
        # Non-mentioners contribute 0

    smiths_s = round3(total_s / n_total) if n_total > 0 else 0.0
    mention_rate = round3(mention_count / n_total)

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
category_unaided = defaultdict(int)
category_unaided_terms = defaultdict(list)
for pid in persona_ids:
    free_list = responses[pid]["responses"]["Q3"]["free_list"]
    for term in free_list:
        category_unaided_terms[term.lower()].append(pid)

# ══════════════════════════════════════════════════════════════════════════
# SECTION 3: Category Recognition (Q5)
# ══════════════════════════════════════════════════════════════════════════
print("Computing Section 3: Category Recognition...")

category_recognition = {}
for cid in all_category_ids:
    n_recognized = 0
    tier_rec = defaultdict(int)
    tier_n = defaultdict(int)

    for pid in persona_ids:
        tier = persona_lookup[pid]["expertise_tier"]
        tier_n[tier] += 1
        recognized = responses[pid]["responses"]["Q5"]["recognized_category_ids"]
        if cid in recognized:
            n_recognized += 1
            tier_rec[tier] += 1

    rate = round3(n_recognized / n_total)
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

# ══════════════════════════════════════════════════════════════════════════
# SECTION 4: Pair Comparison Consensus (Q6)
# ══════════════════════════════════════════════════════════════════════════
print("Computing Section 4: Pair Comparison Consensus...")

pair_consensus = {}
for pair_id in all_pair_ids:
    cat_a, cat_b = category_pairs[pair_id]
    judgment_counts = Counter()
    tier_judgments = defaultdict(Counter)

    for pid in persona_ids:
        tier = persona_lookup[pid]["expertise_tier"]
        pair_judgments = responses[pid]["responses"]["Q6"]["pair_judgments"]
        for pj in pair_judgments:
            if pj["pair_id"] == pair_id:
                j = pj["judgment"]
                judgment_counts[j] += 1
                tier_judgments[tier][j] += 1
                break

    # Determine consensus: >40% of opinionated (non-no_opinion) responses
    opinionated_total = sum(v for k, v in judgment_counts.items() if k != "no_opinion")
    if opinionated_total > 0:
        best_judgment = None
        best_count = 0
        for j, c in judgment_counts.items():
            if j != "no_opinion" and c > best_count:
                best_count = c
                best_judgment = j
        consensus_pct = round3(best_count / opinionated_total)
        if consensus_pct > 0.40:
            consensus = best_judgment
        else:
            consensus = "no_consensus"
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
        "category_a_label": category_labels[cat_a],
        "category_b_id": cat_b,
        "category_b_label": category_labels[cat_b],
        "judgment_counts": dict(judgment_counts),
        "opinionated_total": opinionated_total,
        "consensus_judgment": consensus,
        "consensus_strength": consensus_pct,
        "tier_consensus": tier_consensus_data
    }

# ══════════════════════════════════════════════════════════════════════════
# SECTION 5: Entity Placement (Q7, Q8)
# ══════════════════════════════════════════════════════════════════════════
print("Computing Section 5: Entity Placement...")

entity_placement = {}
for eid in all_entity_ids:
    category_counts = Counter()
    primary_counts = Counter()
    n_placed = 0
    n_multi_placed = 0
    tier_placements = defaultdict(Counter)

    exposed = entity_exposed[eid]
    for pid in exposed:
        tier = persona_lookup[pid]["expertise_tier"]
        placements = responses[pid]["responses"]["Q7"]["placements"]
        for pl in placements:
            if pl["entity_id"] == eid:
                cats = pl["category_ids"]
                n_placed += 1
                if len(cats) > 1:
                    n_multi_placed += 1
                for cid in cats:
                    category_counts[cid] += 1
                    tier_placements[tier][cid] += 1
                break

        # Check Q8 for primary assignments
        primary_assignments = responses[pid]["responses"]["Q8"]["primary_assignments"]
        for pa in primary_assignments:
            if pa["entity_id"] == eid:
                primary_counts[pa["primary_category_id"]] += 1
                break

    n_exposed = len(exposed)
    placement_rate = round3(n_placed / n_exposed) if n_exposed > 0 else 0.0

    # Determine plurality category
    if category_counts:
        plurality_cid = category_counts.most_common(1)[0][0]
        plurality_count = category_counts.most_common(1)[0][1]
        plurality_strength = round3(plurality_count / n_placed) if n_placed > 0 else 0.0
    else:
        plurality_cid = None
        plurality_count = 0
        plurality_strength = 0.0

    # Distribution
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

# ══════════════════════════════════════════════════════════════════════════
# SECTION 6: Co-Placement Matrix
# ══════════════════════════════════════════════════════════════════════════
print("Computing Section 6: Co-Placement Matrix...")

co_placement = defaultdict(int)
for pid in persona_ids:
    placements = responses[pid]["responses"]["Q7"]["placements"]
    for pl in placements:
        cats = pl["category_ids"]
        if len(cats) > 1:
            for i in range(len(cats)):
                for j in range(i + 1, len(cats)):
                    pair_key = tuple(sorted([cats[i], cats[j]]))
                    co_placement[pair_key] += 1

# Build symmetric matrix
co_placement_matrix = {}
for cid_a in all_category_ids:
    co_placement_matrix[cid_a] = {}
    for cid_b in all_category_ids:
        if cid_a == cid_b:
            co_placement_matrix[cid_a][cid_b] = 0
        else:
            pair_key = tuple(sorted([cid_a, cid_b]))
            co_placement_matrix[cid_a][cid_b] = co_placement.get(pair_key, 0)

# ══════════════════════════════════════════════════════════════════════════
# SECTION 7: Micro-Monopoly Results (Q9)
# ══════════════════════════════════════════════════════════════════════════
print("Computing Section 7: Micro-Monopoly Results...")

micro_monopoly = {}
for eid in all_entity_ids:
    cat_selections = Counter()
    descriptors_by_cat = defaultdict(list)
    all_descriptors = []
    tier_selections = defaultdict(Counter)

    exposed = entity_exposed[eid]
    for pid in exposed:
        tier = persona_lookup[pid]["expertise_tier"]
        entries = responses[pid]["responses"]["Q9"]["micro_monopoly_entries"]
        for entry in entries:
            if entry["entity_id"] == eid:
                cid = entry["selected_category_id"]
                desc = entry.get("descriptor", "")
                cat_selections[cid] += 1
                tier_selections[tier][cid] += 1
                if desc:
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

    # Category distribution
    cat_dist = {}
    for cid, count in cat_selections.most_common():
        cat_dist[cid] = {
            "count": count,
            "rate": round3(count / total_selections) if total_selections > 0 else 0.0,
            "descriptors": descriptors_by_cat[cid]
        }

    # Semantic clustering of descriptors (simplified: group by plurality category)
    # Find the most representative descriptor via keyword overlap
    def cluster_descriptors(descs):
        if not descs:
            return {"representative": "", "all_descriptors": [], "cluster_count": 0}
        # Use first descriptor as representative for simplicity;
        # real implementation would use NLP clustering
        # Group by common words
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

# ══════════════════════════════════════════════════════════════════════════
# SECTION 8: Depth Perception (Q10)
# ══════════════════════════════════════════════════════════════════════════
print("Computing Section 8: Depth Perception...")

depth_perception = {}
for cid in all_category_ids:
    scores = []
    tier_scores = defaultdict(list)

    for pid in persona_ids:
        tier = persona_lookup[pid]["expertise_tier"]
        depth_ratings = responses[pid]["responses"]["Q10"]["depth_ratings"]
        for dr in depth_ratings:
            if dr["category_id"] == cid:
                scores.append(dr["depth_score"])
                tier_scores[tier].append(dr["depth_score"])
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

# ══════════════════════════════════════════════════════════════════════════
# SECTION 9: Boundary Clarity (Q11)
# ══════════════════════════════════════════════════════════════════════════
print("Computing Section 9: Boundary Clarity...")

boundary_clarity = {}
for cid in all_category_ids:
    scores = []
    tier_scores = defaultdict(list)

    for pid in persona_ids:
        tier = persona_lookup[pid]["expertise_tier"]
        clarity_ratings = responses[pid]["responses"]["Q11"]["clarity_ratings"]
        for cr in clarity_ratings:
            if cr["category_id"] == cid:
                scores.append(cr["clarity_score"])
                tier_scores[tier].append(cr["clarity_score"])
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

# ══════════════════════════════════════════════════════════════════════════
# SECTION 10: Structure Satisfaction (Q12)
# ══════════════════════════════════════════════════════════════════════════
print("Computing Section 10: Structure Satisfaction...")

satisfaction_scores = []
tier_sat = defaultdict(list)
satisfaction_explanations = []

for pid in persona_ids:
    tier = persona_lookup[pid]["expertise_tier"]
    q12 = responses[pid]["responses"]["Q12"]
    score = q12["satisfaction_score"]
    explanation = q12.get("explanation", "")
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

# ══════════════════════════════════════════════════════════════════════════
# SECTION 11: Open-Ended Themes (Q13)
# ══════════════════════════════════════════════════════════════════════════
print("Computing Section 11: Open-Ended Themes...")

open_ended_responses = []
for pid in persona_ids:
    tier = persona_lookup[pid]["expertise_tier"]
    q13 = responses[pid]["responses"]["Q13"]
    text = q13.get("open_ended_response", "")
    if text:
        open_ended_responses.append({
            "persona_id": pid,
            "expertise_tier": tier,
            "response": text
        })

# Extract themes via keyword analysis
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

# ══════════════════════════════════════════════════════════════════════════
# SECTION 12: CCT Eigenvalue Approximation
# ══════════════════════════════════════════════════════════════════════════
print("Computing Section 12: CCT Eigenvalue Approximation...")

# Build agreement matrix from Q7 placements
# For each pair of respondents, compute proportion of shared placements
# Only consider entities both respondents were exposed to (via their shared block entities)

agreement_scores = []
respondent_pairs = []
for i in range(len(persona_ids)):
    for j in range(i + 1, len(persona_ids)):
        pid_a = persona_ids[i]
        pid_b = persona_ids[j]
        bid_a = persona_lookup[pid_a]["assigned_block_id"]
        bid_b = persona_lookup[pid_b]["assigned_block_id"]

        # Shared entities
        shared = block_entities[bid_a] & block_entities[bid_b]
        if not shared:
            continue

        # Build placement maps
        placements_a = {}
        for pl in responses[pid_a]["responses"]["Q7"]["placements"]:
            if pl["entity_id"] in shared:
                placements_a[pl["entity_id"]] = set(pl["category_ids"])

        placements_b = {}
        for pl in responses[pid_b]["responses"]["Q7"]["placements"]:
            if pl["entity_id"] in shared:
                placements_b[pl["entity_id"]] = set(pl["category_ids"])

        # Only consider entities both respondents placed
        both_placed = set(placements_a.keys()) & set(placements_b.keys())
        if not both_placed:
            continue

        # Jaccard-like agreement: intersection / union of category sets per entity
        agreements = []
        for eid in both_placed:
            cats_a = placements_a[eid]
            cats_b = placements_b[eid]
            if cats_a | cats_b:
                agreement = len(cats_a & cats_b) / len(cats_a | cats_b)
                agreements.append(agreement)

        if agreements:
            pair_agreement = mean(agreements)
            agreement_scores.append(pair_agreement)

# Approximate eigenvalue ratio
if agreement_scores:
    overall_agreement = round3(mean(agreement_scores))
    agreement_std = round2(std_dev(agreement_scores))
    # CCT heuristic: if mean agreement > 0.5, first eigenvalue likely dominant
    # Approximate ratio as mean_agreement / (1 - mean_agreement)
    if overall_agreement < 1.0:
        approx_ratio = round2(overall_agreement / (1 - overall_agreement))
    else:
        approx_ratio = 99.99
else:
    overall_agreement = 0.0
    agreement_std = 0.0
    approx_ratio = 0.0

# Tier-level agreement
tier_pair_agreements = defaultdict(list)
for i in range(len(persona_ids)):
    for j in range(i + 1, len(persona_ids)):
        pid_a = persona_ids[i]
        pid_b = persona_ids[j]
        tier_a = persona_lookup[pid_a]["expertise_tier"]
        tier_b = persona_lookup[pid_b]["expertise_tier"]
        bid_a = persona_lookup[pid_a]["assigned_block_id"]
        bid_b = persona_lookup[pid_b]["assigned_block_id"]

        shared = block_entities[bid_a] & block_entities[bid_b]
        if not shared:
            continue

        placements_a = {}
        for pl in responses[pid_a]["responses"]["Q7"]["placements"]:
            if pl["entity_id"] in shared:
                placements_a[pl["entity_id"]] = set(pl["category_ids"])

        placements_b = {}
        for pl in responses[pid_b]["responses"]["Q7"]["placements"]:
            if pl["entity_id"] in shared:
                placements_b[pl["entity_id"]] = set(pl["category_ids"])

        both_placed = set(placements_a.keys()) & set(placements_b.keys())
        if not both_placed:
            continue

        agreements = []
        for eid in both_placed:
            cats_a = placements_a[eid]
            cats_b = placements_b[eid]
            if cats_a | cats_b:
                agreement = len(cats_a & cats_b) / len(cats_a | cats_b)
                agreements.append(agreement)

        if agreements:
            pair_agreement = mean(agreements)
            if tier_a == tier_b:
                tier_pair_agreements[f"within_{tier_a}"].append(pair_agreement)
            else:
                key = f"between_{min(tier_a, tier_b)}_{max(tier_a, tier_b)}"
                tier_pair_agreements[key].append(pair_agreement)

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

# ══════════════════════════════════════════════════════════════════════════
# SECTION 13: Expertise Tier Breakdowns
# ══════════════════════════════════════════════════════════════════════════
print("Computing Section 13: Expertise Tier Breakdowns...")

expertise_summary = {}
for tier in ["casual", "professional", "insider"]:
    tier_pids = tier_respondents[tier]
    n_tier = len(tier_pids)

    # Avg entities recognized (Q4)
    q4_counts = []
    for pid in tier_pids:
        q4_counts.append(len(responses[pid]["responses"]["Q4"]["recognized_entity_ids"]))

    # Avg categories recognized (Q5)
    q5_counts = []
    for pid in tier_pids:
        q5_counts.append(len(responses[pid]["responses"]["Q5"]["recognized_category_ids"]))

    # Avg entities placed (Q7)
    q7_counts = []
    for pid in tier_pids:
        q7_counts.append(len(responses[pid]["responses"]["Q7"]["placements"]))

    # Avg multi-placements (Q7)
    multi_place_counts = []
    for pid in tier_pids:
        mp = sum(1 for pl in responses[pid]["responses"]["Q7"]["placements"] if len(pl["category_ids"]) > 1)
        multi_place_counts.append(mp)

    # Avg free list length (Q2)
    q2_lengths = []
    for pid in tier_pids:
        q2_lengths.append(len(responses[pid]["responses"]["Q2"]["free_list"]))

    # Avg satisfaction (Q12)
    q12_scores = [responses[pid]["responses"]["Q12"]["satisfaction_score"] for pid in tier_pids]

    # Engagement frequency distribution (Q1)
    q1_dist = Counter()
    for pid in tier_pids:
        q1_dist[responses[pid]["responses"]["Q1"]["selected_option"]] += 1

    # Pair judgment diversity (Q6) - how many non-peer judgments
    non_peer_counts = []
    for pid in tier_pids:
        pair_judgments = responses[pid]["responses"]["Q6"]["pair_judgments"]
        non_peer = sum(1 for pj in pair_judgments if pj["judgment"] != "peers")
        non_peer_counts.append(non_peer)

    expertise_summary[tier] = {
        "n_respondents": n_tier,
        "avg_entities_recognized": round2(mean(q4_counts)),
        "avg_categories_recognized": round2(mean(q5_counts)),
        "avg_entities_placed": round2(mean(q7_counts)),
        "avg_multi_placements": round2(mean(multi_place_counts)),
        "avg_free_list_length": round2(mean(q2_lengths)),
        "avg_satisfaction": round2(mean(q12_scores)),
        "engagement_distribution": dict(q1_dist),
        "avg_non_peer_judgments": round2(mean(non_peer_counts)),
        "std_entities_recognized": round2(std_dev(q4_counts)),
        "std_categories_recognized": round2(std_dev(q5_counts)),
    }

# ══════════════════════════════════════════════════════════════════════════
# BUILD aggregated_results.json
# ══════════════════════════════════════════════════════════════════════════
print("\nBuilding aggregated_results.json...")

aggregated = {
    "metadata": {
        "domain": domain_config["domain"]["name"],
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
        "computation_notes": "All rates rounded to 3 decimal places. Means and standard deviations rounded to 2 decimal places. Entity awareness uses block-aware denominators (n_exposed, not n_total=30)."
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
        "pairs": [pair_consensus[pid] for pid in all_pair_ids]
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

with open(OUTPUT / "aggregated_results.json", "w") as f:
    json.dump(aggregated, f, indent=2)
print(f"  Written: {OUTPUT / 'aggregated_results.json'}")

# ══════════════════════════════════════════════════════════════════════════
# BUILD CSV files
# ══════════════════════════════════════════════════════════════════════════
print("\nBuilding CSV files...")
os.makedirs(CSV_DIR, exist_ok=True)

# 1. entity_awareness.csv
with open(CSV_DIR / "entity_awareness.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["entity_id", "label", "n_exposed", "n_recognized", "recognition_rate",
                 "casual_rate", "professional_rate", "insider_rate"])
    for ea in sorted(entity_awareness.values(), key=lambda x: x["recognition_rate"], reverse=True):
        w.writerow([
            ea["entity_id"], ea["label"], ea["n_exposed"], ea["n_recognized"],
            ea["recognition_rate"],
            ea["tier_rates"].get("casual", ""),
            ea["tier_rates"].get("professional", ""),
            ea["tier_rates"].get("insider", "")
        ])
print(f"  Written: {CSV_DIR / 'entity_awareness.csv'}")

# 2. category_recognition.csv
with open(CSV_DIR / "category_recognition.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["category_id", "label", "n_recognized", "recognition_rate",
                 "casual_rate", "professional_rate", "insider_rate"])
    for cr in sorted(category_recognition.values(), key=lambda x: x["recognition_rate"], reverse=True):
        w.writerow([
            cr["category_id"], cr["label"], cr["n_recognized"],
            cr["recognition_rate"],
            cr["tier_rates"].get("casual", ""),
            cr["tier_rates"].get("professional", ""),
            cr["tier_rates"].get("insider", "")
        ])
print(f"  Written: {CSV_DIR / 'category_recognition.csv'}")

# 3. pair_comparison_consensus.csv
with open(CSV_DIR / "pair_comparison_consensus.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["pair_id", "category_a_id", "category_a_label", "category_b_id", "category_b_label",
                 "consensus_judgment", "consensus_strength", "peers_count", "A_contains_B_count",
                 "B_contains_A_count", "no_opinion_count",
                 "casual_judgment", "professional_judgment", "insider_judgment"])
    for pc in [pair_consensus[pid] for pid in all_pair_ids]:
        jc = pc["judgment_counts"]
        tc = pc["tier_consensus"]
        w.writerow([
            pc["pair_id"], pc["category_a_id"], pc["category_a_label"],
            pc["category_b_id"], pc["category_b_label"],
            pc["consensus_judgment"], pc["consensus_strength"],
            jc.get("peers", 0), jc.get("A_contains_B", 0),
            jc.get("B_contains_A", 0), jc.get("no_opinion", 0),
            tc.get("casual", {}).get("judgment", ""),
            tc.get("professional", {}).get("judgment", ""),
            tc.get("insider", {}).get("judgment", "")
        ])
print(f"  Written: {CSV_DIR / 'pair_comparison_consensus.csv'}")

# 4. entity_placement.csv
with open(CSV_DIR / "entity_placement.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["entity_id", "label", "n_exposed", "n_placed", "placement_rate",
                 "n_multi_placed", "plurality_category_id", "plurality_category_label",
                 "plurality_strength"])
    for ep in sorted(entity_placement.values(), key=lambda x: x["placement_rate"], reverse=True):
        w.writerow([
            ep["entity_id"], ep["label"], ep["n_exposed"], ep["n_placed"],
            ep["placement_rate"], ep["n_multi_placed"],
            ep["plurality_category_id"] or "", ep["plurality_category_label"] or "",
            ep["plurality_strength"]
        ])
print(f"  Written: {CSV_DIR / 'entity_placement.csv'}")

# 5. co_placement_matrix.csv
with open(CSV_DIR / "co_placement_matrix.csv", "w", newline="") as f:
    w = csv.writer(f)
    header = ["category_id"] + all_category_ids
    w.writerow(header)
    for cid_a in all_category_ids:
        row = [cid_a] + [co_placement_matrix[cid_a][cid_b] for cid_b in all_category_ids]
        w.writerow(row)
print(f"  Written: {CSV_DIR / 'co_placement_matrix.csv'}")

# 6. micro_monopoly.csv
with open(CSV_DIR / "micro_monopoly.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["entity_id", "label", "total_selections", "plurality_category_id",
                 "plurality_category_label", "consensus_strength", "top_descriptor"])
    for mm in sorted(
        [v for v in micro_monopoly.values() if v["total_selections"] > 0],
        key=lambda x: x["consensus_strength"], reverse=True
    ):
        # Get the top descriptor from the plurality category
        plur_cid = mm["plurality_category_id"]
        top_desc = ""
        if plur_cid and plur_cid in mm["descriptor_clusters"]:
            top_desc = mm["descriptor_clusters"][plur_cid].get("representative", "")
        w.writerow([
            mm["entity_id"], mm["label"], mm["total_selections"],
            mm["plurality_category_id"] or "", mm["plurality_category_label"] or "",
            mm["consensus_strength"], top_desc
        ])
print(f"  Written: {CSV_DIR / 'micro_monopoly.csv'}")

# 7. depth_clarity.csv
with open(CSV_DIR / "depth_clarity.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["category_id", "label", "n_depth_raters", "mean_depth", "std_depth",
                 "n_clarity_raters", "mean_clarity", "std_clarity",
                 "casual_depth", "professional_depth", "insider_depth",
                 "casual_clarity", "professional_clarity", "insider_clarity"])
    for cid in all_category_ids:
        dp = depth_perception[cid]
        bc = boundary_clarity[cid]
        w.writerow([
            cid, category_labels[cid],
            dp["n_raters"], dp["mean_depth"], dp["std_depth"],
            bc["n_raters"], bc["mean_clarity"], bc["std_clarity"],
            dp["tier_means"].get("casual", ""),
            dp["tier_means"].get("professional", ""),
            dp["tier_means"].get("insider", ""),
            bc["tier_means"].get("casual", ""),
            bc["tier_means"].get("professional", ""),
            bc["tier_means"].get("insider", "")
        ])
print(f"  Written: {CSV_DIR / 'depth_clarity.csv'}")

# 8. expertise_tier_summary.csv
with open(CSV_DIR / "expertise_tier_summary.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["tier", "n_respondents", "avg_entities_recognized", "avg_categories_recognized",
                 "avg_entities_placed", "avg_multi_placements", "avg_free_list_length",
                 "avg_satisfaction", "avg_non_peer_judgments"])
    for tier in ["casual", "professional", "insider"]:
        es = expertise_summary[tier]
        w.writerow([
            tier, es["n_respondents"], es["avg_entities_recognized"],
            es["avg_categories_recognized"], es["avg_entities_placed"],
            es["avg_multi_placements"], es["avg_free_list_length"],
            es["avg_satisfaction"], es["avg_non_peer_judgments"]
        ])
print(f"  Written: {CSV_DIR / 'expertise_tier_summary.csv'}")

# ══════════════════════════════════════════════════════════════════════════
# BUILD data_tables.txt (ASCII box-drawing tables)
# ══════════════════════════════════════════════════════════════════════════
print("\nBuilding data_tables.txt...")

lines = []

def box_line(widths, left, mid, right, fill):
    parts = [fill * w for w in widths]
    return left + mid.join(parts) + right

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

    # Top border
    result.append("\u250c" + "\u252c".join("\u2500" * w for w in widths) + "\u2510")
    # Header
    result.append(box_row(headers, widths))
    # Header separator
    result.append("\u251c" + "\u253c".join("\u2500" * w for w in widths) + "\u2524")
    # Data rows
    for row in rows:
        result.append(box_row(row, widths))
    # Bottom border
    result.append("\u2514" + "\u2534".join("\u2500" * w for w in widths) + "\u2518")
    return result

# ── Table 1: Top 30 Entity Awareness ──
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

# ── Table 2: Unaided Salience Top 20 ──
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

# ── Table 3: Category Recognition ──
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

# ── Table 4: Pair Comparison Consensus ──
pc_headers = ["Pair", "Cat A", "Cat B", "Consensus", "Strength", "Peers", "A>B", "B>A"]
pc_rows = []
for pid in all_pair_ids:
    pc = pair_consensus[pid]
    jc = pc["judgment_counts"]
    pc_rows.append([
        pid,
        f"{pc['category_a_id'][:4]}", f"{pc['category_b_id'][:4]}",
        pc["consensus_judgment"][:15], pc["consensus_strength"],
        jc.get("peers", 0), jc.get("A_contains_B", 0), jc.get("B_contains_A", 0)
    ])
lines.extend(make_table("TABLE 4: Pair Comparison Consensus (Q6)", pc_headers, pc_rows))

# ── Table 5: Entity Placement Top 30 ──
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

# ── Table 6: Micro-Monopoly Top 30 ──
mm_sorted = sorted(
    [v for v in micro_monopoly.values() if v["total_selections"] > 0],
    key=lambda x: x["consensus_strength"], reverse=True
)[:30]
mm_headers = ["Rank", "Entity", "Sel", "Plur Cat", "Cons.Str", "Top Descriptor"]
mm_rows = []
for i, mm in enumerate(mm_sorted):
    plur_cid = mm["plurality_category_id"]
    top_desc = ""
    if plur_cid and plur_cid in mm["descriptor_clusters"]:
        top_desc = mm["descriptor_clusters"][plur_cid].get("representative", "")[:30]
    mm_rows.append([
        i + 1, f"{mm['entity_id']} {mm['label'][:16]}", mm["total_selections"],
        f"{mm['plurality_category_id'] or ''} {(mm['plurality_category_label'] or '')[:12]}",
        mm["consensus_strength"], top_desc
    ])
lines.extend(make_table("TABLE 6: Micro-Monopoly Results (Top 30, Q9)", mm_headers, mm_rows))

# ── Table 7: Depth & Clarity ──
dc_headers = ["Category", "n_D", "Depth", "SD_D", "n_C", "Clarity", "SD_C"]
dc_rows = []
for cid in all_category_ids:
    dp = depth_perception[cid]
    bc = boundary_clarity[cid]
    dc_rows.append([
        f"{cid} {category_labels[cid][:22]}", dp["n_raters"], dp["mean_depth"], dp["std_depth"],
        bc["n_raters"], bc["mean_clarity"], bc["std_clarity"]
    ])
lines.extend(make_table("TABLE 7: Category Depth & Boundary Clarity (Q10/Q11)", dc_headers, dc_rows))

# ── Table 8: Structure Satisfaction ──
sat_headers = ["Metric", "Value"]
sat_rows = [
    ["Mean Score (1-7)", structure_satisfaction["mean_score"]],
    ["Std Dev", structure_satisfaction["std_score"]],
    ["N Respondents", structure_satisfaction["n_respondents"]],
    ["Casual Mean", structure_satisfaction["tier_means"]["casual"]],
    ["Professional Mean", structure_satisfaction["tier_means"]["professional"]],
    ["Insider Mean", structure_satisfaction["tier_means"]["insider"]],
]
for score in sorted(structure_satisfaction["score_distribution"].keys()):
    sat_rows.append([f"Score {score} count", structure_satisfaction["score_distribution"][score]])
lines.extend(make_table("TABLE 8: Structure Satisfaction (Q12)", sat_headers, sat_rows))

# ── Table 9: Expertise Tier Summary ──
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
        expertise_summary["casual"][metric_key],
        expertise_summary["professional"][metric_key],
        expertise_summary["insider"][metric_key]
    ])
lines.extend(make_table("TABLE 9: Expertise Tier Summary", et_headers, et_rows))

# ── Table 10: CCT Approximation ──
cct_headers = ["Metric", "Value"]
cct_rows = [
    ["N Respondent Pairs", cct_analysis["n_respondent_pairs"]],
    ["Mean Pairwise Agreement", cct_analysis["mean_pairwise_agreement"]],
    ["Std Pairwise Agreement", cct_analysis["std_pairwise_agreement"]],
    ["Approx Eigenvalue Ratio", cct_analysis["approx_eigenvalue_ratio"]],
    ["Single Culture Indicated", cct_analysis["single_culture_indicated"]],
]
for key, val in cct_analysis["tier_agreement"].items():
    cct_rows.append([f"{key} Mean Agreement", val["mean_agreement"]])
    cct_rows.append([f"{key} N Pairs", val["n_pairs"]])
lines.extend(make_table("TABLE 10: CCT Eigenvalue Approximation (Q7-based)", cct_headers, cct_rows))

# ── Table 11: Open-Ended Themes ──
theme_headers = ["Theme", "Count", "Rate"]
theme_rows = []
for theme_name, theme_data in open_ended_analysis["themes"].items():
    theme_rows.append([theme_name, theme_data["count"], theme_data["rate"]])
lines.extend(make_table("TABLE 11: Open-Ended Response Themes (Q13)", theme_headers, theme_rows))

# ── Table 12: Co-Placement Matrix (top pairs) ──
co_pairs_sorted = sorted(co_placement.items(), key=lambda x: x[1], reverse=True)[:20]
cop_headers = ["Rank", "Category A", "Category B", "Co-Placement Count"]
cop_rows = []
for i, (pair_key, count) in enumerate(co_pairs_sorted):
    cid_a, cid_b = pair_key
    cop_rows.append([
        i + 1,
        f"{cid_a} {category_labels[cid_a][:20]}",
        f"{cid_b} {category_labels[cid_b][:20]}",
        count
    ])
lines.extend(make_table("TABLE 12: Top Co-Placement Pairs (Q7)", cop_headers, cop_rows))

# Write footer
lines.append("")
lines.append("=" * 80)
lines.append("  NOTES")
lines.append("=" * 80)
lines.append("")
lines.append("- Entity awareness uses block-aware denominators (n_exposed, not n_total=30)")
lines.append("- Smith's S formula: (1/n) * Sum[(L_i - R_i + 1) / L_i], non-mentioners contribute 0")
lines.append("- Pair consensus: highest count if >40% of opinionated responses, else no_consensus")
lines.append("- CCT eigenvalue ratios are LLM-approximated, not formally computed. Interpret as directional only.")
lines.append("- All rates: 3 decimal places. Means/SDs: 2 decimal places. Counts: integer.")
lines.append("")

with open(OUTPUT / "data_tables.txt", "w") as f:
    f.write("\n".join(lines))
print(f"  Written: {OUTPUT / 'data_tables.txt'}")

print("\n" + "=" * 60)
print("  AGGREGATION COMPLETE")
print("=" * 60)
print(f"\nOutput files:")
print(f"  - {OUTPUT / 'aggregated_results.json'}")
print(f"  - {OUTPUT / 'data_tables.txt'}")
print(f"  - {CSV_DIR / 'entity_awareness.csv'}")
print(f"  - {CSV_DIR / 'category_recognition.csv'}")
print(f"  - {CSV_DIR / 'pair_comparison_consensus.csv'}")
print(f"  - {CSV_DIR / 'entity_placement.csv'}")
print(f"  - {CSV_DIR / 'co_placement_matrix.csv'}")
print(f"  - {CSV_DIR / 'micro_monopoly.csv'}")
print(f"  - {CSV_DIR / 'depth_clarity.csv'}")
print(f"  - {CSV_DIR / 'expertise_tier_summary.csv'}")
