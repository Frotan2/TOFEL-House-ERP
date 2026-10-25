# Customer updates — English and Dari / به‌روزرسانی برای مشتری

## Current status / وضعیت فعلی

The update feature is under safety qualification and **not enabled for real
school records**. The shipped channel is disabled until the provider completes the
release and Owner acceptance gates (#12, #36). Until then, *Check for Updates*
explains that the provider has paused updates and changes nothing.

این قابلیت ساخته و آزمایش شده است، اما **برای سوابق واقعی مکتب فعال نیست**.
تا زمانی که ارائه‌دهنده دروازه‌های انتشار و پذیرش مالک را تکمیل نکند، دکمهٔ
«بررسی به‌روزرسانی» فقط پیام می‌دهد و هیچ چیزی را تغییر نمی‌دهد.

## What the owner sees / مالک چه می‌بیند

Two buttons in the TOEFL House ERP window, separate from Install and Repair:

| Button | English | دری |
| --- | --- | --- |
| Check for Updates | Downloads the provider's signed release information and asks the safety engine whether this computer may update. It changes nothing. | معلومات نسخهٔ امضاشدهٔ ارائه‌دهنده را می‌گیرد و از موتور ایمنی می‌پرسد که آیا این کمپیوتر می‌تواند به‌روز شود. هیچ چیزی را تغییر نمی‌دهد. |
| Install Update | Asks for confirmation, repeats every check, and only then installs the update. | تأیید می‌خواهد، همهٔ بررسی‌ها را تکرار می‌کند و تنها پس از آن به‌روزرسانی را نصب می‌کند. |

Every message is shown in English and Dari. The version number is shown with the
result. No terminal, Git, Docker command or database command is ever needed.

هر پیام به انگلیسی و دری نمایش داده می‌شود. شمارهٔ نسخه همراه نتیجه نشان داده
می‌شود. هیچ ترمینال، Git، فرمان Docker یا فرمان دیتابیس لازم نیست.

## What the updater checks before it touches anything

1. The provider signature on the release, using a key installed separately on
   this computer (a checksum alone is never accepted as identity).
2. The exact version, release sequence, source revision and prebuilt image
   identity — the customer PC never builds anything.
3. A supported upgrade path from the installed version.
4. The existing site configuration, credentials and the named database volume.
5. Enough free disk space.
6. A **verified, encrypted backup on a separate drive**, whose artifacts still
   match the backup receipt.
7. A signed Owner recovery and key-custody authorization, bound to that backup.
8. That no previous update is still unfinished.
9. That the downloaded image still has the exact size, SHA-256 and image
   identity the signed release promised — checked again immediately before the
   update is applied.
10. That every existing student, payment, invoice, book, class, attendance and
    payroll record is still there afterwards, with the same counts and the same
    links between records. If any count cannot be read, the update stops before
    the first change instead of assuming the data is safe.

The image is downloaded only after the release information has passed every
check, and a verified update permission expires after 30 minutes, so a stale or
repeated step is refused rather than executed twice.

If any item cannot be verified, the update is refused before the first change.
A release cannot switch these requirements off: a manifest that does not demand
a verified backup and a signed Owner authorization is rejected as invalid.

### بررسی‌های پیش از هر تغییر

۱. امضای ارائه‌دهنده با کلیدی که جداگانه روی این کمپیوتر نصب شده است.
۲. نسخهٔ دقیق، شمارهٔ ترتیب، نسخهٔ منبع و هویت تصویر آماده — کمپیوتر مشتری
هیچ چیزی را نمی‌سازد.
۳. مسیر ارتقای پشتیبانی‌شده از نسخهٔ نصب‌شده.
۴. تنظیمات سایت، اسناد ورود و حجم نام‌دار دیتابیس.
۵. فضای کافی دیسک.
۶. **بکاپ رمزگذاری‌شده و تأییدشده روی یک درایو جداگانه** که فایل‌های آن با
رسید بکاپ مطابقت داشته باشد.
۷. اجازهٔ امضاشدهٔ مالک برای بازیابی و نگهداری کلید، متصل به همان بکاپ.
۸. اینکه هیچ به‌روزرسانی قبلی ناتمام نمانده باشد.

۹. اینکه فایل تصویر دانلودشده هنوز همان اندازه، همان SHA-256 و همان هویت
تصویر وعده‌داده‌شده در نسخهٔ امضاشده را دارد — درست پیش از تطبیق دوباره
بررسی می‌شود.
۱۰. اینکه همهٔ سوابق موجود شاگردان، پرداخت‌ها، بل‌ها، صنوف، حاضری و معاشات
پس از به‌روزرسانی باقی مانده‌اند؛ با همان شمار و همان روابط میان سوابق. اگر
شمردن هر سابقه ممکن نباشد، به‌روزرسانی پیش از نخستین تغییر متوقف می‌شود و
فرض نمی‌شود که داده‌ها سالم‌اند.

فایل تصویر تنها پس از گذشتن معلومات نسخه از همهٔ بررسی‌ها دانلود می‌شود و
اجازهٔ تأییدشده پس از ۳۰ دقیقه منقضی می‌گردد؛ بنابراین یک مرحلهٔ کهنه یا
تکرارشده رد می‌شود و دو بار اجرا نمی‌گردد.

اگر هر مورد تأیید نشود، به‌روزرسانی پیش از نخستین تغییر رد می‌شود. یک نسخه
نمی‌تواند این شرط‌ها را خاموش کند: مانیفستی که بکاپ تأییدشده و اجازهٔ امضاشدهٔ
مالک را لازم نداند، نامعتبر شمرده می‌شود.

## Safe recovery / بازیابی ایمن

If an update stops, the window explains the state in both languages:

* **The update was refused before installation** — no installation change was
  started. Follow the displayed support instructions.
* **An import or apply step failed** — services are not automatically restarted,
  even when the database migration did not start; storage may be unavailable.
  Keep the installation intact and ask trusted support for a recovery decision.
* **The update needs a recovery decision** — do **not** reinstall, do not delete
  data, do not reset Docker and do not restore over the live site. Keep this
  folder, copy the safe support status, and contact trusted support. The journal
  blocks a second update until this is resolved.

اگر به‌روزرسانی متوقف شود، پنجره وضعیت را به هر دو زبان توضیح می‌دهد:

* **به‌روزرسانی پیش از نصب رد شد** — تغییر نصب آغاز نشد؛ رهنمایی روی صفحه را دنبال کنید.
* **واردکردن تصویر یا تطبیق نسخه ناکام شد** — سرویس‌ها خودکار دوباره آغاز نمی‌شوند؛ وضعیت ذخیره‌سازی باید تأیید شود. نصب موجود را حفظ و با پشتیبانی مطمئن تماس بگیرید.
* **به‌روزرسانی نیاز به تصمیم بازیابی دارد** — دوباره نصب نکنید، داده‌ها را حذف
نکنید، Docker را بازنشانی نکنید و روی سایت زنده بازیابی نکنید. این پوشه را
نگه دارید، وضعیت ایمن پشتیبانی را کاپی کنید و با پشتیبانی مورد اعتماد تماس
بگیرید. دفتر روزنامه تا حل شدن این وضعیت، به‌روزرسانی دوم را متوقف می‌کند.

## Provider: enabling a channel / ارائه‌دهنده: فعال‌سازی کانال

1. Build and verify the customer package as usual, then sign it:

   ```bash
   python3 tools/release/create_update_bundle.py bundle \
     --release-dir <package>/product/release \
     --private-key <offline-key>.pem --key-id <key-id> \
     --out <channel>/stable --trust-store-out <secure>/trust-store.json \
     --target-schema-version frappe-v16-<release> --copy-archive
   ```

   The tool signs only what the package already says: the release status and
   the production authorization are copied from `release-manifest.json`, so a
   `TEST PACKAGE - NO REAL DATA` / `REJECT` package produces a signed update
   that every customer engine refuses.

   The tool copies the release status and production authorization from the
   package manifest; it cannot invent authorization. It re-verifies its own
   output with the shipped engine.

2. Publish `index.json`, `update.json`, `update.json.sig` and the image archive
   at the `metadata_url` host allowlist.
3. Install `trust-store.json` separately on the customer PC at
   `product\data\updates\trust-store.json` (never download the trust anchor from
   the update server).
4. Set `product/updates/channel.json` to `"enabled": true` and the real
   provider host, then re-issue the customer package.
5. Record the Owner recovery authorization for the current verified backup:

   ```bash
   python3 tools/release/create_update_bundle.py sign \
     --document recovery-authorization.json --private-key <offline-key>.pem \
     --key-id <key-id> --document-type recovery --out recovery-authorization.sig
   ```

## Never / هرگز

* Never delete the Docker volume, run `docker system prune`, or reset Docker to
  "fix" an update.
* Never restore a backup over the live site; restore is a separate, Owner-gated
  operation.
* Never rebuild the image on the customer PC.
* Never install an update whose signature, backup or recovery authorization is
  missing — the updater will refuse, and it is correct to do so.

* هرگز حجم Docker را حذف نکنید، `docker system prune` را اجرا نکنید و برای
«درست کردن» به‌روزرسانی، Docker را بازنشانی نکنید.
* هرگز بکاپ را روی سایت زنده بازیابی نکنید.
* هرگز تصویر را روی کمپیوتر مشتری نسازید.
* هرگز به‌روزرسانی‌ای را که امضا، بکاپ یا اجازهٔ بازیابی ندارد نصب نکنید؛
برنامه آن را رد می‌کند و این رفتار درست است.
