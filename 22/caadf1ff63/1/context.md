# Session Context

## User Prompts

### Prompt 1

Please investigate all logs (excluding those in the 'older' folder), focussing on the errors. What is going wrong for each run? I do not get the results I expect. 

See this path: /hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia/logs

You can refer to the types of errors here /hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia/code_development_tools_agents/monitoring_and_evaluation/types_of_log_and_trace_problems.yaml, al...

### Prompt 2

Change all configs to increase MAX_WAIT. Check the trace and report the fix to me. Remove the devstrall-small.

### Prompt 3

why was devstrall-small.yaml deleted? It uses local devstrall-small. Check this thoroughly.

### Prompt 4

Yes, remove it. Then commit the changes with a clear message and stop.

### Prompt 5

[Request interrupted by user for tool use]

### Prompt 6

wait why is there still a pony-alpha? I thought this was removed as thas was stealth GLM5. Are you sure you did not overwrite newer configs?

### Prompt 7

Yes. And then commit all changes. Thanks and sorry for my faulty assumption on your part.

### Prompt 8

Can you now run 3 experiments:

/hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia/experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_devstral-small.yaml
/hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia/experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_devstral.yaml
/hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia/experi...

### Prompt 9

[Request interrupted by user]

### Prompt 10

Before doing that, please first move all folders in results to the old subfolder, and all logs in logs to the older subfolder. Then run these 3 automated experiments.

### Prompt 11

Explain what is happening in these two:
/hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia/logs/dou_harmonization_devstral_47314514_ollama.log

REDACTED.log

### Prompt 12

They are separate jobs, and each gets a certain amount of memory on the GPU. Why wouldn't this work?

### Prompt 13

[Request interrupted by user]

### Prompt 14

One node can also have multiple GPUs, and each GPU has more than 2*VRAM_requested memory, hence my question.

### Prompt 15

Yes, and request more GPU memory as well. ALso tell me why I don't see the output of estimate_vram_usage from exec_apptainer_harmonia.sh in the log. That would be useful.

