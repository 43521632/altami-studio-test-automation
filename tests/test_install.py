"""Тест подготовки чистой ВМ: скачивание установщика в госте и установка.

Схема (п. 12.4 INSTRUCTION_FOR_AI.md): установщик НЕ скачивается на хосте.
Ссылку на артефакт даёт тест-ран Kiwi (поле `summary`), скачивает её браузер
ВНУТРИ гостя, и уже оттуда запускается установщик. На хосте остаётся только
UI-управление через QMP.

Тест идёт первым в цепочке ВМ (@pytest.mark.order(0)): остальные тесты
работают с уже установленным приложением. ID кейса проставляется в
src/case_ids.py — тест без ID не попадёт ни в `--case`, ни в Kiwi.

Почему браузер, а не команда в госте: в домене нет ни QEMU guest agent, ни
virtiofs/9p, ни SSH — программно выполнить команду внутри гостя нельзя.
Как только guest agent появится, шаг скачивания переедет на него
(см. utils/guest_ui.py).
"""

import asyncio
import logging
import os
from pathlib import Path

import pytest

from src.vm_manager import VMSession
from utils.config import get_revision
from utils.guest_ui import (
    enter_jfrog_credentials,
    installer_filename,
    open_browser,
)

logger = logging.getLogger(__name__)

#: Сколько ждать закрытия диалога аутентификации и старта загрузки
_DOWNLOAD_START_TIMEOUT = 30.0


def _installer_url() -> str:
    """URL установщика: из тест-рана Kiwi, иначе собранный из ревизии.

    Приоритет — URL из рана: именно его положил туда CI, и он может
    отличаться от шаблона. Если рана нет (локальный прогон) — собираем URL
    по той же схеме, что и раньше делал utils/download.py, из ревизии.
    """
    testrun_id = os.environ.get("KIWI_TESTRUN_ID")
    if testrun_id:
        from utils.kiwi_client import get_installer_url_from_kiwi

        url = get_installer_url_from_kiwi(int(testrun_id))
        if url:
            return url
        logger.warning(
            "В тест-ране %s нет URL установщика — собираю из ревизии", testrun_id
        )

    # Fallback: URL по шаблону JFrog из ревизии сборки
    from utils.config import get_app_version, get_platform

    revision = get_revision()
    version = get_app_version()
    platform = get_platform()
    ext = ".exe" if "windows" in platform else ".deb"
    url = (
        "https://cache.altami.ru/artifactory/app-builds/altami/"
        f"{revision}/{platform}/AS_{version}_{revision}_{platform}{ext}"
    )
    logger.info("URL установщика собран из ревизии: %s", url)
    return url


@pytest.mark.app
@pytest.mark.asyncio
async def test_install_app(vm_session: VMSession) -> None:
    """Скачать установщик внутри гостя и установить приложение.

    Скачивание и установка объединены в один тест намеренно: это одна
    операция с одним состоянием (скачанный файл), а не два независимых
    кейса. Раздельные тесты пришлось бы связывать через pytest-order и
    передавать путь к файлу между ними — лишняя точка отказа.
    """
    session = vm_session
    url = _installer_url()
    filename = installer_filename(url)
    logger.info("Установщик: %s", url)

    # --- 1. Скачивание в госте -------------------------------------------
    creds = bool(os.environ.get("CACHE_USER") and os.environ.get("CACHE_PASSWORD"))
    if not creds:
        logger.warning(
            "CACHE_USER/CACHE_PASSWORD не заданы — JFrog ответит 401, "
            "и вместо установщика скачается HTML-страница"
        )

    logger.info("Открываю ссылку в браузере гостя")
    await open_browser(session, url)
    await asyncio.sleep(_DOWNLOAD_START_TIMEOUT)

    # Диалог аутентификации: браузер показывает его после первого запроса
    # к защищённому артефакту. Тип диалога зависит от браузера гостя, поэтому
    # сценарий проверяется на живой ВМ и при необходимости правится здесь.
    await enter_jfrog_credentials(session)
    logger.info(
        "Ожидаю появления '%s' в папке загрузок гостя (%s)",
        filename, session.config.get("download", {}).get("dir", "Downloads"),
    )

    # Файл скачивается браузером асинхронно; проверить его наличие можно
    # только по UI (в госте нет командной строки). Тест снимает финальный
    # кадр — по нему видно, началась ли загрузка, и он же попадает в отчёт.
    shot = await session.screenshot("installer_download")
    logger.info("Кадр после скачивания: %s", shot)

    # --- 2. Установка -----------------------------------------------------
    # TODO: запустить скачанный установщик из папки загрузок гостя и
    # пройти мастер установки (кнопки и этапы — по живой ВМ). Пока этот шаг
    # оставлен заглушкой: без него проверять нечего, и тест честно падает.
    pytest.fail(
        "Установка приложения ещё не реализована: скачивание в госте "
        "выполнено, шаг запуска установщика и прохождения мастера — TODO. "
        f"Скачанный файл ожидается как {filename}."
    )
