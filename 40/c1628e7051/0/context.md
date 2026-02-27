# Session Context

## User Prompts

### Prompt 1

please investigate how to rebuild the harmonia container using the local versions of archytas and beaker-kernel: /hpc/compgen/projects/llm_GEO_project/beaker-kernel and /hpc/compgen/projects/llm_GEO_project/archytas and /hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia/build_harmonia_apptainer.sh

Tell me the commands you will run and what you need to change in the .def etc.

### Prompt 2

MAke the edits, rebuild the container, and make sure it completes

### Prompt 3

Can you check whether there are any relevant lines in the latest 'how this codebase works' files, and add 1 sentence describing how the new container generation depends on local (changed) versions of Archytas and beaker-kernel.

Then, I would like to make my own fork of Archytas and beaker-kernel on Github and make our local changes in /hpc/compgen/projects/llm_GEO_project/archytas and /hpc/compgen/projects/llm_GEO_project/beaker-kernel commit and push to that. Can you tell me how to do that?

### Prompt 4

can you perform the commands in step 2 and 3? The forks are at:
https://github.com/DieStok/beaker-kernel.git
https://github.com/DieStok/archytas.git

### Prompt 5

I am pushing things sucessfully through the VSCode Github interface, so why is this not working while that is? Perhaps I can do it through the GUI instead?

### Prompt 6

it says 'you don't have permissions to push to DieStok/beaker-kernel'. Strange...Why?

### Prompt 7

[Request interrupted by user]

### Prompt 8

Ah, yes, change it back to https.

### Prompt 9

And how do I make sure I always (sync&)push to myforks there?

