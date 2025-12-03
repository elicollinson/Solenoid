import os
import uuid
import shutil
from pathlib import Path
from wasmtime import Engine, Store, Module, Linker, WasiConfig

class WasmEngine:
    def __init__(self, wasm_path: str):
        self.wasm_root = Path(wasm_path)
        self.binary_path = self.wasm_root / "python.wasm"
        self.lib_path = self.wasm_root / "lib"
        
        if not self.binary_path.exists():
            raise FileNotFoundError(f"Missing python.wasm at: {self.binary_path}")

        # Initialize Wasmtime
        self.engine = Engine()
        self.linker = Linker(self.engine)
        self.linker.define_wasi()

        # Pre-compile module
        with open(self.binary_path, "rb") as f:
            self.module = Module(self.engine, f.read())

    def run(self, code: str, context_files: dict = None) -> dict:
        """
        Args:
            code (str): The Python code to run.
            context_files (dict): A dictionary of {filename: content_string} 
                                  to create inside the sandbox before running.
        """
        run_id = str(uuid.uuid4())[:8]
        
        # Temp paths for this specific run
        temp_dir = Path(f"temp_sandbox_{run_id}")
        temp_dir.mkdir(parents=True, exist_ok=True)
        
        stdout_path = temp_dir / "stdout.txt"
        stderr_path = temp_dir / "stderr.txt"

        # 1. Create Context Files (The "Upload")
        # This lets the agent read 'input.html' locally
        if context_files:
            for name, content in context_files.items():
                (temp_dir / name).write_text(content, encoding='utf-8')

        store = Store(self.engine)
        wasi = WasiConfig()

        # 2. Configuration
        wasi.argv = ["python", "-u", "-c", code]
        wasi.env = [("PYTHONPATH", "/lib")]
        
        # 3. Mounts
        # Mount the libs read-only
        wasi.preopen_dir(str(self.lib_path), "/lib")
        # Mount the temp directory as the current working directory ('.')
        wasi.preopen_dir(str(temp_dir), ".")

        # 4. IO Capture
        wasi.stdout_file = str(stdout_path)
        wasi.stderr_file = str(stderr_path)

        store.set_wasi(wasi)
        
        outcome = "error"
        try:
            instance = self.linker.instantiate(store, self.module)
            start = instance.exports(store)["_start"]
            start(store)
            outcome = "success"
        except Exception as e:
            # Handle sys.exit(0) gracefully
            if "sys.exit(0)" in str(e) or "exit status 0" in str(e):
                outcome = "success"
            else:
                with open(stderr_path, "a") as f:
                    f.write(f"\n[Runtime Error]: {str(e)}")

        # 5. Read Output
        output_data = stdout_path.read_text(encoding='utf-8') if stdout_path.exists() else ""
        error_data = stderr_path.read_text(encoding='utf-8') if stderr_path.exists() else ""

        # 6. Cleanup
        shutil.rmtree(temp_dir)

        return {
            "stdout": output_data,
            "stderr": error_data,
            "outcome": outcome
        }