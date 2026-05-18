import { StatusBar } from 'expo-status-bar';
import { useRef, useState, useCallback } from 'react';
import {
  ActivityIndicator,
  BackHandler,
  Platform,
  StyleSheet,
  View,
} from 'react-native';
import { WebView, type WebViewNavigation } from 'react-native-webview';
import { useEffect } from 'react';

const PWA_URL =
  (globalThis as any).process?.env?.EXPO_PUBLIC_PWA_URL ||
  'https://REPLACE_ME.netlify.app';

export default function App() {
  const webRef = useRef<WebView>(null);
  const [loading, setLoading] = useState(true);
  const [canGoBack, setCanGoBack] = useState(false);

  // Hardware back button on Android = browser back inside the WebView.
  useEffect(() => {
    if (Platform.OS !== 'android') return;
    const sub = BackHandler.addEventListener('hardwareBackPress', () => {
      if (canGoBack && webRef.current) {
        webRef.current.goBack();
        return true;
      }
      return false;
    });
    return () => sub.remove();
  }, [canGoBack]);

  const onNavStateChange = useCallback((nav: WebViewNavigation) => {
    setCanGoBack(nav.canGoBack);
  }, []);

  return (
    <View style={styles.root}>
      <StatusBar style="auto" />
      <WebView
        ref={webRef}
        source={{ uri: PWA_URL }}
        originWhitelist={['*']}
        javaScriptEnabled
        domStorageEnabled
        allowsBackForwardNavigationGestures
        pullToRefreshEnabled
        cacheEnabled
        startInLoadingState
        onLoadStart={() => setLoading(true)}
        onLoadEnd={() => setLoading(false)}
        onNavigationStateChange={onNavStateChange}
        setSupportMultipleWindows={false}
        style={styles.web}
      />
      {loading && (
        <View pointerEvents="none" style={styles.loader}>
          <ActivityIndicator size="large" />
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#F6F0E7' },
  web: { flex: 1, backgroundColor: '#F6F0E7' },
  loader: {
    position: 'absolute',
    inset: 0,
    alignItems: 'center',
    justifyContent: 'center',
  },
});
