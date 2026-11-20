# Twilio phone call setup: step by step (~20 minute)

Is setup ke baad: tumhare phone pe call aayegi, tum Punjabi mein bhaav poochoge, aur bot jawab dega.
Trial account free hai (~$15 credit milta hai, ek call ka kuch cents lagta hai).

## Kaise kaam karta hai
```
Tumhara phone ◄──call──► Twilio ──"kisan ne kya bola" (webhook)──► humara server (laptop)
                                ◄──"ye MP3 sunao" (TwiML)──────────
```
Twilio internet pe hai, humara server laptop pe. Isliye laptop ko ek **public https URL** chahiye.
Ye kaam ek "tunnel" karta hai (cloudflared).

---

## Step 1: Twilio account (website pe khud karo)
1. https://www.twilio.com/try-twilio pe sign up karo aur email + phone verify karo.
2. Console ke home page pe **Account SID** aur **Auth Token** dikhenge. Inhe copy karo.
   ⚠️ Auth Token password jaisa hai: WhatsApp pe mat bhejo, aur GitHub pe kabhi mat daalo.
3. **Phone Numbers → Buy a number** se free trial number lo (US number milega, ye theek hai).

## Step 2: Trial account ki 2 settings
1. **Verified Caller IDs:** jis phone pe call karni hai (tumhara, aur demo ke din judge ka), use verify karo.
   Twilio OTP bhejega. Trial mein sirf verified numbers pe call jaati hai.
2. **Voice → Settings → Geo Permissions → India** ko ON karo. Warna India mein call nahi jaayegi.

## Step 3: `.env` file banao
Project folder mein `.env.example` ki copy banao, uska naam `.env` rakho, aur values bharo:
```
TWILIO_ACCOUNT_SID=AC...
TWILIO_AUTH_TOKEN=...
TWILIO_NUMBER=+1...
PUBLIC_BASE_URL=        <- Step 5 ke baad bharna
ADMIN_TOKEN=koi-bhi-lamba-random-password
```
`.env` file `.gitignore` mein hai, isliye git mein nahi jaayegi.

## Step 4: Server chalao (terminal 1)
```powershell
python -m uvicorn app.main:app --port 8000
```

## Step 5: Tunnel chalao (terminal 2)
cloudflared ek baar install karna hai (ye Cloudflare ka official tool hai, free hai, account nahi chahiye):
```powershell
winget install --id Cloudflare.cloudflared
```
Phir tunnel chalao:
```powershell
cloudflared tunnel --url http://localhost:8000
```
(Install ke baad **naya terminal** kholo, warna `cloudflared` command nahi milegi. Ya pura path use karo:
`& "C:\Program Files (x86)\cloudflared\cloudflared.exe" tunnel --url http://localhost:8000`)

Ye ek URL dega, jaise `https://abcd-efgh.trycloudflare.com`. **Naya URL internet pe chalu hone mein ~1 minute lagta hai**,
utni der browser mein "can't reach" dikhe to ghabrao mat. Phir use `.env` mein `PUBLIC_BASE_URL` pe daalo,
aur **server restart karo** (terminal 1 mein Ctrl+C, phir Step 4 wali command dobara).
⚠️ Har baar cloudflared restart karne pe naya URL milta hai. Tab `.env` badlo aur Step 6 dobara chalao.

## Step 6: Check + webhook set karo (terminal 3)
```powershell
python scripts/twilio_setup.py
```
Ye check karega: `.env` values, kya server internet se khulta hai, Twilio login, aur number.
Agar sab [OK] hai, to webhook set karo (Twilio ko batao ki call aaye to humare server pe bheje):
```powershell
python scripts/twilio_setup.py --apply
```

## Step 7: Test call
```powershell
python scripts/twilio_setup.py --call +91XXXXXXXXXX
```
Ya admin page (`/admin` → "Phone call demo") se bhi call kar sakte ho.

Phone uthao. Pehle Twilio ka trial message aayega, phir koi bhi button dabao. Uske baad:
"ਸਤ ਸ੍ਰੀ ਅਕਾਲ ਜੀ..." → beep → bolo **"ਅੰਮ੍ਰਿਤਸਰ ਮੰਡੀ ਵਿੱਚ ਕਣਕ ਦਾ ਭਾਅ"** → jawab aayega.

Do baar chup raho ya bakwaas bolo, to keypad menu aayega ("ਕਣਕ ਲਈ 1 ਦਬਾਓ...").
Har call admin page ke log mein channel `phone` ke saath dikhegi.

---

## Kuch kaam na kare to
| Dikkat | Hal |
|---|---|
| "An application error has occurred" sunai de | Server ya tunnel band hai, ya `PUBLIC_BASE_URL` purana hai. `twilio_setup.py` chalao. |
| Server log mein `403` | `PUBLIC_BASE_URL` us URL se match nahi karta jo Twilio ko diya. `.env` theek karo, server restart karo, `--apply` dobara chalao. |
| Call hi nahi aati | Number verified nahi hai, ya Geo Permissions mein India OFF hai. |
| Bot "ਆਵਾਜ਼ ਸਾਫ਼ ਨਹੀਂ ਆਈ" hi bolta hai | Beep ke **baad** bolo, aur phone mic ke paas rakho. Recording admin log mein dekho. |
| Jawab aane mein der | Pehli call pe TTS cache khaali hota hai. Doosri baar se fast ho jaata hai. |

## Security (viva mein poocha ja sakta hai)
- **Signature check:** har `/voice/*` request pe `X-Twilio-Signature` check hota hai. Nakli request aaye to 403.
- **Recording URL:** sirf `https://api.twilio.com/` se download hoti hai. Isse koi humare server se
  apne URL pe request nahi karwa sakta, aur humara Auth Token leak nahi hota.
- **`/api/call-me`:** `ADMIN_TOKEN` ke bina nahi chalta. Isse koi humare credit se call nahi karwa sakta.

## Demo day tips
- Demo se 1 ghanta pehle judge ka number verify karwa lo (OTP 1 minute ka kaam hai), ya apne phone se demo do.
- Venue ka internet kharab ho sakta hai, isliye backup ke liye ek call ki screen recording pehle se bana lo.
- Real life mein: Exotel/Knowlarity se Indian toll-free number + missed-call service. Code wahi rahega,
  sirf TwiML ki jagah unka XML format.
