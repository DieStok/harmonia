Given these two code files /hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia/src/evaluation/metrics.py
  /hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia/src/evaluation/schemas.py and the results, can you discuss with me an in-depth plan to make a script that
   is a command-line visualization tool. It should make complete visualizations and side-by-side comparisons of the performance of different experiments. First let's make the visualizations that 
  work for one table - one schema matching. There will be global column matching scores, then by-column value-matching scores and average value-matching scores. I want to make a comparison of how
   different models perform, optionally disambiguated by any config parameters. e.g. the context the model is operating in (codeact, bdikit-context, or true code-only), by model (e.g. gemini 3, 
  claude sonnet 4.6), or any other config parameters given to the runs. I might also want to collapse runs by model type (e.g. local versus frontier). In all, we need reusable plotting code to 
  make nice barplots, ideally with seaborn for now, and also to make confusion matrices, etc. with grouping logic. Could you read the results for gemini 3 in the two contexts for now, and then 
  assume that there may be more models and one more context, etc. Finally, I think for this single-table case it would be nice to have a sort of heatmap where rows are different models (with 
  different settings, or coloured labels next to it showing what is local/online, what is codeact/bdikit-context/code-context, etc.) and the columns correspond to the columns of the dataframe, 
  and each block is coloured by how good the performance is for that column for that model. For now make it the accuracy, but make the metric configurable (e.g. F1 if needed). After this CLI is 
  done I would also like to make an interactive notebook that uses these functions so I can explore and tinker with the plots more easily. Now discuss with me what would be needed for this 
  script, any comments or edge cases you see, etc.Th