# مواصفات واجهات الربط (REST API)
## النظام الوطني لإدارة مؤشرات الأداء الصحي والجودة وسلامة المرضى — وزارة الصحة العامة والسكان

**الإصدار:** 1.1 · **الحالة:** مسودة بانتظار الموافقة

---

## الشرح بلغة بسيطة
واجهة الربط (API) هي **لغة الحوار** بين تطبيق المستشفى والمنصة المركزية. هذه الوثيقة تحدّد "الجمل" المسموح بها بالضبط: ما نرسله، ما نتلقّاه، وكيف نعالج الأخطاء — بدقة تمنع الالتباس عند التنفيذ.

---

## 1. المبادئ العامة
- **النمط:** REST فوق HTTPS.
- **التنسيق:** JSON (UTF-8).
- **الإصدار في المسار:** `/api/v1/...` — تغيير كبير = إصدار جديد دون كسر القديم.
- **التواريخ:** UTC بصيغة ISO-8601 (`2026-11-07T21:00:00Z`).
- **المعرّفات:** UUIDv7 نصّية.
- **الأسماء:** `snake_case` للحقول.
- **الترقيم (Pagination):** `?offset=0&limit=50` (limit أقصى 200)، والرد يحمل `total` و `has_more`.
- **الفرز:** `?sort=created_at&order=desc`.
- **الفلترة:** حقول صريحة (`?hospital_id=...&period_id=...`).
- **الحقول المطلوبة:** `Content-Type: application/json` لكل طلب كتابة.

## 2. المصادقة والتخويل
### 2.1 ترويسات المصادقة
```
Authorization: Bearer <access_token>
X-Client-Node: <uuid-of-device>      # معرّف الجهاز (للمزامنة)
X-Request-Id: <uuid>                 # لتتبّع الطلب في السجلات
```
### 2.2 تدفّق الرموز
- `POST /api/v1/auth/login` → يعيد `access_token` (عمره 30–60 دقيقة) + `refresh_token` (عمره أطول).
- `POST /api/v1/auth/refresh` → رمز وصول جديد.
- `POST /api/v1/auth/logout` → إبطال الجلسة.
- **عند انتهاء الرمز:** 401 + رمز خطأ `token_expired` ليجدّد العميل تلقائياً.

### 2.3 مثال تسجيل الدخول
```json
POST /api/v1/auth/login
{
  "username": "quality.sanaa",
  "password": "********",
  "client_node": "0190f1c2-...-a1"
}
→ 200
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "expires_in": 3600,
  "user": { "id": "0190...", "display_name": "أمينة", "role": "quality_manager" },
  "scopes": ["indicator.enter","period.submit","period.approve","incident.manage"],
  "scope_org": { "level": "hospital", "hospital_id": "0190...", "governorate_id": "0190..." }
}
```

## 3. نموذج الأخطاء الموحّد
كل خطأ يعيد:
```json
{
  "error": {
    "code": "validation_failed",
    "message_ar": "المقام لا يمكن أن يكون صفراً.",
    "details": [ { "field": "denominator", "issue": "must_be_positive" } ],
    "request_id": "0190...-req"
  }
}
```
### 3.1 أكواد الحالة والأخطاء
| HTTP | code | المعنى |
|------|------|--------|
| 400 | `validation_failed` | مدخل غير صالح |
| 401 | `unauthenticated` / `token_expired` | لا مصادقة |
| 403 | `forbidden` | لا صلاحية |
| 404 | `not_found` | غير موجود |
| 409 | `conflict` / `already_approved` | تعارض/معتمد |
| 422 | `business_rule_violated` | خرق قاعدة عمل |
| 429 | `rate_limited` | تجاوز الحد (مع `Retry-After`) |
| 500 | `internal_error` | خطأ داخلي |

> **قاعدة أمان:** رسائل الخطأ **لا تكشف** تفاصيل داخلية (لا استعلامات، لا مسارات، لا أسرار).

## 4. تحديد المعدّل (Rate Limiting)
- لكل مستخدم/جهاز حدود (مثلاً: 300 طلب/دقيقة عادي، وحدود أعلى لنقاط المزامنة).
- الترويسات: `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`.
- عند التجاوز: 429 + `Retry-After`.

## 5. منع التكرار (Idempotency)
- كل طلب كتابة يحمل ترويسة:
```
Idempotency-Key: <entity_type>:<entity_id>:<rev>
```
- إن أُعيد نفس المفتاح: يعيد الخادم **نفس النتيجة** دون أثر مزدوج.

## 6. فهرس النقاط (Endpoint Catalogue)

### 6.1 المصادقة والمستخدمون
| الطريقة | المسار | الوصف |
|--------|-------|-------|
| POST | `/auth/login` | دخول |
| POST | `/auth/refresh` | تجديد الرمز |
| POST | `/auth/logout` | خروج |
| GET | `/me` | بيانات المستخدم وصلاحياته |
| GET | `/users` | قائمة المستخدمين (حسب الصلاحية) |
| POST | `/users` | إنشاء مستخدم |
| PATCH | `/users/{id}` | تعديل |
| POST | `/users/{id}/assignments` | ربط بدور/جهة |

### 6.2 المؤسسات
| الطريقة | المسار | الوصف |
|--------|-------|-------|
| GET | `/organizations` | شجرة المستويات |
| GET | `/hospitals` | المستشفيات (مفلترة بالصلاحية) |
| POST | `/hospitals` | إنشاء مستشفى |
| GET | `/hospitals/{id}` | تفاصيل |
| PATCH | `/hospitals/{id}` | تعديل |
| GET | `/hospitals/{id}/departments` | أقسام المستشفى |
| POST | `/hospitals/{id}/departments` | إضافة قسم |

### 6.3 مكتبة المؤشرات
| الطريقة | المسار | الوصف |
|--------|-------|-------|
| GET | `/indicators` | قائمة (وطنية + خاصة) |
| POST | `/indicators` | إنشاء مؤشر |
| GET | `/indicators/{id}` | تفاصيل + الإصدار الحالي |
| POST | `/indicators/{id}/versions` | إصدار جديد |
| POST | `/indicators/{id}/bindings` | ربط بأقسام |
| GET | `/indicators/catalogue` | المكتبة الوطنية الجاهزة |

### 6.4 الفترات والإدخال
| الطريقة | المسار | الوصف |
|--------|-------|-------|
| GET | `/periods` | الفترات |
| POST | `/periods` | إنشاء فترة |
| GET | `/period-values` | قيم الفترة (مفلترة) |
| POST | `/period-values` | إدخال قيمة |
| PATCH | `/period-values/{id}` | تعديل (مسودة) |
| POST | `/period-values/{id}/submit` | إرسال للمراجعة |
| POST | `/period-values/{id}/approve` | اعتماد |
| POST | `/period-values/{id}/reject` | رفض/إعادة |

### 6.5 الجودة وسلامة المرضى
| الطريقة | المسار | الوصف |
|--------|-------|-------|
| GET/POST | `/incidents` | الحوادث |
| GET/PATCH | `/incidents/{id}` | تفاصيل/تعديل |
| POST | `/incidents/{id}/rca` | إنشاء تحليل أسباب |
| GET/POST | `/capa-actions` | إجراءات CAPA |
| GET/POST | `/risks` | المخاطر |
| GET/POST | `/audits` | التدقيق |
| GET/POST | `/improvement-plans` | خطط التحسين |
| GET/POST | `/documents` | الوثائق |
| GET/POST | `/meetings` | الاجتماعات |

### 6.6 التقارير
| الطريقة | المسار | الوصف |
|--------|-------|-------|
| GET | `/reports/hospital/{id}` | تقرير مستشفى |
| GET | `/reports/governorate/{id}` | تقرير محافظة |
| GET | `/reports/national` | تقرير وطني |
| POST | `/reports/export` | توليد PDF/Excel (غير متزامن) |
| GET | `/reports/exports/{job_id}` | حالة/رابط الملف |

### 6.7 التحليل والذكاء الاصطناعي
| الطريقة | المسار | الوصف |
|--------|-------|-------|
| GET | `/analytics/trends` | اتجاهات مؤشر |
| GET | `/analytics/anomalies` | شذوذ مكتشف |
| GET | `/analytics/summary` | ملخص أداء (مُسنَد للبيانات) |
| POST | `/ai/draft-report` | مسودة تقرير إداري |

> المنفَّذ فعلاً في v0.8 يستخدم البادئة `/assistant` (انظر الوثيقة 23): `GET /assistant/status`،
> `GET /assistant/national`، `GET /assistant/hospital/{id}`، `GET /assistant/hospital/{id}/draft-report`.
> الصفوف أعلاه بقيت من التصميم الأولي للتخطيط.

### 6.7.1 مركز التنبيهات (v0.9)
| الطريقة | المسار | الوصف | الصلاحية |
|--------|-------|-------|----------|
| GET | `/alerts?year=&month=&hospital_id=&include_acked=` | تنبيهات محسوبة + ملخّص | `report.view` |
| POST | `/alerts/{key}/ack?year=&month=&hospital_id=` | الإقرار بتنبيه | `alert.manage` |
| POST | `/alerts/{key}/reopen?year=&month=&hospital_id=` | إعادة فتح تنبيه | `alert.manage` |

التنبيهات **تُحسب ولا تُحفظ**؛ يُحفظ الإقرار فقط. الأنواع تشمل مصدر **المزامنة**
منذ v0.13 (`stale_device` لجهاز لم يُزامن منذ العتبة، و`open_conflict` لتعارضات
لم يراجعها مسؤول). التفاصيل في الوثيقتين 24 و27.

### 6.7.2 قواعد التنبيه القابلة للتهيئة (v0.10)
| الطريقة | المسار | الوصف | الصلاحية |
|--------|-------|-------|----------|
| GET | `/alert-rules?hospital_id=` | كتالوج العتبات مع القيم الفعلية | `alert.manage` |
| PUT | `/alert-rules/{kind}?hospital_id=` | ضبط عتبات نوع (وطني أو تخصيص مستشفى) | `alert.configure` |
| POST | `/alert-rules/{kind}/reset?hospital_id=` | حذف التخصيص/الافتراضي ليعود الأعلى نطاقاً | `alert.configure` |

العتبات الرقمية التي يستخدمها محرّك التنبيه **صارت بيانات** لا ثوابت في الكود:
قيمة افتراضية في الكود، يعلوها صف وطني، ثم يعلوه صف المستشفى. القيم تُدقَّق
وتُقصّ في الخادم، والمفاتيح المجهولة تُتجاهل، فلا يمكن لتعديل خاطئ أن يُعطّل
المحرّك. النوع `late_submission` **مفتاح وطني فقط** (تشغيل/إيقاف). التفاصيل في
الوثيقة 24، القسم 8.

### 6.8 المزامنة (تفصيلها في الوثيقة 14)
| الطريقة | المسار | الوصف |
|--------|-------|-------|
| POST | `/sync/push` | إرسال دفعة تغييرات |
| GET | `/sync/pull` | سحب تغييرات تزايدية |
| POST | `/sync/ack` | تأكيد تطبيق دفعة |
| GET | `/sync/status` | حالة المزامنة للجهاز |

أنواع الكيانات القابلة للدفع من الجهاز: `reporting_period`، `indicator_value`، `incident`
(v0.7)، و`capa_action` و`risk` (v0.14)، و`audit` و`improvement_plan` و`improvement_action`
(v0.15). أي نوع آخر يُرفَض بـ`rejected: unsupported_entity`.

#### 6.8.1 مركز المزامنة الوطني (v0.12 — منفَّذ فعلاً)
| الطريقة | المسار | الوصف | الصلاحية |
|--------|-------|-------|----------|
| GET | `/sync-monitor/overview` | ملخّص الأجهزة والتعارضات | `sync.view` |
| GET | `/sync-monitor/devices?only_stale=` | قائمة أجهزة المزامنة وحالتها | `sync.view` |
| GET | `/sync-monitor/conflicts?include_resolved=&hospital_id=&limit=&offset=` | صفحة تعارضات | `sync.view` |
| POST | `/sync-monitor/conflicts/{id}/resolve` | تسجيل مراجعة/استبعاد تعارض | `sync.manage` |

القراءة والكتابة محكومتان بـ RLS: المستخدم يرى نطاقه فقط. الجهاز **متأخر** إذا مضى
على آخر ظهور له 7 أيام أو أكثر. حلّ التعارض **لا يغيّر أي بيانات**، بل يسجّل القرار
في سجل التدقيق. التفاصيل في الوثيقة 26.

### 6.9 الإدارة والتدقيق
| الطريقة | المسار | الوصف |
|--------|-------|-------|
| GET | `/audit-log` | سجل التدقيق (مفلترة) |
| GET | `/admin/backups` | النسخ الاحتياطي |
| POST | `/admin/backups` | نسخة الآن |
| GET | `/admin/health` | صحة النظام |

#### 6.9.1 سجل التدقيق (v0.11 — منفَّذ فعلاً)
| الطريقة | المسار | الوصف | الصلاحية |
|--------|-------|-------|----------|
| GET | `/audit-log?entity_type=&action=&actor_user_id=&hospital_id=&since=&until=&q=&limit=&offset=` | صفحة من المدخلات (الأحدث أولاً) | `audit.view` |
| GET | `/audit-log/facets` | عدّادات التصفية (أنواع، إجراءات، مستخدمون) | `audit.view` |
| GET | `/audit-log/export.csv` | تصدير CSV (بترميز يفهمه Excel) | `audit.view` |
| GET | `/audit-log/export.xlsx` | تصدير Excel | `audit.view` |

السجل **للقراءة فقط**: لا توجد نقطة تضيف أو تعدّل أو تحذف مدخلة. يُقيَّد `hospital_id`
بنطاق المستخدم تلقائياً، والقراءة محكومة بـ RLS على مستوى الصفوف. الحد الأقصى
للترقيم 200، وللتصدير 5000 صف. التفاصيل في الوثيقة 25.

## 7. أمثلة تفصيلية

### 7.1 إدخال قيمة مؤشر
```json
POST /api/v1/period-values
Idempotency-Key: period_value:0190f2...:0
{
  "indicator_version_id": "0190i...v2",
  "department_id": "0190d...",
  "period_id": "0190p...2026-10",
  "numerator": 12,
  "denominator": 1450,
  "note": "مصدر: سجلات مكافحة العدوى"
}
→ 201
{
  "id": "0190pv...",
  "computed_value": 8.276,
  "unit": "لكل 1000 يوم مريض",
  "status": "draft",
  "target": null,
  "acceptable_range": null,
  "direction": "lower_better",
  "flags": [],
  "rev": 0
}
```

### 7.2 اعتماد فترة
```json
POST /api/v1/period-values/0190pv.../approve
{ "comment_ar": "تمت المراجعة والاعتماد" }
→ 200
{ "id": "0190pv...", "status": "approved", "approved_at": "2026-11-07T21:10:00Z", "rev": 2 }
→ 409 (إن كان معتمداً مسبقاً)
{ "error": { "code": "already_approved", "message_ar": "هذه القيمة معتمدة بالفعل." } }
```

### 7.3 ملخص تحليلي (مسنَد)
```json
GET /api/v1/analytics/summary?hospital_id=0190h...&period=2026-10
→ 200
{
  "basis": "بيانات فعلية معتمدة للفترة 2026-10",
  "disclaimer_ar": "تحليل مساعد آلي ولا يُعد حكماً طبياً.",
  "highlights": [
    { "indicator": "IC-01", "value": 8.28, "target": null, "trend": "up",
      "direction": "lower_better", "note_ar": "ارتفاع عن الشهر السابق",
      "source_periods": ["2026-09","2026-10"] }
  ]
}
```

## 8. قواعد الأعمال المُلزَمة على الخادم
1. لا اعتماد من نفس من أدخل (فصل مهام) → 422 `business_rule_violated`.
2. لا تعديل فترة معتمدة دون صلاحية خاصة → 409 `already_approved`.
3. المقام لا يساوي صفراً لمؤشرات النسبة/المعدل → 400 `validation_failed`.
4. لا مؤشر وطني يُعدَّل من مستشفى → 403 `forbidden`.
5. الوصول خارج نطاق المستخدم → 403 + تسجيل.

## 9. الإصدارات والتوافق
- **`/api/v1`** مستقر؛ الإضافات غير الكاسرة مسموحة.
- أي كسر = `/api/v2` مع فترة توازٍ.
- **توافق خلفي:** عميل قديم يجب أن يعمل مع خادم أحدث (إضافات فقط).

## 10. غير المتزامن (Async Jobs)
- تصدير التقارير الثقيلة: `POST /reports/export` → `202 Accepted` + `job_id`، ثم polling على `/reports/exports/{job_id}`.
- الاستيراد الكبير (T4): `POST /sync/import-bundle` → مهمة خلفية.

## 11. ملاحظات أمنية على الواجهات
- TLS إلزامي، رفض غير المشفّر.
- CORS مُقيَّد بالنطاقات المعروفة.
- تحقق كامل من المدخلات (نوع/طول/نطاق) على الخادم.
- رؤوس أمان: HSTS، CSP، X-Content-Type-Options، Referrer-Policy.
- تسجيل كل طلب حساس في سجل التدقيق.
