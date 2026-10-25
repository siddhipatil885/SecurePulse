import { Text, View } from 'react-native';
import { router } from 'expo-router';
import { useCameras } from '../api/queries';
import { useAuth } from '../auth/AuthProvider';
import { Screen } from '../components/Screen';
import { PrimaryButton } from '../components/PrimaryButton';
import { Notice, PropertyBanner, QueryState, ui } from '../components/Content';
export function CamerasScreen() {
  const { propertyId } = useAuth();
  const cameras = useCameras();
  return <Screen>
    <Text style={ui.title}>Your cameras</Text><PropertyBanner />
    <PrimaryButton variant="secondary" label="Refresh cameras" disabled={!propertyId || cameras.isFetching} onPress={() => void cameras.refetch()} />
    <QueryState query={cameras} empty={!cameras.data?.length} />
    {!cameras.isError && cameras.data?.map(camera => <View key={camera.id} style={ui.card}>
      <Text style={ui.heading}>{camera.name}</Text>
      <Notice>{camera.location ?? 'No location provided'}</Notice>
      <Notice>{camera.enabled ? 'Enabled' : 'Disabled'} · Connection unverified</Notice>
      <PrimaryButton variant="secondary" label="Camera details" onPress={() => router.push({ pathname: '/cameras/[id]', params: { id: camera.id } })} />
    </View>)}
  </Screen>;
}
