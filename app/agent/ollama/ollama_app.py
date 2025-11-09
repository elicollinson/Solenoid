import os
import time
import subprocess
import requests
from typing import Optional

def _is_ollama_up(host: str = "127.0.0.1", port: int = 11434, timeout: float = 0.8) -> bool:
    url = f"http://{host}:{port}/api/tags"
    try:
        r = requests.get(url, timeout=timeout)
        return r.status_code == 200
    except Exception:
        return False

def start_ollama_server(
    host: str = "127.0.0.1",
    port: int = 11434,
    models_dir: Optional[str] = None,
    log_file: Optional[str] = None,
    wait_seconds: float = 30.0,
):
    """
    Ensure an Ollama server is running. If already up, returns None.
    If started by this function, returns the subprocess.Popen handle.
    """
    if _is_ollama_up(host, port):
        return None  # already running

    # Verify CLI is available
    from shutil import which
    if which("ollama") is None:
        raise RuntimeError("`ollama` CLI not found in PATH. Install from https://ollama.com/download and ensure it's on PATH.")

    env = os.environ.copy()
    env["OLLAMA_HOST"] = f"{host}:{port}"
    if models_dir:
        env["OLLAMA_MODELS"] = models_dir

    # Cross-platform “detached-ish” start
    stdout = open(log_file, "a", buffering=1) if log_file else subprocess.DEVNULL
    stderr = subprocess.STDOUT

    creationflags = 0
    start_new_session = False
    if os.name == "nt":
        # Windows: detach so server isn't tied to the parent console
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
    else:
        # POSIX: new session so it doesn’t get SIGINT with your app
        start_new_session = True

    proc = subprocess.Popen(
        ["ollama", "serve"],
        env=env,
        stdout=stdout,
        stderr=stderr,
        creationflags=creationflags,
        start_new_session=start_new_session,
    )

    # Wait until the HTTP API comes up (or the process dies)
    deadline = time.time() + wait_seconds
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"`ollama serve` exited early with code {proc.returncode}. Check logs.")
        if _is_ollama_up(host, port):
            return proc
        time.sleep(0.25)

    # Timed out; clean up
    try:
        proc.terminate()
    except Exception:
        pass
    raise TimeoutError(f"Ollama did not become ready on {host}:{port} within {wait_seconds}s.")
