// Render the built HTML into a paginated, print-quality PDF using the system Chromium.
const { chromium } = require('playwright-core');
const path = require('path');

(async () => {
  const root = path.resolve(__dirname, '..');
  const htmlPath = path.join(root, 'dist', 'study.html');
  const pdfPath = process.argv[2] || path.join(root, 'dist', 'دراسة-النظام-الصحي-اليمني.pdf');

  const browser = await chromium.launch({
    executablePath: '/usr/bin/chromium',
    args: ['--no-sandbox', '--font-render-hinting=none'],
  });
  const page = await browser.newPage();
  await page.goto('file://' + htmlPath, { waitUntil: 'networkidle' });
  await page.emulateMedia({ media: 'print' });
  await page.evaluate(() => document.fonts && document.fonts.ready);

  const footer = `
    <div style="width:100%;font-family:'Noto Kufi Arabic',sans-serif;font-size:7pt;color:#64748b;
                padding:0 14mm;display:flex;justify-content:space-between;direction:rtl">
      <span>النظام الوطني لإدارة مؤشرات الأداء الصحي والجودة وسلامة المرضى — اليمن</span>
      <span>صفحة <span class="pageNumber"></span> / <span class="totalPages"></span></span>
    </div>`;

  await page.pdf({
    path: pdfPath,
    format: 'A4',
    printBackground: true,
    displayHeaderFooter: true,
    headerTemplate: '<div></div>',
    footerTemplate: footer,
    margin: { top: '14mm', bottom: '16mm', left: '13mm', right: '13mm' },
  });

  await browser.close();
  console.log('wrote', pdfPath);
})();
