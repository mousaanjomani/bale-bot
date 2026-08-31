# بات پیام‌رسان بله + داشبورد مدیریت

بات بله با داشبورد وب فارسی برای نصب روی سرور ویندوزی مشتری، به همراه
بروزرسانی خودکار از GitHub Releases.

## معماری

```
C:\BaleBot\
├── app\      ← کد برنامه (هنگام بروزرسانی جایگزین می‌شود)
├── data\     ← config.json ، دیتابیس، لاگ‌ها (همیشه حفظ می‌شود)
├── venv\     ← محیط پایتون
└── run_bot.ps1  ← حلقه نگهبان (سرویس)
```

- **بات:** پایتون، اتصال به Bale Bot API (`tapi.bale.ai`) با long-polling
- **داشبورد:** Flask + Waitress روی پورت 8585 — وضعیت بات، کاربران،
  پیام‌ها، تنظیمات (توکن، متن‌ها، رمز مدیر)، لاگ‌ها و دکمه بروزرسانی
- **سرویس:** Scheduled Task ویندوز (`BaleBot`) که هنگام بوت اجرا و در صورت
  کرش/بروزرسانی دوباره راه‌اندازی می‌شود

## نصب روی سرور مشتری

PowerShell را **به عنوان Administrator** باز کنید و اجرا کنید:

```powershell
irm https://raw.githubusercontent.com/mousaanjomani/bale-bot/main/installer/install.ps1 -OutFile $env:TEMP\balebot-install.ps1; powershell -ExecutionPolicy Bypass -File $env:TEMP\balebot-install.ps1
```

نصاب مسیر نصب را می‌پرسد (Enter = `C:\BaleBot`).
پس از نصب: داشبورد روی `http://<server-ip>:8585` (کاربر `admin`).

## انتشار نسخه جدید (روی سیستم توسعه)

```powershell
.\scripts\release.ps1 -Version 0.2.0 -Notes "توضیح تغییرات"
```

مشتری در داشبورد روی «بروزرسانی» کلیک می‌کند؛ نسخه جدید دانلود، نصب و
سرویس به صورت خودکار ری‌استارت می‌شود.

## اجرای محلی برای توسعه

```powershell
pip install -r requirements.txt
python main.py
```

داشبورد: http://localhost:8585 (کاربر/رمز پیش‌فرض: admin / admin)
