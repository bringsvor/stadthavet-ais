# Om Stadthavet AIS Sporing

## Kva er dette?

Dette er eit system for å spore skipstrafikk som kryssar Stad-halvøya i Noreg. Systemet samlar inn data frå Barentswatch sitt AIS API og analyserer skip som kryssar den imaginære linja over Stad.

## Kvifor?

Stad Skipstunnel er eit planlagt prosjekt for å byggje verdas første skipstunnel gjennom Stad-halvøya. Det offentlege ordskiftet fokuserer mykje på kor mykje tid skip brukar på å vente på betre vêr før dei kan krysse Stad.

Dette systemet prøver å kvantifisere:
- Kor mange skip kryssar Stad dagleg
- Kor mange skip ventar i opne farvatn på grunn av dårleg vêr (vind >10 m/s)
- Samanhengen mellom tal på kryssingar og vêrforhold

Dette er eit hobbyprosjekt og er i ein tidleg fase. Det er difor ikkje råd å konkludere noko som helst om kost-nytte av tunnelen.

## Korleis fungerer det?

### Datainnsamling
- Systemet hentar AIS-data frå [Barentswatch](https://www.barentswatch.no/) kvar 12. time
- Data blir lagra i ein database (SQLite lokalt, PostgreSQL i produksjon)
- Vêrdata blir henta frå [Meteorologisk institutt](https://frost.met.no/) sin Frost API

### Kryssingsdetektor
Ein kryssing blir registrert når eit skip kryssar den imaginære linja frå:
- Start: 62.194513°N, 5.100380°E
- Slutt: 62.442407°N, 4.342984°E

Retning blir bestemt basert på kvar skipet kjem frå (aust eller vest).

### Ventesonedetektor
Systemet identifiserer skip som "ventar" basert på:
- Låg fart (<3 knop)
- Lang tid (>120 minutt) i ventesone
- Dårleg vêr (vind >10 m/s)

Det er to ventesoner:
- **Austleg sone**: 62.25°N, 5.3°E (radius 10 km) - skip som ventar på å krysse vestover
- **Vestleg sone**: 62.25°N, 4.2°E (radius 10 km) - skip som ventar på å krysse austover

Utviklar av applikasjonen har ikkje nautisk utdanning så ein må hauste litt erfaringstal for optimalisering av ventesoner.

## Teknisk informasjon

### Stack
- **Backend**: Python 3, Flask
- **Database**: SQLite (lokal), PostgreSQL (produksjon)
- **Frontend**: Vanilla JavaScript, Leaflet.js, Chart.js
- **API**: Barentswatch AIS API, MET Norway Frost API

### Kjeldekode
Prosjektet er open source og tilgjengeleg på GitHub (lenke kjem).

## Avgrensingar

- AIS-data frå Barentswatch har berre 14 dagars historikk
- Ikkje alle skip sender AIS-signal
- Ventesone-deteksjonen er basert på enkle heuristikkar og kan ha falske positivar
- Vêrdata er frå Svinøy Fyr værstasjon (SN59800) som kan avvike frå faktiske forhold på havet

## Kontakt

For spørsmål eller tilbakemeldingar, kontakt Torvald Baade Bringsvor, bringsvor@bringsvor.com.

---

*Sist oppdatert: Oktober 2025*
