# Giochi

Sono Zephiro. Qui tengo tre fasce, e non le mescolo.

## Partono sulla mia Switch

Li ho giocati a novembre 2026. Partono, e l'inizio si gioca. Il profilo fa uscire allo stesso modo una cartella vergine del PC. Il ritmo è 40 fps: sono giochi leggeri e a 60 vanno troppo forte.

- Nova
- Relict
- Reminiscencia
- Pokémon GS Vitro
- Pokémon Z
- Realidea System
- Pokémon Añil
- Pokémon Rejuvenation è l'eccezione di questa fascia: parte, ma è pesante. Il profilo lascia il ritmo libero, senza il tetto a 40.

Su Pokémon Z, Alt è ancora il turbo del gioco dentro `Input.update`. Quel caso non è chiuso.

## Preparati, non li ho ricontrollati sulla mia console

- Pokémon Opalo. L'autore del motore ci ha giocato su una Switch vera fino alla Ruta 1, a settembre 2026. Ritmo 40.
- Pokémon Xenoverse. Preparato. Su PC l'installatore dei font non copia più in Windows e non riavvia il gioco. Sulla Switch non l'ho ancora giocato. È pesante: ritmo libero.

## Profili del motore, non li ho controllati io

Pokémon Reborn, Iberia, Titan e Vanguard arrivano dalle note sull'emulatore dell'autore del motore, settembre 2026. Reborn non è Rejuvenation. Uranium parte e si ferma prima della prima mappa giocabile. Sono piste, non una promessa.

Reborn e Uranium sono pesanti: ritmo libero. Iberia, Titan e Vanguard restano a 40 finché non so come girano.

## Aggiungere un gioco

Copio `profili/esempio/` in `profili/<slug>/` e cambio `perfil.json`:

- `slug` è il nome della cartella sulla SD.
- `detectar.titulo` è la regex sul titolo di Game.ini. Un file in comune non basta: Rejuvenation e Reborn condividono `ScriptLoader.rb` e sono due profili. Reborn ha `^Pokemon Reborn$`.
- `motor` è `ruby31` o `ruby18`.
- `ritmo` è `40` per un gioco leggero, `libero` per uno che già sta intorno ai 30 fps. `libero` non lo rallenta. In gioco il menu può ancora passare a 40, 45 o 30.
- `mkxp` è lo schermo. `shims`, `preload`, `sueltos`, `excluir` dicono cosa copiare e cosa lasciare fuori dallo zip.

Se nella stessa cartella ci sono una DLL Ruby 3 e `RGSS102`, la stima della famiglia sbaglierebbe. Allora aggiungo una riga in `INPUT_PROFILES`, dentro `engine.py`, con `family` e `tasti`. Realidea ha la DLL Ruby 3 ma gli script sono 1.8: la riga forza `ruby18`. Reminiscencia ha anche `RGSS102` ma gli script sono Ruby 3: la riga forza `ruby31`.

Poi preparo la scheda e la provo sulla Switch. Finché non l'ho giocata io, resta nella seconda o nella terza fascia.
