import React, { useState, useMemo } from 'react';
import {
  View, Text, FlatList, TextInput, StyleSheet,
  Pressable, ScrollView, ActivityIndicator,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useQuery } from '@tanstack/react-query';
import { useRouter } from 'expo-router';
import Slider from '@react-native-community/slider';
import { fetchSignals } from '../../api/signals';
import { useStore } from '../../store';
import { Colors, FontSize, Radius, Spacing } from '../../constants/theme';

const EXCHANGES = ['ALL', 'NSE', 'NASDAQ'] as const;

export default function ScreenerScreen() {
  const router = useRouter();
  const setActiveSymbol = useStore((s) => s.setActiveSymbol);

  const [query, setQuery] = useState('');
  const [volRatio, setVolRatio] = useState(2.0);
  const [minConf, setMinConf] = useState(0.4);
  const [exchange, setExchange] = useState<'ALL' | 'NSE' | 'NASDAQ'>('ALL');

  const { data, isLoading, isFetching, refetch } = useQuery({
    queryKey: ['screener'],
    queryFn: () => fetchSignals({ min_confidence: 0.3 }),
    staleTime: 60_000,
  });

  const results = useMemo(() => {
    if (!data) return [];
    return data.filter((s) => {
      const matchSym = !query || s.symbol.includes(query.toUpperCase());
      const matchExch = exchange === 'ALL' || s.exchange === exchange;
      const matchConf = s.confidence >= minConf;
      const matchVol = (s.volume_ratio ?? 0) >= volRatio;
      return matchSym && matchExch && matchConf && matchVol;
    });
  }, [data, query, exchange, minConf, volRatio]);

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <View style={styles.header}>
        <Text style={styles.title}>Screener</Text>
        <Text style={styles.count}>{results.length} stocks</Text>
      </View>

      <ScrollView style={styles.filters} stickyHeaderIndices={[]} showsVerticalScrollIndicator={false}>
        {/* Search */}
        <TextInput
          style={styles.search}
          placeholder="Search symbol..."
          placeholderTextColor={Colors.dim}
          value={query}
          onChangeText={setQuery}
          autoCapitalize="characters"
        />

        {/* Exchange chips */}
        <View style={styles.chipRow}>
          {EXCHANGES.map((e) => (
            <Pressable
              key={e}
              style={[styles.chip, exchange === e && styles.chipActive]}
              onPress={() => setExchange(e)}
            >
              <Text style={[styles.chipText, exchange === e && styles.chipTextActive]}>{e === 'ALL' ? 'All Markets' : e}</Text>
            </Pressable>
          ))}
        </View>

        {/* Vol ratio slider */}
        <View style={styles.sliderRow}>
          <Text style={styles.sliderLabel}>Min Volume Ratio</Text>
          <Text style={[styles.sliderVal, { color: Colors.accent }]}>{volRatio.toFixed(1)}×</Text>
        </View>
        <Slider
          style={styles.slider}
          minimumValue={1} maximumValue={5} step={0.5}
          value={volRatio} onValueChange={setVolRatio}
          minimumTrackTintColor={Colors.accent} maximumTrackTintColor={Colors.border2}
          thumbTintColor={Colors.accent}
        />

        {/* Confidence slider */}
        <View style={styles.sliderRow}>
          <Text style={styles.sliderLabel}>Min Confidence</Text>
          <Text style={[styles.sliderVal, { color: Colors.accent }]}>{(minConf * 100).toFixed(0)}%</Text>
        </View>
        <Slider
          style={styles.slider}
          minimumValue={0} maximumValue={1} step={0.05}
          value={minConf} onValueChange={setMinConf}
          minimumTrackTintColor={Colors.accent} maximumTrackTintColor={Colors.border2}
          thumbTintColor={Colors.accent}
        />

        {/* Results */}
        {isLoading
          ? <ActivityIndicator color={Colors.accent} style={{ marginTop: 32 }} />
          : results.length === 0
            ? <View style={styles.empty}><Text style={styles.emptyText}>No results</Text></View>
            : results.map((s) => (
                <Pressable
                  key={s.symbol}
                  style={({ pressed }) => [styles.resultRow, pressed && { opacity: 0.75 }]}
                  onPress={() => { setActiveSymbol(s.symbol, s.exchange); router.push('/(tabs)/chart'); }}
                >
                  <View style={styles.resultLeft}>
                    <Text style={styles.resultSym}>{s.symbol} <Text style={styles.resultExch}>{s.exchange}</Text></Text>
                    <Text style={styles.resultSub}>
                      {s.direction === 1 ? '🟢 BUY' : '🔴 SELL'} · {(s.confidence * 100).toFixed(0)}% conf
                    </Text>
                  </View>
                  <Text style={styles.resultVol}>{s.volume_ratio?.toFixed(1)}×</Text>
                </Pressable>
              ))
        }
      </ScrollView>
    </SafeAreaView>
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
  title: { fontSize: FontSize.lg, fontWeight: '700', color: Colors.text },
  count: { fontSize: FontSize.sm, color: Colors.muted, fontFamily: 'monospace' },
  filters: { flex: 1, padding: Spacing.md },
  search: {
    backgroundColor: Colors.surface, borderWidth: 1, borderColor: Colors.border2,
    borderRadius: Radius.sm, paddingHorizontal: Spacing.md, paddingVertical: 10,
    color: Colors.text, fontFamily: 'monospace', fontSize: FontSize.md,
    marginBottom: Spacing.md,
  },
  chipRow: { flexDirection: 'row', gap: Spacing.sm, marginBottom: Spacing.md },
  chip: {
    paddingHorizontal: 12, paddingVertical: 5, borderRadius: Radius.full,
    borderWidth: 1, borderColor: Colors.border2, backgroundColor: Colors.surface,
  },
  chipActive: { backgroundColor: Colors.accentBg, borderColor: Colors.accent },
  chipText: { fontSize: FontSize.xs, fontWeight: '600', color: Colors.muted, fontFamily: 'monospace' },
  chipTextActive: { color: Colors.accent },
  sliderRow: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 4 },
  sliderLabel: { fontSize: FontSize.sm, color: Colors.muted, fontFamily: 'monospace' },
  sliderVal: { fontSize: FontSize.sm, fontWeight: '700', fontFamily: 'monospace' },
  slider: { width: '100%', marginBottom: Spacing.md },
  resultRow: {
    flexDirection: 'row', alignItems: 'center', gap: Spacing.md,
    backgroundColor: Colors.surface, borderWidth: 1, borderColor: Colors.border,
    borderRadius: Radius.sm, paddingHorizontal: Spacing.md, paddingVertical: Spacing.sm + 2,
    marginBottom: Spacing.sm,
  },
  resultLeft: { flex: 1 },
  resultSym: { fontSize: FontSize.base, fontWeight: '700', color: Colors.text, fontFamily: 'monospace' },
  resultExch: { fontSize: FontSize.xs, color: Colors.dim, fontWeight: '400' },
  resultSub: { fontSize: FontSize.xs, color: Colors.dim, marginTop: 2 },
  resultVol: { fontSize: FontSize.md, fontWeight: '700', color: Colors.yellow, fontFamily: 'monospace' },
  empty: { alignItems: 'center', paddingTop: 48 },
  emptyText: { fontSize: FontSize.md, color: Colors.dim, fontFamily: 'monospace' },
});
