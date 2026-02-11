In the current codebase, exec_apptainer_harmonia.sh does not start another ollama server if one is already running on the node. 
However, I want every job to be self-contained: it should have its own ollama instance with its own model loaded, and be a separate experiment. If experiments start sharing ollama instances then that could lead to memory issues and slow-downs that influence comparisons.

Hence:
- analyze the codebase (start with /hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia/documentation/codebase_descriptions/how_this_codebase_works_10_02_2026.md and /hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia/exec_apptainer_harmonia.sh)
- think about how to make sure separate jobs/srun commands start separate ollama instances, and the correct port is listened to. To do this:
- make sure to check all files where $PORT or PORT or port is used (or ollama is used) and to understand what calls what.
- output this hierarchy in a way that is clear
- make a proposed implementation plan to make sure there are separate ollama instances for each job/srun and that each experiment can run separately.
NOTE: please double-check that this functionalty is not already present! I believe there is already some functionality to randomize ports based on job id. Where is this and how does it work?
Relay your findings to me.