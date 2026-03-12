/hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia/docs/plans/11_02_2026_1450_plan_to_make_prompts_changeable.md read this plan and perform feasibility analysis.

What should happen is that I will make different versions of prompts, and want to be able to compose them. For instance, in /hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia/experiments/experiment_1_harmonia_dou2020_gdc/configs I could make a prompts folder, where I have system_prompt, bdikit_prompts, and react_agent_prompts subfolders, with subfolders with different configurations for each. the .yaml config files in /hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia/experiments/experiment_1_harmonia_dou2020_gdc/configs/automated should then have explicit mappings to all the required prompts. Note that the code-only agent doesn't need bdikit-prompts as such.

Now perform a thorough and full feasibility analysis:
- check all prompts
- check how prompts are initialized
- run test containers where you intialize beaker and see how you can change the prompts
- do other tests to see what the best way to allow configurable prompts is.

I want you to be thorough, search through all code paths and signal possible conflicts or difficulties (perhaps Archytas overwrites certain things? Perhaps context management as a whole is now unwieldy and should be streamlined?)
I want you to also deploy a subagent that reflects in general on the instantiation of a (coding) agent and its tools inside beaker and whether it could be streamlined or improved somehow, taking notes from more mature agent orchestration platforms, even simple implementations such as smollagents.

After feasibility analysis, thorough testing of possible implementation methods, comparing and contrasting of different ways to implement this, and comments on the strcuture of agent initialization in general, write a full report and append it to 
/hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia/docs/plans/11_02_2026_1450_plan_to_make_prompts_changeable.md
at the end of the file. 

Now first ask me any clarifying questions that are needed, then go off and work autonomously. 


Questions:

User has answered your questions: "Should the code_context (code-only agent) also support configurable prompts via YAML, or just BDIKit context and ReAct agent prompts? You mentioned code-only doesn't need bdikit-prompts, but should it have its own configurable system prompt?"="Yes, configurable", "For prompt composition, do you want the YAML to reference prompt file paths (relative to a prompts folder), inline prompt text, or both?"="File paths only (Recommended)", "For the Archytas/Beaker reflection subagent: should it research and compare against specific frameworks (e.g., smolagents, LangGraph, CrewAI), or is a general architectural critique sufficient?"="Both", "Should I actually run test containers (srun with Apptainer) to test prompt injection points, or is static code analysis sufficient? Running containers requires HPC resources and time."="You need to do extensive testing in an apptainer test container that is running. The routing is circuitous and so you should test in the container. Be sure to do root cause analysis and identify all layers where the prompts pass through the combined framework of Beaker so you have clear actionable information on how to do all this. Don't skimp on test scenarios of all sorts and logging of those tests. ". You can now continue with the user's answers in mind.

Note: if you need 