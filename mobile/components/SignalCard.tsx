import React from 'react';
import { View, Text, StyleSheet, Pressable } from 'react-native';
import { useRouter } from 'expo-router';
import { Signal } from '../api/signals';
import { Badge } from './ui/Badge';
import { ScoreBar } from './ui/ScoreBar';
import { Colors, FontSize, Radius, Spacing } from '../constants/theme';
import { useStore } from '../store';

interface Props {
  signal: Signal;
}

export function SignalCard({ signal }: Props) {
  const router = useRouter();
  const setActiveSymbol = useStore((s) => s.setActiveSymbol);

  const isBuy = signal.direction === 1;
  const exch = signal.exchange === 'NSE' ? '₹' : '$';
  const price = signal.price_at_signal?.toLocaleString('en-IN', { minimumFractionDigits: 2 });
  const confPct = (signal.confidence * 100).toFixed(0);
  const reason = signal.signal_reasons?.[0] ?? '';

  const handlePress = () => {
    setActiveSymbol(signal.symbol, signal.exchange);
    router.push('/(tabs)/chart');
  };

  return (
    <Pressable
      style={({ pressed }) => [styles.card, pressed && styles.pressed]}
      onPress={handlePress}
    >
      {/* Left accent bar */}
      <View style={[styles.accent, { backgroundColor: isBuy ? Colors.green : Colors.red }]} />

      <View style={styles.body}>
        {/* Top row */}
        <View style={styles.row}>
          <View style={styles.symbolRow}>
            <Text style={styles.symbol}>{signal.symbol}</Text>
            <Text style={styles.exchange}>{signal.exchange}</Text>
          </View>
          <Badge label={isBuy ? 'BUY' : 'SELL'} variant={isBuy ? 'buy' : 'sell'} />
        </View>

        {/* Price */}
        <View style={styles.row}>
          <Text style={styles.price}>
            {exch}{price}
            <Text style={styles.volTag}>  {signal.volume_ratio?.toFixed(1)}× vol</Text>
          </Text>
          <Text style={[styles.conf, { color: signal.confidence >= 0.7 ? Colors.green : Colors.accent }]}>
            {confPct}%
          </Text>
        </View>

        {/* Score bars */}
        <View style={styles.scores}>
          <ScoreBar label="VOLUME" value={signal.volume_score} color={Colors.accent} />
          <ScoreBar label="MOMENTUM" value={signal.momentum_score} color={Colors.yellow} />
          <ScoreBar label="NEWS" value={(signal.news_score + 1) / 2} color={Colors.green} />
        </View>

        {/* Reason */}
        {!!reason && (
          <Text style={styles.reason} numberOfLines={2}>
            <Text style={styles.reasonLabel}>Why: </Text>{reason}
          </Text>
        )}
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: Colors.surface,
    borderRadius: Radius.md,
    borderWidth: 1,
    borderColor: Colors.border,
    marginBottom: Spacing.sm,
    flexDirection: 'row',
    overflow: 'hidden',
  },
  pressed: { opacity: 0.85 },
  accent: { width: 3 },
  body: { flex: 1, padding: Spacing.md, gap: Spacing.sm },
  row: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  symbolRow: { flexDirection: 'row', alignItems: 'baseline', gap: 6 },
  symbol: { fontSize: FontSize.lg, fontWeight: '700', color: Colors.text, fontFamily: 'monospace' },
  exchange: { fontSize: FontSize.xs, color: Colors.dim, fontFamily: 'monospace' },
  price: { fontSize: FontSize.xl, fontWeight: '700', color: Colors.text, fontFamily: 'monospace' },
  volTag: { fontSize: FontSize.sm, color: Colors.muted, fontWeight: '400' },
  conf: { fontSize: FontSize.lg, fontWeight: '700', fontFamily: 'monospace' },
  scores: { flexDirection: 'row', gap: Spacing.sm },
  reason: { fontSize: FontSize.sm, color: Colors.dim, lineHeight: 16 },
  reasonLabel: { color: Colors.muted, fontWeight: '600' },
});
