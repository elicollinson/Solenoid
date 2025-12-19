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


def ensure_model_available(model_name: str, host: str = "127.0.0.1", port: int = 11434):
    """
    Ensures that the specified model is available in Ollama.
    If not, it attempts to pull it.
    """
    # 1. Check if model exists
    if _check_model_exists(model_name, host, port):
        return

    # 2. Pull model if not exists
    print(f"Model '{model_name}' not found. Pulling from Ollama library...")
    _pull_model(model_name, host, port)
    print(f"Model '{model_name}' pulled successfully.")


def _check_model_exists(model_name: str, host: str, port: int) -> bool:
    """
    Checks if the model is already installed via GET /api/tags.
    """
    url = f"http://{host}:{port}/api/tags"
    try:
        r = requests.get(url)
        if r.status_code == 200:
            data = r.json()
            models = data.get("models", [])
            # Check if model_name matches any 'name' in the list
            # Note: Ollama model names in /api/tags usually include the tag (e.g. "llama3:latest")
            # We should check for exact match or match with ":latest" if no tag provided in model_name
            for m in models:
                if m["name"] == model_name:
                    return True
                # Handle case where model_name might not have a tag but the list does, or vice versa if needed.
                # For now, we assume exact match is required as per LiteLLM usage.
            return False
    except Exception as e:
        print(f"Error checking models: {e}")
    return False


def _pull_model(model_name: str, host: str, port: int):
    """
    Pulls the model via POST /api/pull.
    Uses stream=True to avoid timeouts and show progress (optional).
    """
    url = f"http://{host}:{port}/api/pull"
    payload = {"name": model_name, "stream": False} # Using stream=False for simplicity as per plan, but with long timeout
    
    try:
        # Large models take time, so we set a very long timeout (e.g., 30 minutes)
        r = requests.post(url, json=payload, timeout=1800)
        r.raise_for_status()
        
        # If we wanted to handle stream=True, we would iterate over r.iter_lines()
        
    except requests.exceptions.HTTPError as e:
        if r.status_code == 404:
             raise ValueError(f"Model '{model_name}' not found in Ollama library.") from e
        raise RuntimeError(f"Failed to pull model '{model_name}': {e}") from e
    except Exception as e:
        raise RuntimeError(f"Failed to pull model '{model_name}': {e}") from e
