import sys
import os
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
from pathlib import Path
import threading

# 导入核心爬虫类
from pippi_core import RobustImageSpider


class SpiderThread(threading.Thread):
    """后台线程"""

    def __init__(self, url, folder, gui):
        super().__init__()
        self.url = url
        self.folder = folder
        self.gui = gui
        self.spider = None
        self.is_running = True

    def run(self):
        try:
            import builtins

            original_print = builtins.print

            def gui_print(*args, **kwargs):
                msg = " ".join(map(str, args))
                self.gui.log(msg)

            builtins.print = gui_print

            self.spider = RobustImageSpider(self.folder)

            # Monkey patch crawl 方法添加进度
            original_crawl = self.spider.crawl

            def crawl_with_progress(url):
                self.gui.log(f"🚀 开始爬取: {url}")

                # 检查是否是直接的图片链接
                if self.spider._is_direct_image_url(url):
                    self.gui.log("🎯 检测到直接图片链接，开始下载...")
                    self.gui.set_progress(0, 1)
                    self.spider.download_image(url, 1)
                    self.gui.set_progress(1, 1)
                    success = self.spider.downloaded_count
                    skipped = self.spider.skipped_count
                    failed = self.spider.failed_count
                    self.gui.log(
                        f"✅ 下载完成！成功: {success}, 跳过: {skipped}, 失败: {failed}"
                    )
                    return success

                # 原有逻辑：从HTML页面提取图片链接
                html = self.spider.get_page(url)
                if not html:
                    self.gui.log("❌ 获取页面失败")
                    return 0

                images = self.spider.extract_images(html, base_url=url)
                total = len(images)

                if not images:
                    self.gui.log("❌ 未找到任何图片")
                    return 0

                self.gui.log(f"🎯 共发现 {total} 张图片")
                self.gui.set_progress(0, total)

                for i, img_url in enumerate(images, 1):
                    if not self.is_running:
                        self.gui.log("⏹️ 用户取消下载")
                        break

                    self.spider.download_image(img_url, i)
                    self.gui.set_progress(i, total)

                    if i % 10 == 0 and i < total:
                        self.gui.log(f"💤 已下载 {i}/{total}，休息中...")

                success = self.spider.downloaded_count
                skipped = self.spider.skipped_count
                failed = self.spider.failed_count
                self.gui.log(
                    f"✅ 下载完成！成功: {success}, 跳过: {skipped}, 失败: {failed}"
                )
                return success

            self.spider.crawl = crawl_with_progress
            result = self.spider.crawl(self.url)

            builtins.print = original_print
            self.gui.download_finished(True, f"下载完成，共 {result} 张新图片")

        except Exception as e:
            self.gui.log(f"❌ 错误: {str(e)}")
            self.gui.download_finished(False, str(e))

    def stop(self):
        self.is_running = False


class PippiGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("皮皮蛛 PippiSpider 1.2.1")
        self.root.geometry("700x650")
        self.root.minsize(600, 500)

        # 先隐藏窗口，避免闪烁
        self.root.withdraw()

        # 设置窗口图标
        try:
            # 获取资源文件的正确路径（兼容开发环境和打包后的exe）
            if getattr(sys, "frozen", False):
                # 打包后的exe环境
                base_path = sys._MEIPASS
            else:
                # 开发环境
                base_path = os.path.dirname(os.path.abspath(__file__))

            icon_path = os.path.join(base_path, "Pippi-logo.ico")
            self.root.iconbitmap(icon_path)
        except Exception as e:
            print(f"无法加载图标: {e}")

        # 样式配置
        self.bg_color = "#f0f0f0"
        self.accent_color = "#4CAF50"
        self.root.configure(bg=self.bg_color)

        # 主容器
        main_frame = tk.Frame(root, bg=self.bg_color, padx=20, pady=20)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # === 标题区域 ===
        title_frame = tk.Frame(main_frame, bg=self.bg_color)
        title_frame.pack(fill=tk.X, pady=(0, 20))

        # Logo
        try:
            from PIL import Image, ImageTk

            # 获取资源文件的正确路径（兼容开发环境和打包后的exe）
            if getattr(sys, "frozen", False):
                # 打包后的exe环境
                base_path = sys._MEIPASS
            else:
                # 开发环境
                base_path = os.path.dirname(os.path.abspath(__file__))

            logo_path = os.path.join(base_path, "Pippi-logo.ico")
            if os.path.exists(logo_path):
                # 使用PIL加载并调整图标大小
                logo_image = Image.open(logo_path)
                logo_image = logo_image.resize((64, 64), Image.LANCZOS)
                logo_photo = ImageTk.PhotoImage(logo_image)

                logo_label = tk.Label(title_frame, image=logo_photo, bg=self.bg_color)
                logo_label.image = logo_photo  # 保持引用
                logo_label.pack(pady=(0, 10))
            else:
                raise FileNotFoundError("Logo文件不存在")
        except ImportError:
            # 如果没有安装PIL，使用简单的文本替代
            print("未安装PIL，使用emoji替代")  # 调试信息
            logo_label = tk.Label(
                title_frame,
                text="🕷️",
                font=("Arial", 48),
                bg=self.bg_color,
                fg="#4CAF50",
            )
            logo_label.pack(pady=(0, 10))
        except Exception as e:
            # 如果加载图标失败，使用简单的文本替代
            print(f"Logo加载失败: {e}")  # 调试信息
            logo_label = tk.Label(
                title_frame,
                text="🕷️",
                font=("Arial", 48),
                bg=self.bg_color,
                fg="#4CAF50",
            )
            logo_label.pack(pady=(0, 10))

        # 大标题
        title_label = tk.Label(
            title_frame,
            text="皮皮蛛图片下载器",
            font=("Microsoft YaHei", 24, "bold"),
            bg=self.bg_color,
            fg="#333333",
        )
        title_label.pack()

        # 副标题
        subtitle_label = tk.Label(
            title_frame,
            text="一只懂得休息、会跳过已下载、绝不给主人添麻烦的乖蜘蛛",
            font=("Microsoft YaHei", 10),
            bg=self.bg_color,
            fg="#666666",
        )
        subtitle_label.pack(pady=(5, 0))

        # === 输入区域 ===
        input_frame = tk.LabelFrame(
            main_frame,
            text=" 下载设置 ",
            bg=self.bg_color,
            font=("Microsoft YaHei", 10, "bold"),
        )
        input_frame.pack(fill=tk.X, pady=(0, 10))

        # URL输入
        tk.Label(input_frame, text="目标链接:", bg=self.bg_color).grid(
            row=0, column=0, sticky=tk.W, pady=5
        )
        self.url_entry = tk.Entry(input_frame, width=50, font=("Consolas", 10))
        self.url_entry.grid(row=0, column=1, sticky=tk.EW, padx=5)
        self.url_entry.insert(0, "https://bing.fullpx.com/")

        # 文件夹选择
        tk.Label(input_frame, text="保存目录:", bg=self.bg_color).grid(
            row=1, column=0, sticky=tk.W, pady=5
        )
        self.folder_entry = tk.Entry(input_frame, width=40, font=("Consolas", 10))
        self.folder_entry.grid(row=1, column=1, sticky=tk.EW, padx=5)
        self.folder_entry.insert(0, "pippi_images")

        self.browse_btn = tk.Button(
            input_frame, text="浏览...", command=self.browse_folder, bg="#e0e0e0"
        )
        self.browse_btn.grid(row=1, column=2, padx=5)

        input_frame.columnconfigure(1, weight=1)

        # === 控制按钮 ===
        btn_frame = tk.Frame(main_frame, bg=self.bg_color)
        btn_frame.pack(fill=tk.X, pady=10)

        self.start_btn = tk.Button(
            btn_frame,
            text="🚀 开始下载",
            command=self.start_download,
            bg=self.accent_color,
            fg="white",
            font=("Microsoft YaHei", 12, "bold"),
            padx=20,
            pady=5,
            cursor="hand2",
        )
        self.start_btn.pack(side=tk.LEFT, padx=(0, 10))

        self.stop_btn = tk.Button(
            btn_frame,
            text="⏹️ 停止",
            command=self.stop_download,
            bg="#f44336",
            fg="white",
            font=("Microsoft YaHei", 12, "bold"),
            padx=20,
            pady=5,
            state=tk.DISABLED,
            cursor="hand2",
        )
        self.stop_btn.pack(side=tk.LEFT)

        # === 进度条 ===
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(
            main_frame,
            variable=self.progress_var,
            maximum=100,
            mode="determinate",
            length=400,
        )
        self.progress_bar.pack(fill=tk.X, pady=10)

        self.progress_label = tk.Label(
            main_frame, text="就绪", bg=self.bg_color, fg="gray"
        )
        self.progress_label.pack()

        # === 日志区域 ===
        log_frame = tk.LabelFrame(
            main_frame,
            text=" 运行日志 ",
            bg=self.bg_color,
            font=("Microsoft YaHei", 10, "bold"),
        )
        log_frame.pack(fill=tk.BOTH, expand=True, pady=(10, 0))

        self.log_text = scrolledtext.ScrolledText(
            log_frame,
            wrap=tk.WORD,
            font=("Consolas", 9),
            bg="#fafafa",
            fg="#333",
            padx=10,
            pady=10,
            height=8,  # 限制高度为8行，为状态栏留出空间
        )
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.log_text.config(state=tk.DISABLED)

        # === 状态栏 ===
        status_frame = tk.Frame(main_frame, bg=self.bg_color, height=25)
        status_frame.pack(fill=tk.X, side=tk.BOTTOM, pady=(5, 0))
        status_frame.pack_propagate(False)  # 防止子组件改变框架大小

        # 版本和作者信息（左侧）
        version_label = tk.Label(
            status_frame,
            text="版本 1.2.1 - 作者: GEORGEWU",
            bg=self.bg_color,
            fg="#666666",
            font=("Microsoft YaHei", 8),
            anchor=tk.W,
        )
        version_label.pack(side=tk.LEFT, padx=(5, 0))

        self.thread = None

    def browse_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.folder_entry.delete(0, tk.END)
            self.folder_entry.insert(0, folder)

    def log(self, message):
        """添加日志"""
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)

    def set_progress(self, current, total):
        """更新进度"""
        if total > 0:
            percentage = (current / total) * 100
            self.progress_var.set(percentage)
            self.progress_label.config(
                text=f"{current}/{total} ({percentage:.1f}%)", fg="blue"
            )
            self.root.update_idletasks()

    def start_download(self):
        url = self.url_entry.get().strip()
        folder = self.folder_entry.get().strip()

        if not url:
            messagebox.showwarning("警告", "请输入目标链接！")
            return

        if not folder:
            folder = "pippi_images"
            self.folder_entry.insert(0, folder)

        if not url.startswith(("http://", "https://")):
            messagebox.showwarning("警告", "链接必须以 http:// 或 https:// 开头！")
            return

        # 更新UI
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        self.progress_var.set(0)
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete(1.0, tk.END)
        self.log_text.config(state=tk.DISABLED)
        self.progress_label.config(text="正在下载...", fg="blue")

        # 启动线程
        self.thread = SpiderThread(url, folder, self)
        self.thread.daemon = True
        self.thread.start()

    def stop_download(self):
        if self.thread:
            self.thread.stop()
            self.log("⏹️ 正在停止...")
            self.stop_btn.config(state=tk.DISABLED)

    def download_finished(self, success, message):
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)

        # 重置进度条和状态标签
        self.progress_var.set(0)
        self.progress_label.config(text="就绪", fg="gray")

        if success:
            messagebox.showinfo("完成", message)
        else:
            messagebox.showerror("错误", message)


def main():
    root = tk.Tk()
    root.withdraw()  # 先隐藏窗口，避免显示在默认位置

    app = PippiGUI(root)

    # 计算窗口居中位置
    root.update_idletasks()  # 确保窗口已经更新

    # 使用实际设置的窗口尺寸，而不是请求尺寸
    # 从geometry字符串中提取宽度和高度
    geometry = root.geometry()

    if "x" in geometry:
        # 从"700x600+0+0"格式中提取宽度和高度
        size_part = geometry.split("+")[0]  # 取"700x600"部分
        width, height = map(int, size_part.split("x"))  # 分割为700和600
    else:
        # 如果解析失败，使用默认值
        width, height = 700, 600

    # 获取屏幕尺寸
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()

    # 计算居中位置 - 考虑到Windows任务栏和可能的边框
    # 通常Windows任务栏在底部，占约40像素高度
    taskbar_height = 40
    x = (screen_width // 2) - (width // 2)
    y = (screen_height // 2) - (height // 2) - (taskbar_height // 2)

    # 设置窗口位置（保持原有尺寸）
    root.geometry(f"{width}x{height}+{x}+{y}")

    # 验证设置后的几何信息
    final_geometry = root.geometry()

    # 现在显示窗口
    root.deiconify()

    root.mainloop()


if __name__ == "__main__":
    main()
