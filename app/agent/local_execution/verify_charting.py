import sys
from pathlib import Path

# Add app to path
sys.path.append(str(Path(__file__).resolve().parent.parent.parent.parent))

from app.agent.local_execution.wasm_engine import WasmEngine
from app.agent.local_execution.adk_wrapper import ADKLocalWasmExecutor
from google.adk.code_executors.code_execution_utils import CodeExecutionInput

def test_wasm_file_output():
    print("Testing WASM File Output...")
    wasm_path = Path(__file__).resolve().parent.parent.parent / "resources" / "python-wasi"
    engine = WasmEngine(wasm_path=str(wasm_path))
    
    code = """
with open('test_output.txt', 'w') as f:
    f.write('Hello from WASM!')
print('Done')
"""
    result = engine.run(code)
    
    if "test_output.txt" in result.get("output_files", {}):
        content = result["output_files"]["test_output.txt"]
        print(f"SUCCESS: File captured. Content: {content}")
    else:
        print("FAILURE: File not captured.")
        print(f"Result keys: {result.keys()}")
        if "output_files" in result:
             print(f"Output files: {result['output_files'].keys()}")

def test_executor_wrapper():
    print("\nTesting ADK Executor Wrapper...")
    wasm_path = Path(__file__).resolve().parent.parent.parent / "resources" / "python-wasi"
    executor = ADKLocalWasmExecutor(wasm_path=str(wasm_path))
    
    code = """
with open('chart.svg', 'w') as f:
    f.write('<svg>fake chart</svg>')
print('Chart generated')
"""
    input_obj = CodeExecutionInput(code=code)
    result = executor.execute_code(None, input_obj)
    
    found = False
    if result.output_files:
        for f in result.output_files:
            if f.name == "chart.svg" and "<svg>" in f.content:
                print(f"SUCCESS: Executor returned file {f.name}")
                found = True
                break
    
    if not found:
        print("FAILURE: Executor did not return file.")
        print(f"Output files: {result.output_files}")

if __name__ == "__main__":
    test_wasm_file_output()
    test_executor_wrapper()
