TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "get_suspects",
            "description": "Returns a list of all suspects from previous task with name, surname, birthYear.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_suspect",
            "description": (
                "Checks suspect locations, finds nearest power plant, and returns distance in km "
                "plus candidate flag (true when close enough)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "surname": {"type": "string"},
                    "birthYear": {"type": "integer"},
                },
                "required": ["name", "surname", "birthYear"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_access_level",
            "description": "Gets access level from /api/accesslevel endpoint for a given suspect.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "surname": {"type": "string"},
                    "birthYear": {"type": "integer"},
                },
                "required": ["name", "surname", "birthYear"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "submit_findhim_answer",
            "description": "Submits final answer to /verify for task findhim.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "surname": {"type": "string"},
                    "accessLevel": {"type": "integer"},
                    "powerPlant": {"type": "string"},
                },
                "required": ["name", "surname", "accessLevel", "powerPlant"],
                "additionalProperties": False,
            },
        },
    },
]

