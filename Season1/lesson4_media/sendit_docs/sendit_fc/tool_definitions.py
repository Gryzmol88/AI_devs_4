TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "fetch_docs_recursive",
            "description": (
                "Downloads task documentation recursively from index.md and [include file=\"...\"] "
                "directives. Saves every discovered file locally and updates manifest."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "index_url": {"type": "string"},
                    "output_dir": {"type": "string"},
                },
                "required": [],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "extract_nontext",
            "description": (
                "Extracts text from non-text files (images) using configured vision model and writes "
                "markdown transcripts to parsed/nontext."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "raw_dir": {"type": "string"},
                    "parsed_dir": {"type": "string"}
                },
                "required": [],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "build_declaration_from_rules",
            "description": (
                "Builds SPK declaration from fixed sendit task constraints and saves to parsed/declaration.txt."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "parsed_dir": {"type": "string"}
                },
                "required": [],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "verify_sendit",
            "description": (
                "Submits answer.declaration from file to https://hub.ag3nts.org/verify for task sendit and "
                "returns HTTP + response body."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "declaration_path": {"type": "string"},
                    "task": {"type": "string"}
                },
                "required": [],
                "additionalProperties": False,
            },
        },
    },
]
