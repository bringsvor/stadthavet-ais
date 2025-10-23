        // Update UI with translations
        function updateTranslations() {
            document.getElementById('page-title').textContent = t('title');
            document.getElementById('header-title').textContent = '🌊 ' + t('title');
            document.getElementById('header-subtitle').textContent = t('subtitle');
            document.querySelectorAll('[data-i18n]').forEach(el => {
                el.textContent = t(el.getAttribute('data-i18n'));
            });
        }

        updateTranslations();

        // Store initial map view
        const initialView = {
            center: [62.25, 4.75],
            zoom: 9
        };

        // Initialize map centered on Stad with wider zoom
        const map = L.map('map', {
            zoomControl: false,
            dragging: true,
            scrollWheelZoom: false,
            doubleClickZoom: false,
            touchZoom: true
        }).setView(initialView.center, initialView.zoom);

        L.tileLayer('https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png', {
            attribution: '&copy; OpenStreetMap contributors &copy; CARTO',
            subdomains: 'abcd',
            maxZoom: 20
        }).addTo(map);

        // Add custom home button control
        L.Control.HomeButton = L.Control.extend({
            onAdd: function(map) {
                const btn = L.DomUtil.create('button', 'home-button');
                btn.innerHTML = '🏠';
                btn.title = 'Tilbakestill zoom';
                btn.onclick = function() {
                    map.setView(initialView.center, initialView.zoom);
                };
                return btn;
            }
        });

        new L.Control.HomeButton({ position: 'topleft' }).addTo(map);

        // Fix map size after initialization
        setTimeout(() => {
            map.invalidateSize();
        }, 100);

        // Draw Stad crossing line
        const stadLine = L.polyline([
            [62.194513, 5.100380],
            [62.442407, 4.342984]
        ], {
            color: '#ef4444',
            weight: 3,
            opacity: 0.7,
            dashArray: '10, 10'
        }).addTo(map);

        // Draw waiting zones
        const eastZone = L.circle([62.25, 5.3], {
            radius: 10000,
            color: '#fbbf24',
            fillColor: '#fbbf24',
            fillOpacity: 0.1,
            weight: 2
        }).addTo(map);

        const westZone = L.circle([62.25, 4.2], {
            radius: 10000,
            color: '#34d399',
            fillColor: '#34d399',
            fillOpacity: 0.1,
            weight: 2
        }).addTo(map);

        // Store ship markers for updates
        let shipMarkers = [];
        let shipMarkersMap = new Map(); // Store ship markers by MMSI
        let crossingMarkers = new Map(); // Store crossing markers by MMSI+timestamp

        // Create SVG arrow icon for ships
        function createShipIcon(heading, color, isStationary = false) {
            const pulse = isStationary ? `<circle cx="12" cy="12" r="10" fill="none" stroke="#fbbf24" stroke-width="2" opacity="0.6"><animate attributeName="r" from="8" to="14" dur="2s" repeatCount="indefinite"/><animate attributeName="opacity" from="0.6" to="0" dur="2s" repeatCount="indefinite"/></circle>` : '';
            const svgIcon = `
                <svg width="24" height="24" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                    ${pulse}
                    <g transform="rotate(${heading || 0} 12 12)">
                        <path d="M12 2 L16 18 L12 15 L8 18 Z" fill="${color}" stroke="#fff" stroke-width="1.5"/>
                    </g>
                </svg>
            `;
            return L.divIcon({
                html: svgIcon,
                className: 'ship-marker',
                iconSize: [24, 24],
                iconAnchor: [12, 12]
            });
        }

        async function loadActiveShips() {
            const response = await fetch('/api/active-ships');
            const ships = await response.json();

            // Clear old markers
            shipMarkers.forEach(marker => map.removeLayer(marker));
            shipMarkers = [];
            shipMarkersMap.clear();

            ships.forEach(ship => {
                // Determine color based on speed
                const isMoving = (ship.sog || 0) > 3;
                const color = isMoving ? '#10b981' : '#f59e0b';

                // Use heading or course over ground
                const heading = ship.heading || ship.cog || 0;

                const marker = L.marker([ship.latitude, ship.longitude], {
                    icon: createShipIcon(heading, color, !isMoving)
                }).addTo(map);

                // Format time ago nicely
                function formatTimeAgo(timestamp) {
                    const now = new Date();
                    const then = new Date(timestamp);
                    const diffMs = now - then;
                    const diffMins = Math.floor(diffMs / 60000);
                    const diffHours = Math.floor(diffMs / 3600000);
                    const diffDays = Math.floor(diffMs / 86400000);

                    if (diffMins < 60) {
                        return `${diffMins}min sidan`;
                    } else if (diffHours < 24) {
                        const mins = diffMins % 60;
                        return mins > 0 ? `${diffHours}t ${mins}min sidan` : `${diffHours}t sidan`;
                    } else {
                        return `${diffDays}d sidan`;
                    }
                }

                const timeAgo = formatTimeAgo(ship.timestamp);

                let crossingInfo = '';
                if (ship.last_crossing_time) {
                    const crossingTimeAgo = formatTimeAgo(ship.last_crossing_time);
                    crossingInfo = `<br>Siste kryssing: ${ship.last_direction} (${crossingTimeAgo})`;
                } else {
                    crossingInfo = '<br>Har ikkje kryssat Stadt (i databasen)';
                }

                // Build popup content with optional fields
                let popupContent = `<strong>${ship.name}</strong><br>`;
                popupContent += `${t('map.type')}: ${ship.ship_type_name}<br>`;
                if (ship.length && ship.length > 0) {
                    popupContent += `Lengde: ${ship.length.toFixed(0)}m`;
                    if (ship.width && ship.width > 0) {
                        popupContent += ` × ${ship.width.toFixed(0)}m<br>`;
                    } else {
                        popupContent += `<br>`;
                    }
                }
                if (ship.destination && ship.destination.trim()) {
                    popupContent += `Destinasjon: ${ship.destination}<br>`;
                }
                if (ship.callsign && ship.callsign.trim()) {
                    popupContent += `Kallesignal: ${ship.callsign}<br>`;
                }
                popupContent += `Fart: ${(ship.sog || 0).toFixed(1)} knop<br>`;
                popupContent += `Kurs: ${(ship.cog || 0).toFixed(0)}°<br>`;
                popupContent += `Sist sett: ${timeAgo}${crossingInfo}`;

                marker.bindPopup(popupContent);

                shipMarkers.push(marker);
                shipMarkersMap.set(ship.mmsi, marker);
            });
        }

        // Fetch and display data
        async function loadStats() {
            const response = await fetch('/api/stats');
            const stats = await response.json();

            document.getElementById('stat-ships').textContent = stats.total_ships;
            document.getElementById('stat-crossings').textContent = stats.total_crossings;
            document.getElementById('stat-waiting').textContent = stats.total_waiting_events;
            document.getElementById('stat-recent').textContent = stats.recent_crossings_24h;

            // Update last data collection time
            updateLastUpdated(stats.last_data_collection);

            return stats;
        }

        async function loadCrossings() {
            const response = await fetch('/api/crossings');
            const crossings = await response.json();

            const list = document.getElementById('crossings-list');
            list.innerHTML = '';
            crossingMarkers.clear();

            crossings.slice(0, 20).forEach(crossing => {
                // Add marker to map
                const color = crossing.direction === 'E->W' ? '#fbbf24' : '#34d399';
                const marker = L.circleMarker([crossing.crossing_lat, crossing.crossing_lon], {
                    radius: 4,
                    fillColor: color,
                    color: '#fff',
                    weight: 1,
                    fillOpacity: 0.8
                }).addTo(map);

                marker.bindPopup(`
                    <strong>${crossing.name}</strong><br>
                    ${t('map.type')}: ${crossing.ship_type_name}<br>
                    ${t('map.direction')}: ${crossing.direction}<br>
                    ${t('map.time')}: ${formatDateTime(crossing.crossing_time)}
                `);

                // Store marker reference
                const markerId = `${crossing.mmsi}-${crossing.crossing_time}`;
                crossingMarkers.set(markerId, marker);

                // Add to list
                const item = document.createElement('div');
                item.className = 'event-item clickable';
                item.innerHTML = `
                    <div class="ship-name">${crossing.name}</div>
                    <div class="time">${formatDateTime(crossing.crossing_time)}</div>
                    <div class="direction-${crossing.direction.toLowerCase().replace('->', '')}">${crossing.direction} • ${crossing.ship_type_name}</div>
                `;

                // Add click handler to show popup on map
                item.addEventListener('click', () => {
                    // Try to find current ship position marker first
                    const shipMarker = shipMarkersMap.get(crossing.mmsi);
                    if (shipMarker) {
                        // Show ship's current position
                        shipMarker.openPopup();
                        map.setView(shipMarker.getLatLng(), 11);
                    } else {
                        // Fall back to crossing point if ship not currently visible
                        marker.openPopup();
                        map.setView([crossing.crossing_lat, crossing.crossing_lon], 11);
                    }
                });

                list.appendChild(item);
            });
        }

        async function loadWaiting() {
            const response = await fetch('/api/waiting');
            const waiting = await response.json();

            const list = document.getElementById('waiting-list');
            list.innerHTML = '';

            if (waiting.length === 0) {
                list.innerHTML = `<div class="loading">${t('loading.noWaiting')}</div>`;
                return;
            }

            waiting.forEach(event => {
                const item = document.createElement('div');
                item.className = 'event-item';
                const crossed = event.crossed ? t('event.crossed') : t('event.didNotCross');
                const hours = Math.round(event.duration_minutes/60);
                item.innerHTML = `
                    <div class="ship-name">${event.name}</div>
                    <div class="time">${formatDateTime(event.start_time)}</div>
                    <div>${t('event.zone')}: ${event.zone} • ${hours}t ${t('event.wait')} • ${crossed}</div>
                `;
                list.appendChild(item);
            });
        }

        async function loadCharts() {
            const response = await fetch('/api/daily-stats');
            const stats = await response.json();

            // Crossings vs Wind chart
            const ctx1 = document.getElementById('crossings-chart').getContext('2d');
            new Chart(ctx1, {
                type: 'line',
                data: {
                    labels: stats.map(s => formatDate(s.date)),
                    datasets: [{
                        label: 'Kryssingar',
                        data: stats.map(s => s.total_crossings || 0),
                        borderColor: '#60a5fa',
                        backgroundColor: 'rgba(96, 165, 250, 0.1)',
                        yAxisID: 'y',
                    }, {
                        label: 'Snitt vind (m/s)',
                        data: stats.map(s => s.avg_wind_speed || 0),
                        borderColor: '#fbbf24',
                        backgroundColor: 'rgba(251, 191, 36, 0.1)',
                        yAxisID: 'y1',
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    interaction: { mode: 'index', intersect: false },
                    plugins: { legend: { labels: { color: '#94a3b8' } } },
                    scales: {
                        y: { type: 'linear', position: 'left', ticks: { color: '#94a3b8' }, grid: { color: '#334155' } },
                        y1: { type: 'linear', position: 'right', ticks: { color: '#94a3b8' }, grid: { display: false } },
                        x: { ticks: { color: '#94a3b8' }, grid: { color: '#334155' } }
                    }
                }
            });

            // Weather chart
            const ctx2 = document.getElementById('weather-chart').getContext('2d');
            new Chart(ctx2, {
                type: 'line',
                data: {
                    labels: stats.map(s => formatDate(s.date)),
                    datasets: [{
                        label: 'Snitt vind (m/s)',
                        data: stats.map(s => s.avg_wind_speed || null),
                        borderColor: '#fbbf24',
                        backgroundColor: 'rgba(251, 191, 36, 0.1)',
                        yAxisID: 'y',
                        spanGaps: false
                    }, {
                        label: 'Ventehendingar',
                        data: stats.map(s => s.waiting_events || 0),
                        borderColor: '#8b5cf6',
                        backgroundColor: 'rgba(139, 92, 246, 0.1)',
                        yAxisID: 'y1',
                        spanGaps: false
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    interaction: { mode: 'index', intersect: false },
                    plugins: {
                        legend: { labels: { color: '#94a3b8' } }
                    },
                    scales: {
                        y: {
                            type: 'linear',
                            position: 'left',
                            ticks: { color: '#94a3b8' },
                            grid: { color: '#334155' },
                            beginAtZero: true
                        },
                        y1: {
                            type: 'linear',
                            position: 'right',
                            ticks: { color: '#94a3b8' },
                            grid: { display: false },
                            beginAtZero: true
                        },
                        x: { ticks: { color: '#94a3b8' }, grid: { color: '#334155' } }
                    }
                }
            });
        }

        async function loadWeather() {
            try {
                const response = await fetch('/api/weather');
                const weather = await response.json();

                const card = document.getElementById('weather-card');

                if (weather.length === 0) {
                    card.innerHTML = `<div class="loading">${t('weather.noData')}</div>`;
                    return;
                }

                const latest = weather[weather.length - 1];

                card.innerHTML = `
                    <div>
                        <strong>${t('weather.wind')}:</strong> ${latest.wind_speed ? latest.wind_speed.toFixed(1) : '-'} m/s
                    </div>
                    <div>
                        <strong>${t('weather.gust')}:</strong> ${latest.wind_gust ? latest.wind_gust.toFixed(1) : '-'} m/s
                    </div>
                    <div>
                        <strong>${t('weather.temp')}:</strong> ${latest.air_temperature ? latest.air_temperature.toFixed(1) : '-'} °C
                    </div>
                    <div>
                        ${formatDateTime(latest.timestamp)}
                    </div>
                `;
            } catch (error) {
                console.error('Error loading weather:', error);
            }
        }

        // Update last updated time based on data collection time
        function updateLastUpdated(timestamp) {
            if (!timestamp) {
                document.getElementById('update-time').textContent = '-';
                return;
            }
            const dataTime = new Date(timestamp);
            const day = String(dataTime.getDate()).padStart(2, '0');
            const month = String(dataTime.getMonth() + 1).padStart(2, '0');
            const year = dataTime.getFullYear();
            const hours = String(dataTime.getHours()).padStart(2, '0');
            const minutes = String(dataTime.getMinutes()).padStart(2, '0');
            const timeStr = `${day}/${month}/${year} ${hours}:${minutes}`;
            document.getElementById('update-time').textContent = timeStr;
        }

        // Load all data
        async function loadAllData() {
            const stats = await loadStats();
            await Promise.all([
                loadCrossings(),
                loadWaiting(),
                loadWeather(),
                loadActiveShips()
            ]);
        }

        loadAllData();
        loadCharts();

        // Refresh every 60 seconds
        setInterval(() => {
            loadAllData();
        }, 60000);
