import React from 'react';
import { View, Text, StyleSheet, Pressable } from 'react-native';
import { useRouter } from 'expo-router';
import { Breakout } from '../api/signals';
import { Colors, FontSize, Radius, Spacing } from '../constants/theme';
import { useStore } from '../store';

interface Props {
  item: Breakout;
}

export function BreakoutRow({ item }: Props) {
  const router = useRouter();
  const setActiveSymbol = useStore((s) => s.setActiveSymbol);

  const fires = '🔥'.repeat(Math.min(5, Math.floor(item.volume_ratio)));
  const isPos = item.pct_change >= 0;
  const sign = isPos ? '+' : '';

  const handlePress = () => {
    setActiveSymbol(item.symbol, item.exchange);
    router.push('/(tabs)/chart');
  };

  return (
    <Pressable
      style={({ pressed }) => [styles.row, pressed && styles.pressed]}
      onPress={handlePress}
    >
      <View style={styles.left}>
        <Text style={styles.symbol}>{item.symbol}</Text>
        <Text style={styles.exchange}>{item.exchange}</Text>
      </View>
      <Text style={styles.fire}>{fires}</Text>
      <Text style={styles.vol}>{item.volume_ratio.toFixed(1)}×</Text>
      <Text style={[styles.pct, { color: isPos ? Colors.green : Colors.red }]}>
        {sign}{item.pct_change?.toFixed(1)}%
      </Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.md,
    backgroundColor: Colors.surface,
    borderWidth: 1,
    borderColor: Colors.border,
    borderRadius: Radius.sm,
    paddingHorizontal: Spacing.md,
    paddingVertical: Spacing.sm + 2,
    marginBottom: Spacing.sm,
  },
  pressed: { backgroundColor: Colors.surface2 },
  left: { flex: 1 },
  symbol: { fontSize: FontSize.base, fontWeight: '700', color: Colors.text, fontFamily: 'monospace' },
  exchange: { fontSize: FontSize.xs, color: Colors.dim },
  fire: { fontSize: 13 },
  vol: { fontSize: FontSize.md, fontWeight: '700', color: Colors.yellow, fontFamily: 'monospace' },
  pct: { fontSize: FontSize.md, fontWeight: '700', fontFamily: 'monospace', minWidth: 50, textAlign: 'right' },
});
