import json
import os
import importlib
def get_current_weather(args):
    # Defensive access to arguments
    location = args.get("location", "Unknown location")
    return f'{{"weather": "sunny", "temperature":"30","location": {location},"instruction":"report the result field in plain text(do not show this json to user)"}}'

TOOLS_PATH="tools_dir"
TOOL_MAP = {
    "get_current_weather": {
        "function": get_current_weather,
        "description": "Fetches current weather information for a specified location.",
        "parameters": {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "The city and state, e.g. 'San Francisco, CA'."
                },
                "unit": {
                    "type": "string",
                    "enum": ["celsius", "fahrenheit"],
                    "description": "Temperature unit"
                }
            },
            "required": ["location"]
        }
    },
    
}
killers=[]
def add_all_tools(args):
    try:
        for i in os.listdir(TOOLS_PATH):
            try:
                print(f"loading tool {i}...")
                temp_tool=importlib.import_module(f"{TOOLS_PATH}.{i}.main")
                temp_tool.init(args)
                temp_tool.add_tool(TOOL_MAP)
                killers.append(temp_tool.kill)
                print(f"tool {i} successfully loaded")
            except Exception as e:
                print(e)
                print(f"failed to load tool {i}")
                continue
    except:
        pass

def format_tools_for_prompt(tool_map):
    """Format tools list for inclusion in system prompt"""
    tools_list = []
    for name, info in tool_map.items():
        tools_list.append({
            "type": "function",
            "function": {
                "name": name,
                "description": info["description"],
                "parameters": info["parameters"]
            }
        })
    return json.dumps(tools_list, indent=2)

import re

def extract_tool_calls_from_text(text: str):
    """Safely extract JSON with 'tool_calls', ignoring normal code blocks."""
    # Look specifically for the start of a tool_calls JSON object
    match = re.search(r'\{\s*"tool_calls"\s*:', text)
    if not match:
        return None

    start_idx = match.start()
    brace_count = 0
    
    # Brace-counting ensures we get the exact end of the JSON object 
    # even if there are nested {} inside the arguments.
    for i in range(start_idx, len(text)):
        if text[i] == '{':
            brace_count += 1
        elif text[i] == '}':
            brace_count -= 1
            
            # When braces balance out to 0, we found the end of the JSON block
            if brace_count == 0:
                candidate = text[start_idx:i + 1]
                try:
                    data = json.loads(candidate)
                    if "tool_calls" in data:
                        return data["tool_calls"]
                except json.JSONDecodeError:
                    return None
    return None
def kill_tools():
    for i in killers:
        try:
            i()
        except:
            pass