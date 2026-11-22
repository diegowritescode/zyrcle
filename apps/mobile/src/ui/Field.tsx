import { StyleSheet, Text, TextInput, View, type TextInputProps } from "react-native";
import { colors, radius, space } from "./theme";

type FieldProps = TextInputProps & { label: string; hint?: string };

/** A labelled text input in the app's style. */
export function Field({ label, hint, style, ...props }: FieldProps) {
  return (
    <View style={{ gap: space(1) }}>
      <Text style={styles.label}>{label}</Text>
      <TextInput
        placeholderTextColor={colors.muted}
        accessibilityLabel={label}
        style={[styles.input, style]}
        {...props}
      />
      {hint && <Text style={styles.hint}>{hint}</Text>}
    </View>
  );
}

const styles = StyleSheet.create({
  label: { fontSize: 13, fontWeight: "600", color: colors.textSoft },
  input: {
    minHeight: 48,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    backgroundColor: colors.white,
    paddingHorizontal: space(3),
    fontSize: 16,
    color: colors.forestDark,
  },
  hint: { fontSize: 12, color: colors.muted },
});
