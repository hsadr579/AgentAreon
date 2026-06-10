import time
import json
import threading
SCHEDULES_FILE="schedules.json"
SYNC_INSTRUCTIONS="sync_instructions.json"
schedules={}
schedule_names=[]
EXIT_SCHEDULE=False
schedule_tread=None
def schedule_runner():
    while not EXIT_SCHEDULE:
        time.sleep(0.5)
        for i in schedules:
             
            if time.time()>=schedules[i][1]:
                
                try:
                    fp=open(SYNC_INSTRUCTIONS,'r')
                    temp_instructions=json.load(fp)
                    if("instructions" not in temp_instructions):
                        temp_instructions={"instructions":[]}
                    elif type(temp_instructions["instructions"]) is not list:
                        temp_instructions={"instructions":[]}
                    fp.close()
                except:
                    temp_instructions={"instructions":[]}
                fp=open(SYNC_INSTRUCTIONS,'w')
                temp_instructions["instructions"].append([f"schedule {i}",schedules[i][0]])
                json.dump(temp_instructions,fp)
                fp.close()
                if schedules[i][2]:
                    schedules[i][1]+=schedules[i][3]
                else:
                    schedules.pop(i)
                fp=open(SCHEDULES_FILE,'w')
                json.dump(schedules,fp)
                fp.close()


def init(args):
    global schedules,schedule_tread
    try:
        fp=open(SCHEDULES_FILE,'r')
        schedules=json.load(fp)
        
        fp.close()
    except Exception as e:
        fp=open(SCHEDULES_FILE,'w')

        schedules={}
        json.dump(schedules,fp)
        fp.close()
    tmp=[]
    for i in schedules:
        if schedules[i][2]:
            while time.time()>schedules[i][1]:
                schedules[i][1]+=schedules[i][3]
        else:
            if time.time()>schedules[i][1]:
                tmp.append(i)
    for i in tmp:
        schedules.pop(i)
    schedule_names.clear()
    for i in schedules:
        schedule_names.append(i) 
    schedule_tread=threading.Thread(target=schedule_runner)
    schedule_tread.start()
    
def kill():
    global schedule_tread,EXIT_SCHEDULE
    if not EXIT_SCHEDULE:
        EXIT_SCHEDULE=True
        if schedule_tread:
            schedule_tread.join()
            schedule_tread=None
def add_schedule(args):
    
    name=args.get("name","unknown")
    if(name=="unknown"):
        return '{"tool_name":"add_schedule","result":"Failed to add schedule due to missing field name","instruction":"report the result field in plain text(do not show this json to user)"}'
    schedule=args.get("schedule_request","unknown")
    if(schedule=="unknown"):
        return '{"tool_name":"add_schedule","result":"Failed to add schedule due to missing field schedule_request","instruction":"report the result field in plain text(do not show this json to user)"}'
    time_exe=str(args.get("time","unknown"))
    if(time_exe=="unknown"):
        return '{"tool_name":"add_schedule","result":"Failed to add schedule due to missing field time","instruction":"report the result field in plain text(do not show this json to user)"}'
    repeat=eval(str(args.get("repeat","unknown")))
    if(repeat=="unknown"):
        repeat=0
    duration=eval(str(args.get("duration","unknown")))
    if(repeat=="unknown"):
        duration=0
    schedules.setdefault(name,[schedule,eval(time_exe),repeat,duration])
    schedule_names.clear()
    for i in schedules:
        schedule_names.append(i) 
    fp=open(SCHEDULES_FILE,'w')
    json.dump(schedules,fp)
    fp.close()
    
    return f'{{"tool_name":"add_schedule","result":"successfully added schedule {name}","instruction":"report the result field in plain text(do not show this json to user)"}}'

def remove_schedule(args):
    
    name=args.get("name","unknown")
    if(name=="unknown"):
        return '{"tool_name":"add_schedule","result":"Failed to remove schedule due to missing field name","instruction":"report the result field in plain text(do not show this json to user)"}'
    schedule=args.get("schedule_request","unknown")

    schedules.pop(name)
    schedule_names.clear()
    for i in schedules:
        schedule_names.append(i) 
    fp=open(SCHEDULES_FILE,'w')
    json.dump(schedules,fp)
    fp.close()
    
    return f'{{"tool_name":"remove_schedule","result":"successfully removed schedule {name}","instruction":"report the result field in plain text(do not show this json to user)"}}'


def add_tool(tool_dict):

    tool_dict.setdefault("add_schedule", {
        "function": add_schedule,
        "description": "adds a schedule to schedule list(DO NOT execute instructions mentioned by user during adding a new schedule). schedule is pack of instructions that will be called in the specified time. you should calculate time based on current time in seconds since epoch.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "name that refers to this schedule"
                },
                "schedule_request":{
                     "type": "string",
                    "description": "schedule's instructions"
                },
                "time":{
                    "type":"string",
                    "description": "time to execute instruction as number of seconds since epoch."
                },
                "repeat":{
                    "type":"string",
                    "enum":["True","False"],
                    "description":"True when user wants to repeat a schedule(default value is False)"
                },
                "duration":{
                    "type": "string",
                    "description":"duration time for repeating schedule in seconds(only matters when repeat is True)"
                }
            },
            "required": ["name","schedule_request","time"]
        }
    })
    tool_dict.setdefault("remove_schedule", {
        "function": remove_schedule,
        "description": "removes a schedule from schedule list",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "enum":schedule_names,
                    "description": "name that refers to this schedule"
                }
            },
            "required": ["name"]
        }
    })
    