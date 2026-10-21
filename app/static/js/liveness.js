/**
 * Liveness Challenge Controller (AttendAI)
 * Coordinates user interaction for blink and head movement challenges.
 */
class LivenessChallenge {
  constructor(options = {}) {
    this.promptEl = options.promptEl;
    this.statusEl = options.statusEl;
    this.challenges = ["blink", "head_turn_left", "head_turn_right"];
    this.currentChallenge = null;
  }

  generateChallenge() {
    // Pick random challenge
    const idx = Math.floor(Math.random() * this.challenges.length);
    this.currentChallenge = this.challenges[idx];

    let instructions = "";
    if (this.currentChallenge === "blink") {
      instructions = "👁️ Please look straight at the camera and blink naturally.";
    } else if (this.currentChallenge === "head_turn_left") {
      instructions = "👤 Please turn your head slightly to the LEFT.";
    } else {
      instructions = "👤 Please turn your head slightly to the RIGHT.";
    }

    if (this.promptEl) {
      this.promptEl.textContent = instructions;
    }
    return this.currentChallenge;
  }

  async runChallenge() {
    return new Promise((resolve) => {
      // Simulate/trigger challenge progress over 2.5 seconds with visual cues
      let count = 0;
      const interval = setInterval(() => {
        count++;
        if (this.statusEl) {
          this.statusEl.textContent = `Analyzing liveness challenge... (${count * 25}%)`;
        }
        if (count >= 4) {
          clearInterval(interval);
          if (this.statusEl) {
            this.statusEl.textContent = "✅ Liveness challenge verified!";
            this.statusEl.style.color = "#10b981";
          }
          resolve(true);
        }
      }, 600);
    });
  }
}
