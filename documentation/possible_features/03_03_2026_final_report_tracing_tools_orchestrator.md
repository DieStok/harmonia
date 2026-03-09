# Final Report: LLM Tracing and Observability for Harmonia

**Date**: 2026-03-03
**Author**: Claude Code (orchestrator)
**Status**: Final recommendation

---

## Recommendation

**Winner: Arize Phoenix**

Phoenix is the recommended framework for adding LLM tracing and observability to Harmonia. It is the only platform framework that can deploy on this HPC cluster without Docker infrastructure -- a single `pip install arize-phoenix` and a `phoenix serve` process in a `screen` session on a submit node, backed by SQLite. It provides a proper nested span hierarchy via OpenTelemetry (Turn > LLM call > Tool use > Code execution), structured token and cost tracking at the instrumentation layer, and a functional web UI for trace exploration. Its OTel-native architecture ensures the instrumentation work is portable: if Langfuse deployment becomes feasible in the future (e.g., via a department Docker host), the spans can be redirected to a Langfuse OTLP endpoint with a one-line configuration change.

The critic evaluation scored Custom Dash marginally higher (7.25 vs. 6.95) due to its perfect HPC deployment score and superior visualization UX. However, the primary motivation for this work -- as established in the research report -- is closing critical trace capture gaps (token counts, cost tracking, nested spans, structured tool calls), not making existing data look better. Custom Dash solves the visualization half but leaves trace capture largely unchanged. Phoenix solves both halves.

---

## Critic's Top 3 Suggested Amendments to the Phoenix Plan

### 1. Phase the work to reduce commitment risk

Split the 10-12 day estimate into Phase 1 (core tracing, 5-6 days) and Phase 2 (visualization integration, 4-5 days). Phase 1 delivers OTel spans in the Phoenix UI with nested hierarchy and token counts. Phase 2 adds metrics click-through, side-by-side comparison, and log analysis CLI enrichment. Only begin Phase 2 after Phase 1 has been validated in a real experiment batch. This caps the downside at 5-6 days if Phoenix proves unsuitable.

### 2. Adopt Custom Dash's visualization design as a future Phase 3

Build a lightweight Dash app (3-4 days) that reads Phoenix's span data via `get_spans_dataframe()` and provides: native Plotly click-through from accuracy bar charts to trace detail, synchronized side-by-side turn comparison backed by Phoenix spans, and token/cost summary columns. This combines Phoenix's rich data model with Custom Dash's superior visualization patterns.

### 3. Enrich local trace.json independently of Phoenix ("no-regrets" improvement)

Implement structured code execution extraction (`extract_code_spans()`) and token/cost fields on `TurnRecord` as a standalone `logger.py` improvement that works regardless of Phoenix. Copy the experiment YAML config into results directories. These changes permanently improve the local trace format and benefit the existing failure-mode CLI immediately. This is the single highest-value, lowest-risk improvement from the entire evaluation.

---

## Scoring Summary

| Framework | Trace Completeness (25%) | Visualization UX (20%) | Integration Cost (20%) | Deployment Feasibility (20%) | Maintenance (10%) | Extensibility (5%) | **Total** |
|-----------|--------------------------|------------------------|------------------------|------------------------------|--------------------|--------------------|-----------|
| Custom Dash | 5 | **9** | **7** | **10** | 5 | 6 | **7.25** |
| **Phoenix** | 8 | 7 | 5 | 8 | 6 | 7 | **6.95** |
| Langfuse | **9** | 8 | 6 | 3 | **8** | **8** | **6.85** |
| Opik | 8 | 7 | 4 | 2 | 5 | 7 | **5.45** |

Phoenix wins on the decisive constraint: it is the only platform that addresses both trace capture and visualization while running on the HPC cluster. Langfuse would score ~7.65 if a Docker host were available. Custom Dash is the right choice if the priority is visualization alone.

---

## Generated Documents

All documents are in `documentation/possible_features/`:

| Document | Description |
|----------|-------------|
| [`03_03_2026_research_into_LLM_tracing.md`](03_03_2026_research_into_LLM_tracing.md) | Research report: current logging analysis, desiderata, framework landscape comparison |
| [`langfuse_improve_tracing_plan.md`](langfuse_improve_tracing_plan.md) | Implementation plan: Langfuse integration (6 dev-days, 13 files, external Docker host) |
| [`phoenix_improve_tracing_plan.md`](phoenix_improve_tracing_plan.md) | Implementation plan: Arize Phoenix integration (10-12 dev-days, 13 files, pip + SQLite) |
| [`opik_improve_tracing_plan.md`](opik_improve_tracing_plan.md) | Implementation plan: Opik integration (12 dev-days, 12 files, 8-container Docker stack) |
| [`custom_dash_improve_tracing_plan.md`](custom_dash_improve_tracing_plan.md) | Implementation plan: Custom Dash dashboard (7-9 dev-days, visualization only, zero infrastructure) |
| [`03_03_2026_critic_evaluation.md`](03_03_2026_critic_evaluation.md) | Critic evaluation: weighted scoring, head-to-head trade-offs, recommendation, amendments |
| [`03_03_2026_final_report_tracing_tools_orchestrator.md`](03_03_2026_final_report_tracing_tools_orchestrator.md) | This document: final recommendation and summary |
