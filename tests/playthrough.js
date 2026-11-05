// Plays the full app many times on a 390x844 phone viewport and checks the posted data.
// Usage: node tests/playthrough.js [runs]   (default 80)
var http = require('http');
var fs = require('fs');
var path = require('path');
var playwright = require('playwright');

var RUNS = Number(process.argv[2] || 80);
var PARALLEL = 8;
var FAKE_ENDPOINT = 'https://script.google.com/macros/s/TEST_DEPLOYMENT/exec';
var ROOT = path.join(__dirname, '..');

var REQUIRED = [
  'id', 'order', 'nudgeGroup', 'anchorGroup', 'startedAt', 'consent', 'age', 'describes', 'spending',
  'priorKnowledge', 'otherSurvey', 'stress', 'trust', 'flipNear', 'flipNear_rt',
  'attn1', 'attn2', 'anchorYes', 'anchorAmount', 'flipFar', 'procrast', 'regret', 'comment',
  'p1', 'p2', 'p3', 'p4', 'p5', 'p1_rt', 'p2_rt', 'p3_rt', 'p4_rt', 'p5_rt', 'upi',
  'type1Score', 'correctScore', 'flipped', 'attentionFail', 'finishedAt', 'totalSec', 'device', 'trialsJSON'
];
var TASKS = ['A_gain', 'A_loss', 'A_health', 'A_friend', 'B_gain', 'B_loss', 'B_health', 'B_friend', 'nudge'];
var SUFFIXES = ['_ind', '_k', '_censored', '_meanRT'];
for (var ti = 0; ti < TASKS.length; ti++) {
  for (var si = 0; si < SUFFIXES.length; si++) { REQUIRED.push(TASKS[ti] + SUFFIXES[si]); }
}

// Range of each task, mirroring PROJECT_CONTEXT.md
function spec(taskId) {
  if (taskId.indexOf('health') !== -1) { return { V: 20, lo: 20, hi: 50, step: 1 }; }
  if (taskId === 'nudge') { return { V: 2000, lo: 2000, hi: 5000, step: 10 }; }
  return { V: 500, lo: 500, hi: 1250, step: 5 };
}

function pick(arr) { return arr[Math.floor(Math.random() * arr.length)]; }
function randInt(a, b) { return a + Math.floor(Math.random() * (b - a + 1)); }

// Serves the project folder, with ENDPOINT swapped for the fake URL
function startServer() {
  var server = http.createServer(function (req, res) {
    var url = req.url.split('#')[0].split('?')[0];
    if (url === '/') { url = '/index.html'; }
    var file = path.join(ROOT, url);
    if (!fs.existsSync(file)) { res.writeHead(404); res.end(); return; }
    var body = fs.readFileSync(file, 'utf8');
    if (url === '/index.html') { body = body.replace("'PASTE_YOUR_WEB_APP_URL_HERE'", "'" + FAKE_ENDPOINT + "'"); }
    res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
    res.end(body);
  });
  return new Promise(function (resolve) {
    server.listen(0, function () { resolve(server); });
  });
}

// Plays one full survey; mode 'random' or 'consistent' (a respondent with a fixed switch point per task)
async function playOnce(browser, base, mode, hash) {
  var ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
  var page = await ctx.newPage();
  var errors = [];
  page.on('console', function (m) { if (m.type() === 'error') { errors.push(m.text()); } });
  page.on('pageerror', function (e) { errors.push(String(e)); });
  var posted = null;
  await page.route(FAKE_ENDPOINT, async function (route) {
    posted = JSON.parse(route.request().postData());
    await route.fulfill({ status: 200, body: 'ok' });
  });
  await page.goto(base + '/index.html' + (hash || ''));

  // Hidden true switch point per task for the consistent respondent
  var truth = {};
  var pcts = [];
  var doubleTapped = false;
  var guard = 0;
  while (!posted && guard < 300) {
    guard += 1;
    await page.waitForTimeout(30);
    var st = await page.evaluate(function () {
      if (idx >= steps.length) { return { type: 'done' }; }
      var s = steps[idx];
      return { type: s.type, id: s.id, ctx: s.ctx, frame: s.frame, min: s.min, max: s.max, options: s.options, pct: document.getElementById('pct').textContent, busy: busy };
    });
    if (st.type === 'done') { await page.waitForTimeout(100); continue; }
    if (st.busy) { continue; }
    pcts.push(parseInt(st.pct, 10));
    if (st.type === 'consent') { await page.click('#yes'); }
    else if (st.type === 'about') {
      await page.fill('#age', String(randInt(18, 70)));
      var groups = ['#c_desc', '#c_spend', '#c_prior', '#c_other', '#c_stress', '#c_trust'];
      for (var g = 0; g < groups.length; g++) {
        // Spending is optional: sometimes skip it
        if (groups[g] === '#c_spend' && Math.random() < 0.3) { continue; }
        var chips = await page.$$(groups[g] + ' .chip');
        await pick(chips).click();
      }
      await page.click('#go');
    }
    else if (st.type === 'intro') { await page.click('#go'); }
    else if (st.type === 'choice' || st.type === 'anchor') {
      var opts = await page.$$('.opt');
      var o = pick(opts);
      // Once per run, try a fast double tap to check it cannot answer twice
      if (!doubleTapped) { doubleTapped = true; await o.dblclick(); } else { await o.click(); }
    }
    else if (st.type === 'adaptive') {
      var offerTxt = await page.textContent('#ob');
      var sp = spec(st.id);
      var later;
      if (mode === 'consistent') {
        if (truth[st.id] === undefined) { truth[st.id] = sp.lo + Math.random() * (sp.hi - sp.lo); }
        var nums = offerTxt.replace(/,/g, '').match(/\d+/g);
        var L = Number(nums[0]);
        if (st.id === 'nudge' && nums.length > 1) { L = Math.max.apply(null, nums.map(Number)); }
        if (st.ctx === 'loss') {
          // Postpone only while the later fine is still below the personal switch point
          later = L < truth[st.id];
        } else {
          later = L >= truth[st.id];
        }
      } else {
        later = Math.random() < 0.5;
      }
      var target = '#oa';
      if (later) { target = '#ob'; }
      await page.click(target);
    }
    else if (st.type === 'number') {
      var v;
      if (st.id === 'anchorAmount') { v = randInt(5000, 100000); }
      else if (st.id === 'p1') { v = pick([4, 9, 6]); }
      else if (st.id === 'p2') { v = pick([9, 5, 10]); }
      else if (st.id === 'p3') { v = pick([36, 40, 30]); }
      else { v = pick([7000, 10000, 6000]); }
      await page.fill('#num', String(v));
      await page.click('#go');
    }
    else if (st.type === 'scale') { var sc = await page.$$('#sc .chip'); await pick(sc).click(); }
    else if (st.type === 'text') {
      if (Math.random() < 0.5) { await page.fill('#tx', 'thought about it'); }
      await page.click('#go');
    }
    else if (st.type === 'upi') {
      if (Math.random() < 0.7) { await page.fill('#upi', 'tester' + randInt(1, 999) + '@okaxis'); }
      await page.click('#go');
    }
  }
  if (posted) { await page.waitForSelector('#share'); }
  await ctx.close();
  return { posted: posted, errors: errors, truth: truth, pcts: pcts, mode: mode };
}

// Replays one task's taps with the bisection rule from PROJECT_CONTEXT.md
function replay(taskId, taps) {
  var sp = spec(taskId);
  var lo = sp.lo;
  var hi = sp.hi;
  for (var i = 0; i < taps.length; i++) {
    var t = taps[i];
    if (taskId.indexOf('loss') !== -1) {
      if (t.choice === 'later') { lo = t.offer; } else { hi = t.offer; }
    } else {
      if (t.choice === 'later') { hi = t.offer; } else { lo = t.offer; }
    }
  }
  return { lo: lo, hi: hi, ind: (lo + hi) / 2 };
}

function checkRun(r, problems) {
  var d = r.posted;
  var tag = '[' + (d && d.id) + ' ' + r.mode + '] ';
  if (!d) { problems.push(tag + 'no POST captured'); return; }
  if (r.errors.length) { problems.push(tag + 'console errors: ' + r.errors.join(' | ')); }
  for (var i = 0; i < REQUIRED.length; i++) {
    if (!(REQUIRED[i] in d)) { problems.push(tag + 'missing field ' + REQUIRED[i]); }
  }
  var taps = JSON.parse(d.trialsJSON);
  for (var t = 0; t < TASKS.length; t++) {
    var id = TASKS[t];
    var sp = spec(id);
    var mine = taps.filter(function (x) { return x.step === id; });
    if (mine.length !== 5) { problems.push(tag + id + ' has ' + mine.length + ' taps, expected 5'); continue; }
    var seen = {};
    for (var m = 0; m < mine.length; m++) {
      // Interval before this tap; when it is one step wide no new interior offer exists (health only)
      var before = replay(id, mine.slice(0, m));
      var degenerate = before.hi - before.lo <= sp.step;
      var inside = mine[m].offer > sp.lo && mine[m].offer < sp.hi;
      if (!inside && !(degenerate && mine[m].offer >= sp.lo && mine[m].offer <= sp.hi)) { problems.push(tag + id + ' offer out of range ' + mine[m].offer); }
      if (seen[mine[m].offer] && !degenerate) { problems.push(tag + id + ' repeated offer ' + mine[m].offer); }
      if (!(mine[m].offer >= before.lo && mine[m].offer <= before.hi)) { problems.push(tag + id + ' offer ' + mine[m].offer + ' outside current interval'); }
      seen[mine[m].offer] = true;
    }
    var rep = replay(id, mine);
    var ind = d[id + '_ind'];
    var k = d[id + '_k'];
    if (Math.abs(rep.ind - ind) > 1e-9) { problems.push(tag + id + ' ind ' + ind + ' != replay ' + rep.ind); }
    if (!(ind >= sp.lo && ind <= sp.hi)) { problems.push(tag + id + ' ind out of bounds ' + ind); }
    var kMax = (sp.hi / sp.V - 1) / 30;
    if (!(k >= 0 && k <= kMax + 1e-9)) { problems.push(tag + id + ' k out of bounds ' + k); }
    if (Math.abs(k - (ind / sp.V - 1) / 30) > 1e-4) { problems.push(tag + id + ' k does not match ind'); }
    if (['no', 'high', 'low'].indexOf(d[id + '_censored']) === -1) { problems.push(tag + id + ' bad censored ' + d[id + '_censored']); }
    if (r.mode === 'consistent') {
      // Five halvings of the range plus rounding: the estimate must land near the true switch point
      var tolerance = (sp.hi - sp.lo) / 32 + sp.step;
      if (Math.abs(ind - r.truth[id]) > tolerance) { problems.push(tag + id + ' ind ' + ind + ' far from true ' + r.truth[id].toFixed(1)); }
      var allSooner = mine.every(function (x) { return x.choice === 'sooner'; });
      var allLater = mine.every(function (x) { return x.choice === 'later'; });
      var expectHigh = allSooner;
      var expectLow = allLater;
      if (id.indexOf('loss') !== -1) { expectHigh = allLater; expectLow = allSooner; }
      if (expectHigh && d[id + '_censored'] !== 'high') { problems.push(tag + id + ' should be censored high'); }
      if (expectLow && d[id + '_censored'] !== 'low') { problems.push(tag + id + ' should be censored low'); }
    }
  }
  // Single-tap steps must appear exactly once (double tap protection)
  var singles = ['flipNear', 'attn1', 'attn2', 'anchorYes', 'flipFar', 'procrast', 'regret', 'p5'];
  for (var s = 0; s < singles.length; s++) {
    var c = taps.filter(function (x) { return x.step === singles[s]; }).length;
    if (c !== 1) { problems.push(tag + singles[s] + ' tapped ' + c + ' times'); }
  }
  if (!(d.age >= 18 && d.age <= 70)) { problems.push(tag + 'age out of range'); }
  if (!(d.anchorAmount >= 5000 && d.anchorAmount <= 100000)) { problems.push(tag + 'anchorAmount out of range'); }
  if (!(d.type1Score >= 0 && d.type1Score <= 5 && d.correctScore >= 0 && d.type1Score + d.correctScore <= 5)) { problems.push(tag + 'bad puzzle scores'); }
  for (var p = 1; p < r.pcts.length; p++) {
    if (r.pcts[p] < r.pcts[p - 1]) { problems.push(tag + 'progress went backwards ' + r.pcts[p - 1] + ' -> ' + r.pcts[p]); break; }
  }
  var lastPct = r.pcts[r.pcts.length - 1];
  if (!(lastPct >= 97 && lastPct <= 100)) { problems.push(tag + 'progress on last screen was ' + lastPct + '%'); }
}

// Two-sided check that a 50/50 split is plausible (|z| < 3.29, p > 0.001)
function balanced(name, counts, n, problems, lines) {
  var keys = Object.keys(counts);
  var a = counts[keys[0]] || 0;
  var z = (a - n / 2) / Math.sqrt(n / 4);
  lines.push(name + ': ' + JSON.stringify(counts) + ' z=' + z.toFixed(2));
  if (keys.length !== 2 || Math.abs(z) > 3.29) { problems.push('unbalanced ' + name + ' ' + JSON.stringify(counts)); }
}

// One-play lock, #test bypass, and retry of a failed POST
async function lockAndRetry(browser, base, problems) {
  var ctx = await browser.newContext({ viewport: { width: 390, height: 844 } });
  var page = await ctx.newPage();
  var bodies = [];
  var fail = true;
  await page.route(FAKE_ENDPOINT, async function (route) {
    if (fail) { await route.abort(); return; }
    bodies.push(JSON.parse(route.request().postData()));
    await route.fulfill({ status: 200, body: 'ok' });
  });
  await page.goto(base + '/index.html');
  // Jump straight to the end to make a finished response quickly
  await page.evaluate(function () {
    data.consent = 'yes';
    var fake = { ind: 800, k: 0.02 };
    results.A_gain = fake; results.B_gain = fake; results.A_friend = fake; results.A_health = { ind: 30, k: 0.016 }; results.A_loss = fake;
    idx = steps.length - 1;
    render();
  });
  await page.click('#go');
  await page.waitForSelector('#share');
  await page.waitForTimeout(300);
  var queued = await page.evaluate(function () { return Object.keys(readQueue()); });
  var firstId = await page.evaluate(function () { return data.id; });
  if (queued.indexOf(firstId) === -1) { problems.push('failed POST was not kept in the queue'); }

  fail = false;
  await page.reload();
  await page.waitForTimeout(500);
  var text = await page.textContent('#app');
  if (text.indexOf('already played') === -1) { problems.push('lock screen not shown on second visit'); }
  if (bodies.length !== 1 || bodies[0].id !== firstId) { problems.push('queued response was not retried on reload (got ' + bodies.length + ')'); }
  var left = await page.evaluate(function () { return Object.keys(readQueue()).length; });
  if (left !== 0) { problems.push('queue not cleared after retry'); }

  await page.goto(base + '/index.html#test');
  await page.reload();
  await page.waitForTimeout(300);
  var hasYes = await page.$('#yes');
  if (!hasYes) { problems.push('#test did not bypass the lock'); }
  var testFlag = await page.evaluate(function () { return data.test; });
  if (testFlag !== 'yes') { problems.push('#test run not flagged test=yes'); }
  await ctx.close();
}

// With the placeholder ENDPOINT nothing is sent and the response stays queued
async function placeholderCheck(browser, base, problems) {
  var ctx = await browser.newContext();
  var page = await ctx.newPage();
  var sent = 0;
  await page.route('**/*', function (route) {
    if (route.request().method() === 'POST') { sent += 1; }
    route.continue();
  });
  await page.goto(base + '/index.html');
  await page.evaluate(function () {
    ENDPOINT = 'PASTE_YOUR_WEB_APP_URL_HERE';
    send();
  });
  await page.waitForTimeout(300);
  var n = await page.evaluate(function () { return Object.keys(readQueue()).length; });
  if (sent !== 0) { problems.push('POST sent while ENDPOINT is a placeholder'); }
  if (n !== 1) { problems.push('placeholder response not kept in queue'); }
  await ctx.close();
}

function csvCell(v) {
  if (v === undefined || v === null) { return ''; }
  var s = String(v);
  if (/[",\n]/.test(s)) { s = '"' + s.replace(/"/g, '""') + '"'; }
  return s;
}

function saveCsv(file, posted) {
  var cols = [];
  for (var i = 0; i < posted.length; i++) {
    var keys = Object.keys(posted[i].posted);
    for (var j = 0; j < keys.length; j++) { if (cols.indexOf(keys[j]) === -1) { cols.push(keys[j]); } }
  }
  cols.push('receivedAt');
  var lines = [cols.join(',')];
  for (var r = 0; r < posted.length; r++) {
    var row = posted[r].posted;
    row.receivedAt = new Date().toISOString();
    var cells = [];
    for (var c = 0; c < cols.length; c++) { cells.push(csvCell(row[cols[c]])); }
    lines.push(cells.join(','));
  }
  fs.writeFileSync(file, lines.join('\n'));
}

async function main() {
  var server = await startServer();
  var base = 'http://localhost:' + server.address().port;
  var browser = await playwright.chromium.launch();
  var problems = [];
  var results = [];
  var started = Date.now();
  var next = 0;

  async function worker() {
    while (next < RUNS) {
      var i = next;
      next += 1;
      var mode = 'random';
      if (i % 2 === 1) { mode = 'consistent'; }
      // Every run uses #test so the lock never blocks a fresh context
      results.push(await playOnce(browser, base, mode, '#test'));
    }
  }
  var pool = [];
  for (var w = 0; w < PARALLEL; w++) { pool.push(worker()); }
  await Promise.all(pool);

  for (var i = 0; i < results.length; i++) { checkRun(results[i], problems); }
  var lines = [];
  var groups = { order: {}, nudgeGroup: {}, anchorGroup: {} };
  var posted = results.filter(function (r) { return r.posted; });
  for (var j = 0; j < posted.length; j++) {
    var gk = Object.keys(groups);
    for (var q = 0; q < gk.length; q++) {
      var v = posted[j].posted[gk[q]];
      groups[gk[q]][v] = (groups[gk[q]][v] || 0) + 1;
    }
  }
  var names = Object.keys(groups);
  for (var b = 0; b < names.length; b++) { balanced(names[b], groups[names[b]], posted.length, problems, lines); }

  await lockAndRetry(browser, base, problems);
  await placeholderCheck(browser, base, problems);
  await browser.close();
  server.close();

  // Saves the posted rows as a Sheet-like CSV, for checking analysis/analyze.py (gitignored)
  if (process.env.SAVE_CSV) { saveCsv(process.env.SAVE_CSV, posted); }
  var fieldCount = 0;
  if (posted.length) { fieldCount = Object.keys(posted[0].posted).length; }
  console.log('Runs: ' + results.length + ', posted: ' + posted.length + ', fields per row: ' + fieldCount + ', time: ' + Math.round((Date.now() - started) / 1000) + 's');
  for (var l = 0; l < lines.length; l++) { console.log(lines[l]); }
  if (problems.length) {
    console.log('\nFAILED (' + problems.length + ' problems):');
    for (var p = 0; p < Math.min(problems.length, 40); p++) { console.log(' - ' + problems[p]); }
    process.exit(1);
  }
  console.log('\nALL CHECKS PASSED');
}

main().catch(function (e) { console.error(e); process.exit(1); });
