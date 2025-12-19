import os
import sys
import time
import tarfile
import subprocess
import requests
from pathlib import Path
from typing import Optional

# Determine the bundled ollama directory
_THIS_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _THIS_DIR.parent.parent.parent  # app/agent/ollama -> project root
_BUNDLED_TAR = _PROJECT_ROOT / "ollama-darwin.tar"
_BUNDLED_OLLAMA_DIR = _PROJECT_ROOT / ".ollama_bin"


def _get_bundled_ollama_path() -> Optional[Path]:
    """
    Returns the path to the bundled ollama binary if available.
    Extracts from tar if needed. Returns None if not on darwin or tar doesn't exist.
    """
    if sys.platform != "darwin":
        return None

    if not _BUNDLED_TAR.exists():
        return None

    ollama_bin = _BUNDLED_OLLAMA_DIR / "ollama"

    # Extract if not already done
    if not ollama_bin.exists():
        _BUNDLED_OLLAMA_DIR.mkdir(parents=True, exist_ok=True)
        with tarfile.open(_BUNDLED_TAR, "r") as tar:
            tar.extractall(_BUNDLED_OLLAMA_DIR)
        # Ensure executable
        ollama_bin.chmod(0o755)

    return ollama_bin


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

    # Determine which ollama binary to use
    ollama_bin = _get_bundled_ollama_path()
    if ollama_bin is None:
        # Fall back to system install
        from shutil import which
        system_ollama = which("ollama")
        if system_ollama is None:
            raise RuntimeError("`ollama` CLI not found in PATH and no bundled binary available. Install from https://ollama.com/download.")
        ollama_bin = Path(system_ollama)

    env = os.environ.copy()
    env["OLLAMA_HOST"] = f"{host}:{port}"
    if models_dir:
        env["OLLAMA_MODELS"] = models_dir

    # For bundled binary, set library path so it finds the bundled .dylib/.so files
    if ollama_bin.parent == _BUNDLED_OLLAMA_DIR:
        if sys.platform == "darwin":
            env["DYLD_LIBRARY_PATH"] = str(_BUNDLED_OLLAMA_DIR)
        else:
            env["LD_LIBRARY_PATH"] = str(_BUNDLED_OLLAMA_DIR)

    # Cross-platform "detached-ish" start
    stdout = open(log_file, "a", buffering=1) if log_file else subprocess.DEVNULL
    stderr = subprocess.STDOUT

    creationflags = 0
    start_new_session = False
    if os.name == "nt":
        # Windows: detach so server isn't tied to the parent console
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
    else:
        # POSIX: new session so it doesn't get SIGINT with your app
        start_new_session = True

    proc = subprocess.Popen(
        [str(ollama_bin), "serve"],
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
