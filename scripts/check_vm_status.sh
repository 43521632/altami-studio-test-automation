#!/usr/bin/env bash
# Быстрая проверка состояния ВМ через virsh, без Python.
#
# Использование:
#   ./scripts/check_vm_status.sh                  # все ВМ из конфига
#   ./scripts/check_vm_status.sh windows-10-test  # конкретный домен

set -uo pipefail

URI="${LIBVIRT_URI:-qemu:///system}"
CONFIG="$(dirname "$0")/../config/vms_config.yaml"

if ! command -v virsh >/dev/null 2>&1; then
    echo "ОШИБКА: virsh не установлен."
    echo "  sudo apt install -y virt-manager libvirt-daemon-system"
    exit 2
fi

if ! virsh -c "$URI" version >/dev/null 2>&1; then
    echo "ОШИБКА: нет подключения к libvirt по $URI"
    echo "  Проверьте: systemctl status libvirtd"
    echo "  И членство в группе libvirt: groups | grep libvirt"
    exit 2
fi

echo "=== Все домены ($URI) ==="
virsh -c "$URI" list --all
echo

# Если домен передан аргументом — берём его, иначе вытаскиваем vm_name из конфига
if [ $# -gt 0 ]; then
    DOMAINS=("$@")
else
    mapfile -t DOMAINS < <(grep -E '^\s+vm_name:' "$CONFIG" 2>/dev/null \
        | sed -E 's/.*vm_name:[[:space:]]*"?([^"]*)"?[[:space:]]*$/\1/')
fi

if [ ${#DOMAINS[@]} -eq 0 ]; then
    echo "Не удалось определить список доменов из $CONFIG"
    exit 1
fi

for domain in "${DOMAINS[@]}"; do
    [ -z "$domain" ] && continue
    echo "=== $domain ==="
    if ! virsh -c "$URI" dominfo "$domain" 2>/dev/null; then
        echo "  НЕ НАЙДЕН в libvirt (проверьте vm_name в vms_config.yaml)"
        echo
        continue
    fi

    XML="$(virsh -c "$URI" dumpxml "$domain" 2>/dev/null)"

    # Второй QMP-сокет: без него управление UI не работает
    if echo "$XML" | grep -q 'qemu:arg.*qmp'; then
        echo "  QMP-сокет для тестов: настроен в XML"
    else
        echo "  QMP-сокет для тестов: НЕ НАСТРОЕН — см. README «Второй QMP-сокет»"
    fi

    # USB-планшет нужен для абсолютных координат мыши
    if echo "$XML" | grep -q "input type='tablet'"; then
        echo "  USB-планшет: есть (абсолютные координаты мыши работают)"
    else
        echo "  USB-планшет: ОТСУТСТВУЕТ — клики мышью будут уходить мимо"
    fi

    echo "  --- Сетевые интерфейсы ---"
    virsh -c "$URI" domifaddr "$domain" 2>/dev/null || echo "  (нет данных DHCP)"
    echo
done
