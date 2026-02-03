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

        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0',
        ]

        self.session.headers.update({
            'User-Agent': self.user_agents[0],
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9',
        })

        self.download_folder.mkdir(parents=True, exist_ok=True)
        self.downloaded_count = 0
        self.skipped_count = 0
        self.failed_count = 0
        self.image_extensions = ('.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp', '.tiff')
        self.existing_files = self._load_existing_files()

    def _load_existing_files(self):
        existing = set()
        if self.download_folder.exists():
            for f in self.download_folder.iterdir():
                if f.is_file():
                    existing.add(f.stem)
        print(f"📂 发现 {len(existing)} 个已下载的文件，将自动跳过")
        return existing

    def _get_random_delay(self, min_sec=1.5, max_sec=3.5):
        return random.uniform(min_sec, max_sec)

    def get_page(self, url, retries=3):
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
        if not html:
            return []

        images = []
        generic_pattern = r'https?://[^\s"<>\']+?\.(?:jpg|jpeg|png|webp|gif|bmp|tiff)(?:\?[^\s"<>\']*)?'
        matches = re.findall(generic_pattern, html, re.IGNORECASE)
        images.extend(matches)

        cdn_pattern = r'https?://image\.acg\.lol/file/\d{4}/\d{2}/\d{2}/[^"\s<>\']+\.(?:jpg|jpeg|png|webp)'
        cdn_matches = re.findall(cdn_pattern, html, re.IGNORECASE)
        images.extend(cdn_matches)

        if len(images) < 5:
            soup = BeautifulSoup(html, 'html.parser')
            for img in soup.find_all('img'):
                for attr in ['src', 'data-src', 'data-original', 'data-url']:
                    src = img.get(attr)
                    if src:
                        if src.startswith('//'):
                            src = 'https:' + src
                        elif src.startswith('/'):
                            if base_url:
                                src = base_url.rstrip('/') + src
                        elif not src.startswith('http'):
                            continue

                        if any(src.lower().endswith(ext) for ext in self.image_extensions) or \
                                any(ext in src.lower() for ext in self.image_extensions):
                            images.append(src)
                        break

        lazy_pattern = r'(?:data-|original-|lazy-)(?:src|url)["\']?\s*[=:]\s*["\']?(https?://[^\s"<>\']+?\.(?:jpg|jpeg|png|webp))'
        lazy_matches = re.findall(lazy_pattern, html, re.IGNORECASE)
        images.extend(lazy_matches)

        cleaned = []
        seen = set()
        for url in images:
            url = url.strip().rstrip('"\'').replace('\\/', '/')
            if url and url not in seen:
                seen.add(url)
                cleaned.append(url)

        print(f"🔍 找到 {len(cleaned)} 个图片链接")
        if cleaned:
            print(f"   示例: {cleaned[0][:60]}...")
        return cleaned

    def _get_filename(self, url, index):
        try:
            decoded_url = unquote(url)
            parsed = urlparse(decoded_url)
            path = parsed.path
            original_name = Path(path).name

            if original_name and '.' in original_name:
                clean_name = re.sub(r'[<>:"/\\|?*]', '_', original_name)
                clean_name = clean_name.split('?')[0]
                name = Path(clean_name).stem[:50]
                ext = Path(clean_name).suffix.lower()

                if ext not in self.image_extensions:
                    ext = '.jpg'

                return name, ext

        except Exception:
            pass

        url_hash = hashlib.md5(url.encode()).hexdigest()[:6]
        return f"img_{index:04d}_{url_hash}", ".jpg"

    def _is_exists(self, filename_stem):
        if filename_stem in self.existing_files:
            return True
        for ext in self.image_extensions:
            if (self.download_folder / f"{filename_stem}{ext}").exists():
                return True
        return False

    def download_image(self, url, index, retries=3):
        filename_stem, ext = self._get_filename(url, index)

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
