import { Text } from 'react-native';
import { useCameras, useEvents } from '../api/queries';
import { useAuth } from '../auth/AuthProvider';
import { Screen } from '../components/Screen';
import { PrimaryButton } from '../components/PrimaryButton';
import { EventCard, PropertyBanner, QueryState, ui } from '../components/Content';
export function ActivityScreen() {
  const { propertyId } = useAuth();
  const events = useEvents(); const cameras = useCameras();
  const items = events.data?.pages.flatMap(page => page.items) ?? [];
  return <Screen>
    <Text style={ui.title}>Security alerts</Text><PropertyBanner />
    <PrimaryButton variant="secondary" label={events.isFetching ? 'Refreshing…' : 'Refresh alerts'} disabled={!propertyId || events.isFetching} onPress={() => { void events.refetch(); void cameras.refetch(); }} />
    <QueryState query={events} empty={!items.length} />
    {!events.isError && items.map(event => <EventCard key={event.id} event={event} cameraName={cameras.data?.find(c => c.id === event.camera_id)?.name} />)}
    {events.hasNextPage && <PrimaryButton label={events.isFetchingNextPage ? 'Loading…' : 'Load more'} disabled={events.isFetching} onPress={() => void events.fetchNextPage()} />}
  </Screen>;
}
