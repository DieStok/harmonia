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

- analyze exactly what is logged in the LLM turns now in the codebase. How do these trace.json files look, do they correctly contain everything, are any interactions not logged and what is missing or could be improved? The final answer to this should be a clear list of Current Functionality with what is present, and Desiderata of what would serve to optimally give context to my experiments.
- analyze the landscape of LLM agent observeability: what open source packages exist, what out-of-the-box solutions are there for GUIs or visualisations to compare multi-turn LLM conversations. Here investigate at least langchain, langfuse, Arize Phoenix and Opik. For initial research, see file: /hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia/documentation/my_instructions/initial_info_LLM_tracing.md
- given the above findings of what is currently implemented, important desiderata, and what each of the frameworks does, make a full report in documentation/possible_features/<DATETIME>_research_into_LLM_tracing.md
- Dispatch 4 subagents, one per candidate framework identified as most promising in the research report. Each subagent runs in a fresh context and receives the same structured brief below, with only the framework name swapped. Each subagent outputs its plan to:
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

  Write the plan in markdown. Be thorough but not redundant — aim for 1500–3500 words.
  </subagent_brief>
- Finally, dispatch a critic agent in a fresh context. Provide it with all 4 subagent plan files
  and the research report as input. Use the system prompt defined in
  critic_agent_prompt.md. The critic agent should compare all plans, score them on
  the 6 evaluation criteria, and output a single recommendation with suggested
  amendments. Save its output to:
  documentation/possible_features/<DATETIME>_critic_evaluation.md
  Give it this user prompt, filled in properly:
  Below are 4 implementation plans for adding LLM observability and tracing to the Harmonia metadata harmonisation benchmarking project. Each plan was produced by an independent subagent that investigated a specific framework. Evaluate and compare them according to your instructions, then select the best option.

<plan_1>
{CONTENT OF SUBAGENT 1 PLAN}
</plan_1>

<plan_2>
{CONTENT OF SUBAGENT 2 PLAN}
</plan_2>

<plan_3>
{CONTENT OF SUBAGENT 3 PLAN}
</plan_3>

<plan_4>
{CONTENT OF SUBAGENT 4 PLAN}
</plan_4>

<research_report>
{CONTENT OF THE MAIN RESEARCH REPORT from documentation/possible_features/<DATETIME>_research_into_LLM_tracing.md — this gives the critic shared context on current logging, desiderata, and framework landscape}
</research_report>

Now perform your evaluation.

- Finally, Surface the critic's recommendation and top-3 amendments to the user as the
  final response.