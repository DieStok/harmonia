# Session Context

## User Prompts

### Prompt 1

Given the most recent run logs here:
/hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia/logs
And the tool here: /hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia/code_development_tools_agents/monitoring_and_evaluation/read_and_analyze_logs_and_traces_cli.py

Please categorize what went wrong and report back to me. I am interested in a bullet point list of the different types of errors, and also specifically a more in-dept...

### Prompt 2

Could you output this analysis into /hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia/documentation/miscellaneous/DATE_TIME_analysis_log_errors.md 

and then edit /hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia/code_development_tools_agents/monitoring_and_evaluation/types_of_log_and_trace_problems.yaml to make sure it captures the specific categories of errors you have mentioned here that are not yet in there

and then...

### Prompt 3

Before we move on: could you commit just the edited .yaml file and the analysis of errors.md file?

### Prompt 4

Could you write the background of how context is managed between the beaker kernel and archytas (i.e. what each does, how that influences the context, and where you can possibly intervene) into a separate markdown file here /hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia/documentation/possible_features. Call it DATETIMESTAMP_context_management_Archytas_beaker.md. Make it comprehensive and have all the relevant function signatures and how they are called, a...

### Prompt 5

1. I do not know. Just set both.
2. context length is already in the config.yamls, it just wasn't used properly. In the log of the run and stdout that exec_apptainer_harmonia.sh produces, can you include back-of-the-envelope calcualtions of memory needed to properly fit in memory, and if it is 20% less or more then give a clear WARNING
3. patch it in the apptainer build definition. Make sure to include clear comments on what this is doing and why it is needed
4. yes, let's do that. 
5. this is a...

