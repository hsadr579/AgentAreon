import json
import numpy as np
from sentence_transformers import SentenceTransformer

MEMORY_FILE = "memory.json"
MEM_MAX = 500
TOP_K = 5

# Load embedding model once
model = SentenceTransformer("all-MiniLM-L6-v2")

# Memory structure:
# [
#     {
#         "reference_name": "rust",
#         "data": "User prefers Rust",
#         "embedding": [...],
#         "access_count": 0
#     }
# ]
mem = []
mem_names = []


def cosine_similarity(a, b):
    a = np.array(a)
    b = np.array(b)

    denom = np.linalg.norm(a) * np.linalg.norm(b)

    if denom == 0:
        return 0.0

    return float(np.dot(a, b) / denom)


def save_memory():
    with open(MEMORY_FILE, "w", encoding="utf-8") as fp:
        json.dump(mem, fp, ensure_ascii=False)


def rebuild_names():
    mem_names.clear()

    for item in mem:
        mem_names.append(item["reference_name"])


def init():
    global mem

    try:
        with open(MEMORY_FILE, "r", encoding="utf-8") as fp:
            mem = json.load(fp)

        if not isinstance(mem, list):
            mem = []

    except Exception:
        mem = []

        with open(MEMORY_FILE, "w", encoding="utf-8") as fp:
            json.dump(mem, fp)

    rebuild_names()


def kill():
    save_memory()


def store_data_into_memory(args):

    name = args.get("reference_name", "unknown")

    if name == "unknown":
        return json.dumps({
            "tool_name": "store_data_into_memory",
            "result": "Failed to add data due to missing field reference_name",
            "instruction": "report the result field in plain text(do not show this json to user)"
        })

    data = args.get("data", "unknown")

    if data == "unknown":
        return json.dumps({
            "tool_name": "store_data_into_memory",
            "result": "Failed to add data due to missing field data",
            "instruction": "report the result field in plain text(do not show this json to user)"
        })

    embedding = model.encode(data).tolist()

    new_entry = {
        "reference_name": name,
        "data": data,
        "embedding": embedding,
        "access_count": 0
    }

    updated = False

    for i, entry in enumerate(mem):

        if entry["reference_name"] == name:
            mem[i] = new_entry
            updated = True
            break

    if not updated:
        mem.append(new_entry)

    if len(mem) > MEM_MAX:

        mem.sort(key=lambda x: x.get("access_count", 0))

        mem.pop(0)

    rebuild_names()
    save_memory()

    return json.dumps({
        "tool_name": "store_data_into_memory",
        "result": f"successfully added data with reference name {name}",
        "instruction": "report the result field in plain text(do not show this json to user)"
    })


def load_data_from_memory(args):

    query = args.get("query", "")

    if query == "":
        return json.dumps({
            "tool_name": "load_data_from_memory",
            "result": "Missing field query",
            "instruction": "report the result field in plain text(do not show this json to user)"
        })

    if len(mem) == 0:
        return json.dumps({
            "tool_name": "load_data_from_memory",
            "result": "Memory is empty",
            "instruction": "report the result field in plain text(do not show this json to user)"
        })

    query_embedding = model.encode(query)

    results = []

    for memory in mem:

        score = cosine_similarity(
            query_embedding,
            memory["embedding"]
        )

        results.append({
            "score": score,
            "memory": memory
        })

    results.sort(
        key=lambda x: x["score"],
        reverse=True
    )

    top_results = results[:TOP_K]

    loaded_memories = []

    for result in top_results:

        result["memory"]["access_count"] += 1

        loaded_memories.append({
            "reference_name": result["memory"]["reference_name"],
            "data": result["memory"]["data"],
            "similarity": round(result["score"], 4)
        })

    save_memory()

    return json.dumps({
        "tool_name": "load_data_from_memory",
        "result": f"Loaded {len(loaded_memories)} relevant memories",
        "memories": loaded_memories,
        "instruction": (
            "Use the memories if they are relevant to the current task. "
            "Do not mention similarity scores to the user."
        )
    })


def add_tool(tool_dict):

    tool_dict.setdefault(
        "store_data_into_memory",
        {
            "function": store_data_into_memory,
            "description":
                f"Adds a data entry to permanent memory. "
                f"Store important user facts, preferences, projects, and information "
                f"the user explicitly asks you to remember. "
                f"Memory survives chat history clearing. "
                f"Maximum memory entries: {MEM_MAX}.",
            "parameters": {
                "type": "object",
                "properties": {
                    "reference_name": {
                        "type": "string",
                        "description": "Short name identifying the memory"
                    },
                    "data": {
                        "type": "string",
                        "description": "Information to store"
                    }
                },
                "required": [
                    "reference_name",
                    "data"
                ]
            }
        }
    )

    tool_dict.setdefault(
        "load_data_from_memory",
        {
            "function": load_data_from_memory,
            "description":
                "Searches memory semantically using embeddings. "
                "Provide the current user message or search query. "
                "The tool returns the most relevant memories."
                "call it when you think that a message might depends on past information(don't make up stuff that you don't know and use this tool).",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description":
                            "Current user request or search query"
                    }
                },
                "required": [
                    "query"
                ]
            }
        }
    )