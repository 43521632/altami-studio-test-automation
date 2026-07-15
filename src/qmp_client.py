"""Клиент для работы с QMP (QEMU Machine Protocol)"""

import asyncio
import json
import logging
from typing import Dict, Any, Optional
from pathlib import Path
import socket

logger = logging.getLogger(__name__)

class QMPClientWrapper:
    """Обертка для работы с QMP протоколом через Unix socket"""
    
    def __init__(self, vm_id: str, socket_path: str):
        self.vm_id = vm_id
        self.socket_path = socket_path
        self.reader: Optional[asyncio.StreamReader] = None
        self.writer: Optional[asyncio.StreamWriter] = None
        self._connected = False
        self._message_id = 0
    
    async def connect(self) -> None:
        """Подключение к QMP сокету"""
        try:
            # Подключение к Unix socket
            self.reader, self.writer = await asyncio.open_unix_connection(
                self.socket_path
            )
            
            # Чтение приветственного сообщения
            greeting = await self._read_message()
            logger.debug(f"{self.vm_id}: QMP приветствие: {greeting}")
            
            # Выполнение рукопожатия QMP
            await self._send_message({"execute": "qmp_capabilities"})
            response = await self._read_message()
            
            if response.get("return") != {}:
                raise Exception(f"Ошибка рукопожатия QMP: {response}")
            
            self._connected = True
            logger.info(f"✅ {self.vm_id}: Подключение к QMP установлено")
            
        except Exception as e:
            logger.error(f"❌ {self.vm_id}: Ошибка подключения к QMP: {e}")
            raise
    
    async def disconnect(self) -> None:
        """Отключение от QMP"""
        if self.writer:
            self.writer.close()
            await self.writer.wait_closed()
        self._connected = False
        logger.info(f"{self.vm_id}: Отключение от QMP")
    
    async def _send_message(self, message: Dict) -> None:
        """Отправка сообщения в QMP"""
        self._message_id += 1
        message["id"] = str(self._message_id)
        data = json.dumps(message) + "\n"
        self.writer.write(data.encode())
        await self.writer.drain()
        logger.debug(f"{self.vm_id}: Отправлено: {message}")
    
    async def _read_message(self) -> Dict:
        """Чтение сообщения из QMP"""
        try:
            data = await self.reader.readline()
            if not data:
                raise Exception("Соединение закрыто")
            
            message = json.loads(data.decode())
            logger.debug(f"{self.vm_id}: Получено: {message}")
            return message
        except json.JSONDecodeError as e:
            logger.error(f"{self.vm_id}: Ошибка парсинга JSON: {e}")
            raise
        except Exception as e:
            logger.error(f"{self.vm_id}: Ошибка чтения: {e}")
            raise
    
    async def execute(self, command: str, arguments: Optional[Dict] = None) -> Dict:
        """Выполнение команды QMP"""
        if not self._connected:
            raise Exception("Не подключен к QMP")
        
        message = {"execute": command}
        if arguments:
            message["arguments"] = arguments
        
        await self._send_message(message)
        
        # Чтение ответа
        response = await self._read_message()
        
        # Проверка на ошибку
        if "error" in response:
            error_msg = response["error"].get("desc", "Неизвестная ошибка")
            logger.error(f"{self.vm_id}: Ошибка QMP: {error_msg}")
            raise Exception(f"QMP ошибка: {error_msg}")
        
        return response.get("return", {})
    
    async def query_status(self) -> Dict:
        """Запрос статуса ВМ"""
        return await self.execute("query-status")
    
    async def query_balloon(self) -> Dict:
        """Запрос использования памяти"""
        return await self.execute("query-balloon")
    
    async def query_cpus(self) -> Dict:
        """Запрос состояния CPU"""
        return await self.execute("query-cpus")
    
    async def system_reset(self) -> None:
        """Перезагрузка ВМ"""
        await self.execute("system_reset")
    
    async def system_powerdown(self) -> None:
        """Выключение ВМ"""
        await self.execute("system_powerdown")
    
    @property
    def is_connected(self) -> bool:
        return self._connected
