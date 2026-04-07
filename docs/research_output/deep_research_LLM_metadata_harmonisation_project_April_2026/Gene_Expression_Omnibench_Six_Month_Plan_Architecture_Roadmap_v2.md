# Gene Expression Omnibench: Six-Month Research Plan, Codebase Architecture, and Research Roadmap for LLM-Based Omics Metadata Harmonization (v2)

---

## Document Index

| Line | Section |
|------|---------|
| 65   | Executive Summary |
| 85   | Conceptual Overview |
| 98   | **DELIVERABLE 1: PRIORITIZED SIX-MONTH RESEARCH PLAN** |
| 100  | 1.1 Competitive Landscape and Strategic Positioning |
| 104  | 1.1.1 Schema Matching Systems with Performance Numbers |
| 121  | 1.1.2 Search Pipeline Prior Systems |
| 134  | 1.1.3 Omics-Specific LLM Evaluations and Competitors |
| 152  | 1.1.4 White-Space Opportunities |
| 160  | 1.2 Experiment Inventory with Priority Scoring |
| 162  | 1.2.1 The Eleven-Variable Taxonomy |
| 182  | 1.2.2 Priority Score Formula and Experiment Classification |
| 186  | 1.2.3 P1 Experiments (8) — The Irreducible Core |
| 214  | 1.2.4 P2 Experiments (16+) — Strengthen the Paper (incl. S6b AutoAgent) |
| 233  | 1.2.5 P3 Experiments (8+) — Stretch Goals |
| 244  | 1.2.6 P-Extra Experiments (3) — Future Work |
| 248  | 1.2.7 Paper Section Mapping |
| 264  | 1.3 Month-by-Month Timeline |
| 266  | 1.3.1 The Four-Phase Successive Halving Methodology |
| 280  | 1.3.2 Conditional Architecture Roadmap |
| 293  | Month 1: Foundation + Harbor Apptainer Backend + Quick Wins |
| 313  | Month 2: Local Model Screening and Architecture Comparison |
| 331  | Month 3: Value Mapping, Multi-Table, Search Pipeline, S6b |
| 341  | Month 4: Ablations, N-Table (Stretch), and Search Refinement |
| 347  | Month 5: End-to-End and Comprehensive Analysis |
| 355  | Month 6: Paper Writing and Reproducibility |
| 361  | 1.4 Contingency Plans and Go/No-Go Decision Framework |
| 392  | 1.5 Resource Requirements |
| 408  | **DELIVERABLE 2: PROPOSED CODEBASE ARCHITECTURE** |
| 410  | 2.1 Current Architecture Assessment |
| 420  | 2.2 Proposed Architecture: geo-harmonizer v2 (directory tree) |
| 497  | 2.3 Key Architectural Changes (incl. Harbor/Apptainer for coding agents) |
| 539  | 2.4 Component Interfaces and Data Contracts |
| 619  | 2.5 What Should Not Change |
| 635  | 2.6 Inference Backend Deployment (vLLM, SGLang, GPU matrix) |
| 675  | 2.7 Observability and Prompt Management Stack |
| 690  | 2.8 Four-Layer Reproducibility Strategy |
| 704  | 2.9 Search Pipeline HPC Infrastructure |
| 730  | **DELIVERABLE 3: RESEARCH ROADMAP BEYOND SIX MONTHS** |
| 732  | 3.1 Publication 2: Search Pipeline and End-to-End (Months 7-12) |
| 760  | 3.2 Publication 3: Multi-Agent and N-Table (Months 12-18) |
| 787  | 3.3 P-Extra: Aspirational Future Work |
| 805  | Gap Analysis and Open Questions |
| 829  | Further Reading |

## Source Report References

| Label | File |
|-------|------|
| Report A | `Part_A_DeepResearch_Claude_LLM-based metadata harmonization for omics_state of the art and benchmark design.md` |
| Report B | `Part_B_DeepResearch_Claude_Designing a RAG search pipeline over GEO metadata for omics data harmonization.md` |
| Report C | `merged_Part_C_DeepResearch_Claude_optimal_agent_architecture_for_omics_metadata_harmonization.md` |
| Report D | `Part_D_with_QwenGemma_DeepResearch_Claude_Optimizing LLMs for Omics Metadata Harmonization A Comprehensive Methodological Guide.md` |

---

## Executive Summary

**Title:** *Gene Expression Omnibench: Benchmarking LLM-Based Metadata Harmonization for Omics Data*

**The problem.** Over 250,000 omics datasets in repositories like GEO remain difficult to find and harmonize for large-scale analyses. LLM-based tools promise automation, but no domain-specific benchmark exists, no systematic comparison of models and architectures has been conducted on omics metadata, and no practical guidelines exist for omics researchers choosing among the growing number of tools.

**What we will build.** (1) **Gene Expression Omnibench** — the first benchmark suite for omics metadata harmonization, comprising gold-standard tasks at five complexity levels (single-table schema matching through end-to-end search-and-harmonize); (2) a comprehensive comparison of classical methods (Valentine), embedding methods, LLM-based tools (Magneto, Matchmaker reimplementation, SCHEMORA, BDI-Kit), frontier models, local models, and frontier coding agents (Claude Code, Codex, OpenCode) on this benchmark, using the Harbor evaluation framework for standardized agent comparison and the AutoAgent meta-optimization loop for automated agent engineering; (3) a failure mode taxonomy with practical mitigation guidelines.

**What we expect to find.** LLM-based approaches will significantly outperform classical and embedding-based methods on omics-specific metadata, but the margin between a well-prompted frontier coding agent and a specialized multi-tool agent will be smaller than expected — suggesting context engineering matters more than tool architecture. We will test Matchmaker's finding that compositional pipeline design compensates for weaker backbone models in the omics domain, quantify the quality gap between frontier and local models, and identify Pareto-optimal configurations on the cost-quality frontier.

**Six-month plan at a glance.** 7 essential (P1) experiments form the irreducible core for a publishable paper: benchmark construction, Valentine baselines, frontier and local model screening, frontier coding agent baseline, Matchmaker reimplementation, and failure mode taxonomy. 16 important (P2) experiments strengthen the paper and are feasible within the timeline. 7 stretch (P3) experiments may spill to month 7-8 and feed a second publication. 3 aspirational (P-Extra) ideas are fully specified for future work. The experiment plan is organized around Report A's eleven-variable taxonomy of factors affecting LLM schema matching performance, and executed via Report D's four-phase successive halving methodology to manage the 270+ configuration space without brute force.

**Target venues.** BioDMS Workshop at VLDB 2026 (stepping stone, May 15 deadline), VLDB 2027 Experiments, Analyses & Benchmarks track (primary, rolling deadlines), NeurIPS 2026 Evaluations & Datasets track (May 4/6 deadline — aggressive but possible for a position paper).

**Why it matters.** This work gives the omics community a reusable benchmark for evaluating future harmonization tools, empirical evidence for which approaches work on their specific data, and practical "for budget X, use model Y with approach Z to achieve quality W" guidelines. The benchmark and evaluation framework will be publicly released on HuggingFace with Croissant machine-readable metadata.

**Key performance baselines from the literature.** The current state of the art on clinical benchmarks provides calibration for expected GEO performance: SCHEMORA achieves HitRate@5 = 80.39% on MIMIC-OMOP (the highest reported), Matchmaker achieves acc@1 = 62.20% with O(n) cost, Magneto achieves MRR = 0.860 on GDC-SM (up from 0.551 pre-fine-tuning), and ConStruM demonstrates that structured context engineering yields accuracy of 0.935 vs. 0.503 for raw context on disambiguation tasks. However, GEO metadata is measurably harder: "Toward Total Recall" (Sundaram et al., GigaScience 2025) shows GEO recall (44%) trails BioSample recall (82%) by 38 points under identical LLM conditions. For value mapping, the gap is even wider: Verbitsky et al. report 96% in-dictionary but only 17% out-of-dictionary accuracy — a 79-point gap that represents the hardest unsolved sub-problem.

---

## Conceptual Overview

Metadata harmonization for omics data — mapping the heterogeneous free-text annotations that researchers attach to their Gene Expression Omnibus (GEO) datasets into controlled vocabularies like the Genomic Data Commons (GDC) schema — sits at a productive intersection of four active research areas: classical schema matching (25 years of algorithms, now well-benchmarked via Valentine), LLM-based data integration (rapid progress from F1=0.04 to HitRate@5=80% in three years, but only on clinical schemas), agentic AI systems (where the "simplicity vs. capability" tradeoff is fiercely debated), and biomedical informatics (where GEO's free-text metadata is measurably harder than other repositories, with 38 percentage points lower recall than BioSample under identical LLM conditions).

The core tension this plan navigates is between **comprehensiveness and feasibility**: a single researcher in six months cannot explore the full combinatorial space of 10+ models × 5+ architectures × 3+ prompt strategies × 5+ quantization levels × 5 benchmark complexity levels. The resolution is a four-tier priority system (P1 essential → P-Extra aspirational) with explicit go/no-go gates, managed through a four-phase successive halving pipeline (Report D, lines 159–167) that reduces 270+ configurations to 3-5 final validated configurations without brute force.

Four key insights from the prior research reports shape every decision in this plan. First, **pipeline architecture dominates model choice** — Matchmaker demonstrated GPT-3.5 with a well-designed compositional pipeline outperforms GPT-4 with a simple pipeline (acc@1 = 62.20% vs. Jellyfish's 15.36%), implying the highest-ROI investment is pipeline design. Second, **multi-agent systems are the wrong default** for sequential reasoning tasks like schema matching, with empirical failure rates of 41-87% across frameworks and 39-70% performance degradation on sequential tasks (Cemri et al., NeurIPS 2025; Kim et al., Google DeepMind 2026). Third, **the benchmark is the primary contribution** — if system results are mixed, the benchmark alone justifies publication. Fourth, **the frontier coding agent comparison is the most provocative finding** — if Claude Code in full-auto mode matches a specialized pipeline, that reshapes the field's direction toward context engineering over tool development.

→ See Report A, lines 131–149 for the full eleven-variable taxonomy with estimated effect sizes per variable.
→ See Report C, lines 153–183 for the comprehensive case against multi-agent as default, with specific failure rates and conditions.

---

## DELIVERABLE 1: PRIORITIZED SIX-MONTH RESEARCH PLAN

### 1.1 Competitive Landscape and Strategic Positioning

Gap-filling searches across 10 queries confirm: **no published benchmark evaluates GEO-to-GDC metadata harmonization**. The closest existing resources are Magneto's GDC-SM benchmark and LLMatch's SchemaNet.

#### 1.1.1 Schema Matching Systems with Performance Numbers

**Magneto** (Liu et al., PVLDB 2025; GitHub: VIDA-NYU/magneto-matcher, Apache 2.0) achieves MRR = 0.860 with fine-tuned MPNet + LLaMA3.3-70B on the GDC-SM benchmark (10 CPTAC datasets, 736 GDC target columns), up from MRR = 0.551 before fine-tuning — a 56% relative improvement from self-supervised SLM training using LLM-generated synthetic data. GPT-4o-mini achieves MRR = 0.815. The GDC-SM benchmark covers pancreatic, renal, endometrial, lung, head/neck, breast, ovarian, colon, and brain cancers (Zenodo DOI: 10.5281/zenodo.14963588). Pre-trained GDC retrievers are available on HuggingFace. Magneto has not been applied to GEO free-text metadata.

**Matchmaker** (Seedat & van der Schaar, NeurIPS 2024 GenAI for Health Workshop; arXiv:2410.24105) achieves acc@1 = 62.20% (±2.40) on MIMIC-OMOP and 70.20% on Synthea-OMOP via a compositional three-stage pipeline (ColBERTv2 retrieval → dual candidate generation [semantic + reasoning] → MCQ confidence scoring with abstain option), reducing LLM calls from O(n²) to O(n) (~1,340 calls vs. ~24,771 for binary classification). DSPy BootstrapFewShot provides +5% acc@1. **No code has been released.** Oregon State reproduction attempts report that "Matchmaker fails when the LLM does not follow the required format in intermediate steps" — a critical reproducibility warning for the S7 reimplementation.

**SCHEMORA** (Gungor et al., arXiv:2507.14376, July 2025; GitHub: ermangungor/schemora) currently holds the highest reported hit rates on MIMIC-OMOP: HitRate@3 = 72.05% and HitRate@5 = 80.39%, surpassing Matchmaker (68.8%) and ReMatch (72.9%). Its approach generates enriched/alternative column names via Chain-of-Thought prompting, then builds hybrid indices (FAISS vector + BM25) over enriched names. Best configuration: GPT-4.1 + text-embedding-3-large + 3 generated names per column. SCHEMORA is the first open-source LLM schema matcher and is pip-installable — the most directly comparable and accessible baseline for our work.

**LLMatch** (Wang et al., APWeb-WAIM 2025; arXiv:2507.10897; GitHub: knowledge-fusion/LLMatch) introduced Rollup/Drilldown for multi-table schema matching: Rollup consolidates target columns into abstract concepts, Drilldown re-expands for fine-grained mapping. On MIMIC-to-OMOP, LLMatch achieves F1 = 0.30–0.85 across table pairs. Its SchemaNet benchmark (7 source-target pairs, average 14 tables and 135 columns per dataset, healthcare/finance/entertainment) is the only multi-table schema matching evaluation resource, directly relevant to Task Levels 3-4.

**ConStruM** (Chen et al., January 2026) demonstrates that structured context engineering dramatically outperforms raw context for disambiguation: accuracy of 0.935 vs. 0.503 on HRS-B when using context trees and differentiation cues. This result is key evidence for the paper's central thesis that context engineering matters more than model choice.

**Valentine** (Koutras et al., ICDE 2021) provides classical baselines (COMA, Cupid, SimilarityFlooding, DistributionBased, JaccardLevenMatcher). On MIMIC-III-to-OMOP complex tasks, COMA achieves only F1 = 0.04, SimilarityFlooding F1 = 0.09. Valentine's fabricated datasets are now widely criticized as too lexical — multiple 2025-2026 papers note they contain artificial patterns (e.g., "Gender"→"Ge") that inflate classical matcher scores.

→ See Report A, lines 9–57 for comprehensive descriptions of all classical and LLM-based schema matching systems.
→ See Report A, lines 59–67 for the value mapping landscape (MILA F1=0.83–0.95, MapperGPT ~67%, BERTMap, and the critical GDC value mapping constraints).

#### 1.1.2 Search Pipeline Prior Systems

**POE (Public Omics Explorer)** (Grigoriadis et al., Comp Struct Biotech J 27:4802-4812, 2025) is the closest existing GEO search system: semantic search over 250K+ GEO-linked records using SBioBERT (768-dim) + FAISS. POE searches only linked PubMed abstracts — not GEO metadata directly — creating coverage gaps for datasets without publications. It demonstrates that semantic search at GEO scale is practical and superior to keyword matching.

**GEOmetadb** (Zhu et al., Bioinformatics 2008) provides the SQL baseline for GEO queries but cannot handle semantic similarity. NCBI's native Entrez search supports Boolean queries but was "not intended for robust systematic analyses."

**BMQExpander** (Al Nazi et al., arXiv:2508.11784, 2025) achieves up to 22.1% improvement in NDCG@10 over sparse baselines via UMLS/MeSH/NCI ontology-guided query expansion, with 15.7% robustness improvement under query perturbation. This establishes the expected gain from ontology expansion for biomedical search.

Hybrid BM25 + dense retrieval with RRF improves recall by 15–30% over BM25 alone (consensus across multiple 2024–2025 studies), establishing a quantitative baseline for the search pipeline experiments (R1-R3).

→ See Report B, lines 7–58 for the full comparison of seven retrieval strategies with estimated Recall@100 ranges.
→ See Report B, lines 80–101 for the embedding model comparison table with recommended models per deployment tier.

#### 1.1.3 Omics-Specific LLM Evaluations and Competitors

**Elucidata multi-agent system** (bioRxiv June 2025) targets single-cell/single-nucleus RNA-seq from GEO using dedicated agents including an ontology reasoning agent (SapBERT + PubMedBERT + ontology graph traversal). Claims 93% recall across 23 GEO metadata fields but has no public benchmark.

**Kaier et al.** (BMC Research Notes 2026) evaluate GPT-4.1, Gemini, and Claude on metadata from GEO, ENA, PRIDE, and SRA — the most directly comparable published evaluation to our planned frontier model screening (S3). Their multi-repository scope makes this a key competitor paper.

**March 2026 bioRxiv preprint** demonstrates GPT-4o+RAG for GEO entity annotation at 77% accuracy (mouse strains) and 59% (cell lines), providing performance calibration for RAG-based approaches on GEO metadata.

**Verbitsky et al.** (Bioinformatics Advances 2025) fine-tuned GPT-2 models achieving 96% in-dictionary but only 17% out-of-dictionary accuracy ($29 total cost). The 79-point gap underscores how poorly current models generalize to unseen terminology.

**h5adify** (bioRxiv March 2026) demonstrates local LLM harmonization for single-cell AnnData using Gemma, Llama, Mistral, and Qwen via Ollama — high semantic accuracy with low hallucination rates.

**Harmonia v2** (Santos et al., arXiv:2502.07132, NOVAS'25) provides a full GDC harmonization demo and explicitly identifies "Agent Evaluation & Benchmarks" as an open research direction — Gene Expression Omnibench fills exactly this gap.

**The "Toward Total Recall" causal analysis.** The 38-point GEO-BioSample recall gap (44% vs. 82%) is attributable to three factors: (1) GEO lacks a dedicated CEDAR template, so BioSample templates were repurposed; (2) GEO's lengthy free-text values cause the LLM to deviate (e.g., generating "NSCLC tumor" instead of "lung"); (3) GEO lacks a structured data dictionary comparable to BioSample's. These three factors directly inform the context engineering experiments (S8) and value mapping approach (V1).

→ See Report A, lines 69–83 for the full omics domain gap analysis with all seven GEO-specific LLM studies.

#### 1.1.4 White-Space Opportunities

**Two confirmed white-space opportunities.** First, no systematic evaluation of frontier coding agents (Claude Code, Codex CLI) on structured biomedical data processing exists — existing coding benchmarks (SWE-bench, Terminal-Bench) test software engineering, not data integration. DABStep, KramaBench, and DA-Code test custom agents, not commercial coding products. Second, while Matchmaker validated DSPy's BootstrapFewShot for schema matching (+5% acc@1), nobody has applied DSPy's broader optimizer suite (MIPROv2, GEPA) to this task or to the omics domain, and no systematic comparison of DSPy-optimized vs. hand-crafted prompts across architectures exists.

**Venue timing.** NeurIPS 2026's "Evaluations & Datasets Track" has abstract deadline May 4 and paper deadline May 6, 2026. Requirements include HuggingFace/Dataverse hosting, Croissant machine-readable metadata, double-blind review, and reporting of compute, error bars, and CO2 emissions. VLDB 2027's EA&B track has rolling monthly deadlines with a three-badge reproducibility system — a safer primary target. The BioDMS Workshop at VLDB 2026 (May 15 deadline) provides a 2-4 page position paper stepping stone.

→ See Report D, lines 200–230 for full venue requirements and timeline analysis.

### 1.2 Experiment Inventory with Priority Scoring

#### 1.2.1 The Eleven-Variable Taxonomy

Report A identifies eleven variable categories affecting LLM schema matching performance, ranked by estimated effect size. This taxonomy provides the intellectual scaffolding connecting experiments to literature-grounded hypotheses — each experiment tests one or more of these variables:

| Priority | Variable | Estimated Effect | Tested By |
|----------|----------|-----------------|-----------|
| 1 | Agent architecture / pipeline formulation | Jellyfish 15.36% → Matchmaker 62.20% | S3, S6, S6b, S7 |
| 2 | Candidate generation strategy | Dual-source > single-source (Matchmaker, SCHEMORA) | S7, S8 |
| 3 | LLM choice | MRR 0.815 (GPT-4o-mini) → 0.860 (LLaMA3.3-70B) | S3, S4, S5 |
| 4 | Context content | 0.935 vs. 0.503 (ConStruM structured vs. raw) | S8 |
| 5 | Number of example values | 10 optimal (Magneto ablation) | S8b (new) |
| 6 | Schema representation | Full (736 cols) vs. pruned vs. few-shot | S8 |
| 7 | Ontology access method | 97% (GPT-4+CEDAR) vs. 80% (GPT-4 alone) | S8c (new) |
| 8 | Temperature / reasoning settings | Lower preferred for schema matching | S9 |
| 9 | Multi-turn / bidirectional matching | Symmetric transformations improve robustness | S9 |
| 10 | Prompt optimization | DSPy BootstrapFewShot +5% acc@1 | P1opt, P2opt |
| 11 | Context window management | RLM pattern for 736-col schemas | H1 (new) |

→ See Report A, lines 131–149 for the full taxonomy with citations and effect size justifications.

#### 1.2.2 Priority Score Formula and Experiment Classification

Priority Score = (Yield × Risk × Novelty) / (6 − Simplicity). Each experiment is scored on Simplicity (1-5, higher = easier), Yield (1-5, higher = more paper content), Risk (1-5, higher = more certain to produce useful results), and Novelty (1-5, higher = more unprecedented). Priority classification follows: P1 = irreducible core for publishable paper; P2 = substantially strengthens paper, feasible in 6 months; P3 = stretch, may spill to months 7-8; P-Extra = aspirational future work.

#### 1.2.3 P1 Experiments (8) — The Irreducible Core

These experiments, and only these, produce a publishable paper if nothing else gets done.

**B1: Single-table GDC gold standards** (Score=33.3). Construct 5-10 GEO metadata tables with expert-annotated mappings to GDC. Sources: Dou 2020 (existing), CPTAC studies with Li 2023 ground truth, 3-5 new GEO series spanning different cancer types and metadata complexity. Target ≥200 ground-truth column matches across 10+ tables for adequate statistical power (McNemar's test at power=0.80, α=0.05 can detect F1 differences of 0.10 with 100-200 instances). Require ≥3 annotators, target Cohen's κ ≥ 0.60. Existing curated GEO resources that could seed construction: CREEDS (4,205 curated signatures), STARGEO (42,950 annotations), Gemma (10,811 datasets with 10,215 ontology terms), OmicsMLRepo (212,027 samples with explicit original→curated mappings). No dependencies. *This is the most important single experiment — everything else depends on it.*

**Important timeline caveat:** Report D estimates benchmark creation at 6-10 weeks (lines 224-229), significantly longer than the 2-week allocation in the aggressive timeline below. The 2-week target covers a minimal viable benchmark (5 tables, ≥150 matches); benchmark expansion to Report A's 400+ match target (needed for detecting F1 differences of 0.05) continues as a background task through Month 3. The MIMIC-OMOP gold standard required 500 hours from two experts (Report A, line 107).

**B5: Extend evaluation pipeline** (Score=7.5, but essential infrastructure). Extend `calculate_all_metrics()` to support the new benchmark format, adding value mapping metrics (exact match for enums, semantic similarity via NCIt for partial credit), cross-table consistency scores, and statistical comparison utilities. Depends on B1. Low novelty but zero-risk infrastructure.

**S1: Valentine baselines** (Score=15.0). Run all five Valentine matchers (COMA, Cupid, SimilarityFlooding, DistributionBased, JaccardLevenMatcher) on the omics benchmark. These establish the floor performance. Valentine is pip-installable; execution is straightforward. Depends on B1.

**S3: Frontier LLM screening** (Score=20.0). Run top-3 frontier models (Claude Sonnet 4.6, GPT-5-mini, Gemini 2.5 Flash) × 3 architectures (ReAct+tools, CodeAct, frontier coding agent) = 9 configurations × 3 runs = 27 experiments. Include budget frontier baselines: DeepSeek V3.2 ($0.28/$0.42 per M tokens) and Qwen3.5-Flash ($0.10/M input) for the cost-quality Pareto analysis — the Pareto frontier cannot be properly drawn without points spanning the full cost range ($0.10 to $15 per M tokens). Depends on B1, B5. ~50 API calls, ~$100-200.

**S4: Local LLM screening** (Score=20.0). Run top-4 mid-range local models (Qwen3.5-35B-A3B, Gemma 4 26B-A4B, Gemma 4 31B dense, Qwen3.5-27B dense) × best architecture from S3 = 12-16 configurations × 3 runs. Updated model roster reflects Gemma 4 (released April 2, 2026) and Qwen 3.5 (February-March 2026). Additionally test at least one model on both vLLM and SGLang to determine whether inference framework affects accuracy (Report D, line 34). Depends on B1, B5. Requires vLLM on HPC GPU.

→ See Report D, lines 38–79 for the full GPU-specific deployment matrix and model specifications.

**S6: Frontier coding agent baseline** (Score=25.0). Run Claude Code, Codex CLI, and OpenCode on the same benchmark tasks, given only source CSV, target GDC schema, BDI-Kit as installed library, and a well-crafted CLAUDE.md with 5-10 difficult mapping examples. This is the "Kapoor test" — if frontier coding agents achieve ≥85% column mapping accuracy at <$5 per dataset, all bespoke pipeline work is premature optimization. **No published study has evaluated coding agents on structured biomedical data processing**, making this a genuinely novel baseline. **Execution via Harbor:** Use the Harbor framework (https://harborframework.com) for S6, which provides built-in Claude Code (1092-line implementation with full ATIF trajectory capture, session management, skills/memory/MCP registration), Codex, and OpenCode agents. Write Gene Expression Omnibench tasks in Harbor task format (instruction.md + Dockerfile + verifier). This eliminates the need to build `coding_agent.py` wrappers from scratch and gives us standardized ATIF trajectories for failure analysis (E2). Run via: `harbor run -p tasks/ -a claude-code -m anthropic/claude-sonnet-4-6`. Depends on B1.

→ See harbor_usage_usability_analysis.md, Section 4.2 for a complete example of a harmonization task in Harbor format.

**S7: Reimplement Matchmaker** (Score=25.0). Reimplement Matchmaker's compositional LM program (ColBERTv2 candidate retrieval + dual candidate generation [semantic + reasoning] → LLM refinement → MCQ confidence scoring with abstain option) adapted for GDC harmonization. Paper provides Algorithm 2 and full prompt examples (Appendix C). Also implement DSPy BootstrapFewShot optimization for this pipeline (+5% acc@1 validated in original paper). No code published, but well-documented algorithm. Note the Oregon State reproducibility warning regarding format-following failures in intermediate steps. Depends on B1. Effort: medium (2 weeks).

**E2: Failure mode taxonomy** (Score=30.0). Document failure modes from all experiments using the existing 20-class taxonomy across 6 categories (Infrastructure, Model Config, LLM Behavioral, Data/Config, Output, Diagnostic). Extend with GDC-specific failure modes: wrong mappings affect 20-40% of column pairs on complex schemas (Report A, line 157); value mapping ICD codes achieve under 50% accuracy (Report A, line 159); multi-turn conversation shows average 39% performance drop (Report A, line 165). This is a unique contribution that practitioners value highly. Begins in Month 1, completes in Month 5. Depends on S3, S4.

→ See Report A, lines 153–167 for the complete six-category failure taxonomy with measured frequencies.

#### 1.2.4 P2 Experiments (16+) — Strengthen the Paper

Aim to complete all; can be deprioritized if P1 takes longer.

**B2** (Score=16.0): Two-table harmonization gold standards (3-5 pairs). **B4** (Score=16.0): GEO search query gold standards — target 30+ queries (expanded from original 10-15) using three construction methods: semi-gold-standard from existing lab classifiers, programmatic semi-gold-standards from structured metadata, and TREC-style pooling with GPT-4o pre-screening (Report B, lines 110-120). **S2** (Score=12.0): Embedding model comparison — MPNet, BGE-large-en-v1.5, SapBERT, MedCPT, PubMedBERT, plus BMRETRIEVER-410M (SOTA biomedical retriever, outperforms 11.7× larger models; Report B, lines 86-90) and BGE-M3 (native sparse+dense). **S5** (Score=16.0): Small local LLMs — Qwen3.5-9B, Gemma 4 E4B, Mistral Nemo 12B. **S7b** (Score=12.0): LLMatch/Magneto comparison if code available. **S8** (Score=16.0): Context content ablation per ConStruM — vary sample values 0/5/10/20, schema representation (full/pruned/few-shot), and test Matchmaker's dual candidate generation insight.

**S8b (new, P2):** Example value count ablation — test 0/5/10/20 values per column to validate Magneto's finding that 10 is optimal for omics metadata. **S8c (new, P2):** Ontology access method ablation — test none vs. NCIt descriptions embedded in prompt vs. OAK tool-use API. The "Toward Total Recall" finding that GPT-4+CEDAR achieves 97% adherence vs. 80% without ontology constraints makes this a high-effect-size variable.

**S9** (Score=8.0): Temperature and reasoning settings ablation. **V1** (Score=16.0): Value mapping comparison (LLM vs. dictionary lookup vs. ontology matching). **M1** (Score=12.0): Two-table harmonization. **P1opt** (Score=12.0): Manual prompt optimization from error analysis.

**S6b (new, P2): AutoAgent meta-optimization for harmonization** (Score=15.0). After establishing the S6 baseline (fixed CLAUDE.md), run the AutoAgent meta-optimization loop (https://github.com/kevinrgu/autoagent) for 15-20 iterations. AutoAgent uses a coding agent as a "meta-agent" that iteratively improves the agent harness — modifying system prompts, tools, agent configuration, and orchestration — while hill-climbing on benchmark F1. The human programs `program.md` with harmonization-specific directives (domain context, available tools like BDI-Kit, what to optimize); the meta-agent programs `agent.py`. This directly tests whether automated agent engineering outperforms manual context engineering (the CLAUDE.md approach) on GEO→GDC harmonization. **No published work has applied meta-agent optimization to structured biomedical data processing.** Depends on B1, S6 (need baseline to compare against). Effort: ~1 week setup + 2-3 days unattended iteration. Cost: ~$20-50 per optimization run.

→ See harbor_usage_usability_analysis.md, Section 4.5 for the full AutoAgent setup guide with a harmonization-specific program.md template.

**R1** (Score=15.0): BM25 over SQLite FTS5 — configure with porter unicode61 tokenizer, column weighting (title 10×, summary 1×). **R2** (Score=16.0): Dense embedding retrieval using best model from S2 — specify reranker candidates: bge-reranker-v2-m3 (568M, best quality/efficiency) and ms-marco-MiniLM-L-12-v2 (33M, surprisingly effective on BioASQ 2025). **R3** (Score=8.0): Hybrid retrieval (BM25+dense) with RRF (k=60) — include ontology-guided query expansion as a variable (Report B, lines 39-41: up to 22.1% NDCG@10 improvement). **A1** (Score=5.3): Per-agent model configuration. **A2** (Score=8.0): Structured output validation with Pydantic + retry; additionally test constrained decoding (vLLM structured output mode, llama.cpp GBNF grammar) as a separate variable from post-hoc Pydantic validation — these are distinct mechanisms with different failure modes. **A4** (Score=10.0): Quantization sweep — Q4_K_M/Q5_K_M/Q6_K/Q8/F16; specify AWQ vs. GPTQ as an experimental variable (AWQ achieves 51.8% Pass@1 vs. GPTQ's 46.3% on HumanEval; Report D, line 103). **A5 (new, P2-P3):** Asymmetric Actor-Critic validation — test whether adding a cheap critic model (GPT-4o-mini or Haiku) to validate frontier model mappings improves F1 beyond the cost overhead.

→ See Report D, lines 82–103 for the full quantization analysis including AWQ vs. GPTQ benchmarks.
→ See Report B, lines 92–101 for the embedding model and reranker comparison table.

#### 1.2.5 P3 Experiments (8+) — Stretch Goals

Fully specified and ready to execute, but may spill to months 7-8.

**B3** (Score=16.0): N-table gold standard from CPTAC 10-table set. **V2** (Score=9.0): Constrained generation for value mapping using llama.cpp GBNF grammars or vLLM structured output. **M2** (Score=10.0): N-table harmonization (10 CPTAC tables). **M3** (Score=12.5): Multi-agent vs. single-agent for N-table. **P2opt** (Score=12.0): DSPy optimization with MIPROv2/GEPA — GEPA requires only 14 labeled examples at $2-3 cost (Report D, line 247). **R4** (Score=9.0): LLM reranking for search. **E1** (Score=12.5): End-to-end search→harmonize pipeline.

**H1 (new, P3): RLM vs. Fan-Out for Large-Schema Harmonization.** Test Recursive Language Model decomposition (Zhang et al., arXiv:2512.24601; 34+ accuracy point improvement on OOLONG) of GDC's 736-column schema against the fan-out parallel agent approach on the CPTAC 10-table dataset. The root LM writes code to partition columns into semantic groups and invokes sub-LMs for each group. Include cost and accuracy comparison. This experiment tests Variable 11 (context window management) from the eleven-variable taxonomy.

→ See Report C, lines 239–257 for the full RLM and Chain-of-Agents analysis.
→ See Report C, lines 377–408 for the four-phase architecture roadmap with go/no-go gates.

#### 1.2.6 P-Extra Experiments (3) — Future Work

**R5** (Score=6.75): Paper full-text embedding and retrieval. **R6** (Score=8.0): Agentic multi-step search. **A3** (Score=2.5): Streaming progress display.

#### 1.2.7 Paper Section Mapping

| Paper Section | Experiments |
|---------------|-------------|
| Introduction + Related Work | Literature from Reports A-D |
| Methods — Benchmark (§3) | B1, B5 |
| Methods — Experimental Setup (§4) | All S* experiments |
| Results — Classical Baselines (§5.1) | S1 |
| Results — Frontier Models (§5.2) | S3, S6, S6b |
| Results — Local Models (§5.3) | S4, S5 |
| Results — Architecture Comparison (§5.4) | S3 vs S6 vs S7 |
| Results — Ablations (§5.5) | S8, S8b, S8c, S9 |
| Results — Value Mapping (§5.6) | V1 |
| Discussion — Failure Modes (§6) | E2 |
| Discussion — Practical Guidelines (§7) | Cost-quality Pareto from all experiments |

### 1.3 Month-by-Month Timeline

#### 1.3.1 The Four-Phase Successive Halving Methodology

The experiment management follows Report D's four-phase successive halving pipeline (lines 159-167), mapped to calendar months:

**Phase 1 — Pilot & power analysis (Month 1, weeks 1-2):** Select ~20 representative configurations covering all factor levels (at least one frontier model, one mid-range local, one small local; at least one of each architecture). Run 1 time each on the benchmark. Include at least one Qwen 3.5 and one Gemma 4 model per tier to establish family-level baselines early.

**Phase 2 — Screening via successive halving (Month 2):** Evaluate all 270+ configurations on 10% of test instances (1 run). Eliminate bottom two-thirds. Promote survivors to 30% of test instances. Continue until ~30 configurations remain evaluated on the full test set. For S4/S5 local model experiments, 2-run screening is cost-effective during this phase.

**Phase 3 — Detailed comparison (Months 3-4, top 10-15 configurations):** Run 3-5 times each on the full test set. Apply mixed-effects models with test instance as random intercept.

**Phase 4 — Final validation (Month 5, top 3-5 configurations):** Run 5+ times on a held-out validation set. These numbers are reported in the paper.

→ See Report D, lines 151–178 for the full experimental design methodology including statistical test selection table.

#### 1.3.2 Conditional Architecture Roadmap

The month-by-month schedule below incorporates Report C's four-phase conditional architecture roadmap (lines 377-408). Critically, **Month 2 activities depend on Month 1 go/no-go outcomes** — the architecture phases are sequential and conditional, not parallel:

| Phase | Timeline | Focus | Go/No-Go Gate |
|-------|----------|-------|---------------|
| 1 | Weeks 1-4 | Frontier baseline (Claude Code + Codex) | If accuracy ≥85%: pivot to deepening that analysis |
| 2 | Months 2-3 | CodeAct + Magneto pipeline with DSPy | Must beat Phase 1 on Pareto frontier |
| 3 | Months 3-4 | Fan-out + critic verification | Only if multi-table needed |
| 4 | Months 5-6 | RLM for large schemas + HITL interface | Only for large-schema experiments |

→ See Report C, lines 391-397 for "What to Avoid" guidance: do not start with a hierarchical multi-agent supervisor; do not build LangGraph orchestration before validating single-agent; do not optimize for 10-table CPTAC before solving 1-table Dou 2020.

#### Month 1: Foundation, Benchmark Construction, and Quick Wins

**Weeks 1-2: Benchmark gold standard construction + Harbor Apptainer backend.** Execute B1 (5-10 single-table gold standards) and B5 (evaluation pipeline extension). Source tables from: Dou 2020 (already available), CPTAC studies with Li 2023 ground truth (already available), and 3-5 new GEO series representing different cancer types (breast, lung, colorectal) and metadata complexity levels (structured vs. free-text heavy). Consider seeding from existing curated resources: CREEDS, STARGEO, Gemma, OmicsMLRepo (Report A, line 113). Simultaneously begin B4 (10-15 search queries with semi-gold-standard GEO ID sets using existing lab classifications). Start GEO database construction as a background process — this requires downloading and parsing GEO SOFT files, building the SQLite+FTS5 database per the final_implementation_plan_GEO_db.md specification.

**In parallel (2-3 days in Week 1): Build the Harbor `ApptainerEnvironment` backend.** The HPC has no Docker daemon — Apptainer is the only container runtime available. Implement `BaseEnvironment` for Apptainer: `start()` → `apptainer instance start [--nv] [--bind ...] task.sif instance_name`; `exec()` → `apptainer exec [--env K=V] instance://name bash -c "cmd"`; `upload_file()` → pre-stage via bind mounts; `stop()` → `apptainer instance stop name`. Task Dockerfiles are converted to `.sif` images via `apptainer build task.sif docker://task-image:latest`. This is a hard prerequisite for all Harbor-based experiments (S6, S6b). Write the initial Gene Expression Omnibench tasks in Harbor task format during benchmark construction. Validate the backend on Harbor's example tasks (hello-world, llm-judge-example) before running S6.

→ See harbor_usage_usability_analysis.md, Section 5.3 for the full ApptainerEnvironment implementation sketch.

**Deliverables:** Benchmark dataset v1.0 (≥5 tables, ≥150 ground-truth column matches), evaluation pipeline v2.0 supporting schema matching and value mapping metrics, Harbor `ApptainerEnvironment` backend validated on example tasks, Gene Expression Omnibench tasks in Harbor format.

**Go/no-go:** If gold standards cannot be constructed for ≥5 tables by end of week 2, narrow to Dou 2020 + CPTAC tables only (≥4 tables, sufficient for initial experiments). Annotator recruitment and training should begin before Month 1. Benchmark expansion to 400+ matches continues as a background task (see Section 1.4 contingency on benchmark expansion).

**Weeks 3-4: Classical baselines + frontier model screening.** Execute S1 (Valentine baselines), S3 (frontier LLM screening — 9 configurations × 3 runs = 27 experiments), and S6 (Claude Code + Codex + OpenCode via Harbor on SLURM, using the ApptainerEnvironment backend built in Week 1). Begin E2 (failure mode documentation from each run). The S6 experiment is the single most important architectural decision point: if a frontier coding agent with only a CLAUDE.md file matches or exceeds a specialized agent with domain tools, this fundamentally redirects the research. Note: S6 requires outbound HTTPS from compute nodes for API calls — run on gateway/login nodes via SLURM if compute nodes lack internet, or use `--bind` to route through a proxy.

**Deliverables:** Valentine baseline results, frontier model results across 3 architectures, frontier coding agent baseline, initial failure mode observations.

**Person-hours:** ~80-100. **Compute:** ~50 frontier API calls (~$100-200). **GPU:** Negligible (all frontier API).

**Go/no-go decision (end of Month 1):** Two binary questions determine the paper's narrative. (1) Do LLM-based approaches outperform Valentine baselines? If not, investigate why — the "Toward Total Recall" three-factor causal analysis (no dedicated CEDAR template, free-text deviation, no structured data dictionary) suggests GEO-specific challenges that may need targeted context engineering. (2) Does the bespoke pipeline outperform frontier coding agents? If not, the paper becomes "off-the-shelf coding agents match or exceed specialized tools for omics metadata harmonization." **If coding agents achieve ≥85% accuracy, pivot Month 2 to deepening that analysis** (context engineering ablations on the CLAUDE.md, failure mode characterization) rather than proceeding with bespoke pipeline development.

#### Month 2: Local Model Screening and Architecture Comparison

**Conditional on Month 1 results.** If the frontier coding agent baseline proved dominant (≥85% accuracy), reduce the bespoke pipeline investment and redirect Month 2 toward: (a) more thorough coding agent evaluation (different CLAUDE.md designs, varying example counts, multiple coding agents), (b) context content ablation (S8) applied to the coding agent paradigm, and (c) begin quantization experiments with coding agent-style prompts on local models.

**If bespoke pipeline justified (the expected path):**

**Weeks 5-6: Local model experiments.** Execute S4 (4 mid-range local models × best architecture from Month 1, using vLLM on SLURM/Apptainer). The model roster has been updated to reflect the latest releases: Qwen3.5-35B-A3B (MoE, 3B active, Apache 2.0), Gemma 4 26B-A4B (MoE, ~4B active, Apache 2.0 — released April 2, 2026), Gemma 4 31B dense, and Qwen3.5-27B dense. Test at least one configuration on both vLLM and SGLang (Report D, line 34). Execute S5 (3 small local models: Qwen3.5-9B, Gemma 4 E4B, Mistral Nemo 12B). Execute A4 (quantization sweep: Q4_K_M/Q5_K_M/Q6_K/Q8/F16 for best local model, testing both AWQ and GPTQ formats). This quantization experiment fills a confirmed research gap — no published work isolates quantization effects on schema matching accuracy.

**Weeks 7-8: Architecture deep-dive.** Execute S2 (embedding model comparison: MPNet, BGE-large-en-v1.5, SapBERT, MedCPT, PubMedBERT, BMRETRIEVER-410M, BGE-M3 on benchmark), S8 (context content ablation with best frontier model), and begin S7 (Matchmaker reimplementation — allocate 2 weeks, with fallback to reporting reproduction challenges). Attempt S7b (LLMatch/Magneto comparison) if code is available.

**Background: Start search pipeline BM25 baseline + evaluation infrastructure** (Report B Phase 1, lines 196-197) as a parallel task — create FTS5 table, implement pytrec_eval-based evaluation, build initial expert queries. This spreads the search pipeline work across Months 2-4 rather than compressing it into Month 3.

**Deliverables:** Local vs. frontier comparison table, quantization impact curves, architecture comparison results, context ablation results, embedding baselines, Matchmaker reimplementation (or documented attempt).

**Compute:** ~100 GPU-hours on A100/A40, ~$50-100 API costs.

**Go/no-go decision (end of Month 2):** Which architecture wins — ReAct+tools, CodeAct, frontier coding agent, or Matchmaker compositional pipeline? This determines the focus for the remaining months.

#### Month 3: Value Mapping, Multi-Table, and Search Pipeline

**Weeks 9-10:** Execute V1 (value mapping comparison), B2 (two-table gold standards), M1 (two-table harmonization), and P1opt (manual prompt optimization based on Month 1-2 error analysis). Execute S8b (example value count ablation: 0/5/10/20) and S8c (ontology access method ablation: none vs. NCIt-embedded vs. OAK tool-use). Begin S6b (AutoAgent meta-optimization): fork AutoAgent, populate tasks/ with Harbor-formatted benchmark tasks from B1, write harmonization-specific program.md, run baseline, start meta-agent iteration loop (runs unattended for 2-3 days). Value mapping is the harder unsolved half of harmonization — the 79-point gap between in-dictionary (96%) and out-of-dictionary (17%) accuracy from Verbitsky et al. underscores the challenge.

**Weeks 11-12: Search pipeline Phases 2-3.** Deploy Qdrant via Apptainer. Execute R2 (embed GEO Series with best embedding model from S2). Execute R3 (hybrid retrieval with RRF). Add ontology-guided query expansion following BMQExpander approach. Add bge-reranker-v2-m3 cross-encoder on top-100 candidates. Test on gold-standard queries from B4. Expected improvements: +15-25% recall for hybrid over BM25 alone (Report B Phase 2), +10-15% additional recall from expansion and reranking (Report B Phase 3).

**Background task continuing: GEO database construction, benchmark expansion toward 400+ matches.**

**Deliverables:** Value mapping results, two-table harmonization results, search pipeline v1, retrieval evaluation.

#### Month 4: Ablations, N-Table (Stretch), and Search Refinement

**Weeks 13-14:** Execute S9 (temperature ablation), complete S8 (context ablation analysis), A1 (per-agent model configuration), A2 (structured output validation). Execute A5 (Asymmetric Actor-Critic) if Phase 2 of the architecture roadmap validated the bespoke pipeline. These are relatively low-effort experiments that fill out the ablation section of the paper.

**Weeks 15-16:** Begin P3 stretch goals: M2 (N-table harmonization if B3 gold standard is complete), R4 (LLM reranking for search), P2opt (DSPy optimization if benchmark ≥20 tables — GEPA requires only 14 examples at $2-3). These experiments have lower risk scores and may not produce results, but are worth attempting.

#### Month 5: End-to-End and Comprehensive Analysis

**Weeks 17-18:** Execute E1 (end-to-end search→harmonize on gold-standard queries, P3 stretch), complete E2 (finalize failure mode taxonomy with examples from all experiments, P1). The failure taxonomy is one of the paper's unique contributions — spend the time to make it comprehensive, with concrete examples and frequencies from the actual benchmark runs.

**Weeks 19-20:** Statistical analysis of all results: McNemar's exact test for pairwise binary comparisons (use exact form when discordant pairs <25), Cochran's Q → pairwise McNemar with Holm-Bonferroni for >2 configurations, Wilcoxon signed-rank across datasets, Friedman test with Nemenyi post-hoc for all-system comparison. Report bootstrap BCa 95% CIs and Cliff's δ effect sizes throughout (|δ|<0.147 negligible, <0.33 small, <0.474 medium, ≥0.474 large). Generate cost-quality Pareto frontier plots, failure mode distributions, and all paper figures.

→ See Report D, lines 169-178 for the statistical test selection table with switching criteria.

#### Month 6: Paper Writing and Reproducibility

**Weeks 21-22:** Draft paper: Introduction (revise with concrete results), Methods (benchmark construction, experimental setup, evaluation metrics), Results (schema matching comparison, architecture comparison, local vs. frontier, search pipeline, end-to-end), Discussion (failure modes, practical recommendations, limitations). Target ~10-12 pages for VLDB EA&B or NeurIPS E&D format.

**Weeks 23-24:** Reproducibility package: code on GitHub with MIT/Apache 2.0 license, experiment configs (YAML), Docker/Apptainer images, benchmark data on HuggingFace with Croissant metadata. Public release of Gene Expression Omnibench. Internal review and revision. Track and report CO2 emissions as required by NeurIPS. If targeting NeurIPS 2026, the paper must be ready by May 4-6 — this requires compressing the timeline by approximately 1 month, focusing solely on P1 experiments.

### 1.4 Contingency Plans and Go/No-Go Decision Framework

**If benchmark gold standard construction takes longer than 2 weeks:** Use only Dou 2020 + CPTAC tables with Li 2023 ground truth (already available). This gives ≥4 tables with ≥100 ground-truth column matches — sufficient for initial experiments and adequate statistical power to detect F1 differences of 0.10. Report D estimates 6-10 weeks for full benchmark creation; plan progressive expansion as a background task through Month 3, targeting Report A's 400+ match recommendation for detecting F1 differences of 0.05.

**If frontier coding agents outperform the bespoke pipeline:** This is itself a major finding. The paper becomes: "Off-the-shelf coding agents match or exceed specialized tools for omics metadata harmonization — implications for the field." The narrative shifts from "our pipeline is better" to "context engineering (the CLAUDE.md file) matters more than tool architecture." This is arguably more impactful and provocative, since it implies the field should invest in better prompts and context curation rather than more complex agent frameworks. **Month 2 pivots to deepening this finding:** more coding agent configurations, CLAUDE.md design ablations, failure characterization.

**If local models perform poorly relative to frontier:** Focus the paper on the frontier model comparison + failure taxonomy + practical guidelines. The local model results become a section quantifying the quality gap and its implications for budget-constrained labs. Report the Pareto frontier with cost-quality tradeoffs: "if your budget is $X per harmonization, use model Y with architecture Z to achieve quality W." Include Qwen3.5-Flash ($0.10/M) as a budget API baseline in the Pareto analysis.

**If GEO database construction is not complete by Month 3:** Use a subset of GEO (e.g., all human cancer studies, ~50K series) for the search experiments, and report results as preliminary. The full database can be completed post-publication. Alternatively, deprioritize search experiments (R1-R3) from P2 to P3 and strengthen the harmonization-focused paper.

**If LLMatch/Magneto code is not available or reproducible:** Report this as a limitation. Run Valentine baselines + embedding baselines as comparison points. Cite Magneto and LLMatch's published results on their respective benchmarks and note the comparison is limited by code availability — this is itself a useful data point about reproducibility in the field.

**If Matchmaker reimplementation takes longer than 2 weeks:** Implement a simplified version capturing the core insights: dual candidate generation (semantic retrieval + LLM reasoning) with MCQ confidence scoring. Omit ColBERTv2 integration and DSPy bootstrapping for the first pass. The simplified version still tests the compositional pipeline hypothesis.

**If NeurIPS deadline (May 4-6) is a target:** Compress the timeline to 4 months of experiments + 1 month of writing. Execute only P1 experiments. Submit results on 5-7 tables with frontier models, coding agents, and Valentine baselines. This is tight but achievable if benchmark construction begins immediately.

**If search pipeline returns poor results (Recall@100 < 0.50):** Investigate whether the failure is in BM25 (vocabulary mismatch), dense retrieval (wrong embedding model), or query formulation. Fall back to larger BM25 index with expanded synonym dictionaries. If Recall@100 cannot reach 0.65, defer search to Publication 2 and focus the paper on harmonization quality given known-relevant studies.

**If over-engineering threatens progress:** Follow Report C's "What to Avoid" guidance (lines 391-397): do not start with a hierarchical multi-agent supervisor, do not build a LangGraph orchestration layer before validating single-agent, do not optimize for the 10-table CPTAC dataset before solving the 1-table Dou 2020 benchmark. If complexity is growing without measured accuracy improvement, stop and consolidate.

**Pivotal go/no-go decisions:**

| Decision point | Timing | Question | If YES | If NO |
|---|---|---|---|---|
| End of Month 1 | Week 4 | Do LLMs outperform Valentine? | Proceed with full plan | Investigate GEO-specific challenges; may need domain-specific context engineering |
| End of Month 1 | Week 4 | Does bespoke pipeline outperform coding agents? | Develop bespoke pipeline further | Pivot to coding agent analysis (Report C Phase 1 gate) |
| End of Month 2 | Week 8 | Is best local model within 10% of frontier? | Local models become a central result | Report quality gap; focus on frontier + cost analysis |
| End of Month 3 | Week 12 | Is search pipeline producing useful results? | Include search in paper | Defer search to Publication 2 |
| End of Month 3 | Week 12 | Are 400+ ground-truth matches available? | Full statistical power for small effects | Report as limitation; focus on larger effect sizes |
| End of Month 4 | Week 16 | Can P3 experiments be completed in remaining time? | Execute stretch goals | Focus on polishing P1+P2 results |

### 1.5 Resource Requirements

| Resource | Quantity | Estimated Cost | Notes |
|---|---|---|---|
| GPU compute (A100/A40) | ~200 GPU-hours total | Free (institutional HPC) | vLLM inference for local models, embedding computation |
| Frontier model API costs | ~500-1000 API calls | ~$200-500 | Claude Sonnet 4.6 ($3/$15 per M tokens), GPT-5-mini, Gemini Flash, DeepSeek V3.2, Qwen3.5-Flash |
| Claude Code / Codex CLI | ~50-100 invocations | ~$50-150 | Frontier coding agent baseline (S6) |
| Storage for GEO database + embeddings | ~200 GB | Free (HPC storage) | SQLite DB (~50GB) + vector embeddings (~1GB) + papers (optional, ~100GB) |
| Expert annotation time for gold standards | ~40-60 person-hours | In-kind (lab members) | ≥3 annotators for B1, ≥2 for B2, B4 |
| Paper full-text downloads (P-Extra) | ~150K papers | ~100 GB storage + download time | Optional, deferred to Publication 2 |
| HuggingFace hosting | Benchmark dataset + Croissant metadata | Free (academic) | Required for NeurIPS/VLDB submission |

**Total estimated cash cost: $250-650.** The primary constraint is researcher time (1 person, 6 months), not compute or API costs. The largest hidden cost is expert annotation time for gold standards (B1, B2, B4), which requires coordinating with lab members who have GDC domain expertise.

---

## DELIVERABLE 2: PROPOSED CODEBASE ARCHITECTURE

### 2.1 Current Architecture Assessment

The current research fork (Harmonia) is a heavily extended version of the published BDI-Kit/Harmonia system (Lopez et al., Patterns 2026; Santos et al., arXiv 2025). It provides a working metadata harmonization agent with two primary paradigms: (1) ReAct + BDI-Kit domain tools (5 tools: `match_schema`, `rank_schema_matches`, `match_values`, `materialize_mapping`, `get_gdc_acceptable_values`) via the Archytas framework, and (2) true CodeAct where the LLM writes executable Python in markdown fences, executed via the Beaker kernel. The system includes Apptainer sandboxing for HPC, Phoenix/OTel tracing with OpenInference semantic conventions, a Plotly Dash dashboard with 8 tabs (overview, metrics, failure analysis, error analysis, trace explorer, token cost, comparison, activity log), YAML-configured experiments, a 20-class failure taxonomy across 6 categories, and an evaluation pipeline centered on `calculate_all_metrics()`.

**Strengths of the current architecture.** The dual-paradigm design (ReAct vs. CodeAct) is itself an experimental variable worth preserving. Phoenix/OTel tracing provides the observability needed for diagnosing agent failures. YAML experiment configs enable reproducible experiments. The Apptainer sandboxing works on institutional HPC. The failure taxonomy is a research asset. The `materialize_mapping` pattern (separating LLM-assisted discovery from deterministic execution) is a reproducibility asset to preserve.

**Gaps the v2 architecture must address.** (1) No support for the frontier coding agent paradigm (Claude Code / Codex headless) — addressed by adopting Harbor with an `ApptainerEnvironment` backend. (2) No compositional LM program architecture (Matchmaker pattern). (3) No benchmark infrastructure — gold standards, batch evaluation, statistical comparison. (4) No parameter sweep automation — experiments are launched individually. (5) No search pipeline. (6) No structured output validation (Pydantic). (7) No per-phase model configuration (e.g., cheap model for candidate generation, expensive model for reranking). (8) No prompt versioning system. (9) No quantization-aware serving configuration. (10) No inference backend configuration (vLLM/SGLang deployment specs). (11) No standardized agent evaluation framework — Harbor fills this gap for coding agent experiments, with Apptainer as the container runtime since no Docker daemon is available on the HPC.

→ See Report C, lines 317-336 for sandbox environment details including Apptainer mount scheme and frontier coding agent container setup.

### 2.2 Proposed Architecture: geo-harmonizer v2

The proposed architecture is designed for the complete vision (search + harmonization + observability + benchmark) but built incrementally. P1 components create foundations that P2/P3 naturally extend. Every boundary has a clean interface.

```
geo-harmonizer/
├── src/
│   ├── core/                        # Shared infrastructure
│   │   ├── model_factory.py         # [P2] Multi-model support (SRAgent Pattern 2)
│   │   ├── structured_output.py     # [P2] Pydantic validation + retry (SRAgent Pattern 3)
│   │   ├── tracing.py               # [KEEP] Extended for multi-agent traces
│   │   ├── config.py                # [EVOLVE] Phase-specific model/temperature overrides
│   │   ├── caching.py               # [P1] SHA-256 hash-keyed LLM call caching
│   │   └── inference.py             # [P2] vLLM/SGLang configuration and deployment
│   │
│   ├── search/                      # [P2/P3] GEO search pipeline
│   │   ├── geo_database/            # [P2] SQLite + FTS5 (from geo_metadata_db plan)
│   │   ├── embeddings/              # [P2] Vector store (Qdrant) for GEO descriptions
│   │   ├── retrieval.py             # [P2] Hybrid retrieval (BM25 + dense + reranking)
│   │   ├── query_expansion.py       # [P3] LLM-based ontology-guided expansion
│   │   └── evaluation.py            # [P3] Search-specific metrics (Recall@K, NDCG)
│   │
│   ├── harmonization/               # EVOLVED from current src/
│   │   ├── agents/
│   │   │   ├── bdikit_agent.py      # [KEEP] ReAct + domain tools
│   │   │   ├── codeact_agent.py     # [KEEP] True CodeAct
│   │   │   ├── coding_agent.py      # [P1] Minimal coding agent (bash+read+write)
│   │   │   ├── compositional.py     # [P1] Matchmaker-style fixed pipeline
│   │   │   └── multi_agent.py       # [P3] Hierarchical multi-agent (interface now)
│   │   ├── prompts/                 # [EVOLVE] Versioned Jinja2 templates + context mgmt
│   │   ├── tools/                   # [KEEP] BDI-Kit tools + extensions
│   │   └── materialize.py           # [KEEP] Deterministic mapping code generator
│   │
│   ├── evaluation/                  # EVOLVED from current
│   │   ├── metrics.py               # [EVOLVE] Schema matching + value mapping metrics
│   │   ├── benchmark.py             # [P1] Benchmark task runner
│   │   ├── comparison.py            # [P1] Statistical comparison (McNemar, bootstrap)
│   │   └── visualization.py         # [P2] Publication-quality plots
│   │
│   ├── dashboard/                   # [KEEP+EXTEND] Plotly Dash UI
│   │
│   └── experiment/                  # EVOLVED from src/automation/
│       ├── runner.py                # [EVOLVE] Multi-config support
│       ├── sweep.py                 # [P1] Automated parameter sweeps
│       └── analysis.py              # [P2] Post-experiment statistical analysis
│
├── benchmark/                       # [P1] Gene Expression Omnibench
│   ├── tasks/
│   │   ├── single_table_gdc/        # [P1] Task Levels 1-2 gold standards
│   │   ├── two_table/               # [P2] Task Level 3 gold standards
│   │   ├── n_table/                 # [P3] Task Level 4 gold standards
│   │   └── search_queries/          # [P2] Task Level 5 gold standards
│   ├── baselines/                   # [P1] Valentine + embedding baseline results
│   └── leaderboard.py              # [P2] Public leaderboard generation
│
├── sandbox/                         # EVOLVED
│   ├── apptainer.def               # [KEEP] Container definition
│   ├── launch.sh                    # [KEEP] SLURM integration
│   └── coding_agent_sandbox.sh     # [P1] Sandbox for coding agent testing
│
├── experiments/                     # EVOLVED
│   ├── configs/                     # Per-experiment YAML configs
│   ├── sweeps/                      # [P1] Parameter sweep definitions
│   └── results/                     # Experiment outputs (gitignored)
│
├── scripts/
│   ├── build_geo_db.py              # [P2] Build GEO metadata database
│   ├── embed_geo.py                 # [P2] Embed GEO descriptions
│   ├── run_benchmark.py             # [P1] Run full benchmark suite
│   └── generate_paper_figures.py    # [P2] Generate all paper figures
│
└── paper/                           # [Month 6] LaTeX source
    ├── figures/
    ├── tables/
    └── main.tex
```

### 2.3 Key Architectural Changes with Priority Markers

**1. coding_agent.py [P1].** The frontier coding agent experimental condition. Rather than building a custom wrapper from scratch, this component uses the **Harbor framework** (https://harborframework.com) which provides production-grade implementations for Claude Code (1092 lines with full ATIF trajectory capture, session management, skills/memory/MCP registration, Bedrock mode), Codex CLI (677 lines with trajectory extraction), and OpenCode. Harbor's `BaseAgent` interface handles installation, execution, structured output capture, and lifecycle management inside containers. Gene Expression Omnibench tasks are written in Harbor's task format (instruction.md + Dockerfile + verifier) and run via `harbor run -p tasks/ -a claude-code -m anthropic/claude-sonnet-4-6`.

For the AutoAgent meta-optimization experiment (S6b), the harness follows AutoAgent's pattern: a single `agent.py` with an editable section (system prompt, tools, orchestration) and a fixed Harbor adapter boundary. The meta-agent (Claude Code or Codex acting as the "outer" agent) iteratively edits the harness, runs the benchmark, and hill-climbs on F1.

Harbor uses Docker as its default container runtime. Since the HPC has no Docker-capable nodes, an `ApptainerEnvironment` backend implementing Harbor's `BaseEnvironment` interface is a **P1 infrastructure prerequisite** (estimated 2-3 days). The implementation maps cleanly: `docker compose build` → `apptainer build task.sif docker://...`; `docker compose up` → `apptainer instance start`; `docker compose exec` → `apptainer exec instance://...`; `docker compose down` → `apptainer instance stop`. Task Dockerfiles are converted to Apptainer `.sif` images with a single command. See harbor_usage_usability_analysis.md Section 5.3 for the implementation sketch.

*Replaces: custom coding agent wrapper. Effort: small (task authoring, ~1-2 days). Risk: very low.*

→ See harbor_usage_usability_analysis.md for the complete Harbor onboarding guide, task format examples, and Apptainer compatibility analysis.

**2. compositional.py [P1].** Reimplementation of Matchmaker's three-stage pipeline: (i) dual candidate generation — ColBERTv2 (or a cross-encoder fallback) retrieval combined with LLM reasoning-based candidates; (ii) LLM refinement — narrows combined candidate set; (iii) MCQ confidence scoring with an abstain option. Also implements DSPy BootstrapFewShot optimization for each stage. This is a fixed pipeline (no agent loop), making it deterministic in structure though not in LLM outputs. Each stage is independently optimizable. *Replaces: nothing (new paradigm). Effort: medium (2 weeks). Risk: low — Algorithm 2 + Appendix C prompts in paper provide sufficient detail.*

→ See Report C, lines 213-235 for the full Matchmaker and Magneto pipeline design analysis.

**3. benchmark/ directory [P1].** The Gene Expression Omnibench. Gold standard tasks in standardized JSON format, evaluation code that computes all metrics, and baseline results for reference. The task format is a `BenchmarkTask` dataclass with task_id, complexity level (1-5), source table path, target schema path, gold standard mappings, and metadata. The evaluation code wraps `calculate_all_metrics()` with additional value mapping metrics and cross-table consistency scores. *Replaces: ad hoc evaluation. Effort: large (mostly annotation work, ~40-60 person-hours). Risk: low.*

**4. sweep.py [P1].** Automated parameter sweeps across models, architectures, prompt variants, and quantization levels. Generates SLURM job arrays from sweep definition YAML files. Implements the four-phase successive halving methodology (Report D, lines 159-167): Phase 1 pilot on representative configurations, Phase 2 screening on 10% of test instances with bottom-⅔ elimination, Phase 3 detailed comparison on survivors, Phase 4 final validation on held-out set. Manages experiment namespacing, result collection, and parallel execution. *Replaces: manual SLURM script generation. Effort: medium (1 week). Risk: low.*

**5. comparison.py [P1].** Statistical comparison utilities: McNemar's exact test for pairwise binary comparisons (use exact form when discordant pairs <25, asymptotic otherwise), Cochran's Q for >2 configurations, Wilcoxon signed-rank for continuous metrics, Friedman test with Nemenyi post-hoc, bootstrap BCa 95% confidence intervals, Cliff's δ effect sizes, and Bonferroni/Holm correction for multiple comparisons. All implemented using scipy.stats and custom bootstrap code. *Replaces: nothing (new). Effort: small (2-3 days). Risk: very low.*

**6. caching.py [P1].** Exact-match LLM call caching using SHA-256 hash of (prompt string + model ID + generation parameters) as cache key. Stores first successful response in SQLite. Makes the application deterministic at the interface boundary. Integrates with tracing so cached calls are marked as such in Phoenix. *Replaces: nothing (new). Effort: small (1-2 days). Risk: very low.*

**7. model_factory.py [P2].** Per-phase model support via SRAgent's Pattern 2. Enables testing different models for candidate generation vs. reranking vs. value mapping within a single experiment run (e.g., Qwen3.5-9B for cheap candidate generation, Claude Sonnet for expensive reranking). Configuration via YAML: `phases: {candidates: "qwen3.5-9b", reranking: "claude-sonnet-4.6", value_mapping: "gemma-4-26b"}`. For multi-agent (P3), extend to per-agent configuration: `agents: {schema_matcher: "qwen3.5-35b", critic: "gpt-4o-mini"}`. *Replaces: single-model assumption. Effort: small. Risk: low.*

→ See Report C, lines 95-127 for the SRAgent agent-as-tool-factory pattern and hierarchical supervisor architecture, including the `create_esearch_agent()` code pattern showing how sub-agents are wrapped as callable tools.

**8. structured_output.py [P2].** Pydantic validation for agent outputs (column_mapping.json, value_mapping.json) with automatic retry on validation failure — SRAgent's Pattern 3. Reduces hallucinated output failures. The retry mechanism re-prompts with the validation error message, giving the LLM a chance to self-correct. Maximum 3 retries before falling back to partial results. Additionally implement SRAgent's Pattern 5 (regex-first extraction with LLM fallback): for value mapping, many GDC enumerated values have exact string matches that do not need LLM processing — regex-first extraction at <1ms reduces both cost and error rate. *Replaces: nothing (defensive addition). Effort: small. Risk: low.*

→ See Report C, lines 412-426 for the full 8-pattern SRAgent inventory with effort/risk assessments.

**9. search/ module [P2 for database, P3 for full pipeline].** Full GEO search pipeline: SQLite+FTS5 for BM25, Qdrant for dense retrieval, hybrid RRF fusion, cross-encoder reranking. Can be developed independently of the harmonization pipeline. The GEO database itself (P2 infrastructure) is needed regardless of whether search enters the first paper — it provides the corpus metadata for benchmark construction and future work. *Replaces: nothing (new subsystem). Effort: large. Risk: medium.*

→ See Report B, lines 148-174 for the full HPC infrastructure layout for the search pipeline.

**10. multi_agent.py [P3 — design interface now, implement later].** Hierarchical multi-agent orchestration for N-table harmonization: supervisor agent delegates to parallel harmonization agents (one per table), then a merge agent checks cross-table consistency. Uses LangGraph's `Send()` API for fan-out. The agent-as-tool-factory pattern from SRAgent (Report C, lines 96-115) provides the concrete implementation: each sub-agent is wrapped as a callable tool via `@tool` decorator, enabling standalone testing of each sub-agent before composition. Interface defined now so P1/P2 single-agent work feeds cleanly into P3 multi-agent experiments. *Replaces: nothing. Effort: large. Risk: medium.*

**11. inference.py [P2].** vLLM and SGLang configuration for HPC deployment. This component encapsulates the deployment-critical specifications that are the highest-probability blocker for local model experiments.

→ See Section 2.6 (Inference Backend Deployment) for the full vLLM deployment specification.

### 2.4 Component Interfaces and Data Contracts

The architecture defines four critical interface boundaries. Strict typing via Python dataclasses ensures components can be developed and tested independently.

**Benchmark → Evaluation interface:**

```python
@dataclass
class BenchmarkTask:
    """A single evaluation task in Gene Expression Omnibench."""
    task_id: str                          # e.g., "L1_GSE12345_gdc"
    level: int                            # 1-5 (single-table to end-to-end)
    source_table: pd.DataFrame            # Raw GEO metadata table
    target_schema: dict                   # GDC schema subset (relevant nodes)
    gold_schema_mapping: dict[str, str]   # source_col → GDC_property
    gold_value_mapping: dict[str, dict]   # col → {source_val → GDC_val} (Level 2+)
    metadata: dict                        # GSE ID, organism, platform, cancer type
    difficulty_tags: list[str]            # e.g., ["free_text_heavy", "ambiguous_columns"]
```

**Search → Harmonization interface (the handoff contract):**

```python
@dataclass
class SearchResult:
    """Output of the search pipeline, input to harmonization."""
    query: str
    gse_ids: list[str]
    metadata: dict[str, GEOSeriesMetadata]  # Per-GSE structured metadata
    relevance_scores: dict[str, float]       # Per-GSE calibrated relevance
    match_evidence: dict[str, list[str]]     # Per-GSE: which query terms matched
    search_trace: dict                       # Full trace for observability
```

**Harmonization → Evaluation interface:**

```python
@dataclass
class HarmonizationResult:
    """Output of any harmonization agent/pipeline."""
    task_id: str
    agent_type: str                        # "react_bdikit", "codeact", "coding_agent",
                                           # "compositional", "multi_agent"
    schema_mapping: dict[str, str]         # source_col → GDC_property
    value_mapping: dict[str, dict[str, str]]  # col → {source_val → GDC_val}
    confidence_scores: dict[str, float]    # Per-mapping confidence
    harmonized_table: pd.DataFrame | None  # Final harmonized data (optional)
    mapping_code: str | None               # Deterministic Python code (materialize)
    metrics: HarmonizationMetrics          # Auto-evaluated quality
    trace: dict                            # Full trace for observability
    cost_usd: float                        # Total API cost for this run
    wall_time_seconds: float               # End-to-end wall time
    failure_modes: list[str]               # Detected failure taxonomy classes
```

**Experiment → Statistical Comparison interface:**

```python
@dataclass
class ExperimentSuite:
    """A collection of runs across configurations for statistical comparison."""
    benchmark_tasks: list[BenchmarkTask]
    configurations: list[dict]             # Model × architecture × prompt combos
    results: dict[str, list[HarmonizationResult]]  # config_id → [runs]
    
    def compare_pairwise(self, config_a: str, config_b: str) -> PairwiseComparison:
        """McNemar's test + Cliff's δ + bootstrap CIs."""
        ...
    
    def compare_all(self) -> MultiComparison:
        """Friedman + Nemenyi post-hoc with Holm-Bonferroni correction."""
        ...
    
    def pareto_frontier(self, x='cost_usd', y='f1_score') -> list[str]:
        """Identify Pareto-optimal configurations."""
        ...
```

These contracts ensure that any agent implementation — whether ReAct, CodeAct, frontier coding agent, Matchmaker pipeline, or future multi-agent — produces outputs in the same format, enabling apples-to-apples comparison. The `agent_type` field enables architecture-specific analysis without requiring architecture-specific evaluation code.

### 2.5 What Should Not Change

Six components of the current architecture are battle-tested and should be preserved:

**Phoenix/OTel tracing.** The existing span hierarchy (AGENT → CHAIN → LLM → TOOL) with OpenInference semantic conventions works. Extend for multi-agent traces by propagating Trace IDs across agent boundaries and adding descriptive span naming (`schema_matcher:gdc_column_match` rather than generic `tool_call`). The 20-class failure taxonomy maps to span events with structured attributes (`failure.taxonomy_class`, `failure.agent_id`, `failure.recovery_attempted`).

**YAML experiment configs.** These enable reproducible experiments and are the natural format for sweep definitions. Extend to support quantization level, model-per-phase configuration, and prompt version references. Each experiment run should produce an immutable config snapshot alongside results.

**Plotly Dash dashboard.** The 8-tab structure provides the experiment analysis infrastructure needed. Extend with: a search pipeline tab (for R1-R3 evaluation), a statistical comparison tab (for comparison.py output visualization), and multi-agent trace views (for P3 experiments). Do not replace with a different framework.

**Apptainer sandboxing.** This is a hard requirement for HPC environments. The existing `.sif` image with Python 3.11, litellm, and BDI-Kit 0.9.0 works. Add a separate sandbox definition for frontier coding agent testing (`coding_agent_sandbox.sh`) that includes Claude CLI / Codex CLI and outbound HTTPS access.

**The two primary agent paradigms (ReAct + BDI-Kit tools, and CodeAct).** These are core experimental conditions, not implementation details. Both must be preserved as-is so the v2 experiments can be directly compared with existing results. New paradigms (coding agent, compositional) are additive.

**The evaluation pipeline.** `calculate_all_metrics()` is solid. Extend for value mapping metrics (exact match for enums, Wu-Palmer semantic similarity via NCIt for partial credit, BLEU/CER for string fields) and cross-table consistency scores (percentage of semantically equivalent source columns receiving identical target mappings). Do not rewrite — build on the existing Pydantic schemas (metrics.json v1.1).

### 2.6 Inference Backend Deployment

This section provides the implementation-critical deployment specifications that are the highest-probability blocker for local model experiments on HPC.

**vLLM on SLURM with Apptainer.** Known Apptainer quirks require `--containall` and explicit bind mounts since vLLM's container assumes root Docker execution (Report D, line 15). Minimal SLURM job script:

```bash
#!/bin/bash
#SBATCH --gres=gpu:1 --mem=48G --time=8:00:00
apptainer exec --nv --containall \
  --bind /path/to/models:/models:ro \
  --bind /path/to/cache:/root/.cache \
  vllm_v0.18.sif \
  python -m vllm.entrypoints.openai.api_server \
    --model /models/Qwen3.5-35B-A3B-AWQ \
    --quantization awq \
    --tensor-parallel-size 1 \
    --tool-call-parser qwen3_coder \
    --max-model-len 32768 \
    --port 8000
```

Key flags: `--containall` prevents host environment leakage; `--bind` provides explicit model and cache access; `--tool-call-parser qwen3_coder` enables native Qwen 3.5 tool calling; `--tensor-parallel-size` controls multi-GPU distribution.

**SGLang comparison.** Deploy SGLang on a subset of experiments (especially Qwen 3.5 models where MTP speculative decoding support may provide throughput advantages). Both expose OpenAI-compatible APIs, so migration requires only changing the endpoint URL in litellm configuration.

**GPU-specific deployment matrix** (from Report D, lines 70-79):

| GPU | Best Model | Quantization | VRAM Used | Notes |
|-----|-----------|-------------|-----------|-------|
| A100-80GB | Qwen3.5-122B-A10B | FP8 | ~70GB | Best open-weight function calling |
| A100-40GB | Qwen3.5-35B-A3B | FP8 | ~20-25GB | Room for large context |
| A40/RTX6000 48GB | Qwen3.5-35B-A3B or Gemma 4 31B | FP8/FP16 | ~20-22GB | Test both |
| RTX 4090 24GB | Gemma 4 26B-A4B or Qwen3.5-35B-A3B | Q4_K_M | ~15-18GB | MoE models fit |
| Any ≥12GB | Qwen3.5-9B | Q8 | ~10GB | Best Tier 3 option |

**Quantization format selection.** Use AWQ format with vLLM's Marlin kernels for GPU deployment (AWQ achieves 51.8% Pass@1 vs. GPTQ's 46.3% on HumanEval, with 741 vs. 712 tokens/sec; Report D, line 103). Minimum Q5_K_M for structured output tasks. Always pair with constrained decoding (vLLM structured output mode) to guarantee JSON validity regardless of quantization level.

→ See Report D, lines 11-34 for the full inference framework comparison table.

### 2.7 Observability and Prompt Management Stack

The recommended three-layer observability stack for HPC (Report C, lines 283-286):

**Layer 1 — OpenLLMetry instrumentors** (Traceloop, Apache 2.0): A pure instrumentation library generating OpenInference-compliant traces. Framework-agnostic — works with LangChain, LlamaIndex, DSPy, OpenAI, and Anthropic. Not a platform but a connector layer providing backend flexibility.

**Layer 2 — Self-hosted Phoenix** (Arize, 7,800+ GitHub stars, Elastic License 2.0): OTLP backend for trace visualization and analysis. Fully self-hostable with no feature gates, runs as a single container, includes built-in LLM-based evaluation. The strongest choice for HPC environments with no cloud dependencies. Managed by existing `scripts/ensure_phoenix_server.py`.

**Layer 3 — Langfuse** (MIT license, 19,000+ GitHub stars): Handles prompt versioning with experiment-specific labels (e.g., "codeact-v2.1-dou2020", "react-v1.0-cptac"). Auto-assigned version IDs, custom labels, protected labels, prompt diffs, and environment bindings (dev → "latest", prod → "v1.2.0"). SDK v3 is a thin OTel wrapper.

**Platform comparison rationale:** LangSmith requires Enterprise tier for self-hosting and charges per-trace — problematic for 100+ model experiments generating millions of traces. W&B Weave extends mature ML tracking but adds ecosystem lock-in. Phoenix + Langfuse combination provides the best HPC-compatible stack with zero cloud dependencies.

→ See Report C, lines 261-286 for the full platform comparison including LangSmith, W&B Weave, and OpenLLMetry.
→ See Report C, lines 275-281 for the OTel span hierarchy specification (agent.execute → agent.llm_step → agent.tool.{name}).

### 2.8 Four-Layer Reproducibility Strategy

Practical reproducibility demands defense in depth — four complementary mechanisms where each layer compensates for weaknesses of the others (Report C, lines 291-311). The evidence motivating this strategy: temperature=0 is not deterministic (floating-point non-associativity, MoE routing variation), and 0/18 papers from ICSE/ASE 2024 with LLM artifacts could be fully reproduced (Report C, lines 291-296).

**Layer 1 — Exact-match LLM call caching.** Hash full prompt string (SHA-256) + model ID + generation parameters (temperature, top_p, max_tokens) as cache key. Store first successful response in SQLite. Serve cached responses for identical subsequent requests. Implemented in `caching.py`. Integrates with Phoenix tracing so cached calls are marked.

**Layer 2 — Configuration snapshots.** Capture model name/version, temperature, top_p, seed (if available), system prompt text, tool definitions, API version, `system_fingerprint` (OpenAI), prompt template version hash, and litellm model string for every run. Extend existing `config_snapshot.yaml`.

**Layer 3 — Prompt versioning.** Semantic versioning (major.minor.patch) for all prompts: major bumps for model or output schema changes, minor for new features, patch for typo fixes. Langfuse provides built-in versioning with environment bindings. Each experiment run records the exact prompt version used.

**Layer 4 — Materialized intermediate outputs.** Save the output of every pipeline stage (candidate retrieval results, refinement scores, final mappings) as versioned artifacts keyed by composite hash: `(prompt_version + input_hash + model_params)`. This enables restarting from any checkpoint, comparing intermediate results across experiments, and diagnosing exactly where two experiment runs diverge.

**The materialize-mapping pattern** (Report C, lines 309-311) provides an additional reproducibility asset: BDI-Kit's `materialize_mapping` tool produces a deterministic Python script that applies the discovered mapping without any LLM calls, cleanly separating the LLM-assisted discovery phase from the deterministic execution phase. Every experiment should produce both the mapping decisions and the materialized script as paired artifacts.

### 2.9 Search Pipeline HPC Infrastructure

The search pipeline requires specific HPC resource allocation beyond the harmonization compute (Report B, lines 148-174):

```
Search Pipeline HPC Architecture:
├── CPU Node: Qdrant (Apptainer, 4-8GB RAM, NVMe SSD, port 6333)
│   └── Deploy: apptainer pull qdrant.sif docker://qdrant/qdrant:latest-unprivileged
│   └── HNSW tuning: m=16, ef_construction=128
│   └── Native hybrid search: BM25 + dense via prefetch API
├── GPU Node (weekly): Batch embedding job (~2 min for 250K docs)
│   └── bge-base or BMRETRIEVER-410M, batch_size=32
└── GPU Node (persistent): Query service (A100 40GB)
    ├── Qwen2.5-14B-Q4 for query expansion (~8GB VRAM)
    ├── bge-reranker-v2-m3 for reranking (~2GB VRAM)
    └── Total query-time: ~20-28GB VRAM
```

Qdrant's native hybrid search (since v1.15.2) supports BM25 with server-side IDF computation alongside dense vectors, eliminating the need for a separate search engine. Its `prefetch` API enables multi-stage retrieval (sparse → dense → reranking) within a single query call. Metadata filtering is applied during HNSW traversal for efficient pre-filtering on GEO's structured fields (organism, platform, experiment type, date ranges). Incremental updates via upsert handle weekly GEO syncs without full index rebuilds.

**Framework choice:** LlamaIndex is recommended for the orchestration layer (native `QdrantVectorStore` with `enable_hybrid=True`, ~1.6K tokens/query vs. LangChain's ~2.4K). For HPC, a lightweight custom pipeline with direct Qdrant client + sentence-transformers may be simpler than any framework.

→ See Report B, lines 148-174 for the full infrastructure specification including Qdrant Apptainer deployment and GPU budget.

---

## DELIVERABLE 3: RESEARCH ROADMAP BEYOND SIX MONTHS

### 3.1 Publication 2: Search Pipeline and End-to-End Evaluation (Months 7-12)

**Research question.** Can a GEO-specific RAG pipeline surface 80%+ of relevant studies for a given omics-data search query, and does the combination of search + harmonization produce usable harmonized datasets from open-ended biological queries?

**Experiments.** This publication picks up P2 search experiments (R1-R3, already started) and adds the deferred P3 experiments: R4 (LLM reranking — cross-encoder on top-100 candidates), R5 (paper full-text embedding and retrieval, with section-aware chunking at 100-200 tokens for Methods/Results), R6 (agentic multi-step search with Adaptive RAG routing for query complexity), and E1 (end-to-end search→harmonize pipeline on gold-standard queries from B4, expanded to 30-50 queries). The search evaluation framework uses Recall@K as the primary metric (Recall@100 ≥ 0.80 minimum, ≥ 0.85 target), with NDCG@10 for ranking quality and cascaded evaluation decomposing end-to-end success as P(search finds study) × P(study is processable) × P(harmonization succeeds) × P(data is usable).

**Additional experiments for Publication 2:**

**LightRAG knowledge graph evaluation.** Evaluate LightRAG (Guo et al., EMNLP 2025) for graph-based retrieval over GEO's structured metadata fields (organism, platform, technique, disease). LightRAG's dual-level retrieval (low-level entity queries + high-level thematic queries) and incremental update support via union operations map directly to GEO's hierarchical metadata structure and weekly sync of ~500-1000 new records. Compare against pure vector retrieval to quantify the value of explicit relational structure. Pre-build a structured knowledge graph from GEO's existing fields without LLM extraction for structured data, reserving LLM extraction for free-text summaries.

→ See Report B, lines 136-140 for the full LightRAG vs. GraphRAG analysis.

**Synthetic query generation for retriever fine-tuning.** Generate synthetic queries from GEO series summaries using an LLM to create a large-scale training set for retriever fine-tuning. This addresses the cold-start problem for the search pipeline, where 30-50 manual queries (B4) are insufficient for supervised retriever training. This is the bridge between zero-shot search and trained retrieval.

**CRAG retrieval evaluation + DeepEval CI/CD quality gates.** Implement CRAG-style retrieval evaluation (Yan et al., 2024; 26.7pp improvement over vanilla RAG) as a runtime quality layer that classifies retrieved documents as Correct/Incorrect/Ambiguous and triggers query reformulation when quality is low. Set up CI/CD evaluation with DeepEval quality gates, mapping its five RAG metrics to specific pipeline components: contextual recall evaluates the embedding model, contextual precision evaluates the reranker, contextual relevancy evaluates chunk size.

→ See Report B, lines 130-144 for the full agentic RAG patterns analysis (Adaptive RAG, CRAG, HalluGraph).

**Infrastructure.** The GEO database (SQLite + FTS5, started as background task in Month 1) should be complete by Month 7. Qdrant deployed via Apptainer. Embedding models from S2 results inform the choice between MedCPT, BMRETRIEVER-410M, and BGE-large. Ontology-guided query expansion using UMLS/MeSH/DOID following the BMQExpander approach (up to 22% NDCG improvement reported). Paper full-text integration via GROBID parsing of PMC articles citing GEO accessions (~47,000 articles available).

**Estimated effort.** 4-6 months for one researcher. The search pipeline is a largely independent subsystem — development can overlap with Publication 1 revisions. The main bottleneck is gold-standard query construction (B4 expansion) and paper full-text downloading/parsing.

**Expected outcome.** Hybrid BM25 + dense retrieval with ontology expansion will achieve Recall@100 of 0.80-0.90 (based on Report B estimates), a 15-30% improvement over keyword search alone. Paper full-text integration will add another 5-10% recall for queries whose answers are implicit in methodology descriptions. The end-to-end pipeline will successfully harmonize 60-70% of retrieved studies, with the remainder failing due to metadata quality issues.

**The GEO long-tail problem** (Report B, lines 213-214) remains genuinely unsolved: rare diseases, unusual organisms, and novel experimental techniques where neither keyword matching nor semantic similarity has sufficient training signal. Active learning from harmonization outcomes and community-contributed relevance judgments are the most promising paths forward, but neither has been validated at GEO scale. This should be framed as an explicit open research question.

**Target venue.** Bioinformatics (Oxford), Nucleic Acids Research (database issue), or CIKM 2027. A systems paper emphasizing the search pipeline architecture with end-to-end evaluation results.

### 3.2 Publication 3: Multi-Agent and N-Table Harmonization (Months 12-18)

**Research question.** How should harmonization scale to multi-table datasets (5-10 tables from the same study collection), and do multi-agent architectures justify their coordination overhead compared to sequential single-agent processing?

**Experiments.** This publication centers on the P3 experiments: B3 (N-table gold standard from CPTAC 10-table set with Li 2023 ground truth), M2 (N-table harmonization with best single-table configuration), M3 (multi-agent vs. single-agent for N-table — fan-out parallel processing via LangGraph `Send()`, hierarchical supervisor pattern, and sequential single-agent as control), P2opt (full DSPy optimization with MIPROv2 and GEPA optimizers, enabled by the larger training set from Publications 1-2 combined), and V2 (constrained generation for value mapping using llama.cpp GBNF grammars or vLLM structured output).

**Additional architectures to evaluate:**

**Chain-of-Agents** (Zhang et al., Google Research, NeurIPS 2024) as a distinct alternative to fan-out: sequential worker agents each process a chunk and pass condensed summaries to the next worker, outperforming both full-context and RAG approaches on all 8 datasets tested with improvements up to 10%. This is a complementary approach to RLM for handling large inputs and provides a concrete fallback if LangGraph fan-out proves brittle.

**Asymmetric Actor-Critic** (arXiv:2604.00304) as a distinct architecture beyond HITL: a frontier LLM generates mappings while a cheaper critic model validates against GDC vocabulary constraints. CellAtria (Nouri et al., npj AI 2026) implements this pattern for scRNA-seq. This is architecturally distinct from simple post-hoc validation (A2) because the critic's feedback informs the generator's next attempt.

→ See Report C, lines 245-257 for Chain-of-Agents and its application to GDC's 736-column schema.
→ See Report C, lines 139-143 for the Critic/Verifier pattern.

**RLM pattern** for processing datasets that exceed practical context limits: load source data and GDC schema as Python variables, partition columns into semantic groups via code, process each group with recursive sub-LM calls (Zhang et al., arXiv:2512.24601 demonstrated 34+ accuracy point improvements on OOLONG benchmark). Cross-table consistency verification as a post-processing pass. Human-in-the-loop interface implementing Matchmaker's entropy-based deferral and Magentic-UI's co-planning pattern.

**For multi-agent context management:** Observation masking (JetBrains, NeurIPS 2025) selectively hides irrelevant information from sub-agents, reducing context pollution in multi-step workflows. This addresses the documented failure mode of context accumulation in multi-agent systems.

→ See Report C, lines 173-183 for conditions when multi-agent does earn its overhead.

**The key empirical question is whether multi-agent orchestration adds value.** The evidence from Report C is cautionary: multi-agent systems fail 41-86.7% of the time across frameworks (Cemri et al., NeurIPS 2025), and sequential reasoning tasks degrade 39-70% under multi-agent coordination (Google DeepMind, Kim et al., 2026). However, N-table harmonization is genuinely parallelizable — each table's harmonization is independent — fitting the one scenario where multi-agent consistently helps. The hypothesis is that fan-out parallel processing with a lightweight merge/consistency check will outperform sequential processing (in wall time) while maintaining or improving accuracy (through cross-table consistency enforcement).

**Estimated effort.** 6-8 months for 1-2 researchers. Multi-agent implementation is the highest-risk component — if LangGraph orchestration proves brittle, the publication can focus on N-table results with sequential processing and RLM decomposition, positioning the multi-agent comparison as a negative result.

**Target venue.** SIGMOD 2028 (industry track, for the system design contribution), Journal of Biomedical Informatics (for the clinical application angle), or a second VLDB EA&B submission with the expanded benchmark.

### 3.3 P-Extra: Aspirational Future Work

These ideas are fully specified for immediate pickup when capacity allows. Each connects to the overall research narrative: Publication 1 asks "which approaches work?", Publication 2 asks "can we find AND harmonize?", Publication 3 asks "can we scale?", and P-Extra asks "can this change how labs actually work?"

**Production deployment study (Est. 6-12 months, requires collaboration).** Deploy the best-performing pipeline for a lab's actual research workflow — e.g., a cancer genomics group wanting to harmonize 50 GEO datasets for a meta-analysis. Measure time savings vs. manual curation (baseline: ~2-4 hours per dataset for experienced curators per Long et al. 2025), error rates on real queries (not benchmark tasks), user satisfaction via structured interviews, and the distribution of failure modes in production vs. benchmark settings. This is the ultimate validation: does the system actually save time and produce usable data? Requires collaboration with a wet-lab or clinical bioinformatics group.

**Cross-schema generalization (Est. 3-4 months).** Test whether models and pipelines trained/optimized for GDC generalize to other target schemas: ENCODE metadata standards, cBioPortal's data model, the Observational Medical Outcomes Partnership (OMOP) CDM (enabling direct comparison with Matchmaker's published MIMIC-OMOP results), and the Clinical Data Interchange Standards Consortium (CDISC) SDTM. If generalization holds, this transforms Gene Expression Omnibench from a GDC-specific tool to a universal harmonization benchmark.

**Fine-tuning domain-specific SLM (Est. 2-3 months).** Following Magneto's self-supervised approach, fine-tune a small language model (MPNet or BGE-base) specifically for GEO→GDC retrieval using LLM-generated synthetic training data. Magneto demonstrated that SLM fine-tuning improved GDC MRR from 0.551 to 0.860 — the same approach applied to GEO's free-text metadata could address the domain gap identified by "Toward Total Recall" (GEO recall 44% vs. BioSample 82%).

**Active learning from harmonization outcomes (Est. 3-4 months).** Build a feedback loop from harmonization success/failure back to search ranking. GSEs successfully harmonized into usable data become positive training signals; GSEs that score high in search but fail processing become hard negatives for retriever fine-tuning. Train a processability model on (GSE metadata → harmonization success) using historical outcomes and blend into ranking: `0.7 × relevance_score + 0.3 × processability_score`. OpenRAG and DRO demonstrate that joint retriever-downstream optimization yields 5-15% improvement over independent training.

**Community benchmark platform (Est. 2-3 months).** Build a public leaderboard on HuggingFace Spaces with automatic evaluation — researchers upload their system's predictions in a standardized format, and the platform computes all metrics, statistical comparisons, and cost-quality Pareto positions. Similar to MTEB but for metadata harmonization. This extends Gene Expression Omnibench's impact beyond the initial publications and creates a living benchmark that tracks progress as new models and methods emerge.

**Multi-modal harmonization (Est. 6-12 months, requires domain expansion).** Extend the benchmark and pipeline to cover proteomics (PRIDE repository, UniProt vocabulary), metabolomics (MetaboLights, ChEBI ontology), and clinical genomics (dbGaP, controlled-access). Each modality introduces different vocabulary conventions and metadata structures. The architecture (search → harmonize → evaluate) generalizes, but the gold standards and domain-specific context engineering do not.

---

## Gap Analysis and Open Questions

**The benchmark size vs. statistical power tradeoff.** The plan targets 200+ ground-truth column matches across 10+ tables, which provides adequate power (McNemar's test, power=0.80, α=0.05) to detect F1 differences of 0.10 between systems. However, to detect smaller differences (0.05) — which is the relevant granularity when comparing systems in the 70-80% accuracy range — would require 400-800 test instances (Report A, line 115). The fallback of ≥4 tables with ≥100 matches is borderline. This tension between annotation cost and statistical resolution is the single largest practical constraint on the benchmark's usefulness.

**The DSPy cold-start problem.** DSPy's BootstrapFewShot optimizer requires successful traces to bootstrap from, but the first runs on a new benchmark have no prior successes. Matchmaker addressed this by bootstrapping from the model's own successful zero-shot attempts, but this works only if zero-shot accuracy is sufficient to generate enough positive examples. If zero-shot performance on GEO metadata is poor (plausible given the 38-point GEO-BioSample gap), the bootstrapping loop may not converge. Fallback: use a small set of manually crafted demonstrations (5-10) as the initial seed. GEPA requires only 14 labeled examples at $2-3 cost (Report D, line 247), making it a viable alternative once the benchmark reaches 20+ tables.

**Value mapping evaluation methodology.** Schema matching (column → column) has well-established metrics (F1, MRR, Recall@K). Value mapping (free-text → controlled vocabulary) lacks standardized evaluation. The proposed three-tier scoring (exact match for enums, partial credit via Wu-Palmer similarity in NCIt, zero for unrelated) is reasonable but introduces subjectivity in the partial credit weight. The GDC's 200+ enumerated properties with case-sensitive permissible values provide ground truth for constrained fields, but free-text fields (e.g., treatment descriptions) have no single correct standardization. No standardized benchmark evaluates instance-level value mapping to controlled vocabularies (Report A, line 67). This is a fundamental measurement challenge the benchmark must address transparently.

**Reproducibility of frontier coding agent experiments.** Claude Code and Codex CLI are commercial products that may change behavior between API versions. The four-layer reproducibility strategy (Section 2.8) helps, but cached results are specific to a model version that may be deprecated. Best practice: report the exact model version string, API access date, and `system_fingerprint` (OpenAI) for every run. Acknowledge that exact reproduction may not be possible and report variance across 3-5 runs as the measure of stability.

**The simplicity of the Dou 2020 benchmark.** The primary existing test case (Dou 2020: 17 columns, 190 rows) is at the simpler end of the complexity spectrum. It is plausible that all agent architectures perform well on it, producing a ceiling effect that obscures meaningful differences. The solution is to include both easy and hard tasks in the benchmark — some tables with clear lexical matches and some requiring deep domain knowledge (e.g., mapping free-text treatment descriptions to GDC's treatment ontology codes). The difficulty distribution should be deliberately skewed toward hard cases, since easy cases provide less discriminative information.

**Model roster volatility.** The model landscape changes faster than a 6-month research plan can track. Gemma 4 was released April 2, 2026 — one day before this plan was written. By Month 4, new models (Llama 4.1, Qwen 4, Claude 5) may be available. The architecture must support easy model addition via litellm's provider system. The paper should frame model-specific results as "representative of the frontier/local quality at time of evaluation" rather than definitive rankings.

**The search pipeline scope decision.** Whether the search pipeline (R1-R3) belongs in Publication 1 or 2 is a genuine strategic question. Including it makes the paper more comprehensive but risks diluting the schema matching contribution. Excluding it focuses the paper but leaves the "end-to-end" claim unsupported. The go/no-go at end of Month 3 resolves this: if search results are strong, include them; if the pipeline is incomplete or results are preliminary, defer to Publication 2 and frame Publication 1 as "harmonization-focused with search as future work."

**The Matchmaker reimplementation challenge.** No code is published. Algorithm 2 and Appendix C prompts provide sufficient architectural detail, but implementation choices (ColBERTv2 indexing parameters, candidate set sizes, MCQ prompt formatting) affect performance. The reimplementation may not exactly replicate published numbers. This is mitigated by (a) evaluating on the omics benchmark rather than claiming parity on MIMIC-OMOP, and (b) reporting the reimplementation as "Matchmaker-inspired compositional pipeline" rather than "Matchmaker." If performance is substantially lower than reported, investigate and document the discrepancy as a reproducibility finding.

**GEO long-tail retrieval.** Rare diseases, unusual organisms, and novel experimental techniques have insufficient training signal for either keyword or semantic retrieval. Active learning and community-contributed relevance judgments are promising but unvalidated at GEO scale (Report B, lines 213-214).

**Cross-model behavioral differences.** Different LLMs exhibit qualitatively different failure modes on harmonization tasks. A systematic per-model failure mode analysis would inform both model selection and architecture design, and is an analytical deliverable that emerges from E2 data (Report C, line 426).

---

## Further Reading

**Schema Matching and Harmonization**
- Seedat N, van der Schaar M. "Matchmaker: Self-Improving LLM Programs for Schema Matching." NeurIPS 2024 GenAI for Health Workshop. arXiv:2410.24105. *acc@1=62.20%, O(n) cost, compositional pipeline, DSPy optimization. No public code.*
- Liu Y et al. "Magneto: Combining Small and Large Language Models for Schema Matching." PVLDB 18, 2025. arXiv:2412.08194. *MRR=0.860 (fine-tuned), GDC-SM benchmark. GitHub: VIDA-NYU/magneto-matcher.*
- Gungor E et al. "SCHEMORA: Schema Matching via Multi-stage Recommendation and Metadata Enrichment." arXiv:2507.14376, July 2025. *HitRate@5=80.39% on MIMIC-OMOP. GitHub: ermangungor/schemora.*
- Lopez R et al. "BDI-Kit: An AI-powered toolkit for biomedical data harmonization." Patterns (Cell Press), February 2026. *The toolkit this project extends.*
- Santos A et al. "Interactive Data Harmonization with LLM Agents." arXiv:2502.07132, 2025. *Harmonia agent architecture; calls for benchmarks.*
- Wang S et al. "LLMatch: A Unified Schema Matching Framework with LLMs." APWeb-WAIM 2025. arXiv:2507.10897. *F1=0.30-0.85 on MIMIC-OMOP, Rollup/Drilldown, SchemaNet. GitHub: knowledge-fusion/LLMatch.*
- Chen Z et al. "ConStruM: Constructive and Structural Schema Matching." January 2026. *0.935 vs. 0.503 on HRS-B with structured context.*
- Koutras C et al. "Valentine: Evaluating Matching Techniques for Dataset Discovery." IEEE ICDE, 2021. *Classical baselines. COMA F1=0.04 on MIMIC-OMOP.*

**Agent Architectures and Design**
- Wang X et al. "Executable Code Actions Elicit Better LLM Agents." ICML 2024. arXiv:2402.01030. *CodeAct: up to 20% higher success rates.*
- Cemri M et al. "Why Do Multi-Agent LLM Systems Fail?" NeurIPS 2025 Datasets Track. arXiv:2503.13657. *1,600+ traces, 14 failure modes, 41-87% failure rates.*
- Kim J et al. "Towards a Science of Scaling Agent Systems." Google DeepMind, January 2026. *180-configuration study: 39-70% sequential reasoning degradation.*
- Kapoor S et al. "AI Agents That Matter." TMLR, 2024. arXiv:2407.01502. *Cost-accuracy Pareto methodology.*
- Zhang E, Kraska T, Khattab O. "Recursive Language Models." MIT CSAIL, December 2025. arXiv:2512.24601. *34+ accuracy point improvement on OOLONG.*
- Zhang Z et al. "Chain-of-Agents." Google Research, NeurIPS 2024. *Up to 10% improvement over full-context and RAG.*

**Omics Metadata and GEO Curation**
- Sundaram S, Gonçalves RS, Musen MA. "Toward Total Recall in Metadata Harmonization." GigaScience, 2025. *GEO recall 44% vs. BioSample 82%; 3-factor causal analysis.*
- Verbitsky A, Boutet P, Eslami M. "Metadata harmonization from biological datasets with language models." Bioinformatics Advances 5(1), 2025. *96% in-dict, 17% OOD accuracy, $29 cost.*
- Long K et al. "Large-scale Manual Curation and Harmonization of Metadata." bioRxiv, November 2025. *212,027 samples, 468 studies; pervasive quality issues.*
- Lim N et al. "Curation of over 10,000 transcriptomic studies to enable data reuse." Database, 2021. *Gemma: 10,811 datasets, 10,215 ontology terms.*
- Adams T et al. "ADHTEB: A benchmark of text embedding models for semantic harmonization." J Prev Alzheimers Dis, January 2026. *MTEB rankings don't predict domain-specific performance.*
- Kaier T et al. "Multi-repository LLM evaluation." BMC Research Notes, 2026. *GPT-4.1/Gemini/Claude on GEO/ENA/PRIDE/SRA.*

**Experimental Methodology**
- Khattab O et al. "DSPy: Compiling Declarative Language Model Calls into Self-Improving Pipelines." ICLR 2024. *BootstrapFewShot, MIPROv2, GEPA optimizers.*
- Demšar J. "Statistical Comparisons of Classifiers over Multiple Data Sets." JMLR 7, 2006. *McNemar, Friedman, Nemenyi, Bonferroni.*
- Weber LM et al. "Essential guidelines for computational method benchmarking." Genome Biology, 2019. *Bioinformatics benchmark standards.*

**Observability and Reproducibility**
- OpenInference Specification. AI-specific OTel semantic conventions. arize-ai.github.io/openinference.
- Hirn S et al. "A Reproducible Tutorial on Reproducibility in Database Systems Research." PVLDB 17, 2024. *VLDB three-badge system.*

**RAG and Search**
- Grigoriadis D et al. "Public Omics Explorer (POE)." Comp Struct Biotech J 27:4802-4812, 2025. *SBioBERT + FAISS over 250K+ GEO records.*
- Al Nazi Z et al. "BMQExpander: Ontology-Guided Query Expansion for Biomedical Retrieval." arXiv:2508.11784, 2025. *22% NDCG improvement.*
- Santhanam K et al. "ColBERTv2: Effective and Efficient Retrieval via Lightweight Late Interaction." NAACL, 2022.
- Guo Z et al. "LightRAG: Simple and Fast Retrieval-Augmented Generation." EMNLP, 2025. *Dual-level retrieval with incremental updates.*
- Yan S et al. "Corrective Retrieval Augmented Generation." arXiv:2401.15884, 2024. *26.7pp improvement over vanilla RAG.*

**Inference and Deployment**
- vLLM Team. "vLLM: Easy, Fast, and Cheap LLM Serving with PagedAttention." 2023+. *Primary inference framework for HPC.*
- Zheng L et al. "SGLang: Efficient Execution of Structured Language Model Programs." 2024+. *RadixAttention, up to 6.4× throughput.*

**Agent Evaluation and Meta-Optimization**
- Harbor Framework Team. "Harbor: A framework for evaluating and optimizing agents and models in container environments." 2026. GitHub: harbor-framework/harbor. *17+ built-in agents (Claude Code, Codex, OpenCode), 50+ benchmark adapters, ATIF trajectory format. Used for S6/S6b experiments.*
- AutoAgent (ThirdLayer). "AutoAgent: Autonomous agent engineering via meta-agent optimization." 2025. GitHub: kevinrgu/autoagent. *Meta-agent hill-climbing loop: coding agent iteratively improves agent harness by running benchmarks, diagnosing failures, editing code. Built on Harbor.*
- Kapoor S et al. "AI Agents That Matter." TMLR, 2024. arXiv:2407.01502. *Cost-accuracy Pareto methodology; demonstrates simple retry strategies can match complex agents.*
