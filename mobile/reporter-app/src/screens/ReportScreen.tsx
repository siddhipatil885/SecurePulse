import { Text } from 'react-native';
import { useLocalSearchParams } from 'expo-router';
import { Screen } from '../components/Screen';
import { PrimaryButton } from '../components/PrimaryButton';
import { Notice, PropertyBanner, ui } from '../components/Content';
export function ReportScreen() {
  const { eventId } = useLocalSearchParams<{ eventId?: string }>();
  return <Screen><Text style={ui.title}>Report an incident</Text><PropertyBanner />
    {eventId && <Notice>Opened from alert #{eventId}.</Notice>}
    <Notice>Incident reporting is not available yet. The server does not support manual reports or alert confirmation.</Notice>
    <PrimaryButton label="Submit incident — unavailable" onPress={() => {}} disabled />
    <Notice>No report has been submitted. Automated detections do not notify or dispatch marshals.</Notice>
  </Screen>;
}
