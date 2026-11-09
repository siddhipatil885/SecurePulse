module.exports = ({ config }) => {
  const projectId = process.env.EXPO_PUBLIC_EXPO_PROJECT_ID?.trim();
  if (projectId && !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(projectId)) {
    throw new Error('EXPO_PUBLIC_EXPO_PROJECT_ID must be an actual Expo/EAS project UUID.');
  }
  return {
    ...config,
    extra: { ...config.extra, ...(projectId ? { eas: { projectId } } : {}) },
  };
};
