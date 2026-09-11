import React from 'react';
import { Box, Text } from 'ink';
import TextInput from 'ink-text-input';

export type PromptProps = {
  value: string;
  onChange: (value: string) => void;
  onSubmit: (value: string) => void;
  /** False while a prompt elsewhere owns the keyboard. */
  focus: boolean;
  busy: boolean;
};

/**
 * Stays mounted while the agent works so typing ahead is not lost;
 * submission is gated by the caller until the runtime is idle.
 */
export function Prompt({
  value,
  onChange,
  onSubmit,
  focus,
  busy,
}: PromptProps): React.ReactElement {
  return (
    <Box>
      <Text color={busy ? 'gray' : 'cyan'} bold>
        {'> '}
      </Text>
      <TextInput value={value} onChange={onChange} onSubmit={onSubmit} focus={focus} />
    </Box>
  );
}
