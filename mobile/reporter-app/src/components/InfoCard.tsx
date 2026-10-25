import { StyleSheet, Text, View } from 'react-native';

interface InfoCardProps {
  label: string;
  value: string;
  detail?: string;
}

export function InfoCard({ label, value, detail }: InfoCardProps) {
  return (
    <View style={styles.card}>
      <Text style={styles.label}>{label}</Text>
      <Text style={styles.value}>{value}</Text>
      {detail ? <Text style={styles.detail}>{detail}</Text> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  card: { backgroundColor: '#ffffff', borderColor: '#e2e8f0', borderRadius: 12, borderWidth: 1, padding: 16 },
  label: { color: '#64748b', fontSize: 13, fontWeight: '600', textTransform: 'uppercase' },
  value: { color: '#0f172a', fontSize: 28, fontWeight: '800', marginTop: 6 },
  detail: { color: '#64748b', fontSize: 13, marginTop: 4 },
});
