<img width="1457" height="971" alt="Screen" src="https://github.com/user-attachments/assets/b142d43b-4278-4fce-b364-f4184e8e314b" />


# 🌊 MERGOHYDROX 🌊
### *L'Architettura Suprema per la Conservazione dell'Eredità Digitale*

![Python Version](https://img.shields.io/badge/python-3.8%2B-blue?style=for-the-badge&logo=python)
![License](https://img.shields.io/badge/license-MIT-teal?style=for-the-badge)
![Status](https://img.shields.io/badge/status-maestoso-blueviolet?style=for-the-badge)

**Mergohydrox** non è un semplice tool di scraping. È un ecosistema multimodale progettato per l'archeologia digitale e la preservazione totale. Che si tratti di un intero forum vBulletin, di un sito web statico o di una collezione di documenti PDF, Mergohydrox è in grado di catturare, trasformare e "fondere" i dati in archivi monolitici, eleganti e completamente autonomi.

---

## 🌀 Visione del Progetto

Nel vasto oceano del web, i dati sono fragili. Siti che scompaiono, database che si corrompono e link che si rompono sono la norma. Mergohydrox nasce per combattere questa entropia, offrendo strumenti per trasformare il caos di internet in strutture ordinate, leggibili e **immortali**, conservate in un unico file che non necessita di connessione o server esterni.

---

## ✨ Caratteristiche e Moduli

Mergohydrox è diviso in sette motori specializzati, ognuno con una missione precisa:

### 1. 🌊 Backup Forum (vBulletin)
*   **Scansione Profonda:** Individua automaticamente tutte le discussioni e le pagine di una sezione forum.
*   **Media Harvesting:** Scarica immagini, video e audio associati ai post, salvandoli in una struttura organizzata.
*   **Resilienza:** Gestisce ritardi, thread multipli e sessioni di download prolungate senza perdita di dati.

### 2. 💧 Conversione HTML (L'Archivio Elegante)
*   **Estetica Acquatica:** Converte i file HTML grezzi in un archivio con un tema visivo moderno, profondo e raffinato.
*   **Ricerca Integrata:** Implementa un motore di ricerca lato client per navigare istantaneamente tra le discussioni.
*   **Autonomia Totale:** Opzione per incorporare ogni singolo media tramite **Base64**, creando un unico file HTML che contiene tutto al suo interno.

### 3. 🌀 Backup + Conversione (Workflow Integrato)
*   **Automazione Totale:** Il modulo più potente per chi vuole il risultato finale in un colpo solo. Scarica il forum, recupera i media e genera l'archivio HTML elegante in un unico processo continuo.

### 4. 🫧 Ripristino Dati (Ingegneria Inversa)
*   **Analisi Inversa:** Prende un archivio generato da Mergohydrox e lo "smonta" per recuperare i dati originali.
*   **Esportazione Database:** Genera file **JSON** strutturati (ideali per importazioni in database moderni) o file **CSV** (per analisi in Excel/Sheets).
*   **Ricostruzione Media:** Estrae i file multimediali codificati in Base64 e li ricostruisce come file fisici sul disco.

### 5. 🌐 Mirror Sito Web
*   **Cattura Totale:** Scarica un intero sito web (pagine, CSS, JS, Immagini, Media).
*   **Link Rewriting:** Riscrive intelligentemente tutti i link interni affinché il sito funzioni perfettamente anche in modalità **offline**.

### 6. 🌊 Fusione Sito Statico (The Ultimate Engine)
*   **Il Monolito:** Prende un sito web composto da centinaia di file e lo comprime in **UN UNICO file HTML**.
*   **SPA Architecture:** Trasforma il sito in una *Single Page Application* con barra laterale per categorie, navigazione fluida e nessuna dipendenza esterna.
*   **Embed Massivo:** Ogni singola risorsa (anche PDF e Audio) viene iniettata nel file tramite Base64.

### 7. 📚 Unione PDF
*   **Unificazione Documentale:** Unisce tutti i PDF presenti in una cartella in un unico grande documento.
*   **Smart Bookmarking:** Crea automaticamente un indice (segnalibri) nel PDF finale per saltare direttamente all'inizio di ogni file originale.

---

## 🚀 Installazione

### Prerequisiti
*   **Python 3.8** o versioni superiori.

### Configurazione
1. **Clona il repository:**
   ```bash
   git clone https://github.com/tuo-username/Mergohydrox.git
   cd Mergohydrox
   ```
Installa le dipendenze
   """pip install requests beautifulsoup4 pypdf"""

   Avvia il programma: python Mergohydrox.py



📖 Guida all'Uso
Scenario A: "Voglio salvare un forum prima che chiuda"
Apri il tab 🌊 Backup Forum.
Inserisci l'URL della sezione.
Spunta "Scarica anche i file multimediali".
Clicca AVVIA BACKUP.
Una volta terminato, usa il tab 💧 Converti 
→
→
 HTML selezionando la cartella creata per ottenere il tuo archivio leggibile e bellissimo.
Scenario B: "Ho un sito web scaricato e voglio un unico file per portarlo su una chiavetta"
Usa il modulo 🌐 Mirror Sito Web per assicurarti di avere tutto il sito sul tuo PC.
Vai nel tab 🌊 Fusione Sito Statico.
Seleziona la cartella del sito.
Clicca AVVIA FUSIONE.
Otterrai un unico file .html che contiene l'intero sito, immagini e navigazione inclusi.
Scenario C: "Devo migrare i dati di un archivio in un nuovo database"
Vai nel tab 🫧 Ripristino Dati.
Seleziona il file HTML dell'archivio.
Scegli Converti in JSON.
Il programma estrarrà post, autori, date e contenuti, salvandoli in un formato pronto per il database.
🛠 Specifiche Tecniche
Interfaccia: GUI sviluppata con tkinter con animazioni custom (Bubble Animator).
Concurrency: Gestione avanzata dei thread per ottimizzare il download massivo.
Parsing: Motore di estrazione basato su BeautifulSoup4 con logica di fallback per strutture HTML non standard.
Memory Management: Implementazione di cicli di gc.collect() per garantire la stabilità durante l'elaborazione di file di grandi dimensioni.
⚖️ Licenza
Distribuito sotto la licenza MIT. Mergohydrox è uno strumento per la libertà della conoscenza.
