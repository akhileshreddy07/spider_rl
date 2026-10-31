/**
 * SPIDER-SENSE ARENA // POKÉMON SHOWDOWN-INSPIRED BATTLE ENGINE
 * 
 * Replays real simulator JSON-lines match logs with turn-by-turn combat visual effects,
 * Showdown-style status boxes, animated battle log, and live simulator runner.
 */

class ShowdownBattleApp {
  constructor() {
    this.records = [];
    this.steps = [];
    this.summary = null;
    this.currentIndex = 0;
    this.isPlaying = false;
    this.playTimer = null;
    this.playSpeed = 1.0;
    this.soundEnabled = true;
    this.autoScroll = true;
    this.audioCtx = null;
    this.matchesList = [];

    this.initAudio();
    this.bindDOM();
    this.bindEvents();
    this.initMatchData();
  }

  /* ========================================================================
     1. ZERO-DEPENDENCY WEB AUDIO API PROCEDURAL SFX
     ======================================================================== */
  initAudio() {
    try {
      const AudioContext = window.AudioContext || window.webkitAudioContext;
      this.audioCtx = new AudioContext();
    } catch (e) {
      console.warn('Web Audio not supported in this browser environment.');
    }
  }

  playSound(type) {
    if (!this.soundEnabled || !this.audioCtx) return;
    if (this.audioCtx.state === 'suspended') {
      this.audioCtx.resume();
    }

    const t = this.audioCtx.currentTime;
    const osc = this.audioCtx.createOscillator();
    const gain = this.audioCtx.createGain();
    osc.connect(gain);
    gain.connect(this.audioCtx.destination);

    if (type === 'live_shot') {
      // Deep bass punch + explosive transient
      osc.type = 'sawtooth';
      osc.frequency.setValueAtTime(160, t);
      osc.frequency.exponentialRampToValueAtTime(30, t + 0.3);
      gain.gain.setValueAtTime(0.5, t);
      gain.gain.exponentialRampToValueAtTime(0.01, t + 0.3);
      osc.start(t);
      osc.stop(t + 0.3);
    } else if (type === 'blank_shot') {
      // Metallic dry click
      osc.type = 'sine';
      osc.frequency.setValueAtTime(900, t);
      osc.frequency.exponentialRampToValueAtTime(350, t + 0.08);
      gain.gain.setValueAtTime(0.25, t);
      gain.gain.exponentialRampToValueAtTime(0.01, t + 0.08);
      osc.start(t);
      osc.stop(t + 0.08);
    } else if (type === 'upgrade') {
      // Two-tone powerup chime
      osc.type = 'triangle';
      osc.frequency.setValueAtTime(523.25, t); // C5
      osc.frequency.exponentialRampToValueAtTime(1046.5, t + 0.16); // C6
      gain.gain.setValueAtTime(0.2, t);
      gain.gain.exponentialRampToValueAtTime(0.01, t + 0.16);
      osc.start(t);
      osc.stop(t + 0.16);
    } else if (type === 'faint') {
      // Low descending defeat tone
      osc.type = 'sine';
      osc.frequency.setValueAtTime(300, t);
      osc.frequency.exponentialRampToValueAtTime(80, t + 0.45);
      gain.gain.setValueAtTime(0.3, t);
      gain.gain.exponentialRampToValueAtTime(0.01, t + 0.45);
      osc.start(t);
      osc.stop(t + 0.45);
    }
  }

  /* ========================================================================
     2. DOM ELEMENT CACHING
     ======================================================================== */
  bindDOM() {
    this.dom = {
      // Header
      turnPill: document.getElementById('turnPill'),
      matchStateBadge: document.getElementById('matchStateBadge'),
      matchStateText: document.getElementById('matchStateText'),
      matchIdLabel: document.getElementById('matchIdLabel'),
      matchSeedLabel: document.getElementById('matchSeedLabel'),
      btnOpenLibrary: document.getElementById('btnOpenLibrary'),
      btnOpenSim: document.getElementById('btnOpenSim'),
      btnFilePicker: document.getElementById('btnFilePicker'),
      fileInput: document.getElementById('fileInput'),
      soundToggleBtn: document.getElementById('soundToggleBtn'),

      // Player Combat Side (Spider-Sense)
      playerStatusBox: document.getElementById('playerStatusBox'),
      playerName: document.getElementById('playerName'),
      playerCondition: document.getElementById('playerCondition'),
      playerHpText: document.getElementById('playerHpText'),
      playerHpFill: document.getElementById('playerHpFill'),
      playerHpPips: document.getElementById('playerHpPips'),
      playerAvatarSvg: document.getElementById('playerAvatarSvg'),
      playerPopup: document.getElementById('playerPopup'),
      playerJuice: document.getElementById('playerJuice'),
      playerCoffee: document.getElementById('playerCoffee'),
      playerMag: document.getElementById('playerMag'),
      playerFloatie: document.getElementById('playerFloatie'),
      playerSaw: document.getElementById('playerSaw'),

      // Opponent Combat Side (Supports multi-opponents)
      opponentSideContainer: document.getElementById('opponentSideContainer'),
      oppStatusBox: document.getElementById('oppStatusBox-1'),
      oppName: document.getElementById('oppName-1'),
      oppCondition: document.getElementById('oppCondition-1'),
      oppHpText: document.getElementById('oppHpText-1'),
      oppHpFill: document.getElementById('oppHpFill-1'),
      oppHpPips: document.getElementById('oppHpPips-1'),
      oppAvatarSvg: document.getElementById('oppAvatarSvg-1'),
      oppPopup: document.getElementById('oppPopup-1'),
      oppJuice: document.getElementById('oppJuice-1'),
      oppCoffee: document.getElementById('oppCoffee-1'),
      oppMag: document.getElementById('oppMag-1'),
      oppFloatie: document.getElementById('oppFloatie-1'),
      oppSaw: document.getElementById('oppSaw-1'),

      // Central Arena Elements
      duelShotgunWrap: document.getElementById('duelShotgunWrap'),
      duelMuzzleFlash: document.getElementById('duelMuzzleFlash'),
      ammoRackRow: document.getElementById('ammoRackRow'),
      ammoRemainingVal: document.getElementById('ammoRemainingVal'),
      ammoLiveVal: document.getElementById('ammoLiveVal'),
      ammoBlankVal: document.getElementById('ammoBlankVal'),
      radarOddsFill: document.getElementById('radarOddsFill'),
      radarLivePct: document.getElementById('radarLivePct'),
      radarBlankPct: document.getElementById('radarBlankPct'),
      marketDraftTray: document.getElementById('marketDraftTray'),
      marketDraftBadges: document.getElementById('marketDraftBadges'),

      // Showdown Battle Log
      battleLogStream: document.getElementById('battleLogStream'),
      autoScrollCheck: document.getElementById('autoScrollCheck'),
      btnJumpLatest: document.getElementById('btnJumpLatest'),

      // Playback Controls
      btnRestart: document.getElementById('btnRestart'),
      btnPrev: document.getElementById('btnPrev'),
      playToggleBtn: document.getElementById('playToggleBtn'),
      btnNext: document.getElementById('btnNext'),
      btnEnd: document.getElementById('btnEnd'),
      timelineSlider: document.getElementById('timelineSlider'),
      currentStepNum: document.getElementById('currentStepNum'),
      totalStepsNum: document.getElementById('totalStepsNum'),
      currentRoundText: document.getElementById('currentRoundText'),
      speedButtons: document.querySelectorAll('.speed-btn'),

      // Modals
      modalLibrary: document.getElementById('modalLibrary'),
      closeLibraryBtn: document.getElementById('closeLibraryBtn'),
      matchPickerList: document.getElementById('matchPickerList'),
      modalSim: document.getElementById('modalSim'),
      closeSimBtn: document.getElementById('closeSimBtn'),
      simSeedInput: document.getElementById('simSeedInput'),
      simPlayersSelect: document.getElementById('simPlayersSelect'),
      btnSubmitSim: document.getElementById('btnSubmitSim'),
      simLoadingIcon: document.getElementById('simLoadingIcon'),
      modalVictory: document.getElementById('modalVictory'),
      closeVictoryBtn: document.getElementById('closeVictoryBtn'),
      victoryCard: document.getElementById('victoryCard'),
      victoryTrophyIcon: document.getElementById('victoryTrophyIcon'),
      victoryTitle: document.getElementById('victoryTitle'),
      victorySubtitle: document.getElementById('victorySubtitle'),
      victoryStatsDetails: document.getElementById('victoryStatsDetails'),
    };
  }

  /* ========================================================================
     3. EVENT BINDINGS
     ======================================================================== */
  bindEvents() {
    // Media Playback
    this.dom.playToggleBtn.addEventListener('click', () => this.togglePlay());
    this.dom.btnPrev.addEventListener('click', () => this.stepBy(-1));
    this.dom.btnNext.addEventListener('click', () => this.stepBy(1));
    this.dom.btnRestart.addEventListener('click', () => this.goToIndex(0));
    this.dom.btnEnd.addEventListener('click', () => this.goToIndex(this.steps.length - 1));

    this.dom.timelineSlider.addEventListener('input', (e) => {
      this.goToIndex(parseInt(e.target.value, 10));
    });

    this.dom.speedButtons.forEach(btn => {
      btn.addEventListener('click', (e) => {
        this.dom.speedButtons.forEach(b => b.classList.remove('active'));
        e.currentTarget.classList.add('active');
        this.playSpeed = parseFloat(e.currentTarget.getAttribute('data-speed'));
        if (this.isPlaying) {
          this.pause();
          this.play();
        }
      });
    });

    // Sound toggle
    this.dom.soundToggleBtn.addEventListener('click', () => {
      this.soundEnabled = !this.soundEnabled;
      this.dom.soundToggleBtn.innerHTML = this.soundEnabled ? '🔊 SFX' : '🔇 Muted';
    });

    // Keyboard Shortcuts
    window.addEventListener('keydown', (e) => {
      if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT') return;
      if (e.code === 'Space') {
        e.preventDefault();
        this.togglePlay();
      } else if (e.code === 'ArrowLeft') {
        e.preventDefault();
        this.stepBy(-1);
      } else if (e.code === 'ArrowRight') {
        e.preventDefault();
        this.stepBy(1);
      } else if (e.code === 'Home') {
        e.preventDefault();
        this.goToIndex(0);
      } else if (e.code === 'End') {
        e.preventDefault();
        this.goToIndex(this.steps.length - 1);
      }
    });

    // Auto-scroll toggle & Jump to Latest
    this.dom.autoScrollCheck.addEventListener('change', (e) => {
      this.autoScroll = e.target.checked;
    });

    this.dom.battleLogStream.addEventListener('scroll', () => {
      const el = this.dom.battleLogStream;
      const isAtBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
      this.dom.btnJumpLatest.style.display = isAtBottom ? 'none' : 'block';
    });

    this.dom.btnJumpLatest.addEventListener('click', () => {
      const el = this.dom.battleLogStream;
      el.scrollTop = el.scrollHeight;
      this.dom.btnJumpLatest.style.display = 'none';
      this.dom.autoScrollCheck.checked = true;
      this.autoScroll = true;
    });

    // Modals
    this.dom.btnOpenLibrary.addEventListener('click', () => this.openLibraryModal());
    this.dom.closeLibraryBtn.addEventListener('click', () => this.closeLibraryModal());
    this.dom.btnOpenSim.addEventListener('click', () => this.openSimModal());
    this.dom.closeSimBtn.addEventListener('click', () => this.closeSimModal());
    this.dom.closeVictoryBtn.addEventListener('click', () => this.dom.modalVictory.classList.remove('open'));

    // File picker & Drag-and-drop
    this.dom.btnFilePicker.addEventListener('click', () => this.dom.fileInput.click());
    this.dom.fileInput.addEventListener('change', (e) => {
      const file = e.target.files[0];
      if (file) this.loadFile(file);
    });

    window.addEventListener('dragover', (e) => e.preventDefault());
    window.addEventListener('drop', (e) => {
      e.preventDefault();
      if (e.dataTransfer.files && e.dataTransfer.files[0]) {
        this.loadFile(e.dataTransfer.files[0]);
      }
    });

    // Live Simulator Submit
    this.dom.btnSubmitSim.addEventListener('click', () => this.executeLiveSimulation());
  }

  /* ========================================================================
     4. MATCH DATA INITIALIZATION
     ======================================================================== */
  async initMatchData() {
    try {
      const res = await fetch('/api/matches');
      if (res.ok) {
        this.matchesList = await res.json();
      }
    } catch (e) {
      console.log('API not reachable; running in standalone mode.');
    }

    if (this.matchesList && this.matchesList.length > 0) {
      await this.loadMatchByPath(this.matchesList[0].path);
    } else if (window.DEFAULT_MATCH_LINES) {
      this.loadMatchFromLines(window.DEFAULT_MATCH_LINES, 'Sample Simulator Match');
    }
  }

  loadFile(file) {
    const reader = new FileReader();
    reader.onload = (e) => {
      const lines = e.target.result.split('\n').filter(l => l.trim().length > 0);
      this.loadMatchFromLines(lines, file.name);
    };
    reader.readAsText(file);
  }

  async loadMatchByPath(relPath) {
    try {
      const res = await fetch(`/api/match?path=${encodeURIComponent(relPath)}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      this.loadMatchFromRecords(data.records, relPath);
    } catch (err) {
      console.error('Failed to load match via API:', err);
    }
  }

  loadMatchFromLines(lines, label = 'Match Log') {
    const records = [];
    for (const line of lines) {
      try {
        records.push(JSON.parse(line));
      } catch (e) {}
    }
    this.loadMatchFromRecords(records, label);
  }

  loadMatchFromRecords(records, label = '') {
    this.pause();
    this.records = records;
    this.steps = records.filter(r => r.step !== undefined);
    const lastRec = records[records.length - 1];
    this.summary = lastRec && lastRec.summary ? lastRec.summary : null;

    if (this.steps.length === 0) {
      alert('No decision records found in this log.');
      return;
    }

    // Header info
    const matchId = (this.summary && this.summary.match_id) || label || 'match_0';
    this.dom.matchIdLabel.innerText = matchId;
    this.dom.matchSeedLabel.innerText = this.summary ? this.summary.seed : 'N/A';
    this.dom.timelineSlider.min = 0;
    this.dom.timelineSlider.max = this.steps.length - 1;
    this.dom.totalStepsNum.innerText = this.steps.length;

    // Render entire battle log in advance
    this.renderInitialBattleLog();

    // Start at step 0
    this.goToIndex(0);
  }

  /* ========================================================================
     5. SHOWDOWN PLAYBACK CONTROLS
     ======================================================================== */
  togglePlay() {
    if (this.isPlaying) {
      this.pause();
    } else {
      if (this.currentIndex >= this.steps.length - 1) {
        this.goToIndex(0);
      }
      this.play();
    }
  }

  play() {
    this.isPlaying = true;
    this.dom.playToggleBtn.innerHTML = '⏸';
    this.setMatchState('running', 'RUNNING');
    const interval = Math.max(90, 850 / this.playSpeed);

    this.playTimer = setInterval(() => {
      if (this.currentIndex < this.steps.length - 1) {
        this.goToIndex(this.currentIndex + 1);
      } else {
        this.pause();
        this.setMatchState('finished', 'FINISHED');
        this.showVictoryModal();
      }
    }, interval);
  }

  pause() {
    this.isPlaying = false;
    this.dom.playToggleBtn.innerHTML = '▶';
    this.setMatchState('paused', 'PAUSED');
    if (this.playTimer) {
      clearInterval(this.playTimer);
      this.playTimer = null;
    }
  }

  stepBy(delta) {
    this.pause();
    const nextIdx = this.currentIndex + delta;
    if (nextIdx >= 0 && nextIdx < this.steps.length) {
      this.goToIndex(nextIdx);
    }
  }

  goToIndex(index) {
    if (index < 0 || index >= this.steps.length) return;
    this.currentIndex = index;
    this.dom.timelineSlider.value = index;
    this.dom.currentStepNum.innerText = index + 1;
    this.dom.turnPill.innerText = `TURN ${index + 1}`;

    const step = this.steps[index];
    const prevStep = index > 0 ? this.steps[index - 1] : null;

    this.renderBattleState(step, prevStep);
    this.highlightActiveLogEntry(index);

    if (index === this.steps.length - 1) {
      this.setMatchState('finished', 'FINISHED');
    }
  }

  setMatchState(cls, text) {
    this.dom.matchStateBadge.className = `status-badge ${cls}`;
    this.dom.matchStateText.innerText = text;
  }

  /* ========================================================================
     6. SHOWDOWN BATTLE STATE RENDERING
     ======================================================================== */
  renderBattleState(step, prevStep) {
    const obs = step.obs;
    const action = step.action || {};
    const seat = step.seat;
    const stage = step.stage;

    this.dom.currentRoundText.innerText = `Round ${obs.session_no + 1}`;

    // 1. Update Player Status (Seat 0: spider_sense)
    const player = obs.players[0] || { health: 5, upgrades: {} };
    this.renderStatusCard(
      player,
      this.dom.playerStatusBox,
      this.dom.playerHpFill,
      this.dom.playerHpText,
      this.dom.playerHpPips,
      this.dom.playerCondition,
      {
        juice: this.dom.playerJuice,
        coffee: this.dom.playerCoffee,
        mag: this.dom.playerMag,
        floatie: this.dom.playerFloatie,
        saw: this.dom.playerSaw,
      },
      seat === 0,
      obs.max_health || 5
    );

    // 2. Update Opponent Status (Supports single or multi opponents)
    const oppSeat = this.getPrimaryOpponentSeat(obs, seat);
    const opp = obs.players[oppSeat] || { health: 5, upgrades: {} };
    this.dom.oppName.innerText = this.getPlayerName(oppSeat);
    this.renderStatusCard(
      opp,
      this.dom.oppStatusBox,
      this.dom.oppHpFill,
      this.dom.oppHpText,
      this.dom.oppHpPips,
      this.dom.oppCondition,
      {
        juice: this.dom.oppJuice,
        coffee: this.dom.oppCoffee,
        mag: this.dom.oppMag,
        floatie: this.dom.oppFloatie,
        saw: this.dom.oppSaw,
      },
      seat === oppSeat,
      obs.max_health || 5
    );

    // 3. Chamber Ammo Rack & Spider-Sense Radar
    this.renderChamberAndRadar(obs);

    // 4. Combat Animations & Damage Popups
    this.triggerCombatAnimations(step, prevStep, seat, oppSeat);

    // 5. Upgrade Draft Tray (during PICK_UPGRADE)
    if (stage === 'PICK_UPGRADE' && obs.available_upgrades) {
      this.dom.marketDraftTray.style.display = 'flex';
      const upg = obs.available_upgrades;
      this.dom.marketDraftBadges.innerHTML = `
        <span class="market-draft-badge">🧃 Juice: ${upg.juice || 0}</span>
        <span class="market-draft-badge">☕ Coffee: ${upg.coffee || 0}</span>
        <span class="market-draft-badge">🔍 Mag: ${upg.mag_glass || 0}</span>
        <span class="market-draft-badge">🛟 Floatie: ${upg.pool_floatie || 0}</span>
        <span class="market-draft-badge">🪚 Saw: ${upg.hand_saw || 0}</span>
      `;
    } else {
      this.dom.marketDraftTray.style.display = 'none';
    }
  }

  renderStatusCard(player, boxEl, hpFillEl, hpTextEl, pipsContainer, conditionEl, upgEls, isTurn, maxHp) {
    const hp = player.health;
    const hpPct = Math.max(0, Math.min(100, (hp / maxHp) * 100));

    // Turn border highlight
    if (isTurn) {
      boxEl.classList.add('active-turn');
    } else {
      boxEl.classList.remove('active-turn');
    }

    // Health bar fill & Showdown color transition
    hpFillEl.style.width = `${hpPct}%`;
    hpFillEl.className = 'hp-fill';
    if (hpPct <= 20) {
      hpFillEl.classList.add('red');
    } else if (hpPct <= 50) {
      hpFillEl.classList.add('yellow');
    }

    hpTextEl.innerText = `${hp} / ${maxHp} (${Math.round(hpPct)}%)`;

    // Dynamic health pips
    let pips = pipsContainer.querySelectorAll('.hp-pip');
    if (pips.length !== maxHp) {
      pipsContainer.innerHTML = '';
      for (let i = 0; i < maxHp; i++) {
        const p = document.createElement('div');
        p.className = 'hp-pip';
        pipsContainer.appendChild(p);
      }
      pips = pipsContainer.querySelectorAll('.hp-pip');
    }

    pips.forEach((pip, idx) => {
      pip.className = 'hp-pip';
      if (idx < hp) {
        pip.classList.add('active');
        if (hpPct <= 20) pip.classList.add('red');
        else if (hpPct <= 50) pip.classList.add('yellow');
      }
    });

    // Condition Badge
    if (hp <= 0) {
      conditionEl.className = 'status-condition-badge fainted';
      conditionEl.innerText = 'ELIMINATED';
      boxEl.classList.add('fainted');
    } else if (player.has_pool_floatie_on) {
      conditionEl.className = 'status-condition-badge skipped';
      conditionEl.innerText = 'SKIPPED';
      boxEl.classList.remove('fainted');
    } else {
      conditionEl.className = 'status-condition-badge alive';
      conditionEl.innerText = 'ALIVE';
      boxEl.classList.remove('fainted');
    }

    // Upgrade counts & Active Highlights
    const upg = player.upgrades || {};
    const setUpg = (el, val) => {
      el.innerText = val || 0;
      const parent = el.closest('.item-badge');
      if (parent) {
        if (val > 0) parent.classList.add('has-item');
        else parent.classList.remove('has-item');
      }
    };
    setUpg(upgEls.juice, upg.juice);
    setUpg(upgEls.coffee, upg.coffee);
    setUpg(upgEls.mag, upg.mag_glass);
    setUpg(upgEls.floatie, upg.pool_floatie);
    setUpg(upgEls.saw, upg.hand_saw);
  }

  renderChamberAndRadar(obs) {
    if (obs.lives_init === undefined) return;

    const livesInit = obs.lives_init || 0;
    const blanksInit = obs.blanks_init || 0;
    const total = livesInit + blanksInit;
    const rem = obs.rounds_remaining;

    // Cartridge rack
    const rack = this.dom.ammoRackRow;
    rack.innerHTML = '';
    for (let i = 0; i < total; i++) {
      const pip = document.createElement('div');
      pip.className = 'shell-pip';
      if (i >= rem) {
        pip.classList.add('spent');
      } else {
        pip.classList.add('active');
      }
      rack.appendChild(pip);
    }

    this.dom.ammoRemainingVal.innerText = rem;
    this.dom.ammoLiveVal.innerText = `${obs.lives_shot || 0}/${livesInit}L`;
    this.dom.ammoBlankVal.innerText = `${obs.blanks_shot || 0}/${blanksInit}B`;

    // Spider-Sense Bayesian Radar calculation
    let pLive = 0.5;
    if (obs.next_round === 'LIVE') {
      pLive = 1.0;
    } else if (obs.next_round === 'BLANK') {
      pLive = 0.0;
    } else {
      const ejections = obs.ejections || { lives_ejected: 0, blanks_ejected: 0 };
      const livesConsumed = (obs.lives_shot || 0) + (ejections.lives_ejected || 0);
      const blanksConsumed = (obs.blanks_shot || 0) + (ejections.blanks_ejected || 0);
      const remLive = Math.max(0, livesInit - livesConsumed);
      const remBlank = Math.max(0, blanksInit - blanksConsumed);
      const totalUnobs = remLive + remBlank;
      if (totalUnobs <= 0) pLive = 0.5;
      else if (remLive === 0) pLive = 0.0;
      else if (remBlank === 0) pLive = 1.0;
      else pLive = remLive / totalUnobs;
    }

    const livePct = Math.round(pLive * 100);
    const blankPct = 100 - livePct;
    this.dom.radarOddsFill.style.width = `${livePct}%`;
    this.dom.radarLivePct.innerText = `${livePct}% LIVE`;
    this.dom.radarBlankPct.innerText = `${blankPct}% BLANK`;
  }

  /* ========================================================================
     7. COMBAT ANIMATIONS & FLOATING POPUPS
     ======================================================================== */
  triggerCombatAnimations(step, prevStep, seat, oppSeat) {
    const act = step.action || {};
    const obs = step.obs;
    const isPlayerActing = seat === 0;

    // Reset animations
    this.dom.playerAvatarSvg.className = 'bot-avatar-sprite idle-float';
    this.dom.oppAvatarSvg.className = 'bot-avatar-sprite idle-float';
    this.dom.duelMuzzleFlash.className = 'duel-muzzle-flash';

    if (step.stage === 'PLAY' && act.action === 'SHOOT') {
      const target = act.target;
      const isShootingSelf = target === seat;

      // Determine if live by checking target HP in next step
      const nextStep = this.currentIndex < this.steps.length - 1 ? this.steps[this.currentIndex + 1] : null;
      let isLive = false;
      let dmg = 0;

      if (nextStep && nextStep.obs && nextStep.obs.players[target]) {
        const prevHp = obs.players[target] ? obs.players[target].health : 0;
        const nextHp = nextStep.obs.players[target].health;
        if (nextHp < prevHp) {
          isLive = true;
          dmg = prevHp - nextHp;
        } else if (nextStep.obs.lives_shot > (obs.lives_shot || 0)) {
          isLive = true;
        }
      }

      // Aim shotgun
      this.dom.duelShotgunWrap.style.transform = isShootingSelf
        ? 'rotate(-25deg) scaleX(-1)'
        : (isPlayerActing ? 'rotate(-10deg) scaleX(1)' : 'rotate(10deg) scaleX(-1)');

      // Attacker lunge
      if (isPlayerActing) {
        this.dom.playerAvatarSvg.className = 'bot-avatar-sprite attack-lunge-hero';
      } else {
        this.dom.oppAvatarSvg.className = 'bot-avatar-sprite attack-lunge-foe';
      }

      // Muzzle flash
      this.dom.duelMuzzleFlash.className = `duel-muzzle-flash ${isLive ? 'fire-live' : 'fire-blank'}`;

      if (isLive) {
        this.playSound('live_shot');
        const stageEl = document.getElementById('battleStage');
        if (stageEl) {
          stageEl.classList.remove('damage-flash');
          void stageEl.offsetWidth;
          stageEl.classList.add('damage-flash');
        }
        // Target hit shake
        if (target === 0) {
          this.dom.playerAvatarSvg.className = 'bot-avatar-sprite hit-shake';
          this.showPopup(this.dom.playerPopup, `-${dmg || 1} HP`, 'damage');
        } else {
          this.dom.oppAvatarSvg.className = 'bot-avatar-sprite hit-shake';
          this.showPopup(this.dom.oppPopup, `-${dmg || 1} HP`, 'damage');
        }
      } else {
        this.playSound('blank_shot');
        if (isShootingSelf) {
          const popupEl = isPlayerActing ? this.dom.playerPopup : this.dom.oppPopup;
          this.showPopup(popupEl, 'BLANK (SAFE)', 'blank');
        } else {
          const popupEl = target === 0 ? this.dom.playerPopup : this.dom.oppPopup;
          this.showPopup(popupEl, 'BLANK (0 DMG)', 'blank');
        }
      }
    } else if (step.stage === 'PLAY' && act.action === 'USE_UPGRADE') {
      this.playSound('upgrade');
      const upg = act.useUpgrade;
      const popupEl = isPlayerActing ? this.dom.playerPopup : this.dom.oppPopup;

      if (upg === 'JUICE') this.showPopup(popupEl, '🧃 +1 HP HEAL', 'heal');
      else if (upg === 'MAG_GLASS') this.showPopup(popupEl, '🔍 PEEKED SHELL', 'boost');
      else if (upg === 'COFFEE') this.showPopup(popupEl, '☕ EJECTED SHELL', 'boost');
      else if (upg === 'HAND_SAW') this.showPopup(popupEl, '🪚 SAW BOOST (+1 DMG)', 'damage');
      else if (upg === 'POOL_FLOATIE') {
        const targetEl = act.target === 0 ? this.dom.playerPopup : this.dom.oppPopup;
        this.showPopup(targetEl, '🛟 TURN SKIPPED', 'boost');
      }
    }
  }

  showPopup(el, text, type) {
    if (!el) return;
    el.innerText = text;
    el.className = `combat-popup-text ${type}`;
    el.style.display = 'block';
    setTimeout(() => {
      el.style.display = 'none';
    }, 800);
  }

  /* ========================================================================
     8. SHOWDOWN BATTLE LOG STREAM
     ======================================================================== */
  renderInitialBattleLog() {
    const stream = this.dom.battleLogStream;
    stream.innerHTML = '';

    let currentSession = -1;

    this.steps.forEach((step, idx) => {
      const obs = step.obs;
      const act = step.action || {};
      const seat = step.seat;
      const actorName = this.getPlayerName(seat);
      const isHero = seat === 0;

      // 1. Session / Round Divider
      if (obs.session_no !== currentSession) {
        currentSession = obs.session_no;
        const roundDiv = document.createElement('div');
        roundDiv.className = 'log-turn-divider';
        roundDiv.innerHTML = `
          <span>★ ROUND ${currentSession + 1} INITIALIZED</span>
          <span>${obs.lives_init || 0} LIVE / ${obs.blanks_init || 0} BLANK</span>
        `;
        stream.appendChild(roundDiv);
      }

      // 2. Turn Entry
      const entry = document.createElement('div');
      entry.className = 'log-entry-row';
      entry.id = `logEntry-${idx}`;
      entry.addEventListener('click', () => this.goToIndex(idx));

      let eventType = 'ACTION';
      let eventIcon = '🎯';
      let actionDesc = '';

      if (step.fault) {
        eventType = 'FAULT';
        eventIcon = '⚠️';
        entry.classList.add('type-fault');
        actionDesc = `<span class="log-hit-live">⚠️ FAULT DETECTED: ${step.fault}</span>`;
      } else if (step.stage === 'PLAY') {
        if (act.action === 'SHOOT') {
          eventType = 'SHOOT';
          eventIcon = '🎯';
          entry.classList.add('type-shoot');
          const targetName = this.getPlayerName(act.target);
          const isSelf = act.target === seat;
          actionDesc = `<span class="${isHero ? 'log-actor-spider' : 'log-actor-opp'}">${actorName}</span> targeted <b>${isSelf ? 'SELF' : targetName}</b> with shotgun`;
        } else if (act.action === 'USE_UPGRADE') {
          eventType = 'ITEM';
          eventIcon = '⚡';
          entry.classList.add('type-upgrade');
          actionDesc = `<span class="${isHero ? 'log-actor-spider' : 'log-actor-opp'}">${actorName}</span> deployed <span class="log-upgrade">${act.useUpgrade}</span>`;
        }
      } else if (step.stage === 'PICK_UPGRADE') {
        eventType = 'DRAFT';
        eventIcon = '📦';
        entry.classList.add('type-draft');
        actionDesc = `<span class="${isHero ? 'log-actor-spider' : 'log-actor-opp'}">${actorName}</span> drafted module <span class="log-upgrade">${act.chosen_upgrade}</span>`;
      }

      entry.innerHTML = `
        <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 2px;">
          <div style="display: flex; align-items: center; gap: 6px;">
            <span style="font-size: 11px;">${eventIcon}</span>
            <span style="font-family: var(--font-hud); font-size: 10px; font-weight: 800; letter-spacing: 0.8px; color: var(--text-dim);">[${eventType}]</span>
          </div>
          <span style="font-family: var(--font-mono); font-size: 10px; font-weight: 700; color: var(--text-dim);">TURN ${idx + 1}</span>
        </div>
        <div style="font-size: 12px; color: var(--text-white);">${actionDesc}</div>
      `;

      stream.appendChild(entry);
    });
  }

  highlightActiveLogEntry(index) {
    const entries = this.dom.battleLogStream.querySelectorAll('.log-entry-row');
    entries.forEach((en, i) => {
      if (i === index) {
        en.classList.add('current-active');
        if (this.autoScroll) {
          en.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        }
      } else {
        en.classList.remove('current-active');
      }
    });
  }

  /* ========================================================================
     9. VICTORY MODAL & MATCH HELPERS
     ======================================================================== */
  showVictoryModal() {
    if (!this.summary) return;
    const sum = this.summary;
    const winnerSeat = sum.winner;
    const winnerName = this.getPlayerName(winnerSeat);
    const isPlayerWin = winnerSeat === 0;

    this.dom.victoryCard.className = `showdown-victory-card ${isPlayerWin ? 'victory' : 'defeat'}`;
    this.dom.victoryTrophyIcon.innerText = isPlayerWin ? '🕷️' : '💀';
    this.dom.victoryTitle.className = `victory-title ${isPlayerWin ? 'victory' : 'defeat'}`;
    this.dom.victoryTitle.innerText = isPlayerWin ? 'VICTORY!' : 'DEFEAT!';
    this.dom.victorySubtitle.innerText = isPlayerWin ? 'spider_sense emerged victorious!' : `${winnerName} won the match!`;

    this.dom.victoryStatsDetails.innerHTML = `
      MATCH ID: <b>${sum.match_id}</b><br>
      TOTAL DECISIONS: <b>${sum.actions}</b> // OUTCOME: <b>${sum.reason}</b><br>
      FINAL INTEGRITY: spider_sense [${sum.final_health ? sum.final_health[0] : 0}] vs Opponent [${sum.final_health && sum.final_health[1] !== undefined ? sum.final_health[1] : 0}]
    `;

    this.dom.modalVictory.classList.add('open');
  }

  getPrimaryOpponentSeat(obs, currentSeat) {
    if (currentSeat > 0 && obs.players[currentSeat]) {
      return currentSeat;
    }
    for (let i = 1; i < obs.players.length; i++) {
      if (obs.players[i].health > 0) return i;
    }
    return 1;
  }

  getPlayerName(seat) {
    if (this.summary && this.summary.seats && this.summary.seats[seat]) {
      return this.summary.seats[seat];
    }
    return seat === 0 ? 'spider_sense' : `random_bot_${seat}`;
  }

  /* ========================================================================
     10. MODALS: REPLAY PICKER & LIVE SIMULATION RUNNER
     ======================================================================== */
  openLibraryModal() {
    this.dom.modalLibrary.classList.add('open');
    const container = this.dom.matchPickerList;
    container.innerHTML = '';

    if (!this.matchesList || this.matchesList.length === 0) {
      container.innerHTML = '<div style="padding: 16px; text-align: center; color: var(--text-dim);">No replay logs available. Use "Load Log" button to upload a .jsonl file.</div>';
      return;
    }

    this.matchesList.slice(0, 50).forEach(m => {
      const row = document.createElement('div');
      row.className = 'match-picker-item';
      const winnerName = m.summary && m.summary.seats && m.summary.winner !== undefined
        ? m.summary.seats[m.summary.winner]
        : 'Completed';

      row.innerHTML = `
        <div>
          <div style="font-family: var(--font-mono); font-size: 12px; font-weight: 700; color: #fff;">${m.match_id}</div>
          <div style="font-size: 11px; color: var(--text-dim);">${m.path} (${m.actions} actions)</div>
        </div>
        <span class="status-condition-badge alive">Winner: ${winnerName}</span>
      `;

      row.addEventListener('click', () => {
        this.closeLibraryModal();
        this.loadMatchByPath(m.path);
      });

      container.appendChild(row);
    });
  }

  closeLibraryModal() {
    this.dom.modalLibrary.classList.remove('open');
  }

  openSimModal() {
    this.dom.modalSim.classList.add('open');
    this.dom.simSeedInput.value = Math.floor(Math.random() * 100000);
  }

  closeSimModal() {
    this.dom.modalSim.classList.remove('open');
  }

  async executeLiveSimulation() {
    const seed = parseInt(this.dom.simSeedInput.value, 10) || 42;
    const numPlayers = parseInt(this.dom.simPlayersSelect.value, 10) || 2;

    this.dom.simLoadingIcon.style.display = 'inline-block';
    this.dom.btnSubmitSim.disabled = true;

    try {
      const res = await fetch('/api/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ seed, num_players: numPlayers }),
      });

      if (!res.ok) throw new Error(`HTTP error ${res.status}`);
      const data = await res.json();

      this.closeSimModal();
      this.loadMatchFromRecords(data.records, data.match_id);
    } catch (err) {
      alert(`Simulation failed: ${err.message}. Ensure visualizer server.py is running.`);
    } finally {
      this.dom.simLoadingIcon.style.display = 'none';
      this.dom.btnSubmitSim.disabled = false;
    }
  }
}

// Instantiate App
document.addEventListener('DOMContentLoaded', () => {
  window.app = new ShowdownBattleApp();
});
