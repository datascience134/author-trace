import re
import json
import streamlit as st
import pandas as pd
import zipfile
import os
import uuid
import requests
from urllib.parse import urlparse
from core import constants
from core import file_handler
from core import prompts
from core.llm_helper import LLMInterface

def extract_keywords(llm: LLMInterface, article: str, num_keywords: int):

    keywords_raw = llm.llm_text(
        system_prompt=prompts.keyword_extraction_prompt.format(num_keywords=num_keywords),
        user_content=article
    )
    keywords_processed = llm.post_process_llm_response(
        processing_prompt=prompts.process_into_list_prompt, 
        response_content=keywords_raw
    )
    return keywords_processed

def ideate_websites(llm: LLMInterface, article: str, keywords_processed: list):
    keywords_str = ", ".join(keywords_processed)
    websites_raw = llm.llm_text(
        system_prompt=prompts.website_ideation_sys_prompt,
        user_content=prompts.website_ideation_prompt.format(article=article, keyword_list=keywords_str)
    )
    websites_processed = llm.post_process_llm_response(
        processing_prompt=prompts.process_into_list_prompt, 
        response_content=websites_raw
    )

    return websites_processed

def debug_base64_encoding(base64_str):
    import base64
    from io import BytesIO
    from PIL import Image   

    try:
        # Decode base64
        image_data = base64.b64decode(base64_str)
        image = Image.open(BytesIO(image_data))

        # Show in Streamlit
        st.image(image, caption="Decoded base64 image", use_column_width=True)

    except Exception as e:
        st.error(f"Failed to decode/display base64 image: {e}")

def author_checker(llm: LLMInterface, author: str, base64_str: str) -> dict:
    """Checks if the author is present in the image and extracts content only if so."""
    
    # Step 1: Check if author appears
    presence_response = llm.llm_image(
        prompt=prompts.author_checker_prompt.format(author=author),
        img_base64=base64_str
    ).strip().lower()

    # print(presence_response)

    if presence_response == "yes":
        # Step 2: Extract content if author is present
        try:
            extraction_response = llm.llm_image(
                prompt=prompts.author_content_extraction_prompt.format(author=author),
                img_base64=base64_str
            )
            try:
                parsed = json.loads(extraction_response)
                return parsed if isinstance(parsed, dict) and "content" in parsed else {"content": []}
            except json.JSONDecodeError as e:
                print(f"Failed to parse JSON: {e}")  
            
        except Exception as e:
            print(f"Error during extraction: {e}")
            return {"content": []}
    else:
        # Author not present, return empty content
        return {"content": []}


def extract_author_content(llm: LLMInterface, author: str, base64_dict: dict):
    content_list = []
    total_images = sum(len(lst) for lst in base64_dict.values())
    progress_text = st.empty()
    progress_bar = st.progress(0)

    processed = 0
    for filename, list_of_base64 in base64_dict.items(): 
        for base64_str in list_of_base64:
            try:
                # Testing
                # debug_base64_encoding(base64_str)

                content_raw = author_checker(llm, author, base64_str)
                content_list.append(content_raw)
            except Exception as e:
                st.error(f"Error during inference: {e}")

            # Update progress
            processed += 1
            progress_text.text(f"Processed {processed} of {total_images} images...")
            progress_bar.progress(processed / total_images)

    # Clear progress indicators after completion (optional)
    progress_text.empty()
    progress_bar.empty()

    input_dicts = []
    input_dicts = [s for s in content_list if isinstance(s, dict)]

    merged_content = []
    for d in input_dicts:
        merged_content.extend(d.get("content", []))

    df = pd.DataFrame({
        "author": [author] * len(merged_content),
        "content": merged_content
    })

    # Remove words that start with 'https://'
    df['content'] = df['content'].apply(
        lambda x: ' '.join(word for word in x.split() if not word.startswith("https://")) if isinstance(x, str) else x
    )

    # Drop NaN/None rows
    df = df[df['content'].notna()] 
    # Drop rows where 'content' is empty or just whitespace
    df = df[df['content'].astype(str).str.strip().astype(bool)] 
    # Drop Duplicates
    df = df.drop_duplicates().reset_index(drop=True)

    return df

def extract_from_text(llm, text_input=None):
    num_keywords = st.number_input("Number of keywords to generate:", value=5, min_value=1, max_value=20)

    if text_input is None:
        text_input = st.text_area("Paste text here:")

    if text_input and num_keywords and re.search(r'\w', text_input):
        if st.button("Extract keywords"):
            with st.spinner("Running inference..."):
                keywords = extract_keywords(llm=llm, article=text_input, num_keywords=num_keywords)
                st.session_state['keywords'] = keywords
                st.session_state.pop('sites', None)  # Clear previous sites

    if 'keywords' in st.session_state:
        st.subheader("Extracted keywords:")
        st.write(st.session_state['keywords'])

        if st.button("Ideate websites to search"):
            with st.spinner("Running inference..."):
                sites = ideate_websites(
                    llm=llm,
                    article=text_input,
                    keywords_processed=st.session_state['keywords']
                )
                st.session_state['sites'] = sites

    if 'sites' in st.session_state:
        st.subheader("Suggested websites to search:")
        st.write(st.session_state['sites'])

def extract_content_from_screenshots(llm, screenshot_files=None):
    uploaded_file = None

    if screenshot_files is None:
        uploaded_file = st.file_uploader(
            "Upload screenshot or zip file of screenshots", 
            type=["png", "jpg", "jpeg", ".webp", "pdf", "zip"],
            key='screenshot_upload'
                                         )
    
    author = st.text_area("Author/ Username (to extract what they wrote):")

    # Only run once per author + file combo
    run_key = f"inference_run_{author}_{hash(str(screenshot_files) + str(uploaded_file))}"

    # Check if content already exists
    if run_key not in st.session_state and (uploaded_file or screenshot_files) and author:
        if screenshot_files:
            base64_dict = file_handler.handle_local_files(screenshot_files)
        else:
            base64_dict = file_handler.handle_uploaded_file(uploaded_file)

        with st.spinner("Running inference..."):
            content_df = extract_author_content(llm=llm, author=author, base64_dict=base64_dict)
        
        # Save to session
        st.session_state[run_key] = content_df
    else:
        content_df = st.session_state.get(run_key)

    if content_df is not None:
        st.subheader("Extracted Author's Content")
        st.dataframe(content_df, use_container_width=True)

        # Convert to CSV
        csv_data = content_df.to_csv(index=False, encoding="utf-8-sig")
        st.download_button(
            label="📥 Download CSV",
            data=csv_data.encode('utf-8-sig'),
            file_name="extracted_data.csv",
            mime="text/csv"
        )

        return content_df

def get_screenshots(urls, SCREENSHOTMACHINE_API_KEY_LIST, output_folder):
    screenshot_api = "https://api.screenshotmachine.com"
    key_index = 0
    saved_images = []

    for url in urls:
        while key_index < len(SCREENSHOTMACHINE_API_KEY_LIST):
            current_key = SCREENSHOTMACHINE_API_KEY_LIST[key_index]
            screenshot_params = {
                "key": current_key,
                "url": url,
                "dimension": "1024xfull",
                "device": "desktop",
                "format": "png",
            }

            try:
                response = requests.get(screenshot_api, params=screenshot_params)
                if response.status_code == 200:

                    parsed = urlparse(url)
                    domain = parsed.hostname.replace('.', '_') if parsed.hostname else "unknown"
                    path = parsed.path.strip("/").replace("/", "_")
                    if not path:
                        path = "_"
                    filename = f"{domain}_{path}.png"
                    filepath = os.path.join(output_folder, filename)  # Save inside correct folder

                    with open(filepath, "wb") as f:
                        f.write(response.content)

                    saved_images.append(filepath)
                    st.success(f"Screenshot: '{filename}'")

                    break  # move to next URL

                elif response.status_code in [432, 403, 429]:
                    key_index += 1

                else:
                    print(f"Failed to capture {url} - Status: {response.status_code}")
                    break

            except Exception as e:
                print(f"Error with screenshot for {url}: {e}")
                key_index += 1

        if key_index >= len(SCREENSHOTMACHINE_API_KEY_LIST):
            print("All API keys exhausted.")
            break

    return saved_images

# Use a persistent directory in your project (won't be deleted on rerun)
def get_or_create_screenshot_folder():
    base_folder = os.path.join(os.getcwd(), ".streamlit_cache", "screenshots")
    os.makedirs(base_folder, exist_ok=True)
    return base_folder

def get_screenshot_from_urls():
    st.subheader("Enter URLs (one per line)")
    url_input = st.text_area("Paste the URLs here:", height=200)

    if url_input.strip():
        urls = [u.strip() for u in url_input.strip().splitlines() if u.strip()]
        st.info(f"Processing {len(urls)} URLs...")

        if "screenshot_result" not in st.session_state or st.session_state.get("last_urls") != urls:
            with st.spinner("Taking screenshots..."):
                output_folder = get_or_create_screenshot_folder()

                # Create a unique subfolder to store this session's screenshots
                unique_folder = os.path.join(output_folder, str(uuid.uuid4()))
                os.makedirs(unique_folder, exist_ok=True)

                # Take screenshots (external API or tool)
                image_paths = get_screenshots(
                    urls,
                    constants.SCREENSHOTMACHINE_API_KEY_LIST,
                    output_folder=unique_folder
                )

                if not image_paths:
                    st.error("No screenshots captured.")
                    return

                # Save to session_state to prevent reprocessing
                st.session_state["screenshot_result"] = {
                    "image_paths": image_paths,
                    "zip_path": os.path.join(unique_folder, "screenshots.zip")
                }
                st.session_state["last_urls"] = urls

                # Create ZIP file only once
                with zipfile.ZipFile(st.session_state["screenshot_result"]["zip_path"], "w") as zipf:
                    for image_file in image_paths:
                        zipf.write(image_file, arcname=os.path.basename(image_file))

        # Show download button using saved result
        image_paths = st.session_state["screenshot_result"]["image_paths"]
        zip_path = st.session_state["screenshot_result"]["zip_path"]

        with open(zip_path, "rb") as f:
            zip_bytes = f.read()

        st.success(f"{len(image_paths)} screenshot(s) captured.")
        st.download_button(
            label="📥 Download Screenshots",
            data=zip_bytes,
            file_name="screenshots.zip",
            mime="application/zip"
        )

# import os
# import requests
# import pandas as pd
# from datetime import datetime

# def run_serper_search(search_terms, SERPER_API_KEY_LIST, max_search_results=10):
#     start = datetime.now()
#     key_index = 0
#     results_list = []

#     headers = {
#         "X-API-KEY": SERPER_API_KEY_LIST[key_index],
#         "Content-Type": "application/json"
#     }

#     for term in search_terms:
#         print(f"\nSearching for: {term}")
        
#         while key_index < len(SERPER_API_KEY_LIST):
#             headers["X-API-KEY"] = SERPER_API_KEY_LIST[key_index]
#             payload = {
#                 "q": term,
#                 "num": max_search_results
#             }

#             try:
#                 response = requests.post(
#                     "https://google.serper.dev/search", 
#                     headers=headers, 
#                     json=payload
#                 )

#                 if response.status_code == 429:
#                     print(f"Key #{key_index + 1} hit its limit (429). Switching to next key...")
#                     key_index += 1
#                     continue

#                 data = response.json()
#                 if "error" in data:
#                     print(f"Error: {data['error']}")
#                     key_index += 1
#                     continue

#                 for result in data.get("organic", []):
#                     results_list.append({
#                         "search_term": term,
#                         "search_result_title": result.get("title"),
#                         "search_result_url": result.get("link"),
#                         "search_result_content": result.get("snippet"),
#                         "search_result_score": None,  # Serper doesn't provide a score
#                     })
#                 break  # Success

#             except Exception as e:
#                 print(f"Exception: {e}")
#                 key_index += 1
#                 continue

#         if key_index >= len(SERPER_API_KEY_LIST):
#             print("All Serper API keys exhausted.")
#             break

#     df = pd.DataFrame(results_list)
#     display(df.sample(min(5, len(df))))
#     end = datetime.now()

#     print("Duration:", end - start)
#     print("Final Serper API key used:", key_index + 1)

#     return df
