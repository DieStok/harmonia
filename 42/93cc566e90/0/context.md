# Session Context

## User Prompts

### Prompt 1

Read the instructions here. Discuss with me what you plan to do and discuss edge cases, what my intentions are with the plan, or details you need. We will work interactively on this REDACTED.md

### Prompt 2

1. I am not sure. Investigate the code here: /hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia/src/bdikit_context
2. Correct.
3. do rename to underscores yes
4. The latest version of bdi-kit is 0.9. Before all else we need to update to the latest version. Could you check within a running container with the version is before we move on?
5. New top-level section. It is the LLM that Harmonia's AI agent internally uses, which is different from the LLM agent that...

### Prompt 3

[Request interrupted by user]

### Prompt 4

You can execute a container by doing srun, and then executing this to run the container: /hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia/exec_apptainer_harmonia.sh 
Do that, then continue.

### Prompt 5

Question 1:

We will implement the full plan so everything works as needed. Rebuilding is fine as part of the plan. Whatever can be executed in parallel while the container is rebuilding should do so.

Question 2:
Yes, check this. Internally it should call the appropriate LLM matchers, so if that goes well it should work. Still chec this.

Question 3: the LLM calls what it wants to call and it should work.

Question 4:
I guess pin to the v0.9 version for now.

Then an extra point from my side: I...

### Prompt 6

Here is the document text:

### Prompt 7

Your two-phase matcher approach seems valid. I agree with making the switch to liteLLM only a separate plan. 

So now I want you to:
- write the full plan for the update of bdikit and configuration of what LLMs bdi-kit uses, with details of what we discussed and context that is needed for a fresh Claude instance getting to work on this problem (i.e. very clear step-by-step instructions and files to change) to /hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia...

### Prompt 8

can plan 2 be executed in parallel or do we need to wait for the new container to be built etc.?

### Prompt 9

I want you to write me a message that I can paste into a Claude instance that is working on plan 1, that tells it to execute plan 2's code changes after plan 1's code changes are done, then rebuild the container once.

### Prompt 10

I think the update to bdikit, which now has different methods etc. necessitates updating the tool prompts that Archytas sees.
Specifically, could you analyze:
- how bdikit now organizes tools in the updated version (can check here /hpc/compgen/projects/llm_GEO_project/bdi-kit or read the plan for updating to check this)
- how that differs from the prompts in the folder

/hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia/src/bdikit_context/prompts

then discus...

### Prompt 11

Continue from where you left off.

### Prompt 12

hello.

### Prompt 13

I want you to continue with that, yes. Report back to me.

### Prompt 14

Could you repeat what you just said? it seems to not be properly saving.

### Prompt 15

[Request interrupted by user]

### Prompt 16

For 1. make it rank_schema_matches what the agent sees as well. Better to have no old-style stuff anywhere.

I want top keep the v1 v2 for now. I want you to indeed make all changes needed to get this to work, including bdikit main.j2, generate_env.py and the experiment configs where needed. Now write a full plan called DATETIME_update_tool_prompts_new_version_bdikit_and_add_prompt_files_codecontextagent_and_codeactagent.md in /hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysi...

### Prompt 17

Why keep this split, rather than showing the LLM the correct internals? if it decides to look at help or documentation it will get confusing error messages, right?

