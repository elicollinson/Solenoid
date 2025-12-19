
from google.adk.models.lite_llm import LiteLlm
import inspect

# Try to find LlmResponse in the module or return annotation
sig = inspect.signature(LiteLlm.generate_content_async)
return_annotation = sig.return_annotation
print(f"Return annotation: {return_annotation}")

# It might be a string 'AsyncGenerator[LlmResponse, None]'
# I'll try to import LlmResponse from google.adk.models.llm_response if it exists, or check where it is imported in lite_llm if I could read it (I can't).
# I'll try to guess the location or inspect the module of LiteLlm to see imports.
# Actually, I can just try to import it from google.adk.models.lite_llm if it's exposed there.

try:
    from google.adk.models.lite_llm import LlmResponse
    with open("response_details.txt", "w") as f:
        f.write("LlmResponse found in google.adk.models.lite_llm\n")
        f.write(f"LlmResponse annotations: {LlmResponse.__annotations__}\n")
        f.write(f"LlmResponse dir: {dir(LlmResponse)}\n")
except ImportError:
    with open("response_details.txt", "w") as f:
        f.write("LlmResponse not found in google.adk.models.lite_llm\n")
        # Try common locations
        try:
            from google.adk.models import LlmResponse
            f.write("LlmResponse found in google.adk.models\n")
            f.write(f"LlmResponse annotations: {LlmResponse.__annotations__}\n")
        except ImportError:
            pass
