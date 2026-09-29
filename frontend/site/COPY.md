# VocalGrid — copy deck (single source of truth for site + film)

Direction: illoca-style (Awwwards SOTD, Unseen Studio). Warm cream grid paper, one orange accent,
friendly sans headlines, serif italic for the emotional half-line, mono for small labels, handwritten
notes (Caveat) that point at things. Calm, confident, concrete. No vague poetry.

Palette: paper #f5f3ec · grid line #e6e3d6 · ink #24271f · muted #6f7266 · orange #fc602f ·
screen #141913 · screen text #eef0e4 · sage (on screen only) #c0d788.
Fonts: Instrument Sans (headlines/body), Instrument Serif Italic (accent half-lines),
JetBrains Mono (labels), Caveat (hand notes).

## Promise
Good ideas. Different languages. *Still connected.*
Sub: Spoken translation for client calls. They speak Italian; you hear English a few seconds later,
in a voice that can sound like theirs, with their permission.

## How it works (numbered ① ② ③)
1. **They speak.** — The client talks in Italian, as usual. VocalGrid listens through your microphone.
   Hand note: "just talk normally"
2. **It translates.** — Speech becomes text, the text is translated phrase by phrase. The first English
   arrives about 3–5 seconds after they start.
   Hand note: "phrase by phrase, not word by word"
3. **You hear it.** — Spoken English in your headphones, optionally in a voice matched to the speaker.
   Hand note: "only with their consent"

## Where you use it
- Client calls (Google Meet — planned)
- In the room (one laptop, headphones — in pilot evaluation)
- Shared sessions (everyone picks a language — planned)

## Languages
Many languages. *One conversation.* Italian → English is tested today; other European pairs are in validation.

## Honesty labels (use exactly)
"Tested today: Italian → English" · "Planned" · "In pilot evaluation" · "Illustration" · "Sample text"

## Film scenes (36 s, match the site's words)
1. Good ideas. / *Different languages.*   label: VOCALGRID
2. They speak. / *In Italian, as usual.*  label: ① LISTEN
3. It translates. / *Phrase by phrase.*   label: ② TRANSLATE
4. You hear it. / *In English. In a familiar voice.* label: ③ HEAR · voice matching with consent
5. Many languages. / *One conversation.*  label: LANGUAGES · Italian → English tested today
6. lingosync ✳ / *Still connected.*        label: EARLY ACCESS

## Audience motion and European language editions

Keep agencies/consultancies first. Independent consultants share the client-call problem;
import/export is a research challenger; teaching is exploratory, not a validated paid segment.
Rotate every six seconds, pause on focus/hover and with the global motion control; respect reduced motion.
Only each audience title appears in the hero; descriptions and research status are editorial context, not extra hero lines. There is no next/refresh control. The entries below generate the audience component and localized landing pages. Website language
does not imply support for that spoken translation direction. The full fit flow and film remain English.

<!-- locale-copy -->
```json
{
  "en": {
    "audiences": [
      [
        "for agencies & consultancies",
        "Understand the client’s brief. Keep the detail in the discussion.",
        "Primary pilot audience"
      ],
      [
        "for freelancers",
        "Follow client feedback. Explain the work in your own words.",
        "Client-call use case · setup validation required"
      ],
      [
        "for import & export teams",
        "Clarify requirements with suppliers and overseas partners.",
        "Research segment · workflow to validate"
      ],
      [
        "for your ideas",
        "Speak in the language you’re most comfortable using.",
        "Broader language directions are planned"
      ],
      [
        "for teachers & lecturers",
        "Explore teaching in your language while learners listen in theirs.",
        "Exploratory use case · group listening is planned"
      ]
    ],
    "next": "Next use case",
    "language": "Website language"
  },
  "it": {
    "title": "VocalGrid — Traduzione vocale per riunioni con clienti internazionali",
    "description": "Traduzione vocale per agenzie, consulenti e clienti internazionali. Prototipo italiano → inglese, con corrispondenza vocale facoltativa e consenso del parlante.",
    "language": "Lingua del sito",
    "next": "Prossimo caso d’uso",
    "audiences": [
      [
        "per agenzie e società di consulenza",
        "Comprendi le richieste del cliente. Segui anche i dettagli.",
        "Pubblico prioritario del progetto pilota"
      ],
      [
        "per consulenti freelance",
        "Segui i feedback dei clienti. Spiega le tue idee con parole tue.",
        "Configurazione da verificare prima del progetto pilota"
      ],
      [
        "per chi lavora nell’import-export",
        "Chiarisci le esigenze con fornitori e partner all’estero.",
        "Segmento di ricerca · flusso di lavoro da validare"
      ],
      [
        "per condividere le tue idee",
        "Parla nella lingua in cui ti senti più a tuo agio.",
        "Altre combinazioni linguistiche sono previste"
      ],
      [
        "per docenti e formatori",
        "Esplora lezioni nella tua lingua, con ascolto nella lingua degli studenti.",
        "Caso esplorativo · ascolto di gruppo previsto"
      ]
    ],
    "headline": [
      "Buone idee.",
      "Lingue diverse.",
      "Sempre in contatto."
    ],
    "lede": "Traduzione vocale per le conversazioni di lavoro. Una persona parla italiano; tu ascolti in inglese pochi secondi dopo. La voce può essere simile alla sua, solo con il suo consenso.",
    "status": "Prototipo in accesso anticipato · Testato oggi: italiano → inglese",
    "open": "Apri il prototipo",
    "cta": "Verifica l’idoneità · in inglese",
    "watch": "Guarda il video",
    "how": "Come funziona",
    "pricing": "Prezzi",
    "skip": "Vai al contenuto",
    "stepsTitle": [
      "Tre passaggi.",
      "Per seguire la conversazione."
    ],
    "steps": [
      [
        "La persona parla.",
        "Il prototipo acquisisce il parlato italiano dal microfono del computer."
      ],
      [
        "VocalGrid traduce.",
        "Il parlato diventa testo e viene tradotto frase per frase. Le prime parole in inglese arrivano dopo alcuni secondi."
      ],
      [
        "Tu ascolti.",
        "Ascolta la traduzione in cuffia, con una voce neutra oppure una voce simile a quella del parlante, con il suo consenso."
      ]
    ],
    "usesTitle": [
      "Le tue chiamate.",
      "Le tue riunioni."
    ],
    "uses": [
      [
        "Chiamate con i clienti",
        "Previsto",
        "Seguire una chiamata Google Meet nella propria lingua. L’integrazione audio non è ancora disponibile: oggi il prototipo usa il microfono."
      ],
      [
        "Nella sala riunioni",
        "In valutazione pilota",
        "Un portatile sul tavolo acquisisce il parlato; chi ha bisogno della traduzione ascolta in cuffia. Acustica e sovrapposizione delle voci richiedono una verifica."
      ],
      [
        "Sessioni condivise",
        "Previsto",
        "Ogni partecipante sceglie la lingua di ascolto. Le sessioni multilingue di gruppo non sono ancora disponibili."
      ]
    ],
    "languagesTitle": "Un sito nella tua lingua. Un prodotto in evoluzione.",
    "languagesText": "Puoi leggere questo sito in italiano, inglese, tedesco e francese. Questo non cambia le lingue del prototipo: oggi è testato italiano → inglese. Le altre combinazioni devono essere validate prima di essere offerte.",
    "filmTitle": [
      "Scopri l’idea.",
      "In 36 secondi."
    ],
    "filmNote": "Video concettuale in inglese · senza audio · non è una registrazione di traduzione dal vivo.",
    "results": "Risultati iniziali",
    "metrics": [
      [
        "Primo audio tradotto",
        "3,2–4,6 s dall’inizio del parlato in 14 simulazioni con registrazioni. Ritardo mediano per clip: 3,8–5,6 s; massimo: 9,6 s. Avvio a freddo escluso."
      ],
      [
        "Errori nel riconoscimento italiano",
        "3,6–4,4% su tre clip di podcast; 11,3–13,7% su due brani di libri. Misura la trascrizione, non la qualità della traduzione."
      ]
    ],
    "method": "Test interni del 27 settembre 2026 con audio registrato e riprodotto in tempo reale su GPU L4. Non sono garanzie per riunioni reali. Questi dati riguardano la precedente pipeline Nemotron, non l’attuale configurazione Soniox.",
    "plan": "Progetto pilota guidato",
    "period": " / 30 giorni",
    "planIntro": "Una riunione ricorrente, configurata insieme a te.",
    "features": [
      "4 ore di ascolto tradotto",
      "Verifica della configurazione audio",
      "Una combinazione linguistica validata",
      "Valutazione dei risultati",
      "Nessun rinnovo automatico"
    ],
    "offer": "Proposta di prezzo in USD, disponibile dopo la verifica della configurazione. Nessun pagamento su questo sito. Un’ora per un ascoltatore equivale a un’ora di ascolto.",
    "support": "La verifica di idoneità e la scheda scaricabile sono attualmente in inglese. Il modulo non invia richieste né prenota appuntamenti.",
    "faq": "Prima di iniziare",
    "questions": [
      [
        "Dove viene elaborato l’audio?",
        "Nel cloud, non sul dispositivo. Prima di usare conversazioni riservate, verifica con noi il luogo di elaborazione e i tempi di conservazione."
      ],
      [
        "È adatto alle lezioni?",
        "È un caso d’uso da esplorare, non un servizio didattico già validato. L’ascolto di gruppo e altre combinazioni linguistiche sono previsti."
      ],
      [
        "Il sito in italiano abilita altre lingue?",
        "No. La lingua del sito è indipendente dalle lingue supportate dal prototipo. Oggi è testata la direzione italiano → inglese."
      ]
    ],
    "pause": "Pausa animazioni",
    "resume": "Riprendi animazioni",
    "back": "Torna su",
    "illustration": "Illustrazione · testo di esempio",
    "source": "ITALIANO",
    "target": "INGLESE",
    "preview": "ANTEPRIMA",
    "voice": "Voce facoltativa · con consenso"
  },
  "de": {
    "title": "VocalGrid — Gesprochene Übersetzung für internationale Kundengespräche",
    "description": "Gesprochene Übersetzung für Agenturen, Beratungen und internationale Kunden. Prototyp Italienisch → Englisch mit optionaler Stimmanpassung nach Zustimmung.",
    "language": "Sprache der Website",
    "next": "Nächster Anwendungsfall",
    "audiences": [
      [
        "für Agenturen & Beratungen",
        "Verstehen Sie das Kundenbriefing. Verfolgen Sie auch die Details.",
        "Primäre Zielgruppe für den Pilotversuch"
      ],
      [
        "für selbstständige Berater",
        "Verstehen Sie Kundenfeedback. Erklären Sie Ihre Ideen mit eigenen Worten.",
        "Kundengespräche · Einrichtung muss geprüft werden"
      ],
      [
        "für Import- und Exportteams",
        "Klären Sie Anforderungen mit Lieferanten und Partnern im Ausland.",
        "Untersuchtes Segment · Ablauf noch zu prüfen"
      ],
      [
        "um Ihre Ideen zu teilen",
        "Sprechen Sie in der Sprache, in der Sie sich am wohlsten fühlen.",
        "Weitere Sprachrichtungen sind geplant"
      ],
      [
        "für Lehrende & Dozenten",
        "Erkunden Sie Unterricht in Ihrer Sprache, den Lernende in ihrer hören.",
        "Erkundung · Zuhören in Gruppen ist geplant"
      ]
    ],
    "headline": [
      "Gute Ideen.",
      "Andere Sprachen.",
      "In Verbindung bleiben."
    ],
    "lede": "Gesprochene Übersetzung für Kundengespräche. Eine Person spricht Italienisch; Sie hören wenige Sekunden später Englisch. Auf Wunsch mit einer ähnlichen Stimme – nur mit Zustimmung der sprechenden Person.",
    "status": "Früher Prototyp · Heute getestet: Italienisch → Englisch",
    "open": "Prototyp öffnen",
    "cta": "Eignung prüfen · auf Englisch",
    "watch": "Film ansehen",
    "how": "So funktioniert es",
    "pricing": "Preise",
    "skip": "Zum Inhalt",
    "stepsTitle": [
      "Drei Schritte.",
      "Dem Gespräch folgen."
    ],
    "steps": [
      [
        "Die Person spricht.",
        "Der Prototyp erfasst italienische Sprache über das Mikrofon Ihres Computers."
      ],
      [
        "VocalGrid übersetzt.",
        "Sprache wird zu Text und Satz für Satz übersetzt. Die ersten englischen Worte hören Sie nach einigen Sekunden."
      ],
      [
        "Sie hören zu.",
        "Hören Sie die Übersetzung über Kopfhörer, mit neutraler Stimme oder optional mit einer ähnlichen Stimme, wenn die sprechende Person zustimmt."
      ]
    ],
    "usesTitle": [
      "Ihre Gespräche.",
      "Ihr Besprechungsraum."
    ],
    "uses": [
      [
        "Kundengespräche",
        "Geplant",
        "Einem Google-Meet-Gespräch in der eigenen Sprache folgen. Die Audioanbindung ist noch nicht verfügbar; heute verwendet der Prototyp Ihr Mikrofon."
      ],
      [
        "Im Besprechungsraum",
        "In der Piloterprobung",
        "Ein Laptop auf dem Tisch erfasst die sprechende Person. Wer Übersetzung benötigt, hört über Kopfhörer zu. Raumakustik und gleichzeitiges Sprechen müssen geprüft werden."
      ],
      [
        "Gemeinsame Sitzungen",
        "Geplant",
        "Alle wählen ihre eigene Hörsprache. Mehrsprachige Gruppensitzungen sind noch nicht verfügbar."
      ]
    ],
    "languagesTitle": "Eine Website in Ihrer Sprache. Ein Produkt in Entwicklung.",
    "languagesText": "Diese Website gibt es auf Englisch, Italienisch, Deutsch und Französisch. Die Sprache der Website ändert nicht die Produktfunktionen: Heute ist Italienisch → Englisch getestet. Weitere Sprachrichtungen müssen vor einem Angebot geprüft werden.",
    "filmTitle": [
      "Die Idee erleben.",
      "In 36 Sekunden."
    ],
    "filmNote": "Konzeptfilm auf Englisch · ohne Ton · keine Aufnahme einer Live-Übersetzung.",
    "results": "Erste Ergebnisse",
    "metrics": [
      [
        "Erste übersetzte Sprachausgabe",
        "3,2–4,6 s nach Sprachbeginn in 14 Simulationen mit Aufnahmen. Median der Verzögerung je Clip: 3,8–5,6 s; Maximum: 9,6 s. Kaltstart nicht enthalten."
      ],
      [
        "Fehlerrate der italienischen Spracherkennung",
        "3,6–4,4 % bei drei Podcast-Clips; 11,3–13,7 % bei zwei Buchpassagen. Gemessen wird die Transkription, nicht die Übersetzungsqualität."
      ]
    ],
    "method": "Interne Tests vom 27. September 2026 mit in Echtzeit abgespielten Aufnahmen auf einer L4-GPU. Keine Garantie für echte Besprechungen. Diese Werte beziehen sich auf die frühere Nemotron-Pipeline, nicht auf die aktuelle Soniox-Konfiguration.",
    "plan": "Begleiteter Pilotversuch",
    "period": " / 30 Tage",
    "planIntro": "Ein wiederkehrendes Gespräch, gemeinsam eingerichtet.",
    "features": [
      "4 übersetzte Zuhörerstunden",
      "Prüfung der Audioeinrichtung",
      "Eine geprüfte Sprachrichtung",
      "Gemeinsame Auswertung",
      "Keine automatische Verlängerung"
    ],
    "offer": "Preisvorschlag in USD, verfügbar nach Prüfung Ihrer Einrichtung. Auf dieser Website wird nichts bezahlt. Eine Stunde für eine zuhörende Person entspricht einer Zuhörerstunde.",
    "support": "Die Eignungsprüfung und die herunterladbare Zusammenfassung sind derzeit auf Englisch. Das Formular versendet keine Anfrage und bucht keinen Termin.",
    "faq": "Vor dem Start",
    "questions": [
      [
        "Wo wird Audio verarbeitet?",
        "In der Cloud, nicht auf Ihrem Gerät. Klären Sie Verarbeitungsort und Speicherfristen mit uns, bevor Sie vertrauliche Gespräche verwenden."
      ],
      [
        "Eignet es sich für den Unterricht?",
        "Das ist ein möglicher Anwendungsfall, kein bereits validiertes Bildungsangebot. Gruppenfunktionen und weitere Sprachrichtungen sind geplant."
      ],
      [
        "Aktiviert die deutsche Website weitere Sprachen?",
        "Nein. Website-Sprache und unterstützte Sprachrichtungen sind unabhängig. Heute ist Italienisch → Englisch getestet."
      ]
    ],
    "pause": "Animation pausieren",
    "resume": "Animation fortsetzen",
    "back": "Nach oben",
    "illustration": "Illustration · Beispieltext",
    "source": "ITALIENISCH",
    "target": "ENGLISCH",
    "preview": "VORSCHAU",
    "voice": "Optionale Stimmanpassung · mit Zustimmung"
  },
  "fr": {
    "title": "VocalGrid — Traduction vocale pour vos échanges clients internationaux",
    "description": "Traduction vocale pour agences, consultants et clients internationaux. Prototype italien → anglais, avec une voix similaire en option et avec consentement.",
    "language": "Langue du site",
    "next": "Cas d’usage suivant",
    "audiences": [
      [
        "pour les agences & cabinets de conseil",
        "Comprenez le brief du client. Suivez aussi les détails.",
        "Public prioritaire du pilote"
      ],
      [
        "pour les consultants indépendants",
        "Suivez les retours clients. Expliquez vos idées avec vos propres mots.",
        "Échanges clients · configuration à vérifier"
      ],
      [
        "pour les équipes import-export",
        "Clarifiez les besoins avec vos fournisseurs et partenaires à l’étranger.",
        "Segment étudié · usage à valider"
      ],
      [
        "pour partager vos idées",
        "Parlez dans la langue dans laquelle vous êtes le plus à l’aise.",
        "D’autres combinaisons linguistiques sont prévues"
      ],
      [
        "pour les enseignants & formateurs",
        "Explorez un cours dans votre langue, écouté dans celle des apprenants.",
        "Usage exploratoire · écoute en groupe prévue"
      ]
    ],
    "headline": [
      "De bonnes idées.",
      "Plusieurs langues.",
      "Toujours en lien."
    ],
    "lede": "La traduction vocale pour vos échanges professionnels. Une personne parle italien ; vous entendez l’anglais quelques secondes plus tard. Avec une voix qui peut ressembler à la sienne, uniquement avec son accord.",
    "status": "Prototype en accès anticipé · Testé aujourd’hui : italien → anglais",
    "open": "Ouvrir le prototype",
    "cta": "Vérifier mon usage · en anglais",
    "watch": "Voir le film",
    "how": "Comment ça marche",
    "pricing": "Tarifs",
    "skip": "Aller au contenu",
    "stepsTitle": [
      "Trois étapes.",
      "Pour suivre la conversation."
    ],
    "steps": [
      [
        "La personne parle.",
        "Le prototype capte la parole en italien avec le microphone de votre ordinateur."
      ],
      [
        "VocalGrid traduit.",
        "La parole devient du texte, traduit phrase par phrase. Les premiers mots en anglais arrivent après quelques secondes."
      ],
      [
        "Vous écoutez.",
        "Écoutez la traduction au casque, avec une voix neutre ou, en option, une voix similaire à celle de la personne qui parle, avec son accord."
      ]
    ],
    "usesTitle": [
      "Vos appels.",
      "Votre salle de réunion."
    ],
    "uses": [
      [
        "Appels clients",
        "Prévu",
        "Suivre un appel Google Meet dans sa langue. La connexion audio n’est pas encore disponible : le prototype utilise actuellement votre microphone."
      ],
      [
        "Dans la salle",
        "En évaluation pilote",
        "Un ordinateur sur la table capte la personne qui parle ; celle qui a besoin de traduction écoute au casque. L’acoustique et les voix qui se chevauchent restent à évaluer."
      ],
      [
        "Sessions partagées",
        "Prévu",
        "Chaque personne choisit sa langue d’écoute. Les sessions de groupe multilingues ne sont pas encore disponibles."
      ]
    ],
    "languagesTitle": "Un site dans votre langue. Un produit qui évolue.",
    "languagesText": "Ce site est disponible en anglais, italien, allemand et français. Cela ne change pas les langues du prototype : aujourd’hui, italien → anglais est testé. Les autres combinaisons doivent être validées avant d’être proposées.",
    "filmTitle": [
      "Découvrez l’idée.",
      "En 36 secondes."
    ],
    "filmNote": "Film conceptuel en anglais · sans audio · ce n’est pas un enregistrement de traduction en direct.",
    "results": "Premiers résultats",
    "metrics": [
      [
        "Premier audio traduit",
        "3,2–4,6 s après le début de la parole, dans 14 simulations sur enregistrements. Retard médian par extrait : 3,8–5,6 s ; maximum : 9,6 s. Démarrage à froid exclu."
      ],
      [
        "Taux d’erreur de reconnaissance de l’italien",
        "3,6–4,4 % sur trois extraits de podcasts ; 11,3–13,7 % sur deux passages de livres. Mesure la transcription, pas la qualité de traduction."
      ]
    ],
    "method": "Tests internes du 27 septembre 2026, avec des enregistrements rejoués en temps réel sur GPU L4. Ces résultats ne garantissent pas les performances en réunion réelle. Ces chiffres concernent l’ancienne chaîne Nemotron, pas la configuration Soniox actuelle.",
    "plan": "Pilote accompagné",
    "period": " / 30 jours",
    "planIntro": "Un échange récurrent, configuré avec vous.",
    "features": [
      "4 heures d’écoute traduite",
      "Vérification de la configuration audio",
      "Une combinaison linguistique validée",
      "Bilan des résultats",
      "Aucun renouvellement automatique"
    ],
    "offer": "Tarif proposé en USD, disponible après validation de votre configuration. Aucun paiement sur ce site. Une heure pour une personne qui écoute correspond à une heure d’écoute.",
    "support": "Le questionnaire et le récapitulatif téléchargeable sont actuellement en anglais. Le formulaire n’envoie aucune demande et ne réserve aucun rendez-vous.",
    "faq": "Avant de commencer",
    "questions": [
      [
        "Où l’audio est-il traité ?",
        "Dans le cloud, pas sur votre appareil. Avant d’utiliser des échanges confidentiels, vérifiez avec nous le lieu de traitement et la durée de conservation."
      ],
      [
        "Est-ce adapté à l’enseignement ?",
        "C’est un usage à explorer, pas encore une offre pédagogique validée. L’écoute en groupe et d’autres combinaisons linguistiques sont prévues."
      ],
      [
        "Le site en français active-t-il d’autres langues ?",
        "Non. La langue du site est indépendante des langues du prototype. Aujourd’hui, la direction italien → anglais est testée."
      ]
    ],
    "pause": "Mettre les animations en pause",
    "resume": "Reprendre les animations",
    "back": "Retour en haut",
    "illustration": "Illustration · texte d’exemple",
    "source": "ITALIEN",
    "target": "ANGLAIS",
    "preview": "APERÇU",
    "voice": "Voix similaire en option · avec consentement"
  }
}
```
<!-- /locale-copy -->

## Launch checklist — 28 September 2026
Policy drafts are local only until operator details, contact, retention, providers and sales terms are verified. Marketing has no cookies or browser storage; app storage is separate. No waitlist or contact submission exists, so CTAs say “Check planned team fit” and “Check organisation fit”. Earlier displayed figures concern the Nemotron pipeline, not the newer Soniox configuration. Voice matching approximates a voice and requires permission; no perfect-voice guarantee.
