// Live timer display + idle-detection banner. Display-only: all state
// changes go through normal form POSTs.
(function () {
  var clock = document.querySelector(".js-elapsed");
  if (!clock) return;

  var startedEpoch = parseInt(clock.dataset.startedEpoch, 10) * 1000;
  var banner = document.getElementById("idle-banner");
  var card = document.querySelector(".timer-card");
  var entryId = card ? card.dataset.entryId : "";
  var dismissKey = "idle-dismissed-" + entryId;

  function pad(n) { return n < 10 ? "0" + n : "" + n; }

  function longFormat(totalSeconds) {
    var h = Math.floor(totalSeconds / 3600);
    var m = Math.floor((totalSeconds % 3600) / 60);
    return h + "h " + pad(m) + "m";
  }

  function tick() {
    var elapsed = Math.max(0, Math.floor((Date.now() - startedEpoch) / 1000));
    var h = Math.floor(elapsed / 3600);
    var m = Math.floor((elapsed % 3600) / 60);
    var s = elapsed % 60;
    clock.textContent = h + ":" + pad(m) + ":" + pad(s);

    if (banner) {
      var threshold = parseInt(banner.dataset.idleThreshold, 10);
      var longEl = banner.querySelector(".js-elapsed-long");
      if (longEl) longEl.textContent = longFormat(elapsed);
      if (elapsed > threshold && !sessionStorage.getItem(dismissKey)) {
        banner.classList.remove("hidden");
      }
    }
  }

  var dismiss = document.getElementById("idle-dismiss");
  if (dismiss) {
    dismiss.addEventListener("click", function () {
      sessionStorage.setItem(dismissKey, "1");
      banner.classList.add("hidden");
    });
  }

  // If the server already flagged idle but the user dismissed it this tab
  // session, keep it hidden on reload.
  if (banner && sessionStorage.getItem(dismissKey)) {
    banner.classList.add("hidden");
  }

  tick();
  setInterval(tick, 1000);
})();
