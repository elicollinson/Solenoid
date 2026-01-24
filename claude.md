# Claude Code Configuration

This file provides guidance for AI agents working on the Solenoid codebase.

## Verification Workflow

Before pushing any code changes, you **must** complete the following verification steps in order:

### 1. Run the Code Simplifier Plugin

After making any code changes, always start by running the code simplifier plugin to ensure the code is clean and follows best practices:

```bash
poetry run python -m app.plugins.code_simplifier
```

### 2. Run the Linter

Check for code style issues and potential errors:

```bash
poetry run ruff check .
```

To automatically fix issues:

```bash
poetry run ruff check --fix .
```

### 3. Run the Typechecker

Verify type correctness across the codebase:

```bash
poetry run mypy app/
```

### 4. Run Unit Tests

Execute the test suite to ensure all tests pass:

```bash
poetry run pytest tests/
```

### 5. Functional Testing with Agent Harness

Use the agent harness to functionally test your changes before pushing:

```bash
poetry run python -m tests.eval.run_eval
```

## Verification Checklist

Before pushing code, confirm all of the following:

- [ ] Code simplifier plugin has been run
- [ ] Linter passes with no errors
- [ ] Typechecker passes with no errors
- [ ] All unit tests pass
- [ ] Functional tests via agent harness pass

## Important Notes

- **Never push code that fails any verification step**
- If any step fails, fix the issues and re-run the entire verification workflow
- When in doubt, run the full verification suite again before pushing
