# Fan Porter 0.7.5 — contesto per Claude (solo i due .rb)

Autore: Zephiro. Prodotto: **Fan Porter**. Motore di gioco: **rgss-switch 0.2.4 originale** (randygil, mkxp-z 2.4.2 + CRuby 3.1.7, GPL-2.0+). I due file stanno in `SD:/switch/<slug>/lib/` accanto a `data.zip`, `<slug>.nro`, `porter.cfg`.

Stasera si sostituiscono **solo** questi Ruby. Non si ricompila il motore C++. Non esiste più il lavoro “Fan R Porter”. Non copiare fix in un altro albero motore.

## Cosa caricare

1. `nx-porter.rb` — menu overlay, tasti, tema, volume, `porter.cfg`.
2. `nx-ruby18.rb` — Ruby 1.8 / Win32API per i fan game Essentials sul CRuby 3.1.7 del 0.2.4.

Opzionale sulla SD, non in questo contesto: `fan-porter-mark.png` (marchio `:D` nel header del menu). Se manca, il menu scrive comunque `FAN PORTER`.

## Architettura da non rompere

### FanPorterGuard

`Pokemon Essentials` e i plugin fanno `alias` di `Input.trigger?`, `Graphics.update`, ecc. Un `prepend` senza guardia fa ricorsione (`stack level too deep`, schermo nero).

`FanPorterGuard` cattura il metodo nativo del motore e, se si rientra nello stesso metodo, chiama quello nativo. **Non avvolgere `super` in `rescue NoMethodError`. Non cambiare l’architettura di FanPorterGuard.**

Moduli prepend: `FanPorterExtra`, `FanPorterKeys`, `FanPorterPad`, `FanPorterPause`, `FanPorterAudio`.

### Due motori, un solo prodotto

`native_keys?` è vero solo se esiste `Input::FanPorter.assegna` (motore ricompilato, **non** in uso).

Su 0.2.4 originale `native_keys?` è falso: i tasti PC si simulano in Ruby (`extra_down?` / VK). `native_overlay?` è vero solo con `Graphics.fanporter_overlay=`. Su 0.2.4 il menu si disegna coprendo lo schermo in Ruby (bitmap fullscreen). **Non chiamare `Graphics.frame_rate=` dal prodotto.** Non usare brightness/screenshot come feature.

## Tasti (verificati in console)

Etichette fisiche Switch → codice RGSS nel motore (`PHYSICAL`):

```
A → :C
B → :B
X → :A
Y → :X
ZL → :Y
ZR → :Z
L → :L
R → :R
```

`PAD_NAMES` SDL → motore: non inventare nomi. Un tasto, un’azione. F1–F12 sono tasti normali; F5 non è speciale.

Default bind PC: A=C, B=X, X=Z. ZL resta Alt, ZR resta F7. Turbo default `+` (preme Alt, turbo di Pokémon Z).

### + e −

- `+` è START, indice **6**. `plus_pressed?` deve usare `raw_kind(6, :START, :trigger?)`. BACK (4) è il `−`.
- `handle_plus` salva `porter.cfg`. Dopo il salvataggio, uscita dal menu **senza** ririchiedere A/B (`same_as_saved?` / `remember_edit`).

### Apertura menu

- Default: **L3+R3** (`menu_apri=stick`).
- Sempre disponibile: **L+R+ZL** (`shoulders?` = L && R && Y, perché ZL è `:Y`).
- Si può spostare su un tasto qualsiasi della console (`PHYSICAL`, L3/R3, d-pad, +/−).
- Migrazione: se `menu_modo` non è `1` e il valore è vuoto/`meno`/`piu` → `stick`.

### Croce (d-pad)

Default: la croce **muove**. Voce “Croce come tasti”: diventa quattro tasti bindabili; lo stick sinistro muove ancora. `croce_blocks?` / `filter_dir` filtrano solo il movimento, non il resto.

## Menu overlay

Si apre al primo avvio, poi con la combo. Mentre è aperto la tastiera simulata è sospesa, così il gioco non prende A/B del menu.

Pagine: opzioni, grafica, tasti, volume, lingua, tema, contatore, registro, apri-menu, reset (solo se aperto “during”), esci.

Tema: `porter.cfg` riga `tema=chiaro` o `tema=scuro`. Palette SwitchU (azzurro). Cerchi = tasti Switch, quadrati = tasti PC. Footer: A assegna, X toglie, B **indietro** (non esce). Tokenizer footer: `HINT_SPLIT`; `:gap` solo su bit che sono **solo** spazi (`\A\s{2,}\z`).

Header: marchio + `FAN PORTER`, credit `0.7.5 · Zephiro`.

Indici opzioni (ordine attuale): resume, graphics, buttons, volume, language, **theme**, counter, registro, menu_open, [reset], quit. Se sposti le voci, aggiorna gli `when` del click.

## porter.cfg (non cancellarlo stasera)

Chiavi usate dal Ruby: `pc` (es. `C:C,B:X,A:Z`), `turbo`, `contatore`, `registro`, `menu_apri`, `croce`, `tema`, `lingua`, `titolo`, volume, grafica. Title id e salvataggi **non** stanno qui. I salvataggi restano in `SD:/switch/<slug>/`.

## nx-ruby18.rb

Serve ai giochi Ruby 1.8 (Pokémon Z, Ópalo, Iberia, Titan, Uranium, …) sul CRuby 3.1.7:

1. `NXFuente.transforma` — sintassi 1.8 guidata dal compilatore, non gsub cieco.
2. Classe `Win32API` posticcia (senza di essa NameError in caricamento script, schermo nero).
3. Metodi 1.8 solo quelli contati nei corpus.

Si carica dopo `nx-compat.rb`. Se `transforma` lancia, il motore valuta l’originale.

## Come lavorare su un bug stasera

1. Leggere il sintomo (menu non apre, + non salva, schermo nero, tasti sbagliati).
2. Toccare **solo** i due `.rb` (e al massimo il png del marchio).
3. Non toccare `data.zip`, `.nro`, salvataggi, `porter.cfg` se il bug non è una chiave cfg.
4. Non inventare API mkxp (`Input::FanPorter`, `Graphics.fanporter_overlay`) se `native_keys?` è falso: sul 0.2.4 originale **non ci sono**.
5. Dopo la modifica: Riccardo copia i `.rb` in `lib/` sulla SD e prova dalla console (homebrew, R su titolo, non Album).

## Cosa è già vero in 1.0.0 (non “rifare”)

Menu L3+R3, fallback L+R+ZL, d-pad movimento / croce come tasti, + salva senza ridomandare, UI chiaro/scuro, footer A/X/B, bind +/−, turbo su +. Packager PC ha lo stesso tema; stasera in console conta solo il Ruby.

Pokémon Z toglie `Input.update` dopo la lingua: `defined?(super)` si legge **nel metodo** (prima del blocco di `FanPorterGuard`), e se il metodo sotto manca si chiama il nativo catturato all’avvio. Essentials 21 (Nova, Relict, Reminiscence): `dir4` che torna 0 è fermo, non va riletto dai bottoni del motore.

`porter.cfg` ha `tasti=essentials` (Nova: lettere / triggerex?) o `tasti=rgss` (Z: numeri RGSS). Lo scrive l’esportazione. Senza riga, si indovina dal metodo sotto i moduli Fan Porter.
