/**
 * Settings Screen Component
 *
 * Overlay screen displaying current configuration from app_settings.yaml.
 * Shows model settings, embedding configuration, MCP servers, and
 * per-agent model overrides. Closes on Enter or Escape key press.
 */
import { useState, useCallback, useMemo } from 'react';
import { Box, Text, useInput } from 'ink';
import { TextInput } from '@inkjs/ui';
import {
  getAllSections,
  getSectionAsYaml,
  updateSection,
  validateSectionYaml,
  type SectionInfo,
} from '../../config/settingsManager.js';
import type { ValidationResult } from '../../config/validator.js';

interface SettingsScreenProps {
  onClose: () => void;
}

interface EditorLine {
  content: string;
  indent: number;
}

type Mode = 'selection' | 'editing' | 'line-edit';

function parseYamlToLines(yaml: string): EditorLine[] {
  if (!yaml.trim()) return [{ content: '', indent: 0 }];

  return yaml.split('\n').map((line) => {
    const match = line.match(/^(\s*)/);
    const indent = match?.[1]?.length ?? 0;
    return {
      content: line.trimStart(),
      indent,
    };
  });
}

function linesToYaml(lines: EditorLine[]): string {
  return lines.map((line) => ' '.repeat(line.indent) + line.content).join('\n');
}

export function SettingsScreen({ onClose }: SettingsScreenProps) {
  const [sections] = useState<SectionInfo[]>(() => getAllSections());
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [mode, setMode] = useState<Mode>('selection');

  // Editor state
  const [editingSection, setEditingSection] = useState<string | null>(null);
  const [lines, setLines] = useState<EditorLine[]>([]);
  const [currentLineIndex, setCurrentLineIndex] = useState(0);
  const [editBuffer, setEditBuffer] = useState('');
  const [inputKey, setInputKey] = useState(0);

  // Feedback
  const [message, setMessage] = useState<{ text: string; type: 'success' | 'error' } | null>(null);
  const [validationResult, setValidationResult] = useState<ValidationResult | null>(null);
  const [showHelp, setShowHelp] = useState(false);

  // Calculate visible lines (show lines around current)
  const visibleRange = useMemo(() => {
    const maxVisible = 12;
    const start = Math.max(0, currentLineIndex - Math.floor(maxVisible / 2));
    const end = Math.min(lines.length, start + maxVisible);
    return { start, end };
  }, [currentLineIndex, lines.length]);

  const startEditing = useCallback((section: SectionInfo) => {
    const yaml = getSectionAsYaml(section.key);
    setEditingSection(section.key);
    setLines(parseYamlToLines(yaml));
    setCurrentLineIndex(0);
    setMode('editing');
    setMessage(null);
    setValidationResult(null);
  }, []);

  const handleSave = useCallback(() => {
    if (!editingSection) return;

    const yaml = linesToYaml(lines);
    const result = updateSection(editingSection, yaml);

    if (result.isValid) {
      setMessage({ text: 'Saved successfully', type: 'success' });
      setValidationResult(null);
    } else {
      setMessage({ text: result.errors[0]?.message || 'Validation failed', type: 'error' });
      setValidationResult(result);
    }
  }, [editingSection, lines]);

  const handleValidate = useCallback(() => {
    if (!editingSection) return;

    const yaml = linesToYaml(lines);
    const result = validateSectionYaml(editingSection, yaml);

    if (result.isValid) {
      setMessage({ text: 'Valid YAML', type: 'success' });
      setValidationResult(null);
    } else {
      setMessage({ text: result.errors[0]?.message || 'Invalid', type: 'error' });
      setValidationResult(result);
    }
  }, [editingSection, lines]);

  const addChildLine = useCallback(() => {
    const currentIndent = lines[currentLineIndex]?.indent ?? 0;
    const newLine: EditorLine = { content: '', indent: currentIndent + 2 };
    const newLines = [...lines];
    newLines.splice(currentLineIndex + 1, 0, newLine);
    setLines(newLines);
    setCurrentLineIndex(currentLineIndex + 1);
    setEditBuffer('');
    setInputKey((k) => k + 1);
    setMode('line-edit');
  }, [currentLineIndex, lines]);

  const addSiblingLine = useCallback(() => {
    const currentIndent = lines[currentLineIndex]?.indent ?? 0;
    const newLine: EditorLine = { content: '', indent: currentIndent };
    const newLines = [...lines];
    newLines.splice(currentLineIndex + 1, 0, newLine);
    setLines(newLines);
    setCurrentLineIndex(currentLineIndex + 1);
    setEditBuffer('');
    setInputKey((k) => k + 1);
    setMode('line-edit');
  }, [currentLineIndex, lines]);

  const deleteLine = useCallback(() => {
    if (lines.length <= 1) {
      // Don't delete the last line, just clear it
      setLines([{ content: '', indent: 0 }]);
      return;
    }
    const newLines = lines.filter((_, i) => i !== currentLineIndex);
    setLines(newLines);
    if (currentLineIndex >= newLines.length) {
      setCurrentLineIndex(Math.max(0, newLines.length - 1));
    }
  }, [currentLineIndex, lines]);

  const startLineEdit = useCallback(() => {
    setEditBuffer(lines[currentLineIndex]?.content || '');
    setInputKey((k) => k + 1);
    setMode('line-edit');
  }, [currentLineIndex, lines]);

  const confirmLineEdit = useCallback((value?: string) => {
    const contentToSave = value ?? editBuffer;
    const newLines = [...lines];
    const currentLine = newLines[currentLineIndex];
    if (currentLine) {
      newLines[currentLineIndex] = {
        indent: currentLine.indent,
        content: contentToSave,
      };
    }
    setLines(newLines);
    setMode('editing');
    // Move to next line
    if (currentLineIndex < lines.length - 1) {
      setCurrentLineIndex(currentLineIndex + 1);
    }
  }, [currentLineIndex, editBuffer, lines]);

  const cancelLineEdit = useCallback(() => {
    setMode('editing');
  }, []);

  const backToSelection = useCallback(() => {
    setMode('selection');
    setEditingSection(null);
    setLines([]);
    setMessage(null);
    setValidationResult(null);
  }, []);

  useInput((input, key) => {
    // Clear message on any input
    if (message) setMessage(null);

    if (mode === 'selection') {
      if (key.escape) {
        onClose();
        return;
      }
      if (key.upArrow) {
        setSelectedIndex((i) => Math.max(0, i - 1));
        return;
      }
      if (key.downArrow) {
        setSelectedIndex((i) => Math.min(sections.length - 1, i + 1));
        return;
      }
      if (key.return) {
        if (sections[selectedIndex]) {
          startEditing(sections[selectedIndex]);
        }
        return;
      }
    }

    if (mode === 'editing') {
      if (input === '?') {
        setShowHelp((h) => !h);
        return;
      }
      if (key.escape) {
        if (showHelp) {
          setShowHelp(false);
          return;
        }
        backToSelection();
        return;
      }
      if (key.upArrow) {
        setCurrentLineIndex((i) => Math.max(0, i - 1));
        return;
      }
      if (key.downArrow) {
        setCurrentLineIndex((i) => Math.min(lines.length - 1, i + 1));
        return;
      }
      if (key.return) {
        startLineEdit();
        return;
      }
      if (key.tab && !key.shift) {
        addChildLine();
        return;
      }
      if (key.tab && key.shift) {
        addSiblingLine();
        return;
      }
      if (key.delete || key.backspace) {
        if (!lines[currentLineIndex]?.content) {
          deleteLine();
        }
        return;
      }
      if (key.ctrl && input === 's') {
        handleSave();
        return;
      }
      if (key.ctrl && input === 'v') {
        handleValidate();
        return;
      }
    }

    if (mode === 'line-edit') {
      if (key.escape) {
        cancelLineEdit();
        return;
      }
      if (key.return) {
        confirmLineEdit();
        return;
      }
    }
  });

  // No sections found
  if (sections.length === 0) {
    return (
      <Box flexDirection="column" padding={1}>
        <Text bold color="yellow">
          Settings
        </Text>
        <Box marginTop={1}>
          <Text color="red">No settings file found. Create app_settings.yaml to configure.</Text>
        </Box>
        <Box marginTop={1}>
          <Text dimColor>Press Esc to close</Text>
        </Box>
      </Box>
    );
  }

  // Selection mode
  if (mode === 'selection') {
    return (
      <Box flexDirection="column" padding={1}>
        <Text bold color="yellow">
          Settings - Select Section
        </Text>

        <Box marginTop={1} flexDirection="column">
          {sections.map((section, index) => (
            <Box key={section.key}>
              <Text color={index === selectedIndex ? 'cyan' : undefined}>
                {index === selectedIndex ? '>' : ' '} {section.displayName}
                <Text dimColor> - {section.description}</Text>
                {section.hasValidator && <Text color="green"> [validated]</Text>}
              </Text>
            </Box>
          ))}
        </Box>

        <Box marginTop={2}>
          <Text dimColor>
            ↑↓: Navigate | Enter: Edit | Esc: Close
          </Text>
        </Box>
      </Box>
    );
  }

  // Editing mode (including line-edit)
  const currentSection = sections.find((s) => s.key === editingSection);

  return (
    <Box flexDirection="column" padding={1}>
      <Text bold color="yellow">
        Editing: {currentSection?.displayName || editingSection}
      </Text>

      <Box marginTop={1} flexDirection="column" borderStyle="single" paddingX={1}>
        {lines.slice(visibleRange.start, visibleRange.end).map((line, displayIndex) => {
          const actualIndex = visibleRange.start + displayIndex;
          const isCurrentLine = actualIndex === currentLineIndex;
          const isEditing = isCurrentLine && mode === 'line-edit';

          return (
            <Box key={actualIndex}>
              <Text color={isCurrentLine ? 'cyan' : undefined}>
                {isCurrentLine ? '>' : ' '}
              </Text>
              <Text dimColor>{String(actualIndex + 1).padStart(3, ' ')} </Text>
              {isEditing ? (
                <Box>
                  <Text>{' '.repeat(line.indent)}</Text>
                  <TextInput
                    key={inputKey}
                    defaultValue={editBuffer}
                    onChange={setEditBuffer}
                    onSubmit={confirmLineEdit}
                  />
                </Box>
              ) : (
                <Text color={isCurrentLine ? 'cyan' : undefined}>
                  {' '.repeat(line.indent)}
                  {line.content || (isCurrentLine ? <Text dimColor>(empty)</Text> : '')}
                </Text>
              )}
            </Box>
          );
        })}

        {lines.length > visibleRange.end && (
          <Text dimColor>... {lines.length - visibleRange.end} more lines</Text>
        )}
      </Box>

      {/* Help panel */}
      {showHelp && (
        <Box marginTop={1} flexDirection="column" borderStyle="round" borderColor="cyan" paddingX={1}>
          <Text bold color="cyan">Keyboard Shortcuts</Text>
          <Box marginTop={1} flexDirection="column">
            <Text><Text bold>Navigation</Text></Text>
            <Text>  ↑/↓         Move between lines</Text>
            <Text>  Enter       Edit current line</Text>
            <Text>  Esc         Back to section list</Text>
            <Text/>
            <Text><Text bold>Editing</Text></Text>
            <Text>  Tab         Add indented child line</Text>
            <Text>  Shift+Tab   Add sibling line (same indent)</Text>
            <Text>  Del         Delete empty line</Text>
            <Text/>
            <Text><Text bold>Actions</Text></Text>
            <Text>  Ctrl+S      Save changes</Text>
            <Text>  Ctrl+V      Validate YAML</Text>
            <Text>  ?           Toggle this help</Text>
            <Text/>
            <Text><Text bold>Line Editing Mode</Text></Text>
            <Text>  Enter       Confirm edit, move to next</Text>
            <Text>  Esc         Cancel edit</Text>
          </Box>
          <Box marginTop={1}>
            <Text dimColor>Press ? or Esc to close</Text>
          </Box>
        </Box>
      )}

      {/* Validation errors */}
      {validationResult && !validationResult.isValid && (
        <Box marginTop={1}>
          <Text color="red">
            Errors:
          </Text>
          {validationResult.errors.slice(0, 3).map((err, i) => (
            <Text key={i} color="red">
              {' '}
              {err.path ? `${err.path}: ` : ''}
              {err.message}
            </Text>
          ))}
        </Box>
      )}

      {/* Success/error message */}
      {message && (
        <Box marginTop={1}>
          <Text color={message.type === 'success' ? 'green' : 'red'}>
            {message.text}
          </Text>
        </Box>
      )}

      {/* Help text */}
      <Box marginTop={1} flexDirection="column">
        {mode === 'line-edit' ? (
          <Text dimColor>Enter: Confirm | Esc: Cancel</Text>
        ) : (
          <Text dimColor>
            Ctrl+S: Save | Ctrl+V: Validate | <Text color="cyan">?: Help</Text> | Esc: Back
          </Text>
        )}
      </Box>
    </Box>
  );
}
