declare module 'pyodide' {
  export interface PyodideInterface {
    loadPackage(packages: string[]): Promise<void>;
    pyimport(name: string): {
      install(pkg: string): Promise<void>;
    };
    runPythonAsync(code: string): Promise<unknown>;
    setStdout(options: { batched: (text: string) => void }): void;
    setStderr(options: { batched: (text: string) => void }): void;
    FS: {
      writeFile(path: string, content: string): void;
      readFile(path: string, options?: { encoding?: string }): string | Uint8Array;
      readdir(path: string): string[];
      stat(path: string): { mode: number };
      isFile(mode: number): boolean;
    };
  }

  export interface LoadPyodideOptions {
    stdout?: (text: string) => void;
    stderr?: (text: string) => void;
    indexURL?: string;
  }

  export function loadPyodide(options?: LoadPyodideOptions): Promise<PyodideInterface>;
}
