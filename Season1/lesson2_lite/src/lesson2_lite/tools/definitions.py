from typing import Any

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_suspects",
            "description": "Returns all suspects with fields: name, surname, birthYear.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_power_plants",
            "description": "Returns available power plants with code, city and active flag.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "estimate_city_coordinates",
            "description": (
                "Save approximate city coordinates estimated by you. "
                "Use this for each power-plant city before suspect analysis."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {"type": "string"},
                    "lat": {"type": "number"},
                    "lon": {"type": "number"},
                },
                "required": ["city", "lat", "lon"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_suspect",
            "description": (
                "Analyzes one suspect by comparing suspect coordinates with estimated "
                "city coordinates for each power plant using Haversine. "
                "Returns ranked plant candidates. You must analyze all suspects before submit."
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
            "description": "Returns access level for one suspect using name, surname and birthYear.",
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
            "description": (
                "Submits final answer to verify endpoint for task findhim. "
                "Fails if not all suspects were analyzed or selected candidate is not best by cityHits and distanceKm."
            ),
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

