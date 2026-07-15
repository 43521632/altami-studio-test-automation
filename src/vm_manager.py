import asyncio
import logging
import subprocess
import os
import signal
from typing import Dict, List, Optional, Tuple
from pathlib import Path
import yaml
import psutil

from .qmp_client import QMPClientWrapper
from config.settings import VMS_CONFIG_PATH

logger = logging.getLogger(__name__)

class VMManager:
    """Управление существующими виртуальными машинами"""
    
    def __init__(self, config_path: str = str(VMS_CONFIG_PATH)):
        self.config_path = Path(config_path)
        self.config = self._load_config()
        self.vms: Dict[str, QMPClientWrapper] = {}
        self.vm_pids: Dict[str, int] = {}
    
    def _load_config(self) -> Dict:
        """Загрузка конфигурации ВМ"""
        try:
            with open(self.config_path, 'r') as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            logger.error(f"❌ Файл конфигурации не найден: {self.config_path}")
            return {'vms': {}}
        except yaml.YAMLError as e:
            logger.error(f"❌ Ошибка парсинга YAML: {e}")
            return {'vms': {}}
    
    def get_vm_config(self, vm_id: str) -> Dict:
        """Получение конфигурации конкретной ВМ"""
        return self.config.get('vms', {}).get(vm_id, {})
    
    def check_vm_running(self, vm_id: str) -> bool:
        """Проверка, запущена ли ВМ"""
        config = self.get_vm_config(vm_id)
        if not config:
            return False
        
        # Способ 1: Проверка через QMP сокет
        socket_path = config.get('qmp_socket')
        if socket_path and os.path.exists(socket_path):
            return True
        
        # Способ 2: Проверка через PID файл
        pid_file = config.get('vm_pid_file')
        if pid_file and os.path.exists(pid_file):
            try:
                with open(pid_file, 'r') as f:
                    pid = int(f.read().strip())
                if psutil.pid_exists(pid):
                    self.vm_pids[vm_id] = pid
                    return True
            except (ValueError, IOError) as e:
                logger.debug(f"Ошибка чтения PID файла {pid_file}: {e}")
                pass
        
        # Способ 3: Поиск процесса QEMU по имени и MAC адресу
        mac = config.get('mac_address')
        if mac:
            for proc in psutil.process_iter(['pid', 'cmdline']):
                try:
                    cmdline = ' '.join(proc.info['cmdline'] or [])
                    if 'qemu' in cmdline.lower() and mac in cmdline:
                        self.vm_pids[vm_id] = proc.info['pid']
                        return True
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
        
        return False
    
    def get_vm_status(self, vm_id: str) -> Dict:
        """Получение статуса ВМ"""
        config = self.get_vm_config(vm_id)
        running = self.check_vm_running(vm_id)
        
        status = {
            'id': vm_id,
            'name': config.get('name', vm_id),
            'running': running,
            'qmp_socket': config.get('qmp_socket'),
        }
        
        if running and vm_id in self.vm_pids:
            status['pid'] = self.vm_pids[vm_id]
        
        return status
    
    async def connect_to_vm(self, vm_id: str) -> QMPClientWrapper:
        """Подключение к существующей ВМ"""
        config = self.get_vm_config(vm_id)
        if not config:
            raise ValueError(f"ВМ {vm_id} не найдена в конфигурации")
        
        socket_path = config.get('qmp_socket')
        if not socket_path:
            raise ValueError(f"Для ВМ {vm_id} не указан QMP сокет")
        
        if not os.path.exists(socket_path):
            raise FileNotFoundError(f"QMP сокет {socket_path} не найден. ВМ возможно не запущена.")
        
        client = QMPClientWrapper(vm_id, socket_path)
        await client.connect()
        self.vms[vm_id] = client
        return client
    
    async def disconnect_from_vm(self, vm_id: str) -> None:
        """Отключение от ВМ"""
        if vm_id in self.vms:
            await self.vms[vm_id].disconnect()
            del self.vms[vm_id]
    
    async def get_connected_vm(self, vm_id: str) -> QMPClientWrapper:
        """Получение подключенного клиента ВМ"""
        if vm_id not in self.vms:
            await self.connect_to_vm(vm_id)
        return self.vms[vm_id]
    
    def get_all_vm_ids(self) -> List[str]:
        """Получение списка всех ID ВМ"""
        return list(self.config.get('vms', {}).keys())
    
    def get_enabled_vm_ids(self) -> List[str]:
        """Получение списка ID ВМ с включенными тестами"""
        enabled = []
        for vm_id, config in self.config.get('vms', {}).items():
            if config.get('enabled_tests'):
                enabled.append(vm_id)
        return enabled
