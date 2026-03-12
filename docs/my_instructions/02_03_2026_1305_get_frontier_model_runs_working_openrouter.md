
Hi,

I have edited /hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia/.env with a new Openrouter API key. I would like you to make new manual and automatic experimental configs for the following openrouter models:
minimax/minimax-m2.5 ; 196,608 context
google/gemini-3-flash-preview ; 1,048,576 context
deepseek/deepseek-v3.2 ; 164k context
moonshotai/kimi-k2.5 ; 262K context
anthropic/claude-sonnet-4.6 ; 1M context
And update all older configs to have the proper API key in their associated .env (if they are not local).

Then, there have been a cavalcade of errors but today I want us to focus on getting tangible results for at least the True code-only agent (CodeAct) and the bdi-tools using agent with 2 models: gemini-3-flash and claude-sonnet-4.6. Hence, We make the configs for those 4 scenarios, then make the sbatch scripts (they only need cpu) and then submit them, check the logs, and make sure they properly run and create outputs as expected. 

Issues to watch out for today:
it seems the LLMs inside the container still see way more in the results directory than they should. We need to investigate why this is. See the sample log output below. Could you write a small CLI that checks exactly how the folder the apptainer runs in gets mounted, what we want the LLM to see, and what it can actually see? 
any errors in the logs. Specifically openrouter responses that are unsuccesfull
other problems you can gather from the latest set of logs.

Please:
make a plan to update all configs with the proper API keys and add the new openrouter models.
include steps to read the logs and check for errors (use /hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia/code_development_tools_agents/monitoring_and_evaluation/types_of_log_and_trace_problems.yaml and the most recent batch of logs here: /hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia/logs to see what you should keep in mind for this)
include steps to work with me to make a visualisation script, based on what the succesfull LLM runs output. 

Now:
- think about what to do and read needed files
- discuss any specifics that you need with me
- after I give the okay, output the final plan in /hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia/docs/plans as DATETIME_make_frontier_models_work.md with enough detail for a fresh claude instance to implement it. 
- then report back to me and wait. 