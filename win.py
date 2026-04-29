# winapi & gdi+ constants, structs, classes and functions used in FSDK examples

import ctypes
from ctypes import windll, wintypes, byref
from ctypes import c_int, c_uint, c_void_p, c_long, c_bool, c_float as cF
from ctypes.wintypes import UINT, LPCWSTR, HWND, WPARAM, LPARAM, HINSTANCE, HICON, HBRUSH, HANDLE, POINT
HCURSOR = HANDLE
LRESULT = LPARAM

import sys

if sys.version_info.major == 2:
	L = lambda x: ctypes.c_wchar_p(x) # ctypes.create_unicode_buffer(x)
else:
	L = lambda x: x # python 3 does not need to transform str to wchar *

# used dll
gdi32 = windll.gdi32
user32 = windll.user32
gdip = windll.gdiplus

ImageFileType_JPEG = "image/jpeg";
ImageFileType_BMP = "image/bmp";
ImageFileType_GIF = "image/gif";
ImageFileType_TIFF = "image/tiff";
ImageFileType_PNG = "image/png";

class HBITMAP(wintypes.HBITMAP):
	def __del__(self): gdi32.DeleteObject(self)

WNDPROC = ctypes.WINFUNCTYPE(LRESULT, HWND, UINT, WPARAM, LPARAM)

class WNDCLASSEX(ctypes.Structure):
    _fields_ = [("cbSize", UINT),
                ("style", UINT),
                ("lpfnWndProc", WNDPROC),
                ("cbClsExtra", c_int),
                ("cbWndExtra", c_int),
                ("hInstance", HINSTANCE),
                ("hIcon", HICON),
                ("hCursor", HCURSOR),
                ("hbrBackground", HBRUSH),
                ("lpszMenuName", LPCWSTR),
                ("lpszClassName", LPCWSTR),
                ("hIconSm", HICON)]

class GdiplusStartupInput(ctypes.Structure):
	_fields_ = (("GdiplusVersion", c_uint), ("DebugEventProc", c_void_p),
		("DebugEventCallback", c_void_p), ("SuppressBackgroundThread", c_bool), ("SuppressExternalCodecs", c_bool))
	def __init__(self):
		self.GdiplusVersion = 1
		self.DebugEventProc = self.DebugEventCallback = 0
		self.SuppressBackgroundThread = self.SuppressExternalCodecs = False

class GDIPlus:
	def __init__(self):
		self.token = c_long()
		gdip.GdiplusStartup(byref(self.token), byref(GdiplusStartupInput()), c_void_p(0))
	def close(self): gdip.GdiplusShutdown(self.token)

class Image(ctypes.Structure):
	_fields_ = ("handle", c_void_p),
	def __del__(self): gdip.GdipDisposeImage(self)

class Bitmap(ctypes.Structure):
	_fields_ = ("handle", c_void_p),
	def __del__(self): gdip.GdipDisposeImage(self)

	@staticmethod
	def FromGraphics(width, height, graphics):
		bmp = Bitmap()
		gdip.GdipCreateBitmapFromGraphics(c_int(width), c_int(height), graphics, byref(bmp))
		return bmp

	@staticmethod
	def FromHBITMAP(hbmp):
		bmp = Bitmap()
		gdip.GdipCreateBitmapFromHBITMAP(hbmp, c_void_p(), byref(bmp))
		return bmp

	def GetHBITMAP(self):
		hbmp = HBITMAP()
		gdip.GdipCreateHBITMAPFromBitmap(self, byref(hbmp), c_int(0x0))
		return hbmp

	def save(self, fname, ft = ImageFileType_JPEG, jpegQuality=50):
		pass		


# CombineModes
CombineModeReplace = 0
CombineModeIntersect = 1
CombineModeUnion = 2
CombineModeXor = 3
CombineModeExclude = 4
CombineModeComplement = 5

class PointF(ctypes.Structure):
	_fields_ = ("x", cF), ("y", cF)

class RectF(ctypes.Structure):
	_fields_ = ("x", cF), ("y", cF), ("width", cF), ("height", cF), 

class Graphics(ctypes.Structure):
	_fields_ = ("handle", c_void_p),
	def __init__(self, dc=None, hwnd = None, bmp = None):
		if dc is not None: res = gdip.GdipCreateFromHDC(c_uint(dc), byref(self))
		elif hwnd is not None: gdip.GdipCreateFromHWND(c_uint(hwnd), byref(self))
		elif bmp is not None: gdip.GdipGetImageGraphicsContext(bmp, byref(self))
	def __del__(self): gdip.GdipDeleteGraphics(self)

	def clear(self, color): gdip.GdipGraphicsClear(self, c_uint(color))
	def setSmoothing(self, val): gdip.GdipSetSmoothingMode(self, c_int(2 if val else 1)); return self
	def ellipse(self, pen, x, y, x2, y2): gdip.GdipDrawEllipse(self, pen, cF(x), cF(y), cF(x2-x), cF(y2-y))
	def circle(self, pen, x, y, r): gdip.GdipDrawEllipse(self, pen, cF(x-r), cF(y-r), cF(r*2), cF(r*2))
	def fillRect(self, brush, x, y, x2, y2): gdip.GdipFillRectangle(self, brush, cF(x), cF(y), cF(x2-x), cF(y2-y))
	def drawImage(self, image, x = 0, y = 0): gdip.GdipDrawImage(self, image, cF(x), cF(y))
	def drawPath(self, pen, path): gdip.GdipDrawPath(self, pen, path)
	def clipPath(self, path, combineMode = CombineModeReplace): gdip.GdipSetClipPath(self, path, c_int(combineMode)); return self
	def resetClip(self): gdip.GdipResetClip(self); return self
	def drawString(self, string, font, x, y, brush):
		r = RectF(x, y, 0, 0)
		gdip.GdipDrawString(self, ctypes.create_unicode_buffer(string), c_int(len(string)), font, byref(r), 
			c_void_p(), brush) # string format and brush

	def beginContainer(self): cnt = c_int(); gdip.GdipBeginContainer2(self, byref(cnt)); return cnt
	def endContainer(self, container): gdip.GdipEndContainer(self, container)

	def translateTransform(self, x, y, matrixOrderPrepend = True): gdip.GdipTranslateWorldTransform(self, cF(x), cF(y), c_int(0 if matrixOrderPrepend else 1)); return self
	def rotateTransform(self, angle, matrixOrderPrepend = True): gdip.GdipRotateWorldTransform(self, cF(angle), c_int(0 if matrixOrderPrepend else 1)); return self

class GraphicsPath(ctypes.Structure):
	_fields_ = ("handle", c_void_p),
	def __init__(self, mode = True): gdip.GdipCreatePath(c_int(mode), byref(self))
	def _del__(self): gdip.GdipDeletePath(self)
	def reset(self): gdip.GdipResetPath(self); return self
	def ellipse(self, x, y, x2, y2): gdip.GdipAddPathEllipse(self, cF(x), cF(y), cF(x2-x), cF(y2-y)); return self

class Pen(ctypes.Structure):
	_fields_ = ("handle", c_void_p),
	def __init__(self, color, width = 1): gdip.GdipCreatePen1(c_uint(color), cF(width), c_int(0), byref(self))
	def __del__(self): gdip.GdipDeletePen(self)
	def setColor(self, color): gdip.GdipSetPenColor(self, c_uint(color)); return self
	def setWidth(self, width): gdip.GdipSetPenWidth(self, cF(width)); return self

class Brush(ctypes.Structure):
	_fields_ = ("handle", c_void_p),
	def __init__(self, color): gdip.GdipCreateSolidFill(c_uint(color), byref(self))
	def __del__(self): gdip.GdipDeleteBrush(self)
	def setColor(self, color): gdip.GdipSetSolidFillColor(self, c_uint(color))	

class FontFamily(ctypes.Structure):
	_fields_ = ("handle", c_void_p),
	def __init__(self, name): gdip.GdipCreateFontFamilyFromName(ctypes.create_unicode_buffer(name), c_void_p(), byref(self))

class Font(ctypes.Structure):
	_fields_ = ("handle", c_void_p),
	def __init__(self, family, emSize, style=0, unit=2): 
		gdip.GdipCreateFont(family, cF(emSize), c_int(style), c_int(unit), byref(self))

# constants
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_CLIENTEDGE = 0x00000200

WS_OVERLAPPED = 0
WS_POPUP = 0x80000000
WS_BORDER = 0x00800000
WS_SYSMENU = 0x00080000
WS_THICKFRAME = 0x00040000
WS_CAPTION = 0x00C00000  # WS_BORDER | WS_DLGFRAME
WS_CHILD   = 0x40000000
WS_CLIPCHILDREN = 0x02000000

SW_HIDE = 0
SW_SHOW = 5

PM_REMOVE = 1

SS_LEFT = 0
SS_CENTER = 1
SS_RIGHT = 2

# messages
WM_DESTROY = 0x0002
WM_CLOSE   = 0x0010
WM_QUIT    = 0x0012
WM_SETFONT = 0x0030
WM_KEYDOWN = 256
WM_MOUSEMOVE = 0x0200
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_CTLCOLOREDIT = 0x0133

VK_ESCAPE = 0x1B

LB_ADDSTRING = 384

SWP_NOMOVE = 2
SWP_NOZORDER = 4

DST_BITMAP = 4

DSS_NORMAL = 0

PS_SOLID = 0

NULL_BRUSH = HOLLOW_BRUSH = 5

IDC_ARROW = 32512

# structs
MSG = wintypes.MSG

# winapi functions
CreateWindowEx = user32.CreateWindowExW
def CreateWindow(lpClassName, lpWindowName, dwStyle, x, y, nWidth, nHeight, hWndParent, hMenu, hInstance, lpParam):
	return CreateWindowEx(0, lpClassName, lpWindowName, dwStyle, x, y, nWidth, nHeight, hWndParent, hMenu, hInstance, lpParam)
ShowWindow = user32.ShowWindow
SetWindowPos = user32.SetWindowPos
UpdateWindow = user32.UpdateWindow
DefWindowProc = user32.DefWindowProcW
RegisterClassEx = user32.RegisterClassExW
PostMessage = user32.PostMessageW
SetActiveWindow = user32.SetActiveWindow
SetFocus = user32.SetFocus
#GetLastError = user32.GetLastError

GetDC = user32.GetDC
ReleaseDC = user32.ReleaseDC
DeleteObject = gdi32.DeleteObject
SelectObject = gdi32.SelectObject
CreatePen = gdi32.CreatePen
GetStockObject = gdi32.GetStockObject
CreateFont = gdi32.CreateFontW
LoadCursor = user32.LoadCursorW
def GetCursorPos():
	p = POINT()
	user32.GetCursorPos(ctypes.byref(p))
	return p
def ScreenToClient(hwnd, p):
	user32.ScreenToClient(hwnd, ctypes.byref(p))
	return p
def GetWindowText(hwnd):
	char_buffer = (ctypes.c_wchar*256)()
	user32.GetWindowTextW(hwnd, char_buffer, 255)
	return char_buffer.value
SetWindowText = user32.SetWindowTextW

DrawState = user32.DrawStateW
Rectangle = gdi32.Rectangle
Ellipse = gdi32.Ellipse

PeekMessage = user32.PeekMessageW
TranslateMessage = user32.TranslateMessage
DispatchMessage = user32.DispatchMessageW
SendMessage = user32.SendMessageW
