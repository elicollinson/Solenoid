from typing import Any
from google.adk.code_executors import BaseCodeExecutor
from google.adk.code_executors.code_execution_utils import CodeExecutionResult, File
from app.agent.local_execution.wasm_engine import WasmEngine
from pydantic import PrivateAttr
import mimetypes
import base64

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
        
        # 4. PROCESS OUTPUT FILES
        output_files = []
        if "output_files" in result:
            for name, content in result["output_files"].items():
                mime_type, _ = mimetypes.guess_type(name)
                if not mime_type:
                    mime_type = "application/octet-stream"
                
                # ADK expects base64 encoded string for content
                if isinstance(content, str):
                    content_bytes = content.encode('utf-8')
                else:
                    content_bytes = content
                
                b64_content = base64.b64encode(content_bytes).decode('ascii')
                
                output_files.append(File(name=name, content=b64_content, mime_type=mime_type))

        # 5. RETURN CORRECT OBJECT
        return CodeExecutionResult(
            stdout=final_stdout,
            stderr=final_stderr,
            output_files=output_files
        )