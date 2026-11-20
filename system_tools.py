"""
Модуль для сбора системной информации, скриншотов и выполнения команд на ноутбуке.
"""
import os
import platform
import subprocess
import psutil


def decode_shell_output(raw_bytes: bytes) -> str:
    """
    Построчно декодирует вывод Windows-консоли:
    PowerShell cmdlets пишут в UTF-8, а нативные утилиты (ipconfig, ping) — в OEM (CP866).
    """
    if not raw_bytes:
        return ""
    oem_encoding = "oem" if os.name == "nt" else "utf-8"
    decoded_lines = []
    for raw_line in raw_bytes.splitlines():
        try:
            decoded_lines.append(raw_line.decode("utf-8"))
        except UnicodeDecodeError:
            try:
                decoded_lines.append(raw_line.decode(oem_encoding))
            except UnicodeDecodeError:
                decoded_lines.append(raw_line.decode("utf-8", errors="replace"))
    return "\n".join(decoded_lines)


def get_system_stats() -> str:
    """Возвращает форматированную строку с состоянием ноутбука."""
    lines = []

    lines.append(f"💻 *Ноутбук:* `{platform.node()}` ({platform.system()} {platform.release()})")

    battery = psutil.sensors_battery()
    if battery:
        plugged_str = "🔌 Подключен к сети" if battery.power_plugged else "🔋 Работа от батареи"
        lines.append(f"{plugged_str}: *{battery.percent}%*")
    else:
        lines.append("⚡ Питание: Стационарное / Батарея не обнаружена")

    cpu_percent = psutil.cpu_percent(interval=0.5)
    lines.append(f"⚙️ *CPU:* {cpu_percent}%")

    ram = psutil.virtual_memory()
    used_gb = (ram.total - ram.available) / (1024**3)
    total_gb = ram.total / (1024**3)
    lines.append(f"🧠 *RAM:* {ram.percent}% ({used_gb:.1f} GB / {total_gb:.1f} GB)")

    try:
        disk = psutil.disk_usage("C:\\")
        free_gb = disk.free / (1024**3)
        total_d_gb = disk.total / (1024**3)
        lines.append(f"💾 *Диск C:* {free_gb:.1f} GB свободно из {total_d_gb:.1f} GB")
    except Exception:
        pass

    return "\n".join(lines)


def capture_screenshot(output_path: str = "temp_screen.png") -> str | None:
    """
    Делает DPI-aware скриншот всего виртуального экрана.
    1. Пробует использовать Pillow (PIL.ImageGrab).
    2. При отсутствии Pillow делает скриншот через PowerShell с включенным SetProcessDPIAware.
    """
    abs_path = os.path.abspath(output_path)
    parent = os.path.dirname(abs_path)
    if parent:
        os.makedirs(parent, exist_ok=True)

    # 1. Попытка через Pillow
    try:
        from PIL import ImageGrab
        img = ImageGrab.grab(all_screens=True)
        img.save(abs_path, "PNG")
        if os.path.exists(abs_path) and os.path.getsize(abs_path) > 0:
            return abs_path
    except ImportError:
        pass
    except Exception as e:
        print(f"[Screenshot PIL error]: {e}")

    # 2. Попытка через PowerShell с учётом DPI-масштабирования
    try:
        escaped_path = abs_path.replace("'", "''")
        ps_cmd = (
            "Add-Type -AssemblyName System.Windows.Forms,System.Drawing; "
            "Add-Type -TypeDefinition 'using System.Runtime.InteropServices; "
            "public class DPI { [DllImport(\"user32.dll\")] public static extern bool SetProcessDPIAware(); }'; "
            "[void][DPI]::SetProcessDPIAware(); "
            "$b = [System.Windows.Forms.SystemInformation]::VirtualScreen; "
            "$bmp = New-Object System.Drawing.Bitmap $b.Width, $b.Height; "
            "$g = [System.Drawing.Graphics]::FromImage($bmp); "
            "$g.CopyFromScreen($b.Location, [System.Drawing.Point]::Empty, $b.Size); "
            f"$bmp.Save('{escaped_path}', [System.Drawing.Imaging.ImageFormat]::Png); "
            "$g.Dispose(); $bmp.Dispose();"
        )
        res = subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], capture_output=True, timeout=10)
        if os.path.exists(abs_path) and os.path.getsize(abs_path) > 0:
            return abs_path
        else:
            err = decode_shell_output(res.stderr)
            print(f"[Screenshot PS failed]: {err}")
    except Exception as e:
        print(f"[Screenshot PS error]: {e}")

    return None


def execute_shell(command: str, timeout: int = 30) -> str:
    """Выполняет команду в PowerShell и возвращает корректно декодированный вывод."""
    try:
        res = subprocess.run(
            ["powershell", "-NoProfile", "-Command", command],
            capture_output=True,
            timeout=timeout,
        )
        stdout_text = decode_shell_output(res.stdout).strip()
        stderr_text = decode_shell_output(res.stderr).strip()

        output = stdout_text
        if stderr_text:
            output = (output + "\n" if output else "") + "[STDERR]:\n" + stderr_text
        if not output:
            output = "Команда выполнена успешно (вывод пуст)."
        return output
    except subprocess.TimeoutExpired:
        return f"⏱ Превышено время ожидания ({timeout} сек)."
    except Exception as e:
        return f"❌ Ошибка выполнения: {str(e)}"
