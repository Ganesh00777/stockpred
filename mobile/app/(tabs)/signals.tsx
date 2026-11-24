import React, { useCallback, useEffect } from 'react';
import {
  View, Text, FlatList, StyleSheet, Pressable,
  RefreshControl, ActivityIndicator, ScrollView,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useQuery } from '@tanstack/react-query';
import { fetchSignals, fetchBreakouts } from '../../api/signals';
import { useStore } from '../../store';
import { SignalCard } from '../../components/SignalCard';
import { BreakoutRow } from '../../components/BreakoutRow';
import { Colors, FontSize, Spacing, Radius } from '../../constants/theme';

const CONF_OPTIONS = [
  { label: 'All conf', value: 0.4 },
  { label: 'High ≥60%', value: 0.6 },
  { label: 'Top ≥75%', value: 0.75 },
];

const DIR_OPTIONS = [
  { label: 'All', value: null },
  { label: 'Buy', value: 1 },
  { label: 'Sell', value: -1 },
];

export default function SignalsScreen() {
  const { filters, setFilter, signals, setSignals, breakouts, setBreakouts } = useStore();

  // ── Breakouts query ──────────────────────────────────────────────────────────
  const breakoutsQ = useQuery({
    queryKey: ['breakouts'],
    queryFn: () => fetchBreakouts(2.0),
    refetchInterval: 5 * 60 * 1000,  // every 5 min
  });

  // ── Signals query ────────────────────────────────────────────────────────────
  const signalsQ = useQuery({
    queryKey: ['signals', filters.minConfidence, filters.direction, filters.exchange],
    queryFn: () => fetchSignals({
      min_confidence: filters.minConfidence,
      direction: filters.direction ?? undefined,
      exchange: filters.exchange === 'ALL' ? undefined : filters.exchange,
    }),
    refetchInterval: 2 * 60 * 1000,
  });

  useEffect(() => { if (breakoutsQ.data) setBreakouts(breakoutsQ.data); }, [breakoutsQ.data]);
  useEffect(() => { if (signalsQ.data) setSignals(signalsQ.data); }, [signalsQ.data]);

  const isLoading = signalsQ.isLoading || breakoutsQ.isLoading;
  const isRefreshing = signalsQ.isFetching || breakoutsQ.isFetching;

  const onRefresh = useCallback(() => {
    breakoutsQ.refetch();
    signalsQ.refetch();
  }, []);

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      {/* Header */}
      <View style={styles.header}>
        <Text style={styles.brand}>Stock<Text style={styles.brandGreen}>Pred</Text></Text>
        <View style={styles.marketBadge}>
          <Text style={styles.marketText}>● NSE</Text>
        </View>
      </View>

      <FlatList
        data={signals}
        keyExtractor={(s) => `${s.id}`}
        refreshControl={<RefreshControl refreshing={isRefreshing} onRefresh={onRefresh} tintColor={Colors.accent} />}
        ListHeaderComponent={
          <View>
            {/* Breakouts */}
            <SectionHeader title="Breakouts Today" onRefresh={() => breakoutsQ.refetch()} />
            {breakoutsQ.isLoading
              ? <ActivityIndicator color={Colors.accent} style={{ marginVertical: 16 }} />
              : breakouts.map((b) => <BreakoutRow key={b.symbol} item={b} />)
            }

            {/* Filter chips */}
            <SectionHeader title="Top Signals" style={{ marginTop: 20 }} />
            <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.chipRow}>
              {DIR_OPTIONS.map((o) => (
                <Pressable
                  key={String(o.value)}
                  style={[styles.chip, filters.direction === o.value && styles.chipActive]}
                  onPress={() => setFilter('direction', o.value as any)}
                >
                  <Text style={[styles.chipText, filters.direction === o.value && styles.chipTextActive]}>
                    {o.label}
                  </Text>
                </Pressable>
              ))}
              {CONF_OPTIONS.map((o) => (
                <Pressable
                  key={o.value}
                  style={[styles.chip, filters.minConfidence === o.value && styles.chipActive]}
                  onPress={() => setFilter('minConfidence', o.value)}
                >
                  <Text style={[styles.chipText, filters.minConfidence === o.value && styles.chipTextActive]}>
                    {o.label}
                  </Text>
                </Pressable>
              ))}
            </ScrollView>
          </View>
        }
        ListEmptyComponent={
          isLoading
            ? <ActivityIndicator color={Colors.accent} style={{ marginTop: 32 }} />
            : <EmptyState text="No signals match your filters" icon="📭" />
        }
        renderItem={({ item }) => <SignalCard signal={item} />}
        contentContainerStyle={styles.list}
      />
    </SafeAreaView>
  );
}

function SectionHeader({ title, onRefresh, style }: any) {
  return (
    <View style={[styles.sectionRow, style]}>
      <Text style={styles.sectionTitle}>{title}</Text>
      {onRefresh && (
        <Pressable onPress={onRefresh} style={styles.refreshBtn}>
          <Text style={styles.refreshText}>↻</Text>
        </Pressable>
      )}
    </View>
  );
}

function EmptyState({ text, icon }: { text: string; icon: string }) {
  return (
    <View style={styles.empty}>
      <Text style={styles.emptyIcon}>{icon}</Text>
      <Text style={styles.emptyText}>{text}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: Colors.bg },
  header: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingHorizontal: Spacing.lg, paddingVertical: Spacing.md,
    borderBottomWidth: 1, borderBottomColor: Colors.border,
    backgroundColor: Colors.surface,
  },
  brand: { fontFamily: 'monospace', fontSize: FontSize.lg, fontWeight: '700', color: Colors.accent },
  brandGreen: { color: Colors.green },
  marketBadge: { backgroundColor: Colors.greenBg, paddingHorizontal: 8, paddingVertical: 3, borderRadius: Radius.full },
  marketText: { fontSize: FontSize.xs, color: Colors.green, fontWeight: '700', fontFamily: 'monospace' },
  list: { padding: Spacing.md, paddingBottom: 80 },
  sectionRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: Spacing.sm },
  sectionTitle: { fontSize: FontSize.xs, fontWeight: '700', color: Colors.muted, letterSpacing: 0.8, fontFamily: 'monospace' },
  refreshBtn: { padding: 4 },
  refreshText: { fontSize: FontSize.md, color: Colors.accent, fontFamily: 'monospace' },
  chipRow: { marginBottom: Spacing.md },
  chip: {
    paddingHorizontal: 12, paddingVertical: 5, borderRadius: Radius.full,
    borderWidth: 1, borderColor: Colors.border2, backgroundColor: Colors.surface,
    marginRight: Spacing.sm,
  },
  chipActive: { backgroundColor: Colors.accentBg, borderColor: Colors.accent },
  chipText: { fontSize: FontSize.xs, fontWeight: '600', color: Colors.muted, fontFamily: 'monospace' },
  chipTextActive: { color: Colors.accent },
  empty: { alignItems: 'center', paddingTop: 48 },
  emptyIcon: { fontSize: 36, marginBottom: 10 },
  emptyText: { fontSize: FontSize.md, color: Colors.dim, fontFamily: 'monospace' },
});
