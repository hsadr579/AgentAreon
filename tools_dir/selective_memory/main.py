import json

      
MEMORY_FILE="memory.json"
MEM_MAX=500
perm_mem={}
mem_names=[]
def init(args):
    global perm_mem
    try:
        fp=open(MEMORY_FILE,'r')
        perm_mem=json.load(fp)
        
        fp.close()
    except Exception as e:
        fp=open(MEMORY_FILE,'w')

        perm_mem={}
        json.dump(perm_mem,fp)
        fp.close()
    mem_names.clear()
    for i in perm_mem:
        mem_names.append(i) 
def kill():
    pass
def store_data_into_memory(args):
    global perm_mem
    name=args.get("reference_name","unknown")
    if(name=="unknown"):
        return '{"tool_name":"store_data_into_memory","result":"Failed to add data due to missing field reference_name","instruction":"report the result field in plain text(do not show this json to user)"}'
    data=args.get("data","unknown")
    if(data=="unknown"):
        return '{"tool_name":"store_data_into_memory","result":"Failed to add data due to missing field data","instruction":"report the result field in plain text(do not show this json to user)"}'

    perm_mem.setdefault(name,data)
    mem_names.clear()
    for i in perm_mem:
        mem_names.append(i) 
    if(len(mem_names)>MEM_MAX):
        perm_mem.pop(mem_names.pop(0))

    fp=open(MEMORY_FILE,'w')
    json.dump(perm_mem,fp)
    fp.close()
    
    return f'{{"tool_name":"store_data_into_memory","result":"successfully added data with reference name {name}","instruction":"report the result field in plain text(do not show this json to user)"}}'


def load_data_from_memory(args):
    name=args.get("reference_name","unknown")
    if(name not in perm_mem):
        return f'{{"tool_name":"load_data_from_memory","result":"Data {name} doesn\'t exist in memory.","instruction":"report the result field."}}'
    mem_names.remove(name)
    mem_names.append(name)
    return f'{{"tool_name":"load_data_from_memory","result":"Data with name {name} loaded into \'data\' field","data":"{perm_mem[name]}","instruction":"do not need to report \'result\' field. use loaded data from \'data\' field based on your intention behind calling this tool."}}'

def add_tool(tool_dict):
    tool_dict.setdefault("store_data_into_memory", {
        "function": store_data_into_memory,
        "description": f"adds a data entry to permanent memory which you can access it later using its reference name. Store things that you think are really important or things that user tells you to remember(this feature is independent of your history and works even when history is cleared). be careful because after storing {MEM_MAX} date entries it will automatically removes least accessed data entry by adding more new things.",
        "parameters": {
            "type": "object",
            "properties": {
                "reference_name": {
                    "type": "string",
                    "description": "name that refers to this data entry"
                },
                "data":{
                     "type": "string",
                    "description": "data that you want to store"
                }
                
            },
            "required": ["reference_name","data"]
        }
    })

    
    tool_dict.setdefault("load_data_from_memory", {
        "function": load_data_from_memory,
        
        "description": "loads data by its associated reference name. you should check users request and see if its referring to any of existing reference names and if need you should load associated entry.",
        "parameters": {
            "type": "object",
            "properties": {
                "reference_name": {
                    "type": "string",
                    "enum": mem_names,
                    "description": "name that refers to the wanted data entry"
                },
            },
            "required": ["reference_name"]
        }
    })