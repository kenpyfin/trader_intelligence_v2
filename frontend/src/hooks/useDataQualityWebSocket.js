import { useState, useEffect, useCallback, useRef } from 'react';

// WebSocket connection states
const WS_STATES = {
  CONNECTING: 'connecting',
  CONNECTED: 'connected',
  DISCONNECTED: 'disconnected',
  ERROR: 'error'
};

// Data quality WebSocket hook
const useDataQualityWebSocket = (
  url = 'ws://localhost:8511/ws/data-quality',
  options = {}
) => {
  const {
    autoReconnect = true,
    reconnectInterval = 5000,
    maxReconnectAttempts = 10,
    onError = null,
    onConnect = null,
    onDisconnect = null
  } = options;

  const [connectionState, setConnectionState] = useState(WS_STATES.DISCONNECTED);
  const [qualityData, setQualityData] = useState(null);
  const [lastUpdate, setLastUpdate] = useState(null);
  const [errorMessage, setErrorMessage] = useState(null);

  const ws = useRef(null);
  const reconnectAttempts = useRef(0);
  const reconnectTimer = useRef(null);
  const isManuallyDisconnected = useRef(false);

  // Connect to WebSocket
  const connect = useCallback(() => {
    if (ws.current?.readyState === WebSocket.OPEN) {
      return; // Already connected
    }

    setConnectionState(WS_STATES.CONNECTING);
    setErrorMessage(null);

    try {
      ws.current = new WebSocket(url);

      ws.current.onopen = () => {
        console.log('Data Quality WebSocket connected');
        setConnectionState(WS_STATES.CONNECTED);
        reconnectAttempts.current = 0;
        setErrorMessage(null);

        if (onConnect) {
          onConnect();
        }

        // Send subscription message for data quality updates
        ws.current.send(JSON.stringify({
          type: 'subscribe',
          channel: 'data_quality_monitoring'
        }));
      };

      ws.current.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);

          switch (data.type) {
            case 'data_quality_update':
              setQualityData(data.payload);
              setLastUpdate(new Date(data.timestamp));
              break;

            case 'validation_alert':
              // Handle validation alerts
              if (data.payload.severity === 'critical') {
                // Trigger system notification if supported
                if ('Notification' in window && Notification.permission === 'granted') {
                  new Notification('Data Quality Alert', {
                    body: data.payload.message,
                    icon: '/favicon.ico',
                    tag: 'data-quality-alert'
                  });
                }
              }
              break;

            case 'system_status':
              // Handle system status updates
              console.log('System status:', data.payload);
              break;

            default:
              console.log('Unknown message type:', data.type);
          }
        } catch (error) {
          console.error('Error parsing WebSocket message:', error);
        }
      };

      ws.current.onerror = (error) => {
        console.error('Data Quality WebSocket error:', error);
        setConnectionState(WS_STATES.ERROR);
        setErrorMessage('Connection error occurred');

        if (onError) {
          onError(error);
        }
      };

      ws.current.onclose = (event) => {
        console.log('Data Quality WebSocket disconnected:', event.code, event.reason);
        setConnectionState(WS_STATES.DISCONNECTED);

        if (onDisconnect) {
          onDisconnect(event);
        }

        // Auto-reconnect logic
        if (
          autoReconnect &&
          !isManuallyDisconnected.current &&
          reconnectAttempts.current < maxReconnectAttempts
        ) {
          reconnectAttempts.current += 1;
          console.log(`Attempting reconnection ${reconnectAttempts.current}/${maxReconnectAttempts}`);

          reconnectTimer.current = setTimeout(() => {
            connect();
          }, reconnectInterval);
        } else if (reconnectAttempts.current >= maxReconnectAttempts) {
          setErrorMessage('Max reconnection attempts reached');
        }
      };

    } catch (error) {
      console.error('Failed to create WebSocket connection:', error);
      setConnectionState(WS_STATES.ERROR);
      setErrorMessage('Failed to establish connection');
    }
  }, [url, autoReconnect, reconnectInterval, maxReconnectAttempts, onConnect, onDisconnect, onError]);

  // Disconnect from WebSocket
  const disconnect = useCallback(() => {
    isManuallyDisconnected.current = true;

    if (reconnectTimer.current) {
      clearTimeout(reconnectTimer.current);
      reconnectTimer.current = null;
    }

    if (ws.current) {
      ws.current.close(1000, 'Manual disconnect');
    }
  }, []);

  // Send message to WebSocket
  const sendMessage = useCallback((message) => {
    if (ws.current?.readyState === WebSocket.OPEN) {
      ws.current.send(JSON.stringify(message));
    } else {
      console.warn('WebSocket is not connected. Cannot send message:', message);
    }
  }, []);

  // Request immediate data quality update
  const requestUpdate = useCallback(() => {
    sendMessage({
      type: 'request_update',
      channel: 'data_quality_monitoring'
    });
  }, [sendMessage]);

  // Subscribe to specific asset data quality
  const subscribeToAsset = useCallback((symbol, assetType = 'equity') => {
    sendMessage({
      type: 'subscribe_asset',
      payload: {
        symbol,
        asset_type: assetType
      }
    });
  }, [sendMessage]);

  // Unsubscribe from specific asset data quality
  const unsubscribeFromAsset = useCallback((symbol) => {
    sendMessage({
      type: 'unsubscribe_asset',
      payload: {
        symbol
      }
    });
  }, [sendMessage]);

  // Initialize connection on mount
  useEffect(() => {
    isManuallyDisconnected.current = false;
    connect();

    // Request notification permission if not already granted
    if ('Notification' in window && Notification.permission === 'default') {
      Notification.requestPermission();
    }

    return () => {
      disconnect();
    };
  }, [connect, disconnect]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (reconnectTimer.current) {
        clearTimeout(reconnectTimer.current);
      }
    };
  }, []);

  return {
    // Connection state
    connectionState,
    isConnected: connectionState === WS_STATES.CONNECTED,
    isConnecting: connectionState === WS_STATES.CONNECTING,
    error: errorMessage,

    // Data
    qualityData,
    lastUpdate,

    // Actions
    connect,
    disconnect,
    sendMessage,
    requestUpdate,
    subscribeToAsset,
    unsubscribeFromAsset,

    // Utilities
    reconnectAttempts: reconnectAttempts.current
  };
};

export default useDataQualityWebSocket;