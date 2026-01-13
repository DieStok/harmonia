#!/usr/bin/env python3
"""Check archytas configuration and OpenRouter support."""

import inspect

# Check archytas version
import archytas
print('archytas version:', getattr(archytas, '__version__', 'unknown'))
print('archytas location:', archytas.__file__)

# Check ReActAgent parameters
from archytas.react import ReActAgent
sig = inspect.signature(ReActAgent.__init__)
print('\nReActAgent.__init__ parameters:')
for name, param in sig.parameters.items():
    default = param.default if param.default != inspect.Parameter.empty else 'no default'
    print(f'  {name}: default={default}')

# Check if OpenRouterModel exists
print('\nChecking for OpenRouterModel:')
try:
    from archytas.models.openrouter import OpenRouterModel
    print('  OpenRouterModel exists:', OpenRouterModel)
    print('  OpenRouterModel location:', inspect.getfile(OpenRouterModel))
except ImportError as e:
    print('  OpenRouterModel import error:', e)

# List available models
print('\nAvailable archytas.models:')
import pkgutil
import archytas.models
for importer, modname, ispkg in pkgutil.iter_modules(archytas.models.__path__):
    print(f'  archytas.models.{modname}')

# Check how BeakerAgent creates the model
print('\nBeakerAgent model creation:')
from beaker_kernel.lib.agent import BeakerAgent
print(f'  BeakerAgent.MODEL = {BeakerAgent.MODEL}')

# Check config
from beaker_kernel.lib.config import config
print(f'  config.LLM_SERVICE_TOKEN = {config.LLM_SERVICE_TOKEN[:30]}...')
