/// Service tile for dashboard (same list as web moltbot_ui/app.js).
class ServiceItem {
  const ServiceItem({
    required this.id,
    required this.name,
    required this.icon,
    required this.cat,
    this.url,
    this.probeUrl,
  });

  final String id;
  final String name;
  final String icon;
  final String cat;
  final String? url;
  final String? probeUrl;
}

class DashboardCategory {
  const DashboardCategory({required this.id, required this.label});
  final String id;
  final String label;
}

/// Same as web SERVICES array (probeUrl = backend URL from Docker network; app calls API which probes).
final List<ServiceItem> kDashboardServices = [
  ServiceItem(id: 'moltbot-api', name: 'Moltbot API', icon: '🤖', cat: 'core', url: 'http://localhost:18080', probeUrl: 'http://moltbot-api:8080/healthz'),
  ServiceItem(id: 'ollama', name: 'Ollama', icon: '🧠', cat: 'core', url: 'http://localhost:11434', probeUrl: ''),
  ServiceItem(id: 'redis', name: 'Redis', icon: '🗄', cat: 'core', url: null, probeUrl: ''),
  ServiceItem(id: 'qdrant', name: 'Qdrant', icon: '📊', cat: 'core', url: 'http://localhost:6333/dashboard', probeUrl: 'http://qdrant:6333/'),
  ServiceItem(id: 'media-api', name: 'Media API', icon: '▶', cat: 'core', url: 'http://localhost:8090', probeUrl: 'http://media-api:8090/healthz'),
  ServiceItem(id: 'homeassistant', name: 'Home Assistant', icon: '🏠', cat: 'ha', url: 'http://localhost:8123', probeUrl: 'http://homeassistant:8123/api/'),
  ServiceItem(id: 'nextcloud', name: 'Nextcloud', icon: '☁️', cat: 'storage', url: 'http://localhost:18082', probeUrl: 'http://nextcloud:80/'),
  ServiceItem(id: 'immich', name: 'Immich', icon: '📷', cat: 'photos', url: 'http://localhost:18083', probeUrl: 'http://immich-server:2283/'),
  ServiceItem(id: 'qbittorrent', name: 'qBittorrent', icon: '📥', cat: 'torrents', url: 'http://localhost:18084', probeUrl: 'http://qbittorrent:8080/'),
  ServiceItem(id: 'stremio', name: 'Stremio Server', icon: '🎬', cat: 'torrents', url: 'http://localhost:11480', probeUrl: 'http://stremio-server:11470/'),
  ServiceItem(id: 'torrserver', name: 'TorrServer', icon: '🌊', cat: 'torrents', url: 'http://localhost:18086', probeUrl: 'http://torrserver:5665/'),
  ServiceItem(id: 'jacred', name: 'Jacred', icon: '📂', cat: 'torrents', url: 'http://localhost:18087', probeUrl: 'http://jacred:9117/'),
  ServiceItem(id: 'searxng', name: 'SearXNG', icon: '🔎', cat: 'search', url: 'http://localhost:18081', probeUrl: 'http://searxng:8080/'),
];

final List<DashboardCategory> kDashboardCategories = [
  DashboardCategory(id: 'core', label: 'Ядро'),
  DashboardCategory(id: 'ha', label: 'Умный дом'),
  DashboardCategory(id: 'storage', label: 'Хранилище'),
  DashboardCategory(id: 'photos', label: 'Фото'),
  DashboardCategory(id: 'torrents', label: 'Медиа / Торренты'),
  DashboardCategory(id: 'search', label: 'Поиск'),
];
