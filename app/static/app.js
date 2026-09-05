/* Nearby - progressive enhancement only. Every form works without this file. */
(function () {
  "use strict";

  var MAX_INTERESTS = 10;
  var PHOTO_EDGE = 640;      // longest side, px
  var PHOTO_QUALITY = 0.82;

  function $(sel) { return document.querySelector(sel); }
  function $$(sel) { return Array.prototype.slice.call(document.querySelectorAll(sel)); }

  /* --- interest picker: enforce the cap client-side too ------------------ */
  function wireInterests() {
    var boxes = $$('input[name="interests"]');
    var label = $("#interest-count");
    if (!boxes.length) return;

    function sync() {
      var checked = boxes.filter(function (b) { return b.checked; });
      boxes.forEach(function (b) {
        b.disabled = !b.checked && checked.length >= MAX_INTERESTS;
      });
      if (label) {
        label.textContent = checked.length + " of " + MAX_INTERESTS + " selected"
          + (checked.length < 3 ? " - pick at least 3" : "");
      }
    }
    boxes.forEach(function (b) { b.addEventListener("change", sync); });
    sync();
  }

  /* --- photo: resize in the browser, submit as a data URI --------------- */
  function wirePhoto() {
    var input = $("#photo-input");
    var hidden = $("#photo-data");
    var clear = $("#photo-clear");
    var preview = $(".photo-preview img") || $(".photo-row img");
    if (!input || !hidden) return;

    input.addEventListener("change", function () {
      var file = input.files && input.files[0];
      if (!file) return;
      if (!/^image\//.test(file.type)) {
        alert("Please choose an image file.");
        input.value = "";
        return;
      }
      var reader = new FileReader();
      reader.onload = function (e) {
        var img = new Image();
        img.onload = function () {
          var scale = Math.min(1, PHOTO_EDGE / Math.max(img.width, img.height));
          var w = Math.max(1, Math.round(img.width * scale));
          var h = Math.max(1, Math.round(img.height * scale));
          var canvas = document.createElement("canvas");
          canvas.width = w; canvas.height = h;
          canvas.getContext("2d").drawImage(img, 0, 0, w, h);
          var dataUri = canvas.toDataURL("image/jpeg", PHOTO_QUALITY);
          hidden.value = dataUri;
          $$(".photo-preview img, .photo-row img").forEach(function (el) {
            el.src = dataUri;
          });
        };
        img.onerror = function () { alert("That image couldn't be read."); };
        img.src = e.target.result;
      };
      reader.readAsDataURL(file);
    });

    if (clear) {
      clear.addEventListener("click", function () {
        hidden.value = "";
        input.value = "";
        if (preview) preview.src = preview.src.split("?")[0] + "?r=" + Date.now();
      });
    }
  }

  /* --- geolocation: fill the hidden lat/lng, save immediately ----------- */
  function wireGeo() {
    var btn = $("#geo-btn");
    var status = $("#geo-status");
    var latEl = $("#lat");
    var lngEl = $("#lng");
    if (!btn || !latEl || !lngEl) return;

    function say(msg) { if (status) status.textContent = msg; }

    btn.addEventListener("click", function () {
      if (!navigator.geolocation) {
        say("This browser can't share a location - pick a city instead.");
        return;
      }
      say("Asking your browser…");
      btn.disabled = true;
      navigator.geolocation.getCurrentPosition(function (pos) {
        var lat = pos.coords.latitude, lng = pos.coords.longitude;
        latEl.value = lat;
        lngEl.value = lng;
        var citySelect = document.querySelector('select[name="city"]');
        if (citySelect) citySelect.value = "";
        say("Got it: " + lat.toFixed(4) + ", " + lng.toFixed(4) + " - saving…");

        var token = (document.querySelector('input[name="csrf"]') || {}).value || "";
        fetch("/api/location", {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-CSRF-Token": token },
          body: JSON.stringify({ latitude: lat, longitude: lng })
        }).then(function (r) { return r.json(); }).then(function (data) {
          if (data && data.ok) {
            say("Saved.");
            var label = $("#loc-label");
            if (label) label.textContent = data.label;
          } else {
            say("Couldn't save that - submit the form to try again.");
          }
        }).catch(function () {
          say("Couldn't reach the server - submit the form to try again.");
        }).then(function () { btn.disabled = false; });
      }, function (err) {
        btn.disabled = false;
        say(err.code === 1
          ? "Permission denied - pick a city from the list instead."
          : "Couldn't get a fix - pick a city from the list instead.");
      }, { enableHighAccuracy: false, timeout: 10000, maximumAge: 300000 });
    });
  }

  function csrf() {
    var el = document.querySelector('input[name="csrf"]');
    return el ? el.value : "";
  }

  /* --- like / pass without a full page reload --------------------------- */
  function wireDecisions() {
    var forms = $$(".inline-form");
    if (!forms.length) return;

    forms.forEach(function (form) {
      form.addEventListener("submit", function (ev) {
        var btn = ev.submitter || form.querySelector("button[data-action]");
        if (!btn || !btn.dataset.action) return;      /* let it post normally */
        ev.preventDefault();

        var card = form.closest(".card");
        var userId = btn.dataset.user;
        form.querySelectorAll("button").forEach(function (b) { b.disabled = true; });

        fetch("/decide", {
          method: "POST",
          headers: {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "X-CSRF-Token": csrf()
          },
          body: "user_id=" + encodeURIComponent(userId)
              + "&action=" + encodeURIComponent(btn.dataset.action)
        }).then(function (r) { return r.json(); }).then(function (data) {
          if (!data || !data.ok) throw new Error("rejected");
          if (data.matched) showMatch(data);
          updateBadges(data);
          if (card) {
            card.style.transition = "opacity .18s ease, transform .18s ease";
            card.style.opacity = "0";
            card.style.transform = "scale(.97)";
            setTimeout(function () {
              var grid = card.parentNode;
              card.remove();
              if (grid && !grid.querySelector(".card")) window.location.reload();
            }, 180);
          }
        }).catch(function () {
          form.querySelectorAll("button").forEach(function (b) { b.disabled = false; });
          form.submit();                               /* fall back to a real post */
        });
      });
    });
  }

  function updateBadges(data) {
    var likeBadge = document.querySelector('a[href="/likes"] .nav-badge');
    if (likeBadge && typeof data.pending_likes === "number") {
      likeBadge.textContent = data.pending_likes;
      likeBadge.hidden = data.pending_likes === 0;
    }
  }

  function showMatch(data) {
    var el = document.createElement("div");
    el.className = "matchpop";
    el.innerHTML =
      '<div class="matchpop-card">'
      + (data.photo ? '<img class="avatar avatar-lg" src="' + data.photo + '" alt="">' : "")
      + "<h2>It's a match!</h2>"
      + "<p class=\"muted\">You and " + (data.name || "they") + " liked each other.</p>"
      + '<div class="actions">'
      + '<a class="btn" href="/chat/' + data.match_id + '">Send a message</a>'
      + '<button class="btn btn-ghost" type="button">Keep browsing</button>'
      + "</div></div>";
    el.addEventListener("click", function (ev) {
      if (ev.target === el || ev.target.tagName === "BUTTON") el.remove();
    });
    document.body.appendChild(el);
  }

  /* --- chat: send inline, poll for replies ------------------------------ */
  function wireChat() {
    var log = $("#chat-log");
    var form = $("#chat-form");
    var input = $("#chat-input");
    if (!log || !form || !input) return;

    var matchId = log.dataset.match;
    var lastId = parseInt(log.dataset.last || "0", 10);
    var me = null;

    function scroll() { log.scrollTop = log.scrollHeight; }

    function append(msg) {
      if (msg.id <= lastId) return;
      lastId = msg.id;
      var empty = log.querySelector(".chat-empty");
      if (empty) empty.remove();
      var div = document.createElement("div");
      div.className = "msg " + (me !== null && msg.sender_id === me ? "mine" : "theirs");
      div.dataset.id = msg.id;
      var p = document.createElement("p");
      p.textContent = msg.body;
      var t = document.createElement("time");
      t.textContent = "just now";
      div.appendChild(p); div.appendChild(t);
      log.appendChild(div);
      scroll();
    }

    form.addEventListener("submit", function (ev) {
      var body = input.value.trim();
      if (!body) return;
      ev.preventDefault();
      input.value = "";
      fetch("/chat/" + matchId, {
        method: "POST",
        headers: {
          "Content-Type": "application/x-www-form-urlencoded",
          "Accept": "application/json",
          "X-CSRF-Token": csrf()
        },
        body: "body=" + encodeURIComponent(body)
      }).then(function (r) { return r.json(); }).then(function (data) {
        if (data && data.message) { me = data.message.sender_id; append(data.message); }
      }).catch(function () { input.value = body; form.submit(); });
    });

    function poll() {
      fetch("/api/chat/" + matchId + "?after=" + lastId,
            { headers: { "Accept": "application/json" } })
        .then(function (r) { return r.json(); })
        .then(function (data) {
          if (!data || !data.ok) return;
          me = data.me;
          (data.messages || []).forEach(append);
        }).catch(function () { /* keep polling */ });
    }

    scroll();
    setInterval(poll, 4000);
    document.addEventListener("visibilitychange", function () {
      if (!document.hidden) poll();
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    wireInterests();
    wirePhoto();
    wireGeo();
    wireDecisions();
    wireChat();
  });
})();
