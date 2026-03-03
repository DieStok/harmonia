# Session Context

## User Prompts

### Prompt 1

Hi, I would like to generate a plan for implementing automatic data collection on available models on openrouter into config generation.

I would like the following steps:
make a CLI script that downloads all openrouter models to a file, with optional force-overwriting and otherwise only replacing it if it is older than a day by default. It should output in /hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia/LLM_associated_metadata. Something like openrouter_m...

### Prompt 2

[Request interrupted by user for tool use]

### Prompt 3

Stop web fetching. Enough. Maybe use something like this justfile: 
set positional-arguments := true

default:
  just --list

#list Ollama models
@models:
    curl -s https://ollama.com/library | grep -oP 'href="/library/\K[^"]+'

#list model tags
@tags model:
    curl -s https://ollama.com/library/$1/tags | grep -o "$1:[^\" ]*q[^\" ]*" | grep -E -v 'text|base|fp|q[45]_[01]'

Or maybe use something else. Use the information you have available and report back:

