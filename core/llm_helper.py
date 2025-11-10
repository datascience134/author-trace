import json
import streamlit as st
import tiktoken

from openai import AzureOpenAI
from core import constants
from core import prompts 

class LLMInterface:

    """
    Generic interface for interacting with an LLM (e.g., OpenAI, Azure OpenAI).
    Assumes a `client` object with a `chat.completions.create` method is available.
    """

    def __init__(self):
        self.client = AzureOpenAI(
        azure_endpoint=constants.AZUREOPENAI_ENDPOINT,
        api_key=constants.AZUREOPENAI_API_KEY,
        api_version=constants.AZUREOPENAI_API_VERION,
    )  

    # def count_tokens(text: str, model: str = "gpt-4-1106-preview") -> int:
    #     encoding = tiktoken.encoding_for_model(model)
    #     return len(encoding.encode(text))

    def llm_image(self, prompt, img_base64):  
        response = self.client.chat.completions.create(
          model=constants.AZUREOPENAI_MODEL, 
          messages=[
              {"role": "user", "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{img_base64}"
                        }
                    }
                ]
              },
          ]
        )
        
        return response.choices[0].message.content

    def llm_text(
            self, 
            system_prompt: str,
            user_content: str,
            response_format: dict = {"type": "json_object"},
            temperature: float = 0,
            top_p: float = 0.95,
            frequency_penalty: float = 0,
            presence_penalty: float = 0,
            stop=None
        ):  
        response = self.client.chat.completions.create(
          model=constants.AZUREOPENAI_MODEL,
          messages=[
              {"role": "system", "content": system_prompt},
              {"role": "user", "content": user_content},
          ],
          response_format=response_format,
          temperature=temperature,
          top_p=top_p,
          frequency_penalty=frequency_penalty,
          presence_penalty=presence_penalty,
          stop=stop

        )
        
        return response.choices[0].message.content
    
    def post_process_llm_response(self, processing_prompt: str, response_content: str):
        
      try:
        #   response_content = self.llm_text(
        #         system_prompt=processing_prompt,
        #         user_content=response_content
        #     )
          cleaned_response = json.loads(response_content)
          return cleaned_response
      except json.JSONDecodeError:
          cleaned = re.sub(r"^```(?:json)?\n|```$", "", response_content.strip(), flags=re.MULTILINE)
          cleaned_response = json.loads(cleaned)
          return cleaned_response
