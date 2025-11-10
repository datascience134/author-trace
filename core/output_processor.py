import json
import re

from core.llm import client, llm_text

process_into_dict_sys_prompt = '''
You will be given a string that represents a dictionary of key-value pairs. 
The string may contain:
- Newline characters
- Colons or equal signs as separators (e.g., "Key: Value", "Key = Value")
- Extra whitespace or inconsistent formatting
- Bullet points (e.g., "-", "•")
- Mixed or malformed punctuation

Your task is to extract and return a clean Python dictionary in **valid JSON format**, where:
- Each key and value is stripped of any bullet characters, leading/trailing whitespace, and extra punctuation.
- The result is a flat key-value mapping.

Return **only valid JSON**.

For example, given the input:

- Name: Alice  
- Age:  30  
• Location = New York  
Gender : Female

You should return:

{
  "Name": "Alice",
  "Age": "30",
  "Location": "New York",
  "Gender": "Female"
}

Input string:
{{input_string}}
'''

process_into_list_sys_prompt = '''
You will be given a string that contains a list of items. The list may include newline characters, bullet points (e.g. `-` or `•`), or inconsistent spacing.

Your task is to extract and return a clean **Python list** of strings, with each item stripped of any bullet characters and whitespace.

Return only valid JSON output. For example, given the input:

'- abc  \n - def ghi'

Return:
["abc", "def ghi"]

Input string:
{{input_string}}
'''

def process_output(output, process_prompt):
    
    question = process_prompt + output
    try:
        json_output = json.loads(output)
        return json_output
    except json.JSONDecodeError:
        cleaned = re.sub(r"^```(?:json)?\n|```$", "", llm_text(client, question).strip(), flags=re.MULTILINE)
        json_output = json.loads(cleaned)
        return json_output