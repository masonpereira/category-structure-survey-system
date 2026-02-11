# Category Structure Survey System

A multi-agent pipeline that administers a fixed 13-question category structure survey to synthetic respondents, then aggregates, analyzes, and reports results. Designed to map how people mentally organize entities into categories within any consumer or professional domain.

## Quick Start

1. Place your `domain_config.json` in `/input/`
2. Run the Research Director prompt: `.claude/prompts/research-director.md`
3. Pipeline produces `/output/final_report.md` plus all intermediate artifacts

## Architecture

**7-agent sequential pipeline**, orchestrated by the Research Director:

| # | Agent | Temp | Input | Output |
|---|-------|------|-------|--------|
| 0 | Research Director | 0.0 | domain_config.json | orchestration |
| 1 | Instrument Builder | 0.0 | domain_config.json | instrument_registry.json |
| 2 | Persona Builder | 0.7 | instrument_registry.json, domain_config.json | personas.json |
| 3 | Survey Administrator | 0.6 | persona_id, personas.json, instrument_registry.json, domain_config.json | response_[id].json, persona_synthesis_[id].txt |
| 4 | Data Aggregator | 0.0 | all responses, instrument, personas, domain_config | aggregated_results.json, data_tables.txt, 8 CSVs |
| 5 | Research Analyst | 0.3 | aggregated_results.json, data_tables.txt | analysis.json |
| 6 | Report Writer | 0.4 | analysis.json, aggregated_results.json, data_tables.txt, personas.json | final_report.md |

## Pipeline Stages

```
BUILD_INSTRUMENT → BUILD_PERSONAS → ADMINISTER_SURVEY → AGGREGATE_DATA → ANALYZE → WRITE_REPORT
```

Each stage has a validation gate. The Research Director retries failed stages once before halting.

## The 13-Question Instrument

| Q# | Section | Type | Purpose |
|----|---------|------|---------|
| Q1 | awareness_salience | multiple_choice | Domain engagement frequency |
| Q2 | awareness_salience | free_list | Unaided entity recall |
| Q3 | category_recognition | free_list | Unaided category recall |
| Q4 | awareness_salience | checklist | Aided entity recognition (block-scoped) |
| Q5 | category_recognition | checklist | Aided category recognition |
| Q6 | hierarchy_perception | pair_comparison | Category hierarchy judgments |
| Q7 | entity_placement | entity_category_matrix | Entity-to-category placement (conditional on Q5) |
| Q8 | entity_placement | conditional_assignment | Primary category assignment (conditional on Q7) |
| Q9 | micro_monopoly | micro_monopoly_grid | Category ownership + 3-5 word descriptor per recognized entity (conditional on Q4/Q5) |
| Q10 | depth_perception | scale | Category depth perception |
| Q11 | depth_perception | scale | Category boundary clarity |
| Q12 | meta | scale | Category structure satisfaction |
| Q13 | meta | open_ended | Missing categories / misclassifications |

### Conditional Logic
- **Q5 → Q7**: Only categories recognized in Q5 appear as columns in the Q7 matrix
- **Q7 → Q8**: Only entities placed in 2+ categories in Q7 trigger Q8
- **Q4 → Q9**: Only entities recognized in Q4 appear in Q9 (and ALL of them must appear)
- **Q5 → Q9**: Only categories recognized in Q5 are available as Q9 category selections

## File System Contract

### Input
```
input/
  domain_config.json          # Required: domain entities, categories, pairs, blocks
  refinement_config.json      # Optional: partial rerun configuration
```

### Output (generated at runtime)
```
output/
  instrument_registry.json    # Hydrated 13-question instrument
  personas.json               # n synthetic respondent personas
  responses/
    response_R001.json        # Individual responses (one per persona)
    ...
  persona_synthesis/
    persona_synthesis_R001.txt # Voice anchor files (one per persona)
    ...
  aggregated_results.json     # All aggregated statistics
  data_tables.txt             # ASCII-formatted data tables
  csv/
    entity_awareness.csv
    category_recognition.csv
    pair_comparison_consensus.csv
    entity_placement.csv
    co_placement_matrix.csv
    micro_monopoly.csv
    depth_clarity.csv
    expertise_tier_summary.csv
  analysis.json               # 8 deliverables + findings + implications
  final_report.md             # Client-ready research report
  d3_taxonomy_tree.json       # D3-compatible nested JSON for collapsible tree visualization
```

### Schemas
```
schemas/
  domain_config.schema.json
  instrument_registry.schema.json
  personas.schema.json
  response.schema.json
  aggregated_results.schema.json
  analysis.schema.json
  refinement_config.schema.json
```

## Key Principles

### Fixed Instrument, Variable Domain
The 13 questions are hardcoded. The Instrument Builder validates domain data and hydrates placeholders — it does NOT design questions. This ensures structural consistency across any domain.

### Expertise-Tiered Analysis
Everything is segmented by three expertise tiers:
- **Casual** (default 40%): Occasional domain engagement, broad recognition patterns
- **Professional** (default 40%): Regular engagement, moderate depth
- **Insider** (default 20%): Deep expertise, fine-grained distinctions

### Block-Based Design
Entities are split into overlapping blocks of 30-40. Each respondent sees one block. This enables studying more entities than a single respondent could evaluate. **Critical**: entity awareness denominators use n_exposed (respondents who saw that entity), NOT total n.

### Conditional Flow Integrity
Q5 gates Q7 (only recognized categories are available). Q7 gates Q8 (only multi-placed entities trigger primary assignment). Every agent and every validation gate enforces this.

### Cognitive Style Drives Response Patterns
Personas have cognitive styles (lumper/splitter, hierarchy preference, boundary rigidity) that determine HOW they answer, not WHAT they answer. Category judgments emerge from the interaction of cognitive style with the survey instrument.

### Expanded Micro-Monopoly (Q9)
Q9 now covers ALL entities recognized by any respondent (gated by Q4), not just a pre-selected candidate list. Each respondent selects the one category each recognized entity "owns" (from Q5-recognized categories) AND provides a 3-5 word descriptor phrase capturing the entity's unique positioning. Descriptors are aggregated via semantic clustering, targeting ~80% consensus. The result is a complete micro-monopoly dictionary with both category ownership and positioning language for every entity in the domain.

### D3 Taxonomy Tree Output
The Report Writer generates `/output/d3_taxonomy_tree.json` — a D3-compatible nested JSON file where the consensus taxonomy hierarchy contains entity leaves with their descriptors. This enables interactive collapsible tree visualization. All entities must appear; unplaced entities go under an "Unplaced / Insufficient Data" node.

### CCT as Approximate Computation
Cultural Consensus Theory eigenvalue ratios are LLM-approximated, not formally computed. All reports include explicit caveats.

## 8 Analysis Deliverables

1. **Consensus Taxonomy Tree** — hierarchical category structure from pair-comparison consensus
2. **Entity Placement Map** — entity-to-category assignments with boundary entity identification
3. **Micro-Monopoly Dictionary** — which entities "own" which categories, with consensus descriptor phrases for ALL entities
4. **Awareness Rankings** — aided recognition + unaided salience (Smith's S)
5. **Depth Map** — perceived category depth × boundary clarity
6. **Expertise Divergence Report** — where tiers disagree on structure
7. **Recognition Gap Analysis** — knowledge asymmetries across tiers and aided/unaided
8. **CCT Analysis** — cultural consensus assessment with caveats

## Confidence Framework

Findings are assessed on three dimensions:
- **Tier Agreement**: Do casual, professional, and insider tiers converge?
- **Consensus Strength**: What proportion share the dominant view?
- **Cross-Question Corroboration**: Do multiple questions independently support the finding?

Confidence levels: **high** (all 3), **moderate** (2 of 3), **directional** (0-1).

## Refinement Runs

Place a `refinement_config.json` in `/input/` to partially rerun the pipeline:
- Retain prior artifacts
- Restart from any stage after BUILD_INSTRUMENT
- Adjust expertise distribution, exclude personas, change n_factor, refocus analysis

## Success Metrics

- All 13 questions consistently defined across instrument builder, response schema, and data aggregator
- Conditional logic (Q5→Q7, Q7→Q8) enforced in every response
- Block-aware denominators in all awareness calculations
- All 8 deliverables present in analysis and report
- Confidence assessments on every headline finding
- CCT caveat present wherever eigenvalue ratios are cited
- Q9 covers all Q4-recognized entities with Q5-gated categories and descriptors
- Micro-monopoly dictionary includes descriptor and descriptor_consensus_strength for every entity
- `d3_taxonomy_tree.json` exists, is valid JSON, contains all entities as leaves with descriptors
- Conditional logic (Q4→Q9, Q5→Q9) enforced in every response alongside Q5→Q7, Q7→Q8
