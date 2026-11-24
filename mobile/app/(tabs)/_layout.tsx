import { Tabs } from 'expo-router';
import { View, StyleSheet } from 'react-native';
import { Colors } from '../../constants/theme';
import Svg, { Polyline, Line, Rect, Path } from 'react-native-svg';

function Icon({ name, color, size = 22 }: { name: string; color: string; size?: number }) {
  const s = { stroke: color, strokeWidth: 2, fill: 'none' };
  if (name === 'signals')
    return <Svg width={size} height={size} viewBox="0 0 24 24"><Polyline points="22 12 18 12 15 21 9 3 6 12 2 12" {...s}/></Svg>;
  if (name === 'screener')
    return <Svg width={size} height={size} viewBox="0 0 24 24"><Line x1="8" y1="6" x2="21" y2="6" {...s}/><Line x1="8" y1="12" x2="21" y2="12" {...s}/><Line x1="8" y1="18" x2="21" y2="18" {...s}/><Line x1="3" y1="6" x2="3.01" y2="6" {...s}/><Line x1="3" y1="12" x2="3.01" y2="12" {...s}/><Line x1="3" y1="18" x2="3.01" y2="18" {...s}/></Svg>;
  if (name === 'chart')
    return <Svg width={size} height={size} viewBox="0 0 24 24"><Rect x="3" y="3" width="18" height="18" rx="2" {...s}/><Polyline points="3 9 9 9 12 6 15 12 18 9 21 9" {...s}/></Svg>;
  if (name === 'backtest')
    return <Svg width={size} height={size} viewBox="0 0 24 24"><Path d="M18 20V10" {...s}/><Path d="M12 20V4" {...s}/><Path d="M6 20v-6" {...s}/></Svg>;
  if (name === 'alerts')
    return <Svg width={size} height={size} viewBox="0 0 24 24"><Path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" {...s}/><Path d="M13.73 21a2 2 0 0 1-3.46 0" {...s}/></Svg>;
  return null;
}

export default function TabLayout() {
  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarStyle: styles.tabBar,
        tabBarActiveTintColor: Colors.accent,
        tabBarInactiveTintColor: Colors.dim,
        tabBarLabelStyle: styles.label,
      }}
    >
      <Tabs.Screen
        name="signals"
        options={{
          title: 'Signals',
          tabBarIcon: ({ color }) => <Icon name="signals" color={color} />,
        }}
      />
      <Tabs.Screen
        name="screener"
        options={{
          title: 'Screener',
          tabBarIcon: ({ color }) => <Icon name="screener" color={color} />,
        }}
      />
      <Tabs.Screen
        name="chart"
        options={{
          title: 'Chart',
          tabBarIcon: ({ color }) => <Icon name="chart" color={color} />,
        }}
      />
      <Tabs.Screen
        name="backtest"
        options={{
          title: 'Backtest',
          tabBarIcon: ({ color }) => <Icon name="backtest" color={color} />,
        }}
      />
      <Tabs.Screen
        name="alerts"
        options={{
          title: 'Alerts',
          tabBarIcon: ({ color }) => <Icon name="alerts" color={color} />,
        }}
      />
    </Tabs>
  );
}

const styles = StyleSheet.create({
  tabBar: {
    backgroundColor: Colors.surface,
    borderTopColor: Colors.border,
    borderTopWidth: 1,
    height: 56,
    paddingBottom: 6,
  },
  label: {
    fontSize: 10,
    fontWeight: '600',
  },
});
