import os
import random
import json

CONFIG_FILE="config.json"
moods=[]
MUSIC_PATH="C:\\Users\\ASUS\\Music\\Agent Areon_musics\\"
music_list={}
PREFIXES=['mp3','ogg','mp4','wav']

try:
    
    with open(CONFIG_FILE, 'r') as fp:
        configs = json.load(fp)["music_player"]
        if "music_path" in configs:MUSIC_PATH=configs["music_path"]
        if "prefixes" in configs:PREFIXES=configs["prefixes"] 
         
except Exception:
    pass


def init():
    if not os.path.exists(MUSIC_PATH):
        os.mkdir(MUSIC_PATH)
        
    list_of_files=os.listdir(MUSIC_PATH)
    for i in list_of_files:
        if(not os.path.isdir(i)):
            if(os.path.basename(i).split('.')[-1] in PREFIXES):
                temp=""
                for j in os.path.basename(i).split('.')[:-1]:
                    temp+=j
                
                temp=temp.split('-')
                name=temp[0]
                mood="unknown"
                if(len(temp)>1):
                    mood=temp[1]
                music_list.setdefault(name,{"path":f"{MUSIC_PATH}{i}","mood":mood})


    for i in music_list:
        moods.append(music_list[i]["mood"])
def kill():
    pass
def play_music(args):
    answer='{"tool_name":"play_music","status":"no music was found...","instruction":"report the result field in plain text(do not show this json to user)"}'
    music_name=args.get("name","unknown")
    mood=args.get("mood","unknown")
    if mood in moods:
        list_of_musics=[]
        for i in music_list:
            if(music_list[i]["mood"]==mood):
                list_of_musics.append(i)
        music_name=random.choice(list_of_musics)
        os.startfile(f'{music_list[music_name]["path"]}')

        answer=f'{{"tool_name":"play_music","result":"music {music_name} is being played...","instruction":"report the result field in plain text(do not show this json to user)"}}'        
   
    elif music_name in music_list:
        os.startfile(f'{music_list[music_name]["path"]}')

        answer=f'{{"tool_name":"play_music","result":"music {music_name} is being played...","instruction":"report the result field in plain text(do not show this json to user)"}}'        
    
    return answer

def list_music(args):
    mood=args.get("mood","unknown")
    list_of_musics={}
    if mood in moods:
        
        for i in music_list:
            if(music_list[i]["mood"]==mood):
                list_of_musics.setdefault(i,{"mood":mood})
    else:
        list_of_musics=music_list.copy()
    return f'{{"tool_name":"play_music","result":{list_of_musics.__str__()},"instruction":"report list of musics in a human readable format"}}'
        

def add_tool(tool_dict):
    tool_dict.setdefault("play_music", {
        "function": play_music,
        "description": "plays music based on provided name or provided mood.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "enum": list(music_list.keys()),
                    "description": "name of music"
                },
                "mood":{
                     "type": "string",
                    "enum": moods,
                    "description": "mood of music"
                }
            },
            "required": []
        }
    })
    tool_dict.setdefault("fetch_music_list", {
        "function": list_music,
        "description": "lists available musics and their moods.",
        "parameters": {
            "type": "object",
            "properties": {
                
                "mood":{
                     "type": "string",
                    "enum": moods,
                    "description": "tells the tool to only list musics with this especial mood. if you leave it empty it will list all musics."
                }
            },
            "required": []
        }
    })