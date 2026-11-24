"""Проверяет свободные слоты на подачу документов на ВНЖ в посольстве Австрии (Астана)
и присылает уведомление в Telegram, если слот появился. Только стандартная библиотека Python."""
import http.cookiejar
import os
import re
import sys
import time
import urllib.parse
import urllib.request

BASE = "https://appointment.bmeia.gv.at/"
START_URL = BASE + "?fromSpecificInfo=True&Office=ASTANA"
OFFICE = "ASTANA"
CALENDAR_ID = "20213868"  # Aufenthaltstitel/Вид на жительство
TOKEN = os.environ["TG_TOKEN"]
CHAT_ID = os.environ["TG_CHAT_ID"]
RUN_MINUTES = int(os.environ.get("RUN_MINUTES", "55"))   # сколько минут работает один запуск
INTERVAL_SEC = int(os.environ.get("INTERVAL_SEC", "120"))  # пауза между проверками
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0 Safari/537.36")


def send(text):
    data = urllib.parse.urlencode({"chat_id": CHAT_ID, "text": text,
                                   "disable_web_page_preview": "true"}).encode()
    urllib.request.urlopen(f"https://api.telegram.org/bot{TOKEN}/sendMessage", data, timeout=30).read()


def check():
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    opener.addheaders = [("User-Agent", UA)]

    def post(data):
        with opener.open(BASE, urllib.parse.urlencode(data).encode(), timeout=30) as r:
            return r.read().decode("utf-8", "replace")

    opener.open(START_URL, timeout=30).read()
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
                send(f"⚠️ Бот не может проверить сайт записи уже ~20 минут: {e}")
        time.sleep(INTERVAL_SEC)


if __name__ == "__main__":
    main()
