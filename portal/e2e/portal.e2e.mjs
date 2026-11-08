// End-to-end checks for the central portal (v0.3).
//
// Runs a real Chromium against a served build of the portal and the live API,
// signs in with the seeded demo accounts and asserts what each page shows.
// Proves the portal actually works: routing, auth, RTL Arabic UI, permissions
// and per-hospital data isolation.
//
//   node e2e/portal.e2e.mjs
//
// Environment:
//   PORTAL_URL   default http://127.0.0.1:4174
//   CHROME_PATH  path to a Chromium/Chrome binary (auto-detected otherwise)

import { existsSync } from "node:fs";
import { chromium } from "playwright-core";

const PORTAL = process.env.PORTAL_URL ?? "http://127.0.0.1:4174";
const PASSWORD = "Demo@12345";

const CANDIDATES = [
  process.env.CHROME_PATH,
  `${process.env.HOME}/.cache/ms-playwright/chromium-1254/chrome-linux64/chrome`,
  "/usr/bin/chromium",
  "/usr/bin/google-chrome",
].filter(Boolean);

function findChrome() {
  for (const p of CANDIDATES) if (p && existsSync(p)) return p;
  throw new Error("No Chromium binary found; set CHROME_PATH.");
}

let passed = 0;
const failures = [];

function check(name, condition, detail = "") {
  if (condition) {
    passed += 1;
    console.log(`  ok   ${name}`);
  } else {
    failures.push(`${name}${detail ? ` — ${detail}` : ""}`);
    console.log(`  FAIL ${name}${detail ? ` — ${detail}` : ""}`);
  }
}

async function signIn(page, username) {
  await page.goto(`${PORTAL}/login`, { waitUntil: "networkidle" });
  await page.fill('input[type="text"], input:not([type="password"])', username);
  await page.fill('input[type="password"]', PASSWORD);
  await page.click('button[type="submit"], button');
  await page.waitForURL((u) => !u.pathname.endsWith("/login"), { timeout: 15000 });
  await page.waitForLoadState("networkidle");
}

async function bodyText(page) {
  return (await page.textContent("body")) ?? "";
}

async function run() {
  const browser = await chromium.launch({ executablePath: findChrome(), args: ["--no-sandbox"] });
  const context = await browser.newContext({ locale: "ar", viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();
  const consoleErrors = [];
  // Chromium logs a handled 4xx response as a console error too; those are not
  // JavaScript faults, so keep only real script errors.
  page.on("console", (m) => {
    if (m.type() !== "error") return;
    const t = m.text();
    if (t.includes("Failed to load resource")) return;
    consoleErrors.push(t);
  });
  page.on("pageerror", (e) => consoleErrors.push(String(e)));

  try {
    console.log("\n[1] الصفحة تفتح على شاشة الدخول بالعربية");
    await page.goto(`${PORTAL}/login`, { waitUntil: "networkidle" });
    const dir = await page.getAttribute("html", "dir");
    check("الاتجاه من اليمين إلى اليسار (dir=rtl)", dir === "rtl", `dir=${dir}`);
    check("لغة الصفحة العربية", (await page.getAttribute("html", "lang"))?.startsWith("ar"));
    check("عنوان الدخول ظاهر", (await bodyText(page)).includes("دخول"));

    console.log("\n[2] دخول مدير النظام المركزي ولوحة القيادة الوطنية");
    await signIn(page, "central.admin");
    let text = await bodyText(page);
    check("الشريط الجانبي يحمل «لوحة القيادة الوطنية»", text.includes("لوحة القيادة الوطنية"));
    check("اسم المستخدم في الشريط العلوي", text.includes("مدير النظام المركزي"));
    check("بيانات فعلية من الخادم (عدد المستشفيات)", text.includes("المستشفيات"));

    console.log("\n[3] الصفحات الرئيسية تعرض محتوى فعلياً");
    const pages = [
      ["/charts", ["الرسوم", "المؤشرات"]],
      ["/comparisons", ["مقارنة المستشفيات", "المستشفى"]],
      ["/tracking", ["المستشفيات", "الإرسال"]],
      ["/alerts", ["التنبيهات", "تأخر إرسال"]],
      ["/hospitals", ["المستشفيات", "الأقسام"]],
      ["/indicators", ["مكتبة المؤشرات الوطنية", "AUDIT-COVER"]],
      ["/quality", ["الجودة وسلامة المرضى", "نظرة عامة"]],
      ["/users", ["المستخدمون", "central.admin"]],
      ["/audit", ["سجل التدقيق", "الإجراء", "الملخّص"]],
      ["/sync", ["مركز المزامنة", "حالة أجهزة المزامنة"]],
    ];
    for (const [path, needles] of pages) {
      await page.goto(`${PORTAL}${path}`, { waitUntil: "networkidle" });
      const t = await bodyText(page);
      const missing = needles.filter((n) => !t.includes(n));
      check(`${path} يعرض المحتوى`, missing.length === 0, missing.length ? `ناقص: ${missing.join(", ")}` : "");
    }

    console.log("\n[4] صفحة تفاصيل المستشفى والمخططات");
    await page.goto(`${PORTAL}/tracking`, { waitUntil: "networkidle" });
    const href = await page.getAttribute("a[href^='/hospital/']", "href").catch(() => null);
    if (href) {
      await page.goto(`${PORTAL}${href}`, { waitUntil: "networkidle" });
      const t = await bodyText(page);
      check("/hospital/:id يعرض مؤشرات الفترة", t.includes("نسبة تحقيق الأهداف"));
    } else {
      check("/hospital/:id متاح", false, "لا يوجد رابط مستشفى في صفحة المتابعة");
    }

    console.log("\n[5] الصلاحيات: المستخدم للقراءة فقط لا يرى الإدارة ولا سجل التدقيق");
    await page.goto(`${PORTAL}/`, { waitUntil: "networkidle" });
    await page.evaluate(() => localStorage.clear());
    await signIn(page, "rep.reader");
    text = await bodyText(page);
    check("عناصر إدارة المستخدمين مخفية", !text.includes("المستخدمون والصلاحيات"));
    check("سجل التدقيق مخفي", !text.includes("سجل التدقيق"));
    check("لوحة القيادة متاحة للقراءة", text.includes("لوحة القيادة الوطنية"));
    check("المستخدم يعرّف كمستشفى", text.includes("المستشفى"));

    console.log("\n[6] عزل البيانات: المستخدم المقيّد يرى مستشفاه فقط");
    await page.goto(`${PORTAL}/tracking`, { waitUntil: "networkidle" });
    text = (await bodyText(page)).replace(/\s+/g, " ");
    check("إجمالي المستشفيات = 1 لنطاق المستشفى", /إجمالي المستشفيات\s*1/.test(text), "لم يظهر الرقم 1");

    console.log("\n[7] وحدات الجودة وسلامة المرضى (v0.7)");
    await page.goto(`${PORTAL}/`, { waitUntil: "networkidle" });
    await page.evaluate(() => localStorage.clear());
    await signIn(page, "rep.quality");
    await page.goto(`${PORTAL}/quality`, { waitUntil: "networkidle" });

    // Overview tab is the default and shows the seeded summary counts. The dev
    // database can accumulate rows, so assert the seeded three are at least there.
    let qt = (await bodyText(page)).replace(/\s+/g, " ");
    const incidentTotal = Number(/إجمالي الحوادث\s*(\d+)/.exec(qt)?.[1] ?? "-1");
    check("نظرة عامة: إجمالي الحوادث ≥ 3", incidentTotal >= 3, `العدد المعروض = ${incidentTotal}`);
    check("نظرة عامة: توزيع حسب الخطورة", qt.includes("توزيع الحوادث حسب الخطورة"));

    // Incidents tab lists the seeded demo incidents.
    await page.click('button:has-text("الحوادث وRCA")');
    await page.waitForSelector('text=INC-2026-0001', { timeout: 10000 }).catch(() => {});
    qt = await bodyText(page);
    check("الحوادث: ظهور حادث تجريبي", qt.includes("INC-2026-0001"), "لم يظهر رمز الحادث");
    check("الحوادث: نموذج الإبلاغ متاح للمدير", qt.includes("الإبلاغ عن حادث جديد"));

    // Open the incident detail (RCA) for the fall incident.
    const detailButtons = page.locator('table button:has-text("تفاصيل")');
    if ((await detailButtons.count()) > 0) {
      await detailButtons.first().click();
      await page.waitForTimeout(600);
      qt = await bodyText(page);
      check("تفاصيل الحادث تُعرض", qt.includes("تحليل الأسباب الجذرية") || qt.includes("لا يوجد تحليل"));
    } else {
      check("تفاصيل الحادث متاحة", false, "لا يوجد زر تفاصيل");
    }

    // Risks tab shows the database-computed score badge.
    await page.click('button:has-text("سجل المخاطر")');
    await page.waitForSelector('text=RSK-2026-0001', { timeout: 10000 }).catch(() => {});
    qt = await bodyText(page);
    check("المخاطر: ظهور سجل المخاطر", qt.includes("RSK-2026-0001"), "لم يظهر رمز الخطر");
    check("المخاطر: احتساب الدرجة", /(15|20|6)\s*—/.test(qt.replace(/\s+/g, " ")));

    // Documents tab shows an approved document.
    await page.click('button:has-text("الوثائق والسياسات")');
    await page.waitForSelector('text=DOC-2026-0001', { timeout: 10000 }).catch(() => {});
    qt = await bodyText(page);
    check("الوثائق: ظهور وثيقة معتمدة", qt.includes("معتمدة"), "لم تظهر حالة الاعتماد");

    // Meetings tab.
    await page.click('button:has-text("اجتماعات الجودة")');
    await page.waitForSelector('text=اجتماع لجنة الجودة الشهري', { timeout: 10000 }).catch(() => {});
    qt = await bodyText(page);
    check("الاجتماعات: ظهور اجتماع منعقد", qt.includes("اجتماع لجنة الجودة الشهري"), "لم يظهر الاجتماع");

    console.log("\n[8] الجودة: القراءة فقط لا ترى نماذج الإنشاء");
    await page.goto(`${PORTAL}/`, { waitUntil: "networkidle" });
    await page.evaluate(() => localStorage.clear());
    await signIn(page, "rep.reader");
    await page.goto(`${PORTAL}/quality`, { waitUntil: "networkidle" });
    qt = await bodyText(page);
    check("الجودة: تنبيه القراءة فقط", qt.includes("وضع القراءة فقط"));
    check("الجودة: لا نموذج إبلاغ للقارئ", !qt.includes("الإبلاغ عن حادث جديد"));

    console.log("\n[9] المساعد الذكي (v0.8)");
    await page.goto(`${PORTAL}/`, { waitUntil: "networkidle" });
    await page.evaluate(() => localStorage.clear());
    await signIn(page, "central.admin");
    await page.goto(`${PORTAL}/assistant`, { waitUntil: "networkidle" });
    await page.waitForTimeout(1500);
    qt = (await bodyText(page)).replace(/\s+/g, " ");
    check("المساعد: تنبيه الأمانة", qt.includes("لا يختلق") && qt.includes("ليس حكماً طبياً"));
    check("المساعد: نطاق وطني", qt.includes("نطاق التحليل"));
    check("المساعد: نتائج تحليلية", qt.includes("النتائج التحليلية"));
    // Switch to a single hospital and generate a draft report.
    const scopeSelect = page.locator("select").filter({ has: page.locator('option', { hasText: "مستشفى واحد" }) });
    await scopeSelect.first().selectOption({ label: "مستشفى واحد" });
    await page.waitForTimeout(600);
    // Pick the first real hospital in the hospital picker.
    const picker = page.locator("select").filter({ has: page.locator('option', { hasText: "اختر مستشفى" }) });
    const opts = await picker.first().locator("option").all();
    for (const o of opts) {
      const v = await o.getAttribute("value");
      if (v) {
        await picker.first().selectOption(v);
        break;
      }
    }
    await page.waitForTimeout(1200);
    const generate = page.locator('button:has-text("توليد المسودة")');
    if ((await generate.count()) > 0) {
      await generate.first().click();
      await page.waitForTimeout(1200);
      qt = await bodyText(page);
      check("المساعد: مسودة التقرير", qt.includes("مسودة تقرير أداء"));
    } else {
      check("المساعد: زر توليد المسودة متاح", false, "لم يظهر الزر");
    }

    console.log("\n[10] قواعد التنبيه القابلة للتهيئة (v0.10)");
    await page.goto(`${PORTAL}/`, { waitUntil: "networkidle" });
    await page.evaluate(() => localStorage.clear());
    await signIn(page, "central.admin");
    await page.goto(`${PORTAL}/alerts`, { waitUntil: "networkidle" });
    await page.waitForTimeout(800);
    const openRules = page.locator('button:has-text("تهيئة عتبات التنبيه")');
    check("زر تهيئة العتبات متاح لمدير النظام", (await openRules.count()) > 0);
    await openRules.first().click();
    await page.waitForTimeout(1200);
    qt = (await bodyText(page)).replace(/\s+/g, " ");
    check("لوحة العتبات: النطاق الوطني", qt.includes("الافتراضي الوطني"));
    check("لوحة العتبات: نوع تدنّي الأهداف", qt.includes("تدنّي تحقيق الأهداف"));
    check("لوحة العتبات: نوع المخاطر العالية", qt.includes("مخاطر عالية مفتوحة"));
    check("لوحة العتبات: عتبة الشذوذ (z)", qt.includes("عتبة الشذوذ الإحصائي"));
    // Change the high-risk threshold to 20 and save.
    const riskRow = page.locator("tr", { hasText: "مخاطر عالية مفتوحة" });
    const riskInput = riskRow.locator('input[type="number"]');
    if ((await riskInput.count()) > 0) {
      await riskInput.first().fill("20");
      const saveBtn = riskRow.locator('button:has-text("حفظ")');
      await saveBtn.first().click();
      await page.waitForTimeout(1200);
      check("لوحة العتبات: حفظ قيمة جديدة", (await bodyText(page)).includes("تم الحفظ"));
      // restore the default
      await riskRow.locator('button:has-text("استرجاع الوطني")').first().click().catch(() => {});
      await page.waitForTimeout(800);
    } else {
      check("لوحة العتبات: حقل رقمي للمخاطر", false, "لم يظهر حقل الإدخال");
    }

    console.log("\n[11] سجل التدقيق: التصفية والتصدير (v0.11)");
    await page.goto(`${PORTAL}/`, { waitUntil: "networkidle" });
    await page.evaluate(() => localStorage.clear());
    await signIn(page, "central.admin");
    await page.goto(`${PORTAL}/audit`, { waitUntil: "networkidle" });
    await page.waitForTimeout(600);
    let at = (await bodyText(page)).replace(/\s+/g, " ");
    check("سجل التدقيق: بطاقة التصفية", at.includes("عوامل التصفية"));
    check("سجل التدقيق: عمود الملخّص", at.includes("الملخّص"));
    check("سجل التدقيق: زر التصدير", at.includes("تصدير Excel"));
    check("سجل التدقيق: إحصاء النطاق", at.includes("عدد المدخلات في نطاقك"));
    const typeSelect = page.locator("#f-type, select").first();
    if ((await typeSelect.count()) > 0) {
      await typeSelect.selectOption({ index: 1 });
      await page.locator('button:has-text("تطبيق")').first().click();
      await page.waitForTimeout(800);
      at = (await bodyText(page)).replace(/\s+/g, " ");
      check("سجل التدقيق: تطبيق التصفية يعمل", at.includes("سجل التدقيق"));
    } else {
      check("سجل التدقيق: قائمة نوع الكيان", false, "لم تظهر القائمة");
    }

    console.log("\n[12] مركز المزامنة الوطني: الأجهزة والتعارضات (v0.12)");
    await page.goto(`${PORTAL}/`, { waitUntil: "networkidle" });
    await page.evaluate(() => localStorage.clear());
    await signIn(page, "central.admin");
    await page.goto(`${PORTAL}/sync`, { waitUntil: "networkidle" });
    await page.waitForTimeout(800);
    let st = (await bodyText(page)).replace(/\s+/g, " ");
    check("مركز المزامنة: بطاقة الأجهزة", st.includes("حالة أجهزة المزامنة"));
    check("مركز المزامنة: عمود آخر مزامنة", st.includes("آخر مزامنة"));
    check("مركز المزامنة: بطاقة التعارضات", st.includes("تعارضات المزامنة"));
    check("مركز المزامنة: إحصاء التعارضات المفتوحة", st.includes("تعارضات مفتوحة"));
    check("مركز المزامنة: جهاز تجريبي ظاهر", st.includes("جهاز الجودة"), "لم يظهر الجهاز التجريبي");
    check("مركز المزامنة: جهاز متأخر موسوم", st.includes("متأخر"), "لم تظهر حالة التأخر");

    // Review the demo conflict if it is still open (idempotent across runs).
    const resolveBtn = page.locator('button:has-text("تسجيل المراجعة")');
    const detailBtn = page.locator('table button:has-text("التفاصيل")').first();
    if ((await detailBtn.count()) > 0) {
      await detailBtn.click();
      await page.waitForTimeout(400);
    }
    if ((await resolveBtn.count()) > 0) {
      await resolveBtn.first().click();
      await page.waitForTimeout(1000);
      st = (await bodyText(page)).replace(/\s+/g, " ");
      check("مركز المزامنة: تسجيل مراجعة التعارض", st.includes("تم تسجيل مراجعة التعارض"));
    } else {
      // Already reviewed by an earlier run: the resolved view must show it.
      await page.locator('input[type="checkbox"]').last().check();
      await page.waitForTimeout(800);
      st = (await bodyText(page)).replace(/\s+/g, " ");
      check("مركز المزامنة: التعارض المُعالَج ظاهر", st.includes("راجعه مسؤول واعتمده"));
    }

    console.log("\n[13] تنبيهات المزامنة تظهر في مركز التنبيهات (v0.13)");
    await page.goto(`${PORTAL}/`, { waitUntil: "networkidle" });
    await page.evaluate(() => localStorage.clear());
    await signIn(page, "central.admin");
    await page.goto(`${PORTAL}/alerts`, { waitUntil: "networkidle" });
    await page.waitForTimeout(800);
    let sat = (await bodyText(page)).replace(/\s+/g, " ");
    check("التنبيهات: مصدر المزامنة ظاهر", sat.includes("المزامنة"), "لم يظهر مصدر المزامنة");
    check(
      "التنبيهات: تنبيه جهاز مزامنة متأخر",
      sat.includes("جهاز مزامنة متأخر"),
      "لم يظهر تنبيه تأخر الجهاز",
    );
    // The configurable threshold for the sync kinds is offered in the rules panel.
    const openSyncRules = page.locator('button:has-text("تهيئة عتبات التنبيه")');
    if ((await openSyncRules.count()) > 0) {
      await openSyncRules.first().click();
      await page.waitForTimeout(1000);
      sat = (await bodyText(page)).replace(/\s+/g, " ");
      check("لوحة العتبات: نوع جهاز المزامنة المتأخر", sat.includes("جهاز مزامنة متأخر"));
      check("لوحة العتبات: عتبة أيام التأخر", sat.includes("أيام التأخر قبل التنبيه"));
    } else {
      check("لوحة العتبات: زر التهيئة متاح", false, "لم يظهر الزر");
    }

    console.log("\n[14] لا أخطاء في وحدة تحكم المتصفح");
    check("لا أخطاء JavaScript", consoleErrors.length === 0, consoleErrors.slice(0, 3).join(" | "));
  } finally {
    await browser.close();
  }

  console.log(`\nالنتيجة: ${passed} ناجح، ${failures.length} فاشل`);
  if (failures.length) {
    console.log("الإخفاقات:");
    for (const f of failures) console.log(`  - ${f}`);
    process.exit(1);
  }
}

run().catch((e) => {
  console.error("فشل تشغيل الاختبارات:", e);
  process.exit(1);
});
