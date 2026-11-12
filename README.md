# Fan Porter

Fan Porter 0.7.5 is a project base, written by vibe coding by Zephiro. It turns a PC fan game (RPG Maker XP / Pokémon Essentials) into a folder for a Nintendo Switch with Atmosphere: `sdmc:/switch/<slug>/`.

Use is free. Anyone who uses, modifies, or shares Fan Porter credits Zephiro as the creator. The same terms are in `LICENZA.txt`.

The console engine is not Zephiro's. It is [rgss-switch](https://github.com/randygil/rgss-switch) 0.2.4 by randygil, GPL-2.0+ (`LICENZA-MOTORE.txt`), on top of mkxp-z and CRuby. Fan Porter does not recompile that engine. It downloads the published zip, then adds its own Ruby shims and a profile per game.

The fan games are not included. They stay with their authors. Fan Porter is not made by Nintendo or The Pokémon Company. There is no warranty.

The Windows download is the release asset `Fan-Porter-0.7.5-windows.zip` on GitHub. Extract the whole zip and start `Fan D Porter.exe`. A later update replaces the program files from `fdp-aggiornamento.zip`; it leaves Python, the engine, the games and the settings in place. The build number is `versione.txt`.

## Giochi che partono

Zephiro li ha giocati sulla Switch a novembre 2026. Partono, e l'inizio si gioca:

- Nova
- Relict
- Reminiscencia
- Pokémon GS Vitro
- Pokémon Z
- Realidea System
- Pokémon Añil
- Pokémon Rejuvenation

Preparati, non ricontrollati sulla console di Zephiro:

- Pokémon Opalo. L'autore del motore ci ha giocato su una Switch vera fino alla Ruta 1, a settembre 2026.
- Pokémon Xenoverse. Preparato. Su PC l'installatore dei font non copia più in Windows e non riavvia il gioco. Sulla Switch non è ancora stato giocato.

Profili arrivati col motore, non controllati da Zephiro: Pokémon Reborn, Iberia, Titan e Vanguard (note sull'emulatore dell'autore del motore, settembre 2026). Reborn non è Rejuvenation. Uranium parte e si ferma prima della prima mappa giocabile. Sono piste, non una promessa.

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

L'uso del codice di Zephiro è gratuito. Chi lo usa, lo modifica o lo condivide cita Zephiro come creatore (`LICENZA.txt`). Il motore resta GPL-2.0+ e va citato con randygil.
