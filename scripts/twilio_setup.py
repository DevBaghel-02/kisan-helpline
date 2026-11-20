"""
TWILIO SETUP CHECKER.

  python scripts/twilio_setup.py                     -> sab check karo (kuch badalta nahi)
  python scripts/twilio_setup.py --apply             -> Twilio number ka webhook humare server pe set karo
  python scripts/twilio_setup.py --call +91XXXXXXXXXX -> us number pe test call karo

Check karta hai: .env values, Twilio login, trial number, webhook, aur kya public URL se
server sach mein khulta hai (Twilio ko bhi wahi URL chahiye).
"""
import json
import os
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app.config import load_env  # noqa: E402

OK, BAD = "  [OK] ", "  [!!] "


def main():
    load_env()
    need = ["TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_NUMBER", "PUBLIC_BASE_URL"]
    missing = [k for k in need if not os.environ.get(k) or "xxxx" in os.environ[k] or "example" in os.environ[k]]
    print("1. .env values")
    if missing:
        print(BAD + f"Ye bharo (.env file mein): {missing}  -> .env.example dekho")
        return
    print(OK + "sab values hain")

    base = os.environ["PUBLIC_BASE_URL"].rstrip("/")
    print(f"2. Public URL: {base}")
    try:
        with urllib.request.urlopen(base + "/api/crops", timeout=10) as r:
            print(OK + f"server internet se khul raha hai ({len(json.load(r)['crops'])} fasalein)")
    except Exception as e:
        print(BAD + f"server nahi khula: {e}\n       Server chal raha hai? Tunnel chal raha hai? URL sahi copy kiya?")

    from twilio.base.exceptions import TwilioRestException
    from twilio.rest import Client
    client = Client(os.environ["TWILIO_ACCOUNT_SID"], os.environ["TWILIO_AUTH_TOKEN"])
    print("3. Twilio login")
    try:
        acc = client.api.v2010.accounts(os.environ["TWILIO_ACCOUNT_SID"]).fetch()
        print(OK + f"account '{acc.friendly_name}' ({acc.type})")
    except TwilioRestException as e:
        print(BAD + f"login fail: {e.msg}  -> SID/Auth Token dobara copy karo")
        return

    print("4. Twilio number aur webhook")
    nums = client.incoming_phone_numbers.list(phone_number=os.environ["TWILIO_NUMBER"])
    if not nums:
        print(BAD + f"{os.environ['TWILIO_NUMBER']} is account mein nahi mila. Console > Phone Numbers dekho.")
        return
    num, want = nums[0], base + "/voice/incoming"
    print(f"       abhi webhook: {num.voice_url or '(khaali)'} [{num.voice_method}]")
    if num.voice_url == want and num.voice_method == "POST":
        print(OK + "webhook sahi hai")
    elif "--apply" in sys.argv:
        num.update(voice_url=want, voice_method="POST")
        print(OK + f"webhook set kar diya: {want}")
    else:
        print(BAD + f"webhook {want} hona chahiye. Set karne ke liye: python scripts/twilio_setup.py --apply")

    if "--call" in sys.argv:
        to = sys.argv[sys.argv.index("--call") + 1]
        print(f"5. Test call -> {to}")
        try:
            call = client.calls.create(to=to, from_=os.environ["TWILIO_NUMBER"], url=want)
            print(OK + f"call ja rahi hai (sid {call.sid}). Phone uthao, trial message ke baad koi button dabao.")
        except TwilioRestException as e:
            print(BAD + f"call fail: {e.msg}")
            print("       Trial account: number 'Verified Caller IDs' mein hona chahiye, aur")
            print("       Voice > Settings > Geo permissions mein India ON hona chahiye.")


if __name__ == "__main__":
    main()
