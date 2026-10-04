# Поток 1 — сценарии: приоритет ▲▼, сортировка по людям, имя файла выгрузки

Спека: `docs/superpowers/specs/2026-10-04-q4-improvements-pack-design.md` (Поток 1).

1. Имя файла выгрузки, сервер. Тест `tests/test_export_filename.py` (очистка имени, длина, пустое) →
   функция `scenario_file_name` в `app/api/endpoints/exports.py`, xlsx и pptx сценария; `expose_headers` в CORS.
2. Имя файла выгрузки, браузер. Тест `frontend/src/utils/contentDisposition.test.ts` →
   `utils/contentDisposition.ts`, использование в `api.download` (override > заголовок > адрес).
3. Приоритет ▲▼. Тесты `utils/latestSaver.test.ts` (последовательные сохранения, итог — последнее) и
   `utils/priorityStep.test.ts` (границы, пустое) → хелперы + кнопки в `BacklogAllocRow.tsx`,
   `handlePriorityChange` возвращает промис.
4. Сортировка по Аналитику/Разработчику. Тест `utils/allocationSort.test.ts` (А→Я, Я→А, пустые в конце,
   цикл 3 щелчков) → хелперы, заголовки в `PlanningPage.tsx`, сортировка внутри секций, DnD выключен.
5. Финал: полный бэкенд-прогон, `npm run build`, eslint по изменённым файлам.
