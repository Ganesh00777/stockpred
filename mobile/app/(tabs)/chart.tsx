import React, { useState, useMemo } from 'react';
import {
  View, Text, ScrollView, StyleSheet, Pressable,
  Dimensions, ActivityIndicator,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useQuery } from '@tanstack/react-query';
import { LineChart, BarChart } from 'react-native-chart-kit';
import { fetchCandles, fetchSignalHistory } from '../../api/signals';
import { useStore } from '../../store';
import { Colors, FontSize, Radius, Spacing } from '../../constants/theme';

const { width } = Dimensions.get('window');
const CHART_W = width - 32;

const PERIODS = [
  { label: '1W', period: '5d',  interval: '1h' },
  { label: '1M', period: '1mo', interval: '1d' },
  { label: '3M', period: '3mo', interval: '1d' },
  { label: '6M', period: '6mo', interval: '1wk' },
];

export default function ChartScreen() {
  const { activeSymbol, activeExchange, watchlist, setActiveSymbol } = useStore();
  const [periodIdx, setPeriodIdx] = useState(1);
  const { period, interval } = PERIODS[periodIdx];

  const candleQ = useQuery({
    queryKey: ['candles', activeSymbol, period, interval],
    queryFn: () => fetchCandles(activeSymbol, period, interval),
    enabled: !!activeSymbol,
  });

  const sigQ = useQuery({
    queryKey: ['signal-history', activeSymbol],
    queryFn: () => fetchSignalHistory(activeSymbol),
    enabled: !!activeSymbol,
  });

  const candles = candleQ.data ?? [];

  const { labels, closes, volumes, chartColor } = useMemo(() => {
    if (!candles.length) return { labels: [], closes: [], volumes: [], chartColor: Colors.accent };
    const closes = candles.map((c) => c.close);
    const volumes = candles.map((c) => c.volume / 1e6);
    const avgVol = volumes.reduce((a, b) => a + b, 0) / volumes.length;
    const trend = closes[closes.length - 1] >= closes[0];
    const labels = candles.map((c) =>
      new Date(c.time).toLocaleDateString('en-IN', { day: '2-digit', month: 'short' })
    );
    return { labels, closes, volumes, avgVol, chartColor: trend ? Colors.green : Colors.red };
  }, [candles]);

  const last = candles[candles.length - 1];
  const prev = candles[candles.length - 2];
  const chg = last && prev ? ((last.close - prev.close) / prev.close * 100).toFixed(2) : '—';
  const isPos = parseFloat(chg) >= 0;

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      {/* Symbol picker */}
      <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.symbolBar}>
        {watchlist.map((sym) => (
          <Pressable
            key={sym}
            style={[styles.symPill, activeSymbol === sym && styles.symPillActive]}
            onPress={() => setActiveSymbol(sym, activeExchange)}
          >
            <Text style={[styles.symText, activeSymbol === sym && styles.symTextActive]}>{sym}</Text>
          </Pressable>
        ))}
      </ScrollView>

      <ScrollView style={styles.scroll} showsVerticalScrollIndicator={false}>
        {/* Price header */}
        <View style={styles.priceHeader}>
          <View>
            <Text style={styles.symbol}>{activeSymbol}</Text>
            <Text style={styles.exchange}>{activeExchange}</Text>
          </View>
          {last && (
            <View style={styles.priceRight}>
              <Text style={styles.price}>
                {activeExchange === 'NSE' ? '₹' : '$'}{last.close.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
              </Text>
              <Text style={[styles.chg, { color: isPos ? Colors.green : Colors.red }]}>
                {isPos ? '+' : ''}{chg}%
              </Text>
            </View>
          )}
        </View>

        {/* Period selector */}
        <View style={styles.periodRow}>
          {PERIODS.map((p, i) => (
            <Pressable
              key={p.label}
              style={[styles.periodBtn, periodIdx === i && styles.periodBtnActive]}
              onPress={() => setPeriodIdx(i)}
            >
              <Text style={[styles.periodText, periodIdx === i && styles.periodTextActive]}>{p.label}</Text>
            </Pressable>
          ))}
        </View>

        {/* Price chart */}
        <View style={styles.chartWrap}>
          {candleQ.isLoading
            ? <ActivityIndicator color={Colors.accent} style={{ height: 180 }} />
            : closes.length > 1
              ? <LineChart
                  data={{ labels: labels.filter((_, i) => i % Math.ceil(labels.length / 6) === 0), datasets: [{ data: closes, color: () => chartColor, strokeWidth: 1.5 }] }}
                  width={CHART_W - 28}
                  height={180}
                  withDots={false}
                  withInnerLines={false}
                  withOuterLines={false}
                  chartConfig={{
                    backgroundColor: Colors.surface,
                    backgroundGradientFrom: Colors.surface,
                    backgroundGradientTo: Colors.surface,
                    color: () => chartColor,
                    labelColor: () => Colors.muted,
                    propsForLabels: { fontSize: 9, fontFamily: 'monospace' },
                  }}
                  bezier
                  style={{ borderRadius: 6 }}
                />
              : <Text style={styles.noData}>No data</Text>
          }
        </View>

        {/* OHLCV stats */}
        {last && (
          <View style={styles.statsRow}>
            {[
              { label: 'OPEN', val: last.open.toFixed(1) },
              { label: 'HIGH', val: last.high.toFixed(1), color: Colors.green },
              { label: 'LOW', val: last.low.toFixed(1), color: Colors.red },
              { label: 'VOL', val: (last.volume / 1e6).toFixed(1) + 'M' },
            ].map((s) => (
              <View key={s.label} style={styles.stat}>
                <Text style={[styles.statVal, s.color ? { color: s.color } : {}]}>{s.val}</Text>
                <Text style={styles.statLbl}>{s.label}</Text>
              </View>
            ))}
          </View>
        )}

        {/* Volume chart */}
        <View style={styles.chartWrap}>
          <Text style={styles.chartSubtitle}>Volume (M)</Text>
          {!candleQ.isLoading && volumes.length > 1 && (
            <BarChart
              data={{ labels: [], datasets: [{ data: volumes }] }}
              width={CHART_W - 28}
              height={80}
              yAxisLabel="" yAxisSuffix=""
              withHorizontalLabels={false}
              withInnerLines={false}
              chartConfig={{
                backgroundColor: Colors.surface,
                backgroundGradientFrom: Colors.surface,
                backgroundGradientTo: Colors.surface,
                color: (opacity = 1) => `rgba(88, 166, 255, ${opacity * 0.5})`,
                barPercentage: 0.6,
              }}
              style={{ borderRadius: 6 }}
            />
          )}
        </View>

        {/* Signal overlays */}
        {sigQ.data && sigQ.data.length > 0 && (
          <View style={styles.sigWrap}>
            <Text style={styles.sigTitle}>Recent Signals on {activeSymbol}</Text>
            {sigQ.data.slice(0, 5).map((s) => (
              <View key={s.id} style={styles.sigRow}>
                <View style={[styles.sigDot, { backgroundColor: s.direction === 1 ? Colors.green : Colors.red }]} />
                <Text style={styles.sigDate}>{new Date(s.created_at).toLocaleDateString('en-IN')}</Text>
                <Text style={styles.sigDir}>{s.direction === 1 ? 'BUY' : 'SELL'}</Text>
                <Text style={styles.sigConf}>{(s.confidence * 100).toFixed(0)}%</Text>
              </View>
            ))}
          </View>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: Colors.bg },
  symbolBar: { borderBottomWidth: 1, borderBottomColor: Colors.border, paddingVertical: 8, paddingHorizontal: Spacing.md, backgroundColor: Colors.surface },
  symPill: { paddingHorizontal: 12, paddingVertical: 5, borderRadius: Radius.full, borderWidth: 1, borderColor: Colors.border2, marginRight: 8 },
  symPillActive: { backgroundColor: Colors.accentBg, borderColor: Colors.accent },
  symText: { fontSize: FontSize.xs, fontWeight: '600', color: Colors.muted, fontFamily: 'monospace' },
  symTextActive: { color: Colors.accent },
  scroll: { flex: 1, padding: Spacing.md },
  priceHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: Spacing.md },
  symbol: { fontSize: FontSize.xl, fontWeight: '700', color: Colors.text, fontFamily: 'monospace' },
  exchange: { fontSize: FontSize.xs, color: Colors.dim },
  priceRight: { alignItems: 'flex-end' },
  price: { fontSize: FontSize.xl, fontWeight: '700', color: Colors.text, fontFamily: 'monospace' },
  chg: { fontSize: FontSize.md, fontWeight: '600', fontFamily: 'monospace' },
  periodRow: { flexDirection: 'row', gap: 8, marginBottom: Spacing.md },
  periodBtn: { paddingHorizontal: 12, paddingVertical: 5, borderRadius: 6, borderWidth: 1, borderColor: Colors.border2 },
  periodBtnActive: { backgroundColor: Colors.accentBg, borderColor: Colors.accent },
  periodText: { fontSize: FontSize.xs, fontWeight: '600', color: Colors.muted, fontFamily: 'monospace' },
  periodTextActive: { color: Colors.accent },
  chartWrap: { backgroundColor: Colors.surface, borderRadius: Radius.md, borderWidth: 1, borderColor: Colors.border, padding: 14, marginBottom: Spacing.md },
  chartSubtitle: { fontSize: FontSize.xs, color: Colors.muted, fontFamily: 'monospace', marginBottom: 6 },
  noData: { color: Colors.dim, textAlign: 'center', paddingVertical: 20, fontFamily: 'monospace' },
  statsRow: { flexDirection: 'row', gap: 8, marginBottom: Spacing.md },
  stat: { flex: 1, backgroundColor: Colors.surface2, borderRadius: 6, padding: 8, alignItems: 'center' },
  statVal: { fontSize: FontSize.md, fontWeight: '600', color: Colors.text, fontFamily: 'monospace' },
  statLbl: { fontSize: 9, color: Colors.dim, marginTop: 2, fontFamily: 'monospace' },
  sigWrap: { backgroundColor: Colors.surface, borderRadius: Radius.md, borderWidth: 1, borderColor: Colors.border, padding: 14, marginBottom: 80 },
  sigTitle: { fontSize: FontSize.xs, color: Colors.muted, fontFamily: 'monospace', marginBottom: Spacing.sm },
  sigRow: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingVertical: 6, borderTopWidth: 1, borderTopColor: Colors.border },
  sigDot: { width: 8, height: 8, borderRadius: 4 },
  sigDate: { flex: 1, fontSize: FontSize.xs, color: Colors.dim, fontFamily: 'monospace' },
  sigDir: { fontSize: FontSize.xs, fontWeight: '700', color: Colors.text, fontFamily: 'monospace' },
  sigConf: { fontSize: FontSize.xs, color: Colors.accent, fontFamily: 'monospace' },
});
