# Critical Evaluation of LLM Tracing Implementation Plans for Harmonia

**Date**: 2026-03-03
**Author**: Claude Code (architectural evaluation)
**Input documents**: Research report (`03_03_2026_research_into_LLM_tracing.md`), four implementation plans (Langfuse, Phoenix, Opik, Custom Dash)

---

## 1. Evaluation Criteria and Weights

| # | Criterion | Weight | Definition |
|---|-----------|--------|------------|
| 1 | **Trace Completeness** | 25% | How thoroughly does the plan address the gaps identified in the research report? Specifically: token counts per LLM call, cost tracking per turn/run, nested span hierarchy (Turn > LLM call > Tool use > Code execution), structured tool call data, model parameters logging, full prompt at each turn, retry tracking. Plans that leave high-severity gaps unaddressed score lower. |
| 2 | **Visualization and UX** | 20% | Quality of the trace drill-down GUI, side-by-side trace comparison, click-through from metrics to individual traces, search/filter capabilities, latency waterfall, and overall usability for a researcher analyzing experiment results. Out-of-the-box capabilities score higher than "requires custom development." |
| 3 | **Integration Cost** | 20% | Total developer-days, number of files created/modified, complexity of changes to the existing codebase, risk of breaking existing functionality (trace.json, conversation.md, metrics.json, the log analysis CLI). Lower cost and lower disruption score higher. |
| 4 | **Deployment Feasibility** | 20% | Compatibility with HPC constraints: no Docker daemon on compute nodes (Apptainer only), no persistent services between SLURM jobs, no root/sudo, 5 GB home directory limit, SSH port-forwarding for UI access, file-based persistence preferred. Plans requiring external infrastructure or complex container orchestration score lower. |
| 5 | **Maintenance and Ecosystem** | 10% | License permissiveness, community size, long-term viability of the project, frequency of breaking changes, documentation quality, update burden for a single-developer team. |
| 6 | **Extensibility** | 5% | How easily can the solution accommodate future needs: new LLM providers, new evaluation types, new visualization requirements, integration with other tools (e.g., a future annotation workflow or LLM-as-judge evaluation pipeline)? |

---

## 2. Per-Plan Evaluation

### 2.1 Langfuse

#### Scores

| Criterion | Score (1-10) | Weight | Weighted |
|-----------|-------------|--------|----------|
| Trace Completeness | 9 | 25% | 2.25 |
| Visualization and UX | 8 | 20% | 1.60 |
| Integration Cost | 6 | 20% | 1.20 |
| Deployment Feasibility | 3 | 20% | 0.60 |
| Maintenance and Ecosystem | 8 | 10% | 0.80 |
| Extensibility | 8 | 5% | 0.40 |
| **Weighted Total** | | | **6.85** |

#### Strengths

- **Richest data model among the platform options.** Langfuse's 10 observation types (generation, span, event, etc.) map cleanly to Harmonia's needs. The plan's `HarmoniaLangfuseTracer` class is well-designed, with explicit methods for each span type and graceful degradation when the server is unreachable. The generation observation type has first-class token/cost fields that directly close the two highest-severity gaps from the research report.
- **Best ecosystem and long-term viability.** MIT license, 22.6k GitHub stars, active development, and the largest community of any evaluated framework. For a project that may outlive a single researcher's tenure, this provides the safest bet against framework abandonment.
- **Thoughtful dual-write architecture.** The plan explicitly keeps local `trace.json` files as the authoritative record and positions Langfuse as an enrichment layer. The export bridge (`langfuse_export.py`) that converts Langfuse traces back to the local format for the failure-mode CLI is a well-considered design decision that respects the existing tooling.

#### Weaknesses

- **Infrastructure requirements are prohibitive for this HPC environment.** Six Docker Compose containers (PostgreSQL, ClickHouse, MinIO, Redis, web, worker) requiring 4 vCPUs and 16 GB RAM cannot run on compute nodes. The plan acknowledges this and proposes a separate "lab workstation or department VM," but this introduces a hard dependency on infrastructure that the developer does not currently control. If that machine is unavailable, reboots, or is decommissioned, the entire visualization tier is lost.
- **Network connectivity between compute nodes and the Langfuse server is unverified.** The plan lists this as Risk 2 and proposes testing with `curl` before development. This is responsible, but the fact that it remains an open question is concerning. If compute nodes cannot reach a self-hosted Langfuse instance, the only fallback is Langfuse Cloud (data residency issues) or a local buffer-and-sync approach that adds complexity the plan does not account for.
- **Estimated 6 developer-days is optimistic.** The plan modifies 13 files and requires standing up and maintaining a 6-container Docker Compose stack. The "1 day" allocated for "Langfuse server deployment and testing" underestimates the effort of provisioning a persistent machine, configuring Docker Compose, setting up backups, and validating network connectivity from HPC compute nodes. A more realistic estimate is 8-10 developer-days including infrastructure setup and validation.

#### Key Risk

The entire visualization benefit depends on a separate persistent machine running Docker Compose. If that machine is not available, or if HPC network policies block connectivity, the Langfuse plan degrades to "enriched trace.json files with no GUI" -- essentially a more complex version of the Custom Dash approach but without the dashboard.

---

### 2.2 Arize Phoenix

#### Scores

| Criterion | Score (1-10) | Weight | Weighted |
|-----------|-------------|--------|----------|
| Trace Completeness | 8 | 25% | 2.00 |
| Visualization and UX | 7 | 20% | 1.40 |
| Integration Cost | 5 | 20% | 1.00 |
| Deployment Feasibility | 8 | 20% | 1.60 |
| Maintenance and Ecosystem | 6 | 10% | 0.60 |
| Extensibility | 7 | 5% | 0.35 |
| **Weighted Total** | | | **6.95** |

#### Strengths

- **Lightest deployment footprint of any platform framework.** A single `pip install` and a `phoenix serve` process with SQLite storage. No Docker, no PostgreSQL, no Redis. This is the only platform framework that can run on the HPC submit node without external infrastructure. The plan's `phoenix_server.sh` script using `screen` on a submit node is realistic and follows a pattern already established in this project.
- **OpenTelemetry-native architecture provides genuine portability.** Using OTel span attributes and the OpenInference semantic conventions means the instrumentation code is not locked to Phoenix. If a future decision requires migrating to a different backend (Jaeger, Grafana Tempo, or Langfuse, which now supports OTLP ingestion), the spans can be redirected by changing the exporter endpoint. This is a significant architectural advantage over Langfuse and Opik SDKs, which use proprietary wire formats.
- **Strong data export pipeline.** `get_spans_dataframe()` returns a pandas DataFrame, which integrates naturally with the existing metrics pipeline. The plan to export `spans.parquet` files alongside `trace.json` is practical and enables the existing analysis CLI to be enriched incrementally without a hard dependency on the Phoenix server being available.

#### Weaknesses

- **Estimated 10-12 developer-days is the highest of any plan.** The scope includes not just the core tracing module but also a `compare_traces.py` side-by-side tool, extensive modifications to the visualization CLI, and testing across 3+ providers. The plan does not clearly distinguish "must-have" from "nice-to-have" work, making it difficult to identify a viable minimum deliverable.
- **Elastic License v2 is not truly open source.** ELv2 prohibits offering Phoenix as a managed service, which is irrelevant for this use case, but some institutional procurement or legal teams may flag it. More practically, ELv2 projects have historically changed license terms. For an academic project with long timelines, this is a non-zero risk, though a low one.
- **No dedicated side-by-side trace comparison or metrics click-through out of the box.** The plan acknowledges both gaps and proposes custom solutions, but the side-by-side comparison (`compare_traces.py`) is estimated at 1.5 days and deferred as "optional." This means the P0 side-by-side requirement remains unmet at initial delivery.

#### Key Risk

Phoenix server lifecycle on the HPC submit node. Submit nodes are shared resources. A long-running `screen` process can be killed by administrators, OOM events, or node reboots. The plan proposes a restart loop in `phoenix_server.sh` and frequent span flushing, but data loss during a crash remains possible. The mitigation is sound (local trace.json is always written), but there may be gaps in the Phoenix UI if the server was down during an experiment batch.

---

### 2.3 Opik

#### Scores

| Criterion | Score (1-10) | Weight | Weighted |
|-----------|-------------|--------|----------|
| Trace Completeness | 8 | 25% | 2.00 |
| Visualization and UX | 7 | 20% | 1.40 |
| Integration Cost | 4 | 20% | 0.80 |
| Deployment Feasibility | 2 | 20% | 0.40 |
| Maintenance and Ecosystem | 5 | 10% | 0.50 |
| Extensibility | 7 | 5% | 0.35 |
| **Weighted Total** | | | **5.45** |

#### Strengths

- **First-class token/cost fields on span objects.** Unlike Langfuse and Phoenix where token counts are stored as generic attributes or semantic convention strings, Opik's `llm` span type has typed, named fields for `input_tokens`, `output_tokens`, `total_tokens`, and `cost`. This is a cleaner API that reduces the chance of attribute naming errors.
- **Built-in experiment leaderboard and Agent Optimizer.** The experiment comparison UI and the Agent Optimizer SDK for prompt tuning go beyond what the other frameworks offer. If Harmonia's evaluation workflow grows to include systematic prompt optimization across models, Opik provides scaffolding that the other options lack.
- **Apache 2.0 license.** The most permissive license among the platform options, which matters for academic projects that may produce derivatives or be shared across institutions.

#### Weaknesses

- **Heaviest infrastructure of any option (8 containers).** ClickHouse, MySQL, Redis, MinIO, Zookeeper, plus three application containers. The plan acknowledges this is the "main deployment challenge" and proposes using Opik Cloud as Phase 1, which effectively means the plan does not solve the self-hosted deployment problem. Converting Docker Compose to individual Apptainer instances with shared networking is described as "a non-trivial systems engineering task" -- this is an understatement that likely adds 3-5 developer-days beyond the 12 already estimated.
- **Youngest ecosystem with the smallest community.** Opik has significantly fewer users, contributors, and battle-tested deployments than Langfuse or Phoenix. The Docker Compose deployment is described as "not production-ready" in the research report. Betting on the youngest option increases the risk of encountering undocumented bugs or breaking API changes during the project's lifetime.
- **12 developer-days estimated, likely 14-16 in practice.** The 2-day "Opik infrastructure setup" allocation is unrealistic for converting an 8-container Docker Compose stack to Apptainer. If the cloud fallback is used instead, the plan should honestly account for the ongoing dependency and data-residency risks of relying on an external SaaS for experiment traces.

#### Key Risk

The plan has no viable self-hosted deployment path on HPC. The only realistic option is Opik Cloud, which creates a permanent external dependency for an academic research project. If Comet.ml changes pricing, restricts their free tier, or discontinues Opik, all historical trace data in the cloud becomes inaccessible. This fundamentally undermines data sovereignty for a research project that should own its data.

---

### 2.4 Custom Dash Dashboard

#### Scores

| Criterion | Score (1-10) | Weight | Weighted |
|-----------|-------------|--------|----------|
| Trace Completeness | 5 | 25% | 1.25 |
| Visualization and UX | 9 | 20% | 1.80 |
| Integration Cost | 7 | 20% | 1.40 |
| Deployment Feasibility | 10 | 20% | 2.00 |
| Maintenance and Ecosystem | 5 | 10% | 0.50 |
| Extensibility | 6 | 5% | 0.30 |
| **Weighted Total** | | | **7.25** |

#### Strengths

- **Perfect HPC deployment feasibility.** Zero infrastructure beyond a single Python process. Reads existing file artifacts directly. Can run as a SLURM job or in `screen` on a submit node. No database, no container orchestration, no external dependencies. SSH port-forwarding to a single port. This is the only plan that fully respects all HPC constraints without any compromise or workaround.
- **Best native click-through from metrics to traces.** Because both the metrics visualization and the trace viewer live in the same Dash application, the click-through from a bar chart to a trace is a native Dash callback -- no URL construction, no sidecar files, no cross-system linking. The side-by-side comparison is also a built-in tab with synchronized turn accordions and a diff summary card. This is the only plan that delivers all three P0 visualization requirements (trace viewer, side-by-side comparison, metrics click-through) without deferring any to "future work."
- **Lowest disruption to existing codebase.** The plan modifies only `logger.py` (to enrich `TurnRecord` with new fields) and creates all new files under `src/dashboard/`. The existing `trace.json`, `conversation.md`, and `metrics.json` formats are extended backward-compatibly with default values. The log analysis CLI, the metrics visualization CLI, and the experiment runners are untouched at the integration layer.

#### Weaknesses

- **Does not solve the trace capture problem -- the primary motivation for this work.** The research report identifies token counts, cost tracking, nested spans, and structured tool data as high-severity gaps. The Custom Dash plan enriches `logger.py` with some of these fields (token counts, cost, code cell extraction) but does not introduce a true nested span hierarchy. The trace data model remains fundamentally flat (turns with optional sub-fields), not a proper span tree. The dashboard visualizes an incomplete picture more beautifully, but the picture remains incomplete.
- **Single-developer maintenance burden for the entire visualization stack.** Langfuse, Phoenix, and Opik provide maintained, tested, evolving GUI components backed by engineering teams. The Custom Dash plan requires the project developer to build and maintain AG Grid configurations, Plotly chart layouts, Dash callbacks, accordion components, syntax highlighting, and responsive two-column layouts from scratch. When Dash, AG Grid, or Plotly release breaking changes, the developer must update the application. This is a long-tail cost that compounds.
- **No built-in evaluation or annotation framework.** The plan mentions a "Notes" text area writing to `annotations.json` as a workaround, but this is minimal compared to Langfuse's evaluation framework, Phoenix's annotation system, or Opik's experiment scorer. If the project later needs systematic human evaluation of agent outputs or LLM-as-judge scoring, the Custom Dash plan provides no foundation to build on.

#### Key Risk

The trace data model improvements are shallow. The plan adds optional fields to `TurnRecord` but does not restructure the logging to capture nested LLM calls within a turn, retry attempts, or the growing conversation context sent to the LLM at each turn. This means even with the dashboard fully built, the deepest analysis questions ("why did the agent make 3 internal LLM calls on turn 5?" or "what was the total token cost of the retry sequence on turn 7?") remain unanswerable. The dashboard visualizes what exists; it does not create what is missing.

---

## 3. Comparative Matrix

| Criterion (Weight) | Langfuse | Phoenix | Opik | Custom Dash |
|---------------------|----------|---------|------|-------------|
| Trace Completeness (25%) | **9** | 8 | 8 | 5 |
| Visualization and UX (20%) | 8 | 7 | 7 | **9** |
| Integration Cost (20%) | 6 | 5 | 4 | **7** |
| Deployment Feasibility (20%) | 3 | **8** | 2 | **10** |
| Maintenance and Ecosystem (10%) | **8** | 6 | 5 | 5 |
| Extensibility (5%) | **8** | 7 | 7 | 6 |
| **Weighted Total** | **6.85** | **6.95** | **5.45** | **7.25** |

**Ranking: Custom Dash (7.25) > Phoenix (6.95) > Langfuse (6.85) > Opik (5.45)**

---

## 4. Head-to-Head Trade-offs

### 4.1 Custom Dash vs. Phoenix (the top two candidates)

This is the central decision, and it comes down to a fundamental trade-off: **visualization completeness now vs. trace data completeness now**.

**What Custom Dash gives that Phoenix does not:**
- Native click-through from metrics bar charts to trace drill-down, in a single application with Dash callbacks. Phoenix requires a sidecar file mapping run_id to trace_id and URL construction in the visualization CLI.
- Native side-by-side trace comparison as a built-in tab with synchronized turn accordions and a diff summary card. Phoenix defers this to a separate `compare_traces.py` script estimated at 1.5 additional days, described as "optional."
- Perfect HPC deployment with zero infrastructure risk -- no long-running server process to crash, no submit-node dependency.
- Lower initial effort (7-9 days vs. 10-12 days) and fewer files modified.

**What Phoenix gives that Custom Dash does not:**
- A true nested span hierarchy following OpenTelemetry standards. Each turn can contain multiple LLM calls, tool executions, and state inspections as proper child spans with their own timing, attributes, and error status. Custom Dash's enriched `TurnRecord` adds flat fields (`code_cells`, `code_outputs`) but not a recursive span tree. This is not a minor difference -- it determines whether the project can answer "what happened inside this turn?" at the granularity needed for model comparison research.
- Token counting and cost tracking wired into the instrumentation layer at the point of the LLM call, not retrofitted onto the logging output after the fact. Phoenix's OTel spans carry `llm.token_count.prompt` and `llm.token_count.completion` as semantic attributes set by the tracer at creation time; Custom Dash relies on extracting these from provider-specific response formats in `logger.py`, which is more fragile and less complete.
- A maintained, evolving GUI that receives new features (annotations, UMAP embedding visualization, experiment evaluation) without developer effort. Custom Dash requires building and maintaining every UI component indefinitely.
- Standards-based instrumentation (OTel + OpenInference) that can be redirected to any compatible backend in the future. Custom Dash's logging enrichments are bespoke and non-portable.

**The uncomfortable truth:** Custom Dash scores highest in the weighted total because the deployment feasibility criterion heavily penalizes Phoenix for requiring a persistent server process, and because Custom Dash's visualization UX is genuinely superior for the specific requirements stated. But Custom Dash's trace completeness score (5/10) reflects a real gap: it does not solve the core problem of capturing what happens inside a turn. It makes the existing data look better; it does not make the existing data richer. The question is whether the project's primary bottleneck today is "we cannot see our data well enough" or "our data does not contain what we need." The research report strongly argues for the latter.

### 4.2 Phoenix vs. Langfuse (the platform choice)

If the developer had access to a persistent machine with Docker Compose, Langfuse would score approximately 7.65 (moving Deployment Feasibility from 3 to 8). The infrastructure gap is the primary reason Langfuse loses to Phoenix. In every other criterion, Langfuse is equal to or better than Phoenix: richer data model (10 observation types vs. 10 span kinds, but Langfuse's generation type is more purpose-built for LLM calls), larger community (22.6k vs. 8.7k GitHub stars), MIT license (vs. ELv2), and more mature documentation.

Phoenix wins the platform comparison solely because of `pip install` + SQLite. This is a decisive advantage for this specific environment. The OTel-native architecture is a bonus that provides a future migration path: the instrumentation work done for Phoenix is not wasted if Langfuse deployment becomes feasible later, since Langfuse v3 supports OTLP ingestion natively.

### 4.3 Opik: why it falls short

Opik combines the worst combination for this environment: the heaviest infrastructure requirements (8 containers, even more than Langfuse's 6) paired with the youngest, least battle-tested ecosystem. Its unique strengths (Agent Optimizer, experiment leaderboard) are forward-looking features that do not address the immediate priorities identified in the research report. The plan's own recommendation to use Opik Cloud in Phase 1 is an honest concession that self-hosted deployment is not viable, but it transforms the choice from "which tracing platform?" to "which SaaS vendor?" -- a different question with different trade-offs that the plan does not fully explore.

---

## 5. Recommendation

**The winning framework is Arize Phoenix**, despite Custom Dash scoring marginally higher in the weighted total.

The weighted scores are close (7.25 vs. 6.95), and the 0.3-point gap is driven almost entirely by Custom Dash's perfect deployment feasibility score. But the purpose of this work, as stated in the research report, is to close critical gaps in trace data capture -- token counts, cost tracking, nested span hierarchy, structured tool calls. Custom Dash addresses the visualization half of the problem but leaves the trace capture half largely unsolved. Phoenix addresses both halves: it provides a proper nested span hierarchy via OpenTelemetry, structured token/cost tracking at the instrumentation layer, and a functional (if not custom-tailored) GUI for exploring the enriched traces. Its deployment model (`pip install` + SQLite + a `screen` session on a submit node) is realistic for this HPC environment and follows patterns already established in the project. The OTel-native instrumentation ensures that the development work is not wasted if the project later migrates to a different backend -- the spans are portable.

Custom Dash is the right choice if the team's primary need is visualization of existing data. Phoenix is the right choice if the team's primary need is capturing richer data and then visualizing it. The research report makes a strong case for the latter.

---

## 6. Suggested Amendments to the Winning Plan

### Amendment 1: Split into Phase 1 / Phase 2 to reduce the initial commitment (addresses the 10-12 day estimate)

The Phoenix plan's effort estimate is the highest of any option because it bundles essential and optional work without differentiation. Split into two phases:

**Phase 1 (5-6 days):** Core tracing only. Implement `tracing.py`, instrument `runner.py` and `client.py`, add `TracingConfig` to `config.py`, create `phoenix_server.sh`, and update `exec_apptainer_harmonia.sh`. Enrich `logger.py` with structured code execution extraction and token count fields (borrowing from the Custom Dash plan's `extract_code_spans()` design). At the end of Phase 1, experiments produce OTel spans visible in the Phoenix UI with nested turn/LLM/tool hierarchy and token counts. The existing `trace.json` continues to be written, now enriched with the new fields. No modifications to `visualize_metrics_cli.py` or the log analysis CLI.

**Phase 2 (4-5 days, deferred until Phase 1 is validated):** Visualization integration. Add trace links to `visualize_metrics_cli.py`, build `compare_traces.py` for side-by-side comparison, add `--phoenix` enrichment to the log analysis CLI, and export `spans.parquet` sidecars. Phase 2 should only begin after Phase 1 has been used in at least one full experiment batch and the team has confirmed that the Phoenix server is stable on the submit node and that the span data is useful.

This reduces the commitment risk: if Phoenix proves unsuitable after Phase 1, only 5-6 days are invested, and the `trace.json` enrichments (code extraction, token fields) remain valuable regardless.

### Amendment 2: Adopt the Custom Dash plan's click-through and side-by-side design for Phase 3

The Custom Dash plan's most compelling contribution is its visualization architecture: native Plotly `clickData` callbacks for metrics-to-trace navigation, two-column synchronized turn accordions for comparison, AG Grid for run overview tables. Instead of building the standalone `compare_traces.py` CLI proposed in the Phoenix plan, build a lightweight Dash app that reads from Phoenix's SQLite database via `phoenix.Client().get_spans_dataframe()`. This combines Phoenix's rich span data with Custom Dash's superior visualization design:

- Click-through from accuracy bar charts to Phoenix trace detail URLs using the `customdata` + `on_click` callback pattern.
- Side-by-side comparison with synchronized turn accordions backed by Phoenix spans (showing nested LLM calls and tool executions, not just flat turns).
- Token/cost summary columns in the run overview table populated from span aggregates.

This would be a Phase 3 addition (estimated 3-4 days), after Phases 1 and 2 are complete. It is less effort than the Custom Dash plan's full 7 days because the data loading layer queries Phoenix's DataFrame API instead of parsing raw JSON files, and the span data is already structured.

### Amendment 3: Enrich local trace.json independently of Phoenix (the "no-regrets" move)

The Phoenix plan modifies `logger.py` to add `input_tokens`, `output_tokens`, `cost_usd`, and `code_executions` fields to `TurnRecord`, but frames these changes as part of the Phoenix integration. These enrichments should be implemented as a standalone improvement that works regardless of whether Phoenix tracing is enabled:

- Implement the `extract_code_spans()` helper (from the Custom Dash plan's `logger.py` design) as a Phase 1 deliverable, applied every time `log_turn()` is called.
- Add token count and cost fields to `TurnRecord` with defaults, populated from provider responses when available.
- Copy the experiment YAML config into the results directory as `config_snapshot.yaml` (the "Run-level experiment config" gap from the research report).
- Ensure all new fields have `None` or empty defaults so existing traces remain loadable without migration.

This amendment guarantees that even if Phoenix is later removed, the local trace format has been permanently improved. The `read_and_analyze_logs_and_traces_cli.py` can immediately benefit from structured code execution data and token counts without requiring a Phoenix server. It is the single highest-value, lowest-risk improvement that can be extracted from this entire evaluation.
