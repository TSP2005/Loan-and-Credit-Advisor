/* Service Worker — Loan Advisor Push Notifications */

// Handle messages posted from the main thread (e.g. ChatPanel)
self.addEventListener('message', (event) => {
  if (event.data?.type === 'SHOW_NOTIFICATION') {
    const { title, body } = event.data;
    self.registration.showNotification(title, {
      body,
      icon: '/vite.svg',
      badge: '/vite.svg',
      tag: 'loan-report',
      requireInteraction: false,
    });
  }
});

// When user clicks the notification — focus the app tab
self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clientList) => {
      for (const client of clientList) {
        if ('focus' in client) return client.focus();
      }
      if (clients.openWindow) return clients.openWindow('/');
    })
  );
});
