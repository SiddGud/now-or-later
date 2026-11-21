// Builds the final report PDF: inserts the figures from report/figures into the template and prints it with Chromium.
// Usage (from the repo root, after `py analysis/report_assets.py responses.csv`): node report/source/render.js
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const here = __dirname;
const figures = path.join(here, '..', 'figures');
const dataLink = '<a href="https://github.com/SiddGud/now-or-later/tree/main/data">github.com/SiddGud/now-or-later/tree/main/data</a>';

// Reads an SVG figure and lets the page CSS control its size
function svg(name) {
  let s = fs.readFileSync(path.join(figures, name), 'utf8');
  s = s.replace(/<\?xml[^>]*>/, '').replace(/<!DOCTYPE[^>]*>/, '');
  s = s.replace(/<svg([^>]*?)\swidth="[^"]*"/, '<svg$1').replace(/<svg([^>]*?)\sheight="[^"]*"/, '<svg$1');
  return s;
}

async function main() {
  let html = fs.readFileSync(path.join(here, 'report_template.html'), 'utf8');
  html = html.replace('{{FIG0}}', svg('fig0_design.svg'))
    .replace('{{FIG1}}', svg('fig1_context.svg'))
    .replace('{{FIG2}}', svg('fig2_inconsistency.svg'))
    .replace('{{FIG3}}', svg('fig3_trait.svg'))
    .replace('{{DATALINK}}', dataLink);
  const built = path.join(here, 'report.html');
  fs.writeFileSync(built, html);
  const browser = await chromium.launch();
  const page = await browser.newPage();
  await page.goto('file:///' + built.replace(/\\/g, '/'));
  await page.pdf({ path: path.join(here, '..', 'Now_or_Later_Final_Report.pdf'), format: 'A4',
    printBackground: true, preferCSSPageSize: true });
  await browser.close();
  fs.unlinkSync(built);
  console.log('Wrote report/Now_or_Later_Final_Report.pdf');
}

main();
