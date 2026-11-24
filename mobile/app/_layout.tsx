import { useEffect } from 'react';
import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import { StyleSheet } from 'react-native';
import { Colors } from '../constants/theme';
import { signalWS } from '../api/websocket';
import { useStore } from '../store';
import { setTokenGetter } from '../api/client';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 2, staleTime: 30_000 },
  },
});

export default function RootLayout() {
  const accessToken = useStore((s) => s.accessToken);
  const prependSignal = useStore((s) => s.prependSignal);

  // Wire token getter for axios interceptor
  useEffect(() => {
    setTokenGetter(() => accessToken);
  }, [accessToken]);

  // Connect WebSocket on mount
  useEffect(() => {
    signalWS.connect();
    const unsub = signalWS.subscribe((signal) => prependSignal(signal));
    return () => {
      unsub();
      signalWS.disconnect();
    };
  }, []);

  return (
    <GestureHandlerRootView style={styles.root}>
      <QueryClientProvider client={queryClient}>
        <StatusBar style="light" backgroundColor={Colors.bg} />
        <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: Colors.bg } }}>
          <Stack.Screen name="(tabs)" />
        </Stack>
      </QueryClientProvider>
    </GestureHandlerRootView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: Colors.bg },
});
