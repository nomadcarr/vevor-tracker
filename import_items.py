import requests

BASE_URL = "https://vevor-tracker-production.up.railway.app"

items = [
    {"barcode": "MGYCSLBYCTFDG4UYPV2",      "order_number": "",      "name": "пясъчна помпа - заявки"},
    {"barcode": "BTZEK1JTJXGYIGI3C001V0",    "order_number": "28772", "name": "Удължена Бар Маса"},
    {"barcode": "CKKMJ3300LBSAPPKZV2",       "order_number": "28821", "name": "механизъм за плъзгаща порта"},
    {"barcode": "YMQJDJTLOGPEATQEJV0",        "order_number": "28524", "name": "лост за трупи"},
    {"barcode": "JSYHZZC421FTD87BW001V0",     "order_number": "28514", "name": "комплект 2 лехи"},
    {"barcode": "SDXWS15X7X7FF8XA0V0",        "order_number": "28536", "name": "оранжерия"},
    {"barcode": "LJQXHTGDGQ2IPCCGVV0",        "order_number": "28404", "name": "теглич"},
    {"barcode": "GYWQPTJRGJPJSGQJDV0",        "order_number": "28290", "name": "Шипон пистолет"},
    {"barcode": "QSYYTSFBZBJQPTEY4V2",        "order_number": "7182",  "name": "ледогенератор"},
    {"barcode": "ZDBTMSZBJMIN27PNEV2",         "order_number": "",      "name": "малък черен ледогенератор"},
    {"barcode": "CLJGTJ2GDSSXOFYCV001V0",     "order_number": "28226", "name": "ремъци за закрепване"},
    {"barcode": "BBPPPPE416L12HNJ1V2",         "order_number": "28214", "name": "раница пръскачка"},
    {"barcode": "KSSJGQKZSH35MRQPNV0",        "order_number": "26759", "name": "Автоматична Макара с Градински Маркуч 35м"},
    {"barcode": "JSJS322MYDDMEUEN5001V0",      "order_number": "25877", "name": "Голям метален кокошарник за двор 2*3*2M"},
    {"barcode": "PVCBRRJTZYGJ6Z5W7V2",        "order_number": "25399", "name": "Пистолет за горещ въздух 1600W 600°C с 17 аксесоара"},
    {"barcode": "YSCJ4MBS0000B7WIY001V0",     "order_number": "24847", "name": "Дървен подов шкаф за баня регулируем рафт бял"},
    {"barcode": "BXSYSCBSG440FYILKV2",         "order_number": "23688", "name": "Преносима медицинска везна 200кг"},
    {"barcode": "YSCJ4CT2MBS0HWI0D001V0",     "order_number": "23333", "name": "Дървен шкаф за баня с 4 чекмеджета"},
    {"barcode": "JQWLQ85LBS6KPAOVX001V0",     "order_number": "28180", "name": "хранилка за кокошки"},
    {"barcode": "JSFXZZC631FTKXKVH001V0",     "order_number": "28099", "name": "мрежа за лехи"},
    {"barcode": "SCXJJHSWTMFFW86ZUV0",         "order_number": "28138", "name": "стригане на животни"},
    {"barcode": "QKLR9800W3042CKX1V2",         "order_number": "7146",  "name": "за шоколад (от заявки)"},
    {"barcode": "JLKMQGGDS220V24CSV2",          "order_number": "",      "name": "врати за кокошарник метална"},
    {"barcode": "XXSYTTQJ1550L3I78V2",          "order_number": "27720", "name": "мини понички"},
    {"barcode": "JTSZWSL8W12F5VOMTV0",          "order_number": "",      "name": "Оранжерия от заявки"},
    {"barcode": "SYTMDDJRJSYSYQFR9V2",          "order_number": "7060",  "name": "месомелачка от заявки"},
    {"barcode": "SYYTSFBZBJX3K9FO7001V2",       "order_number": "",      "name": "Ледогенератор с туба 4"},
    {"barcode": "SYYTSFBZBJX2PWUUX001V2",       "order_number": "",      "name": "Ледогенератор с туба 3"},
    {"barcode": "YTSZBJFB120LTIHJP001V2",        "order_number": "",      "name": "Ледогенератор с туба 2"},
    {"barcode": "YTSZBJFB90LBX1S0G001V2",        "order_number": "",      "name": "Ледогенератор с туба"},
    {"barcode": "ZXGBQTYYEZYZWYNL0V0",           "order_number": "27101", "name": "Бебешка люлка"},
    {"barcode": "SQBXHCTSHWXCEKOO5001V2",        "order_number": "",      "name": "Сейф за пистолет чекмедже"},
    {"barcode": "PYMKMJNLCTPYKORE9001V2",        "order_number": "",      "name": "Соларен мотор за врата"},
    {"barcode": "PVCBRRJTZWGJ7OPJ8V2",           "order_number": "26078", "name": "Пистолет за заваряване на пластмаса"},
    {"barcode": "DLZB60102INCVF8HX001V0",        "order_number": "26375", "name": "Покривки за правоъгълни маси"},
    {"barcode": "JQFHQEKZX36DVQS9A001V2",        "order_number": "26282", "name": "инкубатор за 36 яйца"},
    {"barcode": "ZHSKU00000000000469",            "order_number": "23270", "name": "соларен комплект"},
    {"barcode": "JQWSQ25BSX0000001V0",           "order_number": "23555", "name": "хранилка за птици"},
    {"barcode": "JSWL2413INCHO06VPV0",           "order_number": "25066", "name": "Защитна ограда за животни"},
    {"barcode": "CGXXRJ25X24LT0XJF001V2",        "order_number": "",      "name": "Скрежина 8л"},
    {"barcode": "DSCDGZT120CMLOECU001V0",        "order_number": "26260", "name": "мивка 1200x500x940 мм"},
    {"barcode": "YTSZBJFB150LBSFBP001V2",        "order_number": "26404", "name": "Машина за Лед с туба голямата"},
    {"barcode": "CQCBBHYC910PNGK5GV2",           "order_number": "6883",  "name": "детски батут-от заявки"},
    {"barcode": "ZHSKU00000000000473",            "order_number": "6877",  "name": "соларен панел-от заявки"},
    {"barcode": "TYNLYQHSPVCLRGYW5V0",            "order_number": "6898",  "name": "душ (от заявки)"},
    {"barcode": "SYYYZLYQ2020WGXKEV0",            "order_number": "26843", "name": "филтър за абсорбатор"},
    {"barcode": "BYBQD42YCHS2PKJDWV0",            "order_number": "6968",  "name": "чанта за пушки - заявки"},
    {"barcode": "PQGJZMSO135CM641YV2",            "order_number": "26876", "name": "Резачка за пяна с гореща"},
    {"barcode": "QSYYTSFBZBJ1NHMZO001V2",         "order_number": "",      "name": "черен ледогенератор"},
]

ok = 0
skip = 0
errors = 0

for item in items:
    try:
        r = requests.post(f"{BASE_URL}/api/items", json=item, timeout=10)
        if r.status_code == 200:
            print(f"  ✓  {item['barcode']}  ({item['name']})")
            ok += 1
        elif r.status_code == 409:
            print(f"  –  {item['barcode']}  (вече съществува)")
            skip += 1
        else:
            print(f"  ✗  {item['barcode']}  → {r.status_code} {r.text}")
            errors += 1
    except Exception as e:
        print(f"  ✗  {item['barcode']}  → {e}")
        errors += 1

print(f"\nГотово: {ok} добавени, {skip} пропуснати, {errors} грешки")
