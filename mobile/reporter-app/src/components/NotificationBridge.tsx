import { useEffect } from 'react';
import type { NotificationResponse } from 'expo-notifications';
import { router } from 'expo-router';
import { api, queryClient, useAuth } from '../auth/AuthProvider';
import { notificationTarget } from '../api/notificationTarget';
import { isExpoGo, loadNotifications, registerPush } from '../notifications';

export function NotificationBridge() {
  const { state, selectProperty } = useAuth();
  const profile = state.profile;
  useEffect(() => {
    if (!profile || isExpoGo) return;
    let active = true;
    const subscriptions: { remove(): void }[] = [];
    void (async () => {
      const Notifications = await loadNotifications();
      if (!active) return;
      Notifications.setNotificationHandler({ handleNotification: async () => ({
        shouldShowBanner: true, shouldShowList: true, shouldPlaySound: true, shouldSetBadge: false,
      }) });
      const refresh = () => { void queryClient.invalidateQueries(); };
      const open = (response: NotificationResponse) => {
        const target = notificationTarget(response.notification.request.content.data, profile.id, profile.properties);
        if (!active || !target) return;
        selectProperty(target.propertyId); refresh();
        if (target.pathname === '/') router.push('/');
        else router.push({ pathname: target.pathname, params: { id: target.id! } });
        void Notifications.clearLastNotificationResponseAsync().catch(() => {});
      };
      subscriptions.push(Notifications.addNotificationReceivedListener(refresh));
      subscriptions.push(Notifications.addNotificationResponseReceivedListener(open));
      void Notifications.getLastNotificationResponseAsync().then(response => { if (response) open(response); }).catch(() => {});
      void api.notificationPreferences().then(preferences => {
        if (active && preferences.some(p => p.enabled)) return registerPush(api, false);
      }).catch(() => { /* Settings exposes registration errors without blocking sign-in. */ });
      subscriptions.push(Notifications.addPushTokenListener(() => { if (active) void registerPush(api, false).catch(() => {}); }));
    })().catch(() => {
      // Missing native capabilities must never prevent navigation or sign-in.
      subscriptions.splice(0).forEach(subscription => subscription.remove());
    });
    return () => { active = false; subscriptions.splice(0).forEach(subscription => subscription.remove()); };
  }, [profile]);
  return null;
}
