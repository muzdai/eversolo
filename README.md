# Eversolo для Home Assistant

Интеграция для плееров **Eversolo DMP / DAC** (локальная сеть, порт 9529). Ставится через HACS как
custom repository и добавляет устройство с сущностями и карточку плеера.

## Что есть

| Функция | Где |
|---|---|
| Плеер: play/pause, назад/вперёд, громкость, mute, перемотка, повтор/shuffle | `media_player.<имя>` |
| Карточка плеера: альбомный / портретный вид по форме карточки, фон по цветам обложки | Lovelace `custom:eversolo-player-card` |
| Переключение входов | карточка, `select.<имя>_input`, сервис `eversolo.set_input` |
| Переключение выходов | карточка, `select.<имя>_output`, сервис `eversolo.set_output` |
| Музыкальные сервисы (локальная библиотека, Qobuz, Tidal и т.д., что есть на устройстве) | карточка, `select.<имя>_music_service`, сервис `eversolo.set_service` |
| Стрелочные индикаторы (VU) / спектр на дисплее | карточка, `select.<имя>_meter_display`, сервис `eversolo.set_vu_mode` |
| Дисплей устройства вкл/выкл | карточка, `switch.<имя>_front_display`, сервис `eversolo.set_display` (**экспериментально**) |
| Зондирование API | сервис `eversolo.request` (GET по произвольному пути, ответ возвращается) |

## Установка через HACS

1. HACS → Интеграции → меню «⋮» → **Пользовательские репозитории** → URL `https://github.com/muzdai/eversolo`, категория **Интеграция**.
2. Установить **Eversolo**, перезапустить Home Assistant.
3. Настройки → Устройства и службы → **Добавить интеграцию** → Eversolo.
4. Ввести IP-адрес плеера. На экране плеера появится запрос подключения: разрешите его и нажмите «Отправить» в мастере.
   Если устройство найдено через mDNS (`_eversolo._tcp`), оно появится в «Обнаруженных» автоматически.

## Карточка

После установки карточка доступна в редакторе Lovelace как **Eversolo Player**. Конфигурация:

```yaml
type: custom:eversolo-player-card
entity: media_player.dmp_a6
show_background: true   # фон по обложке (по умолчанию true)
show_chips: true        # ряд переключателей входа/выхода/сервиса/индикаторов
```

Вид выбирается по форме карточки: если ширина больше высоты, используется альбомный макет, иначе портретный.
Чтобы получить альбомный вид на планшете, поставьте карточку в широкую колонку или на всю ширину экрана.

## Сервисы

```yaml
service: eversolo.set_input        # data: entity_id, name (имя или tag из списка)
service: eversolo.set_output       # data: entity_id, name
service: eversolo.set_service      # data: entity_id, name
service: eversolo.set_vu_mode      # data: entity_id, mode: vu | spectrum
service: eversolo.set_display      # data: entity_id, on: true|false
service: eversolo.set_loop_mode    # data: entity_id, mode: list | single | shuffle
service: eversolo.request          # data: entity_id, path  -> response: сырой ответ устройства
```

## Что проверено, а что нет

Протокол восстановлен из декомпилированного приложения Eversolo Controller 1.15.65, см. `docs/protocol.md`.
Ни одна строка не проверена на живом устройстве автором этого кода. Подробности:

* **Проверено по коду (высокая уверенность):** подключение (`ZidooControlCenter/connect`), `getState`, play/pause/next/prev,
  `seekTo`, `setDevicesVolume`, `setLoopMode`, `sendkey Key.Mute`, `setInputList`, `setOutInputList`,
  `setDisplayMusicServerTag`, `changVUDisplay`, `getInputAndOutputList`, `getSupportServer`, `getImage`.
* **Не проверено (допущения):**
  * **Дисплей вкл/выкл** (`switch`): сейчас реализовано через `SystemSettings/functionSettings/setFrontBright?value=0|3`.
    Это яркость передней панели, а не отдельная команда питания дисплея, и значения 0/3 не подтверждены.
    Если на вашей прошивке есть другой путь, подправьте `api.set_display`.
    Состояние этого переключателя оптимистичное, устройство его не сообщает.
  * **Индикаторы:** `changVUDisplay(openType)`: `0` в приложении — кнопка VU, `1` — кнопка с иконкой «pinpu» (спектр).
    Как читать текущий режим из `vuDisplayMode`, тоже не подтверждено.
  * **Форматы ответов** `getInputAndOutputList` и `getSupportServer` неизвестны, парсер разбирает их по эвристике.
    Если входы или сервисы не видны, посмотрите сырой ответ через `eversolo.request` и поправьте `api.parse_io`.
  * **Единицы времени:** считается, что `duration`/`position`/`seekTo` в миллисекундах, если `duration > 20000`.
  * **Сервис «Музыкальный сервис»:** `setDisplayMusicServerTag` переключает вкладку сервиса; что именно
    начинает играть на устройстве, требует проверки.
  * **Обложка:** берётся `albumArtBig`/`albumArt` из `playingMusic`. Если это не URL, запрашивается `getImage?content=`.

## Разработка

```
custom_components/eversolo/      интеграция
  www/eversolo-player-card.js    карточка
tools/eversolo_client.py         автономный CLI-клиент для проверки протокола
docs/protocol.md                 описание протокола
docs/ui_reference/               разметка и иконки оригинального приложения
```

Проверка карточки без Home Assistant: открыть страницу с моком `hass` и подключить `www/eversolo-player-card.js`.

## Лицензия

Не указана. Это неофициальный проект, не связанный с Eversolo.
