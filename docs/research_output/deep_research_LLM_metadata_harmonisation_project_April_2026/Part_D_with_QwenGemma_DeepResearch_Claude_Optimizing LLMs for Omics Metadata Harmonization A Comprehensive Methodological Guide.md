# Optimizing LLMs for Omics Metadata Harmonization: A Comprehensive Methodological Guide

## v2 — Updated April 3, 2026: Incorporates Gemma 4 (released April 2, 2026) and Qwen 3.5 (released Feb 16 – Mar 1, 2026)

---

**The single most important finding across all eight research dimensions is that pipeline architecture dominates model choice.** Matchmaker demonstrated GPT-3.5 with a well-designed compositional pipeline outperforms GPT-4 with a simple pipeline on healthcare schema matching — directly applicable to GDC harmonization. This means the highest-ROI investment is agent architecture design, not chasing frontier models. For local deployment, **vLLM on SLURM/Apptainer with Qwen3.5-35B-A3B at Q5_K_M quantization** represents the current Pareto-optimal configuration for structured biomedical metadata tasks, achieving near-frontier quality at negligible marginal cost — and the just-released **Gemma 4 26B-A4B** should be evaluated as a direct competitor given its exceptional agentic tool-use benchmarks. A rigorous benchmark paper combining cost-quality Pareto analysis with quantization impact measurement would fill a genuine gap — no published work systematically evaluates quantization effects on schema matching accuracy — and targets VLDB 2027's Experiments, Analyses & Benchmarks track or NeurIPS 2026's renamed Evaluations & Datasets track.

---

## 1. Inference Frameworks: vLLM Leads, but SGLang May Overtake It for Agent Workloads

Five frameworks were evaluated for SLURM + Apptainer + NVIDIA GPU deployment. The field has consolidated around two serious contenders, with one framework entering maintenance mode and two others useful only for development.

**vLLM (v0.18.1, March 2026)** is the safest production choice. It has published academic work specifically on SLURM+Apptainer deployment (MIND '25, RWTH Aachen), a native litellm provider (`hosted_vllm/`), and the most mature HPC documentation across multiple centers (C3SE Chalmers, MeluXina, NYU). PagedAttention eliminates 60–80% of KV cache memory waste, enabling ~128 concurrent sequences on 24GB VRAM where standard implementations manage ~32. Under concurrent load, vLLM delivers 35× higher request throughput than llama.cpp (Red Hat H200 benchmark). Structured output is supported via xgrammar/outlines backends, and tensor parallelism enables multi-GPU deployment with a single flag (`--tensor-parallel-size N`). Known Apptainer quirks require `--containall` and explicit bind mounts since the container assumes root Docker execution. **Both Qwen 3.5 and Gemma 4 have day-0 vLLM support** — Qwen 3.5 with native `--tool-call-parser qwen3_coder` and Gemma 4 via transformers integration.

**SGLang (v0.5.0+, active development)** is the potentially superior alternative, purpose-built for structured LLM programs. Its RadixAttention organizes KV cache in a radix tree, enabling automatic prefix reuse across multi-turn agent conversations — directly benefiting ReAct workflows. On agent control, JSON decoding, and multi-turn chat, SGLang achieves up to 6.4× higher throughput than comparable systems. Qwen 3.5 models include first-class SGLang launch commands in their official documentation (including MTP speculative decoding support), making SGLang a particularly strong option for the Qwen 3.5 family.

**TGI entered maintenance mode on December 11, 2025.** HuggingFace officially recommends vLLM or SGLang for new deployments. No new features will be developed.

**Ollama** is unsuitable for production agent workloads — response times balloon from 2 seconds to 45+ seconds with just 10 concurrent users due to absence of continuous batching. Its value is strictly in rapid prototyping. Gemma 4 has day-0 Ollama support (`ollama run gemma4`). **llama.cpp/llama-server** offers best-in-class grammar-constrained generation (GBNF format with guaranteed 100% JSON validity) but throughput stays flat regardless of concurrency, making it unsuitable for batch evaluation. Both Gemma 4 and Qwen 3.5 have day-0 llama.cpp GGUF support.

| Feature | vLLM | SGLang | llama.cpp | Ollama |
|---------|------|--------|-----------|--------|
| Continuous batching | ✅ Core | ✅ Yes | ❌ Basic slots | ❌ No |
| Structured output perf. | Good (overhead at high batch) | **Best** (overlapped masks) | **Best** (grammar guarantee) | Limited |
| Tensor parallelism | ✅ Excellent | ✅ Yes | ❌ Layer offload only | ❌ No |
| HPC/SLURM docs | **Best** | Adequate | Good (lightweight) | Poor |
| litellm provider | ✅ Native | Via OpenAI compat. | Via OpenAI compat. | ✅ Native |
| Agent workload throughput | 35× llama.cpp | Up to 6.4× vLLM | Baseline | Collapses |
| Qwen 3.5 tool calling | ✅ `qwen3_coder` parser | ✅ `qwen3_coder` parser | Via GGUF | Via Ollama |
| Gemma 4 support | ✅ Day-0 | ✅ Day-0 | ✅ Day-0 GGUF | ✅ Day-0 |

**Recommendation:** Deploy vLLM as the primary framework via Apptainer on SLURM. Evaluate SGLang on a subset of experiments — if its structured output performance advantage is confirmed on your workloads, migration is straightforward since both expose OpenAI-compatible APIs. Use llama.cpp during development for guaranteed JSON validity when debugging prompt templates.

---

## 2. Model Selection Across Three Deployment Tiers

Model selection must be evaluated in the context of pipeline architecture. The Matchmaker finding — that compositional pipelines with weaker models beat monolithic prompts with stronger models — means the optimal strategy is prototyping pipeline design with frontier models, then systematically substituting local models at each pipeline stage.

> **Important nomenclature note:** The original research prompt referenced "Qwen 3.5 (4B, 9B, 27B)" models. Those were the **Qwen 3 generation** (released April 2025). The **actual Qwen 3.5** series (released February–March 2026) is a substantial generational upgrade with a hybrid Gated Delta Networks + MoE architecture, native multimodality via early fusion, and dramatically improved agentic performance. This section uses the correct naming throughout. Similarly, **Gemma 4** (released April 2, 2026) represents a generational leap over Gemma 3, with native function calling that was absent in Gemma 3.

### Tier 1: Frontier API Models for Baseline Establishment

**Claude Sonnet 4.6** ($3/$15 per M tokens, 1M context) is the recommended default for pipeline prototyping. It offers native JSON function calling deeply integrated with multi-step agentic workflows, approaching previous flagship performance at 40% lower cost than Opus. **Gemini 2.5 Flash** ($0.50/$3) is optimal for high-volume candidate generation stages where cost per operation matters more than peak reasoning — at $0.40 per 1,000 schema matching operations. **DeepSeek V3.2** ($0.28/$0.42) offers 10–50× cost advantage over Western frontier models with strong tool-calling capabilities, though its 128K context window is shorter than competitors.

### Tier 2: Mid-range Models for Production on A100/A40/RTX6000

**Qwen3.5-35B-A3B is the top recommendation.** This MoE model (35B total, **3B active** per token, 256 experts with 8 routed + 1 shared) surpasses the previous-generation Qwen3-235B-A22B (22B active) despite activating only 3B parameters — a remarkable efficiency breakthrough. It features a novel hybrid Gated Delta Networks + sparse MoE architecture with 262K native context (extensible to 1M via YaRN), native multimodal support via early-fusion training on multimodal tokens, and 201-language coverage. Tool calling is natively supported with dedicated parsers in both vLLM (`--tool-call-parser qwen3_coder`) and SGLang. At Q4_K_M quantization it requires ~18–20GB VRAM, fitting comfortably on any available GPU. It generates at ~188 tokens/sec on Alibaba's API and comparable speeds locally. The Qwen3.5-122B-A10B scores 72.2 on BFCL-V4 (function calling), outperforming GPT-5 mini (55.5) by 30% — strong evidence that the Qwen 3.5 family excels at the tool-calling patterns required for ReAct agents. Apache 2.0 license permits unrestricted use.

**Gemma 4 26B-A4B (NEW — released April 2, 2026) should be evaluated as a direct competitor.** This MoE model (26B total, **~4B active**, 128 small experts with 8 active + 1 shared always-on) represents an extraordinary generational leap: on τ2-bench Retail (agentic tool use), the 26B scores **85.5%** versus Gemma 3 27B's 6.6% — a 79-point jump that signals fundamental improvements in multi-step tool-use capability. It achieves an LMArena ELO of 1441, MMLU Pro of ~82%, and 88.3% on AIME 2026 (math reasoning). Critically for the harmonization use case, **Gemma 4 introduces native function calling and native system prompt support** — both absent in Gemma 3, which the original report flagged as disqualifying ("Avoid Gemma 3 variants — no native tool-calling tokens"). This limitation is fully resolved. Apache 2.0 license (first time for Gemma). 256K context window. Day-0 support in Ollama, vLLM, llama.cpp, transformers, and MLX. At Q4 quantization, the 26B-A4B fits on a 24GB GPU.

**Gemma 4 31B (dense)** is the alternative for maximum quality within Tier 2. It scores 86.4% on τ2-bench, 89.2% on AIME 2026, 85.2% on MMLU Pro, and 80.0% on LiveCodeBench v6. It requires ~20GB at FP16 (fits on a 24GB GPU) or ~40GB unquantized, easily fitting on a single A100. For the harmonization use case where inference speed matters less than accuracy during batch evaluation, the 31B dense variant may outperform the MoE on complex multi-turn tool-calling scenarios.

**Nemotron 3 Nano 30B-A3B** (NVIDIA, 31.6B/3.6B active, hybrid Mamba-Transformer MoE) offers a **1M token context window** — industry-leading at this size — trained with 690 agentic tool-use tasks via RL. This context length is valuable for loading entire GDC schemas alongside metadata tables. Requires ~20GB at INT4. **Kimi K2** (1.04T total/32B active) delivers exceptional agentic performance supporting 200–300 sequential tool calls, but its 1T total parameters require multi-GPU hosting.

**Qwen3.5-27B (dense)** is a strong dense alternative, achieving 72.4 on SWE-bench Verified (matching GPT-5 mini). At ~16GB in FP16, it fits easily on any available GPU. Choose this over 35B-A3B if you want slightly more accurate results on a device that struggles with the MoE overhead, or if you need a dense architecture for simpler deployment.

### Tier 3: Small Models for Rapid Screening and Candidate Generation

**Qwen3.5-9B** (9B dense, ~5.5GB at Q4, 262K context) is the standout in this tier and a major upgrade from the Qwen3 generation. It matches or surpasses models 13× its size on multiple benchmarks (81.7 on GPQA Diamond) and scored 70.1 on MMMU-Pro visual reasoning, outperforming Gemini 2.5 Flash-Lite (59.7) and GPT-5-Nano (57.4). Native multimodal via early-fusion, native tool calling, and dual-mode thinking/non-thinking. The 4B variant is the optimal choice for most coding tasks per community benchmarks, offering stability without performance drops and faster inference.

**Gemma 4 E4B (NEW)** (4.5B effective parameters with Per-Layer Embeddings, 128K context) is the new contender for ultra-lightweight deployment. It scores 52.0% on LiveCodeBench and 58.6% on GPQA Diamond — strong for a model that runs on a T4 GPU. Supports images, video, and audio input. While its reasoning ceiling is lower than Qwen3.5-9B, its native multimodal capabilities including audio may be useful for specific pipeline stages. Runs in under 4GB at Q4 quantization.

**Mistral Nemo 12B** remains a solid Tier 3 alternative with native Mistral tool-calling format supported in vLLM.

**Avoid:** Phi-4 (poor instruction following, 16K context), Llama 4 Scout (deprecated, unreliable tool calling format), and ~~Gemma 3 variants~~ (superseded by Gemma 4 in every dimension — do not use Gemma 3 for new work).

### GPU-Specific Deployment Matrix

| GPU | Best Model | Quantization | VRAM Used | Notes |
|-----|-----------|-------------|-----------|-------|
| A100-80GB | Qwen3.5-122B-A10B | FP8 | ~70GB | Best open-weight function calling (BFCL-V4: 72.2) |
| A100-40GB | Qwen3.5-35B-A3B | FP8 | ~20–25GB | Room for large context; or Gemma 4 31B dense (~22GB FP16) |
| A40/RTX6000 48GB | Qwen3.5-35B-A3B + Gemma 4 31B | FP8/FP16 | ~20–22GB | Test both — room for large KV cache at either |
| RTX 4090 24GB | Gemma 4 26B-A4B or Qwen3.5-35B-A3B | Q4_K_M | ~15–18GB | MoE models fit comfortably; test both |
| Any ≥12GB | Qwen3.5-9B | Q8 | ~10GB | Best Tier 3 option; or Gemma 4 E4B (~3GB at Q4) |

---

## 3. Quantization Degrades Structured Outputs More Than General Benchmarks Suggest

The consensus from multiple sources is clear: **Q5_K_M or GPTQ-INT8 is the minimum recommended quantization for production structured output tasks.** Below this threshold, instruction-following accuracy — critical for tool calling and JSON schema adherence — degrades faster than general perplexity metrics indicate.

The Ionio.ai benchmark study (September 2025, preprint) across Qwen2.5, DeepSeek, Mistral, and LLaMA 3.3 found that "instruction-following accuracy degrades the fastest under low-bit quantization, especially AWQ and Q4_K_M" and that "agents operating in deterministic flows require stable decoding and alignment, which lower-bit quantization disrupts." GPTQ-INT8 and Q5_K_M were identified as optimal trade-offs. The IJCAI 2025 paper on quantization methods confirmed coding and STEM tasks suffer most, while LiveBench results showed Q3_K_M and below significantly reduce scores on data analysis tasks.

**Qwen 3.5 quantization update:** Unsloth's updated GGUF quantizations for Qwen 3.5 (March 2026) show that UD-Q4_K_XL and UD-Q3_K_XL stay within a 1-point accuracy drop on a 750-prompt mixed suite for the 397B flagship. For the 35B-A3B variant, the community reports improved tool-calling reliability after Unsloth's chat template fixes (March 5, 2026 — redownload recommended). **Gemma 4** benefits from quantization-aware training during the base model training phase, which may reduce quality degradation at lower bit widths — this should be empirically verified as part of the quantization impact study.

### The Larger-Model-at-Lower-Quantization Rule Holds — with Caveats

Strong consensus favors running a larger model at Q4 over a smaller model at Q8 for general tasks. However, this rule breaks down at extreme quantization (≤Q3) and for highly structured tasks where token-level precision matters. For the metadata harmonization use case:

- **48GB GPU:** Qwen3.5-35B-A3B at FP8 (~20GB) or Gemma 4 31B at FP16 (~22GB) — both fit with ample room for KV cache
- **80GB GPU:** Qwen3.5-122B-A10B at FP8 (~70GB) maximizes quality and structured output reliability
- **24GB GPU:** Either MoE model (Gemma 4 26B-A4B or Qwen3.5-35B-A3B) at Q4_K_M (~15–18GB)
- **Always pair with constrained decoding** (vLLM structured outputs or llama.cpp grammar mode) to guarantee JSON validity regardless of quantization level

### A Critical Research Gap Exists

**No published benchmark specifically isolates quantization level versus JSON/schema output accuracy.** This gap represents a genuine novel contribution axis for the benchmark paper. The recommended evaluation protocol: run identical prompts through F16, Q8, Q6_K, Q5_K_M, and Q4_K_M with and without constrained decoding, measuring JSON validity rate, schema conformance, field-level accuracy, and KL divergence against the F16 baseline. **Test across both Qwen 3.5 and Gemma 4 families** to determine whether hybrid architectures (Gated Delta Networks) and MoE sparsity patterns interact differently with quantization than standard dense transformers.

**AWQ outperforms GPTQ for structured tasks.** JarvisLabs benchmarks show AWQ achieves 51.8% Pass@1 on HumanEval versus GPTQ's 46.3%, with better quality retention (95% vs 90% at 4-bit). For vLLM deployment, AWQ with Marlin kernels delivers 741 tokens/sec versus GPTQ's 712. Qwen 3.5 also provides official GPTQ-Int4 variants on HuggingFace for all sizes.

---

## 4. Context Selection: Budget Evidence Aggressively Rather Than Maximizing It

ConStruM's central finding transforms how prompts should be designed for schema matching: "Matching quality suffers from a lack of context information, but also from providing too much context information." This "Goldilocks zone" was validated across multiple papers and directly applies to GEO→GDC harmonization.

### Context Elements Ranked by Impact on Schema Matching

Based on converging evidence from ConStruM, Parciak et al. (VLDB TaDA 2024), Matchmaker, KG-RAG4SM, and SCHEMORA:

**Critical tier:** (1) Column/attribute names + natural language descriptions consistently provide the largest accuracy boost. (2) Schema-level context — neighboring columns in the same table — was essential in ConStruM, enabling 93.5% accuracy versus 68.8% for column-only context on HRS-B. (3) Domain knowledge from ontologies: KG-RAG4SM showed KG-augmented prompts improved Jellyfish-8B by +35.89% precision on MIMIC.

**Important tier:** (4) Few-shot example mappings, validated by Matchmaker's +5% improvement with 4 synthetic demonstrations. (5) Differentiation cues among confusable candidates — ConStruM's similarity hypergraph provides contrastive descriptions for near-duplicate GDC fields. (6) Table-level context (table name + description).

**Supplementary tier:** Data types, sample values (often unavailable in healthcare due to privacy), and foreign key relationships.

### Translating to GEO→GDC

For each GEO metadata field, the prompt should include (in priority order): source field name + any description; target GDC property name + description + allowed enum values; GDC node category and table context; NCIt/caDSR semantic type and synonyms for ambiguous terms; 2–3 neighboring source columns; and explicit differentiation cues for confusable GDC candidates. SCHEMORA's technique of generating 3 alternative column names via LLM improved HitRate@5 by 7.49% on MIMIC-OMOP — this should be applied to GEO field enrichment before embedding-based retrieval against the GDC dictionary.

Smaller models benefit disproportionately from structured context: KG-RAG4SM showed KG augmentation helped 8B models far more than frontier models. **This is particularly relevant for evaluating Qwen3.5-9B and Gemma 4 E4B** — proper context engineering may allow these small models to approach Tier 2 performance on the harmonization task.

---

## 5. DSPy Is the Validated Choice for Prompt Optimization, with GEPA as the Emerging Upgrade

Among automatic prompt optimization approaches — DSPy, OPRO, APE, and meta-prompting — **DSPy (v3.1.3, GitHub: github.com/stanfordnlp/dspy, 32.6K stars) is the only framework with direct validation for schema matching** via Matchmaker's +5% acc@1 improvement using bootstrapped few-shot demonstrations.

### DSPy Optimizer Selection for This Use Case

**BootstrapFewShot** (Matchmaker-validated): Runs the program across training inputs, collects traces, filters to keep only trajectories scoring highly on the target metric, and includes filtered input-output pairs as synthetic demonstrations. Matchmaker used at most 4 synthetic in-context examples per component. This optimizer works with very few labeled examples and is the recommended starting point.

**GEPA (July 2025, newest):** Reflective Prompt Evolution using Genetic-Pareto optimization. Maintains a Pareto frontier of candidates rather than a single best, using LLM reflection on execution traces to propose improvements. Remarkably sample-efficient — a dataset of just 14 training examples showed significant improvement on extraction tasks, with ~1,200 rollouts costing only $2–3 in API calls for a ~22-percentage-point accuracy boost.

**MIPROv2** (flagship general-purpose): Bayesian optimization over instruction+demonstration space. Best when 100+ training examples are available.

### OPRO Is Ineffective for Local Models

A critical limitation confirmed by independent replication (arXiv 2405.10276): OPRO is ineffective for small-scale LLMs including LLaMA-2 and Mistral 7B. Since the metadata harmonization system targets local model deployment, OPRO should not be used.

### Methodological Safeguards

DSPy's official documentation recommends a 20% train / 80% validation split. Maintain a completely separate held-out test set never touched during optimization. Report both training and test performance. Run multiple optimization seeds and report variance. Declare optimization cost. "30 examples provides substantial value; aim for at least 300" per DSPy documentation.

---

## 6. Experimental Design Must Handle 270+ Configurations Without Brute Force

With ~10 models × 3 architectures × 3 prompt strategies × 3 quantization levels = 270+ configurations, brute-force evaluation (3 runs each = 810+ runs) is prohibitively expensive. **Note: the addition of Gemma 4 models to the model roster increases the number of Tier 2 and Tier 3 candidates, making sequential experimentation even more important.**

### Temperature=0 Is Not Deterministic

This is now well-documented across all major providers. A systematic investigation of 5 models on 8 tasks with 10 runs each at temperature=0 (arXiv 2408.04667) confirmed non-trivial variance. 83% of single-run evaluations led to rank inversions versus three-run aggregates (arXiv 2509.24086). The minimum is 3 runs for final comparison; 2 runs is cost-effective for screening.

### A Four-Phase Experimental Pipeline

**Phase 1 — Pilot & power analysis (~20 configurations, 1 run each):** Select representative configurations covering all factor levels. Include at least one Qwen 3.5 and one Gemma 4 model per tier to establish family-level baselines early.

**Phase 2 — Screening via successive halving (~270+ configurations):** Evaluate all configurations on 10% of test instances (1 run). Eliminate bottom two-thirds. Promote survivors to 30% of test instances. Continue until ~30 configurations remain evaluated on the full test set.

**Phase 3 — Detailed comparison (top 10–15 configurations):** Run 3–5 times each on the full test set. Apply mixed-effects models with test instance as random intercept.

**Phase 4 — Final validation (top 3–5 configurations):** Run 5+ times on a held-out validation set. This produces the numbers reported in the paper.

### Statistical Test Selection

| Outcome type | Comparison | Test | Multiple correction |
|-------------|-----------|------|-------------------|
| Binary (column match correct/incorrect) | Two configurations | McNemar's (exact when discordant pairs <25) | — |
| Binary | >2 configurations | Cochran's Q → pairwise McNemar | Holm-Bonferroni |
| Continuous (F1, accuracy) | Two configurations | Wilcoxon signed-rank | — |
| Continuous | >2 configurations | Friedman → pairwise Wilcoxon | Benjamini-Hochberg for screening; Holm-Bonferroni for final |

**Effect sizes:** Use Cliff's δ (range −1 to +1; |δ|<0.147 negligible, <0.33 small, <0.474 medium, ≥0.474 large). Report with bootstrap BCa 95% CIs.

---

## 7. Cost-Quality Pareto Analysis and What Benchmark Papers Must Report

### LLM Inference Costs Span Three Orders of Magnitude

For a typical schema matching operation (2K input + 500 output tokens):

| Model tier | Cost per 1,000 operations | Representative model |
|-----------|--------------------------|---------------------|
| Premium frontier | $22.50 | Claude Opus 4.6 |
| Standard frontier | $13.50 | Claude Sonnet 4.6, GPT-5.4 |
| Budget frontier | $0.40 | Gemini 2.0 Flash |
| Budget frontier (Qwen API) | $0.10–0.25 | Qwen3.5-Flash ($0.10/M input) |
| Near-frontier API | $0.31–0.85 | DeepSeek V4 (cached) |
| Local 70B on H100 | ~$8.40 | Including amortized hardware |
| Local 35B MoE on A100 | ~$1.50 | Qwen3.5-35B-A3B or Gemma 4 26B-A4B (electricity only) |

**Qwen3.5-Flash at $0.10/M input tokens** delivers frontier-adjacent intelligence at roughly 1/13th the cost of Claude Sonnet 4.6 for comparable tasks — this should be included in the cost-quality Pareto analysis as a cloud API baseline for the 35B-A3B architecture.

### NeurIPS and ICML Reporting Requirements

The NeurIPS 2026 Evaluations & Datasets Track requires: Croissant machine-readable metadata, dataset hosting on Dataverse/Kaggle/HuggingFace/OpenML, executable benchmark code, and public dataset availability by camera-ready. The paper checklist requires reporting compute workers, amount of compute per run, total compute including failed experiments, error bars from multiple runs, and CO2 emissions tracking.

For LLM-specific papers: exact model identifiers with version strings (e.g., `Qwen/Qwen3.5-35B-A3B`, `google/gemma-4-26B-A4B-it`), full prompt templates, all generation parameters, number of API calls and total tokens consumed, and API access dates. Pin exact model checkpoint hashes for open-weight models and inference framework versions.

---

## 8. Publication Strategy Targets VLDB 2027 with a BioDMS Workshop Stepping Stone

### What Makes This Publishable

The publishable contribution requires: (1) a reusable benchmark with expert-validated GEO→GDC mappings, (2) systematic evaluation methodology revealing interactions between model choice, pipeline architecture, and quantization, (3) the first quantization impact analysis for schema matching, and (4) cost-quality Pareto analysis with actionable guidance.

**The timing is excellent:** with Gemma 4 released just yesterday (April 2, 2026) and Qwen 3.5 released in February–March 2026, a benchmark paper that systematically evaluates these latest-generation open-weight models on a domain-specific task would be highly timely. Every existing comparator — Magneto (VLDB 2026), Matchmaker, SCHEMORA, ConStruM — must be evaluated on the same benchmark.

### Venue Selection and Timeline

**Immediate stepping stone (deadline May 15, 2026):** BioDMS Workshop at VLDB 2026. Submit a 2–4 page position paper with benchmark design and preliminary results.

**Primary target: VLDB 2027 EA&B Track** (rolling monthly deadlines through ~March 2027). Schema matching is core VLDB territory.

**Alternative: NeurIPS 2026 Evaluations & Datasets Track** (abstract May 4, full paper May 6 — very tight).

### Realistic Timeline

- **Phase 1 — Benchmark creation (6–10 weeks):** Define GEO→GDC ground truth mappings, implement evaluation framework.
- **Phase 2 — Systematic experimentation (6–10 weeks):** Full model sweep across tiers (now including Qwen 3.5 and Gemma 4 families), architecture variations, quantization analysis.
- **Phase 3 — Analysis and writing (6–8 weeks).**
- **Total: 5–7 months.**

---

## Integrated Recommendations for the Harmonia/BDI-Kit Research Fork

**Infrastructure:** Deploy vLLM v0.18+ via Apptainer on SLURM as the primary inference backend. Use the `hosted_vllm/` litellm provider. Enable prefix caching for multi-turn ReAct conversations. Evaluate SGLang on a subset of experiments (especially strong for Qwen 3.5 with MTP speculative decoding support). Keep Ollama for development/debugging only.

**Model strategy — updated for Qwen 3.5 and Gemma 4:**
- *Frontier baselines:* Prototype all pipeline architectures with Claude Sonnet 4.6 to establish performance ceilings.
- *Tier 2 primary:* Deploy **Qwen3.5-35B-A3B** (Apache 2.0, ~18GB at Q4) as the primary local model. Evaluate **Gemma 4 26B-A4B** (~15GB at Q4) as a direct head-to-head competitor — its τ2-bench agentic tool-use scores (85.5%) warrant serious evaluation. Also test **Gemma 4 31B dense** (~22GB FP16) for maximum accuracy.
- *Tier 3 screening:* Use **Qwen3.5-9B** (~5.5GB at Q4) for high-volume candidate generation stages. Test **Gemma 4 E4B** (~3GB at Q4) as the ultra-lightweight option.
- *Routing:* Route ambiguous/low-confidence mappings to frontier models via confidence thresholds.

**Quantization:** Use AWQ format with vLLM's Marlin kernels for GPU deployment. Minimum Q5_K_M for structured output tasks. Always enable constrained decoding. Systematically benchmark F16 through Q4_K_M on the harmonization task across both Qwen 3.5 and Gemma 4 families to fill the identified research gap and test whether MoE sparsity interacts with quantization differently than dense architectures.

**Prompt design:** Implement ConStruM-style budgeted evidence packing. Use SCHEMORA's dual-prompt technique for GEO field enrichment. Include NCIt/caDSR ontology context. Limit few-shot demonstrations to 4 per component.

**Prompt optimization:** Start with DSPy BootstrapFewShot (validated by Matchmaker). Upgrade to GEPA once 20+ labeled examples exist. Maintain strict 20/80 train/validation split with a completely separate held-out test set.

**Experimental methodology:** Run minimum 3 replicates per final configuration. Use four-phase successive halving to manage the combinatorial explosion (now larger with Gemma 4 additions). Apply McNemar's test for pairwise binary comparisons, mixed-effects models for item-level analysis, Cliff's δ for effect sizes, and Holm-Bonferroni correction. Report bootstrap BCa 95% CIs.

**Publication:** Submit BioDMS workshop paper by May 15, 2026. Target VLDB 2027 EA&B track as the primary venue. Frame the contribution around evaluation methodology and the quantization gap. Release all code, prompts, configurations, and raw outputs as a reproducibility package with Croissant metadata on HuggingFace.
