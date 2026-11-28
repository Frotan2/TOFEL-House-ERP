# The TOEFL House brand

`toefl-house-logo-official.png` is the official logo supplied by the Owner
(1523 x 728, transparent background). It is the same identity as
https://toeflhouse.pages.dev/. Every product copy below was made from this file
by proportional scaling, transparent padding or a white background only. The
logo is never redrawn, recoloured or stretched.

| Colour | Hex | Where it comes from |
|---|---|---|
| Red | `#E40613` | "TOEFL" in the logo |
| Grey | `#878787` | the house outline |
| Black | `#000000` | "The", "HOUSE", Dari name, tagline |

White text on `#E40613` is 4.9:1 (WCAG AA). The darker hover red `#B80510` is 6.9:1.

| File | Used for |
|---|---|
| `apps/toefl_house/toefl_house/public/images/toefl_house_logo.png` | sign-in page, desk loading screen |
| `.../toefl_house_logo_square.png` | desk app logo (square slots) |
| `.../toefl_house_favicon.png` | browser tab icon |
| `.../toefl_house_logo_print.jpg` | letter head on invoices, receipts and other prints (embedded, works offline) |
| `product/windows/toefl-house-logo.png` | Windows launcher window |
| `product/windows/toefl-house.ico` | launcher, desktop shortcut and Setup EXE icon |

Colours are applied in `public/css/th_brand.css` (native desk and sign-in)
and in the `--th-accent` tokens in `public/css/th_design_system.css`.

To replace the logo later, put the new official file here and regenerate the
copies at the same names; no code change is needed.
