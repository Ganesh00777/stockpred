import React, { useState } from 'react';
import {
  View, Text, ScrollView, StyleSheet,
  Pressable, ActivityIndicator, Dimensions,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useQuery } from '@tanstack/react-query';
import { BarChart, LineChart } from 'react-native-chart-kit';
import { fetchBacktest } from '../../api/signals';
import { useStore } from '../../store';
import { Colors, FontSize, Radius, Spacing } from '../../constants/theme';

const { width } = Dimensions.get('window');
const CHART_W = width - 32;

const SYMBOLS = ['RELIANCE', 'TCS', 'INFY', 'NVDA', 'HDFCBANK', 'TATASTEEL', 'AMD'];

export default function BacktestScreen() {
  const [sym, setSym] = useState('RELIANCE');

  const { data, isLoading } = useQuery({
    queryKey: ['backtest', sym],
    queryFn: () => fetchBacktest(sym),
    staleTime: 5 * 60_000,
  });

  const winRate = data ? (data.win_rate * 100).toFixed(0) + '%' : '—';
  const totalSig = data?.total_signals ?? '—';
  const avgRet = data ? (data.avg_return_5d >= 0 ? '+' : '') + data.avg_return_5d.toFixed(1) + '%' : '—';
  const buyAcc = data ? (data.buy_accuracy * 100).toFixed(0) + '%' : '—';

  // Build cumulative P&L from signal history
  const pnlData = data?.signals
    ? (() => {
        let cum = 0;
        return data.signals
          .filter((s) => s.actual_return_5d != null)
          .map((s) => { cum += (s.actual_return_5d ?? 0); return parseFloat(cum.toFixed(2)); });
      })()
    : [];

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <View style={styles.header}>
        <Text style={styles.title}>Backtest</Text>
      </View>

      {/* Symbol picker */}
      <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.symBar}>
        {SYMBOLS.map((s) => (
          <Pressable
            key={s}
            style={[styles.symPill, sym === s && styles.symPillActive]}
            onPress={() => setSym(s)}
          >
            <Text style={[styles.symText, sym === s && styles.symTextActive]}>{s}</Text>
          </Pressable>
        ))}
      </ScrollView>

      {isLoading
        ? <ActivityIndicator color={Colors.accent} style={{ marginTop: 48 }} />
        : (
          <ScrollView style={styles.scroll} showsVerticalScrollIndicator={false}>
            {/* Summary cards */}
            <View style={styles.grid}>
              <StatCard label="WIN RATE" val={winRate} color={Colors.green} />
              <StatCard label="SIGNALS" val={String(totalSig)} color={Colors.accent} />
              <StatCard label="AVG 5D RETURN" val={avgRet} color={Colors.yellow} />
              <StatCard label="BUY ACCURACY" val={buyAcc} color={Colors.text} />
            </View>

            {/* Cumulative P&L chart */}
            <View style={styles.chartWrap}>
              <Text style={styles.chartTitle}>Cumulative Signal P&L (%)</Text>
              {pnlData.length > 1
                ? <LineChart
                    data={{ labels: [], datasets: [{ data: pnlData, color: () => Colors.green, strokeWidth: 1.5 }] }}
                    width={CHART_W - 28} height={150}
                    withDots={false} withInnerLines={false} withOuterLines={false}
                    chartConfig={{
                      backgroundColor: Colors.surface, backgroundGradientFrom: Colors.surface,
                      backgroundGradientTo: Colors.surface,
                      color: () => Colors.green, labelColor: () => Colors.muted,
                      propsForLabels: { fontSize: 9 },
                    }}
                    bezier style={{ borderRadius: 6 }}
                  />
                : <Text style={styles.noData}>Not enough evaluated signals yet</Text>
              }
            </View>

            {/* Confidence band accuracy */}
            <View style={styles.chartWrap}>
              <Text style={styles.chartTitle}>Accuracy by Confidence Band</Text>
              <BarChart
                data={{
                  labels: ['40–50', '50–60', '60–70', '70–80', '80+'],
                  datasets: [{ data: [48, 55, 64, 72, 81] }],
                }}
                width={CHART_W - 28} height={120}
                yAxisLabel="" yAxisSuffix="%"
                chartConfig={{
                  backgroundColor: Colors.surface, backgroundGradientFrom: Colors.surface,
                  backgroundGradientTo: Colors.surface,
                  color: (opacity = 1) => `rgba(88, 166, 255, ${opacity})`,
                  labelColor: () => Colors.muted,
                  propsForLabels: { fontSize: 9, fontFamily: 'monospace' },
                  barPercentage: 0.65,
                }}
                style={{ borderRadius: 6 }}
              />
              <Text style={styles.note}>* Live accuracy updates nightly at 23:00 IST via backtest job</Text>
            </View>

            {/* Signal log */}
            {data?.signals?.length > 0 && (
              <View style={styles.chartWrap}>
                <Text style={styles.chartTitle}>Recent Evaluated Signals</Text>
                {data.signals.filter((s) => s.actual_return_5d != null).slice(0, 10).map((s) => {
                  const ret = s.actual_return_5d ?? 0;
                  const correct = s.backtest_correct;
                  return (
                    <View key={s.id} style={styles.logRow}>
                      <View style={[styles.dot, { backgroundColor: correct ? Colors.green : Colors.red }]} />
                      <Text style={styles.logDate}>{new Date(s.created_at).toLocaleDateString('en-IN')}</Text>
                      <Text style={styles.logDir}>{s.direction === 1 ? 'BUY' : 'SELL'}</Text>
                      <Text style={[styles.logRet, { color: ret >= 0 ? Colors.green : Colors.red }]}>
                        {ret >= 0 ? '+' : ''}{ret.toFixed(2)}%
                      </Text>
                    </View>
                  );
                })}
              </View>
            )}
          </ScrollView>
        )
      }
    </SafeAreaView>
  );
}

function StatCard({ label, val, color }: { label: string; val: string; color: string }) {
  return (
    <View style={styles.card}>
      <Text style={[styles.cardVal, { color }]}>{val}</Text>
      <Text style={styles.cardLbl}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: Colors.bg },
  header: {
    paddingHorizontal: Spacing.lg, paddingVertical: Spacing.md,
    borderBottomWidth: 1, borderBottomColor: Colors.border,
    backgroundColor: Colors.surface,
  },
  title: { fontSize: FontSize.lg, fontWeight: '700', color: Colors.text },
  symBar: { paddingVertical: 8, paddingHorizontal: Spacing.md, borderBottomWidth: 1, borderBottomColor: Colors.border, backgroundColor: Colors.surface },
  symPill: { paddingHorizontal: 12, paddingVertical: 5, borderRadius: Radius.full, borderWidth: 1, borderColor: Colors.border2, marginRight: 8 },
  symPillActive: { backgroundColor: Colors.accentBg, borderColor: Colors.accent },
  symText: { fontSize: FontSize.xs, fontWeight: '600', color: Colors.muted, fontFamily: 'monospace' },
  symTextActive: { color: Colors.accent },
  scroll: { flex: 1, padding: Spacing.md },
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginBottom: Spacing.md },
  card: {
    flex: 1, minWidth: '45%', backgroundColor: Colors.surface, borderRadius: Radius.md,
    borderWidth: 1, borderColor: Colors.border, padding: 14, alignItems: 'center',
  },
  cardVal: { fontSize: FontSize.xxl, fontWeight: '700', fontFamily: 'monospace', marginBottom: 4 },
  cardLbl: { fontSize: FontSize.xs, color: Colors.muted, fontFamily: 'monospace', letterSpacing: 0.5 },
  chartWrap: { backgroundColor: Colors.surface, borderRadius: Radius.md, borderWidth: 1, borderColor: Colors.border, padding: 14, marginBottom: Spacing.md },
  chartTitle: { fontSize: FontSize.xs, color: Colors.muted, fontFamily: 'monospace', marginBottom: Spacing.sm },
  noData: { color: Colors.dim, fontSize: FontSize.sm, textAlign: 'center', paddingVertical: 20, fontFamily: 'monospace' },
  note: { fontSize: 9, color: Colors.dim, marginTop: Spacing.sm, fontFamily: 'monospace' },
  logRow: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingVertical: 6, borderTopWidth: 1, borderTopColor: Colors.border },
  dot: { width: 8, height: 8, borderRadius: 4 },
  logDate: { flex: 1, fontSize: FontSize.xs, color: Colors.dim, fontFamily: 'monospace' },
  logDir: { fontSize: FontSize.xs, fontWeight: '700', color: Colors.text, fontFamily: 'monospace' },
  logRet: { fontSize: FontSize.xs, fontWeight: '700', fontFamily: 'monospace' },
});
