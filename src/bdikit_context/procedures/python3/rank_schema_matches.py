import bdikit as bdi
top_matches = bdi.rank_schema_matches({{ dataset }}, attributes=["{{ attribute }}"], target="{{ target }}", top_k={{ top_k }})
top_matches.to_markdown()
