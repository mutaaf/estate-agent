/* The adoption ladder, made clickable.
 *
 * Two things happen here. You can walk the five levels and read what each one
 * actually gets you — written for someone who has never used an AI coding
 * agent. And you can answer four yes/no questions and be told where you are
 * and the single next thing to do, which is more useful than a feature list
 * to somebody deciding whether any of this is worth their afternoon.
 *
 * The level data is injected by the page as JSON, so it comes from the same
 * definition the documentation uses and the two cannot drift.
 *
 * No dependencies, no build step. */

(function () {
  "use strict";

  var root = document.getElementById("levels-explorer");
  if (!root) return;

  var DATA = window.ESTATE_LEVELS || {};
  var LEVELS = DATA.levels || [];
  var QUESTIONS = DATA.questions || [];
  var NEXT = DATA.next || {};
  if (!LEVELS.length) return;

  var state = { open: 1, answers: {}, assessed: false };

  function esc(text) {
    return String(text).replace(/[&<>]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c];
    });
  }

  function reached() {
    // You are at the highest level whose question you answered yes to, and
    // every level below it. Answering yes to "can you ask what breaks" while
    // having no context files is not level 3 - the ladder is cumulative.
    var level = 0;
    for (var i = 0; i < QUESTIONS.length; i++) {
      if (state.answers[QUESTIONS[i].id] === true) level = QUESTIONS[i].level;
      else break;
    }
    return level;
  }

  function renderLadder() {
    return LEVELS.map(function (level) {
      var open = state.open === level.number;
      var here = state.assessed && reached() === level.number;
      var done = state.assessed && reached() > level.number;

      var body = "";
      if (open) {
        body += '<div class="level-body">';
        body += "<p>" + esc(level.plain) + "</p>";

        if (level.you_get.length) {
          body += "<h4>What you get</h4><ul>";
          body += level.you_get.map(function (item) {
            return "<li>" + esc(item) + "</li>";
          }).join("");
          body += "</ul>";
        }
        if (level.still_wrong.length) {
          body += "<h4>What is still wrong here</h4><ul class=\"gap\">";
          body += level.still_wrong.map(function (item) {
            return "<li>" + esc(item) + "</li>";
          }).join("");
          body += "</ul>";
        }
        body += '<div class="level-facts">';
        body += "<div><span>Cost</span>" + esc(level.cost) + "</div>";
        if (level.command) {
          body += "<div><span>How</span><code>" + esc(level.command) + "</code></div>";
        }
        body += "<div><span>You are here when</span>" + esc(level.check) + "</div>";
        body += "<div><span>Who it is for</span>" + esc(level.who) + "</div>";
        body += "</div></div>";
      }

      return (
        '<li class="level' + (open ? " open" : "") +
        (here ? " here" : "") + (done ? " done" : "") + '">' +
        '<button class="level-head" data-level="' + level.number +
        '" aria-expanded="' + open + '">' +
        '<span class="level-no">' + level.number + "</span>" +
        '<span class="level-title"><strong>' + esc(level.name) + "</strong>" +
        '<span class="level-tag">' + esc(level.tagline) + "</span></span>" +
        (here ? '<span class="badge">you are here</span>' : "") +
        (done ? '<span class="badge done">done</span>' : "") +
        "</button>" + body + "</li>"
      );
    }).join("");
  }

  function renderQuiz() {
    var rows = QUESTIONS.map(function (question, index) {
      var answer = state.answers[question.id];
      var locked = index > 0 && state.answers[QUESTIONS[index - 1].id] !== true;
      return (
        '<div class="q' + (locked ? " locked" : "") + '">' +
        '<p class="q-ask">' + esc(question.ask) +
        '<span class="q-hint">' + esc(question.hint) + "</span></p>" +
        '<div class="q-buttons">' +
        '<button data-q="' + question.id + '" data-a="yes"' +
        (answer === true ? ' class="on"' : "") + ">Yes</button>" +
        '<button data-q="' + question.id + '" data-a="no"' +
        (answer === false ? ' class="on"' : "") + ">No</button>" +
        "</div></div>"
      );
    }).join("");

    var verdict = "";
    if (state.assessed) {
      var level = reached();
      var found = LEVELS[level] || LEVELS[0];
      var step = NEXT[String(level)] || ["", ""];
      verdict =
        '<div class="verdict">' +
        "<p><strong>You are at level " + level + " — " +
        esc(found.name) + ".</strong></p>" +
        "<p class=\"next-title\">" + esc(step[0]) + "</p>" +
        "<p>" + step[1] + "</p>" +
        "</div>";
    }

    return (
      '<div class="quiz"><h3>Where are you now?</h3>' +
      '<p class="quiz-intro">Four questions. Answer honestly — the useful ' +
      "answer is the next step, not the score.</p>" +
      rows + verdict + "</div>"
    );
  }

  function render() {
    root.innerHTML =
      '<ol class="ladder">' + renderLadder() + "</ol>" + renderQuiz();
  }

  root.addEventListener("click", function (event) {
    var head = event.target.closest && event.target.closest(".level-head");
    if (head) {
      var number = parseInt(head.getAttribute("data-level"), 10);
      state.open = state.open === number ? -1 : number;
      render();
      return;
    }
    var button = event.target.closest && event.target.closest("[data-q]");
    if (button) {
      var id = button.getAttribute("data-q");
      var yes = button.getAttribute("data-a") === "yes";
      state.answers[id] = yes;
      // Answering no ends the ladder: everything above is unanswered.
      if (!yes) {
        var past = false;
        QUESTIONS.forEach(function (question) {
          if (past) delete state.answers[question.id];
          if (question.id === id) past = true;
        });
      }
      state.assessed = true;
      state.open = reached();
      render();
    }
  });

  render();
})();
