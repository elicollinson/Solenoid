from typing import Any
from google.adk.code_executors import BaseCodeExecutor
from google.adk.code_executors.code_execution_utils import CodeExecutionResult
from app.agent.local_execution.wasm_engine import WasmEngine
from pydantic import PrivateAttr

class ADKLocalWasmExecutor(BaseCodeExecutor):
    _backend: Any = PrivateAttr()

    def __init__(self, wasm_path: str, **kwargs):
        super().__init__(**kwargs)
        self._backend = WasmEngine(wasm_path=wasm_path)

    def execute_code(self, invocation_context, code_execution_input, **kwargs) -> CodeExecutionResult:
        print("⚡ [WasmExecutor] Sandboxing code execution...")

        # 1. EXTRACT CODE
        code_to_run = code_execution_input.code

        # 2. CHECK FOR FILES
        context_files = {}
        if hasattr(code_execution_input, 'input_files') and code_execution_input.input_files:
             for name, content in code_execution_input.input_files.items():
                 context_files[name] = content
        
        # Legacy support
        if "input_data" in kwargs:
             context_files["data.txt"] = kwargs["input_data"]

        # 3. RUN
        result = self._backend.run(code_to_run, context_files=context_files)
        if result['stderr']:
            final_stdout = ""
            final_stderr = f"RUNTIME ERROR:\n{result['stderr']}"
        else:
            # We add a "System Note" to the output to stop the loop
            final_stdout = (
                f"COMMAND OUTPUT:\n{result['stdout']}\n"
                f"--------------------------------------------------\n"
                f"SYSTEM NOTE: The code execution is complete. "
                f"Use the output above to answer the user's question. "
                f"DO NOT generate more code."
            )
            final_stderr = ""

        print(f"   >>> Wasm Result: {result['stdout'][:100]}...")
        # 4. RETURN CORRECT OBJECT (Updated to match your definition)
        # We pass raw stdout/stderr separately so the framework can format them.
        return CodeExecutionResult(
            stdout=final_stdout,
            stderr=final_stderr
            # output_files=[]  <-- We can omit this since it has a default factory
        )