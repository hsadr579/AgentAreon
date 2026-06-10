###Agent Areon Awakened...

import openai
from colorama import *
import time
import json
import os
from tools import*
from system_prompt import *
from speaker import* 
import voice_detector as vd

AI_NAME="Agent Areon"
SYNC_INSTRUCTIONS="sync_instructions.json"

SYSTEM_PROMPT =""
def construct_system_prompt():
    global SYSTEM_PROMPT
    #p=json.dumps(procedures)
    SYSTEM_PROMPT = SYSTEM_PROMPT_NOT_FORMATTED.format(tools=format_tools_for_prompt(TOOL_MAP),name=AI_NAME)#,procedures=p)
#load_procedures()
construct_system_prompt()
STARTING_MESSAGE=f"{AI_NAME} Awakened..."

# ======================
# Speech (TTS) Handling
# ======================
run_speaker()

vd.run_voice_detector()

# ======================
# OpenAI / Ollama Client
# ======================

client = openai.OpenAI(
   # base_url="http://localhost:11434/v1",
    base_url="http://localhost:1234/v1",
    api_key="lm-studio"
    #api_key="nokeyneeded"
)

# ======================
# Main Loop
# ======================

init(autoreset=True)

noExit = True
conversation_history = []
tool_temp_hist = []
voice = True
history_enable = False
tool_response=False
print(f"{Fore.GREEN}\n{STARTING_MESSAGE}{Fore.RESET}")
speech_queue.append(STARTING_MESSAGE)
while noExit:
    construct_system_prompt()
    # keep limited history
    if len(conversation_history) > 10:
        conversation_history = conversation_history[2:]
    if(not tool_response):
        
        temp_instructions={"instructions":[]}
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
            json.dump(temp_instructions,fp)
            fp.close()
        sync_response=False
        user_input=""
        if(len(temp_instructions["instructions"])>0):
            user_input_raw=temp_instructions["instructions"].pop()
            fp=open(SYNC_INSTRUCTIONS,'w')
            json.dump(temp_instructions,fp)
            fp.close()
            if type(user_input_raw) is list:
                if(len(user_input_raw)>1):
                    sync_response=True
                    if(user_input_raw[0]!="null"):
                        print(Fore.LIGHTBLACK_EX + f'\n[{user_input_raw[0]}]: {user_input_raw[1]}' + Fore.RESET)
                    user_input=user_input_raw[1]

        if(not sync_response):
            user_input = input(Fore.LIGHTRED_EX + "\n[you]: " + Fore.RESET)
        
        print()
        
        # ------------------
        # Slash Commands
        # ------------------
        if user_input.startswith("\\"):
            commands = user_input[1:].split(" ")
            command=commands[0]
            if command == "exit":
                noExit = False
            elif command == "voice_off":
                voice = False
                print(Fore.YELLOW + "Voice off")
            elif command == "voice_on":
                voice = True
                print(Fore.YELLOW + "Voice on")
            elif command == "hist":
                for i, msg in enumerate(conversation_history):
                    print(f"{i+1}. [{msg['role']}]: {msg['content']}")
            elif command == "clear_hist":
                conversation_history = []
                print(Fore.YELLOW + "History cleared")
            elif command == "hist_off":
                history_enable = False
                print(Fore.YELLOW + "History disabled")
            elif command == "hist_on":
                history_enable = True
                print(Fore.YELLOW + "History enabled")
            continue

        # ------------------
        # Conversation Handling
        # ------------------
        current_message = {"role": "user", "content": user_input}
        if history_enable:
            conversation_history.append(current_message)
        messages_for_api = [{"role": "system", "content": SYSTEM_PROMPT}] + (
                conversation_history if history_enable else [current_message]
            )
        print(Fore.GREEN + f"[{AI_NAME}]:" + Fore.RESET)
        
    else:
        messages_for_api = [{"role": "system", "content": SYSTEM_PROMPT}] + (
             tool_temp_hist
            )
        
   
    full_reply = ""
    voice_reply=""
    try:
        # Stateless request
        stream = client.chat.completions.create(
            model="meta-llama-3.1-8b-instruct",#"phi3",
            temperature=0.1,
            messages=messages_for_api,
            stream=True,
            extra_body={"context": []},
        )

        tool_response=False
      
        bracket_counter=0
        code_box=False
        
        for chunk in stream:
           
            delta = chunk.choices[0].delta
            
                
            if delta.content is not None:
                for i in delta.content:
                    if(i=='{'):bracket_counter+=1
                    elif(i=='}'):bracket_counter-=1
                    

                if(bracket_counter<=0):
                    end = delta.content.rfind("}")
                    print(delta.content[end+1:].replace('\n\n','\n'), end="", flush=True)
                # message_start_point=0
                    voice_reply+=delta.content
                full_reply += delta.content
                # if(is_first_chunk):is_first_chunk=False
        if( bracket_counter>0):
            print(full_reply, end="")
            voice_start_point=0
        print()
        if history_enable:
            conversation_history.append({"role": "assistant", "content": full_reply})
        tool_calls = extract_tool_calls_from_text(full_reply)
        response=None
        if tool_calls:
            tool_temp_hist.clear()
            tool_temp_hist.append(current_message)
            tool_temp_hist.append({"role": "assistant", "content": full_reply})
            for tc in tool_calls:
                
                fn = tc.get("function", {})
                tool_name = fn.get("name")#morning
                args = fn.get("arguments", {})

                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {}

                tool = TOOL_MAP.get(tool_name)
                
                if tool:
                    try:
                        response=tool["function"](args)
                        print(Fore.YELLOW + f"[Tool {tool_name} called]")
                        if(response!=None):
                            tool_response=True
                            
                            tool_temp_hist.append({"role": "assistant", "content": f"tool {tool_name} response: "+response})
                            if history_enable:
                                conversation_history.append({"role": "tool", "content": f"tool {tool_name} response: "+response})
                     
                                
                    except Exception as e:
                        print(Fore.RED + f"[Tool Error: {e}]\n")
                        response=None
            if(tool_response):
                tool_temp_hist.append({"role": "user", "content": "report me result of all tool responses in plain text(not json) and in your language."})# continue if needed based on the my first request" })
       
        if voice:
            speech_queue.append(voice_reply)
    

    except Exception as e:
        print(Fore.RED + f"\nError: {e}\n")
        if conversation_history and conversation_history[-1]["role"] == "user":
            conversation_history.pop()

# cleanup
stop_speaker()
vd.stop_voice_detector()
