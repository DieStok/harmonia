I want you to investigate which version of bdi-kit is installed in this container. Check both the .def file and by spinning up the .sif file and printing some version information in it.

Here is the .def file: /hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia/harmonia_beaker_LLM_agent_environment_apptainer.def

Then, I want you to use the bdikit source code here:
/hpc/compgen/projects/llm_GEO_project/bdi-kit
to see what environment variables or other settings are used to define the LLM that is called for various schema-matching and value-matching methods. I then want you to update the config files here:
/hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia/experiments/experiment_1_harmonia_dou2020_gdc
to set these variables:
HARMONIA_LLM_FOR_INSTANCE_MATCHING
HARMONIA_LLM_FOR_NUMERIC_INSTANCE_MATCHING
HARMONIA_EMBEDDING_MODEL_FOR_INSTANCE_MATCHING
HARMONIA_LLM_FOR_SCHEMA_MATCHING
HARMONIA_LLM_FOR_MAGNETO_ZERO-SHOT_SCHEMA_MATCHING
HARMONIA_LLM_FOR_MAGNETO_FINE-TUNED_SCHEMA_MATCHING
which control, in turn:
the LLM that Harmonia uses in the value-matching method 'llm'
the LLM that Harmonia uses in the value-matching method 'llm_numeric'
the embedding model that Harmonia uses in the value-matching method 'embedding'
the LLM that Harmonia uses in the schema-matching method 'llm'
the LLM that Harmonia uses in the schema-matching method 'magneto_zs_llm' (which uses an LLM under the hood)
the LLM that Harmonia uses in the schema-matching method 'magneto_ft_llm' (which uses an LLM under the hood)

Please note that for schema matching the two-phase approach can also call methods that use an LLM. Make sure that this works. 

Finally, this should all be made to work correctly with the experiment initialization done from /hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia/exec_apptainer_harmonia.sh. Hence, you should investigate how environment variables are used and passed there, and make sure that these variables are also printed and logged. 