import { Pressable, StyleSheet, Text } from 'react-native';

interface PrimaryButtonProps {
  label: string;
  onPress: () => void;
  disabled?: boolean;
  variant?: 'primary' | 'secondary';
}

export function PrimaryButton({ label, onPress, disabled = false, variant = 'primary' }: PrimaryButtonProps) {
  return (
    <Pressable
      accessibilityRole="button"
      disabled={disabled}
      onPress={onPress}
      style={({ pressed }) => [
        styles.button,
        variant === 'secondary' && styles.secondary,
        pressed && styles.pressed,
        disabled && styles.disabled,
      ]}
    >
      <Text style={[styles.label, variant === 'secondary' && styles.secondaryLabel]}>{label}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  button: { alignItems: 'center', backgroundColor: '#0f766e', borderRadius: 10, padding: 14 },
  pressed: { opacity: 0.8 },
  disabled: { opacity: 0.5 },
  label: { color: '#ffffff', fontSize: 16, fontWeight: '700' },
  secondary: { backgroundColor: '#ffffff', borderColor: '#0f766e', borderWidth: 1 },
  secondaryLabel: { color: '#0f766e' },
});
