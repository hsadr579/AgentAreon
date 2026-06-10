import json
import base64
import os
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def _derive_key(password: str, salt: bytes) -> bytes:
    # Derive a 256‑bit (32‑byte) key using PBKDF2-HMAC-SHA256
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=200_000,
    )
    return kdf.derive(password.encode("utf-8"))


def encrypt(data: str, password: str) -> str:
    # Convert data to bytes
    plaintext = data.encode("utf-8")

    # Generate salt + nonce
    salt = os.urandom(16)
    nonce = os.urandom(12)

    # Derive key
    key = _derive_key(password, salt)

    # Encrypt
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, plaintext, None)

    # Combine salt + nonce + ciphertext and encode as base64 string
    combined = base64.urlsafe_b64encode(salt + nonce + ciphertext)
    return combined.decode("utf-8")


def decrypt(data: str, password: str) -> str:
    decoded = base64.urlsafe_b64decode(data)

    # Extract components
    salt = decoded[:16]
    nonce = decoded[16:28]
    ciphertext = decoded[28:]

    # Derive key
    key = _derive_key(password, salt)

    # Decrypt
    aesgcm = AESGCM(key)
    plaintext = aesgcm.decrypt(nonce, ciphertext, None)

    return plaintext.decode("utf-8")

      
PROCEDURES_FILE="procedures.json"
SYNC_INSTRUCTIONS="sync_instructions.json"
procedures={}
procedures_names=[]
def init(args):
    global procedures
    try:
        fp=open(PROCEDURES_FILE,'r')
        procedures=json.load(fp)
        
        fp.close()
    except Exception as e:
        fp=open(PROCEDURES_FILE,'w')

        procedures={}
        json.dump(procedures,fp)
        fp.close()
    procedures_names.clear()
    for i in procedures:
        procedures_names.append(i) 
def kill():
    pass
def add_procedure(args):
    
    name=args.get("name","unknown")
    if(name=="unknown"):
        return '{"tool_name":"add_procedure","result":"Failed to add procedure due to missing field name","instruction":"report the result field in plain text(do not show this json to user)"}'
    procedure=args.get("procedure_request","unknown")
    if(procedure=="unknown"):
        return '{"tool_name":"add_procedure","result":"Failed to add procedure due to missing field procedure_request","instruction":"report the result field in plain text(do not show this json to user)"}'
    enc=args.get("encrypt","unknown")
    if(enc!="unknown"):

        if eval(str(enc)):
            enc=True
            passw=args.get("password","unknown")
            if(passw!="unknown"):
                procedure=encrypt(procedure,passw)
    else:enc=False
    procedures.setdefault(name,[procedure,enc])
    procedures_names.clear()
    for i in procedures:
        procedures_names.append(i) 
    fp=open(PROCEDURES_FILE,'w')
    json.dump(procedures,fp)
    fp.close()
    
    return f'{{"tool_name":"add_procedure","result":"successfully added procedure {name}","instruction":"report the result field in plain text(do not show this json to user)"}}'

def remove_procedure(args):
    
    name=args.get("name","unknown")
    if(name=="unknown"):
        return '{"tool_name":"add_procedure","result":"Failed to remove procedure due to missing field name","instruction":"report the result field in plain text(do not show this json to user)"}'
 
    procedures.pop(name)
    procedures_names.clear()
    for i in procedures:
        procedures_names.append(i) 
    fp=open(PROCEDURES_FILE,'w')
    json.dump(procedures,fp)
    fp.close()
    
    return f'{{"tool_name":"remove_procedure","result":"successfully removed procedure {name}","instruction":"report the result field in plain text(do not show this json to user)"}}'

def call_procedure(args):
    name=args.get("name","unknown")
    passw=args.get("password","unknown")
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
    
    if(name not in procedures):
        return f'{{"tool_name":"call_procedure","result":"Procedure {name} not found","instruction":"report the result field in plain text(do not show this json to user)"}}'
    fp=open(SYNC_INSTRUCTIONS,'w')

    try:
        procedure=procedures[name][0] if not procedures[name][1] else decrypt(procedures[name][0],passw)
    except:
        return f'{{"tool_name":"call_procedure","result":"password for procedure {name} was wrong!","instruction":"report the result field in plain text(do not show this json to user) and ask user to provide right password"}}'
    temp_instructions["instructions"].append([f"procedure {name}",procedure])
    json.dump(temp_instructions,fp)
    fp.close()
    return f'{{"tool_name":"call_procedure","result":"procedure {name} called","instruction":"do not say anything. you will receive instruction of this procedure later. so for this one just wait."}}'

def add_tool(tool_dict):
    tool_dict.setdefault("add_procedure", {
        "function": add_procedure,
        "description": "adds a procedure to procedure list(DO NOT execute instructions mentioned by user during adding a new procedure). procedure is pack of instructions that can be called later",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "name that refers to this procedure"
                },
                "procedure_request":{
                     "type": "string",
                    "description": "procedure's instructions"
                },
                "encrypt":{
                    "type":"bool",
                    "description":"weather the user wants to encrypt procedure details with password or not"
                },
                "password":{
                    "type":"string",
                    "description":"the password for encrypting procedure details(required only when 'encrypt' field is 'True')"
                }
            },
            "required": ["name","procedure_request"]
        }
    })
    tool_dict.setdefault("remove_procedure", {
        "function": remove_procedure,
        "description": "removes a procedure from procedure list",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "name that refers to this procedure"
                }
            },
            "required": ["name"]
        }
    })
    
    tool_dict.setdefault("call_procedure", {
        "function": call_procedure,
        
        "description": "calls a procedure and sends back the result of call(success or failure)",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "enum": procedures_names,
                    "description": "name that refers to this procedure"
                },
            },
            
            "password":{
                "type":"string",
                "description":"the password for decrypting procedure details"
            },
            "required": ["name"]
        }
    })