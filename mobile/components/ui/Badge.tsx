import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { Colors, FontSize, Radius } from '../../constants/theme';

type Variant = 'buy' | 'sell' | 'accent' | 'yellow' | 'muted';

interface BadgeProps {
  label: string;
  variant?: Variant;
}

const variantStyles: Record<Variant, { bg: string; color: string }> = {
  buy:    { bg: Colors.greenBg,  color: Colors.green },
  sell:   { bg: Colors.redBg,   color: Colors.red },
  accent: { bg: Colors.accentBg, color: Colors.accent },
  yellow: { bg: Colors.yellowBg, color: Colors.yellow },
  muted:  { bg: Colors.border,  color: Colors.muted },
};

export function Badge({ label, variant = 'muted' }: BadgeProps) {
  const v = variantStyles[variant];
  return (
    <View style={[styles.badge, { backgroundColor: v.bg }]}>
      <Text style={[styles.text, { color: v.color }]}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  badge: {
    paddingHorizontal: 10,
    paddingVertical: 3,
    borderRadius: Radius.full,
    alignSelf: 'flex-start',
  },
  text: {
    fontSize: FontSize.xs,
    fontWeight: '700',
    letterSpacing: 0.5,
  },
});
