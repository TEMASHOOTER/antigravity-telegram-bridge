"""
Модуль для сбора системной информации и скриншотов с ноутбука.
"""
import os
import platform
import subprocess
import psutil

def get_system_stats() -> str:
    """Возвращает форматированную строку с состоянием ноутбука."""
    lines = []
    
    # Имя хоста и ОС
    lines.append(f"💻 *Ноутбук:* `{platform.node()}` ({platform.system()} {platform.release()})")
    
    # Батарея
    battery = psutil.sensors_battery()
    if battery:
        plugged_str = "🔌 Подключен к сети" if battery.power_plugged else "🔋 Работа от батареи"
        lines.append(f"{plugged_str}: *{battery.percent}%*")
    else:
        lines.append("⚡ Питание: Стационарное / Батарея не обнаружена")
        
    # Процессор
    cpu_percent = psutil.cpu_percent(interval=0.5)
    lines.append(f"⚙️ *CPU:* {cpu_percent}%")
    
    # Оперативная память
    ram = psutil.virtual_memory()
    used_gb = (ram.total - ram.available) / (1024**3)
    total_gb = ram.total / (1024**3)
    lines.append(f"🧠 *RAM:* {ram.percent}% ({used_gb:.1f} GB / {total_gb:.1f} GB)")
    
    # Диск C:
    try:
        disk = psutil.disk_usage('C:\\')
        free_gb = disk.free / (1024**3)
        total_d_gb = disk.total / (1024**3)
        lines.append(f"💾 *Диск C:* {free_gb:.1f} GB свободно из {total_d_gb:.1f} GB")
    except Exception:
        pass
        
    return "\n".join(lines)


def capture_screenshot(output_path: str = "temp_screen.png") -> str | None:
    """
    Делает скриншот экрана.
    1. Пробует использовать Pillow (PIL.ImageGrab).
    2. При отсутствии Pillow делает скриншот через встроенный PowerShell System.Drawing.
    Возвращает путь к сохраненному файлу или None в случае ошибки.
    """
    # 1. Попытка через Pillow
    try:
        from PIL import ImageGrab
        img = ImageGrab.grab()
        img.save(output_path, "PNG")
        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            return output_path
    except ImportError:
        pass
    except Exception as e:
        print(f"[Screenshot PIL error]: {e}")

    # 2. Попытка через PowerShell
    try:
        ps_cmd = (
            "Add-Type -AssemblyName System.Windows.Forms,System.Drawing; "
            "$b = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds; "
            "$bmp = New-Object System.Drawing.Bitmap $b.Width, $b.Height; "
            "$g = [System.Drawing.Graphics]::FromImage($bmp); "
            "$g.CopyFromScreen($b.Location, [System.Drawing.Point]::Empty, $b.Size); "
            f"$bmp.Save('{output_path}', [System.Drawing.Imaging.ImageFormat]::Png); "
            "$g.Dispose(); $bmp.Dispose();"
        )
        res = subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], capture_output=True, timeout=10)
        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            return output_path
        else:
            print(f"[Screenshot PS failed]: {res.stderr.decode('utf-8', errors='ignore')}")
    except Exception as e:
        print(f"[Screenshot PS error]: {e}")

    return None


def execute_shell(command: str, timeout: int = 30) -> str:
    """Выполняет команду в PowerShell и возвращает консольный вывод."""
    try:
        res = subprocess.run(
            ["powershell", "-NoProfile", "-Command", command],
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace"
        )
        output = res.stdout.strip()
        if res.stderr.strip():
            output += "\n[STDERR]:\n" + res.stderr.strip()
        if not output:
            output = "Команда выполнена успешно (вывод пуст)."
        return output
    except subprocess.TimeoutExpired:
        return f"⏱ Превышено время ожидания ({timeout} сек)."
    except Exception as e:
        return f"❌ Ошибка выполнения: {str(e)}"
