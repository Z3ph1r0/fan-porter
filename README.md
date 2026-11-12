# Fan Porter

Fan Porter 0.7.5 è una base di progetto che ho scritto in vibe coding. Ci metti un fan game per PC (RPG Maker XP / Pokémon Essentials) e ottieni la cartella per una Switch con Atmosphere: `sdmc:/switch/<slug>/`.

L'uso è gratuito. Se lo usi, lo modifichi o lo condividi, citami. Le stesse condizioni sono in `LICENZA.txt`.

Il motore sulla console non l'ho scritto io. È [rgss-switch](https://github.com/randygil/rgss-switch) 0.2.4 di randygil, GPL-2.0+ (`LICENZA-MOTORE.txt`), sopra mkxp-z e CRuby. Non lo ricompilo. Scarico lo zip che ha pubblicato lui, poi aggiungo gli shim Ruby e un profilo per gioco.

I fan game non sono inclusi. Restano dei loro autori.

The Windows download is the release asset `Fan-Porter-0.7.5-windows.zip` on GitHub. Extract the whole zip and start `Fan D Porter.exe`. A later update replaces the program files from `fdp-aggiornamento.zip`; it leaves Python, the engine, the games and the settings in place. The build number is `versione.txt`.

## Giochi che partono

Li ho giocati sulla Switch a novembre 2026. Partono, e l'inizio si gioca:

- Nova
- Relict
- Reminiscencia
- Pokémon GS Vitro
- Pokémon Z
- Realidea System
- Pokémon Añil
- Pokémon Rejuvenation

Preparati, non li ho ricontrollati sulla mia console:

- Pokémon Opalo. L'autore del motore ci ha giocato su una Switch vera fino alla Ruta 1, a settembre 2026.
- Pokémon Xenoverse. Preparato. Su PC l'installatore dei font non copia più in Windows e non riavvia il gioco. Sulla Switch non è ancora stato giocato.

Profili arrivati col motore, non li ho controllati io: Pokémon Reborn, Iberia, Titan e Vanguard (note sull'emulatore dell'autore del motore, settembre 2026). Reborn non è Rejuvenation. Uranium parte e si ferma prima della prima mappa giocabile. Sono piste, non una promessa.

La stessa lista è nella pagina Giochi del programma.

## Per chi vuole modificarlo

Il programma è Python e tkinter. I file da leggere sono `app.py`, `ui.py`, `i18n.py`, `engine.py`, `icona.py`, `splash.py`, `runtime/` e `profili/`.

Un gioco noto è una cartella `profili/<slug>/perfil.json`:

- `detectar.titulo` è la regex sul titolo di Game.ini. Un file in comune non basta: Rejuvenation e Reborn condividono `ScriptLoader.rb` e sono due profili.
- `motor` è `ruby31` o `ruby18`.
- `mkxp` è lo schermo, i tasti e le patch scritte in `mkxp.json`.
- `shims`, `preload`, `sueltos`, `excluir` dicono cosa copiare e cosa lasciare fuori dallo zip.

Famiglia e schema tasti dei titoli verificati sono fissati anche in `INPUT_PROFILES`, dentro `engine.py`. Una DLL Ruby 3 e `RGSS102` possono stare nella stessa cartella: senza quella lista il rilevamento sbaglierebbe. Per un gioco nuovo si copia il profilo più vicino, si cambia la regex del titolo, e si aggiunge una riga lì solo se la famiglia va forzata.

`runtime/nx-porter.rb` è lo shim copiato per ultimo in `lib/`. `runtime/nx-ruby18.rb` entra solo per Ruby 1.8. I giochi Ruby 3 non lo precaricano.

`Lib/`, `python.exe` e `pythonw.exe` accanto a questi file sono il runtime con cui parte `Fan D Porter.exe`. Non sono il progetto. `LICENSE.txt` è la licenza di quel Python, non di Fan Porter. In un repository pubblico non vanno i fan game, non vanno le chiavi della console (`prod.keys`, `.switch`) e non va il motore ricompilato: si scarica la release 0.2.4 di randygil. Il file `.gitignore` tiene fuori quel runtime.

L'uso del mio codice è gratuito. Chi lo usa, lo modifica o lo condivide mi cita come creatore (`LICENZA.txt`). Il motore resta GPL-2.0+ e va citato con randygil.
