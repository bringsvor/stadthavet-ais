// i18n translations
const translations = {
    nn: {
        title: "Stadthavet AIS Sporing",
        subtitle: "Sanntidsovervaking av skipstrafikk over Stad-halvøya",
        stats: {
            totalShips: "Skip totalt",
            crossings: "Kryssingar",
            waitingEvents: "Ventehendingar",
            last24h: "Siste 24t",
            positions: "Posisjonar",
            modalTitle: "📊 Statistikk",
            topShips: "🏆 Topp 10 skip etter kryssingar"
        },
        table: {
            shipName: "Namn",
            shipType: "Type",
            crossings: "Kryssingar"
        },
        sections: {
            recentCrossings: "Siste kryssingar",
            waitingEvents: "Ventehendingar",
            crossingsVsWind: "Daglige kryssingar vs vindstyrke",
            weatherConditions: "Værforhold"
        },
        loading: {
            crossings: "Lastar kryssingar...",
            waiting: "Lastar ventehendingar...",
            noWaiting: "Ingen ventehendingar registrert",
            stats: "Lastar..."
        },
        info: {
            clickToView: "Klikk på eit skip for å sjå det i kartet"
        },
        map: {
            direction: "Retning",
            type: "Type",
            time: "Tid"
        },
        event: {
            zone: "Sone",
            wait: "venting",
            crossed: "✓ krossa",
            didNotCross: "✗ krossa ikkje"
        },
        weather: {
            current: "Aktuelt vêr (Svinøy Fyr)",
            wind: "Vind",
            gust: "Vindkast",
            temp: "Temperatur",
            noData: "Ingen værdata tilgjengeleg"
        },
        webcams: {
            title: "Webcams i området"
        },
        legend: {
            title: "Forklaring",
            crossingLine: "Raud stipla linje = Stad-kryssingslinje",
            eastZone: "Gul sirkel = Austleg ventesone (venter på å krysse vestover)",
            westZone: "Grøn sirkel = Vestleg ventesone (venter på å krysse austover)",
            yellowDots: "Gule prikkar = Kryssingar aust→vest",
            greenDots: "Grøne prikkar = Kryssingar vest→aust",
            info: "Systemet sporer skip som passerer Stad og identifiserer skip som ventar i opne farvatn når vinden er >10 m/s. Data blir samla kvar 12. time for å byggje opp historikk over tid."
        },
        status: {
            lastUpdated: "Sist oppdatert:"
        },
        nav: {
            about: "Om oss",
            statistics: "📊 Statistikk"
        }
    },
    en: {
        title: "Stadthavet AIS Tracker",
        subtitle: "Real-time monitoring of ship traffic crossing the Stad peninsula",
        stats: {
            totalShips: "Total Ships",
            crossings: "Crossings",
            waitingEvents: "Waiting Events",
            last24h: "Last 24h",
            positions: "Positions",
            modalTitle: "📊 Statistics",
            topShips: "🏆 Top 10 Ships by Crossings"
        },
        table: {
            shipName: "Name",
            shipType: "Type",
            crossings: "Crossings"
        },
        sections: {
            recentCrossings: "Recent Crossings",
            waitingEvents: "Waiting Events",
            crossingsVsWind: "Daily Crossings vs Wind Speed",
            weatherConditions: "Weather Conditions"
        },
        loading: {
            crossings: "Loading crossings...",
            waiting: "Loading waiting events...",
            noWaiting: "No waiting events recorded",
            stats: "Loading..."
        },
        info: {
            clickToView: "Click on a ship to view it on the map"
        },
        map: {
            direction: "Direction",
            type: "Type",
            time: "Time"
        },
        event: {
            zone: "Zone",
            wait: "wait",
            crossed: "✓ crossed",
            didNotCross: "✗ did not cross"
        },
        weather: {
            current: "Current Weather (Svinøy Fyr)",
            wind: "Wind",
            gust: "Gust",
            temp: "Temperature",
            noData: "No weather data available"
        },
        webcams: {
            title: "Webcams in the Area"
        },
        legend: {
            title: "Legend",
            crossingLine: "Red dashed line = Stad crossing line",
            eastZone: "Yellow circle = East waiting zone (waiting to cross westward)",
            westZone: "Green circle = West waiting zone (waiting to cross eastward)",
            yellowDots: "Yellow dots = Eastward→Westward crossings",
            greenDots: "Green dots = Westward→Eastward crossings",
            info: "The system tracks ships passing by Stad and identifies ships waiting in open water when wind is >10 m/s. Data is collected every 12 hours to build up history over time."
        },
        status: {
            lastUpdated: "Last updated:"
        },
        nav: {
            about: "About",
            statistics: "📊 Statistics"
        }
    }
};

// Default language: Nynorsk
let currentLang = 'nn';

function t(key) {
    const keys = key.split('.');
    let value = translations[currentLang];
    for (const k of keys) {
        value = value[k];
        if (!value) return key;
    }
    return value;
}

function formatDateTime(dateString) {
    const date = new Date(dateString);
    // Use Norwegian locale with 24-hour clock
    return date.toLocaleString('nn-NO', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        hour12: false
    });
}

function formatDate(dateString) {
    const date = new Date(dateString);
    return date.toLocaleDateString('nn-NO', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit'
    });
}
