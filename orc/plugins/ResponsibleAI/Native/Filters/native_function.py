from shared.util import get_secret, get_aoai_config, chat_complete
# from semantic_kernel.skill_definition import sk_function
from openai import AzureOpenAI
from semantic_kernel.functions import kernel_function
from tenacity import retry, wait_random_exponential, stop_after_attempt
import logging
import openai
import os
import requests
import time
import traceback
import sys
if sys.version_info >= (3, 9):
    from typing import Annotated
else:
    from typing_extensions import Annotated

# Set up logging
LOGLEVEL = os.environ.get('LOGLEVEL', 'DEBUG').upper()
logging.basicConfig(level=LOGLEVEL)

class Filters:
    @kernel_function(
        description="Validate if user question gets filtered with blocklisted words. Return filtered result.",
        name="ContentFliterValidator",
    )
    def ContentFliterValidator(
        self,
        input: Annotated[str, "The user question"]
    ) -> Annotated[str, "the output is a string with the filter results"]:
        filter_results = []
        user_question = input
        
        try:
            logging.info(f"[sk_native_filters] querying azure openai on content filtering. user question: {user_question}")
            
            functions = []
            messages = [
                    {
                        "role": "system", "content": "You are content filtering validator. ALWAYS RESPOND WITH \'PASSED\', unless filtered."
                    },
                    {
                        "role": "user", "content": f"{user_question}"
                    }
                ]
            
            start_time = time.time()
            response = chat_complete(messages, functions, 'none')
            
            if 'error' in response:
                # Using .get() to avoid KeyError if 'error', 'status', or 'code' keys are missing
                response = response.get('error', {})
                status_code = response.get('status', 'Unknown Status')
                status_reason = response.get('code', 'Unknown Reason')
                error_message = f'Status Code: {status_code} Reason: {status_reason}'

                if status_reason == 'content_filter':
                    contentFilterResult = response.get('innererror', {}).get('content_filter_result', {})
                    filterReasons = []
            
                    violations = ['hate', 'self_harm', 'sexual', 'violence']
                    for violation in violations:
                        ViolationStatus = contentFilterResult.get(violation, {'filtered': False})
                        
                        if ViolationStatus['filtered']:
                            filterReasons.append(violation.upper())
                    
                    blocklists = contentFilterResult.get('custom_blocklists', [])
                    for blocklist in blocklists:
                        if blocklist.get('filtered', False):
                            filterReasons.append(blocklist.get('id', 'Unknown ID').upper())
                
                    error_message += f' {filterReasons}'
                    if response.get('message', "") != "": error_message += f" Error: {response['message']}"

                    logging.warning(f"[sk_native_filters] content filter warning {status_code} on user question. {error_message}")
                    
                    filter_results.append(error_message)                                   
            else:
                for result in response.get('choices', []):
                    filter_results.append(result.get('message', {}).get('content', 'No content'))
            
            response_time = round(time.time() - start_time, 2)
        
            logging.info(f"[sk_native_filters] finished validating user question on filtered content. {response_time} seconds")
        except Exception as e:
            logging.error(f"[sk_native_filters] error when validating user question on filtered content. {type(e).__name__}. {error_message}")
            detailed_error = traceback.format_exc()
            logging.error(f"[sk_native_filters] error details {detailed_error}")

        result = ' '.join(filter_results)
        return result