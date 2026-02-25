import bdikit as bdi
column_mappings = bdi.match_schema({{ dataset }}, target="{{ target }}", method="{{ method }}"{% if method_args %}, method_args={{ method_args }}{% endif %})
column_mappings.to_markdown()