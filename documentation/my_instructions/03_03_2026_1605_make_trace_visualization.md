In this project, I want to analyze the performance of different LLMs for metadata harmonisation. We have instantiated the current codebase for this, which can use experiment configs and ground-truth metadata tables to launch apptainer images, in which an LLM agent (running in a beaker kernel with Archytas for the agent part) can generate code, (optionally) use bdikit-tools, and do the analysis. We have both automated and manual experiment configs, where the automated configs use a set script, and the manual configs start an interactive beaker server that I can connect to.

The codebase has extensive logging, chiefly through /hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia/src/automation/logger.py and /hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia/src/prompt_logging.py

I have visualisation tools in /hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia/src/evaluation/visualize_metrics_cli.py. 

The results folder of each run looks something like this /hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia/results/dou_harmonization_code-context_gemini-3-flash-preview_20260302_170745_58fa9479
Here, the conversational parts (what the LLM sees as combined prompts, the conversation turns, and a top-level summary of the final LLM responses) are saved in full_prompt_composition.json; trace.json, and conversation.md. 

To query these traces and categorize what happened we have these files:
/hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia/code_development_tools_agents/monitoring_and_evaluation/read_and_analyze_logs_and_traces_cli.py
/hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia/code_development_tools_agents/monitoring_and_evaluation/types_of_log_and_trace_problems.yaml

Now that runs are succesful, I can make visualisations and compare perfomances, such as in /hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia/analysis/plots_latest_successful_20260302_1843.

However, these plots alone don't tell the full story, I need to be able to easily cross-reference these with the traces of the conversation, and also anyway be able to step through conversation traces, perhaps comparing them side-by-side for different models. I want to make a GUI that allows me to easily do this. 

As a first step, I want to brainstorm about the possible options here. LLM observeability frameworks like langfuse/langchain and many more already exist, as, probably, do open source tools. For making a sort of interactive dashboard, where I can interact with both the performance metrics/plots of the run and click through to compare traces (and see what went wrong or not, etc.) I want ideas. The easiest idea would perhaps be Dash or a Streamlit app, but I don't know what else is out there.

I want you to dive into these separate topics:

- Before beginning any analysis, read the following files into context to ground your findings in the actual codebase: automation/logger.py, prompt_logging.py, an example trace.json from a completed results directory, an example full_prompt_composition.json, and the document at documentation/my_instructions/initial_info_LLM_tracing.md. Do not speculate about file contents — inspect them first.

- Analyze exactly what is logged in the LLM turns now in the codebase. How do these trace.json files look, do they correctly contain everything, are any interactions not logged and what is missing or could be improved? The final answer to this should be a clear list of Current Functionality with what is present, and Desiderata of what would serve to optimally give context to my experiments.

- Analyze the landscape of LLM agent observeability: what open source packages exist, what out-of-the-box solutions are there for GUIs or visualisations to compare multi-turn LLM conversations. Here investigate at least langchain, langfuse, Arize Phoenix and Opik. For initial research, see file: /hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia/documentation/my_instructions/initial_info_LLM_tracing.md

- Given the above findings of what is currently implemented, important desiderata, and what each of the frameworks does, make a full report in documentation/possible_features/<DATETIME>_research_into_LLM_tracing.md. The report must contain three sections: (1) Current Logging — what is captured and what is missing, with references to the actual source files and example outputs you inspected; (2) Desiderata — what an ideal tracing and visualisation system would provide for this project; (3) Framework Landscape — a structured comparison of the candidate frameworks against those desiderata. This report will be the primary input for all subagents, so it must be self-contained.

- Dispatch 4 subagents, one per candidate framework. Three are pinned: Langfuse, Arize Phoenix, and Opik. Select one additional framework based on the research report findings (e.g., a custom Dash/Streamlit approach, or another promising candidate that emerged from the landscape analysis). Each subagent must run in its own independent context so that findings do not bleed between them. Each subagent receives the same structured brief below, with only the framework name swapped. Each subagent outputs its plan to:
  documentation/possible_features/<SUBAGENT_ID>_<FRAMEWORKNAME>_improve_tracing_plan.md

  <subagent_brief>
  You are writing a detailed implementation plan for integrating **{FRAMEWORK_NAME}** into the Harmonia codebase to provide comprehensive LLM agent tracing and observability.

  <project_context>
  Harmonia benchmarks LLMs on a metadata harmonisation task. An orchestrator launches containerised LLM agents (Archytas/Beaker inside Apptainer) that generate and execute code to harmonise biomedical metadata tables. The codebase already produces per-run artifacts: trace.json (conversation turns), full_prompt_composition.json (assembled prompts), and conversation.md (human-readable summary). Existing logging lives in automation/logger.py and prompt_logging.py. Quantitative evaluation metrics and plots are generated by evaluation/visualize_metrics_cli.py. The system runs on an HPC cluster; containers have limited network access and no guaranteed persistent services.
  </project_context>

  <input_files>
  You will be provided with:
  1. The research report (documentation/possible_features/<DATETIME>_research_into_LLM_tracing.md) — read this first for full context on current logging, desiderata, and framework landscape.
  2. The current logging source files: automation/logger.py, prompt_logging.py, and the trace analysis tooling in code_development_tools_agents/monitoring_and_evaluation/.
  3. An example results directory showing the structure of trace.json, full_prompt_composition.json, and conversation.md.
  </input_files>

  Your plan must cover ALL of the following sections in order. Be concrete and specific throughout — name files, functions, classes, and parameters. Do not hand-wave.

  <section_1_framework_capabilities>
  ### 1. Framework Functionality Mapping
  For {FRAMEWORK_NAME}, detail:
  - Which framework components handle trace capture (spans, events, generations, etc.) and what data model they use.
  - Which components provide the GUI / visualisation layer, and what views they offer out of the box (single-trace drill-down, multi-trace comparison, filtering, search).
  - What the data persistence story is (local SQLite, Postgres, cloud-hosted, file-based export) and how it maps to HPC/Apptainer constraints.
  - What SDK/API integration points exist for Python, and whether they support manual instrumentation (not just auto-patching of known LLM libraries) — this is critical since Harmonia uses Archytas, not a mainstream LLM framework.
  </section_1_framework_capabilities>

  <section_2_codebase_changes>
  ### 2. Codebase Integration — Complete Change Specification
  Provide a file-by-file breakdown of every code path that would change or be added. For each file:
  - **File path** (full path from project root)
  - **What changes**: new file, modified file, or deleted file
  - **Function/class signatures affected**: list each function or class that is added, modified, or wrapped, with its signature
  - **Nature of change**: e.g., "wrap existing call in a trace span", "add decorator", "replace logger.info with framework.log_generation", "new adapter class"
  - **Dependencies introduced**: any new pip packages, config files, or environment variables

  Group changes into:
  (a) **Core tracing instrumentation** — changes to capture LLM turns, tool calls, code execution, errors
  (b) **Data export / persistence** — how traces are stored and made available to the GUI
  (c) **Configuration and setup** — new config entries, Apptainer definition changes, startup scripts

  Be exhaustive. If a code path is not listed here, assume it will not be changed during implementation.
  </section_2_codebase_changes>

  <section_3_visualisation_integration>
  ### 3. Visualisation and Cross-Referencing with Metrics
  Specify exactly how the tracing GUI would be combined with the existing quantitative performance plots in a single interactive experience. Address:
  - **Unified dashboard architecture**: what serves the UI (framework's built-in server, Dash, Streamlit, or other), and how the trace viewer and metric plots coexist (embedded iframes, shared app, linked views, etc.).
  - **Click-through from metrics to traces**: how a user looking at a bar chart of model accuracy can click on a specific run and land in the corresponding trace view.
  - **Side-by-side trace comparison**: how a user can select 2+ runs (e.g., different models on the same task) and view their conversation traces in parallel, with aligned turns.
  - **Deployment of the GUI**: how it is launched (local server, static export, notebook widget), port requirements, and compatibility with the HPC environment.
  </section_3_visualisation_integration>

  <section_4_effort_and_risks>
  ### 4. Effort Estimate and Risks
  - Estimated implementation effort in developer-days, broken down by the three change groups in Section 2.
  - Top 3 technical risks and a concrete mitigation for each.
  - Any limitations of {FRAMEWORK_NAME} that would require custom workarounds, and what those workarounds look like.
  </section_4_effort_and_risks>

  Write the plan in markdown. Aim for 1500–2500 words; do not exceed 3500.
  </subagent_brief>

- After all 4 subagent plans are complete, dispatch a critic subagent in its own independent context. Provide it with all 4 plan files and the research report. The critic should compare all plans, score them on the evaluation criteria below, and output a single recommendation with suggested amendments. Save its output to:
  documentation/possible_features/<DATETIME>_critic_evaluation.md

  Use the following as the system prompt for the critic subagent:

  <critic_system_prompt>
  You are a senior technical reviewer acting as an independent critic. Your job is to compare competing implementation plans for adding LLM agent observability and tracing to an existing Python codebase, then select the single best option. You will receive 4 detailed plans — one per candidate framework — each written by a separate subagent. You have no loyalty to any plan; your only goal is to surface the option that best serves the project's needs.

  <evaluation_context>
  The project ("Harmonia") benchmarks different LLMs on a metadata harmonisation task. An orchestrator launches containerised LLM agents (via Archytas/Beaker inside Apptainer) that write and execute code to harmonise biomedical metadata tables. The codebase already has custom logging (automation/logger.py, prompt_logging.py) producing trace.json, full_prompt_composition.json, and conversation.md per run. The team now needs:

  1. Rich, structured tracing of every LLM turn (prompts, completions, tool calls, code execution, errors, latencies, token counts).
  2. An interactive GUI where traces can be explored turn-by-turn, compared side-by-side across models, and cross-referenced with quantitative performance metrics/plots already produced by the evaluation pipeline.
  3. Minimal disruption to the existing automation and logging code — the solution must integrate cleanly.
  4. The system runs on an HPC cluster inside Apptainer containers; network access, persistence, and deployment constraints matter.
  </evaluation_context>

  <evaluation_criteria>
  Evaluate each plan along ALL of the following dimensions. Weight them in this order of importance:

  1. **Trace completeness** — Does the plan capture every interaction (system prompt composition, each LLM turn with full prompt + response, tool/function calls and results, code execution outputs, errors and retries, token usage, latencies)? Are there gaps?
  2. **Visualisation and comparison UX** — How well does the proposed GUI support (a) stepping through a single trace turn-by-turn, (b) side-by-side comparison of traces from different models on the same task, and (c) cross-referencing traces with quantitative metric plots?
  3. **Integration cost** — How many existing code paths change? How invasive are the changes? Is the mapping of current logging to the new framework's data model clean or forced?
  4. **Deployment feasibility** — Can it run on an HPC cluster inside Apptainer? Does it need a persistent server, external database, or network access that may not be available? How complex is setup?
  5. **Maintenance and ecosystem** — Is the framework actively maintained? Is the community large enough for long-term support? Are there lock-in risks?
  6. **Extensibility** — How easy is it to add new trace fields, custom metadata, or new visualisation views later?
  </evaluation_criteria>

  <output_format>
  Structure your response exactly as follows:

  ### Per-Plan Analysis
  For each of the 4 plans, produce a section with:
  - **Framework**: name
  - **Summary**: 2–3 sentence distillation of the plan's approach
  - **Strengths**: bulleted list, each item no more than 2 sentences, referencing specific evaluation criteria
  - **Weaknesses**: bulleted list, same format, being concrete about what is missing or risky
  - **Open questions**: anything the plan left unresolved or underspecified

  ### Comparative Matrix
  A markdown table with frameworks as rows and the 6 evaluation criteria as columns. Use a 1–5 score per cell with a one-word qualifier (e.g., "4 — strong").

  ### Head-to-Head Trade-offs
  Identify the 2–3 most consequential trade-offs between the top candidates. For each, explain what you gain and what you lose concretely.

  ### Recommendation
  State your single recommended framework. Justify the choice by referencing the comparative matrix and the most important trade-offs. If appropriate, note whether a hybrid approach (e.g., framework X for tracing + framework Y's UI component) would outperform any single option, but only if genuinely warranted — do not hedge for the sake of hedging.

  ### Suggested Amendments
  List up to 5 specific, actionable improvements to the winning plan that would address its identified weaknesses. Reference concrete code paths or integration points where possible.
  </output_format>

  <guidelines>
  - Be direct and opinionated. The orchestrator needs a clear decision, not a balanced "they're all good" summary.
  - Ground every claim in specifics from the plans. Do not introduce framework features that are not mentioned in the plans unless you flag them explicitly as "not covered in plan, but worth noting."
  - If a plan is vague or hand-wavy on a criterion, penalise it — specificity is a signal of quality.
  - Consider second-order effects: e.g., a framework that is easy to set up but hard to customise may score well on integration cost but poorly on extensibility.
  - Keep the total response under 3500 words. Conciseness is valued.
  </guidelines>
  </critic_system_prompt>

  Give the critic this user prompt, with the plan contents and research report filled in:

  Below are 4 implementation plans for adding LLM observability and tracing to the Harmonia metadata harmonisation benchmarking project. Each plan was produced by an independent subagent that investigated a specific framework. Evaluate and compare them according to your instructions, then select the best option.

  <plan_1>
  {content of subagent 1 plan}
  </plan_1>

  <plan_2>
  {content of subagent 2 plan}
  </plan_2>

  <plan_3>
  {content of subagent 3 plan}
  </plan_3>

  <plan_4>
  {content of subagent 4 plan}
  </plan_4>

  <research_report>
  {content of the research report}
  </research_report>

  Now perform your evaluation.

- After the critic completes, surface its output to me as the final response. The final output must contain: (a) the winning framework name, (b) a 3–5 sentence justification, (c) the critic's top 3 suggested amendments to the winning plan, and (d) links to all generated documents (the research report, the 4 subagent plans, and the critic evaluation).