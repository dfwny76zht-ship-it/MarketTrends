# Market Trends

Projektbrief für Claude Code, Stand 18.11.2026.

Eigenständiges Projekt von GeniScent, getrennt von LIMS und GeniScent-API: eigener Ordner (`~/MarketTrends`), eigenes Repo, eigene Datenbank, eigener Login.

Die Datenbank ist eine eigene PostgreSQL-Instanz (eigener Container, eigenes Volume, eigene Zugangsdaten). Sie teilt sich weder Server noch Datenbank noch Benutzer mit der GeniScent-API/LIMS, und es gibt keine Verbindung zwischen beiden.

## Ziel

Hoya-Angebote von Händlern, Gärtnereien, Großhändlern und Importhändlern laufend erfassen und als Zeitreihen auswerten:
- Welche Arten und Sorten gibt es wo, zu welchem Preis, wie lange verfügbar und in welcher Menge?
- Welche Arten werden shopübergreifend häufig geliefert?
- Wie hängen die Shops zusammen?
- Zu welchen Konditionen verkaufen Groß- und Importhändler?

Die Ergebnisse fließen in Sortiment, Preise und Marktargumente ein.

## Betrieb

- Bedienung nur im Browser (Desktop zuerst, mobil lesbar), nicht am Bildschirm des Pi.
- **Hetzner** (bereit): Web-Tool, eigene PostgreSQL-Instanz (siehe oben), Zeitplan aller Läufe.
- **Raspberry Pi im Lab** (bereit): zweiter Sammler für Shops, die Rechenzentrums-IPs sperren, und Ablage für das nächtliche Datenbank-Backup. Der Pi verbindet sich nur ausgehend mit Hetzner (Token).
- Docker Compose. HTTPS über das vorhandene nginx auf Hetzner, eigener Port 8445 (443 belegt der SSH-Zugang). Die GeniScent-API bleibt unverändert. Zugang für beide Gründer:innen.

## Funktionen

### 1. Shops
- Liste aller Shops mit Status: vorgeschlagen, in Einrichtung, aktiv, pausiert, nicht erlaubt, Adapter defekt.
- „+“ legt einen Shop mit URL und Notiz an. Er bleibt „in Einrichtung“, bis ein Adapter steht (siehe 3).
- Typen: Großhandel, Importhändler, Händler, Gärtnerei.
- Steckbrief je Shop:
  - Land, Währung, netto oder brutto;
  - Zugang: öffentlich oder eigenes Kundenkonto;
  - welche Daten der Shop liefert (Preis, Verfügbarkeit, Stückzahl, Topfgröße);
  - letzter Lauf, Fehler, Prüfdatum von robots.txt und AGB;
  - Konditionen mit Änderungsverlauf: Mindestbestellwert, Mindestmengen, Staffelpreise, Versand- und Phytokosten, Lieferzeit, Zahlungsbedingungen, Import- oder Liefertermine.
- Start mit:
  - Uhlig: uhlig-kakteen.de, JTL-Shop, nur Verfügbarkeit;
  - FlorAccess: floraccess.com, Großhandel mit Stückzahlen;
  - Kakteen-Haage: kakteen-haage.de, RSS-Feed der Hoya-Kategorie;
  - Jungle Leaves: jungle-leaves.de, Shopify, Hoyas unter „Sukkulenten“;
  - Ben's Jungle: bens-jungle.com.

### 2. Datenerfassung (ohne Claude)
- Läuft automatisch, je Shop höchstens einmal täglich und nachts, seltener wenn der Shop es verlangt.
- Je Shop ein Adapter mit einheitlicher Ausgabe. Vorhandene Schnittstellen haben Vorrang: Shopify-JSON, WooCommerce Store API, RSS. Erst danach wird HTML ausgewertet.
- Shops mit eigenem Kundenkonto werden eingeloggt abgefragt. Die Zugangsdaten liegen in `.env` oder einem Secret-Store, nie im Repo. Sitzungen werden wiederverwendet.
- Gespeichert wird alles, was der Shop zeigt:
  - Name wie im Shop, Artikelnummer, URL, Kategorie, Bild-URL;
  - Preis und Staffelpreise, Währung;
  - Verfügbarkeitstext und daraus ein einheitlicher Status (verfügbar, knapp, ausverkauft, unbekannt);
  - Stückzahl, Topf- und Pflanzengröße;
  - Zeitpunkt.
- Zusätzlich wird die Rohseite komprimiert gespeichert. So lassen sich alte Daten neu auswerten, wenn ein Adapter besser wird.
- Preise werden intern zusätzlich vereinheitlicht: netto, in EUR zum Tageskurs, nach Größenklasse.
- Das Tool leitet Ereignisse ab: neu, verschwunden, ausverkauft, wieder verfügbar, Stückzahl gestiegen (Nachlieferung), Preisänderung.
- Wo Artikelnummern fortlaufend vergeben werden (z. B. FlorAccess), schätzt das Tool daraus, wann ein Angebot angelegt wurde.

### 3. Pflege und Shopsuche durch Claude
- Claude Code arbeitet einmal im Monat automatisch und jederzeit per Knopf im Tool. Das Ergebnis kommt als Pull Request zur Freigabe, dazu ein Hinweis per ntfy.
- **Adapter pflegen:**
  1. robots.txt und AGB prüfen und das Ergebnis festhalten.
  2. Seitenstruktur ansehen und den Adapter schreiben oder anpassen.
  3. Den Adapter gegen gespeicherte Rohseiten testen.
- **Konditionen aktualisieren:** Claude liest Konditionen aus FAQ, AGB und Versandseiten und schreibt sie in den Steckbrief.
- **Neue Shops suchen:** Händler, Gärtnereien, Großhändler und Importhändler mit Hoya-Angebot, auch Exporteure, die in die EU liefern. Treffer erscheinen mit kurzer Begründung als „vorgeschlagen“ und werden per Klick aufgenommen.
- Der tägliche Lauf braucht Claude nicht. Liefert ein Adapter keine Treffer, Parserfehler oder eine stark abweichende Anzahl, markiert das Tool den Shop für den nächsten Pflegelauf.

### 4. Vorsichtsregeln
- Öffentliche Seiten und eigene Kundenkonten. Andere Login-Bereiche bleiben außen vor.
- Für öffentliche Seiten wird robots.txt vor jedem Lauf geprüft. Verbieten die AGB automatisierten Zugriff, bekommt der Shop den Status „nicht erlaubt“ und wird nicht abgefragt.
- Höchstens ein Lauf am Tag und mindestens 5 Sekunden Abstand zwischen Anfragen. Bedingte Anfragen (ETag, If-Modified-Since).
- User-Agent mit Projektnamen und ohne Kontaktadresse. Kein Kontakt zu Shops: keine Formulare, keine Mails, keine Newsletter-Anmeldungen.
- Bei 403 oder 429 bricht der Lauf ab und das Tool fragt seltener ab.
- Die Daten werden nur intern genutzt und weder veröffentlicht noch weitergegeben. Personenbezogene Daten wie Bewertungen werden nicht gespeichert.

### 5. Arten und Sorten
- Eine im Tool pflegbare Taxonomie: Art (z. B. Hoya carnosa), darunter Sorte oder Form (z. B. ‚Krimson Queen‘, Splash). Die Artenliste wird beim Start einmalig aus dem LIMS übernommen, falls es dort eine gibt; danach gibt es keine Verbindung zum LIMS mehr.
- Jedes Angebot gehört zu einer Art und optional zu einer Sorte. Das Tool schlägt Zuordnungen vor. Grundlage sind Namensvergleich, früher bestätigte Schreibweisen und Sammelnummern wie EPC oder IML.
- Vorschläge werden einzeln oder gesammelt bestätigt. Was nicht zugeordnet ist, landet in einer Liste zum Abarbeiten.
- Eine einmal zugeordnete Schreibweise gilt künftig automatisch.

### 6. Auswertung (Vorbild: YouTube Analytics)
- **Übersicht:** Zeitraum wählbar (7 Tage bis alles), Shopfilter. Kennzahlen mit Verlauf: beobachtete Arten und Angebote, Ereignisse, Preisänderungen.
- **Seite je Art und Sorte:**
  - Preis im Zeitverlauf, je Shop und als Median;
  - Verfügbarkeit als Zeitleiste je Shop;
  - Stückzahl und daraus der geschätzte Abverkauf;
  - Zahl der anbietenden Shops;
  - Preise nach Größenklasse.
- **Grafikfenster:** wie im erweiterten Modus von YouTube Analytics, oben die Grafik und darunter die Tabelle.
  - Wer Zeilen in der Tabelle oder in der Suche anhakt, sieht diese Arten und Sorten übereinander verglichen.
  - Die Kennzahl ist wählbar: Preis, Verfügbarkeit, Stückzahl oder Ereignisse.
  - Das Fenster lässt sich andocken, in der Größe ändern, einklappen und maximieren und bleibt beim Wechsel der Seite erhalten.
- Eine Merkliste für Arten, zu denen Ereignisse gemeldet werden (siehe 10).
- Tabellen lassen sich sortieren und filtern, zeigen kleine Verlaufsgrafiken und lassen sich als CSV exportieren.
- Zu jedem Wert ist die Herkunft sichtbar: Shop, Zeitpunkt, live oder Archiv. Fehlende Werte bleiben leer und werden nicht geschätzt.

### 7. Trends ohne KI
- Alle Trends sind regelbasiert und statistisch berechnet; KI ist dafür nicht nötig.
- Gezählt werden die Ereignisse je Art und Sorte und Woche über alle Shops.
- Trendwert: die letzten 4 Wochen gegen die 12 Wochen davor.
- Ranglisten, z. B.:
  - „shopübergreifend am häufigsten nachgeliefert“ (etwa Hoya ‚Rosita‘);
  - neu aufgetaucht, verschwunden;
  - Preis gefallen oder gestiegen.
- Signale aus dem Großhandel: Zugänge und Abverkauf bei Groß- und Importhändlern aus den Stückzahlen, Import- und Liefertermine aus den Konditionen.
- Optional als Hintergrundreihe: monatliche Importe lebender Pflanzen nach Herkunftsland (Eurostat Comext, z. B. aus Thailand).

### 8. Verflechtungen zwischen Shops
- Ebenfalls ohne KI berechnet:
  - Überschneidung der Sortimente;
  - zeitliche Abfolge von Ereignissen, etwa wenn ein Großhändler Ware bekommt und ein Händler sie Tage später listet;
  - gleichzeitige Preisänderungen;
  - identische Produktfotos (Bild-Hash) und gleiche Lieferantencodes.
- Darstellung als Matrix und als Netz der Shops, mit der Stärke jeder Verbindung und Beispielen. Das sind Hinweise, keine Beweise.

### 9. Rückwirkende Daten
- Einmaliger Lauf je Shop, manuell gestartet. Er sucht in der Wayback Machine (CDX-API) und in Common Crawl nach alten Kategorie- und Artikelseiten und wertet sie mit Archiv-Parsern aus.
- Archivdaten sind gröber: einzelne Zeitpunkte und alte Layouts. Die Grafiken kennzeichnen sie, z. B. gestrichelt.
- Auch diese Abfragen laufen mit Pausen zwischen den Anfragen.

### 10. Benachrichtigungen
- **ntfy** (Server und Topic wie in der bestehenden Einrichtung) meldet:
  - Adapter defekt;
  - Pflegelauf wartet auf Freigabe;
  - neue Shop-Vorschläge;
  - Ereignisse zu Arten auf der Merkliste.
- **Wochenmail** an die GeniScent-Adresse bei Proton: kurze Zusammenfassung der Woche mit den wichtigsten Trends und einem Link zur Auswertung. Versand per SMTP.

## Datenmodell (Kern)

`shops`, `shop_terms` (Konditionen mit Verlauf), `shop_candidates`, `adapters` (Version, Status), `runs` (Zeit, Ergebnis, Fehler), `listings` (Shop, Artikelnr., URL, zuerst/zuletzt gesehen), `observations` (Listing, Zeit, Preis, Währung, netto/brutto, Status, Stückzahl, Größen, Rohfelder als JSON, Quelle live/Archiv), `events`, `species`, `cultivars`, `aliases`, `assignments` (Listing → Art/Sorte, bestätigt ja/nein), `image_hashes`, `watchlist`, `snapshots` (Rohseite, komprimiert), optional `trade_stats`.

## Technik (Vorschlag)

- Backend: Python, FastAPI, PostgreSQL (eigene Instanz im eigenen Container, nicht die Datenbank von LIMS oder GeniScent-API).
- Erfassung: httpx und selectolax; Playwright für Logins und für Seiten, die ohne JavaScript nichts zeigen.
- Auswertung: pandas für Trends; imagehash für Produktfotos.
- Zeitplan: systemd-Timer oder APScheduler.
- Frontend: kleines SPA mit Svelte und Apache ECharts.
- Benachrichtigungen: ntfy per HTTP, Mail per SMTP.
- Tests: je Adapter gegen gespeicherte Rohseiten.
- Backup: nächtlicher pg_dump mit Kopie auf den Pi.

## Bei Einrichtung eintragen (`.env`)

- Domain;
- ntfy-Server und Topic;
- Proton-Adresse und SMTP-Zugang;
- Anthropic-API-Schlüssel und GitHub-Zugang für den Pflegelauf;
- Zugangsdaten der Kundenkonten;
- Token für den Pi.

## Reihenfolge

1. Grundgerüst: Datenbank, Läufe, Shopliste mit „+“, Login, Deployment auf Hetzner, ntfy.
2. Adapter für die fünf Startshops.
3. Arten und Sorten mit Zuordnungsvorschlägen.
4. Auswertung mit Grafikfenster und Merkliste.
5. Trends und Wochenmail.
6. Pi als zweiter Sammler und Backup.
7. Verflechtungen zwischen Shops.
8. Rückwirkende Daten.
9. Monatlicher Pflegelauf mit Shopsuche durch Claude Code.
