"""Проверяет свободные слоты на подачу документов на ВНЖ в посольстве Австрии (Астана)
и присылает уведомление в Telegram, если слот появился. Только стандартная библиотека Python."""
import http.cookiejar
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://appointment.bmeia.gv.at/"
START_URL = BASE + "?fromSpecificInfo=True&Office=ASTANA"
OFFICE = "ASTANA"
CALENDAR_ID = "20213868"  # Aufenthaltstitel/Вид на жительство
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "")
TOKEN = os.environ.get("TG_TOKEN", "")
CHAT_ID = os.environ.get("TG_CHAT_ID", "")
RUN_MINUTES = int(os.environ.get("RUN_MINUTES", "55"))   # сколько минут работает один запуск
INTERVAL_SEC = int(os.environ.get("INTERVAL_SEC", "120"))  # пауза между проверками
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0 Safari/537.36")


def retry(fn, attempts=5):
    """Повторяет при временных сбоях сети и при 429 от Telegram."""
    for i in range(attempts):
        try:
            return fn()
        except urllib.error.HTTPError as e:
            if e.code != 429 or i == attempts - 1:
                raise
            m = re.search(r'"retry_after":\s*(\d+)', e.read().decode("utf-8", "replace"))
            wait = int(m.group(1)) if m else 30
            print("Telegram 429, жду", wait, "сек", flush=True)
            time.sleep(wait + 1)
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            if i == attempts - 1:
                raise
            print("сбой сети:", e, "— повтор", flush=True)
            time.sleep(10 * (i + 1))


def send_ntfy(text):
    req = urllib.request.Request(f"https://ntfy.sh/{NTFY_TOPIC}", data=text.encode("utf-8"),
                                 headers={"Title": "Termin Astana", "Priority": "urgent",
                                          "Click": START_URL})
    retry(lambda: urllib.request.urlopen(req, timeout=30).read())


def send_tg(text):
    data = urllib.parse.urlencode({"chat_id": CHAT_ID, "text": text,
                                   "disable_web_page_preview": "true"}).encode()
    retry(lambda: urllib.request.urlopen(
        f"https://api.telegram.org/bot{TOKEN}/sendMessage", data, timeout=30).read(), attempts=2)


def send(text):
    """Шлёт в ntfy (основной канал) и в Telegram (запасной). Ошибка — только если не дошло никуда."""
    ok = False
    for name, fn in (("ntfy", send_ntfy), ("telegram", send_tg)):
        if name == "ntfy" and not NTFY_TOPIC or name == "telegram" and not TOKEN:
            continue
        try:
            fn(text)
            ok = True
            print("отправлено:", name, flush=True)
        except Exception as e:
            print("не отправлено в", name, ":", e, flush=True)
    if not ok:
        raise RuntimeError("уведомление не доставлено ни в один канал")


def check():
    return retry(_check, attempts=3)


def _check():
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    opener.addheaders = [("User-Agent", UA)]

    def post(data):
        with opener.open(BASE, urllib.parse.urlencode(data).encode(), timeout=45) as r:
            return r.read().decode("utf-8", "replace")

    opener.open(START_URL, timeout=45).read()
    base = {"Language": "ru", "Office": OFFICE, "CalendarId": CALENDAR_ID}
    post({**base, "Command": "дальше"})
    html = post({**base, "PersonCount": "1", "Command": "дальше"})

    week = re.search(r"Неделя\s*([\d.]+\s*-\s*[\d.]+)", html)
    if not week:
        raise RuntimeError("страница записи выглядит не так, как ожидалось")
    # Свободный слот = радио-кнопка выбора времени в таблице
    slots = [m for tag in re.findall(r"<input[^>]*>", html) if 'type="radio"' in tag
             for m in re.findall(r'value="([^"]+)"', tag)]
    return week.group(1).strip(), slots


def main():
    if "--test" in sys.argv:
        week, slots = check()
        send(f"✅ Бот работает. Сейчас: неделя {week}, свободных слотов: {len(slots)}. "
             f"Напишу, как только появится слот (Астана, ВНЖ).")
        return
    end = time.time() + RUN_MINUTES * 60
    last, errors = None, 0
    while time.time() < end:
        try:
            week, slots = check()
            errors = 0
            print(time.strftime("%H:%M"), "неделя", week, "| слотов:", len(slots), flush=True)
            if slots and slots != last:
                send(f"🚨 Появились слоты! Посольство Астана, ВНЖ\nНеделя {week}\n"
                     + "\n".join(slots[:15]) + f"\n\nЗаписаться: {START_URL}")
            last = slots
        except Exception as e:  # сеть/сайт временно недоступны — пробуем дальше
            errors += 1
            print("ошибка:", e, flush=True)
            if errors == 10:
                try:
                    send(f"⚠️ Бот не может проверить сайт записи уже ~20 минут: {e}")
                except Exception as e2:
                    print("не удалось отправить предупреждение:", e2, flush=True)
        time.sleep(INTERVAL_SEC)


if __name__ == "__main__":
    main()
