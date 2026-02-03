import requests
from bs4 import BeautifulSoup
import re
import os
import time
import random
import hashlib
from urllib.parse import urlparse, unquote
from pathlib import Path


class RobustImageSpider:
    def __init__(self, download_folder="pippi_images"):
        self.download_folder = Path(download_folder)
        self.session = requests.Session()

        # 多个 User-Agent 轮换
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0',
        ]

        # 基础 headers，**绝不包含 Referer**
        self.session.headers.update({
            'User-Agent': self.user_agents[0],
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9',
        })

        self.download_folder.mkdir(parents=True, exist_ok=True)
        self.downloaded_count = 0
        self.skipped_count = 0
        self.failed_count = 0

        # 支持多种图片格式
        self.image_extensions = ('.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp', '.tiff')

        # 加载已下载的文件列表
        self.existing_files = self._load_existing_files()

    def _load_existing_files(self):
        """加载已存在的文件列表"""
        existing = set()
        if self.download_folder.exists():
            for f in self.download_folder.iterdir():
                if f.is_file():
                    existing.add(f.stem)
        print(f"📂 发现 {len(existing)} 个已下载的文件，将自动跳过")
        return existing

    def _get_random_delay(self, min_sec=1.5, max_sec=3.5):
        """随机延迟"""
        return random.uniform(min_sec, max_sec)

    def get_page(self, url, retries=3):
        """获取页面，带重试"""
        for attempt in range(retries):
            try:
                time.sleep(self._get_random_delay(0.5, 1.5))

                headers = {
                    'User-Agent': random.choice(self.user_agents),
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                }

                r = self.session.get(url, headers=headers, timeout=15)
                r.raise_for_status()
                return r.text
            except Exception as e:
                print(f"  ⚠️ 获取失败 (尝试 {attempt + 1}/{retries}): {str(e)[:50]}")
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)
        return None

    def extract_images(self, html, base_url=None):
        """智能提取图片链接 - 支持多种模式"""
        if not html:
            return []

        images = []

        # 方法1: 通用正则 - 匹配所有常见图片格式
        # 匹配任意文件名，不限于DSC前缀
        generic_pattern = r'https?://[^\s"<>\']+?\.(?:jpg|jpeg|png|webp|gif|bmp|tiff)(?:\?[^\s"<>\']*)?'
        matches = re.findall(generic_pattern, html, re.IGNORECASE)
        images.extend(matches)

        # 方法2: 针对特定CDN优化（如acg.lol）
        cdn_pattern = r'https?://image\.acg\.lol/file/\d{4}/\d{2}/\d{2}/[^"\s<>\']+\.(?:jpg|jpeg|png|webp)'
        cdn_matches = re.findall(cdn_pattern, html, re.IGNORECASE)
        images.extend(cdn_matches)

        # 方法3: BeautifulSoup解析（备用）
        if len(images) < 5:  # 如果正则匹配太少，启用BS4
            soup = BeautifulSoup(html, 'html.parser')
            for img in soup.find_all('img'):
                for attr in ['src', 'data-src', 'data-original', 'data-url']:
                    src = img.get(attr)
                    if src:
                        # 处理相对路径
                        if src.startswith('//'):
                            src = 'https:' + src
                        elif src.startswith('/'):
                            if base_url:
                                src = base_url.rstrip('/') + src
                        elif not src.startswith('http'):
                            continue

                        # 检查是否是图片
                        if any(src.lower().endswith(ext) for ext in self.image_extensions) or \
                                any(ext in src.lower() for ext in self.image_extensions):
                            images.append(src)
                        break

        # 方法4: 匹配懒加载/背景图等
        lazy_pattern = r'(?:data-|original-|lazy-)(?:src|url)["\']?\s*[=:]\s*["\']?(https?://[^\s"<>\']+?\.(?:jpg|jpeg|png|webp))'
        lazy_matches = re.findall(lazy_pattern, html, re.IGNORECASE)
        images.extend(lazy_matches)

        # 清理和去重
        cleaned = []
        seen = set()
        for url in images:
            # 清理URL
            url = url.strip().rstrip('"\'').replace('\\/', '/')

            # 去重
            if url and url not in seen:
                seen.add(url)
                cleaned.append(url)

        print(f"🔍 找到 {len(cleaned)} 个图片链接")
        if cleaned:
            print(f"   示例: {cleaned[0][:60]}...")
        return cleaned

    def _get_filename(self, url, index):
        """智能生成文件名 - 保留原始文件名或生成新名称"""
        try:
            # URL解码
            decoded_url = unquote(url)
            parsed = urlparse(decoded_url)
            path = parsed.path

            # 尝试提取原始文件名
            original_name = Path(path).name

            # 清理文件名
            if original_name and '.' in original_name:
                # 移除查询参数和非法字符
                clean_name = re.sub(r'[<>:"/\\|?*]', '_', original_name)
                clean_name = clean_name.split('?')[0]  # 移除URL参数

                # 限制长度
                name = Path(clean_name).stem[:50]  # 限制50字符
                ext = Path(clean_name).suffix.lower()

                # 确保扩展名合法
                if ext not in self.image_extensions:
                    ext = '.jpg'

                return name, ext

        except Exception:
            pass

        # 备用方案：使用索引+哈希
        url_hash = hashlib.md5(url.encode()).hexdigest()[:6]
        return f"img_{index:04d}_{url_hash}", ".jpg"

    def _is_exists(self, filename_stem):
        """检查是否已存在"""
        if filename_stem in self.existing_files:
            return True
        for ext in self.image_extensions:
            if (self.download_folder / f"{filename_stem}{ext}").exists():
                return True
        return False

    def download_image(self, url, index, retries=3):
        """下载单张图片"""
        filename_stem, ext = self._get_filename(url, index)

        # 检查是否已存在
        if self._is_exists(filename_stem):
            self.skipped_count += 1
            print(f"  ⏭️  [{index}] {filename_stem}{ext} (已存在)")
            return True

        for attempt in range(retries):
            try:
                delay = min(1.5 + self.downloaded_count * 0.03, 5)
                time.sleep(random.uniform(delay, delay + 1.5))

                headers = {
                    'User-Agent': random.choice(self.user_agents),
                    'Accept': 'image/webp,image/apng,image/*,*/*;q=0.8',
                }

                r = self.session.get(url, headers=headers, timeout=20, stream=True)
                r.raise_for_status()

                filepath = self.download_folder / f"{filename_stem}{ext}"
                total_size = 0

                with open(filepath, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            total_size += len(chunk)

                if total_size < 1024:
                    filepath.unlink()
                    raise ValueError("文件过小")

                self.existing_files.add(filename_stem)
                self.downloaded_count += 1

                size_kb = total_size / 1024
                print(f"  ✓ [{index}] {filename_stem}{ext} ({size_kb:.1f} KB)")
                return True

            except Exception as e:
                if attempt < retries - 1:
                    time.sleep(2 ** attempt + random.uniform(0, 1))
                else:
                    self.failed_count += 1
                    print(f"  ❌ [{index}] 失败: {str(e)[:40]}")

        return False

    def crawl(self, target_url):
        """主函数"""
        print(f"\n{'=' * 60}")
        print(f"🚀 爬取: {target_url}")
        print(f"📁 目录: {self.download_folder.absolute()}")
        print(f"{'=' * 60}\n")

        html = self.get_page(target_url)
        if not html:
            print("❌ 获取页面失败")
            return 0

        images = self.extract_images(html, base_url=target_url)
        total = len(images)

        if not images:
            print("❌ 未找到任何图片")
            return 0

        print(f"🎯 共 {total} 张图片，开始下载...\n")

        for i, url in enumerate(images, 1):
            self.download_image(url, i)

            if i % 10 == 0 and i < total:
                rest = random.uniform(3, 6)
                print(f"💤 休息 {rest:.1f} 秒...")
                time.sleep(rest)

        print(f"\n{'=' * 60}")
        print(f"✅ 完成: 新下载 {self.downloaded_count}, 跳过 {self.skipped_count}, 失败 {self.failed_count}")
        print(f"{'=' * 60}")

        return self.downloaded_count


def get_user_input():
    """获取用户输入的URL"""
    print("\n" + "=" * 60)
    print("🕷️  欢迎使用皮皮蛛图片下载器")
    print("   支持任意格式: JPG PNG WEBP GIF 等")
    print("=" * 60)

    default_url = "https://bing.fullpx.com/"
    print(f"\n💡 提示：直接回车使用默认链接")
    print(f"   默认: {default_url}")

    while True:
        try:
            user_input = input("\n🔗 请输入要爬取的页面链接: ").strip()

            if not user_input:
                print(f"✓ 使用默认链接")
                return default_url

            if not user_input.startswith(('http://', 'https://')):
                print("⚠️  链接必须以 http:// 或 https:// 开头")
                continue

            if '.' not in user_input:
                print("⚠️  链接格式不正确")
                continue

            return user_input

        except KeyboardInterrupt:
            return None


def get_folder_name():
    """获取保存文件夹名称"""
    default_folder = "pippi_images"
    print(f"\n💡 提示：直接回车使用默认文件夹 '{default_folder}'")

    try:
        folder = input("📁 请输入保存文件夹名称: ").strip()
        if not folder:
            return default_folder

        folder = re.sub(r'[<>:"/\\|?*]', '_', folder)
        return folder or default_folder

    except KeyboardInterrupt:
        return default_folder


def confirm_download(url, folder):
    """确认下载信息"""
    print("\n" + "-" * 60)
    print("📋 下载信息确认:")
    print(f"   目标链接: {url}")
    print(f"   保存目录: {Path(folder).absolute()}")
    print("-" * 60)

    try:
        confirm = input("🚀 确认开始下载? [Y/n]: ").strip().lower()
        return confirm in ('', 'y', 'yes', '是')
    except KeyboardInterrupt:
        return False


def main():
    """主函数"""
    try:
        target_url = get_user_input()
        if not target_url:
            print("❌ 未提供有效链接")
            return

        folder_name = get_folder_name()

        if not confirm_download(target_url, folder_name):
            print("❌ 用户取消下载")
            return

        spider = RobustImageSpider(folder_name)
        spider.crawl(target_url)

        # 循环下载
        while True:
            try:
                print("\n" + "=" * 60)
                again = input("🔄 是否继续下载其他链接? [y/N]: ").strip().lower()
                if again not in ('y', 'yes', '是'):
                    print("👋 感谢使用，再见！")
                    break

                new_url = get_user_input()
                if not new_url:
                    break

                new_folder = get_folder_name()
                if not confirm_download(new_url, new_folder):
                    continue

                spider = RobustImageSpider(new_folder)
                spider.crawl(new_url)

            except KeyboardInterrupt:
                break

    except KeyboardInterrupt:
        print("\n\n👋 程序被用户中断")
    except Exception as e:
        print(f"\n❌ 程序出错: {e}")
    finally:
        input("\n按回车键退出...")


if __name__ == "__main__":
    main()
