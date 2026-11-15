# Fan D Porter — opzioni per questo gioco.
# Grafica, volume e tasti (anche A, S, D di Pokémon Z).
# Si apre da solo la prima volta, poi tenendo L+R all'avvio.

# Protezione contro i giri a vuoto. Pokemon Essentials 21 (e molti plugin) ridefiniscono
# Input.trigger?, Graphics.update ecc. con un "alias" del metodo precedente. Con un modulo
# davanti (prepend) quell'alias finisce per richiamare noi, e noi richiamiamo il gioco,
# all'infinito: "stack level too deep" e schermo nero. Qui, se rientriamo mentre siamo gia'
# dentro lo stesso metodo, andiamo dritti al metodo originale del motore.
# Essentials chiama load_data(file, true) per leggere i byte grezzi dal
# contenitore. Il motore ne accetta uno solo: in Ruby è ArgumentError
# (Relict), in C è il crash subito dopo Inizia (Anil). Un plugin di Relict
# la ridefinisce dopo, con un solo argomento: il prepend resta davanti.
begin
  require "stringio"
rescue LoadError
  nil
end

module Marshal
  class << self
    # Reminiscencia mette Marshal.neverload = true e poi chiama load_data
    # con un solo argomento, anche su un PNG. Lo shim del motore ignora
    # il flag, e Marshal.load riceve i byte 89 50 dell'immagine.
    # Anil lo alza in pbRgssOpen e non lo abbassa piu': se resta vero, il
    # file dei plugin arriva come stringa e runPlugins chiama .each sul
    # dump. Vale solo per la lettura successiva.
    def neverload=(value)
      @nx_crudo = value ? true : false
    end

    def neverload
      @nx_crudo ? true : false
    end
  end
end

module FanPorterLoadData
  def load_data(file, raw = false)
    # File.binread non passa dal contenitore: la mappa è solo in data.zip
    # e il gioco conclude che non c'è un punto di partenza. File.open sì.
    crudo = raw || (Marshal.respond_to?(:neverload) && Marshal.neverload)
    # Il flag va spento anche se uno script lo ha ridefinito con @@neverload:
    # se resta acceso, Anil legge PluginScripts.rxdata come testo e .each
    # cade sul dump.
    begin
      Marshal.instance_variable_set(:@nx_crudo, false)
    rescue StandardError
      nil
    end
    begin
      Marshal.singleton_class.class_variable_set(:@@neverload, false)
    rescue StandardError
      nil
    end
    begin
      Marshal.neverload = false
    rescue StandardError
      nil
    end
    nome = file.to_s.tr("\\", "/")
    crudo = false if nome.downcase.end_with?("pluginscripts.rxdata")
    if crudo
      return File.open(file, "rb") { |handle| handle.read }
    end
    begin
      super(file)
    rescue TypeError => errore
      # 137.80 e' l'intestazione PNG (0x89 0x50) passata a Marshal.load
      # da SetMapTile, quando pbGetFileChar voleva solo il primo byte.
      raise unless errore.message.include?("137.80")
      File.open(file, "rb") { |handle| handle.read }
    end
  end
end
# `def load_data` in cima a uno script finisce su Object, davanti a Kernel.
# Il prepend va su Object, altrimenti Relict continua a vedere un solo argomento
# e Anil passa i due argomenti alla funzione in C, che si chiude.
Object.prepend(FanPorterLoadData)

# Nuovo gioco di Reminiscencia: pbRgssOpen consegna uno StringInput, che ha
# read ma non e' un IO. Marshal.load di Ruby 3.1 risponde "instance of IO
# needed" e il dialogo del professore non parte. Si tiene il metodo nativo
# e gli si passa uno StringIO. Il prepend resta davanti anche se uno script
# vecchio (SpriteWindow) ridefinisce Marshal.load dopo.
module FanPorterMarshal
  def self.adatta(port)
    if port.is_a?(IO)
      rotto = port.instance_variable_defined?(:@string) &&
              (!port.respond_to?(:getbyte) || port.method(:getbyte).owner == IO)
      return port unless rotto
    elsif !port.is_a?(String) && !port.respond_to?(:read)
      return port
    end
    dati = port.is_a?(String) ? port : nil
    if dati.nil? && port.instance_variable_defined?(:@string)
      dati = port.instance_variable_get(:@string)
    end
    dati = port.read if dati.nil? && port.respond_to?(:read)
    StringIO.new(dati.to_s)
  end

  def load(port, *args)
    if Marshal.respond_to?(:neverload) && Marshal.neverload
      return port.read if port.respond_to?(:read)
      return port
    end
    FanPorterMarshal.nativo.call(FanPorterMarshal.adatta(port), *args)
  end
end
FanPorterMarshal.singleton_class.class_eval { attr_accessor :nativo }
FanPorterMarshal.nativo = Marshal.method(:load)
Marshal.singleton_class.prepend(FanPorterMarshal)

# StringInput#each fa @string.each, tolto in Ruby 1.9. each_byte e getbyte
# servono a fgetb (i .dat dei Pokemon): la classe nasce negli script, dopo
# questo file.
unless String.method_defined?(:each)
  class String
    def each(*args, &blocco)
      each_line(*args, &blocco)
    end
  end
end

TracePoint.trace(:end) do |evento|
  classe = evento.self
  next unless classe.is_a?(Class) && classe.name == "StringInput"
  next if classe.method_defined?(:nx_porter_getbyte)
  classe.class_eval do
    if !method_defined?(:getbyte) || instance_method(:getbyte).owner == IO
      def getbyte
        carattere = getc
        return nil if carattere.nil?
        carattere.is_a?(String) ? carattere.getbyte(0) : carattere
      end
    end
    alias_method :nx_porter_getbyte, :getbyte
    if method_defined?(:each_byte) && !method_defined?(:nx_each_byte_porter)
      alias_method :nx_each_byte_porter, :each_byte
      def each_byte
        nx_each_byte_porter do |carattere|
          yield carattere.is_a?(String) ? carattere.getbyte(0) : carattere
        end
      end
    end
  end
end

# Le estensioni .so di Linux non sono linkate in questo interprete. Un
# require li fa chiudere il processo dentro il caricatore nativo.
module FanPorterRequire
  def require(percorso)
    testo = percorso.to_s
    if testo == "discord" || testo.end_with?("discord.so")
      FanPorterRequire.discord_finto
      return true
    end
    if testo.end_with?(".so") || testo.include?(".so.")
      return false
    end
    super
  rescue NotImplementedError
    false
  end

  # discord.so non è linkabile. Il require parte da DiscordRichPresence.rb
  # e NotImplementedError non è uno StandardError: esce dal rescue del gioco
  # e chiude l'avvio. Il modulo finto basta alle chiamate che lo script fa.
  def self.discord_finto
    return if defined?(::Discord)
    modulo = Module.new do
      def self.update; end
      def self.connected?; false; end
      def self.connect(*); end
      def self.disconnect; end
      def self.update_activity(*); end
    end
    Object.const_set(:Discord, modulo)
  end
end
Kernel.prepend(FanPorterRequire)

# Reminiscencia costruisce Win32API.new(dll, funzione, importa, esporta)
# dentro la classe, prima di definire initialize. Senza una firma da quattro
# argomenti il motore risponde "expected 0" e chiude l'avvio.
class Win32API
  def initialize(*); end
  def call(*); 0; end
  def Call(*); 0; end
end

# Sulla Switch System.data_directory passa da un percorso che il motore
# normalizza in C. Anil e Rejuvenation muoiono lì, far=0x10, senza errore Ruby.
# I salvataggi restano nella cartella del gioco.
if defined?(System)
  module System
    class << self
      def data_directory
        "."
      end
    end
  end
end

# Su questa Switch Thread.new chiude il processo (far=0x10, +0x125cc4).
# Rejuvenation lo fa all'avvio in Scripts/Updater.rb per controllare la
# versione in rete. Il controllo non serve in console: il blocco non parte.
class FanPorterThread
  def alive?; false; end
  def stop?; true; end
  def join(*); nil; end
  def kill; nil; end
  def exit; nil; end
  def terminate; nil; end
  def wakeup; self; end
  def run; self; end
  def value; nil; end
  def status; nil; end
  def [](_chiave); nil; end
  def []=(_chiave, valore); valore; end
  def report_on_exception; false; end
  def report_on_exception=(_valore); end
end

class << Thread
  def new(*)
    FanPorterThread.new
  end

  def start(*)
    FanPorterThread.new
  end

  def fork(*)
    FanPorterThread.new
  end
end

# PokemonSystem#update_vsync di Anil riscrive mkxp.json togliendo la virgola
# dopo syncToRefreshrate, oppure mettendone due, e commenta fixedFramerate
# con //. Il parser del motore rifiuta il file e l'avvio muore prima di Ruby.
module FanPorterMkxpFile
  def open(name, *args)
    mode = args[0].is_a?(String) ? args[0] : "r"
    path = name.to_s.tr("\\", "/")
    writing = path.end_with?("mkxp.json") && mode.include?("w")
    result = block_given? ? super(name, *args) { |file| yield file } : super(name, *args)
    FanPorterMkxpFile.repair(path) if writing
    result
  end

  def self.repair(path)
    return if @repairing
    @repairing = true
    text = File.read(path)
    lines = text.each_line.map { |line| line.sub(/\A(\s*)\/\/\s*/, "\\1") }
    body = lines.join
    body = body.gsub(/,(\s*,)+/, ",")
    body = body.gsub(/(true|false|-?\d+)(\s*\n\s*")/, "\\1,\\2")
    body = body.gsub(/,(\s*[}\]])/, "\\1")
    File.open(path, "w") { |file| file.write(body) } if body != text
  ensure
    @repairing = false
  end
end

class << File
  prepend FanPorterMkxpFile
end

# Il controllo versione di Rejuvenation resta appeso sulla rete.
TracePoint.trace(:end) do |evento|
  next unless evento.self.is_a?(Module) && evento.self.name == "Updater"
  def Updater.initializeAvailableVersion(*)
    nil
  end
end

module FanPorterGuard
  @native = {}
  @busy = {}

  def self.capture(target, *names)
    names.each do |name|
      key = [target.object_id, name]
      next if @native[key]
      begin
        @native[key] = target.method(name)
      rescue NameError
        nil
      end
    end
  end

  def self.native(target, name, args)
    method = @native[[target.object_id, name]]
    return false unless method
    method.call(*args)
  end

  def self.run(mod, target, name, args)
    key = [mod, name]
    if @busy[key]
      return native(target, name, args)
    end
    @busy[key] = true
    begin
      yield
    ensure
      @busy[key] = false
    end
  end
end

# Un tasto del pad può anche premere un tasto da tastiera (F1, una lettera, Esc).
# Sta davanti a FanPorterKeys: i codici RGSS normali passano oltre.
module FanPorterExtra
  def press?(key)
    FanPorterGuard.run(FanPorterExtra, Input, :press?, [key]) do
      FanPorter.note_query(:press?, key)
      next false if FanPorter.croce_blocks?(key)
      next true if FanPorter.virtual_const?(:press?, key)
      next true if FanPorter.extra_down?(key)
      next true if FanPorter.bound_role?(:press?, key)
      case FanPorter.filter_native(:press?, key)
      when :yes then next true
      when :no then next false
      end
      super(key)
    end
  end

  def trigger?(key)
    FanPorterGuard.run(FanPorterExtra, Input, :trigger?, [key]) do
      FanPorter.note_query(:trigger?, key)
      next false if FanPorter.croce_blocks?(key)
      next true if FanPorter.virtual_const?(:trigger?, key)
      next true if FanPorter.extra_edge?(key)
      next true if FanPorter.bound_role?(:trigger?, key)
      case FanPorter.filter_native(:trigger?, key)
      when :yes then next true
      when :no then next false
      end
      super(key)
    end
  end

  def repeat?(key)
    FanPorterGuard.run(FanPorterExtra, Input, :repeat?, [key]) do
      FanPorter.note_query(:repeat?, key)
      next false if FanPorter.croce_blocks?(key)
      next true if FanPorter.virtual_const?(:repeat?, key)
      next true if FanPorter.extra_repeat?(key)
      next true if FanPorter.bound_role?(:repeat?, key)
      case FanPorter.filter_native(:repeat?, key)
      when :yes then next true
      when :no then next false
      end
      super(key)
    end
  end

  def update
    FanPorterGuard.run(FanPorterExtra, Input, :update, []) do
      FanPorter.engine_input(:update)
      FanPorter.after_input
    end
  end

  def pressex?(key)
    FanPorterGuard.run(FanPorterExtra, Input, :pressex?, [key]) do
      FanPorter.note_query(:pressex?, key)
      next true if FanPorter.virtual_key?(:press?, key)
      next true if key.is_a?(Integer) && FanPorter.vk_held?(key)
      begin
        super(key)
      rescue NoMethodError
        false
      end
    end
  end

  def triggerex?(key)
    FanPorterGuard.run(FanPorterExtra, Input, :triggerex?, [key]) do
      FanPorter.note_query(:triggerex?, key)
      next true if FanPorter.virtual_key?(:trigger?, key)
      next true if key.is_a?(Integer) && FanPorter.vk_edge?(key)
      begin
        super(key)
      rescue NoMethodError
        false
      end
    end
  end

  def repeatex?(key)
    FanPorterGuard.run(FanPorterExtra, Input, :repeatex?, [key]) do
      FanPorter.note_query(:repeatex?, key)
      next true if FanPorter.virtual_key?(:repeat?, key)
      next true if key.is_a?(Integer) && FanPorter.vk_repeat?(key)
      begin
        super(key)
      rescue NoMethodError
        false
      end
    end
  end

  def releaseex?(key)
    FanPorterGuard.run(FanPorterExtra, Input, :releaseex?, [key]) do
      FanPorter.note_query(:releaseex?, key)
      next true if FanPorter.virtual_key?(:release?, key)
      next true if key.is_a?(Integer) && FanPorter.vk_release?(key)
      begin
        super(key)
      rescue NoMethodError
        false
      end
    end
  end

  def dir4(*args)
    FanPorterGuard.run(FanPorterExtra, Input, :dir4, args) do
      value = FanPorter.engine_input(:dir4, *args)
      FanPorter.filter_dir(value || 0)
    end
  end

  def dir8(*args)
    FanPorterGuard.run(FanPorterExtra, Input, :dir8, args) do
      value = FanPorter.engine_input(:dir8, *args)
      FanPorter.filter_dir(value || 0)
    end
  end
end

# Il pad della Switch non viene riproposto come controller: alcuni giochi lo leggono
# e altri no. I bottoni arrivano solo come tasti di tastiera.
module FanPorterPad
  [:pressex?, :triggerex?, :repeatex?, :releaseex?].each do |name|
    define_method(name) do |key|
      FanPorterGuard.run(FanPorterPad, self, name, [key]) do
        FanPorter.note_query(:"pad_#{name}", key)
        kind = { pressex?: :press?, triggerex?: :trigger?, repeatex?: :repeat?, releaseex?: :release? }[name]
        next false if FanPorter.controller_hidden?(key)
        next true if FanPorter.virtual_pad?(kind, key)
        begin
          super(key)
        rescue NoMethodError
          false
        end
      end
    end
  end

  def axes_left
    FanPorterGuard.run(FanPorterPad, self, :axes_left, []) do
      orig = begin
        super()
      rescue NoMethodError
        nil
      end
      FanPorter.note_stick(orig)
      orig = [0.0, 0.0] unless orig.is_a?(Array) && orig.length >= 2
      if orig[0].to_f.abs < 0.01 && orig[1].to_f.abs < 0.01
        FanPorter.pad_axes
      else
        orig
      end
    end
  end
end

# Il test di ricorsione prepende questo modulo e poi aliasa update, come fa
# Essentials. Nel gioco vero non si prepende: si veda install_pause.
module FanPorterPause
  def update
    FanPorterGuard.run(FanPorterPause, Graphics, :update, []) do
      begin
        FanPorter.note_frame
        FanPorter.diag_tick
        FanPorter.tick_counter
      rescue Exception
        nil
      end
      super()
      begin
        FanPorter.pace
        FanPorter.maybe_menu
      rescue Exception
        nil
      end
    end
  end

  def freeze(*)
    FanPorterGuard.run(FanPorterPause, Graphics, :freeze, []) do
      FanPorter.mark_frozen
      super
    end
  end

  def transition(*args)
    FanPorterGuard.run(FanPorterPause, Graphics, :transition, args) do
      FanPorter.mark_shown
      super(*args)
    end
  end
end

module FanPorterKeys
  def press?(key)
    FanPorterGuard.run(FanPorterKeys, Input, :press?, [key]) do
      FanPorter.engine_input(:press?, FanPorter.raw_code(key))
    end
  end

  def trigger?(key)
    FanPorterGuard.run(FanPorterKeys, Input, :trigger?, [key]) do
      FanPorter.engine_input(:trigger?, FanPorter.raw_code(key))
    end
  end

  def repeat?(key)
    FanPorterGuard.run(FanPorterKeys, Input, :repeat?, [key]) do
      FanPorter.engine_input(:repeat?, FanPorter.raw_code(key))
    end
  end
end

module FanPorterAudio
  [:bgm_play, :bgs_play, :me_play, :se_play].each do |name|
    define_method(name) do |*args|
      FanPorterGuard.run(FanPorterAudio, Audio, name, args) do
        FanPorter.scale_audio(args)
        next if FanPorter.keep_playing?(name, args)
        super(*args)
      end
    end
  end

  [:bgm_stop, :bgs_stop, :bgm_fade, :bgs_fade].each do |name|
    next unless Audio.respond_to?(name)
    define_method(name) do |*args|
      FanPorterGuard.run(FanPorterAudio, Audio, name, args) do
        FanPorter.forget_audio(name)
        super(*args)
      end
    end
  end
end

module FanPorter
  ACTIONS = [
    ["accetta", "Confirm", :C],
    ["indietro", "Back", :B],
    ["corsa", "Run", :A],
    ["tasto_a", "Key A", :X],
    ["tasto_s", "Key S", :Y],
    ["tasto_d", "Key D", :Z],
    ["elle", "L", :L],
    ["erre", "R", :R],
  ].freeze

  # Codice RGSS che il motore emette, e nome del tasto fisico.
  # Tabella di GUIA.md del motore 0.2.4: A/B = C/B, X = X, Y = A, ZL/ZR = Y/Z.
  PHYSICAL = [
    [:C, "A"],
    [:B, "B"],
    [:X, "Y"],
    [:A, "X"],
    [:Y, "ZL"],
    [:Z, "ZR"],
    [:L, "L"],
    [:R, "R"],
  ].freeze

  FILTERS = [
    ["intera", "Sharp pixels"],
    ["nitida", "Sharp, fill"],
    ["morbida", "Smooth"],
    ["lanczos", "Lanczos"],
  ].freeze

  FPS = [
    ["auto", "as_it_is"],
    ["libero", "fps_free"],
    ["45", "fps_45"],
    ["30", "fps_30"],
  ].freeze

  # Etichette del menu. I nomi dei tasti PC (F1, Enter) restano quelli salvati in porter.cfg.
  TEXT = {
    "en" => {
      "options" => "Options", "resume" => "Resume", "start" => "Start",
      "graphics" => "Graphics", "buttons" => "Buttons", "volume" => "Volume",
      "language" => "Language", "footer" => "A selects    L+R+ZL in game",
      "filter" => "Filter", "aspect" => "Aspect", "free" => "Free", "fixed" => "Fixed",
      "speed" => "Speed", "back" => "Back", "borders" => "Integer scale on handheld can leave borders",
      "sharp" => "Sharp pixels", "fill" => "Sharp, fill", "smooth" => "Smooth", "lanczos" => "Lanczos",
      "as_it_is" => "40 fps", "fps_free" => "Uncapped", "fps_45" => "45 fps", "fps_30" => "30 fps",
      "blur" => "Motion blur",
      "blur_note" => "Mixes the previous frame. It shows once the cap is already running",
      "accetta" => "Confirm", "indietro" => "Back", "corsa" => "Run",
      "tasto_a" => "Key A", "tasto_s" => "Key S", "tasto_d" => "Key D", "elle" => "L", "erre" => "R",
      "pc_key" => "PC key", "buttons_note" => "A sets the key    Y clears    B leaves",
      "suggest_mark" => "*",
      "press" => "press a button", "new_button" => "New button", "cancel_lr" => "L+R together cancels",
      "add" => "Add", "pc_note" => "A binds   Y removes   B leaves",
      "switch_button" => "Switch button", "cancel_combo" => "L+R+ZL cancels",
      "left_right" => "left right", "confirm_cancel" => "A confirms   B cancels",
      "function" => "Function keys", "letters_am" => "Letters A–M", "letters_nz" => "Letters N–Z",
      "editing" => "Editing", "open_section" => "A opens the group    B cancels",
      "back_section" => "A chooses    B back to the groups",
      "none" => "none",
      "reset" => "Reset", "quit" => "Quit",
      "reset_ask" => "Reset the game", "quit_ask" => "Leave the game",
      "reset_note" => "Unsaved progress is lost",
      "quit_note" => "Back to the menu that opened the game",
      "live_note" => "You see this on the game right away",
      "lanczos_next" => "Lanczos shows up only after you restart the game",
      "cap_next" => "The fps cap applies the next time the game starts",
      "counter" => "Frame counter", "on" => "On", "off" => "Off",
      "registro" => "Key the game wants", "asks" => "wants",
      "menu_open" => "Open menu", "footer_rest" => "A selects",
      "croce" => "D-pad as keys",
      "croce_note" => "The D-pad becomes four keys. The left stick still moves",
      "pad_up" => "Up", "pad_down" => "Down", "pad_left" => "Left", "pad_right" => "Right",
    },
    "it" => {
      "options" => "Opzioni", "resume" => "Riprendi", "start" => "Inizia",
      "graphics" => "Grafica", "buttons" => "Tasti", "volume" => "Volume",
      "language" => "Lingua", "footer" => "A sceglie    L+R+ZL in gioco",
      "filter" => "Filtro", "aspect" => "Proporzioni", "free" => "Libere", "fixed" => "Fisse",
      "speed" => "Velocità", "back" => "Indietro", "borders" => "In portatile la scala intera può lasciare bordi",
      "sharp" => "Pixel nitidi", "fill" => "Nitidi, riempi", "smooth" => "Morbido", "lanczos" => "Lanczos",
      "as_it_is" => "40 fps", "fps_free" => "Senza tetto", "fps_45" => "45 fps", "fps_30" => "30 fps",
      "blur" => "Blur di movimento",
      "blur_note" => "Mescola il fotogramma precedente. Si vede quando il tetto è già attivo",
      "accetta" => "Conferma", "indietro" => "Indietro", "corsa" => "Corsa",
      "tasto_a" => "Tasto A", "tasto_s" => "Tasto S", "tasto_d" => "Tasto D", "elle" => "L", "erre" => "R",
      "pc_key" => "Tasto PC", "buttons_note" => "A assegna    Y toglie    B esce",
      "suggest_mark" => "*",
      "press" => "premi un tasto", "new_button" => "Nuovo tasto", "cancel_lr" => "L+R insieme annulla",
      "add" => "Aggiungi", "pc_note" => "A assegna   Y toglie   B esce",
      "switch_button" => "Tasto Switch", "cancel_combo" => "L+R+ZL annulla",
      "left_right" => "sinistra destra", "confirm_cancel" => "A conferma   B annulla",
      "function" => "Tasti funzione", "letters_am" => "Lettere A–M", "letters_nz" => "Lettere N–Z",
      "editing" => "Modifica", "open_section" => "A apre il gruppo    B annulla",
      "back_section" => "A sceglie    B torna ai gruppi",
      "none" => "nessuno",
      "reset" => "Resetta", "quit" => "Esci",
      "reset_ask" => "Resetta il gioco", "quit_ask" => "Esci dal gioco",
      "reset_note" => "Il progresso non salvato si perde",
      "quit_note" => "Torni al menu da cui hai aperto il gioco",
      "live_note" => "Si vede subito sul gioco",
      "lanczos_next" => "Lanczos si vede solo al prossimo avvio",
      "cap_next" => "Il tetto fps parte al prossimo avvio",
      "counter" => "Contatore fotogrammi", "on" => "Sì", "off" => "No",
      "registro" => "Tasto richiesto", "asks" => "chiede",
      "menu_open" => "Apri menu", "footer_rest" => "A sceglie",
      "croce" => "Croce come tasti",
      "croce_note" => "La croce diventa quattro tasti. Lo stick sinistro muove ancora",
      "pad_up" => "Su", "pad_down" => "Giù", "pad_left" => "Sinistra", "pad_right" => "Destra",
    },
  }.freeze

  module_function

  def lingua
    @cfg && @cfg["lingua"] == "it" ? "it" : "en"
  end

  def t(key)
    pack = TEXT[lingua] || TEXT["en"]
    pack[key] || TEXT["en"][key] || key
  end

  def lang_name
    lingua == "it" ? "Italiano" : "English"
  end

  def set_lingua(dir)
    @cfg["lingua"] = step(%w[en it], lingua, dir)
    save_cfg
  end

  # Nuovo gioco di Rejuvenation cerca i salvataggi di altri giochi nella
  # cartella padre. Sulla scheda quella cartella è enorme e lo schermo resta
  # nero. Il segnalino .portable la fa cercare solo in Save Data.
  def saves_portatili
    return unless File.exist?("Scripts/Rejuv/NewGamePlus.rb")
    Dir.mkdir("Save Data") unless File.exist?("Save Data")
    segno = "Save Data/.portable"
    File.open(segno, "w") { |file| file.write("") } unless File.exist?(segno)
  rescue StandardError
    nil
  end

  def boot
    saves_portatili
    load_cfg
    load_pc
    build_map
    grab_raw_input
    alias_engine_input
    FanPorterGuard.capture(Input, :update, :press?, :trigger?, :repeat?, :pressex?, :triggerex?, :repeatex?, :releaseex?, :dir4, :dir8)
    FanPorterGuard.capture(Audio, :bgm_play, :bgs_play, :me_play, :se_play, :bgm_stop, :bgs_stop, :bgm_fade, :bgs_fade)
    class << Input
      prepend FanPorterKeys
      prepend FanPorterExtra
    end
    class << Audio
      prepend FanPorterAudio
    end
    install_pad
    install_win32_keys
    install_async_keys
    install_pause
    begin
      if want_menu?
        open_menu(false)
        @cfg["menu"] = "0"
        save_cfg
      end
    ensure
      @ready = true
    end
    patch_mkxp
  end

  def open_menu(during)
    return if @in_menu
    @in_menu = true
    @during = during
    @passthrough = true
    @combo_lock = true
    begin
      run_menu
    ensure
      if @saved_brightness && Graphics.respond_to?(:brightness=)
        begin
          Graphics.brightness = @saved_brightness
        rescue Exception
          nil
        end
      end
      @saved_brightness = nil
      @passthrough = false
      @in_menu = false
      @during = false
      dispose_screen
    end
    patch_mkxp
    save_cfg
  end

  def note_frame
    @porter_frame = (@porter_frame || 0) + 1
    @input_gen = (@input_gen || 0) + 1
  end

  # Input.update arriva dopo Graphics.update. Se nel frattempo un bottone
  # è cambiato, il gioco lo vede in questo fotogramma, non in quello dopo.
  def after_input
    refresh_keys
    # Z controlla Alt dentro il SUO Input.update. Quel metodo non gira più:
    # il porter tiene update per leggere il pad. Il turbo è pbTurbo.
    return unless defined?(pbTurbo)
    alt = Input.const_defined?(:ALT) ? Input::ALT : 23
    return unless bound_role?(:trigger?, alt)
    pbTurbo()
  rescue StandardError
    nil
  end

  # Diagnostica accesa se manca la riga, spenta con diagnostica=0 in porter.cfg.
  def diag_on?
    @cfg.nil? || @cfg["diagnostica"] != "0"
  end

  # Diagnostica: scrive poche righe "[porter]" in mkxp-ruby.log per capire se il gioco gira
  # (frame), se il motore vede i tasti e se il gioco li riceve. Si ferma dopo 200 righe.
  DIAG_BUTTONS = [
    [:C, "A"], [:B, "B"], [:X, "X"], [:A, "Y"], [:Y, "ZL"], [:Z, "ZR"],
    [:L, "L"], [:R, "R"], [:UP, "su"], [:DOWN, "giu"], [:LEFT, "sinistra"], [:RIGHT, "destra"],
  ].freeze

  # Registra (una volta sola per coppia) quali tasti chiede il gioco e da quale script. Serve a
  # capire cosa aspetta una schermata ferma. Al massimo 250 righe.
  def note_query(name, key)
    remember_asked(key)
    return unless diag_on?
    @seen ||= {}
    table = (@seen[name] ||= {})
    return if table[key]
    table[key] = true
    @seen_n = (@seen_n || 0) + 1
    return if @seen_n > 250
    where = caller.reject { |line| line.include?("nx-porter") || line.include?("004_Input") }
    where = where.first(3).map { |line| line[0, 70] }.join(" < ")
    puts "[porter] chiede #{name}(#{key.inspect}) da #{where}"
  rescue Exception
    nil
  end

  def diag_tick
    return unless diag_on?
    @diag_lines ||= 0
    return if @diag_lines >= 200
    frame = @porter_frame || 0
    if frame == 1 || frame % 600 == 0
      puts "[porter] frame #{frame} (il gioco sta girando)"
      @diag_lines += 1
    end
    return unless @raw_trigger
    DIAG_BUTTONS.each do |name, label|
      raw = code(name)
      next unless @raw_trigger.call(raw)
      @diag_count ||= Hash.new(0)
      @diag_count[label] += 1
      next if @diag_count[label] > 5
      puts "[porter] tasto #{label}: motore=si"
      @diag_lines += 1
    end
  rescue Exception => e
    @diag_lines = 200
    puts "[porter] diagnostica interrotta: #{e.class} #{e.message}"
  end

  def mark_frozen
    @screen_frozen = true
  end

  def mark_shown
    @screen_frozen = false
  end

  def maybe_menu
    return unless @ready
    return if @in_menu
    held = combo?
    if @combo_lock
      @combo_lock = false unless held
      return
    end
    return unless held
    open_menu(true)
  end

  # Il − della Switch è SDL BACK (indice 4), il + è START (indice 6).
  # Il motore non li consegna al gioco: restano liberi per il menu.
  # L+R+ZL resta un secondo ingresso, così se un pad non riporta il − non si resta fuori.
  def combo?
    chosen = case menu_open
             when "piu" then pad_raw?(6, :START)
             when "spalle" then shoulders?
             else pad_raw?(4, :BACK)
             end
    chosen || shoulders?
  end

  def shoulders?
    down?(:L) && down?(:R) && down?(:Y)
  end

  def menu_open
    raw = (@cfg && @cfg["menu_apri"]).to_s
    return raw if raw == "meno" || raw == "spalle"
    "meno"
  end

  def cycle_menu_open(dir)
    choices = %w[meno spalle]
    index = choices.index(menu_open) || 0
    @cfg["menu_apri"] = choices[(index + dir) % choices.length]
    save_cfg
  end

  def menu_open_label
    return "L+R+ZL" if menu_open == "spalle"
    "−"
  end

  def pad_raw?(index, symbol)
    mod = if defined?(Input::Controller)
            Input::Controller
          elsif defined?(::Controller)
            ::Controller
          end
    if mod && mod.respond_to?(:nx_engine_pressex)
      begin
        return true if mod.nx_engine_pressex(symbol)
      rescue Exception
        nil
      end
    elsif @native_pad
      begin
        return true if @native_pad.call(symbol)
      rescue Exception
        nil
      end
    end
    if @native_states
      begin
        states = @native_states.call
        return true if states && states[index]
      rescue Exception
        nil
      end
    end
    false
  end

  def remember_asked(key)
    return if plain_button?(key)
    @asked = asked_name(key)
  rescue Exception
    nil
  end

  def plain_button?(key)
    number = key if key.is_a?(Integer)
    return true if number && ((number >= 11 && number <= 18) || [2, 4, 6, 8].include?(number))
    return true if key.is_a?(Symbol) && %i[C B A X Y Z L R UP DOWN LEFT RIGHT].include?(key)
    false
  end

  def asked_name(key)
    return "Alt" if key == 23 || key == 0x12 || key == :ALT || key == :LALT || key == :RALT
    return "F7" if key == 27 || key == :F7
    return "Esc" if key == 0x1B || key == :ESCAPE
    return "Invio" if key == 0x0D || key == :RETURN || key == :KP_ENTER
    return "Spazio" if key == 0x20 || key == :SPACE
    return "Maiusc" if key == 0x10 || key == :LSHIFT || key == :RSHIFT
    return key.to_s if key.is_a?(Symbol)
    return "F#{key - 0x6F}" if key.is_a?(Integer) && key >= 0x70 && key <= 0x7B
    return key.chr if key.is_a?(Integer) && key >= 65 && key <= 90
    key.to_s
  end

  # Essentials (Z, sezione Transitions) fa alias di Graphics.update e di
  # Graphics.transition DOPO questo file, poi ci mette sopra il suo metodo:
  # la transizione vuota è un rettangolo nero a z=99999 che si cancella solo
  # nel while del SUO transition. Un prepend davanti farebbe chiamare noi
  # al posto di quel while: il rettangolo resta, la mappa Intro (tono nero,
  # le figure stanno sopra) non si vede, e il menu di − finisce sotto.
  # L'alias qui sotto resta il metodo PRECEDENTE. Il gioco lo richiama e
  # poi fa il suo while.
  def install_pause
    return if @pause_on
    return unless defined?(Graphics) && Graphics.respond_to?(:update)
    @pause_on = true
    FanPorterGuard.capture(Graphics, :update, :freeze, :transition)
    singleton = class << Graphics; self; end
    singleton.class_eval do
      alias_method :nx_porter_gfx_update, :update
      def update
        FanPorterGuard.run(FanPorterPause, Graphics, :update, []) do
          begin
            FanPorter.note_frame
            FanPorter.diag_tick
            FanPorter.tick_counter
          rescue Exception
            nil
          end
          nx_porter_gfx_update
          begin
            FanPorter.pace
            FanPorter.tick_blur
            FanPorter.maybe_menu
          rescue Exception
            nil
          end
        end
      end
      if method_defined?(:freeze) || private_method_defined?(:freeze)
        alias_method :nx_porter_gfx_freeze, :freeze
        def freeze(*)
          FanPorterGuard.run(FanPorterPause, Graphics, :freeze, []) do
            FanPorter.mark_frozen
            nx_porter_gfx_freeze
          end
        end
      end
      if method_defined?(:transition) || private_method_defined?(:transition)
        alias_method :nx_porter_gfx_transition, :transition
        def transition(*args)
          FanPorterGuard.run(FanPorterPause, Graphics, :transition, args) do
            FanPorter.mark_shown
            nx_porter_gfx_transition(*args)
          end
        end
      end
    end
  end

  def raw_code(key)
    return key if @passthrough
    @map[key] || key
  end

  # Una porta richiama bgm_play con lo stesso file e la posizione a zero.
  # Il motore riparte da capo. Se il brano è già in corso, lo lascio dov'è.
  # Una posizione maggiore di zero è una ripresa voluta: quella passa.
  def keep_playing?(name, args)
    return false unless name == :bgm_play || name == :bgs_play
    file = args[0].to_s
    return false if file.empty?
    pos = args.length >= 4 ? args[3].to_f : 0.0
    return false if pos > 0.05
    vol = args.length >= 2 ? args[1] : 100
    pitch = args.length >= 3 ? args[2] : 100
    sig = [file, vol, pitch]
    key = name == :bgm_play ? :@bgm_sig : :@bgs_sig
    pos_name = name == :bgm_play ? :bgm_pos : :bgs_pos
    if instance_variable_get(key) == sig && Audio.respond_to?(pos_name)
      begin
        return true if Audio.send(pos_name).to_f > 0.25
      rescue Exception
        return false
      end
    end
    instance_variable_set(key, sig)
    false
  end

  def forget_audio(name)
    if name == :bgm_stop || name == :bgm_fade
      @bgm_sig = nil
    elsif name == :bgs_stop || name == :bgs_fade
      @bgs_sig = nil
    end
  end

  def scale_audio(args)
    return unless args.length >= 2 && args[1].is_a?(Numeric)
    scaled = (args[1].to_f * volume / 100.0).round
    scaled = 0 if scaled < 0
    scaled = 100 if scaled > 100
    args[1] = scaled
  end

  def volume
    (@cfg["volume"] || "100").to_i
  end

  def code(name)
    Input.const_get(name)
  end

  # Il gioco poi definisce di nuovo press?/trigger?/update sul modulo e
  # nx-ruby18 li toglie. L'alias resta: è il metodo del motore, preso prima.
  def alias_engine_input
    eigen = class << Input; self; end
    {
      update: :nx_engine_update,
      press?: :nx_engine_press?,
      trigger?: :nx_engine_trigger?,
      repeat?: :nx_engine_repeat?,
      release?: :nx_engine_release?,
      dir4: :nx_engine_dir4,
      dir8: :nx_engine_dir8,
    }.each do |name, alias_name|
      next unless eigen.method_defined?(name) || eigen.private_method_defined?(name)
      next if eigen.method_defined?(alias_name) || eigen.private_method_defined?(alias_name)
      eigen.send(:alias_method, alias_name, name)
    end
  end

  def engine_input(name, *args)
    alias_name = {
      update: :nx_engine_update,
      press?: :nx_engine_press?,
      trigger?: :nx_engine_trigger?,
      repeat?: :nx_engine_repeat?,
      release?: :nx_engine_release?,
      dir4: :nx_engine_dir4,
      dir8: :nx_engine_dir8,
    }[name]
    if alias_name && Input.respond_to?(alias_name)
      return Input.public_send(alias_name, *args)
    end
    FanPorterGuard.native(Input, name, args)
  end

  def grab_raw_input
    @raw_press = Input.method(:press?)
    @raw_trigger = Input.method(:trigger?)
    @raw_repeat = Input.method(:repeat?)
    @raw_release = begin
      Input.method(:release?)
    rescue NameError
      nil
    end
    mod = if defined?(Input::Controller)
            Input::Controller
          elsif defined?(::Controller)
            ::Controller
          end
    if mod
      @native_pad = mod.method(:pressex?) if mod.respond_to?(:pressex?)
      @native_states = mod.method(:raw_button_states) if mod.respond_to?(:raw_button_states)
    end
  end

  # Nomi SDL del pad -> bottone che il motore emette (poi passa dalla mappa dell'utente).
  PAD_NAMES = {
    A: :C, B: :B, X: :A, Y: :X, LEFTSTICK: :Y, RIGHTSTICK: :Z,
    LEFTSHOULDER: :L, RIGHTSHOULDER: :R,
    DPAD_UP: :UP, DPAD_DOWN: :DOWN, DPAD_LEFT: :LEFT, DPAD_RIGHT: :RIGHT,
  }.freeze
  # Tasti da tastiera (scancode SDL) che un gioco puo' interrogare -> stesso bottone.
  KEY_NAMES = {
    SPACE: :C, RETURN: :C, ESCAPE: :B, BACKSPACE: :A, PAGEUP: :L, PAGEDOWN: :R,
    UP: :UP, DOWN: :DOWN, LEFT: :LEFT, RIGHT: :RIGHT,
  }.freeze

  # F7 resta su ZR. Alt non ha un tasto fisso: i giochi che hanno il turbo
  # lo leggono dal loro tasto, e un Alt del porter ci finirebbe sopra.
  EXTRA_DEFAULTS = { "tasto_f7" => "Z" }.freeze
  EXTRA_KEYS = { F7: "tasto_f7" }.freeze
  EXTRA_CONSTS = { 27 => "tasto_f7" }.freeze # Input::F7
  # SDL_GameControllerButton: dopo START (6) vengono gli stick, le spalle e la croce.
  # Gli indici sono gli stessi già usati per − (4) e + (6). I nomi sono nel motore.
  DPAD = [
    ["UP", 11, :DPAD_UP, :UP],
    ["DOWN", 12, :DPAD_DOWN, :DOWN],
    ["LEFT", 13, :DPAD_LEFT, :LEFT],
    ["RIGHT", 14, :DPAD_RIGHT, :RIGHT],
  ].freeze
  # Clic degli stick. Nel database del motore: leftstick:b7, rightstick:b8.
  CLICKS = [
    ["L3", 7, :LEFTSTICK],
    ["R3", 8, :RIGHTSTICK],
  ].freeze

  def extra_button(setting)
    letter = (@cfg || {})[setting] || EXTRA_DEFAULTS[setting]
    letter.to_s.empty? ? nil : letter.to_s.to_sym
  end

  def croce?
    @cfg && @cfg["croce"] == "1"
  end

  def note_stick(orig)
    @stick_frame = @porter_frame
    if orig.is_a?(Array) && orig.length >= 2
      @stick = [orig[0].to_f, orig[1].to_f]
    else
      @stick = [0.0, 0.0]
    end
  end

  def stick_has?(dir)
    return false unless @stick && @stick_frame == @porter_frame
    x, y = @stick
    case dir
    when :RIGHT then x >= 0.5
    when :LEFT then x <= -0.5
    when :DOWN then y >= 0.5
    when :UP then y <= -0.5
    else false
    end
  end

  def dpad_entry(key)
    DPAD.each do |ident, index, symbol, dir|
      return [ident, index, symbol, dir] if key == dir || key == ident
      begin
        return [ident, index, symbol, dir] if key == code(dir)
      rescue StandardError
        nil
      end
    end
    nil
  end

  def croce_blocks?(key)
    return false unless croce?
    found = dpad_entry(key)
    return false unless found
    _ident, index, symbol, dir = found
    return false if stick_has?(dir)
    pad_raw?(index, symbol)
  end

  def filter_dir(value)
    value = value.to_i
    return value unless croce?
    vert = { 1 => :DOWN, 2 => :DOWN, 3 => :DOWN, 7 => :UP, 8 => :UP, 9 => :UP }[value]
    horiz = { 1 => :LEFT, 3 => :RIGHT, 4 => :LEFT, 6 => :RIGHT, 7 => :LEFT, 9 => :RIGHT }[value]
    return value unless (vert && croce_blocks?(vert)) || (horiz && croce_blocks?(horiz))
    vert = nil if vert && croce_blocks?(vert)
    horiz = nil if horiz && croce_blocks?(horiz)
    return 1 if vert == :DOWN && horiz == :LEFT
    return 3 if vert == :DOWN && horiz == :RIGHT
    return 7 if vert == :UP && horiz == :LEFT
    return 9 if vert == :UP && horiz == :RIGHT
    return 2 if vert == :DOWN
    return 8 if vert == :UP
    return 4 if horiz == :LEFT
    return 6 if horiz == :RIGHT
    0
  end

  def dpad_id?(button)
    DPAD.any? { |ident, _index, _symbol, _dir| ident == button }
  end

  def click_id?(button)
    CLICKS.any? { |ident, _index, _symbol| ident == button }
  end

  def binding_down?(button)
    found = DPAD.find { |ident, _index, _symbol, _dir| ident == button }
    if found
      return false unless croce?
      return pad_raw?(found[1], found[2])
    end
    click = CLICKS.find { |ident, _index, _symbol| ident == button }
    return pad_raw?(click[1], click[2]) if click
    down?(button.to_sym)
  end

  def virtual_const?(kind, key)
    setting = key.is_a?(Integer) ? EXTRA_CONSTS[key] : nil
    return false unless setting
    name = extra_button(setting)
    name ? engine_state(kind, name) : false
  end

  def engine_state(kind, name)
    fn = { press?: @raw_press, trigger?: @raw_trigger, repeat?: @raw_repeat, release?: @raw_release }[kind]
    return false unless fn
    fn.call(raw_code(code(name))) ? true : false
  rescue StandardError
    false
  end

  # Nessun bottone del controller inventato. Lo stick resta, perché è il movimento.
  def virtual_pad?(_kind, _key)
    false
  end

  # Il bottone fisico resta muto sul controller solo se il tasto scelto fa
  # un'azione diversa. A legato a C conferma ancora.
  # − e + non sono in questa tabella: servono al menu.
  def controller_hidden?(key)
    sym = key.is_a?(String) ? key.to_sym : key
    return false unless sym.is_a?(Symbol)
    name = PAD_NAMES[sym]
    return false unless name && button_bound?(name)
    label = bound_label(name)
    role = KEY_RGSS[label]
    return true unless role
    role != name
  end

  def bound_label(engine_name)
    found = (@bindings || []).find { |button, _label| button == engine_name.to_s }
    found ? found[1] : nil
  end

  # Nome che il gioco chiede (SDL) per ogni voce del menu tasti.
  KEY_SYMBOLS = {
    "Enter" => [:RETURN, :KP_ENTER],
    "Esc" => [:ESCAPE],
    "Space" => [:SPACE],
    "Shift" => [:LSHIFT, :RSHIFT],
    "Ctrl" => [:LCTRL, :RCTRL],
    "Alt" => [:LALT, :RALT],
    "Tab" => [:TAB],
  }.freeze

  def key_symbols(label)
    found = KEY_SYMBOLS[label]
    return found if found
    return [label.to_sym] if label =~ /\A[A-Z]\z/ || label =~ /\AF(?:[1-9]|1[0-2])\z/
    []
  end

  # Sul PC questi tasti accendono il bottone RGSS con lo stesso nome.
  # Invio e Spazio sono Conferma, Esc è Indietro, Maiusc è la corsa.
  # Le lettere C, X e Z sono conferma, indietro e azione nei fan game.
  # Invio e Spazio restano conferma, Esc indietro, Maiusc la corsa.
  # Stessa tabella dei fan game (buttonToKey), letta al contrario.
  # S non è un altro C: nel gioco S è il bottone Y.
  KEY_RGSS = {
    "Enter" => :C, "Space" => :C, "C" => :C,
    "Esc" => :B, "X" => :B,
    "Shift" => :A, "Z" => :A,
    "A" => :X, "S" => :Y, "D" => :Z,
    "Q" => :L, "W" => :R,
    "Ctrl" => :CTRL, "Alt" => :ALT,
    "F5" => :F5, "F6" => :F6, "F7" => :F7, "F8" => :F8, "F9" => :F9,
  }.freeze

  # Il pad assegnato a S deve accendere Input::Y, anche se il gioco
  # non sta chiedendo il bottone fisico che hai premuto.
  # Numeri che il gioco passa a trigger?/press?, indipendenti da Input::F5.
  # Z chiede 25 per F5, 23 per Alt, 22 per Ctrl. La costante del motore
  # può avere un altro valore: const_get da solo non basta.
  FIXED_RGSS = {
    "Shift" => [11, 21, 0x10],
    "Alt" => [23, 0x12],
    "Ctrl" => [22, 0x11],
    "F1" => [0x70], "F2" => [0x71], "F3" => [0x72], "F4" => [0x73],
    "F5" => [25, 0x74], "F6" => [26, 0x75], "F7" => [27, 0x76],
    "F8" => [28, 0x77], "F9" => [29, 0x78],
    "F10" => [0x79], "F11" => [0x7A], "F12" => [0x7B],
  }.freeze

  # Realidea numera di nuovo le lettere: F=30, M=31, Q=32, W=33, T=34, V=35.
  # Non sono i codici delle lettere C/X/Z. Si legge la costante del gioco.
  def game_code(label)
    name = { "Alt" => :ALT, "Shift" => :SHIFT, "Ctrl" => :CTRL }[label] || label.to_sym
    return nil if %i[A B C X Y Z L R UP DOWN LEFT RIGHT].include?(name)
    return nil unless Input.const_defined?(name)
    value = Input.const_get(name)
    value.is_a?(Integer) ? value : nil
  rescue StandardError
    nil
  end

  def label_hits?(label, key)
    return true if pc_code(label) == key
    own = game_code(label)
    return own == key if own
    fixed = FIXED_RGSS[label]
    return true if fixed && fixed.include?(key)
    role = KEY_RGSS[label]
    return false unless role
    code(role) == key
  rescue StandardError
    false
  end

  # La croce e lo stick accendono lo stesso Input::DOWN. Il tasto assegnato
  # alla freccia si legge solo dal pulsante fisico della croce.
  def dpad_state(kind, found)
    _ident, index, symbol, _dir = found
    return false unless croce?
    down = pad_raw?(index, symbol) ? true : false
    frame = @porter_frame || 0
    @dpad_slot ||= {}
    @dpad_was ||= {}
    unless @dpad_slot[index] && @dpad_slot[index][0] == frame
      was = @dpad_was[index] ? true : false
      @dpad_was[index] = down
      @dpad_slot[index] = [frame, down, down && !was]
    end
    _frame, held, edge = @dpad_slot[index]
    case kind
    when :press?, :repeat? then held
    when :trigger? then edge
    else false
    end
  end

  def physical_state(kind, button)
    found = DPAD.find { |ident, _index, _symbol, _dir| ident == button }
    return dpad_state(kind, found) if found
    click = CLICKS.find { |ident, _index, _symbol| ident == button }
    return pad_raw?(click[1], click[2]) ? true : false if click && kind != :trigger?
    engine_input(kind, code(button.to_sym)) ? true : false
  rescue StandardError
    false
  end

  def bound_role?(kind, key)
    return false unless key.is_a?(Integer)
    (@bindings || []).any? do |button, label|
      next false unless label_hits?(label, key)
      physical_state(kind, button)
    end
  end

  def button_bound?(engine_name)
    (@bindings || []).any? { |button, _label| button == engine_name.to_s }
  end

  def hides_native?(key)
    return false unless key.is_a?(Integer)
    PHYSICAL.any? do |name, _label|
      next false unless code(name) == key
      button_bound?(name)
    end
  end

  # Essentials sostituisce trigger? e legge i nomi dei tasti. Gli altri giochi
  # leggono il numero RGSS: per quelli il tasto scelto diventa quel numero.
  def filter_native(kind, key)
    return nil unless hides_native?(key)
    return nil if keyboard_method?(kind)
    return :yes if typed_key?(kind, key)
    return :yes if same_button?(kind, key)
    :no
  end

  # A legato alla lettera C: se la tastiera simulata non ha fatto in tempo,
  # vale il bottone vero, perché l'azione è la stessa.
  def same_button?(kind, key)
    return false unless key.is_a?(Integer)
    PHYSICAL.any? do |name, _label|
      next false unless code(name) == key && button_bound?(name)
      role = KEY_RGSS[bound_label(name)]
      next false unless role && code(role) == key
      engine_state(kind, name)
    end
  end

  def keyboard_method?(name)
    eigen = class << Input; self; end
    meth = eigen.instance_method(name)
    @keyboard_method ||= {}
    return @keyboard_method[meth] if @keyboard_method.key?(meth)
    loc = meth.source_location
    text = ""
    if loc
      lines = File.readlines(loc[0]) rescue []
      text = lines[(loc[1] - 1), 16].to_a.join
    end
    @keyboard_method[meth] = text.include?("triggerex?") || text.include?("pressex?")
  end

  def typed_key?(kind, key)
    return false unless key.is_a?(Integer)
    ask = { press?: :vk_held?, trigger?: :vk_edge?, repeat?: :vk_repeat?, release?: :vk_release? }[kind]
    return false unless ask
    (@bindings || []).any? do |_button, label|
      next false unless KEY_RGSS[label] && code(KEY_RGSS[label]) == key
      vk = pc_code(label)
      vk && send(ask, vk)
    end
  end

  def assigned?(sym)
    (@bindings || []).any? { |_button, label| key_symbols(label).include?(sym) }
  end

  def assigned_state?(kind, sym)
    ask = { press?: :vk_held?, trigger?: :vk_edge?, repeat?: :vk_repeat?, release?: :vk_release? }[kind]
    return false unless ask
    (@bindings || []).any? do |_button, label|
      next false unless key_symbols(label).include?(sym)
      vk = pc_code(label)
      vk && send(ask, vk)
    end
  end

  # Spazio e Invio sono la stessa conferma della lettera C. Esc è l'indietro della X.
  # Un gioco che aspetta solo quelli avanza, e non parte una seconda azione.
  FAMILY = {
    SPACE: :C, RETURN: :C, KP_ENTER: :C, ESCAPE: :B,
  }.freeze

  def family_state?(kind, sym)
    return false unless sym.is_a?(Symbol)
    role = FAMILY[sym]
    return false unless role
    ask = { press?: :vk_held?, trigger?: :vk_edge?, repeat?: :vk_repeat?, release?: :vk_release? }[kind]
    return false unless ask
    (@bindings || []).any? do |_button, label|
      next false unless KEY_RGSS[label] == role
      vk = pc_code(label)
      vk && send(ask, vk)
    end
  end

  def virtual_key?(kind, key)
    sym = key.is_a?(String) ? key.to_sym : key
    if sym.is_a?(Symbol) && assigned?(sym)
      return true if assigned_state?(kind, sym)
      setting = EXTRA_KEYS[sym]
      name = setting ? extra_button(setting) : nil
      return engine_state(kind, name) if name
      return false
    end
    return true if family_state?(kind, sym)
    name = KEY_NAMES[sym]
    return engine_state(kind, name) if name && !button_bound?(name)
    setting = EXTRA_KEYS[sym]
    name = setting ? extra_button(setting) : nil
    name ? engine_state(kind, name) : false
  end

  def pad_axes
    x = (engine_state(:press?, :RIGHT) ? 1.0 : 0.0) - (engine_state(:press?, :LEFT) ? 1.0 : 0.0)
    y = (engine_state(:press?, :DOWN) ? 1.0 : 0.0) - (engine_state(:press?, :UP) ? 1.0 : 0.0)
    [x, y]
  end

  def hook_pad(mod)
    return unless mod
    FanPorterGuard.capture(mod, :pressex?, :triggerex?, :repeatex?, :releaseex?, :axes_left)
    eigen = class << mod
      self
    end
    [:pressex?, :triggerex?, :repeatex?, :releaseex?].each do |name|
      alias_name = :"nx_engine_#{name.to_s.gsub('?', '')}"
      next unless eigen.method_defined?(name) || eigen.private_method_defined?(name)
      next if eigen.method_defined?(alias_name) || eigen.private_method_defined?(alias_name)
      eigen.send(:alias_method, alias_name, name)
    end
    return if eigen.ancestors.include?(FanPorterPad)
    eigen.prepend(FanPorterPad)
  end

  # Essentials chiede i tasti a Input::Controller (A, B, X). Il motore non li
  # riempie: li ricaviamo dai bottoni RGSS. ::Controller è l'altro nome possibile.
  def install_pad
    return if @pad_on
    @pad_on = true
    hook_pad(Input::Controller) if defined?(Input::Controller)
    if defined?(::Controller)
      hook_pad(::Controller)
    elsif !defined?(Input::Controller)
      fallback = Module.new
      fallback.define_singleton_method(:axes_right) { [0.0, 0.0] }
      fallback.define_singleton_method(:axes_trigger) { [0.0, 0.0] }
      fallback.define_singleton_method(:connected?) { true }
      Object.const_set(:Controller, fallback)
      hook_pad(::Controller)
    end
  end

  def down?(name)
    engine_input(:press?, code(name)) ? true : false
  end

  def hit?(name)
    engine_input(:trigger?, code(name)) ? true : false
  end

  def held?(name)
    engine_input(:repeat?, code(name)) ? true : false
  end

  def load_cfg
    @cfg = {}
    return unless File.exist?("porter.cfg")
    File.readlines("porter.cfg").each do |line|
      line = line.strip
      next if line.empty? || line.start_with?("#")
      key, value = line.split("=", 2)
      @cfg[key] = value if key && value
    end
  end

  def build_map
    @map = {}
    ACTIONS.each do |key, _label, raw_name|
      letter = @cfg[key] || raw_name.to_s
      @map[code(raw_name)] = code(letter)
    end
  end

  def letter_of(raw)
    PHYSICAL.each do |name, _label|
      return name.to_s if code(name) == raw
    end
    "C"
  end

  def label_of(raw)
    PHYSICAL.each do |name, label|
      return label if code(name) == raw
    end
    "?"
  end

  def save_cfg
    ACTIONS.each do |key, _label, raw_name|
      @cfg[key] = letter_of(@map[code(raw_name)])
    end
    @cfg["volume"] = volume.to_s
    @cfg["scala"] ||= "intera"
    @cfg["proporzioni"] ||= "fisse"
    @cfg["fps"] ||= "auto"
    @cfg["lingua"] ||= "en"
    @cfg["autore"] ||= "Zephiro"
    save_pc_text
    lines = []
    @cfg.each { |key, value| lines << "#{key}=#{value}" }
    File.open("porter.cfg", "w") { |file| file.write(lines.join("\n") + "\n") }
  end

  def want_menu?
    return true if @cfg["menu"] == "1"
    quiet = 0
    90.times do |tick|
      Graphics.update
      Input.update
      return true if combo?
      if down?(:L) || down?(:R) || down?(:Y)
        quiet = 0
      else
        quiet += 1
        break if quiet > 12 && tick > 12
      end
    end
    false
  end

  def run_menu
    begin
      Graphics.transition(0) if Graphics.respond_to?(:transition)
    rescue Exception
      nil
    end
    mark_shown
    @saved_brightness = nil
    if Graphics.respond_to?(:brightness) && Graphics.respond_to?(:brightness=)
      begin
        current = Graphics.brightness.to_i
        if current < 255
          @saved_brightness = current
          Graphics.brightness = 255
        end
      rescue Exception
        nil
      end
    end
    Graphics.update
    return if Graphics.width.to_i <= 0
    index = 0
    lock = 18
    idle = 0
    loop do
      rows = [
        [@during ? t("resume") : t("start"), nil],
        [t("graphics"), nil],
        [t("buttons"), nil],
        [t("volume"), "#{volume}%"],
        [t("language"), lang_name],
        [t("counter"), @cfg["contatore"] == "1" ? t("on") : t("off")],
        [t("registro"), @cfg["registro"] == "1" ? t("on") : t("off")],
        [t("menu_open"), menu_open_label],
      ]
      rows << [t("reset"), nil] if @during
      rows << [t("quit"), nil]
      paint(t("options"), rows, index, "#{menu_open_label}   #{t("footer_rest")}")
      Graphics.update
      Input.update
      idle = tick_idle(idle)
      break if idle > 1500
      if lock > 0
        lock -= 1
        next
      end
      index = move_index(index, rows.length)
      if index == 4 && hit?(:LEFT)
        set_lingua(-1)
      elsif index == 4 && hit?(:RIGHT)
        set_lingua(1)
      elsif index == 5 && (hit?(:LEFT) || hit?(:RIGHT) || hit?(:C))
        @cfg["contatore"] = @cfg["contatore"] == "1" ? "0" : "1"
        save_cfg
        dispose_counter if @cfg["contatore"] != "1" && @cfg["registro"] != "1"
      elsif index == 6 && (hit?(:LEFT) || hit?(:RIGHT) || hit?(:C))
        @cfg["registro"] = @cfg["registro"] == "1" ? "0" : "1"
        save_cfg
        dispose_counter if @cfg["registro"] != "1" && @cfg["contatore"] != "1"
      elsif index == 7 && hit?(:LEFT)
        cycle_menu_open(-1)
      elsif index == 7 && hit?(:RIGHT)
        cycle_menu_open(1)
      elsif held?(:LEFT)
        set_volume(volume - 10) if index == 3
      elsif held?(:RIGHT)
        set_volume(volume + 10) if index == 3
      elsif hit?(:C)
        case index
        when 0 then break
        when 1 then screen_grafica
        when 2 then screen_tasti
        when 4 then set_lingua(1)
        else
          if @during && index == 8
            reset_game if confirm?(t("reset_ask"), t("reset_note"))
          elsif index == rows.length - 1
            leave_game if confirm?(t("quit_ask"), t("quit_note"))
          end
        end
      elsif hit?(:B)
        break
      end
    end
  end

  def set_volume(value)
    value = 0 if value < 0
    value = 100 if value > 100
    @cfg["volume"] = value.to_s
    save_cfg
  end

  def tick_idle(idle)
    names = [:C, :B, :A, :X, :Y, :Z, :L, :R, :UP, :DOWN, :LEFT, :RIGHT]
    return 0 if names.any? { |name| down?(name) }
    idle + 1
  end

  def screen_grafica
    index = 0
    lock = 8
    idle = 0
    apply_live
    loop do
      rows = graphic_rows
      index = rows.length - 1 if index >= rows.length
      paint(t("graphics"), rows, index, graphics_note, false)
      Graphics.update
      Input.update
      idle = tick_idle(idle)
      break if idle > 1500
      if lock > 0
        lock -= 1
        next
      end
      index = move_index(index, rows.length)
      if held?(:LEFT)
        cycle(index, -1)
      elsif held?(:RIGHT)
        cycle(index, 1)
      elsif hit?(:C) || hit?(:B)
        break if index == rows.length - 1 || hit?(:B)
      end
    end
    patch_mkxp
    save_cfg
  end

  def graphic_rows
    rows = [
      [t("filter"), filter_label, :step],
      [t("aspect"), @cfg["proporzioni"] == "libere" ? t("free") : t("fixed"), :step],
      [t("speed"), speed_label, :step],
    ]
    rows << [t("blur"), blur? ? t("on") : t("off"), :step] if fps_capped?
    rows << [t("back"), nil]
    rows
  end

  def cycle(index, dir)
    case index
    when 0
      names = FILTERS.map { |name, _label| name }
      @cfg["scala"] = step(names, @cfg["scala"] || "intera", dir)
    when 1
      @cfg["proporzioni"] = @cfg["proporzioni"] == "libere" ? "fisse" : "libere"
    when 2
      @cfg["fps"] = step(FPS.map { |name, _label| name }, fps_choice, dir)
    when 3
      @cfg["blur"] = blur? ? "0" : "1" if fps_capped?
    end
    save_cfg
    apply_live
    patch_mkxp
    dispose_blur unless blur_live?
  end

  def fps_choice
    return "libero" if @cfg["fps"] == "libero"
    %w[30 45].include?(@cfg["fps"]) ? @cfg["fps"] : "auto"
  end

  # Il vsync del menu di gioco scrive solo la chiave vsync. Il motore però
  # va al ritmo del pannello (60) finché syncToRefreshrate è acceso, e in
  # quel caso ignora Graphics.frame_rate. I giochi sono scritti per 40.
  # Chi è già sotto i 40 (i titoli pesanti, intorno ai 30) non viene
  # rallentato: si aspetta solo se il fotogramma è arrivato prima.
  def pace_target
    case fps_choice
    when "30" then 30
    when "45" then 45
    else 40
    end
  end

  def pace
    return if fps_choice == "libero"
    now = Process.clock_gettime(Process::CLOCK_MONOTONIC)
    @pace_next ||= now
    @pace_next += 1.0 / pace_target
    @pace_next = now if @pace_next < now
    wait = @pace_next - now
    sleep(wait) if wait > 0.001
  rescue Exception
    nil
  end

  def fps_capped?
    fps_choice != "auto"
  end

  def blur?
    @cfg["blur"] == "1"
  end

  def blur_live?
    fps_capped? && blur? && !@restart_fps
  end

  def speed_label
    t(FPS.assoc(fps_choice)[1])
  end

  # Il motore espone questi tre mentre il gioco è aperto (nomi trovati nel .nro).
  # Lanczos è solo una chiave di mkxp.json: non ha un interruttore a gioco avviato.
  def apply_live
    return unless defined?(Graphics)
    scala = @cfg["scala"] || "intera"
    Graphics.integer_scaling = (scala == "intera") if Graphics.respond_to?(:integer_scaling=)
    Graphics.smooth_scaling = (scala == "morbida" || scala == "lanczos") if Graphics.respond_to?(:smooth_scaling=)
    Graphics.fixed_aspect_ratio = (@cfg["proporzioni"] != "libere") if Graphics.respond_to?(:fixed_aspect_ratio=)
  rescue Exception
    nil
  end

  def confirm?(title, note)
    lock = 8
    idle = 0
    loop do
      paint(title, [[note, nil]], 0, t("confirm_cancel"))
      Graphics.update
      Input.update
      idle = tick_idle(idle)
      return false if idle > 1500
      if lock > 0
        lock -= 1
        next
      end
      return true if hit?(:C)
      return false if hit?(:B)
    end
  end

  def reset_game
    save_cfg
    patch_mkxp
    apply_live
    dispose_screen
    # RGSS1 (Pokémon Z, Realidea) chiama l'eccezione Reset. RGSS3 la chiama RGSSReset.
    if Object.const_defined?(:RGSSReset)
      raise RGSSReset
    elsif Object.const_defined?(:Reset)
      raise Reset
    end
  end

  def leave_game
    save_cfg
    patch_mkxp
    dispose_screen
    Kernel.exit!(0)
  end

  def step(names, current, dir)
    index = names.index(current) || 0
    names[(index + dir) % names.length]
  end

  def filter_label
    name = @cfg["scala"] || "intera"
    return t("sharp") if name == "intera"
    return t("fill") if name == "nitida"
    return t("smooth") if name == "morbida"
    return t("lanczos") if name == "lanczos"
    t("sharp")
  end

  def graphics_note
    parts = []
    if (@cfg["scala"] || "intera") == "lanczos"
      parts << t("lanczos_next")
    else
      parts << t("live_note")
    end
    parts << t("cap_next") if @restart_fps
    parts << t("blur_note") if blur_live?
    parts.join("   ")
  end

  # Default dei fan game: A è la lettera C, B è la X, X è la Z.
  SUGGESTED = { "C" => "C", "B" => "X", "X" => "Z" }.freeze

  def key_of(button)
    found = (@bindings || []).find { |bound, _key| bound == button }
    found && found[1]
  end

  def key_label(button)
    chosen = key_of(button)
    return chosen if chosen
    hint = SUGGESTED[button]
    return "#{hint} #{t("suggest_mark")}" if hint
    t("none")
  end

  def set_key(button, key)
    @bindings ||= []
    @bindings.delete_if { |bound, _name| bound == button }
    @bindings << [button, key] if key && pc_code(key)
    save_pc_text
    save_cfg
  end

  def screen_tasti
    buttons = PHYSICAL.map { |name, label| [name.to_s, label] }
    index = 0
    lock = 8
    idle = 0
    loop do
      rows = buttons.map { |code, label| [label, key_label(code)] }
      click_at = rows.length
      CLICKS.each { |ident, _index, _symbol| rows << [ident, key_label(ident)] }
      croce_at = rows.length
      rows << [t("croce"), croce? ? t("on") : t("off")]
      dpad_at = rows.length
      if croce?
        DPAD.each { |ident, _index, _symbol, dir| rows << [t("pad_#{dir.to_s.downcase}"), key_label(ident)] }
      end
      back_at = rows.length
      rows << [t("back"), nil]
      note = if index == croce_at
               t("croce_note")
             else
               t("buttons_note")
             end
      paint(t("buttons"), rows, index, note)
      Graphics.update
      Input.update
      idle = tick_idle(idle)
      break if idle > 1500
      if lock > 0
        lock -= 1
        next
      end
      index = move_index(index, rows.length)
      if hit?(:B) || (hit?(:C) && index == back_at)
        break
      elsif index >= click_at && index < croce_at
        ident = CLICKS[index - click_at][0]
        if hit?(:X)
          set_key(ident, nil)
        elsif hit?(:C)
          picked = pick_pc_key(key_of(ident) || "F1")
          set_key(ident, picked) if picked
        end
      elsif index == croce_at && (hit?(:LEFT) || hit?(:RIGHT) || hit?(:C))
        @cfg["croce"] = croce? ? "0" : "1"
        save_cfg
      elsif croce? && index >= dpad_at && index < back_at
        ident = DPAD[index - dpad_at][0]
        if hit?(:X)
          set_key(ident, nil)
        elsif hit?(:C)
          picked = pick_pc_key(key_of(ident) || "F1")
          set_key(ident, picked) if picked
        end
      elsif hit?(:X) && index < buttons.length
        set_key(buttons[index][0], nil)
      elsif hit?(:C) && index < buttons.length
        code = buttons[index][0]
        current = key_of(code) || SUGGESTED[code] || "Enter"
        picked = pick_pc_key(current)
        set_key(code, picked) if picked
      end
    end
    save_cfg
  end

  def capture_button(index)
    action_key, _label, raw_name = ACTIONS[index]
    lock = 10
    idle = 0
    loop do
      rows = [[t(action_key), t("press")]]
      paint(t("new_button"), rows, 0, t("cancel_lr"))
      Graphics.update
      Input.update
      idle = tick_idle(idle)
      return if idle > 1500
      if lock > 0
        lock -= 1
        next
      end
      if down?(:L) && down?(:R)
        break
      end
      PHYSICAL.each do |name, _button|
        next unless hit?(name)
        assign(raw_name, name)
        save_cfg
        return
      end
    end
  end

  def assign(action_name, raw_name)
    action = code(action_name)
    raw = code(raw_name)
    previous = @map[action]
    ACTIONS.each do |_key, _label, other_name|
      other = code(other_name)
      @map[other] = previous if other != action && @map[other] == raw
    end
    @map[action] = raw
  end

  def move_index(index, length)
    if held?(:DOWN)
      return (index + 1) % length
    end
    if held?(:UP)
      return (index - 1) % length
    end
    index
  end

  def row_window(top, line, height, count, index)
    foot = [line, 36].max + 18
    room = height - top - foot
    room = line if room < line
    visible = room / line
    visible = 1 if visible < 1
    visible = count if visible > count
    start = index - visible + 1
    start = 0 if start < 0
    last = count - visible
    start = last if start > last
    [start, visible]
  end

  def menu_column(screen_w, screen_h)
    screen_w = 640 if screen_w.to_i <= 0
    screen_h = 480 if screen_h.to_i <= 0
    col = screen_h * 4 / 3
    col = screen_w if col > screen_w
    col = 720 if col > 720
    [(screen_w - col) / 2, col]
  end

  UI_DARK = {
    sky: [12, 20, 36], mist: [28, 48, 78], card: [22, 38, 64],
    ink: [234, 241, 255], muted: [143, 163, 199], accent: [63, 169, 255],
    select: [28, 64, 112], ghost: [16, 30, 52],
  }.freeze

  def ui_color(name, alpha = 255)
    rgb = UI_DARK[name]
    Color.new(rgb[0], rgb[1], rgb[2], alpha)
  end

  def ui_rgb(name)
    UI_DARK[name]
  end

  def fill_round(bitmap, x, y, w, h, radius, rgb, alpha = 255)
    return if w < 2 || h < 2
    radius = [radius, w / 2, h / 2].min
    color = Color.new(rgb[0], rgb[1], rgb[2], alpha)
    h.times do |i|
      inset = 0
      if radius > 0 && (i < radius || i >= h - radius)
        dy = i < radius ? radius - i : i - (h - 1 - radius)
        inside = radius * radius - dy * dy
        inset = inside <= 0 ? radius : radius - Math.sqrt(inside).to_i
      end
      span = w - inset * 2
      next if span <= 0
      bitmap.fill_rect(x + inset, y + i, span, 1, color)
    end
  end

  def ring_round(bitmap, x, y, w, h, radius, fill, ring, thick = 2)
    fill_round(bitmap, x, y, w, h, radius, ring)
    inner = [thick, 1].max
    fill_round(bitmap, x + inner, y + inner, w - inner * 2, h - inner * 2, [radius - inner, 1].max, fill)
  end

  def paint(section, rows, index, footer, cover = true)
    bitmap = screen
    bitmap.clear
    width = bitmap.width
    height = bitmap.height
    ox, box = menu_column(width, height)
    bitmap.font.size = [[box / 28, 16].max, 28].min
    line = bitmap.font.size + 18
    if cover
      bitmap.fill_rect(0, 0, width, height, ui_color(:sky))
      title = @cfg["titolo"] || "Fan Porter"
      draw_in(bitmap, ox, box, 16, "FAN PORTER", ui_color(:ink))
      draw_in(bitmap, ox, box, 18 + line, "0.7.6 · Zephiro", ui_color(:accent))
      draw_in(bitmap, ox, box, 22 + line * 2, title, ui_color(:ink))
      draw_in(bitmap, ox, box, 26 + line * 3, section, ui_color(:muted))
      top = 36 + line * 4
    else
      bitmap.fill_rect(0, 0, width, height, ui_color(:sky, 40))
      top = 28
      draw_in(bitmap, ox, box, top, section, ui_color(:muted))
      top += line
    end
    start, visible = row_window(top, line, height, rows.length, index)
    rows.each_with_index do |(label, value, kind), row|
      next if row < start || row >= start + visible
      y = top + (row - start) * line
      selected = row == index
      tile_h = line - 8
      tile_x = ox + 28
      tile_w = box - 56
      if selected
        ring_round(bitmap, tile_x, y, tile_w, tile_h, 12, ui_rgb(:select), ui_rgb(:accent), 3)
      else
        fill_round(bitmap, tile_x, y, tile_w, tile_h, 12, ui_rgb(:card))
      end
      bitmap.font.color = ui_color(:ink)
      bitmap.draw_text(tile_x + 22, y, tile_w / 2, tile_h, label.to_s, 0)
      if value
        shown = kind == :step ? "<  #{value}  >" : value.to_s
        bitmap.font.color = ui_color(:muted)
        bitmap.draw_text(tile_x + 22, y, tile_w - 36, tile_h, shown, 2)
      end
    end
    if rows.length > visible
      track = visible * line
      thumb = [[track * visible / rows.length, 8].max, track].min
      span = [rows.length - visible, 1].max
      thumb_y = top + (track - thumb) * start / span
      fill_round(bitmap, ox + box - 18, thumb_y, 4, thumb, 2, ui_rgb(:accent))
    end
    draw_in(bitmap, ox, box, height - line - 8, footer, ui_color(:muted))
  end

  def shade(bitmap, x, y, w, h, radius, top_rgb, bot_rgb, bar_rgb)
    return if w < 8 || h < 4
    radius = [radius, w / 2, h / 2].min
    h.times do |i|
      inset = 0
      if i < radius || i >= h - radius
        dy = i < radius ? radius - i : i - (h - 1 - radius)
        inside = radius * radius - dy * dy
        inset = inside <= 0 ? radius : radius - Math.sqrt(inside).to_i
      end
      blend = h <= 1 ? 0 : i.to_f / (h - 1)
      rgb = top_rgb.zip(bot_rgb).map { |a, b| (a + (b - a) * blend).to_i }
      span = w - inset * 2
      next if span <= 0
      bitmap.fill_rect(x + inset, y + i, span, 1, Color.new(*rgb))
      bitmap.fill_rect(x + inset, y + i, [3, span].min, 1, Color.new(*bar_rgb))
    end
  end

  def draw(bitmap, y, text, color)
    draw_in(bitmap, 0, bitmap.width, y, text, color)
  end

  def draw_in(bitmap, x, width, y, text, color)
    bitmap.font.color = color
    bitmap.draw_text(x, y, width, bitmap.font.size + 8, text, 1)
  end

  def tick_blur
    return dispose_blur unless blur_live? && !@in_menu && !@screen_frozen
    return dispose_blur unless defined?(Graphics) && Graphics.respond_to?(:snap_to_bitmap)
    @blur_sprite.visible = false if @blur_sprite && !@blur_sprite.disposed?
    shot = Graphics.snap_to_bitmap
    sprite = blur_sprite(shot.width, shot.height)
    old = sprite.bitmap
    sprite.bitmap = shot
    old.dispose if old && !old.disposed? && old != shot
    sprite.opacity = 120
    sprite.visible = true
  rescue Exception
    dispose_blur
  end

  def blur_sprite(width, height)
    if @blur_sprite && !@blur_sprite.disposed? && @blur_w == width && @blur_h == height
      return @blur_sprite
    end
    dispose_blur
    @blur_w = width
    @blur_h = height
    view = Viewport.new(0, 0, width, height)
    view.z = 0x3FFFFFFF
    @blur_view = view
    @blur_sprite = Sprite.new(view)
    @blur_sprite.z = 0
    @blur_sprite
  end

  def dispose_blur
    @blur_sprite.bitmap.dispose if @blur_sprite && @blur_sprite.bitmap && !@blur_sprite.bitmap.disposed?
    @blur_sprite.dispose if @blur_sprite && !@blur_sprite.disposed?
    @blur_view.dispose if @blur_view && !@blur_view.disposed?
    @blur_sprite = nil
    @blur_view = nil
  rescue Exception
    @blur_sprite = nil
    @blur_view = nil
  end

  def screen
    return @bitmap if @bitmap && !@bitmap.disposed?
    width = Graphics.width
    height = Graphics.height
    # Sopra il viewport del fade di Essentials (z 0x3FFFFFFF), altrimenti
    # il menu si disegna e lo schermo resta nero.
    @viewport = Viewport.new(0, 0, width, height)
    @viewport.z = 0x7FFFFFFF
    @bitmap = Bitmap.new(width, height)
    @sprite = Sprite.new(@viewport)
    @sprite.bitmap = @bitmap
    @sprite.z = 100
    @bitmap
  end

  def dispose_screen
    dispose_blur
    @sprite.dispose if @sprite && !@sprite.disposed?
    @bitmap.dispose if @bitmap && !@bitmap.disposed?
    @viewport.dispose if @viewport && !@viewport.disposed?
    @sprite = nil
    @bitmap = nil
    @viewport = nil
  end

  def tick_counter
    return if @in_menu
    show_rate = @cfg && @cfg["contatore"] == "1"
    show_ask = @cfg && @cfg["registro"] == "1" && @asked && !@asked.empty?
    unless show_rate || show_ask
      dispose_counter
      return
    end
    @counter_n = (@counter_n || 0) + 1
    return if @counter_sprite && !@counter_sprite.disposed? && @counter_n % 15 != 1
    sprite = counter_sprite
    return unless sprite
    bitmap = sprite.bitmap
    bitmap.clear
    bitmap.font.color = Color.new(255, 255, 255)
    bitmap.font.size = 16
    y = 0
    if show_rate && defined?(Graphics) && Graphics.respond_to?(:average_frame_rate)
      bitmap.fill_rect(0, 0, 64, 22, Color.new(10, 20, 40, 210))
      bitmap.draw_text(4, 2, 56, 18, Graphics.average_frame_rate.to_i.to_s, 0)
      y = 22
    end
    if show_ask
      bitmap.fill_rect(0, y, 220, 22, Color.new(10, 20, 40, 210))
      bitmap.draw_text(4, y + 2, 212, 18, "#{t("asks")} #{@asked}", 0)
    end
  rescue Exception
    dispose_counter
  end

  def counter_sprite
    return @counter_sprite if @counter_sprite && !@counter_sprite.disposed?
    bitmap = Bitmap.new(240, 44)
    sprite = Sprite.new
    sprite.bitmap = bitmap
    sprite.z = 30
    sprite.x = 8
    sprite.y = 8
    @counter_sprite = sprite
  end

  def dispose_counter
    if @counter_sprite && !@counter_sprite.disposed?
      @counter_sprite.bitmap.dispose if @counter_sprite.bitmap && !@counter_sprite.bitmap.disposed?
      @counter_sprite.dispose
    end
    @counter_sprite = nil
  end

  def pc_key_list
    return @pc_key_list if @pc_key_list
    list = []
    (1..12).each { |number| list << ["F#{number}", 0x6F + number] }
    list << ["Esc", 0x1B]
    list << ["Enter", 0x0D]
    list << ["Space", 0x20]
    list << ["Shift", 0x10]
    list << ["Ctrl", 0x11]
    list << ["Alt", 0x12]
    list << ["Tab", 0x09]
    ("A".."Z").each { |letter| list << [letter, letter.ord] }
    @pc_key_list = list
  end

  def pc_code(name)
    found = pc_key_list.find { |label, _code| label == name }
    found ? found[1] : nil
  end

  def load_pc
    @bindings = []
    (@cfg["pc"] || "").split(",").each do |item|
      button, key = item.split(":", 2)
      next unless button && key && pc_code(key)
      next unless PHYSICAL.any? { |name, _label| name.to_s == button } || dpad_id?(button) || click_id?(button)
      @bindings << [button, key]
    end
  end

  def save_pc_text
    @cfg["pc"] = (@bindings || []).map { |button, key| "#{button}:#{key}" }.join(",")
  end

  def pc_summary
    return t("none") if @bindings.nil? || @bindings.empty?
    button, key = @bindings[0]
    text = "#{label_of(code(button.to_sym))}=#{key}"
    text = "#{text} +" if @bindings.length > 1
    text
  end

  def buttons_now
    now = {}
    (@bindings || []).each do |button, key|
      vk = pc_code(key)
      now[vk] = true if vk && binding_down?(button)
    end
    f7 = extra_button("tasto_f7")
    now[0x76] = true if f7 && engine_state(:press?, f7)
    now
  end

  # Alt è 0x12, Shift 0x10, F1 è 0x70. Il gioco li chiede con triggerex?,
  # non come le lettere. Lo stato si aggiorna in Input.update e resta
  # leggibile per tutto il fotogramma: se si ricalcola alla lettura, il
  # fronte del tasto sparisce prima che il gioco lo veda.
  def refresh_keys
    now = buttons_now
    @edge = {}
    @release = {}
    now.each_key { |vk| @edge[vk] = !(@held_was || {})[vk] }
    (@held_was || {}).each_key { |vk| @release[vk] = !now[vk] }
    @repeat_n ||= {}
    (@repeat_n.keys | now.keys).each do |vk|
      if now[vk]
        @repeat_n[vk] = (@repeat_n[vk] || 0) + 1
      else
        @repeat_n.delete(vk)
      end
    end
    @held_was = now
  end

  # Il gioco chiede Alt, Shift e F5 con triggerex?(codice Windows),
  # nello stesso momento in cui il pad è giù. Non si usa lo stato del
  # fotogramma precedente: a quel punto il fronte è già stato consumato.
  def vk_matches?(kind, key)
    vk = key.to_i
    return false if vk <= 0
    (@bindings || []).any? do |button, label|
      next false unless pc_code(label) == vk
      physical_state(kind, button)
    end
  end

  def vk_held?(key)
    vk_matches?(:press?, key)
  end

  def vk_edge?(key)
    vk_matches?(:trigger?, key)
  end

  def vk_repeat?(key)
    vk_matches?(:repeat?, key)
  end

  def vk_release?(key)
    return false unless key.is_a?(Integer)
    (@release || {})[key] == true
  end

  def extra_down?(key)
    return false unless key.is_a?(Integer)
    return false if key <= 0
    vk_held?(key)
  end

  def extra_edge?(key)
    return false unless key.is_a?(Integer)
    return false if key <= 0
    vk_edge?(key)
  end

  def extra_repeat?(key)
    return false unless key.is_a?(Integer)
    return false if key <= 0
    vk_repeat?(key)
  end

  def install_win32_keys
    return if @win32_on
    return unless defined?(NXWin32) && NXWin32.respond_to?(:despacha)
    @win32_on = true
    original = NXWin32.method(:despacha)
    NXWin32.define_singleton_method(:despacha) do |clave, exporta, args|
      if clave == "user32!GetAsyncKeyState" || clave == "user32!GetKeyState"
        vk = args && args[0] ? args[0].to_i : 0
        return 0x8000 if FanPorter.vk_held?(vk)
      end
      result = original.call(clave, exporta, args)
      if clave == "user32!GetKeyboardState" && args && args[0].is_a?(String)
        FanPorter.mark_keyboard_state(args[0])
      end
      result
    end
  end

  def install_async_keys
    return if @async_on
    return unless defined?(Input) && Input.respond_to?(:asyncKeyState)
    @async_on = true
    original = Input.method(:asyncKeyState)
    Input.define_singleton_method(:asyncKeyState) do |vk|
      return 0x8000 if FanPorter.vk_held?(vk)
      original.call(vk)
    end
  end

  def mark_keyboard_state(buffer)
    (@bindings || []).each do |_button, key|
      vk = pc_code(key)
      next unless vk && vk < buffer.bytesize && vk_held?(vk)
      buffer.setbyte(vk, 0x80)
    end
  end

  def screen_pc
    index = 0
    lock = 8
    idle = 0
    loop do
      rows = @bindings.map { |button, key| [label_of(code(button.to_sym)), key] }
      rows << [t("add"), nil]
      rows << [t("back"), nil]
      paint(t("pc_key"), rows, index, t("pc_note"))
      Graphics.update
      Input.update
      idle = tick_idle(idle)
      break if idle > 1500
      if lock > 0
        lock -= 1
        next
      end
      index = move_index(index, rows.length)
      if hit?(:B) || (hit?(:C) && index == rows.length - 1)
        break
      elsif hit?(:X) && index < @bindings.length
        @bindings.delete_at(index)
        save_pc_text
        save_cfg
        index = 0 if index >= @bindings.length
      elsif hit?(:C) && index < @bindings.length
        picked = pick_pc_key(@bindings[index][1])
        if picked
          @bindings[index][1] = picked
          save_pc_text
          save_cfg
        end
      elsif hit?(:C) && index == @bindings.length
        button = capture_pc_button
        next unless button
        picked = pick_pc_key("F1")
        next unless picked
        @bindings.delete_if { |bound, _key| bound == button }
        @bindings << [button, picked]
        save_pc_text
        save_cfg
      end
    end
  end

  def capture_pc_button
    lock = 10
    idle = 0
    loop do
      paint(t("switch_button"), [[t("press"), nil]], 0, t("cancel_combo"))
      Graphics.update
      Input.update
      idle = tick_idle(idle)
      return nil if idle > 1500
      if lock > 0
        lock -= 1
        next
      end
      return nil if combo?
      PHYSICAL.each do |name, _button|
        next unless hit?(name)
        return name.to_s
      end
    end
  end

  def pc_sections
    [
      [t("function"), (1..12).map { |number| "F#{number}" }],
      [t("letters_am"), ("A".."M").to_a],
      [t("letters_nz"), ("N".."Z").to_a],
      [t("editing"), %w[Esc Enter Space Shift Ctrl Alt Tab]],
    ]
  end

  # Prima si sceglie il gruppo (funzione, lettere, modifica), poi il tasto in quel gruppo.
  # Su e giù spostano. Non si attraversa più tutta la tastiera con sinistra e destra.
  def pick_pc_key(current)
    sections = pc_sections
    sec = 0
    sections.each_with_index { |(_name, keys), row| sec = row if keys.include?(current) }
    choosing = false
    key_index = 0
    lock = 8
    idle = 0
    loop do
      if choosing
        keys = sections[sec][1]
        paint(sections[sec][0], keys.map { |name| [name, nil] }, key_index, t("back_section"))
      else
        paint(t("pc_key"), sections.map { |name, _keys| [name, nil] }, sec, t("open_section"))
      end
      Graphics.update
      Input.update
      idle = tick_idle(idle)
      return nil if idle > 1500
      if lock > 0
        lock -= 1
        next
      end
      if choosing
        keys = sections[sec][1]
        key_index = move_index(key_index, keys.length)
        if hit?(:C)
          return keys[key_index]
        elsif hit?(:B)
          choosing = false
          lock = 8
        end
      else
        sec = move_index(sec, sections.length)
        if hit?(:C)
          keys = sections[sec][1]
          key_index = keys.index(current) || 0
          choosing = true
          lock = 8
        elsif hit?(:B)
          return nil
        end
      end
    end
  end

  def patch_mkxp
    return unless File.exist?("mkxp.json")
    text = File.read("mkxp.json")
    scala = @cfg["scala"] || "intera"
    text = set_bool(text, "smoothScaling", scala == "morbida" || scala == "lanczos")
    text = set_bool(text, "integerScalingActive", scala == "intera")
    text = set_bool(text, "lanczos3Scaling", scala == "lanczos")
    text = set_bool(text, "fixedAspectRatio", @cfg["proporzioni"] != "libere")
    cap = fps_capped?
    number = fps_choice.to_i
    had = !!(text =~ /"fixedFramerate"\s*:\s*#{number}\b/)
    # Con syncToRefreshrate il motore spegne il limitatore e resta alla
    # frequenza del pannello (60). Il 45 esiste solo con entrambi spenti.
    text = set_bool(text, "vsync", !cap)
    text = set_bool(text, "syncToRefreshrate", !cap)
    text = cap ? upsert_int(text, "fixedFramerate", number) : drop_json_key(text, "fixedFramerate")
    return unless json_sano?(text)
    @cfg["fps"] = fps_choice
    @restart_fps = cap ? !had : had
    File.open("mkxp.json", "w") { |file| file.write(text) }
  end

  def upsert_int(text, key, value)
    pattern = /"#{Regexp.escape(key)}"\s*:\s*-?\d+/
    return text.sub(pattern, "\"#{key}\": #{value}") if text =~ pattern
    text.sub(/\n(\s*)\}\s*\z/, ",\n\\1\"#{key}\": #{value}\n}\n")
  end

  def drop_json_key(text, key)
    lines = text.each_line.reject { |line| line =~ /"#{Regexp.escape(key)}"\s*:/ }
    lines.reject! { |line| line.strip == "," }
    body = lines.join
    body.gsub(/,(\s*\})/, "\\1")
  end

  def json_sano?(text)
    return false if text.include?(",,") || text =~ /,\s*[\}\]]/
    depth = 0
    text.each_char do |char|
      depth += 1 if char == "{" || char == "["
      depth -= 1 if char == "}" || char == "]"
      return false if depth < 0
    end
    depth == 0 && text.include?("preloadScript")
  end

  def set_bool(text, key, value)
    word = value ? "true" : "false"
    text.sub(/("#{Regexp.escape(key)}"\s*:\s*)(?:true|false)/, "\\1#{word}")
  end
end

begin
  FanPorter.boot
rescue Exception => error
  begin
    File.open("porter-errore.txt", "w") do |file|
      file.puts(error.respond_to?(:full_message) ? error.full_message : error.to_s)
    end
  rescue Exception
  end
end
