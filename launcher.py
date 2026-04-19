"""
Launcher para ejecutable Windows (.exe)
Inicia Streamlit en un puerto libre y abre el navegador automáticamente.
"""
import os
import sys
import socket
import subprocess
import threading
import time
import webbrowser


def _puerto_libre():
    """Encontrar un puerto TCP disponible."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def _ruta_base():
    """Ruta base: dentro del bundle PyInstaller o directorio del script."""
    if getattr(sys, "frozen", False):
        # Ejecutando como .exe (PyInstaller)
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))


def _abrir_navegador(url: str, espera: float = 3.0):
    """Abrir el navegador después de una espera para que Streamlit arranque."""
    time.sleep(espera)
    webbrowser.open(url)


def main():
    base = _ruta_base()
    app_py = os.path.join(base, "app.py")
    puerto = _puerto_libre()
    url = f"http://localhost:{puerto}"

    print(f"⚡ Cuadros de Carga — Alumbrado Público Vial")
    print(f"   Iniciando servidor en {url} ...")
    print(f"   (no cierre esta ventana mientras usa la aplicación)")

    # Abrir navegador en background
    t = threading.Thread(target=_abrir_navegador, args=(url, 3.0), daemon=True)
    t.start()

    # Comando streamlit
    cmd = [
        sys.executable if not getattr(sys, "frozen", False) else sys.executable,
        "-m", "streamlit", "run", app_py,
        f"--server.port={puerto}",
        "--server.address=localhost",
        "--server.headless=true",
        "--browser.gatherUsageStats=false",
        "--theme.primaryColor=#1F3864",
    ]

    # Si estamos dentro del .exe, streamlit está en el bundle
    if getattr(sys, "frozen", False):
        streamlit_script = os.path.join(base, "_internal", "streamlit", "__main__.py")
        cmd = [sys.executable, streamlit_script, "run", app_py,
               f"--server.port={puerto}",
               "--server.address=localhost",
               "--server.headless=true",
               "--browser.gatherUsageStats=false"]

    try:
        proc = subprocess.run(cmd, cwd=base)
    except KeyboardInterrupt:
        print("\nCerrando Cuadros de Carga...")


if __name__ == "__main__":
    main()
