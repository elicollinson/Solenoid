import { useState, useCallback, useEffect } from 'react';
import { Box, Text, useInput } from 'ink';
import TextInput from 'ink-text-input';
import { getSettingsManager, type SectionInfo, type SectionKey } from '../../config/index.js';

type ScreenMode = 'selecting' | 'editing';

interface SettingsScreenProps {
  onClose: () => void;
  onSettingsChanged?: () => void;
}

export function SettingsScreen({ onClose, onSettingsChanged }: SettingsScreenProps) {
  const [mode, setMode] = useState<ScreenMode>('selecting');
  const [sections, setSections] = useState<SectionInfo[]>([]);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [currentSection, setCurrentSection] = useState<SectionKey | null>(null);
  const [originalYaml, setOriginalYaml] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [cursorLine, setCursorLine] = useState(0);
  const [editLines, setEditLines] = useState<string[]>(['']);
  const [settingsExist, setSettingsExist] = useState(true);

  const manager = getSettingsManager();

  // Load sections on mount
  useEffect(() => {
    try {
      if (!manager.settingsExist()) {
        setSettingsExist(false);
        return;
      }
      const sectionInfos = manager.getAllSectionsInfo();
      setSections(sectionInfos);
    } catch {
      setSettingsExist(false);
    }
  }, [manager]);

  const clearMessages = useCallback(() => {
    setError(null);
    setSuccess(null);
  }, []);

  const openEditor = useCallback(
    (sectionKey: SectionKey) => {
      clearMessages();
      setCurrentSection(sectionKey);
      const yaml = manager.getSectionAsYaml(sectionKey);
      setOriginalYaml(yaml);
      setEditLines(yaml.split('\n'));
      setCursorLine(0);
      setMode('editing');
    },
    [manager, clearMessages]
  );

  const closeEditor = useCallback(() => {
    clearMessages();
    setCurrentSection(null);
    setEditLines(['']);
    setCursorLine(0);
    setMode('selecting');
  }, [clearMessages]);

  const saveCurrentSection = useCallback(() => {
    if (!currentSection) return;

    clearMessages();
    const yaml = editLines.join('\n');
    const result = manager.updateSection(currentSection, yaml);

    if (result.isValid) {
      setSuccess('Settings saved successfully!');
      setOriginalYaml(yaml);
      onSettingsChanged?.();
    } else {
      const errorMsg = result.errors[0]?.message ?? 'Validation failed';
      const errorPath = result.errors[0]?.path;
      setError(errorPath ? `${errorPath}: ${errorMsg}` : errorMsg);
    }
  }, [currentSection, editLines, manager, clearMessages, onSettingsChanged]);

  const hasChanges = useCallback(() => {
    return editLines.join('\n') !== originalYaml;
  }, [editLines, originalYaml]);

  // Handle input for section selection mode
  useInput(
    (_input, key) => {
      if (mode === 'selecting') {
        if (key.escape) {
          onClose();
          return;
        }

        if (key.upArrow) {
          setSelectedIndex((prev) => (prev > 0 ? prev - 1 : sections.length - 1));
          return;
        }

        if (key.downArrow) {
          setSelectedIndex((prev) => (prev < sections.length - 1 ? prev + 1 : 0));
          return;
        }

        if (key.return && sections[selectedIndex]) {
          openEditor(sections[selectedIndex].key);
          return;
        }
      }
    },
    { isActive: mode === 'selecting' }
  );

  // Handle input for editing mode
  useInput(
    (input, key) => {
      if (mode === 'editing') {
        // Escape to go back
        if (key.escape) {
          closeEditor();
          return;
        }

        // Ctrl+S to save
        if (key.ctrl && input === 's') {
          saveCurrentSection();
          return;
        }

        // Navigate lines
        if (key.upArrow) {
          setCursorLine((prev) => Math.max(0, prev - 1));
          return;
        }

        if (key.downArrow) {
          setCursorLine((prev) => Math.min(editLines.length - 1, prev + 1));
          return;
        }

        // Add new line
        if (key.return) {
          clearMessages();
          const newLines = [...editLines];
          newLines.splice(cursorLine + 1, 0, '');
          setEditLines(newLines);
          setCursorLine(cursorLine + 1);
          return;
        }

        // Delete line (backspace at start of empty line)
        if (key.backspace && editLines[cursorLine] === '' && editLines.length > 1) {
          clearMessages();
          const newLines = editLines.filter((_, i) => i !== cursorLine);
          setEditLines(newLines);
          setCursorLine(Math.max(0, cursorLine - 1));
          return;
        }
      }
    },
    { isActive: mode === 'editing' }
  );

  // Handle line text changes
  const handleLineChange = useCallback(
    (value: string) => {
      clearMessages();
      const newLines = [...editLines];
      newLines[cursorLine] = value;
      setEditLines(newLines);
    },
    [cursorLine, editLines, clearMessages]
  );

  // Render no settings state
  if (!settingsExist) {
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

  // Render section selection mode
  if (mode === 'selecting') {
    return (
      <Box flexDirection="column" padding={1}>
        <Text bold color="yellow">
          Settings
        </Text>
        <Text dimColor>Use ↑↓ to navigate, Enter to edit, Esc to close</Text>

        <Box marginTop={1} flexDirection="column">
          {sections.map((section, index) => (
            <Box key={section.key}>
              <Text
                color={index === selectedIndex ? 'cyan' : undefined}
                bold={index === selectedIndex}
              >
                {index === selectedIndex ? '❯ ' : '  '}
                {section.displayName}
              </Text>
            </Box>
          ))}
        </Box>

        {sections[selectedIndex] && (
          <Box marginTop={1}>
            <Text dimColor>{sections[selectedIndex].description}</Text>
          </Box>
        )}
      </Box>
    );
  }

  // Render editing mode
  const sectionInfo = currentSection ? manager.getSectionInfo(currentSection) : null;

  return (
    <Box flexDirection="column" padding={1}>
      <Text bold color="yellow">
        Editing: {sectionInfo?.displayName ?? currentSection}
      </Text>
      <Text dimColor>{sectionInfo?.description}</Text>
      <Text dimColor>↑↓ navigate lines, Enter new line, Ctrl+S save, Esc back</Text>

      <Box marginTop={1} flexDirection="column" borderStyle="single" borderColor="gray" padding={1}>
        {editLines.map((line, index) => (
          <Box key={index}>
            <Text dimColor>{String(index + 1).padStart(3, ' ')} </Text>
            {index === cursorLine ? (
              <TextInput value={line} onChange={handleLineChange} />
            ) : (
              <Text>{line || ' '}</Text>
            )}
          </Box>
        ))}
      </Box>

      {error && (
        <Box marginTop={1}>
          <Text color="red">Error: {error}</Text>
        </Box>
      )}

      {success && (
        <Box marginTop={1}>
          <Text color="green">{success}</Text>
        </Box>
      )}

      <Box marginTop={1}>
        <Text dimColor>
          {hasChanges() ? '● Modified' : '○ No changes'}
        </Text>
      </Box>
    </Box>
  );
}
