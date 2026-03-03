import os
from typing import Optional

from archytas.tool_utils import AgentRef, tool
from beaker_kernel.lib.agent import BeakerAgent

from bdikit_context.llm.provider_prefixes import LITELLM_PROVIDER_PREFIX

# Valid methods for BDI-Kit operations
VALID_SCHEMA_METHODS = [
    "similarity_flooding", "coma", "cupid", "distribution_based", "jaccard_distance",
    "two_phase", "max_val_sim", "magneto_zs_bp", "magneto_ft_bp", "magneto_zs_llm",
    "magneto_ft_llm", "llm"
]
DEFAULT_SCHEMA_METHOD = "magneto_ft_bp"

VALID_VALUE_METHODS = ["edit_distance", "llm", "llm_numeric", "tfidf", "embedding"]
DEFAULT_VALUE_METHOD = "tfidf"

VALID_TARGETS = ["gdc"]
DEFAULT_TARGET = "gdc"

DEFAULT_OUTPUT_FILE = "harmonized_table.csv"


def _build_litellm_model(model: str) -> str:
    """Normalize model names to litellm provider/model format when needed."""
    if not model:
        return model

    # Build known_prefixes dynamically from the shared table
    known_prefixes = tuple(
        f"{p}/" for p in set(filter(None, LITELLM_PROVIDER_PREFIX.values()))
    )
    if model.startswith(known_prefixes):
        return model

    provider = os.environ.get("LLM_SERVICE_PROVIDER", "openai").lower()
    base_provider = provider.split(":")[-1] if ":" in provider else provider
    prefix = LITELLM_PROVIDER_PREFIX.get(base_provider, base_provider)
    return f"{prefix}/{model}" if prefix else model


def _get_method_args_for_schema(method: str) -> dict:
    """Build method_args dict for schema matching based on HARMONIA_* env vars."""
    fallback = os.environ.get("LLM_SERVICE_MODEL", "openai/gpt-4o-mini")
    if method == "llm":
        model = os.environ.get("HARMONIA_LLM_FOR_SCHEMA_MATCHING", fallback)
        return {"model_name": _build_litellm_model(model)}
    elif method == "magneto_zs_llm":
        model = os.environ.get("HARMONIA_LLM_FOR_MAGNETO_ZERO_SHOT_SCHEMA_MATCHING", fallback)
        return {"reranker_model": _build_litellm_model(model)}
    elif method == "magneto_ft_llm":
        model = os.environ.get("HARMONIA_LLM_FOR_MAGNETO_FINE_TUNED_SCHEMA_MATCHING", fallback)
        return {"reranker_model": _build_litellm_model(model)}
    return {}


def _get_method_args_for_values(method: str) -> dict:
    """Build method_args dict for value matching based on HARMONIA_* env vars."""
    fallback = os.environ.get("LLM_SERVICE_MODEL", "openai/gpt-4o-mini")
    if method == "llm":
        model = os.environ.get("HARMONIA_LLM_FOR_INSTANCE_MATCHING", fallback)
        return {"model_name": _build_litellm_model(model)}
    elif method == "llm_numeric":
        model = os.environ.get("HARMONIA_LLM_FOR_NUMERIC_INSTANCE_MATCHING", fallback)
        return {"model_name": _build_litellm_model(model)}
    elif method == "embedding":
        model = os.environ.get("HARMONIA_EMBEDDING_MODEL_FOR_INSTANCE_MATCHING", "bert-base-multilingual-cased")
        return {"model_name": model}
    return {}


class BDIKitAgent(BeakerAgent):
    """
    An agent that will help a user leverage NYU's BDIKit library for data harmonization.
    """

    @tool()
    async def match_schema(
        self,
        dataset: str,
        agent: AgentRef,
        target: Optional[str] = None,
        method: Optional[str] = None,
    ) -> str:
        """
        This function performs schema mapping between the source table and the given target schema.
        The target is either a DataFrame or a string representing a standard data vocabulary supported by the library.
        Currently, only the GDC (Genomic Data Commons) standard vocabulary is supported.

        Args:
            dataset (str): The name of the dataset variable.
            target (str, optional): The target table or standard data vocabulary.
            method (str, optional): The method used for mapping.

        Returns:
            str: returns the matched columns

        You should show the user the result after this function runs.
        """
        # Apply defaults
        if target is None or target == "":
            target = DEFAULT_TARGET
        if method is None or method == "":
            method = DEFAULT_SCHEMA_METHOD

        # Validate target
        if target not in VALID_TARGETS:
            return f"Error: Invalid target '{target}'. Valid targets are: {', '.join(VALID_TARGETS)}. Please try again with a valid target."

        # Validate method
        if method not in VALID_SCHEMA_METHODS:
            return f"Error: Invalid method '{method}'. Valid methods are: {', '.join(VALID_SCHEMA_METHODS)}. Please try again with a valid method."

        method_args = _get_method_args_for_schema(method)
        code = agent.context.get_code(
            "match_schema",
            {
                "dataset": dataset,
                "target": target,
                "method": method,
                "method_args": method_args,
            },
        )
        result = await agent.context.evaluate(
            code,
            parent_header={},
        )

        match_result = result.get("return")

        return match_result


    @tool()
    async def rank_schema_matches(
        self,
        dataset: str,
        attribute: str,
        agent: AgentRef,
        target: Optional[str] = None,
        top_k: Optional[int] = None,
    ) -> str:
        """
        Returns the top-k schema matches between the source and target tables for a given attribute.
        This is useful for evaluating alternative column mappings when the initial match_schema result seems incorrect.

        Args:
            dataset (str): The name of the dataset variable.
            attribute (str): The source attribute/column to find alternative matches for.
            target (str, optional): The target table or standard data vocabulary.
            top_k (int, optional): Number of top matches to return. Defaults to 10.

        Returns:
            str: returns the top-k alternative schema matches for the given attribute
        """
        # Apply defaults
        if target is None or target == "":
            target = DEFAULT_TARGET
        if top_k is None:
            top_k = 10

        # Validate target
        if target not in VALID_TARGETS:
            return f"Error: Invalid target '{target}'. Valid targets are: {', '.join(VALID_TARGETS)}. Please try again with a valid target."

        code = agent.context.get_code(
            "rank_schema_matches",
            {
                "dataset": dataset,
                "attribute": attribute,
                "target": target,
                "top_k": top_k,
            },
        )
        result = await agent.context.evaluate(
            code,
            parent_header={},
        )

        match_result = result.get("return")

        return match_result


    @tool()
    async def match_values(
        self,
        dataset: str,
        column_mapping: str,
        agent: AgentRef,
        target: Optional[str] = None,
        method: Optional[str] = None,
    ) -> str:
        """
        Returns the top 10 value matches between the value of the source and target columns.
        This is useful for evaluating value matches between a pair columns (column mappings) returned by the match_schema function.

        Args:
            dataset (str): The name of the dataset variable.
            column_mapping (tuple): The column and target names for which to find value matches for. The values must be separated by a comma, example: "source_column,target_column"
            target (str, optional): The target table or standard data vocabulary.
            method (str, optional): The method used for mapping.

        Returns:
            str: returns the value matches for the given column mapping (source and target column names)

        Uppon user's request, the output of match_values() can be fed to materialize_mapping() which materializes the final target using both schema and value mappings.
        """
        # Apply defaults
        if target is None or target == "":
            target = DEFAULT_TARGET
        if method is None or method == "":
            method = DEFAULT_VALUE_METHOD

        # Validate target
        if target not in VALID_TARGETS:
            return f"Error: Invalid target '{target}'. Valid targets are: {', '.join(VALID_TARGETS)}. Please try again with a valid target."

        # Validate method
        if method not in VALID_VALUE_METHODS:
            return f"Error: Invalid method '{method}'. Valid methods are: {', '.join(VALID_VALUE_METHODS)}. Please try again with a valid method."

        # Validate column_mapping format
        if ',' not in column_mapping:
            return f"Error: Invalid column_mapping format '{column_mapping}'. Expected format: 'source_column,target_column' (comma-separated)."

        method_args = _get_method_args_for_values(method)
        code = agent.context.get_code(
            "match_values",
            {
                "dataset": dataset,
                "column_mapping": tuple(column_mapping.split(',')),
                "target": target,
                "method": method,
                "method_args": method_args,
            },
        )
        result = await agent.context.evaluate(
            code,
            parent_header={},
        )

        match_result = result.get("return")

        return match_result


    @tool()
    async def materialize_mapping(
        self,
        dataset: str,
        mapping_spec: str,
        agent: AgentRef,
        output_file: Optional[str] = None,
    ) -> str:
        """
        Materializes the final (harmonized) table after applying data transformations specified by the schema mapping and value mappings specifications.

        This function takes as input the source dataset and the mapping specifications
        (schema and value mappings) formated as a MappingSpecLike dictionary object.
        The `MappingSpecLike` is a type alias that specifies mappings between source
        and target columns. It must include the source and target column names
        and a value mapper object that transforms the values of the source column
        into the target.

        The mapping specification can be (1) a DataFrame or (2) a list of dictionaries or DataFrames.
        If it is a list of dictionaries, they must have:
        - `source`: The name of the source column.
        - `target`: The name of the target column.
        - `mapper` (optional): A ValueMapper instance or an object that can be used to
          create one using :py:func:`~bdikit.api.create_mapper()`. Examples of valid objects
          are Python functions or lambda functions. If empty, an IdentityValueMapper
          is used by default.
        - `matches` (optional): Specifies the value mappings. It must be a list of tuples
          containing a pair of source and target values (<source_value>, <target_value>).
          Please make sure to always represent pairs of source and target values using
          Python tuples (with parenthesis). Do NOT use a lists of lists.

        Alternatively, the list can contain DataFrames. In this case, the DataFrames must
        contain not only the value mappings (as described in the `matches` key above) but
        also the `source` and `target` columns as DataFrame attributes. The DataFrames created
        by :py:func:`~bdikit.api.match_values()` include this information by default.
        If the mapping specification is a DataFrame, it must be compatible with the dictionaries
        above and contain `source`, `target`, and `mapper` or `matcher` columns.

        Example:

        .. code-block:: python

            mapping_spec = [
                {
                    # When no value mapping is need, specifying the source and target is enough
                    "source": "source_column1",
                    "target": "target_column1",
                },
                {
                    # Data transformations can be specified using a mapper, which can be a custom Python lambda function (or a regular function)
                    "source": "source_column2",
                    "target": "target_column2",
                    "mapper": lambda age: -age * 365.25,
                },
                {
                    "source": "source_column3",
                    "target": "target_column3",
                    "matches": [
                        ("source_value1", "target_value1"),
                        ("source_value2", "target_value2"),
                    ]
                }
            ]

        Args:
            dataset (str): The name of the dataset variable.
            mapping_spec (MappingSpecLike): the column and value mapping specificiation.
            output_file (str, optional): The name of the output file to save the materialized target.

        Returns:
            str: returns the materialized target using both schema and value mappings
        """
        # Apply defaults
        if output_file is None or output_file == "":
            output_file = DEFAULT_OUTPUT_FILE

        code = agent.context.get_code(
            "materialize_mapping",
            {
                "dataset": dataset,
                "mapping_spec": mapping_spec,
                "output_file": output_file,
            },
        )
        result = await agent.context.evaluate(
            code,
            parent_header={},
        )

        materialize_result = result.get("return")

        return materialize_result


    @tool()
    async def get_gdc_acceptable_values(self, attribute: str, agent: AgentRef) -> str:
        """
        Returns the acceptable values for a given attribute in the GDC standard.

        Args:
            attribute (str): The name of the attribute/column in the GDC target schema.

        Returns:
            str: returns a list of acceptable values (and their descriptions) for the given attribute in the GDC standard
        """
        # Validate attribute is provided
        if not attribute or attribute.strip() == "":
            return "Error: Attribute name is required. Please provide a valid GDC attribute name."

        code = agent.context.get_code(
            "get_gdc_acceptable_values",
            {
                "attribute": attribute,
            },
        )
        result = await agent.context.evaluate(
            code,
            parent_header={},
        )

        acceptable_values = result.get("return")

        return acceptable_values
