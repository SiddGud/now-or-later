// Plays the short proposal survey (proposal.html) many times on a 390x844 phone viewport and checks the posted data.
// Usage: node tests/proposal.js [runs]   (default 60)
var http = require('http');
var fs = require('fs');
var path = require('path');
var playwright = require('playwright');

var RUNS = Number(process.argv[2] || 60);
var PARALLEL = 8;
var FAKE_ENDPOINT = 'https://script.google.com/macros/s/TEST_DEPLOYMENT/exec';
var ROOT = path.join(__dirname, '..');
var TASKS = ['A_gain', 'A_loss', 'A_health', 'A_friend'];
var REQUIRED = ['id', 'survey', 'version', 'flipOrder', 'startedAt', 'test', 'consent', 'age', 'year', 'field',
  'flipNear', 'flipNear_rt', 'flipFar', 'flipFar_rt', 'attn1', 'attn1_rt', 'upi', 'flipped', 'reverseFlip',
  'attentionFail', 'finishedAt', 'totalSec', 'device', 'trialsJSON'];
for (var ti = 0; ti < TASKS.length; ti++) {
  REQUIRED.push(TASKS[ti] + '_ind', TASKS[ti] + '_k', TASKS[ti] + '_censored', TASKS[ti] + '_meanRT');
}

// Range of each task, mirroring proposal.html
function spec(taskId) {
  if (taskId === 'A_health') { return { V: 10, lo: 10, hi: 25, step: 1, cost: true }; }
  if (taskId === 'A_loss') { return { V: 500, lo: 500, hi: 1250, step: 5, cost: true }; }
  return { V: 500, lo: 500, hi: 1250, step: 5, cost: false };
}

function pick(arr) { return arr[Math.floor(Math.random() * arr.length)]; }
function randInt(a, b) { return a + Math.floor(Math.random() * (b - a + 1)); }

function startServer() {
  var server = http.createServer(function (req, res) {
    var url = req.url.split('#')[0].split('?')[0];
    var file = path.join(ROOT, url);
    if (!fs.existsSync(file)) { res.writeHead(404); res.end(); return; }
    var body = fs.readFileSync(file, 'utf8');
    // Tests never write to the real Sheet
    body = body.replace(/var ENDPOINT = '[^']*';/, "var ENDPOINT = '" + FAKE_ENDPOINT + "';");
    res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
    res.end(body);
  });
  return new Promise(function (resolve) { server.listen(0, function () { resolve(server); }); });
}

async function playOnce(browser, base, mode) {
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
  await page.goto(base + '/proposal.html#test');
  var truth = {};
  var pcts = [];
  var guard = 0;
  while (!posted && guard < 2000) {
    guard += 1;
    await page.waitForTimeout(30);
    var st = await page.evaluate(function () {
      if (idx >= steps.length) { return { type: 'done' }; }
      var s = steps[idx];
      return { type: s.type, id: s.id, pct: document.getElementById('pct').textContent, busy: busy };
    });
    if (st.type === 'done' || st.busy) { continue; }
    pcts.push(parseInt(st.pct, 10));
    if (st.type === 'consent') { await page.click('#yes'); }
    else if (st.type === 'about') {
      await page.fill('#age', String(randInt(18, 70)));
      await pick(await page.$$('#c_year .chip')).click();
      await pick(await page.$$('#c_field .chip')).click();
      await page.click('#go');
    }
    else if (st.type === 'intro') { await page.click('#go'); }
    else if (st.type === 'choice') { await pick(await page.$$('.opt')).click(); }
    else if (st.type === 'adaptive') {
      var sp = spec(st.id);
      var later = Math.random() < 0.5;
      if (mode === 'consistent') {
        if (truth[st.id] === undefined) { truth[st.id] = sp.lo + Math.random() * (sp.hi - sp.lo); }
        var L = Number((await page.textContent('#ob')).replace(/,/g, '').match(/\d+/)[0]);
        // A cost is postponed only while the later amount is still below the switch point
        if (sp.cost) { later = L < truth[st.id]; } else { later = L >= truth[st.id]; }
      }
      if (later) { await page.click('#ob'); } else { await page.click('#oa'); }
    }
    else if (st.type === 'upi') { await page.click('#go'); }
  }
  if (posted) { await page.waitForSelector('#share'); }
  await ctx.close();
  return { posted: posted, errors: errors, truth: truth, pcts: pcts, mode: mode };
}

function replay(taskId, taps) {
  var sp = spec(taskId);
  var lo = sp.lo;
  var hi = sp.hi;
  for (var i = 0; i < taps.length; i++) {
    var later = taps[i].choice === 'later';
    if (sp.cost === later) { lo = taps[i].offer; } else { hi = taps[i].offer; }
  }
  return (lo + hi) / 2;
}

function checkRun(r, problems) {
  var d = r.posted;
  var tag = '[' + (d && d.id) + ' ' + r.mode + '] ';
  if (!d) { problems.push(tag + 'no POST captured'); return; }
  if (r.errors.length) { problems.push(tag + 'console errors: ' + r.errors.join(' | ')); }
  for (var i = 0; i < REQUIRED.length; i++) {
    if (!(REQUIRED[i] in d)) { problems.push(tag + 'missing ' + REQUIRED[i]); }
  }
  if (d.survey !== 'proposal' || d.version !== 'p1' || d.test !== 'yes') { problems.push(tag + 'bad survey/version/test tag'); }
  var taps = JSON.parse(d.trialsJSON);
  for (var t = 0; t < TASKS.length; t++) {
    var id = TASKS[t];
    var sp = spec(id);
    var mine = taps.filter(function (x) { return x.step === id; });
    if (mine.length !== 6) { problems.push(tag + id + ' has ' + mine.length + ' taps'); continue; }
    var ind = d[id + '_ind'];
    if (Math.abs(replay(id, mine) - ind) > 1e-9) { problems.push(tag + id + ' ind does not match replay'); }
    if (!(ind >= sp.lo && ind <= sp.hi)) { problems.push(tag + id + ' ind out of range'); }
    if (Math.abs(d[id + '_k'] - (ind / sp.V - 1) / 30) > 1e-4) { problems.push(tag + id + ' k does not match ind'); }
    if (r.mode === 'consistent' && Math.abs(ind - r.truth[id]) > (sp.hi - sp.lo) / 64 + sp.step) {
      problems.push(tag + id + ' ind ' + ind + ' far from true ' + r.truth[id].toFixed(1));
    }
  }
  // Reversal flags must match the two answers
  var classic = d.flipNear === '₹100 today' && d.flipFar === '₹110 in 31 days';
  var reverse = d.flipNear === '₹110 tomorrow' && d.flipFar === '₹100 in 30 days';
  if ((d.flipped === 'yes') !== classic || (d.reverseFlip === 'yes') !== reverse) { problems.push(tag + 'flip flags wrong'); }
  // The first single choice is the pair named by flipOrder, and the last one is the other pair
  var flips = taps.filter(function (x) { return x.step === 'flipNear' || x.step === 'flipFar'; });
  var want = 'flipNear';
  if (d.flipOrder === 'farFirst') { want = 'flipFar'; }
  if (flips.length !== 2 || flips[0].step !== want) { problems.push(tag + 'pair order wrong'); }
  if (taps[taps.length - 1].step !== flips[1].step) { problems.push(tag + 'second pair is not the last question'); }
  if ((d.attentionFail === 'yes') !== (d.attn1 === '₹10 in 60 days')) { problems.push(tag + 'attentionFail wrong'); }
  for (var p = 1; p < r.pcts.length; p++) {
    if (r.pcts[p] < r.pcts[p - 1]) { problems.push(tag + 'progress went backwards'); break; }
  }
}

(async function () {
  var started = Date.now();
  var server = await startServer();
  var base = 'http://127.0.0.1:' + server.address().port;
  var browser = await playwright.chromium.launch();
  var results = [];
  var n = 0;
  async function worker() {
    while (n < RUNS) {
      var mode = 'random';
      if (n % 2 === 1) { mode = 'consistent'; }
      n += 1;
      results.push(await playOnce(browser, base, mode));
    }
  }
  var workers = [];
  for (var w = 0; w < PARALLEL; w++) { workers.push(worker()); }
  await Promise.all(workers);
  await browser.close();
  server.close();
  var problems = [];
  var orders = {};
  for (var i = 0; i < results.length; i++) {
    checkRun(results[i], problems);
    if (results[i].posted) { orders[results[i].posted.flipOrder] = (orders[results[i].posted.flipOrder] || 0) + 1; }
  }
  var posted = results.filter(function (r) { return r.posted; });
  console.log('Runs: ' + results.length + ', posted: ' + posted.length + ', fields: ' + (posted.length && Object.keys(posted[0].posted).length) + ', time: ' + Math.round((Date.now() - started) / 1000) + 's');
  console.log('flipOrder: ' + JSON.stringify(orders));
  if (problems.length) {
    console.log('\nFAILED (' + problems.length + '):');
    for (var p = 0; p < Math.min(problems.length, 30); p++) { console.log(' - ' + problems[p]); }
    process.exit(1);
  }
  console.log('\nALL CHECKS PASSED');
})();
