# Fan Porter

Scarica lo zip della release, non il codice di questo repository. Lo zip si chiama `Fan-Porter-0.7.6-windows.zip`. Estrailo tutto e avvia `Fan D Porter.exe`. Qui accanto all'exe non c'è Python: se lo avvii da una copia del codice, il programma dice di scaricare la release.

Fan Porter 0.7.6 è una base di progetto che ho scritto in vibe coding. Ci metti un fan game per PC (RPG Maker XP / Pokémon Essentials) e ottieni la cartella per una Switch con Atmosphere: `sdmc:/switch/<slug>/`.

L'uso è gratuito. Se lo usi, lo modifichi o lo condividi, citami. Le stesse condizioni sono in `LICENZA.txt`.

Il motore sulla console non l'ho scritto io. È [rgss-switch](https://github.com/randygil/rgss-switch) 0.2.4 di randygil, GPL-2.0+ (`LICENZA-MOTORE.txt`), sopra mkxp-z e CRuby. Non lo ricompilo. Scarico lo zip che ha pubblicato lui, poi aggiungo gli shim Ruby e un profilo per gioco.

I fan game non sono inclusi. Restano dei loro autori.

Un aggiornamento successivo sostituisce i file del programma con `fdp-aggiornamento.zip`. Python, il motore, i giochi e le impostazioni restano dove sono. Il numero di build è `versione.txt`.

La lista dei giochi e il modo per aggiungerne uno sono in [GIOCHI.md](GIOCHI.md).

## Per chi vuole modificarlo

Il programma è Python e tkinter. I file da leggere sono `app.py`, `ui.py`, `i18n.py`, `engine.py`, `icona.py`, `splash.py`, `runtime/` e `profili/`.

`runtime/nx-porter.rb` è lo shim copiato per ultimo in `lib/`. `runtime/nx-ruby18.rb` entra solo per Ruby 1.8. I giochi Ruby 3 non lo precaricano.

`Lib/`, `python.exe` e `pythonw.exe` accanto a questi file sono il runtime con cui parte `Fan D Porter.exe`. Non sono il progetto. `LICENSE.txt` è la licenza di quel Python, non di Fan Porter. In un repository pubblico non vanno i fan game, non vanno le chiavi della console (`prod.keys`, `.switch`) e non va il motore ricompilato: si scarica la release 0.2.4 di randygil. Il file `.gitignore` tiene fuori quel runtime.

L'uso del mio codice è gratuito. Chi lo usa, lo modifica o lo condivide mi cita come creatore (`LICENZA.txt`). Il motore resta GPL-2.0+ e va citato con randygil.
