import openai
import time
import json
import os
import curses
import math
import textwrap
from tools import *
from system_prompt import *
from speaker_v3 import *
import voice_detector_v2 as vd
import chars
import colorizer


CONFIG_FILE="config.json"
AI_NAME = "Agent Areon"
USER_NAME="Diagrammer The First"
USER_SYSPROMPT=""
SYNC_INSTRUCTIONS = "sync_instructions.json"
HIST_FILE="history.json"
SCROLL_OFFSET = 0  # <--- Global scroll tracking
VOICE_DETECTION=True
SYSTEM_PROMPT = ""
URL="http://localhost:1234/v1"
API_KEY="lm-studio"
MODEL="Gemma-4-E4B-Uncensored-HauhauCS-Aggressive-IQ4_NL"
TEMPERATURE=0.3
try:
    
    with open(CONFIG_FILE, 'r') as fp:
        configs = json.load(fp)
        if "ai_name" in configs:AI_NAME=configs["ai_name"]
        if "user_name" in configs:USER_NAME=configs["user_name"] 
        if "user_sysprompt" in configs:USER_SYSPROMPT=configs["user_sysprompt"]
        if "base_url" in configs:URL=configs["base_url"]
        if "api_key" in configs:API_KEY=configs["api_key"]
        if "model" in configs:MODEL=configs["model"]
        if "temperature" in configs:TEMPERATURE=configs["temperature"]


except Exception:
    pass

def construct_system_prompt():
    global SYSTEM_PROMPT
    SYSTEM_PROMPT = SYSTEM_PROMPT_NOT_FORMATTED.format(tools=format_tools_for_prompt(TOOL_MAP)
                                                       , name=AI_NAME,user_name=USER_NAME,user_sysprompt=USER_SYSPROMPT,
                                                       current_time=f"{time.ctime()},time in secs since Epoch:{time.time()}",
                                                    voice=VOICE_NAME,voice_personality=VOICE_PERSONALITY)

construct_system_prompt()
#print(SYSTEM_PROMPT)
STARTING_MESSAGE = f"{AI_NAME} Awakened\n\n"

# ======================
# Curses UI Helper Functions
# ======================

def wrap_segments(tag, tag_color, text, text_color, width):
    full_text = tag + text
    result_segments = []
    
    if not full_text:
        return [[("", 0)]]

    for line_idx, raw_line in enumerate(full_text.split('\n')):
        wrapped = textwrap.wrap(raw_line, width)
        if not wrapped:
            result_segments.append([("", 0)])
            continue
            
        for w_idx, w_line in enumerate(wrapped):
            if line_idx == 0 and w_idx == 0 and tag:
                if len(w_line) >= len(tag):
                    seg = [(w_line[:len(tag)], tag_color), (w_line[len(tag):], text_color)]
                else:
                    seg = [(w_line, tag_color)]
            else:
                seg = [(w_line, text_color)]
            result_segments.append(seg)
            
    return result_segments
code_boxes=[]
def redraw(stdscr, chat_log, current_input, streaming_text="", is_calling_tool=False,thinking=False, ai_name="AI", input_tag="[you]: ", input_color=2):
    """Draws the chat UI: history at the top, divider, and input field at the bottom."""
    global SCROLL_OFFSET
    
    stdscr.erase()
    max_y, max_x = stdscr.getmaxyx()

    if max_x < 15 or max_y < 5:
        stdscr.addstr(0, 0, "Terminal too small!")
        stdscr.refresh()
        return

    # 1. Calculate Input Area Dimensions
    input_lines = wrap_segments(input_tag, input_color, current_input, 0, max_x - 1)
    
    max_input_h = max(1, max_y // 2)
    input_h = len(input_lines)
    visible_input_h = min(input_h, max_input_h)
    
    divider_y = max_y - 1 - visible_input_h

    # 2. Gather Chat History Lines
    lines_to_draw = []
    for msg in chat_log:
        segs = wrap_segments(msg["tag"], msg["tag_color"], msg["content"], msg["content_color"], max_x - 1)
        lines_to_draw.extend(segs)

    # 3. Add Currently Streaming Text
    if streaming_text or is_calling_tool or thinking:
        full_stream = f"\n{streaming_text}" if streaming_text else ""
        
        if is_calling_tool:
            dots_count = int(time.time() * 2) % 4
            dots = "." * dots_count
            if full_stream.strip():
                full_stream += f"\n\ncalling tool{dots}"
            else:
                full_stream = f"\ncalling tool{dots}"
        elif thinking:
            dots_count = int(time.time() * 2) % 4
            dots = "." * dots_count
            if full_stream.strip():
                full_stream += f"\n\nthinking{dots}"
            else:
                full_stream = f"\nthinking{dots}"
        stream_segs = wrap_segments(f"[{ai_name}]:", 1, full_stream, 0, max_x - 1)
        lines_to_draw.extend(stream_segs)

    # Calculate scrolling bounds
    max_scroll = max(0, len(lines_to_draw) - divider_y)
    if SCROLL_OFFSET > max_scroll:
        SCROLL_OFFSET = max_scroll
    if SCROLL_OFFSET < 0:
        SCROLL_OFFSET = 0

    # 4. Draw Chat Area
    start_idx=0
    if divider_y > 0:
        if SCROLL_OFFSET == 0:
            display_lines = lines_to_draw[-divider_y:] if len(lines_to_draw) > divider_y else lines_to_draw
            start_idx = max(0, len(lines_to_draw) - divider_y )
        else:
            start_idx = max(0, len(lines_to_draw) - divider_y - SCROLL_OFFSET)
            end_idx = len(lines_to_draw) - SCROLL_OFFSET
            display_lines = lines_to_draw[start_idx:end_idx]
    else:
        display_lines = []
    code_box=False  
    colorizer.reset_state()
    box_num=0
    for y, segs in enumerate(display_lines):
        x = 0
        colorizer.reset_line()
       
        
        for text, color in segs:
            box_num=0
            code_box=False  
            for num_of_box,ij in enumerate(code_boxes):
                if(ij[0]<y+start_idx<ij[1]):
                    code_box=True
                    box_num=num_of_box
            
            if not text: continue
            try:
                
                if "[CODE_BOX]"  in text:
                    stdscr.hline(y, 0, '=', max_x)
                    x+=max_x
                    found=False
                    for i in code_boxes:                
                        if y+start_idx ==i[0] :
                            found=True
                            break
                    
                    if not found:code_boxes.append([y+start_idx,math.inf])
                    
                    continue
                if "[CODE_BOX_END]" in text :
                    stdscr.hline(y, 0, '=', max_x)
                    x+=max_x
                    if len(code_boxes)>0:
                        code_boxes[box_num][1]=y+start_idx
                    
                    continue
                if code_box:
                    word=""
                    pre_char=''
                    for char in text:
                        if char in chars.chars:
                            r=False
                            if pre_char!='':
                                char=pre_char+char
                                pre_char=''
                            else:
                            
                                for i in chars.double_char:
                                    r=r or (char in i)

                            if word!="":
                                stdscr.addstr(y, x, word, curses.color_pair( colorizer.give_color(word,(x,y+start_idx))))
                                x+=len(word)
                                word=""
                            if r:
                                pre_char=char
                            else:
                                stdscr.addstr(y, x, char,  curses.color_pair(colorizer.give_color(char,(x,y+start_idx))))
                                x+=len(char)        
                        else:
                            word+=char
                    if word!="":
                        stdscr.addstr(y, x, word,  curses.color_pair(colorizer.give_color(word,(x,y+start_idx))))
                        x+=len(word)
                        word=""
                    if pre_char!='':
                        stdscr.addstr(y, x, pre_char,  curses.color_pair(colorizer.give_color(pre_char,(x,y+start_idx))))
                        x+=len(pre_char)
                        pre_char=''   
                    continue
                elif color == 0:
                    
                    stdscr.addstr(y, x, text)
                else:
                    stdscr.addstr(y, x, text, curses.color_pair(color))
                x += len(text)
            except curses.error:
                pass

    # 5. Draw Divider Line
    try:
        if divider_y >= 0:
            stdscr.hline(divider_y, 0, curses.ACS_HLINE, max_x)
            # Add visual indicator if scrolled up
            if SCROLL_OFFSET > 0:
                indicator = f" [SCROLLED UP] (Press DOWN/PgDn) "
                if max_x > len(indicator) + 2:
                    stdscr.addstr(divider_y, max_x - len(indicator) - 2, indicator, curses.color_pair(3) | curses.A_REVERSE)
    except curses.error:
        pass

    # 6. Draw Input Area
    start_input_idx = max(0, input_h - visible_input_h)
    for y, segs in enumerate(input_lines[start_input_idx:]):
        x = 0
        draw_y = divider_y + 1 + y
        if 0 <= draw_y < max_y:
            for text, color in segs:
                if not text: continue
                try:
                    if color == 0:
                        stdscr.addstr(draw_y, x, text)
                    else:
                        stdscr.addstr(draw_y, x, text, curses.color_pair(color))
                    x += len(text)
                except curses.error:
                    pass

    stdscr.refresh()

def get_user_input_and_sync(stdscr, chat_log):
    """
    Non-blocking input loop. Supports multiline typing, pasting, voice listening, and scrolling.
    """
    global SCROLL_OFFSET
    current_input = ""
    
    while True:
        # Check Sync Instructions
        temp_instructions = {"instructions": []}
        try:
            if os.path.exists(SYNC_INSTRUCTIONS):
                with open(SYNC_INSTRUCTIONS, 'r') as fp:
                    temp_instructions = json.load(fp)
            else:
                with open(SYNC_INSTRUCTIONS, 'w') as fp:
                    json.dump(temp_instructions, fp)
        except Exception:
            pass

        if isinstance(temp_instructions.get("instructions"), list) and len(temp_instructions["instructions"]) > 0:
            user_input_raw = temp_instructions["instructions"].pop()
            with open(SYNC_INSTRUCTIONS, 'w') as fp:
                json.dump(temp_instructions, fp)

            if isinstance(user_input_raw, list) and len(user_input_raw) > 1:
                SCROLL_OFFSET = 0 # Snap to bottom on sync input
                return user_input_raw[1], True, user_input_raw[0],"user" if len(user_input_raw)<3 else user_input_raw[2]

        # Polling Keystrokes
        stdscr.nodelay(True)
        try:
            k = stdscr.get_wch()
            
            if isinstance(k, int):
                if k in (curses.KEY_BACKSPACE, 127, 8):
                    current_input = current_input[:-1]
                    SCROLL_OFFSET = 0
                elif k == curses.KEY_UP:
                    SCROLL_OFFSET += 1
                elif k == curses.KEY_DOWN:
                    SCROLL_OFFSET -= 1
                elif k == curses.KEY_PPAGE:
                    max_y, _ = stdscr.getmaxyx()
                    SCROLL_OFFSET += max(1, (max_y // 2) - 2)
                elif k == curses.KEY_NPAGE:
                    max_y, _ = stdscr.getmaxyx()
                    SCROLL_OFFSET -= max(1, (max_y // 2) - 2)
            else:
                if k == '\x1b':
                    try:
                        next_k = stdscr.get_wch()
                        if next_k in ('\n', '\r'):
                            current_input += '\n'
                        else:
                            curses.unget_wch(next_k)
                    except curses.error:
                        pass
                elif k in ('\n', '\r'):
                    stdscr.nodelay(True)
                    try:
                        next_k = stdscr.get_wch()
                        curses.unget_wch(next_k)
                        current_input += '\n'
                    except curses.error:
                        SCROLL_OFFSET = 0 # Snap to bottom on submission
                        return current_input.strip(), False, None,None
                elif k in ('\b', '\x7f'):
                    current_input = current_input[:-1]
                    SCROLL_OFFSET = 0
                elif ord(k) == 14:
                    current_input += '\n'
                elif ord(k) == 24:
                    SCROLL_OFFSET = 0
                    return current_input.strip(), False, None,None
                elif k == '\t':
                    current_input += '    '
                elif k.isprintable():
                    current_input += k
                    SCROLL_OFFSET = 0 # Snap to bottom on type
        except curses.error:
            pass

        # === Handle Voice Listening Mode Visualization ===
        is_voice_listening = getattr(vd, 'IS_LISTENING', False)
        
        if is_voice_listening:
            dots = "." * (int(time.time() * 2) % 4)
            display_input = f"listening{dots}"
            active_tag = "[mic] > "
            active_color = 4 # Cyan color
        else:
            display_input = current_input
            active_tag = "[you] > "
            active_color = 2 # Red color

        redraw(stdscr, chat_log, display_input, ai_name=AI_NAME, input_tag=active_tag, input_color=active_color)
        time.sleep(0.005)


# ======================
# Main Curses Application
# ======================
def sync_hist(hist):
    
    fp=open(HIST_FILE,"w")
    json.dump(hist,fp)
    fp.close      
    

def main(stdscr):
    global SCROLL_OFFSET,VOICE_DETECTION
    # Initialize Colors
    curses.start_color()
    curses.use_default_colors()
   # curses.init_pair(0,curses.COLOR_BLACK,-1)
    curses.init_pair(1, curses.COLOR_GREEN, -1)   # AI Tag
    curses.init_pair(2, curses.COLOR_RED, -1)     # User Tag
    curses.init_pair(3, curses.COLOR_YELLOW, -1)  # Tool Responses / System
    curses.init_pair(4, curses.COLOR_CYAN, -1)    # External Sync
    curses.init_pair(5, curses.COLOR_RED, -1)     # Errors
    curses.init_pair(6,curses.COLOR_BLUE,-1)
    curses.init_pair(7,curses.COLOR_MAGENTA,-1)
    # OpenAI Client
    client = openai.OpenAI(
        base_url=URL,
        api_key=API_KEY
    )
    
    # State variables
    noExit = True
    conversation_history = []
    try:
    
        with open(HIST_FILE, 'r') as fp:
            conversation_history = json.load(fp)
    except Exception:
        pass
    tool_temp_hist = []
    voice = True
    history_enable = False
    tool_response = False
    
    # Internal UI Chat Log
    chat_log = [] 
    chat_log.append({"tag": "", "tag_color": 0, "content": STARTING_MESSAGE, "content_color": 1})
    speech_queue.append(STARTING_MESSAGE)

    while noExit:
        #vd.allow_listening()
        construct_system_prompt()
        #print(SYSTEM_PROMPT)
        if(history_enable):
            if len(conversation_history) > 10:
                conversation_history = conversation_history[2:]
            sync_hist(conversation_history)

        if not tool_response:
            user_input, is_sync, sync_tag,sync_sender = get_user_input_and_sync(stdscr, chat_log)
            
            if user_input.startswith("\\"):
                commands = user_input[1:].split(" ")
                command = commands[0]
                if command == "exit":
                    noExit = False
                elif command == "mic_off":
                    if VOICE_DETECTION:
                        vd.stop_voice_detector()
                        VOICE_DETECTION=False
                    chat_log.append({"tag": "[System]: ", "tag_color": 3, "content": "Mic off\n", "content_color": 0})
                elif command == "mic_on":
                    if not VOICE_DETECTION:
                        vd.run_voice_detector()
                        VOICE_DETECTION=True
                    chat_log.append({"tag": "[System]: ", "tag_color": 3, "content": "Mic on\n", "content_color": 0})
                elif command == "voice_off":
                    voice = False
                    chat_log.append({"tag": "[System]: ", "tag_color": 3, "content": "Voice off\n", "content_color": 0})
                elif command == "voice_on":
                    voice = True
                    chat_log.append({"tag": "[System]: ", "tag_color": 3, "content": "Voice on\n", "content_color": 0})
                elif command == "hist":
                    for i, msg in enumerate(conversation_history):
                        chat_log.append({"tag": f"{i+1}. [{msg['role']}]: ", "tag_color": 3, "content": msg['content'], "content_color": 0})
                elif command == "clear_hist":
                    conversation_history = []
                    chat_log.append({"tag": "[System]: ", "tag_color": 3, "content": "History cleared\n", "content_color": 0})
                elif command == "hist_off":
                    history_enable = False
                    chat_log.append({"tag": "[System]: ", "tag_color": 3, "content": "History disabled\n", "content_color": 0})
                elif command == "hist_on":
                    history_enable = True
                    chat_log.append({"tag": "[System]: ", "tag_color": 3, "content": "History enabled\n", "content_color": 0})
                continue

            current_message = {"role": sync_sender if is_sync else "user", "content": user_input}
            
            if is_sync:
                if sync_tag != "null":
                    chat_log.append({"tag": f"[{sync_tag}]: ", "tag_color": 4, "content": f"\n{user_input}\n", "content_color": 0})
            else:
                fmt_input = f"\n{user_input}" if '\n' in user_input else user_input
                chat_log.append({"tag": "[you]: ", "tag_color": 2, "content": fmt_input+'\n', "content_color": 0})

            if history_enable:
                conversation_history.append(current_message)
            messages_for_api = [{"role": "system", "content": SYSTEM_PROMPT}] + (
                conversation_history if history_enable else [current_message]
            )
        else:
            messages_for_api = [{"role": "system", "content": SYSTEM_PROMPT}]
            if history_enable:
                messages_for_api+=conversation_history
            else:
                messages_for_api+=tool_temp_hist
           
     
        full_reply = ""
        voice_reply = ""
        streaming_ui_text = ""
       
        try:
            
           # vd.forbid_listening()
            stream = client.chat.completions.create(
                #model="meta-llama-3.1-8b-instruct",
                model=MODEL,
                temperature=TEMPERATURE,
                messages=messages_for_api,
                stream=True
            )

            tool_response = False
            bracket_counter = 0
            is_calling_tool = False
            thinking=False
            think_sign=False
            code_box=False
            code_char=0
            
            language=""
            lang_detection=False
            lang_detected=False
            for chunk in stream:
                
                delta = chunk.choices[0].delta
                
                if delta.content is not None:
                    content = delta.content
                    full_reply += content
                    
                    for char in content:  
                        if code_char>=3 and code_box:
                            code_char=0
                            lang_detection=True
                            language=""
                            lang_detected=False
                        if lang_detection:
                            if(char!='\n'):
                                language+=char
                            else:
                                lang_detection=False
                                lang_detected=True
                                colorizer.load_language(language.lower())
                                streaming_ui_text+=f"[CODE_BOX]\n{language}\n"
                                
                        if char=='`' and bracket_counter<=0:
                            if not code_box:
                                code_char+=1
                                if code_char>=3:
                                    code_box=True
                                continue
                            if code_box:
                                code_char+=1
                                if code_char>=3:
                                    code_char=0
                                    code_box=False
                                    streaming_ui_text += "[CODE_BOX_END]"
                                continue
                        else:
                            code_char=0
                        if code_box:
                            if lang_detected:
                                streaming_ui_text += char
                        else:

                            if char == '{': 
                                bracket_counter += 1
                                is_calling_tool = True
                            elif char == '}' and bracket_counter > 0:
                                bracket_counter -= 1
                                if bracket_counter <= 0:
                                    is_calling_tool = False   
                            elif bracket_counter <= 0 and char != '}':
                                if not thinking:
                                    if char=='<':
                                        think_sign=True
                                        continue
                                    if char=='|' and think_sign:
                                        thinking=True
                                        think_sign=False
                                        continue
                                    if think_sign and char!='|':
                                        think_sign=False
                                        streaming_ui_text += '<'+char
                                        voice_reply += '<'+char
                                        continue
                                    streaming_ui_text += char
                                    voice_reply += char
                                if thinking:
                                    if char=='|':
                                        think_sign=True
                                        continue
                                    if think_sign and char=='>':
                                        thinking=False
                                        think_sign=False
                                        continue
                                    if think_sign and char!='>':
                                        think_sign=False
                                        streaming_ui_text += '|'+char
                                        voice_reply += '|'+char
                                        continue
                                
                                
                            
                            

                    redraw(stdscr, chat_log, "", streaming_text=streaming_ui_text.strip(), 
                           is_calling_tool=is_calling_tool,thinking=thinking, ai_name=AI_NAME)

            if streaming_ui_text.strip():
                chat_log.append({"tag": f"[{AI_NAME}]:", "tag_color": 1, "content": f"\n{streaming_ui_text.strip()}\n", "content_color": 0})
            
            redraw(stdscr, chat_log, "", ai_name=AI_NAME)

            if history_enable:
                conversation_history.append({"role": "assistant", "content": full_reply})
            
            # Tool Handling
            tool_calls = extract_tool_calls_from_text(full_reply)
            response = None
            
            if tool_calls:
                tool_temp_hist.clear()
                tool_temp_hist.append(current_message)
                tool_temp_hist.append({"role": "assistant", "content": full_reply})
                
                for tc in tool_calls:
                    fn = tc.get("function", {})
                    tool_name = fn.get("name")
                    args = fn.get("arguments", {})

                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except json.JSONDecodeError:
                            args = {}

                    tool = TOOL_MAP.get(tool_name)
                    
                    if tool:
                        try:
                            response = tool["function"](args)
                            
                            chat_log.append({"tag": "[System]: ", "tag_color": 3, "content": f"Tool {tool_name} called\n", "content_color": 3})
                            redraw(stdscr, chat_log, "", ai_name=AI_NAME)
                            voice_reply += f"\nTool {tool_name} called\n"
                            
                            if response != None:
                                tool_response = True
                                tool_temp_hist.append({"role": "tool", "content": response})
                                if history_enable:
                                    conversation_history.append({"role": "tool", "content": response})
                                    
                        except Exception as e:
                            chat_log.append({"tag": "", "tag_color": 0, "content": f"[Tool Error: {e}]\n", "content_color": 5})
                            response = None

                #if tool_response:
                 #   tool_temp_hist.append({"role": "user", "content": "continue based on the 'instruction' field of all recent tool responses(which is in json) and initial request before recent tool calls."})#report me result of all recent tool responses in plain text(not json) and in your language. continue your message or call more tools if initial request is not fulfilled yet and in this case do not ask for permission for further tool calls."})
     
            if voice and voice_reply.strip():
                speech_queue.append(voice_reply.strip().replace("*",""))

        except Exception as e:
            chat_log.append({"tag": "", "tag_color": 0, "content": f"Error: {e}\n", "content_color": 5})
            if conversation_history and conversation_history[-1]["role"] == "user":
                conversation_history.pop()

if __name__ == "__main__":
    run_speaker()
    vd.run_voice_detector()
    
    try:
        curses.wrapper(main)
    finally:

        stop_speaker()
        vd.stop_voice_detector()
        kill_tools()
