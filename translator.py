import tkinter as tk
from tkinter import ttk
import threading
import time
import numpy as np
import cv2
from mss import mss
from PIL import Image
import pytesseract
import translators as ts  # Giải pháp dịch theo ngữ cảnh tốt hơn googletrans

# Đường dẫn cài đặt Tesseract OCR trên Windows
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

class LiveTranslatorApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.withdraw() # Ẩn cửa sổ gốc
        
        self.is_translating = False
        self.last_frame = None
        self.sct = mss()
        
        # Khởi tạo 2 cửa sổ chính
        self.create_scan_window()
        self.create_result_window()
        
        # SỬA LỖI CHẠY NGẦM: Bắt sự kiện khi người dùng nhấn nút X đóng cửa sổ
        self.scan_win.protocol("WM_DELETE_WINDOW", self.on_close_app)
        self.res_win.protocol("WM_DELETE_WINDOW", self.on_close_app)
        
    def create_scan_window(self):
        self.scan_win = tk.Toplevel()
        self.scan_win.title("Vùng Quét")
        self.scan_win.geometry("500x300+100+100")
        self.scan_win.attributes("-topmost", True) # Pinned: Luôn nằm trên
        
        # Làm trong suốt phần ruột cửa sổ trên Windows bằng cách đục lỗ màu purple
        self.scan_win.attributes("-transparentcolor", "purple")
        
        # Khung chứa thanh điều khiển phía trên
        control_panel = tk.Frame(self.scan_win, bg="gray20", height=40)
        control_panel.pack(fill=tk.X, side=tk.TOP)
        
        self.btn_toggle = tk.Button(control_panel, text="Bắt đầu Dịch", bg="green", fg="white", command=self.toggle_translation, font=("Segoe UI", 10, "bold"))
        self.btn_toggle.pack(side=tk.LEFT, padx=5, pady=5)
        
        lbl_info = tk.Label(control_panel, text="Kéo góc để chỉnh vùng quét", bg="gray20", fg="white")
        lbl_info.pack(side=tk.RIGHT, padx=10)
        
        # Vùng trong suốt ở giữa (Màu purple sẽ bị đục lỗ biến mất)
        self.transparent_area = tk.Frame(self.scan_win, bg="purple")
        self.transparent_area.pack(fill=tk.BOTH, expand=True)
        
    def create_result_window(self):
        self.res_win = tk.Toplevel()
        self.res_win.title("Kết Quả Dịch")
        self.res_win.geometry("400x150+650+100")
        self.res_win.attributes("-topmost", True) # Pinned: Luôn nằm trên
        self.res_win.configure(bg="black")
        
        # Label hiển thị text dịch thuật với font chữ rõ ràng
        self.lbl_text = tk.Label(
            self.res_win, 
            text="Hệ thống sẵn sàng...", 
            font=("Segoe UI", 14, "bold"), 
            fg="#00FF00", # Màu xanh neon nổi bật
            bg="black", 
            wraplength=380, 
            justify=tk.LEFT
        )
        self.lbl_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Tự động cập nhật độ rộng wrap chữ khi người dùng đổi kích thước cửa sổ dịch
        self.res_win.bind("<Configure>", lambda e: self.lbl_text.configure(wraplength=max(100, self.res_win.winfo_width() - 20)))

    def toggle_translation(self):
        if not self.is_translating:
            self.is_translating = True
            self.btn_toggle.config(text="Dừng Dịch", bg="red")
            self.loop_thread = threading.Thread(target=self.translation_loop, daemon=True)
            self.loop_thread.start()
        else:
            self.is_translating = False
            self.btn_toggle.config(text="Bắt đầu Dịch", bg="green")
            self.last_frame = None  # Reset frame khi dừng quét

    def clean_text_context(self, text):
        """ Làm sạch văn bản, nối liền dòng để giữ đúng ngữ cảnh của câu """
        if not text:
            return ""
        # Đổi dấu xuống dòng thành khoảng trắng để Tesseract không làm đứt đoạn câu văn
        text = text.replace('\n', ' ').replace('\r', ' ')
        # Xóa các khoảng trắng thừa ngắt quãng
        return ' '.join(text.split()).strip()

    def translation_loop(self):
        while self.is_translating:
            # 1. Lấy tọa độ thực tế của vùng trong suốt
            x = self.transparent_area.winfo_rootx()
            y = self.transparent_area.winfo_rooty()
            w = self.transparent_area.winfo_width()
            h = self.transparent_area.winfo_height()
            
            if w <= 0 or h <= 0:
                time.sleep(0.2)
                continue
                
            # 2. Chụp ảnh màn hình siêu tốc bằng MSS
            monitor = {"top": y, "left": x, "width": w, "height": h}
            try:
                screenshot = self.sct.grab(monitor)
            except Exception:
                time.sleep(0.2)
                continue
            
            # Chuyển đổi sang numpy array dạng ảnh xám để tối ưu RAM tối đa khi tính toán chuyển động
            frame = np.array(screenshot)
            gray = cv2.cvtColor(frame, cv2.COLOR_BGRA2GRAY)
            
            # 3. Thuật toán phát hiện chuyển động (Motion Detection)
            if self.last_frame is None or self.last_frame.shape != gray.shape:
                self.last_frame = gray
                time.sleep(0.2)
                continue
                
            # Tính toán sai lệch pixel
            frame_delta = cv2.absdiff(self.last_frame, gray)
            thresh = cv2.threshold(frame_delta, 25, 255, cv2.THRESH_BINARY)[1]
            
            change_pixels = np.sum(thresh == 255)
            total_pixels = gray.size
            change_ratio = change_pixels / total_pixels
            
            # Cập nhật frame nền cho chu kỳ kế tiếp
            self.last_frame = gray
            
            # Chỉ bắt đầu dịch khi có chuyển động màn hình (> 1.5% pixel thay đổi)
            if change_ratio > 0.015:
                self.update_result_ui("Phát hiện thay đổi... Đang dịch...")
                
                try:
                    # Chuyển ảnh mss sang đối tượng PIL Image để đưa vào OCR
                    img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
                    
                    # Trích xuất văn bản (Mặc định tiếng Anh)
                    text_extracted = pytesseract.image_to_string(img, lang='eng')
                    
                    # Tiền xử lý văn bản nhằm tăng độ chính xác ngữ cảnh
                    clean_text = self.clean_text_context(text_extracted)
                    
                    if clean_text:
                        # Sử dụng bộ dịch ẩn danh Google (Web) qua translators giúp hiểu ngữ cảnh tốt hơn bản cũ
                        translated_text = ts.translate_text(clean_text, from_language='en', to_language='vi', translator='google')
                        self.update_result_ui(translated_text)
                    else:
                        self.update_result_ui("[Không phát hiện thấy chữ văn bản]")
                except Exception as e:
                    self.update_result_ui(f"Lỗi hệ thống dịch: {str(e)}")
            
            # Tối ưu RAM: Giải phóng tài nguyên biến mảng ngay lập tức trong vòng lặp vô hạn
            del frame, gray, frame_delta, thresh
            
            # Nghỉ 350ms mỗi chu kỳ quét giúp CPU và RAM được nghỉ ngơi, giữ mức tiêu thụ cực thấp
            time.sleep(0.35)

    def update_result_ui(self, text):
        # Đẩy dữ liệu hiển thị về Main Thread của Tkinter an toàn để tránh crash ứng dụng
        if self.res_win.winfo_exists():
            self.res_win.after(0, lambda: self.lbl_text.config(text=text))

    def on_close_app(self):
        """ Hàm dọn dẹp bộ nhớ và giải phóng luồng chạy ngầm để đóng hoàn toàn ứng dụng """
        self.is_translating = False # Phá vỡ vòng lặp dịch thuật ngầm ngay lập tức
        time.sleep(0.1) # Chờ luồng phụ kịp phản hồi và thoát
        
        # Tiêu diệt tất cả giao diện và dừng vòng lặp chính của Tkinter
        try:
            self.scan_win.destroy()
            self.res_win.destroy()
            self.root.quit()
            self.root.destroy()
        except Exception:
            pass

    def run(self):
        self.root.mainloop()

if __name__ == "__main__":
    app = LiveTranslatorApp()
    app.run()