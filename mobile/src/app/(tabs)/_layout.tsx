import { Tabs } from 'expo-router/js-tabs';
import { ColorValue, Text } from 'react-native';

import { useT } from '../../lib/i18n';
import { usePalette } from '../../lib/theme';

// Simple glyph icons keep the app free of an icon-font dependency for now.
function icon(glyph: string) {
  return function TabIcon({ color }: { color: ColorValue }) {
    return <Text style={{ color, fontSize: 18 }} accessibilityElementsHidden importantForAccessibility="no">{glyph}</Text>;
  };
}

export default function TabsLayout() {
  const c = usePalette();
  const { t } = useT();
  return (
    <Tabs
      screenOptions={{
        headerStyle: { backgroundColor: c.surface },
        headerTintColor: c.text,
        tabBarStyle: { backgroundColor: c.surface, borderTopColor: c.border },
        tabBarActiveTintColor: c.accent,
        tabBarInactiveTintColor: c.muted,
        sceneStyle: { backgroundColor: c.bg },
      }}
    >
      <Tabs.Screen name="index" options={{ title: t('Home'), tabBarIcon: icon('♡') }} />
      <Tabs.Screen name="family" options={{ title: t('Family'), tabBarIcon: icon('⌂') }} />
      <Tabs.Screen name="invite" options={{ title: t('Invite'), tabBarIcon: icon('✉') }} />
      <Tabs.Screen name="settings" options={{ title: t('Settings'), tabBarIcon: icon('⚙') }} />
    </Tabs>
  );
}
