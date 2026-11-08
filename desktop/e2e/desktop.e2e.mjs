// End-to-end checks for the desktop app (v0.10).
//
// Runs a real Chromium against a served build of the desktop UI and the live
// API. In a browser there is no Tauri native layer, so the app takes its online
// path; this proves the quality page, permissions and the report form work.
// The offline path itself is covered by the Rust store tests and the backend
// sync tests.
//
//   node e2e/desktop.e2e.mjs
//
// Environment:
//   DESKTOP_URL        default http://127.0.0.1:4173 (a CORS-allowed origin)
//   CHROME_PATH        path to a Chromium/Chrome binary (auto-detected otherwise)
//   DESKTOP_E2E_WRITE  set to 1 to also save a real incident (pollutes the DB)

import { existsSync } from "node:fs";
import { chromium } from "playwright-core";

const APP = process.env.DESKTOP_URL ?? "http://127.0.0.1:4173";
const PASSWORD = "Demo@12345";
const WRITE = process.env.DESKTOP_E2E_WRITE === "1";

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
  await page.goto(`${APP}/login`, { waitUntil: "networkidle" });
  await page.fill("#username", username);
  await page.fill("#password", PASSWORD);
  await page.click('button[type="submit"]');
  await page.waitForURL((u) => !u.pathname.endsWith("/login"), { timeout: 15000 });
}

const bodyText = (page) => page.textContent("body").then((t) => t ?? "");

const browser = await chromium.launch({ executablePath: findChrome(), args: ["--no-sandbox"] });
const ctx = await browser.newContext({ locale: "ar", viewport: { width: 1440, height: 900 } });
const page = await ctx.newPage();
const jsErrors = [];
page.on("pageerror", (e) => jsErrors.push(String(e)));

try {
  console.log("\n[1] تسجيل الدخول وفتح صفحة الجودة");
  await signIn(page, "rep.quality");
  await page.goto(`${APP}/quality`, { waitUntil: "networkidle" });
  await page.waitForTimeout(1200);

  let t = (await bodyText(page)).replace(/\s+/g, " ");
  check("صفحة الجودة تُعرض", t.includes("الجودة وسلامة المرضى"));
  check("بطاقة الملخص تُعرض", t.includes("إجمالي الحوادث"));
  check("سجل الحوادث يُعرض", t.includes("سجل الحوادث"));
  check("حادث تجريبي يظهر", t.includes("INC-2026-0001"), "لم يظهر رمز الحادث");
  check("وسم المزامنة يظهر", t.includes("مُزامن") || t.includes("بانتظار الإرسال"));

  console.log("\n[2] نموذج الإبلاغ والتحقق من المدخلات");
  await page.click('button:has-text("الإبلاغ عن حادث جديد")');
  await page.waitForTimeout(400);
  t = await bodyText(page);
  check("نموذج الإبلاغ يفتح", t.includes("عنوان الحادث"));
  // Saving with no title must be refused with a plain-Arabic message.
  await page.click('button:has-text("حفظ الحادث")');
  await page.waitForTimeout(400);
  t = await bodyText(page);
  check("رفض حفظ حادث بلا عنوان", t.includes("أدخل عنواناً واضحاً"), "لم تظهر رسالة التحقق");

  if (WRITE) {
    console.log("\n[3] حفظ حادث فعلي");
    const title = `حادث اختبار آلي ${Date.now()}`;
    await page.fill('input[placeholder*="سقوط"]', title);
    await page.click('button:has-text("حفظ الحادث")');
    await page.waitForTimeout(2000);
    t = await bodyText(page);
    check("الحادث المحفوظ يظهر في السجل", t.includes(title), "لم يظهر الحادث الجديد");
    console.log(`WRITTEN_TITLE=${title}`);
  }

  console.log("\n[4] المساعد الذكي (v0.8)");
  await page.goto(`${APP}/assistant`, { waitUntil: "networkidle" });
  await page.waitForTimeout(1500);
  t = (await bodyText(page)).replace(/\s+/g, " ");
  check("المساعد: تنبيه الأمانة", t.includes("لا يختلق") && t.includes("ليس حكماً طبياً"));
  check("المساعد: نتائج تحليلية", t.includes("النتائج التحليلية"));
  check("المساعد: مجالات التحسين", t.includes("مجالات مقترحة للتحسين"));
  const gen = page.locator('button:has-text("توليد المسودة")');
  check("المساعد: زر توليد المسودة", (await gen.count()) > 0);
  if ((await gen.count()) > 0) {
    await gen.first().click();
    await page.waitForTimeout(1500);
    t = await bodyText(page);
    check("المساعد: مسودة التقرير", t.includes("مسودة تقرير أداء"));
  }

  console.log("\n[5] مركز التنبيهات (v0.9)");
  await page.goto(`${APP}/alerts`, { waitUntil: "networkidle" });
  await page.waitForTimeout(1500);
  t = (await bodyText(page)).replace(/\s+/g, " ");
  check("التنبيهات: تنبيه الأمانة", t.includes("لا يُولّد النظام أي تنبيه دون أساس"));
  check("التنبيهات: ملخّص", t.includes("إجمالي التنبيهات") && t.includes("غير مُقَرّ بها"));
  check("التنبيهات: قائمة", t.includes("قائمة التنبيهات"));
  check("التنبيهات: أنواع فعلية", t.includes("تأخر إرسال") || t.includes("تدنّي تحقيق الأهداف"));

  console.log("\n[6] تهيئة عتبات التنبيه (v0.10)");
  const openRules = page.locator('button:has-text("تهيئة عتبات التنبيه")');
  check("زر تهيئة العتبات متاح لمسؤول الجودة", (await openRules.count()) > 0);
  if ((await openRules.count()) > 0) {
    await openRules.first().click();
    await page.waitForTimeout(1500);
    t = (await bodyText(page)).replace(/\s+/g, " ");
    check("العتبات: نطاق المستشفى", t.includes("هذا المستشفى"));
    check("العتبات: نوع المخاطر العالية", t.includes("مخاطر عالية مفتوحة"));
    check("العتبات: عمود القيم", t.includes("أقل درجة خطر") || t.includes("عتبة الشذوذ الإحصائي"));
  }

  console.log("\n[7] تنبيهات المزامنة (v0.13)");
  await page.goto(`${APP}/alerts`, { waitUntil: "networkidle" });
  await page.waitForTimeout(1200);
  t = (await bodyText(page)).replace(/\s+/g, " ");
  check("التنبيهات: مصدر المزامنة متاح", t.includes("المزامنة"));

  console.log("\n[8] الإجراءات والمخاطر في الجودة (v0.14)");
  await page.goto(`${APP}/quality`, { waitUntil: "networkidle" });
  await page.waitForTimeout(1500);
  t = (await bodyText(page)).replace(/\s+/g, " ");
  check("قسم الإجراءات التصحيحية يُعرض", t.includes("الإجراءات التصحيحية والوقائية"));
  check("سجل المخاطر يُعرض", t.includes("سجل المخاطر"));
  const capaBtn = page.locator('button:has-text("إجراء جديد")');
  check("زر إضافة إجراء متاح لمسؤول الجودة", (await capaBtn.count()) > 0);
  if ((await capaBtn.count()) > 0) {
    await capaBtn.first().click();
    await page.waitForTimeout(400);
    t = await bodyText(page);
    check("نموذج الإجراء يفتح", t.includes("عنوان الإجراء") && t.includes("الأولوية"));
    await page.click('button:has-text("حفظ الإجراء")');
    await page.waitForTimeout(400);
    t = await bodyText(page);
    check("رفض حفظ إجراء بلا عنوان", t.includes("أدخل عنواناً واضحاً"), "لم تظهر رسالة التحقق");
  }
  const riskBtn = page.locator('button:has-text("خطر جديد")');
  check("زر إضافة خطر متاح لمسؤول الجودة", (await riskBtn.count()) > 0);
  if ((await riskBtn.count()) > 0) {
    await riskBtn.first().click();
    await page.waitForTimeout(400);
    t = await bodyText(page);
    check("نموذج الخطر يفتح", t.includes("عنوان الخطر") && t.includes("الاحتمال"));
    check("حقل الأثر يُعرض", t.includes("الأثر"));
  }

  console.log("\n[8b] التدقيق الداخلي وخطط التحسين (v0.15)");
  check("قسم التدقيق الداخلي يُعرض", t.includes("التدقيق الداخلي"));
  check("قسم خطط التحسين يُعرض", t.includes("خطط التحسين"));
  const auditBtn = page.locator('button:has-text("تدقيق جديد")');
  check("زر إضافة تدقيق متاح لمسؤول الجودة", (await auditBtn.count()) > 0);
  if ((await auditBtn.count()) > 0) {
    await auditBtn.first().click();
    await page.waitForTimeout(400);
    t = await bodyText(page);
    check("نموذج التدقيق يفتح", t.includes("عنوان التدقيق") && t.includes("المعيار المرجعي"));
    await page.click('button:has-text("حفظ التدقيق")');
    await page.waitForTimeout(400);
    t = await bodyText(page);
    check("رفض حفظ تدقيق بلا عنوان", t.includes("أدخل عنواناً واضحاً"), "لم تظهر رسالة التحقق");
  }
  const planBtn = page.locator('button:has-text("خطة جديدة")');
  check("زر إضافة خطة متاح لمسؤول الجودة", (await planBtn.count()) > 0);
  if ((await planBtn.count()) > 0) {
    await planBtn.first().click();
    await page.waitForTimeout(400);
    t = await bodyText(page);
    check("نموذج الخطة يفتح", t.includes("عنوان الخطة") && t.includes("الوضع الأساسي"));
  }

  console.log("\n[9] لا أخطاء JavaScript");
  check("لا أخطاء JavaScript", jsErrors.length === 0, jsErrors.slice(0, 2).join(" | "));
} catch (e) {
  failures.push(`استثناء: ${e.message}`);
  console.log(`  FAIL استثناء: ${e.message}`);
} finally {
  await browser.close();
}

console.log(`\nالنتيجة: ${passed} ناجح، ${failures.length} فاشل`);
if (failures.length) {
  console.log("الإخفاقات:");
  for (const f of failures) console.log(`  - ${f}`);
  process.exit(1);
}
