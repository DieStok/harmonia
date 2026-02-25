import bdikit as bdi
value_mappings = bdi.match_values({{ dataset }}, attribute_matches={{ column_mapping }}, target="{{ target }}", method="{{ method }}"{% if method_args %}, method_args={{ method_args }}{% endif %})
value_mappings.to_markdown()