import React, { useState } from 'react';
import {
  View, Text, ScrollView, StyleSheet, Pressable,
  Switch, ActivityIndicator, Modal, TextInput,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { fetchAlerts, createAlert, deleteAlert, toggleAlert, AlertRule } from '../../api/signals';
import { Colors, FontSize, Radius, Spacing } from '../../constants/theme';

export default function AlertsScreen() {
  const qc = useQueryClient();
  const [showAdd, setShowAdd] = useState(false);

  const { data: alerts = [], isLoading } = useQuery({
    queryKey: ['alerts'],
    queryFn: fetchAlerts,
  });

  const toggleMut = useMutation({
    mutationFn: ({ id, active }: { id: number; active: boolean }) => toggleAlert(id, active),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['alerts'] }),
  });

  const deleteMut = useMutation({
    mutationFn: (id: number) => deleteAlert(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['alerts'] }),
  });

  const addMut = useMutation({
    mutationFn: (rule: Omit<AlertRule, 'id'>) => createAlert(rule),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['alerts'] }); setShowAdd(false); },
  });

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <View style={styles.header}>
        <Text style={styles.title}>Alerts</Text>
        <Pressable style={styles.addBtn} onPress={() => setShowAdd(true)}>
          <Text style={styles.addBtnText}>+ Add</Text>
        </Pressable>
      </View>

      <ScrollView style={styles.scroll} showsVerticalScrollIndicator={false}>

        {/* Alert rules */}
        <SectionTitle title="Alert Rules" />
        {isLoading
          ? <ActivityIndicator color={Colors.accent} style={{ marginTop: 24 }} />
          : alerts.length === 0
            ? <Text style={styles.empty}>No alert rules yet. Tap + Add to create one.</Text>
            : alerts.map((a) => (
                <View key={a.id} style={styles.ruleRow}>
                  <View style={styles.ruleInfo}>
                    <Text style={styles.ruleSym}>{a.symbol} <Text style={styles.ruleExch}>{a.exchange}</Text></Text>
                    <Text style={styles.ruleDetail}>
                      {a.direction === 1 ? 'BUY' : a.direction === -1 ? 'SELL' : 'Any'} · ≥{(a.min_confidence * 100).toFixed(0)}% · {a.channel}
                    </Text>
                  </View>
                  <Switch
                    value={a.active}
                    onValueChange={(v) => toggleMut.mutate({ id: a.id, active: v })}
                    trackColor={{ false: Colors.border2, true: Colors.green }}
                    thumbColor="white"
                  />
                  <Pressable onPress={() => deleteMut.mutate(a.id)} style={styles.delBtn}>
                    <Text style={styles.delText}>✕</Text>
                  </Pressable>
                </View>
              ))
        }

        {/* Channels */}
        <SectionTitle title="Channels" style={{ marginTop: 24 }} />
        <View style={styles.channelCard}>
          <View style={styles.channelRow}>
            <View>
              <Text style={styles.channelName}>📱 Telegram</Text>
              <Text style={styles.channelDetail}>Instant push on every signal ≥ threshold</Text>
            </View>
            <Switch value={true} trackColor={{ false: Colors.border2, true: Colors.green }} thumbColor="white" />
          </View>
          <View style={[styles.channelRow, { borderTopWidth: 1, borderTopColor: Colors.border }]}>
            <View>
              <Text style={styles.channelName}>📧 Email Digest</Text>
              <Text style={styles.channelDetail}>Top 5 signals at 17:30 IST daily</Text>
            </View>
            <Switch value={false} trackColor={{ false: Colors.border2, true: Colors.green }} thumbColor="white" />
          </View>
        </View>

        {/* Instructions */}
        <View style={styles.infoCard}>
          <Text style={styles.infoTitle}>Setup Telegram Bot</Text>
          <Text style={styles.infoText}>
            1. Open Telegram → search @StockPredBot{'\n'}
            2. Send /start → copy your Chat ID{'\n'}
            3. Add TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID to backend .env{'\n'}
            4. Alerts fire automatically after each signal run (17:00 IST)
          </Text>
        </View>
      </ScrollView>

      {/* Add Alert Modal */}
      <AddAlertModal
        visible={showAdd}
        onClose={() => setShowAdd(false)}
        onSave={(rule) => addMut.mutate(rule)}
        loading={addMut.isPending}
      />
    </SafeAreaView>
  );
}

function SectionTitle({ title, style }: any) {
  return (
    <Text style={[{ fontSize: FontSize.xs, fontWeight: '700', color: Colors.muted, letterSpacing: 0.8, fontFamily: 'monospace', marginBottom: Spacing.sm }, style]}>
      {title}
    </Text>
  );
}

function AddAlertModal({ visible, onClose, onSave, loading }: {
  visible: boolean; onClose: () => void;
  onSave: (r: Omit<AlertRule, 'id'>) => void; loading: boolean;
}) {
  const [symbol, setSymbol] = useState('');
  const [exchange, setExchange] = useState<'NSE' | 'NASDAQ'>('NSE');
  const [direction, setDirection] = useState<1 | -1 | null>(null);
  const [minConf, setMinConf] = useState('60');
  const [channel, setChannel] = useState<'telegram' | 'email' | 'both'>('telegram');

  const save = () => {
    if (!symbol) return;
    onSave({ symbol: symbol.toUpperCase(), exchange, direction, min_confidence: parseInt(minConf) / 100, channel, active: true });
  };

  return (
    <Modal visible={visible} animationType="slide" transparent>
      <View style={modal.overlay}>
        <View style={modal.sheet}>
          <Text style={modal.title}>New Alert Rule</Text>

          <Text style={modal.label}>Symbol</Text>
          <TextInput style={modal.input} value={symbol} onChangeText={setSymbol}
            placeholder="e.g. RELIANCE" placeholderTextColor={Colors.dim}
            autoCapitalize="characters" />

          <Text style={modal.label}>Exchange</Text>
          <View style={modal.row}>
            {(['NSE', 'NASDAQ'] as const).map((e) => (
              <Pressable key={e} style={[modal.opt, exchange === e && modal.optActive]} onPress={() => setExchange(e)}>
                <Text style={[modal.optText, exchange === e && modal.optTextActive]}>{e}</Text>
              </Pressable>
            ))}
          </View>

          <Text style={modal.label}>Direction</Text>
          <View style={modal.row}>
            {([{ label: 'Any', val: null }, { label: 'Buy', val: 1 }, { label: 'Sell', val: -1 }] as const).map((d) => (
              <Pressable key={String(d.val)} style={[modal.opt, direction === d.val && modal.optActive]} onPress={() => setDirection(d.val)}>
                <Text style={[modal.optText, direction === d.val && modal.optTextActive]}>{d.label}</Text>
              </Pressable>
            ))}
          </View>

          <Text style={modal.label}>Min Confidence %</Text>
          <TextInput style={modal.input} value={minConf} onChangeText={setMinConf}
            keyboardType="numeric" placeholderTextColor={Colors.dim} />

          <Text style={modal.label}>Channel</Text>
          <View style={modal.row}>
            {(['telegram', 'email', 'both'] as const).map((c) => (
              <Pressable key={c} style={[modal.opt, channel === c && modal.optActive]} onPress={() => setChannel(c)}>
                <Text style={[modal.optText, channel === c && modal.optTextActive]}>{c}</Text>
              </Pressable>
            ))}
          </View>

          <View style={modal.actions}>
            <Pressable style={modal.cancelBtn} onPress={onClose}><Text style={modal.cancelText}>Cancel</Text></Pressable>
            <Pressable style={modal.saveBtn} onPress={save} disabled={loading}>
              <Text style={modal.saveText}>{loading ? 'Saving…' : 'Save Rule'}</Text>
            </Pressable>
          </View>
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: Colors.bg },
  header: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingHorizontal: Spacing.lg, paddingVertical: Spacing.md,
    borderBottomWidth: 1, borderBottomColor: Colors.border, backgroundColor: Colors.surface,
  },
  title: { fontSize: FontSize.lg, fontWeight: '700', color: Colors.text },
  addBtn: { backgroundColor: Colors.accentBg, borderRadius: Radius.sm, paddingHorizontal: 12, paddingVertical: 6 },
  addBtnText: { fontSize: FontSize.sm, fontWeight: '700', color: Colors.accent, fontFamily: 'monospace' },
  scroll: { flex: 1, padding: Spacing.md },
  empty: { fontSize: FontSize.sm, color: Colors.dim, fontFamily: 'monospace', marginTop: 8 },
  ruleRow: {
    flexDirection: 'row', alignItems: 'center', gap: Spacing.sm,
    backgroundColor: Colors.surface, borderWidth: 1, borderColor: Colors.border,
    borderRadius: Radius.sm, paddingHorizontal: Spacing.md, paddingVertical: Spacing.sm + 2,
    marginBottom: Spacing.sm,
  },
  ruleInfo: { flex: 1 },
  ruleSym: { fontSize: FontSize.base, fontWeight: '700', color: Colors.text, fontFamily: 'monospace' },
  ruleExch: { fontSize: FontSize.xs, color: Colors.dim, fontWeight: '400' },
  ruleDetail: { fontSize: FontSize.xs, color: Colors.muted, marginTop: 2 },
  delBtn: { padding: 4 },
  delText: { fontSize: FontSize.md, color: Colors.red },
  channelCard: { backgroundColor: Colors.surface, borderWidth: 1, borderColor: Colors.border, borderRadius: Radius.md, marginBottom: Spacing.md, overflow: 'hidden' },
  channelRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', padding: Spacing.md },
  channelName: { fontSize: FontSize.base, fontWeight: '600', color: Colors.text, marginBottom: 2 },
  channelDetail: { fontSize: FontSize.xs, color: Colors.muted },
  infoCard: { backgroundColor: Colors.surface2, borderRadius: Radius.md, padding: Spacing.md, marginBottom: 80 },
  infoTitle: { fontSize: FontSize.sm, fontWeight: '700', color: Colors.muted, fontFamily: 'monospace', marginBottom: 8 },
  infoText: { fontSize: FontSize.xs, color: Colors.dim, fontFamily: 'monospace', lineHeight: 18 },
});

const modal = StyleSheet.create({
  overlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.6)', justifyContent: 'flex-end' },
  sheet: { backgroundColor: Colors.surface, borderTopLeftRadius: 16, borderTopRightRadius: 16, padding: Spacing.lg, paddingBottom: 36 },
  title: { fontSize: FontSize.lg, fontWeight: '700', color: Colors.text, marginBottom: Spacing.lg },
  label: { fontSize: FontSize.xs, color: Colors.muted, fontFamily: 'monospace', marginBottom: 6, marginTop: Spacing.md },
  input: { backgroundColor: Colors.surface2, borderWidth: 1, borderColor: Colors.border2, borderRadius: Radius.sm, paddingHorizontal: Spacing.md, paddingVertical: 10, color: Colors.text, fontFamily: 'monospace', fontSize: FontSize.md },
  row: { flexDirection: 'row', gap: 8 },
  opt: { paddingHorizontal: 12, paddingVertical: 6, borderRadius: Radius.full, borderWidth: 1, borderColor: Colors.border2 },
  optActive: { backgroundColor: Colors.accentBg, borderColor: Colors.accent },
  optText: { fontSize: FontSize.xs, fontWeight: '600', color: Colors.muted, fontFamily: 'monospace' },
  optTextActive: { color: Colors.accent },
  actions: { flexDirection: 'row', gap: 10, marginTop: Spacing.xl },
  cancelBtn: { flex: 1, padding: 12, borderRadius: Radius.sm, borderWidth: 1, borderColor: Colors.border2, alignItems: 'center' },
  cancelText: { color: Colors.muted, fontWeight: '600' },
  saveBtn: { flex: 1, padding: 12, borderRadius: Radius.sm, backgroundColor: Colors.accentBg, alignItems: 'center' },
  saveText: { color: Colors.accent, fontWeight: '700', fontFamily: 'monospace' },
});
