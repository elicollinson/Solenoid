# Settings Editor Functional Tests

## Prerequisites
- Have a valid `app_settings.yaml` file in the project root
- Run the UI with `npm run dev:ui` or `npm run start:ui`

## Test Cases

### 1. Opening Settings Screen
- [ ] Type `/settings` in the chat input
- [ ] Verify the settings screen appears with a list of sections
- [ ] Verify all sections are displayed: Models, Search, MCP Servers, Agent Prompts, Embeddings

### 2. Section Navigation
- [ ] Use arrow keys (↑↓) to navigate between sections
- [ ] Verify the selected section is highlighted in cyan
- [ ] Verify the description updates as you navigate to each section
- [ ] Press Escape to close the settings screen and return to chat

### 3. Opening Section Editor
- [ ] Navigate to a section and press Enter
- [ ] Verify the YAML editor opens with the section content
- [ ] Verify line numbers are displayed
- [ ] Verify the section name and description are shown at the top

### 4. YAML Editing
- [ ] Navigate between lines using arrow keys (↑↓)
- [ ] Edit text on a line and verify it updates
- [ ] Press Enter to create a new line
- [ ] Verify the "Modified" indicator appears after making changes
- [ ] Delete an empty line with backspace

### 5. Saving Valid Changes
- [ ] Make a valid change to a section (e.g., change a model name)
- [ ] Press Ctrl+S to save
- [ ] Verify "Settings saved successfully!" message appears
- [ ] Press Escape to go back to section list
- [ ] Re-open the section and verify changes persisted

### 6. Validation Errors
- [ ] Open the Models section
- [ ] Remove the `name` field from default model config
- [ ] Press Ctrl+S to save
- [ ] Verify an error message appears about missing 'name' field
- [ ] Fix the error and save again successfully

### 7. Invalid YAML Syntax
- [ ] Open any section
- [ ] Add invalid YAML (e.g., unmatched quotes, bad indentation)
- [ ] Press Ctrl+S to save
- [ ] Verify a YAML syntax error message appears

### 8. Section-Specific Validation

#### Models Section
- [ ] Verify `provider` must be one of: ollama_chat, ollama, openai, anthropic, litellm
- [ ] Verify `context_length` must be a positive integer

#### Search Section
- [ ] Verify `provider` must be one of: brave, google, duckduckgo, serper, none

#### MCP Servers Section
- [ ] Verify stdio servers require a `command` field
- [ ] Verify http servers require a `url` field

#### Agent Prompts Section
- [ ] Verify prompts must be strings
- [ ] Verify prompts must be at least 10 characters

### 9. Backup and Recovery
- [ ] Make and save a change
- [ ] Verify `app_settings.yaml.bak` backup file was created
- [ ] Verify backup contains the previous settings

### 10. No Settings File
- [ ] Rename/remove `app_settings.yaml`
- [ ] Open settings screen
- [ ] Verify error message: "No settings file found"
- [ ] Restore the settings file

### 11. Navigation Flow
- [ ] Open settings → select section → edit → Escape (back to list)
- [ ] Verify you return to section selection, not chat
- [ ] Press Escape again to return to chat
- [ ] Verify chat screen is displayed

### 12. Settings Reload
- [ ] Save a change to settings
- [ ] Verify the app reloads settings (check logs for "Settings reloaded successfully")
