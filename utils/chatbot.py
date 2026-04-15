import requests

def send_telegram(token, chat_id, msg, parse_mode="HTML", timeout=10):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        res = requests.post(
            url,
            data={
                "chat_id": chat_id,
                "text": msg,
                "parse_mode": parse_mode
            },
            timeout=timeout
        )
        if res.status_code == 200:
            return True
        else:
            print("Telegram error:", res.text)
            return False
    except Exception as e:
        print("Telegram exception:", e)
        return False