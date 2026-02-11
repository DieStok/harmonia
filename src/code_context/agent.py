"""
Simple code execution agent for the code_context.
"""

from beaker_kernel.lib.agent import BeakerAgent


class CodeAgent(BeakerAgent):
    """
    A simple Python code execution assistant.

    This agent can write and execute Python code in a Jupyter-like environment.
    It has access to common data science libraries like pandas and numpy.
    """

    # No additional tools - just uses the base BeakerAgent capabilities
    pass
