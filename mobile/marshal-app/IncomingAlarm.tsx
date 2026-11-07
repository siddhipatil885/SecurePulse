import { useEffect, useState } from 'react';
import { AppState, Pressable, Text, Vibration, View } from 'react-native';
import { setAudioModeAsync, useAudioPlayer, useAudioPlayerStatus } from 'expo-audio';

export function IncomingAlarm({ offerIds }: { offerIds: number[] }) {
  const player = useAudioPlayer(require('./assets/assignment-alarm.wav'));
  const status = useAudioPlayerStatus(player);
  const [foreground, setForeground] = useState(AppState.currentState === 'active');
  const [muted, setMuted] = useState<number[]>([]);
  const [soundError, setSoundError] = useState(false);
  const audible = foreground && offerIds.some(id => !muted.includes(id));
  useEffect(() => { const sub = AppState.addEventListener('change', value => setForeground(value === 'active')); return () => sub.remove(); }, []);
  useEffect(() => {
    if (!status.isLoaded) return;
    let active = true;
    if (audible) {
      void setAudioModeAsync({ playsInSilentMode: true, shouldPlayInBackground: false, interruptionMode: 'doNotMix' }).then(() => {
        if (!active) return;
        try { player.loop = true; player.volume = 1; player.play(); setSoundError(false); }
        catch { setSoundError(true); }
      }).catch(() => { if (active) setSoundError(true); });
      Vibration.vibrate([0, 450, 250, 450, 800], true);
    } else player.pause();
    return () => { active = false; player.pause(); Vibration.cancel(); };
  }, [audible, status.isLoaded, player]);
  if (!offerIds.length) return null;
  return <View accessibilityLiveRegion="assertive" style={{ backgroundColor: '#FFF0E8', padding: 18, borderRadius: 18, gap: 10 }}>
    <Text style={{ color: '#91371E', fontSize: 18, fontWeight: '800' }}>New response requested</Text>
    <Text>Accept or decline within 5 minutes. Another marshal may accept first.</Text>
    {soundError && <Text>Audio could not start. Check your phone’s media volume.</Text>}
    <Pressable accessibilityRole="button" onPress={() => setMuted(audible ? offerIds : [])} style={{ padding: 14, backgroundColor: '#FFF', borderRadius: 10 }}><Text style={{ fontWeight: '800' }}>{audible ? 'Silence alert' : 'Sound alert again'}</Text></Pressable>
  </View>;
}
