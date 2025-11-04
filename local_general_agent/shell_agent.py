"""Shell-focused sub-agent exposing safe local tooling."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from textwrap import dedent
from typing import Annotated, Iterable

from agents import Agent, function_tool


MAX_WRITE_CHARS = 200_000
MAX_READ_BYTES = 64_000
MAX_LIST_ENTRIES = 400
MAX_SEARCH_MATCHES = 200


def _is_relative_to(path: Path, base: Path) -> bool:
    try:
        path.relative_to(base)
        return True
    except ValueError:
        return False


def _resolve_path(base: Path, relative: str | None) -> Path:
    candidate = (base / relative).resolve() if relative else base
    if not _is_relative_to(candidate, base):
        raise ValueError("Path escapes the workspace root; provide a relative path within the project.")
    return candidate


def _ensure_directory(path: Path) -> Path:
    if not path.exists():
        raise ValueError(f"Directory does not exist: {path}")
    if not path.is_dir():
        raise ValueError(f"Expected a directory but found a file: {path}")
    return path


def _ensure_file(path: Path, allow_missing: bool = False) -> Path:
    if allow_missing and not path.exists():
        return path
    if not path.exists():
        raise ValueError(f"File does not exist: {path}")
    if not path.is_file():
        raise ValueError(f"Expected a file but found a directory: {path}")
    return path


def _normalize_output(text: str, max_bytes: int) -> str:
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    truncated = encoded[:max_bytes].decode("utf-8", errors="ignore")
    return f"{truncated}\n… [truncated]"


def _format_directory_listing(entries: Iterable[Path], base: Path) -> list[str]:
    formatted: list[str] = []
    for entry in entries:
        if not _is_relative_to(entry, base):
            continue
        name = entry.name + ("/" if entry.is_dir() else "")
        formatted.append(name)
    return sorted(formatted)


def create_shell_agent(workspace_root: Path, model: str | None = None) -> Agent:
    """Build a restricted shell agent bound to *workspace_root*."""
    base = workspace_root.resolve()

    @function_tool(name_override="list_directory")
    def list_directory(
        path: Annotated[str | None, "Directory to inspect, relative to the workspace root."] = None,
        show_hidden: Annotated[bool, "Include dotfiles such as `.git`."] = False,
        recursive: Annotated[bool, "Include a tree of nested entries."] = False,
        max_entries: Annotated[int, "Maximum number of entries to include."] = MAX_LIST_ENTRIES,
    ) -> str:
        target = _ensure_directory(_resolve_path(base, path))
        entries: list[Path] = []

        if recursive:
            for child in target.rglob("*"):
                if not show_hidden and child.name.startswith("."):
                    continue
                if child.is_file() or child.is_dir():
                    entries.append(child)
        else:
            for child in target.iterdir():
                if not show_hidden and child.name.startswith("."):
                    continue
                entries.append(child)

        rel_entries = []
        for child in entries[:max_entries]:
            try:
                rel = child.relative_to(base)
            except ValueError:
                continue
            rel_entries.append(str(rel) + ("/" if child.is_dir() else ""))

        if not rel_entries:
            return "Directory is empty."

        if len(entries) > max_entries:
            rel_entries.append(f"… ({len(entries) - max_entries} more entries truncated)")
        return "\n".join(rel_entries)

    @function_tool(name_override="print_working_directory")
    def print_working_directory(
        path: Annotated[str | None, "Optional directory to resolve relative to the workspace root."] = None,
    ) -> str:
        target = _resolve_path(base, path)
        rel = target.relative_to(base)
        return "/" if str(rel) == "." else str(rel)

    @function_tool(name_override="read_file")
    def read_file(
        path: Annotated[str, "File to read, relative to the workspace root."],
        start_line: Annotated[int | None, "1-based line to start from. Defaults to the beginning."] = None,
        end_line: Annotated[int | None, "1-based line to end at (inclusive). Defaults to the end."] = None,
        max_bytes: Annotated[int, "Maximum bytes of content to return."] = MAX_READ_BYTES,
    ) -> str:
        target = _ensure_file(_resolve_path(base, path))
        try:
            text = target.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            raise ValueError(f"File is not valid UTF-8: {target}")

        lines = text.splitlines()
        if start_line is not None and start_line < 1:
            raise ValueError("start_line must be at least 1.")
        if end_line is not None and end_line < 1:
            raise ValueError("end_line must be at least 1.")
        start_idx = (start_line - 1) if start_line else 0
        end_idx = end_line if end_line else len(lines)
        selected = lines[start_idx:end_idx]
        snippet = "\n".join(selected)
        return _normalize_output(snippet, max_bytes)

    @function_tool(name_override="write_file")
    def write_file(
        path: Annotated[str, "File to create or overwrite, relative to the workspace root."],
        content: Annotated[str, "Complete file contents to persist."] = "",
        create_parents: Annotated[bool, "Create parent directories if they do not exist."] = True,
    ) -> str:
        if len(content) > MAX_WRITE_CHARS:
            raise ValueError(
                f"Content too large ({len(content)} chars). Split the write into smaller chunks (limit {MAX_WRITE_CHARS})."
            )
        target = _resolve_path(base, path)
        if target.exists() and target.is_dir():
            raise ValueError("Cannot write to a directory.")
        if create_parents:
            target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        rel = target.relative_to(base)
        return f"Wrote {len(content)} characters to {rel}"

    @function_tool(name_override="append_file")
    def append_file(
        path: Annotated[str, "File to append to, relative to the workspace root."],
        content: Annotated[str, "Text to append at the end of the file."] = "",
        create_if_missing: Annotated[bool, "Create the file if it does not already exist."] = True,
    ) -> str:
        if len(content) > MAX_WRITE_CHARS:
            raise ValueError(
                f"Content too large ({len(content)} chars). Split the write into smaller chunks (limit {MAX_WRITE_CHARS})."
            )
        target = _ensure_file(_resolve_path(base, path), allow_missing=create_if_missing)
        existed = target.exists()
        if not existed and not create_if_missing:
            raise ValueError(f"File does not exist: {target}")
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8") as handle:
            handle.write(content)
        rel = target.relative_to(base)
        action = "Appended" if existed else "Created"
        return f"{action} {len(content)} characters in {rel}"

    def _python_search(pattern: str, target: Path, ignore_case: bool, max_matches: int) -> str:
        flags = re.IGNORECASE if ignore_case else 0
        try:
            compiled = re.compile(pattern, flags)
        except re.error as exc:
            raise ValueError(f"Invalid regular expression: {exc}") from exc

        matches: list[str] = []
        files = [target] if target.is_file() else [p for p in target.rglob("*") if p.is_file()]
        for candidate in files:
            try:
                text = candidate.read_text(encoding="utf-8")
            except Exception:
                continue
            rel = candidate.relative_to(base)
            for idx, line in enumerate(text.splitlines(), start=1):
                if compiled.search(line):
                    matches.append(f"{rel}:{idx}:{line.rstrip()}")
                    if len(matches) >= max_matches:
                        break
            if len(matches) >= max_matches:
                break
        return "\n".join(matches) if matches else "No matches found."

    def _run_rg(pattern: str, target: Path, ignore_case: bool, max_matches: int) -> str:
        cmd = ["rg", "--line-number", "--max-count", str(max_matches)]
        if ignore_case:
            cmd.append("--ignore-case")
        cmd.extend(["--", pattern, str(target)])
        try:
            completed = subprocess.run(
                cmd,
                cwd=base,
                check=False,
                capture_output=True,
                text=True,
            )
        except FileNotFoundError:
            return _python_search(pattern, target, ignore_case, max_matches)

        if completed.returncode not in (0, 1):
            detail = completed.stderr.strip() or completed.stdout.strip()
            raise ValueError(f"rg failed (exit {completed.returncode}): {detail}")
        output = completed.stdout.strip()
        return output if output else "No matches found."

    @function_tool(name_override="search_text")
    def search_text(
        pattern: Annotated[str, "Regular expression pattern to search for. Use plain text if unsure."] ,
        path: Annotated[str | None, "Directory or file to search within. Defaults to the workspace root."] = None,
        ignore_case: Annotated[bool, "Ignore case while matching."] = False,
        max_matches: Annotated[int, "Maximum number of matches to return."] = MAX_SEARCH_MATCHES,
    ) -> str:
        target = _resolve_path(base, path)
        if target.is_dir():
            _ensure_directory(target)
        else:
            _ensure_file(target)

        if shutil.which("rg"):
            return _run_rg(pattern, target, ignore_case, max_matches)
        return _python_search(pattern, target, ignore_case, max_matches)

    @function_tool(name_override="run_safe_command")
    def run_safe_command(
        command: Annotated[str, "Command to execute. Supported: ls, cat, head, tail, wc, sort."] ,
        arguments: Annotated[tuple[str, ...], "Command arguments, without the program name."] = (),
        cwd: Annotated[str | None, "Working directory relative to the workspace root."] = None,
    ) -> str:
        allowed = {"ls", "cat", "head", "tail", "wc", "sort"}
        if command not in allowed:
            raise ValueError(f"Command '{command}' is not permitted. Allowed commands: {sorted(allowed)}")
        args = list(arguments)
        if any(arg.startswith("--delete") or arg in {"-f", "--force"} for arg in args):
            raise ValueError("Dangerous flags detected; please omit destructive options.")

        target_cwd = _ensure_directory(_resolve_path(base, cwd)) if cwd else base
        try:
            completed = subprocess.run(
                [command, *args],
                cwd=target_cwd,
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError:
            raise ValueError(f"Command not available in PATH: {command}")

        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip()
            raise ValueError(f"{command} exited with code {completed.returncode}: {detail}")

        output = completed.stdout.strip()
        return output if output else "(no output)"

    instructions = dedent(
        """
        You are a careful local shell assistant operating inside a development workspace.
        Use the provided tools to inspect directories, read or edit files, and run a limited
        set of safe shell commands such as `ls`, `cat`, `head`, `tail`, `wc`, and `sort`.

        Safety rules:
        - Never run git commands, package managers, or anything that modifies global state.
        - Never delete, move, or rename files. The tooling here only supports additive changes.
        - Stay within the workspace root. Reject paths that escape it.
        - Prefer targeted reads (specify line ranges) to avoid returning huge files.
        - Ask for clarification if you are unsure which file or directory to inspect.
        """
    ).strip()

    agent_kwargs = {
        "name": "Restricted Shell Assistant",
        "instructions": instructions,
        "tools": [
            list_directory,
            print_working_directory,
            read_file,
            write_file,
            append_file,
            search_text,
            run_safe_command,
        ],
    }
    if model:
        agent_kwargs["model"] = model
    return Agent(**agent_kwargs)


__all__ = ["create_shell_agent"]
