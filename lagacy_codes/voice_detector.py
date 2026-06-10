import sounddevice as sd
import threading as t
import numpy as np
import whisper
import queue
import time
import json
import speaker
import random


CONFIG_FILE="config.json"
INITIAL_SUSPENSE_TIME=4
SUSPENSE_TIME=1
THE_NAME="Agent Areon"
STOP_NAME="dismissed"
SYNC_INSTRUCTIONS="sync_instructions.json"
RESPONSE_MSG=["At your service","my lord","Agent Areon Listening"]
VOICE_OFF_MSG=["I shall take my leave"]

try:
    
    with open(CONFIG_FILE, 'r') as fp:
        configs = json.load(fp)
        if "voice_summoning_word" in configs:THE_NAME=configs["voice_summoning_word"]
        if "voice_summoning_answers" in configs:RESPONSE_MSG=configs["voice_summoning_answers"] 
        if "voice_initial_suspense" in configs:INITIAL_SUSPENSE_TIME=int(configs["voice_initial_suspense"]) 
        if "voice_suspense" in configs:SUSPENSE_TIME=int(configs["voice_suspense"] )
        

except Exception:
    pass


model = whisper.load_model("models/base.pt")

samplerate = 16000
q = queue.Queue()
voice_thread=None
stop_vd=False

# NEW: Global state variable to communicate with the main UI thread
IS_LISTENING = False 
ALLOWED_TO_LISTEN=True
def forbid_listening():
    global ALLOWED_TO_LISTEN
    ALLOWED_TO_LISTEN=False
def allow_listening():
    global ALLOWED_TO_LISTEN
    ALLOWED_TO_LISTEN=True
def audio_callback(indata, frames, time, status):
    q.put(indata.copy())

def listen():
    global IS_LISTENING
    suspense=5
    IS_LISTENING=False
    timer=time.time()
    final_res=""
    with sd.InputStream(samplerate=samplerate, channels=1, callback=audio_callback):

        audio_buffer = np.empty((0,1))

        while (not stop_vd):
            
            data = q.get()
            audio_buffer = np.concatenate((audio_buffer, data))
            if speaker.SPEAKING or not ALLOWED_TO_LISTEN:
                timer=time.time()
                audio_buffer = np.empty((0,1))
                time.sleep(0.001)
                continue
            if len(audio_buffer) > samplerate * 5:

                audio = audio_buffer.flatten().astype(np.float32)
                
                result = model.transcribe(
                    audio,
                    language="en",                        # <--- ADD THIS (change to your language code if not English)
                    initial_prompt=f"{THE_NAME} , {STOP_NAME}",
                    no_speech_threshold=0.6,              # Slightly higher to ignore background noise
                    logprob_threshold=-1.0,               # <--- ADD THIS to filter out low-confidence hallucinations
                    condition_on_previous_text=False,     # <--- Use boolean False instead of 0
                    fp16=False                            # <--- ADD THIS if running on CPU to prevent precision errors
                )["text"]
                #print(result)  #<--- REMOVED: print() ruins the curses UI layout
                
                if IS_LISTENING:
                    
                    
                    if(STOP_NAME.lower() in result.lower()):
                        IS_LISTENING=False
                        final_res=""
                        speaker.speech_queue.append(random.choice(VOICE_OFF_MSG))
                    elif(result.strip()!=""):
                        suspense=SUSPENSE_TIME
                        timer=time.time()
                        final_res+=result
                else:
                    if(THE_NAME.lower() in result.lower()):
                        suspense=INITIAL_SUSPENSE_TIME
                        speaker.speech_queue.append(random.choice(RESPONSE_MSG))
                        IS_LISTENING=True
                        timer=time.time()
                        final_res=""
                

                audio_buffer = np.empty((0,1))
                
            if(IS_LISTENING):
                if(time.time()-timer>suspense):
                
                    # print("end of listening") <--- REMOVED
                    #IS_LISTENING=False
                    if(final_res.strip()==""): continue
                    
                    temp_instructions={"instructions":[]}
                    try:
                        with open(SYNC_INSTRUCTIONS,'r') as fp:
                            temp_instructions=json.load(fp)
                            if("instructions" not in temp_instructions):
                                temp_instructions={"instructions":[]}
                            elif type(temp_instructions["instructions"]) is not list:
                                temp_instructions={"instructions":[]}
                    except:
                        temp_instructions={"instructions":[]}
                        
                    with open(SYNC_INSTRUCTIONS,'w') as fp:
                        
                        temp_instructions["instructions"].append([f"voice", final_res.strip()])
                        json.dump(temp_instructions,fp)
                    suspense=INITIAL_SUSPENSE_TIME
                    final_res=""

def run_voice_detector():
    global voice_thread,stop_vd, IS_LISTENING
    stop_vd=False
    IS_LISTENING=False
    voice_thread = t.Thread(target=listen, daemon=True)
    voice_thread.start()
    

def stop_voice_detector():
    global voice_thread,stop_vd
    if(voice_thread):
        stop_vd=True
        voice_thread.join()
        voice_thread=None

if __name__=="__main__":
    listen()
