# تصميم قاعدة البيانات
## النظام الوطني لإدارة مؤشرات الأداء الصحي والجودة وسلامة المرضى في اليمن

**الإصدار:** 1.0 — المرحلة الأولى · **الحالة:** مسودة بانتظار الموافقة

---

## الشرح بلغة بسيطة
قاعدة البيانات هي **مكان تخزين المعلومات** بشكل منظّم في جداول (مثل جداول Excel لكن مترابطة).
لدينا **قاعدتان**:
1. **قاعدة محلية (SQLite)** داخل كل مستشفى — تعمل دون إنترنت.
2. **قاعدة مركزية (PostgreSQL)** على الخادم — تجمع بيانات كل المستشفيات.

القاعدتان **متشابهتان في الجداول الأساسية** لتسهيل المزامنة، مع إضافات خاصة بالمزامنة والتدقيق.

---

## 1. مبادئ التصميم

1. **معرّفات فريدة عالمياً (UUIDv7):** كل سجل له معرّف فريد يُولَّد في المستشفى، فلا يتعارض مع غيره عند المزامنة. (UUIDv7 مرتب زمنياً → فهارس أفضل.)
2. **طابع زمني موحّد:** كل سجل فيه `created_at`, `updated_at` (UTC) + `deleted_at` للحذف المنطقي.
3. **حقول المزامنة:** `rev` (رقم الإصدار/المراجعة), `origin_node` (الجهاز المُنشئ), `sync_state`.
4. **الحذف المنطقي (Soft delete):** لا نحذف صفاً فعلياً؛ نعلّمه محذوفاً ليُزامَن الحذف.
5. **سجل تغييرات (Change Log):** لكل جدول قابل للمزامنة، سجل يوضح ما تغيّر.
6. **إصدار المخطط:** جدول `schema_migrations` في كل قاعدة.
7. **لا بيانات شخصية للمرضى:** لا أسماء/هويات؛ فقط قياسات مُجمّعة.

---

## 2. الأنواع المشتركة

| الحقل | النوع | الوصف |
|------|------|-------|
| `id` | TEXT/UUID | معرّف فريد (UUIDv7) |
| `created_at` | TIMESTAMP UTC | وقت الإنشاء |
| `updated_at` | TIMESTAMP UTC | وقت آخر تعديل |
| `deleted_at` | TIMESTAMP NULL | وقت الحذف المنطقي |
| `rev` | INTEGER | رقم المراجعة (يزيد مع كل تعديل) |
| `origin_node` | TEXT | معرّف الجهاز/العقدة المُنشئة |
| `sync_state` | TEXT | `local`, `pending`, `synced`, `conflict` |

---

## 3. الجداول الأساسية (مشتركة بين القاعدتين)

### 3.1 الهيكل المؤسسي
```sql
-- المستويات الإدارية: مركزي / محافظة / مديرية / مستشفى
CREATE TABLE organizations (
  id            TEXT PRIMARY KEY,
  parent_id     TEXT REFERENCES organizations(id),
  level         TEXT NOT NULL,      -- 'central','governorate','district','hospital'
  name_ar       TEXT NOT NULL,
  code          TEXT UNIQUE,        -- رمز رسمي
  -- حقول المزامنة المشتركة
  created_at    TIMESTAMP, updated_at TIMESTAMP, deleted_at TIMESTAMP,
  rev INTEGER DEFAULT 0, origin_node TEXT, sync_state TEXT DEFAULT 'local'
);

CREATE TABLE hospitals (
  id            TEXT PRIMARY KEY,
  organization_id TEXT REFERENCES organizations(id),
  name_ar       TEXT NOT NULL,
  governorate   TEXT,
  code          TEXT UNIQUE,
  is_active     INTEGER DEFAULT 1,
  -- مشتركة
  created_at TIMESTAMP, updated_at TIMESTAMP, deleted_at TIMESTAMP,
  rev INTEGER DEFAULT 0, origin_node TEXT, sync_state TEXT DEFAULT 'local'
);

CREATE TABLE departments (
  id            TEXT PRIMARY KEY,
  hospital_id   TEXT REFERENCES hospitals(id),
  name_ar       TEXT NOT NULL,
  code          TEXT,
  manager_user_id TEXT,             -- مسؤول القسم
  is_active     INTEGER DEFAULT 1,
  created_at TIMESTAMP, updated_at TIMESTAMP, deleted_at TIMESTAMP,
  rev INTEGER DEFAULT 0, origin_node TEXT, sync_state TEXT DEFAULT 'local'
);
```

### 3.2 المستخدمون والصلاحيات
```sql
CREATE TABLE users (
  id            TEXT PRIMARY KEY,
  username      TEXT UNIQUE NOT NULL,
  display_name  TEXT NOT NULL,
  password_hash TEXT,               -- Argon2/bcrypt (على الخادم)
  email         TEXT,
  is_active     INTEGER DEFAULT 1,
  failed_logins INTEGER DEFAULT 0,
  locked_until  TIMESTAMP,
  created_at TIMESTAMP, updated_at TIMESTAMP, deleted_at TIMESTAMP,
  rev INTEGER DEFAULT 0, origin_node TEXT, sync_state TEXT DEFAULT 'local'
);

CREATE TABLE roles (
  id       TEXT PRIMARY KEY,
  code     TEXT UNIQUE NOT NULL,    -- 'central_admin','gov_officer',...
  name_ar  TEXT NOT NULL
);

CREATE TABLE permissions (
  id       TEXT PRIMARY KEY,
  code     TEXT UNIQUE NOT NULL,    -- 'indicator.enter','period.approve',...
  name_ar  TEXT NOT NULL
);

CREATE TABLE role_permissions (
  role_id       TEXT REFERENCES roles(id),
  permission_id TEXT REFERENCES permissions(id),
  PRIMARY KEY (role_id, permission_id)
);

-- ربط المستخدم بجهة ومستوى
CREATE TABLE user_assignments (
  id            TEXT PRIMARY KEY,
  user_id       TEXT REFERENCES users(id),
  scope_type    TEXT NOT NULL,      -- 'central','governorate','hospital','department'
  scope_id      TEXT,               -- معرّف الجهة
  role_id       TEXT REFERENCES roles(id),
  created_at TIMESTAMP, updated_at TIMESTAMP, deleted_at TIMESTAMP,
  rev INTEGER DEFAULT 0, origin_node TEXT, sync_state TEXT DEFAULT 'local'
);
```

### 3.3 مكتبة المؤشرات
```sql
CREATE TABLE indicators (
  id             TEXT PRIMARY KEY,
  code           TEXT NOT NULL,        -- رمز المؤشر
  name_ar        TEXT NOT NULL,
  category       TEXT,                 -- 'patient_safety','infection','clinical','management'
  is_national    INTEGER DEFAULT 0,    -- مؤشر وطني أم خاص بمستشفى
  owner_hospital_id TEXT,              -- NULL للمؤشر الوطني
  created_at TIMESTAMP, updated_at TIMESTAMP, deleted_at TIMESTAMP,
  rev INTEGER DEFAULT 0, origin_node TEXT, sync_state TEXT DEFAULT 'local'
);

-- إصدارات المؤشر (لا تتأثر البيانات التاريخية بتعديل لاحق)
CREATE TABLE indicator_versions (
  id             TEXT PRIMARY KEY,
  indicator_id   TEXT REFERENCES indicators(id),
  version_no     INTEGER NOT NULL,
  definition_ar  TEXT,                 -- تعريف المؤشر
  purpose_ar     TEXT,                 -- الهدف منه
  measure_method TEXT,                 -- طريقة القياس والحساب (وصف)
  unit           TEXT,                 -- وحدة القياس (%, لكل 1000,..., أيام)
  data_source    TEXT,                 -- مصدر البيانات
  frequency      TEXT,                 -- 'monthly','quarterly','annual'
  responsible_party TEXT,              -- الجهة المسؤولة
  target_value   REAL,                 -- القيمة المستهدفة
  acceptable_min REAL,                 -- الحد الأدنى المقبول
  acceptable_max REAL,                 -- الحد الأعلى المقبول
  direction      TEXT NOT NULL,        -- 'higher_better','lower_better','closer_to_target'
  calc_type      TEXT NOT NULL,        -- 'ratio','rate','count','average','composite','value'
  numerator_label   TEXT,              -- وصف البسط
  denominator_label TEXT,              -- وصف المقام
  formula        TEXT,                 -- تعبير حسابي آمن (إن لزم)
  effective_from TIMESTAMP,
  created_at TIMESTAMP, updated_at TIMESTAMP,
  rev INTEGER DEFAULT 0, origin_node TEXT, sync_state TEXT DEFAULT 'local'
);

-- ربط المؤشر بأقسام معيّنة
CREATE TABLE indicator_bindings (
  id             TEXT PRIMARY KEY,
  indicator_id   TEXT REFERENCES indicators(id),
  department_id  TEXT REFERENCES departments(id),
  hospital_id    TEXT,
  created_at TIMESTAMP, updated_at TIMESTAMP, deleted_at TIMESTAMP,
  rev INTEGER DEFAULT 0, origin_node TEXT, sync_state TEXT DEFAULT 'local'
);
```

### 3.4 الفترات والإدخال وسير العمل
```sql
CREATE TABLE periods (
  id             TEXT PRIMARY KEY,
  year           INTEGER NOT NULL,
  month          INTEGER,               -- NULL للفترات الربعية/السنوية
  quarter        INTEGER,
  kind           TEXT NOT NULL,         -- 'monthly','quarterly','annual'
  start_date     DATE, end_date DATE,
  created_at TIMESTAMP, updated_at TIMESTAMP,
  rev INTEGER DEFAULT 0, origin_node TEXT, sync_state TEXT DEFAULT 'local'
);

CREATE TABLE period_values (
  id             TEXT PRIMARY KEY,
  indicator_version_id TEXT REFERENCES indicator_versions(id),
  department_id  TEXT REFERENCES departments(id),
  hospital_id    TEXT,
  period_id      TEXT REFERENCES periods(id),
  numerator      REAL,
  denominator    REAL,
  raw_value      REAL,                  -- القيمة المُدخلة (للأعداد/المتوسطات)
  computed_value REAL,                  -- النتيجة المحسوبة
  note           TEXT,
  status         TEXT NOT NULL DEFAULT 'draft', -- draft,submitted,under_review,approved,rejected
  entered_by     TEXT, approved_by TEXT,
  submitted_at TIMESTAMP, approved_at TIMESTAMP,
  created_at TIMESTAMP, updated_at TIMESTAMP, deleted_at TIMESTAMP,
  rev INTEGER DEFAULT 0, origin_node TEXT, sync_state TEXT DEFAULT 'local'
);

CREATE TABLE approval_steps (
  id             TEXT PRIMARY KEY,
  period_value_id TEXT REFERENCES period_values(id),
  action         TEXT NOT NULL,         -- 'submit','review','approve','reject','return'
  actor_user_id  TEXT,
  comment_ar     TEXT,
  created_at TIMESTAMP, rev INTEGER DEFAULT 0,
  origin_node TEXT, sync_state TEXT DEFAULT 'local'
);
```

### 3.5 الجودة وسلامة المرضى
```sql
CREATE TABLE incidents (
  id             TEXT PRIMARY KEY,
  hospital_id    TEXT REFERENCES hospitals(id),
  department_id  TEXT,
  reported_by    TEXT,                  -- قد يكون مجهولاً (إبلاغ سرّي)
  is_anonymous   INTEGER DEFAULT 0,
  occurred_at    TIMESTAMP,
  severity       TEXT,                  -- 'near_miss','minor','moderate','major','sentinel'
  category       TEXT,                  -- نوع الحادث
  description_ar TEXT,
  status         TEXT DEFAULT 'open',   -- open, investigating, closed
  created_at TIMESTAMP, updated_at TIMESTAMP, deleted_at TIMESTAMP,
  rev INTEGER DEFAULT 0, origin_node TEXT, sync_state TEXT DEFAULT 'local'
);

CREATE TABLE rca_analyses (
  id             TEXT PRIMARY KEY,
  incident_id    TEXT REFERENCES incidents(id),
  team_members   TEXT,                  -- فريق التحليل
  timeline_ar    TEXT,                  -- تسلسل الأحداث
  root_causes_ar TEXT,                  -- الأسباب الجذرية
  status         TEXT DEFAULT 'draft',
  created_at TIMESTAMP, updated_at TIMESTAMP,
  rev INTEGER DEFAULT 0, origin_node TEXT, sync_state TEXT DEFAULT 'local'
);

CREATE TABLE capa_actions (
  id             TEXT PRIMARY KEY,
  source_type    TEXT,                  -- 'incident','rca','audit','risk'
  source_id      TEXT,
  action_ar      TEXT NOT NULL,
  kind           TEXT,                  -- 'corrective','preventive'
  responsible_user_id TEXT,
  due_date       DATE,
  status         TEXT DEFAULT 'open',   -- open, in_progress, done, verified, cancelled
  verified_by    TEXT, verified_at TIMESTAMP,
  created_at TIMESTAMP, updated_at TIMESTAMP, deleted_at TIMESTAMP,
  rev INTEGER DEFAULT 0, origin_node TEXT, sync_state TEXT DEFAULT 'local'
);

CREATE TABLE risks (
  id             TEXT PRIMARY KEY,
  hospital_id    TEXT, department_id TEXT,
  title_ar       TEXT NOT NULL,
  description_ar TEXT,
  likelihood     INTEGER,               -- 1..5
  impact         INTEGER,               -- 1..5
  score          INTEGER,               -- likelihood*impact (محسوب)
  level          TEXT,                  -- low, medium, high, critical
  mitigation_ar  TEXT,
  owner_user_id  TEXT,
  status         TEXT DEFAULT 'open',
  created_at TIMESTAMP, updated_at TIMESTAMP, deleted_at TIMESTAMP,
  rev INTEGER DEFAULT 0, origin_node TEXT, sync_state TEXT DEFAULT 'local'
);

CREATE TABLE audits (
  id             TEXT PRIMARY KEY,
  hospital_id    TEXT, department_id TEXT,
  title_ar       TEXT, checklist_json TEXT,
  conducted_at   DATE, auditor_user_id TEXT,
  score          REAL, status TEXT DEFAULT 'open',
  created_at TIMESTAMP, updated_at TIMESTAMP,
  rev INTEGER DEFAULT 0, origin_node TEXT, sync_state TEXT DEFAULT 'local'
);

CREATE TABLE audit_findings (
  id             TEXT PRIMARY KEY,
  audit_id       TEXT REFERENCES audits(id),
  finding_ar     TEXT, severity TEXT, recommendation_ar TEXT,
  created_at TIMESTAMP, updated_at TIMESTAMP,
  rev INTEGER DEFAULT 0, origin_node TEXT, sync_state TEXT DEFAULT 'local'
);

CREATE TABLE improvement_plans (
  id             TEXT PRIMARY KEY,
  hospital_id    TEXT, department_id TEXT,
  title_ar       TEXT, goal_ar TEXT, measures_json TEXT,
  owner_user_id  TEXT, start_date DATE, end_date DATE,
  status         TEXT DEFAULT 'active',
  created_at TIMESTAMP, updated_at TIMESTAMP,
  rev INTEGER DEFAULT 0, origin_node TEXT, sync_state TEXT DEFAULT 'local'
);

CREATE TABLE documents (
  id             TEXT PRIMARY KEY,
  hospital_id    TEXT,
  title_ar       TEXT, category TEXT,
  status         TEXT DEFAULT 'draft',  -- draft, approved, obsolete
  created_at TIMESTAMP, updated_at TIMESTAMP, deleted_at TIMESTAMP,
  rev INTEGER DEFAULT 0, origin_node TEXT, sync_state TEXT DEFAULT 'local'
);

CREATE TABLE document_versions (
  id             TEXT PRIMARY KEY,
  document_id    TEXT REFERENCES documents(id),
  version_no     INTEGER, file_ref TEXT,  -- مرجع ملف في تخزين المرفقات
  approved_by    TEXT, approved_at TIMESTAMP, review_due DATE,
  created_at TIMESTAMP, rev INTEGER DEFAULT 0,
  origin_node TEXT, sync_state TEXT DEFAULT 'local'
);

CREATE TABLE meetings (
  id             TEXT PRIMARY KEY,
  hospital_id    TEXT,
  title_ar       TEXT, held_at TIMESTAMP, attendees_json TEXT,
  created_at TIMESTAMP, updated_at TIMESTAMP,
  rev INTEGER DEFAULT 0, origin_node TEXT, sync_state TEXT DEFAULT 'local'
);

CREATE TABLE meeting_decisions (
  id             TEXT PRIMARY KEY,
  meeting_id     TEXT REFERENCES meetings(id),
  decision_ar    TEXT, owner_user_id TEXT, due_date DATE,
  status         TEXT DEFAULT 'open',
  created_at TIMESTAMP, updated_at TIMESTAMP,
  rev INTEGER DEFAULT 0, origin_node TEXT, sync_state TEXT DEFAULT 'local'
);
```

### 3.6 سجل التدقيق
```sql
CREATE TABLE audit_log (
  id             TEXT PRIMARY KEY,
  entity_type    TEXT NOT NULL,          -- الجدول/الكيان
  entity_id      TEXT NOT NULL,
  action         TEXT NOT NULL,          -- create, update, delete, approve, login...
  actor_user_id  TEXT,
  before_json    TEXT,                   -- الحالة قبل (JSON)
  after_json     TEXT,                   -- الحالة بعد (JSON)
  at             TIMESTAMP NOT NULL,
  node           TEXT,                   -- الجهاز
  rev INTEGER DEFAULT 0, origin_node TEXT, sync_state TEXT DEFAULT 'local'
);
-- ملاحظة: audit_log لا يُعدَّل ولا يُحذف من المستخدمين العاديين.
```

---

## 4. جداول المزامنة (خاصة بالنظام)

```sql
-- طابور التغييرات المحلية التي لم تُرسل بعد
CREATE TABLE sync_outbox (
  id             TEXT PRIMARY KEY,
  entity_type    TEXT NOT NULL,
  entity_id      TEXT NOT NULL,
  operation      TEXT NOT NULL,          -- upsert, delete
  payload_json   TEXT,                   -- الحالة الكاملة للسجل
  rev            INTEGER,
  created_at     TIMESTAMP NOT NULL,
  attempts       INTEGER DEFAULT 0,
  last_error     TEXT,
  state          TEXT DEFAULT 'pending'  -- pending, sending, done, failed
);

-- مفاتيح منع التكرار (Idempotency) لمنع إنشاء نفس السجل مرتين
CREATE TABLE sync_idempotency (
  key            TEXT PRIMARY KEY,       -- مثلاً: entity_id + rev
  entity_type    TEXT,
  applied_at     TIMESTAMP
);

-- مؤشر آخر مزامنة لكل اتجاه
CREATE TABLE sync_cursor (
  id             TEXT PRIMARY KEY,       -- اسم المؤشر: 'pull_hospital_<id>'
  last_pulled_at TIMESTAMP,
  last_pushed_at TIMESTAMP,
  last_server_rev TEXT
);

-- سجل التغييرات من الخادم (للسحب التزايدي)
CREATE TABLE change_log (
  server_seq     BIGINT PRIMARY KEY,     -- تسلسل متزايد على الخادم
  entity_type    TEXT, entity_id TEXT,
  operation      TEXT, payload_json TEXT,
  at             TIMESTAMP
);
```

---

## 5. الفروق بين القاعدتين

| الجانب | SQLite (محلي) | PostgreSQL (مركزي) |
|-------|----------------|---------------------|
| النطاق | بيانات مستشفى واحد | كل المستشفيات |
| الفهارس | فهارس أساسية | فهارس موسّعة + فهارس تجميع |
| العزل | المستشفى واحد أصلاً | **RLS** لعزل المستشفيات |
| البحث النصي | بسيط (FTS5 اختياري) | Full-text موسّع |
| التجميع | محدود | Views/Materialized Views للوحات |
| التشفير | خيار SQLCipher | تشفير القرص/الحقول الحساسة |
| النسخ | نسخ ملف دوري | WAL + نسخ مجدولة + نسخة بعيدة |

### 5.1 مثال عزل الصفوف في PostgreSQL (RLS)
```sql
ALTER TABLE period_values ENABLE ROW LEVEL SECURITY;

CREATE POLICY hospital_isolation ON period_values
  USING (
    hospital_id = current_setting('app.current_hospital_id', true)
    OR current_setting('app.role', true) IN ('central_admin','gov_officer')
  );
-- 'gov_officer' يُقيَّد لاحقاً بمحافظته عبر سياسة إضافية.
```

---

## 6. الفهرس المقترح (Indexes)

```sql
-- محلياً ومركزياً
CREATE INDEX idx_pv_period_dept   ON period_values(period_id, department_id);
CREATE INDEX idx_pv_status        ON period_values(status);
CREATE INDEX idx_ind_code         ON indicators(code);
CREATE INDEX idx_inc_hospital     ON incidents(hospital_id, status);
CREATE INDEX idx_capa_due          ON capa_actions(due_date, status);
CREATE INDEX idx_auditlog_entity   ON audit_log(entity_type, entity_id, at);
CREATE INDEX idx_outbox_state      ON sync_outbox(state, created_at);
-- مركزياً فقط
CREATE INDEX idx_changelog_seq     ON change_log(server_seq);
CREATE INDEX idx_pv_hospital_time  ON period_values(hospital_id, created_at);
```

---

## 7. حساب قيم المؤشرات (قواعد)

| calc_type | المعادلة | مثال |
|----------|---------|------|
| `ratio` | (بسط/مقام) × 100 | نسبة الالتزام بنظافة اليدين |
| `rate` | (بسط/مقام) × 1000 أو 10000 | معدل العدوى لكل 1000 يوم مريض |
| `count` | القيمة كما هي | عدد الحوادث المُبلَّغ عنها |
| `average` | مجموع/عدد | متوسط زمن الانتظار (أيام) |
| `composite` | تجميع مرجّح لمؤشرات فرعية | مؤشر جودة مركّب |
| `value` | قيمة مستهدفة مطلقة | نسبة تغطية |

**قاعدة اتجاه التحسن:**
- `higher_better`: التحسن عند ارتفاع القيمة (مثال: نسبة الالتزام).
- `lower_better`: التحسن عند انخفاض القيمة (مثال: معدل العدوى، الحوادث).
- `closer_to_target`: التحسن عند الاقتراب من قيمة مستهدفة من أي جهة.

**قاعدة الأمانة:** لا تُخترع قيمة؛ إن نقص البسط أو المقام تبقى القيمة **غير مكتملة** وتُعلَّم بوضوح.

---

## 8. الترحيلات (Migrations) وإصدار المخطط
```sql
CREATE TABLE schema_migrations (
  version     TEXT PRIMARY KEY,
  applied_at  TIMESTAMP NOT NULL,
  description TEXT
);
```
- كل تغيير في المخطط = ملف ترحيل مُرقّم، يُطبَّق على القاعدة المحلية والمركزية.
- لا يُعدَّل مخطط موجود مباشرة؛ يُضاف ترحيل جديد (توافق خلفي قدر الإمكان).

---

## 9. ملاحظات أمنية على البيانات
- كلمات المرور **لا تُخزَّن محلياً كنص أبداً**؛ المصادقة الأساسية على الخادم، والمحلي يعمل بجلسة موثوقة ومحدودة.
- المرفقات تُخزَّن كمراجع (file_ref) لا داخل قاعدة البيانات (للتقليل الحجم).
- **لا حقول لأسماء مرضى أو أرقام هوية** في أي جدول.
- سجل التدقيق يُقيَّد تعديله على الخادم (يُنشأ فقط، لا يُحدَّث من المستخدم).

---

## 10. ما لم يُحسم بعد (يُقرَّر عند التنفيذ)
- هل نستخدم SQLCipher لتشفير القاعدة المحلية بالكامل أم تشفير حقول فقط؟
- هل نضيف FTS5 للبحث العربي محلياً؟
- شكل تخزين المرفقات (MinIO مقابل مجلد مُدار) في البيئة النهائية.
