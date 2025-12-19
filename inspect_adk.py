import inspect
from google.adk.code_executors import code_execution_utils

print("Attributes in code_execution_utils:")
print(dir(code_execution_utils))

if hasattr(code_execution_utils, 'File'):
    print("\nFile source:")
    try:
        print(inspect.getsource(code_execution_utils.File))
    except Exception as e:
        print(f"Could not get source: {e}")
        # Try to instantiate to see fields if dataclass
        try:
             import dataclasses
             print(f"Fields: {dataclasses.fields(code_execution_utils.File)}")
        except:
             pass
