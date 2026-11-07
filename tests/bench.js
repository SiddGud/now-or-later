// Plays every benchmark rule card through both surveys (local copies, fake endpoint) and saves the posted rows.
// Shows what the lab benchmark will produce if everyone follows their card exactly.
// Usage: node tests/bench.js out.csv
var http = require('http');
var fs = require('fs');
var path = require('path');
var playwright = require('playwright');

var FAKE_ENDPOINT = 'https://script.google.com/macros/s/TEST_DEPLOYMENT/exec';
var ROOT = path.join(__dirname, '..');
var OUT_CSV = process.argv[2];
var PARALLEL = 8;

function readCards() {
  var lines = fs.readFileSync(path.join(ROOT, 'analysis', 'out', 'benchmark', 'cards.csv'), 'utf8').trim().split(/\r?\n/);
  var head = lines[0].split(',');
  var cards = [];
  for (var i = 1; i < lines.length; i++) {
    var cells = lines[i].split(',');
    var c = {};
    for (var j = 0; j < head.length; j++) { c[head[j]] = Number(cells[j]); }
    cards.push(c);
  }
  return cards;
}

function startServer() {
  var server = http.createServer(function (req, res) {
    var url = req.url.split('#')[0].split('?')[0];
    if (url === '/') { url = '/index.html'; }
    var file = path.join(ROOT, url);
    if (!fs.existsSync(file)) { res.writeHead(404); res.end(); return; }
    var body = fs.readFileSync(file, 'utf8').replace(/var ENDPOINT = '[^']*';/, "var ENDPOINT = '" + FAKE_ENDPOINT + "';");
    res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
    res.end(body);
  });
  return new Promise(function (resolve) { server.listen(0, function () { resolve(server); }); });
}

// Cutoff for an adaptive task from the card
function cutoff(card, survey, id, nudge) {
  if (id === 'nudge') {
    if (nudge === 'hiddenZero') { return card.nudge_hiddenZero; }
    return card.nudge_standard;
  }
  if (survey === 'proposal' && id === 'A_health') { return card.prop_flu; }
  return card[id];
}

async function play(browser, base, card, survey) {
  var ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
  var page = await ctx.newPage();
  var posted = null;
  await page.route(FAKE_ENDPOINT, async function (route) {
    posted = JSON.parse(route.request().postData());
    await route.fulfill({ status: 200, body: 'ok' });
  });
  var file = '/index.html';
  if (survey === 'proposal') { file = '/proposal.html'; }
  await page.goto(base + file + '#bench');
  var daily = Math.pow(card.d30, 1 / 30);
  var groups = await page.evaluate(function () {
    var g = { anchor: '', nudge: '' };
    if (typeof ANCHOR !== 'undefined') { g.anchor = ANCHOR; }
    if (typeof NUDGE !== 'undefined') { g.nudge = NUDGE; }
    return g;
  });
  var t1 = card.type1_gut_answers;
  var gut = { p1: 1, p2: 7, p3: 30, p4: 27 };
  var right = { p1: 2, p2: 8, p3: 29, p4: 0 };
  var order = ['p1', 'p2', 'p3', 'p4'];
  var guard = 0;
  while (!posted && guard < 3000) {
    guard += 1;
    await page.waitForTimeout(25);
    var st = await page.evaluate(function () {
      if (idx >= steps.length) { return { type: 'done' }; }
      var s = steps[idx];
      return { type: s.type, id: s.id, ctx: s.ctx, busy: busy };
    });
    if (st.type === 'done' || st.busy) { continue; }
    if (st.type === 'consent') { await page.click('#yes'); }
    else if (st.type === 'about') {
      await page.fill('#age', '21');
      var boxes = await page.$$('.row');
      for (var b = 0; b < boxes.length; b++) {
        var chips = await boxes[b].$$('.chip');
        await chips[0].click();
      }
      await page.click('#go');
    }
    else if (st.type === 'intro' || st.type === 'text' || st.type === 'upi') { await page.click('#go'); }
    else if (st.type === 'scale') { await page.click('#sc .chip >> nth=2'); }
    else if (st.type === 'adaptive') {
      // The offer is the largest rupee amount on the later option (hidden-zero wording also shows Rs 0); days tasks use the first number
      var txt = (await page.textContent('#ob')).replace(/,/g, '');
      var money = txt.match(/₹\d+/g);
      var L = 0;
      if (money) {
        for (var m = 0; m < money.length; m++) { L = Math.max(L, Number(money[m].slice(1))); }
      } else {
        L = Number(txt.match(/\d+/)[0]);
      }
      var c = cutoff(card, survey, st.id, groups.nudge);
      var cost = st.ctx === 'loss' || (survey === 'proposal' && st.ctx === 'health');
      var later = L >= c;
      if (cost) { later = L < c; }
      if (later) { await page.click('#ob'); } else { await page.click('#oa'); }
    }
    else if (st.type === 'number') {
      var v = 0;
      if (st.id === 'anchorAmount') {
        v = card.anchor_low_amount;
        if (groups.anchor === 'high') { v = card.anchor_high_amount; }
      } else {
        v = right[st.id];
        if (order.indexOf(st.id) < t1) { v = gut[st.id]; }
      }
      await page.fill('#num', String(v));
      await page.click('#go');
    }
    else if (st.type === 'choice' || st.type === 'anchor') {
      // Index 1 is the later / second option
      var pickSecond = false;
      if (st.id === 'flipNear') {
        if (survey === 'proposal') { pickSecond = card.beta * daily * 110 > 100; } else { pickSecond = card.beta * Math.pow(daily, 7) * 1100 > 1000; }
      } else if (st.id === 'flipFar') {
        if (survey === 'proposal') { pickSecond = daily * 110 > 100; } else { pickSecond = Math.pow(daily, 7) * 1100 > 1000; }
      } else if (st.id === 'attn1' || st.id === 'attn2') {
        pickSecond = false;
      } else if (st.type === 'anchor' || st.id === 'anchorYes') {
        if (groups.anchor === 'high') { pickSecond = !(15000 >= card.anchor_high_amount); } else { pickSecond = !(5200 >= card.anchor_low_amount); }
      } else if (st.id === 'p5') {
        pickSecond = t1 >= 5;
      }
      var idxOpt = 0;
      if (pickSecond) { idxOpt = 1; }
      await page.click('.opt >> nth=' + idxOpt);
    }
  }
  await ctx.close();
  return posted;
}

function toCsv(rows) {
  var cols = [];
  for (var i = 0; i < rows.length; i++) {
    var keys = Object.keys(rows[i]);
    for (var k = 0; k < keys.length; k++) { if (cols.indexOf(keys[k]) === -1) { cols.push(keys[k]); } }
  }
  var out = [cols.join(',')];
  for (var r = 0; r < rows.length; r++) {
    var cells = [];
    for (var c = 0; c < cols.length; c++) {
      var v = rows[r][cols[c]];
      if (v === undefined || v === null) { v = ''; }
      cells.push('"' + String(v).replace(/"/g, '""') + '"');
    }
    out.push(cells.join(','));
  }
  return out.join('\n');
}

(async function () {
  var cards = readCards();
  var server = await startServer();
  var base = 'http://127.0.0.1:' + server.address().port;
  var browser = await playwright.chromium.launch();
  var jobs = [];
  for (var i = 0; i < cards.length; i++) { jobs.push([cards[i], 'main'], [cards[i], 'proposal']); }
  var rows = [];
  var missing = 0;
  var n = 0;
  async function worker() {
    while (n < jobs.length) {
      var job = jobs[n];
      n += 1;
      var row = await play(browser, base, job[0], job[1]);
      if (row) {
        row.receivedAt = new Date().toISOString();
        // Which card the row came from
        row.benchPerson = job[0].person;
        rows.push(row);
      } else { missing += 1; }
    }
  }
  var workers = [];
  for (var w = 0; w < PARALLEL; w++) { workers.push(worker()); }
  await Promise.all(workers);
  await browser.close();
  server.close();
  fs.writeFileSync(OUT_CSV, toCsv(rows));
  console.log('Played ' + rows.length + ' of ' + jobs.length + ' (missing ' + missing + '), saved ' + OUT_CSV);
})();
