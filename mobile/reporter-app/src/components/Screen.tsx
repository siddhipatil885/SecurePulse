import { type PropsWithChildren } from 'react';
import { KeyboardAvoidingView, Platform, RefreshControl, ScrollView, StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

interface ScreenProps extends PropsWithChildren {
  refreshing?: boolean;
  onRefresh?: () => void;
}

export function Screen({ children, refreshing = false, onRefresh }: ScreenProps) {
  const insets = useSafeAreaInsets();
  return (
    <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined} keyboardVerticalOffset={100}>
    <ScrollView
      keyboardShouldPersistTaps="handled"
      refreshControl={onRefresh ? <RefreshControl refreshing={refreshing} onRefresh={onRefresh} /> : undefined}
      contentContainerStyle={[styles.content, { paddingBottom: insets.bottom }]}
    >
      <View style={styles.container}>{children}</View>
    </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  content: { flexGrow: 1 },
  container: { padding: 20, gap: 16 },
});
