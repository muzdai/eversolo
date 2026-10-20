# Eversolo для Home Assistant

Интеграция для плееров **Eversolo DMP / DAC** (локальная сеть, порт 9529). Ставится через HACS как
custom repository и добавляет устройство с сущностями и карточку плеера.

## Что есть

| Функция | Где |
|---|---|
| Плеер: play/pause, назад/вперёд, громкость, mute, перемотка, повтор/shuffle | `media_player.<название>` |
| Карточка плеера: альбомный / портретный вид по форме карточки, фон по цветам обложки | Lovelace `custom:eversolo-player-card` |
| Переключение входов | карточка, `select.<имя>_input`, сервис `eversolo.set_input` |
| Переключение выходов | карточка, `select.<имя>_output`, сервис `eversolo.set_output` |
| Стрелочные индикаторы (VU) / спектр на дисплее | карточка, `select.<имя>_meter_display`, сервис `eversolo.set_vu_mode` (**не проверено**) |
| Не реализовано: вкл/выкл дисплея и выбор музыкального сервиса | в API приложения не найден метод, который это переключает (см. ниже) |
| Зондирование API | сервис `eversolo.request` (GET по произвольному пути, ответ возвращается) |

Название задаётся при добавлении интеграции (по умолчанию `Eversolo`) и становится префиксом id всех сущностей:
`media_player.<название>`, `select.<название>_input`, `select.<название>_output` и т.д.
Пример ниже предполагает название `Eversolo`.

## Установка через HACS

1. HACS → Интеграции → меню «⋮» → **Пользовательские репозитории** → URL `https://github.com/muzdai/eversolo`, категория **Интеграция**.
2. Установить **Eversolo**, перезапустить Home Assistant.
3. Настройки → Устройства и службы → **Добавить интеграцию** → Eversolo.
4. Задать название (оно станет префиксом id сущностей) и ввести IP-адрес плеера. На экране плеера появится запрос подключения: разрешите его и нажмите «Отправить» в мастере.
   Если устройство найдено через mDNS (`_eversolo._tcp`), оно появится в «Обнаруженных» автоматически.

### Настройки после установки

В Настройки → Устройства и службы → Eversolo → **Настроить** можно поменять название, IP-адрес и порт.
Интеграция проверит подключение и перезагрузится. Id уже созданных сущностей при смене названия **не меняются**:
переименовать их можно в карточке сущности (Настройки → Объекты).

## Карточка

После установки карточка доступна в редакторе Lovelace как **Eversolo Player**. Конфигурация:

```yaml
type: custom:eversolo-player-card
entity: media_player.dmp_a6
show_background: true   # фон по обложке (по умолчанию true)
show_chips: true        # ряд переключателей входа/выхода/индикаторов
```

Вид выбирается по форме карточки: если ширина больше высоты, используется альбомный макет, иначе портретный.
Чтобы получить альбомный вид на планшете, поставьте карточку в широкую колонку или на всю ширину экрана.

## Сервисы

```yaml
service: eversolo.set_input        # data: entity_id, name (имя или tag из списка)
service: eversolo.set_output       # data: entity_id, name
service: eversolo.set_vu_mode      # data: entity_id, mode: vu | spectrum
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
  * **Индикаторы:** `changVUDisplay(openType)`: `0` в приложении — кнопка VU, `1` — кнопка спектра.
    Как устройство переключает режимы и что означает `vuDisplayMode` (`-1`, `0`, `1`, `2`), на живом плеере не подтверждено.
  * **Входы и выходы:** список читается из `getInputAndOutputList` (`inputData`/`outputData`, текущий элемент по `inputIndex`/`outputIndex`),
    переключение — `setInputList`/`setOutInputList` с `tag`, `index` и `isLight=true`, как в приложении.
  * **Единицы времени:** считается, что `duration`/`position`/`seekTo` в миллисекундах, если `duration > 20000`.
  * **Обложка:** берётся `albumArtBig`/`albumArt` из `playingMusic`. Если это не URL, запрашивается `getImage?content=`.

### Что не реализовано

* **Вкл/выкл дисплея.** Прежний вариант через `setFrontBright` был неверен: это регулировка яркости, а не питание дисплея.
  Список яркостей приложение берёт из `SystemSettings/functionSettings/getFrontBrightList`, но код обработки в декомпиляции отсутствует.
  Для проверки используйте сервис `eversolo.request` с путём `/SystemSettings/functionSettings/getFrontBrightList`.
* **Выбор музыкального сервиса.** `getSupportServer` возвращает список тегов, а названия приложение берёт из своего конфига.
  `setDisplayMusicServerTag` только показывает или скрывает вкладку сервиса, это не переключение.
  Сервис запускается через отдельные вызовы контента (`playWebServerMusicList` и др.), поэтому сущность выбора убрана.

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
