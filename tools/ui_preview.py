"""Render this application's own Tk window and capture its client area on Windows."""

from pathlib import Path
import ctypes
from ctypes import wintypes
import struct
import sys
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import tkinter as tk
from reversi.ui import ChessApp, MODES


def capture(root, path):
    user, gdi = ctypes.windll.user32, ctypes.windll.gdi32
    user.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
    user.GetAncestor.restype = wintypes.HWND
    user.GetDC.argtypes = [wintypes.HWND]
    user.GetDC.restype = wintypes.HDC
    user.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
    gdi.CreateCompatibleDC.argtypes = [wintypes.HDC]
    gdi.CreateCompatibleDC.restype = wintypes.HDC
    gdi.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
    gdi.CreateCompatibleBitmap.restype = wintypes.HBITMAP
    gdi.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
    gdi.SelectObject.restype = wintypes.HGDIOBJ
    gdi.BitBlt.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                         wintypes.HDC, ctypes.c_int, ctypes.c_int, wintypes.DWORD]
    gdi.GetDIBits.argtypes = [wintypes.HDC, wintypes.HBITMAP, wintypes.UINT, wintypes.UINT,
                            ctypes.c_void_p, ctypes.c_void_p, wintypes.UINT]
    gdi.DeleteObject.argtypes = [wintypes.HGDIOBJ]
    gdi.DeleteDC.argtypes = [wintypes.HDC]
    hwnd = user.GetAncestor(root.winfo_id(), 2)
    rectangle = wintypes.RECT()
    user.GetClientRect(hwnd, ctypes.byref(rectangle))
    width, height = rectangle.right, rectangle.bottom
    dc = user.GetDC(hwnd)
    memory = gdi.CreateCompatibleDC(dc)
    bitmap = gdi.CreateCompatibleBitmap(dc, width, height)
    old = gdi.SelectObject(memory, bitmap)
    try:
        if not gdi.BitBlt(memory, 0, 0, width, height, dc, 0, 0, 0x00CC0020):
            raise OSError("Failed to capture app window")
        header = struct.pack("<IiiHHIIiiII", 40, width, -height, 1, 32, 0, width * height * 4, 0, 0, 0, 0)
        buffer = ctypes.create_string_buffer(width * height * 4)
        info = ctypes.create_string_buffer(header)
        if not gdi.GetDIBits(memory, bitmap, 0, height, buffer, info, 0):
            raise OSError("Failed to read app bitmap")
        pixels = buffer.raw
        scanlines = bytearray()
        for row in range(height):
            data = pixels[row * width * 4:(row + 1) * width * 4]
            rgb = bytearray(width * 3)
            rgb[0::3], rgb[1::3], rgb[2::3] = data[2::4], data[1::4], data[0::4]
            scanlines += b"\0" + rgb
        def chunk(kind, data):
            return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
        png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        png += chunk(b"IDAT", zlib.compress(scanlines)) + chunk(b"IEND", b"")
        path.write_bytes(png)
    finally:
        gdi.SelectObject(memory, old)
        gdi.DeleteObject(bitmap)
        gdi.DeleteDC(memory)
        user.ReleaseDC(hwnd, dc)


def main():
    output = Path(__file__).resolve().parents[1] / "artifacts"
    output.mkdir(exist_ok=True)
    root = tk.Tk()
    app = ChessApp(root)
    def shot(index=0):
        sizes = ("1180x850", "1000x780")
        root.geometry(sizes[index] + "+20+20")
        root.update()
        print("layout", sizes[index], "cell", app.board.cell, "logheight", app.move_list.winfo_height(), flush=True)
        capture(root, output / ("ui_default.png" if index == 0 else "ui_minimum.png"))
        if index == 0:
            root.after(300, lambda: shot(1))
        else:
            app.close()
    root.after(600, shot)
    root.mainloop()


if __name__ == "__main__":
    main()
