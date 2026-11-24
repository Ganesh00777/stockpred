import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { Colors, FontSize } from '../../constants/theme';

interface ScoreBarProps {
  label: string;
  value: number;   // -1.0 to 1.0
  color: string;
}

export function ScoreBar({ label, value, color }: ScoreBarProps) {
  const pct = Math.abs(value) * 100;
  return (
    <View style={styles.wrap}>
      <Text style={styles.label}>{label}</Text>
      <View style={styles.track}>
        <View style={[styles.fill, { width: `${pct}%`, backgroundColor: color }]} />
      </View>
      <Text style={[styles.val, { color }]}>{pct.toFixed(0)}%</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { flex: 1, alignItems: 'center', gap: 3 },
  label: { fontSize: 9, color: Colors.dim, fontWeight: '600', letterSpacing: 0.5 },
  track: { width: '100%', height: 3, backgroundColor: Colors.border, borderRadius: 2, overflow: 'hidden' },
  fill: { height: '100%', borderRadius: 2 },
  val: { fontSize: FontSize.xs, fontWeight: '600' },
});
