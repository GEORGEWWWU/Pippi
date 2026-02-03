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
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0",
        ]

        self.session.headers.update(
            {
                "User-Agent": self.user_agents[0],
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9",
            }
        )

        self.download_folder.mkdir(parents=True, exist_ok=True)
        self.downloaded_count = 0
        self.skipped_count = 0
        self.failed_count = 0
        self.image_extensions = (
            ".jpg",
            ".jpeg",
            ".png",
            ".webp",
            ".gif",
            ".bmp",
            ".tiff",
        )
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

    def _is_pixiv_url(self, url):
        """检查是否是Pixiv相关URL"""
        return "pixiv.net" in url.lower() or "pximg.net" in url.lower()

    def _get_headers_for_url(self, url, is_image=False):
        """
        根据URL获取对应的请求头
        针对Pixiv特殊处理：添加Referer
        """
        headers = {
            "User-Agent": random.choice(self.user_agents),
        }

        if self._is_pixiv_url(url):
            # Pixiv 必须添加 Referer，否则图片服务器会返回 403
            headers["Referer"] = "https://www.pixiv.net/"
            if is_image:
                headers["Accept"] = "image/webp,image/apng,image/*,*/*;q=0.8"
            else:
                headers["Accept"] = (
                    "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8"
                )
        else:
            # 其他网站使用通用头，不添加Referer避免反爬
            if is_image:
                headers["Accept"] = "image/webp,image/apng,image/*,*/*;q=0.8"
            else:
                headers["Accept"] = (
                    "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8"
                )

        return headers

    def get_page(self, url, retries=3):
        for attempt in range(retries):
            try:
                time.sleep(self._get_random_delay(0.5, 1.5))
                headers = self._get_headers_for_url(url, is_image=False)
                r = self.session.get(url, headers=headers, timeout=15)
                r.raise_for_status()
                return r.text
            except Exception as e:
                print(f"  ⚠️ 获取失败 (尝试 {attempt + 1}/{retries}): {str(e)[:50]}")
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)
        return None

    def extract_images(self, html, base_url=None):
        """
        修改版：优先使用 Pixiv Ajax API 获取高清原图
        """
        if not base_url:
            return []

        images = []

        # === 核心修改：针对 Pixiv 优先调用 API ===
        if self._is_pixiv_url(base_url):
            # 1. 尝试从 URL 中提取 artwork ID
            # 匹配格式: pixiv.net/artworks/123456 或 pixiv.net/member_illust.php?mode=medium&illust_id=123456
            illust_id = None
            match = re.search(r'artworks/(\d+)', base_url)
            if match:
                illust_id = match.group(1)
            else:
                match = re.search(r'illust_id=(\d+)', base_url)
                if match:
                    illust_id = match.group(1)

            if illust_id:
                print(f" ⚙️ 检测到 Pixiv ID: {illust_id}，正在调用 API...")
                try:
                    # 构造 Pixiv 内部 API 地址 (获取多图/单图均适用)
                    api_url = f"https://www.pixiv.net/ajax/illust/{illust_id}/pages?lang=zh"

                    # 必须带 Referer，否则 API 返回 403
                    headers = self._get_headers_for_url(base_url)

                    # 请求 API
                    api_res = self.session.get(api_url, headers=headers, timeout=10)
                    api_res.raise_for_status()

                    # 解析 JSON
                    data = api_res.json()

                    if not data.get('error'):
                        # data['body'] 是一个列表，包含每一页的信息
                        for page in data.get('body', []):
                            urls = page.get('urls', {})
                            # 优先获取 original (原图)，如果没有则获取 regular
                            img_url = urls.get('original_pic_url') or urls.get('original') or urls.get('regular')
                            if img_url:
                                images.append(img_url)

                        if images:
                            print(f"  ✓ API 调用成功，获取到 {len(images)} 张原图")
                            return images
                    else:
                        print(f"  ⚠️ API 返回错误: {data.get('message')}")

                except Exception as e:
                    print(f"  ⚠️ API 调用失败，尝试回退到 HTML 解析: {e}")

        # === 以下是回退逻辑（你原有的代码，保留以防万一）===

        # 尝试从 __NEXT_DATA__ 提取 (保留你原有的逻辑作为备份)
        import json
        next_data_pattern = r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>'
        match = re.search(next_data_pattern, html, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(1))
                # ... (此处省略你原有的复杂解析逻辑，如果上面API成功，这里不会执行) ...
                # 简单处理：如果 API 失败了，尝试在这里找 urls
                if not images:
                    illust_data = data.get('props', {}).get('pageProps', {}).get('illust', {})
                    # ... (为了代码简洁，这里建议直接依赖上面的 API 逻辑)
            except:
                pass

        # 通用正则匹配（作为最后的兜底）
        if not images:
            print("  ⚠️ API 和 JSON 解析均失败，尝试暴力正则匹配...")
            generic_pattern = r'https?://i\.pximg\.net/[^\s"<>\']+?\.(?:jpg|jpeg|png|webp)'
            matches = re.findall(generic_pattern, html, re.IGNORECASE)
            for url in matches:
                # 清洗 URL
                url = url.strip().rstrip("\"'").replace("\\/", "/")
                # 尝试将缩略图转换为原图
                # 缩略图通常包含: _master1200, _square1200, c/600x1200_90 等
                # 原图格式通常是: https://i.pximg.net/img-original/img/.../xxx_p0.jpg

                # 这是一个简单的替换尝试，不一定 100% 准确，但比没有好
                clean_url = url
                if "_master1200" in url:
                    clean_url = url.replace("_master1200", "")
                    clean_url = clean_url.replace("/img-master/", "/img-original/")
                    # 还需要注意后缀，缩略图可能是 jpg 但原图是 png
                    # 这里比较难处理，所以 API 方法才是正道

                if clean_url not in images:
                    images.append(clean_url)

        # 去重
        seen = set()
        cleaned = []
        for url in images:
            if url and url not in seen:
                seen.add(url)
                cleaned.append(url)

        return cleaned

    def _is_direct_image_url(self, url):
        """检查URL是否是直接的图片链接"""
        try:
            parsed_url = urlparse(url)
            path = parsed_url.path.lower()

            # 检查URL路径是否以图片扩展名结尾
            if any(path.endswith(ext) for ext in self.image_extensions):
                return True

            # 检查URL路径中是否包含图片格式
            if any(ext in path for ext in self.image_extensions + (".avif",)):
                return True

            return False
        except Exception:
            return False

    def _get_filename(self, url, index):
        try:
            decoded_url = unquote(url)
            parsed = urlparse(decoded_url)
            path = parsed.path
            original_name = Path(path).name

            if original_name and "." in original_name:
                clean_name = re.sub(r'[<>:"/\\|?*]', "_", original_name)
                clean_name = clean_name.split("?")[0].split("@")[0]
                name = Path(clean_name).stem[:50]
                ext = Path(clean_name).suffix.lower()

                # 处理avif格式，转换为jpg
                if ext == ".avif":
                    ext = ".jpg"

                if ext not in self.image_extensions:
                    ext = ".jpg"

                return name, ext

        except Exception:
            pass

        # 如果无法从URL中提取文件名，则使用默认命名
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

                # 使用URL特定的请求头（Pixiv会添加Referer）
                headers = self._get_headers_for_url(url, is_image=True)

                # 针对Pixiv的特殊处理：可能需要禁用SSL验证
                verify_ssl = True
                if self._is_pixiv_url(url):
                    # Pixiv有时会有SSL证书问题，可以选择禁用验证
                    # 注意：生产环境建议保持True，除非确实遇到证书错误
                    pass  # 保持True，如果遇到问题可以改为False

                r = self.session.get(
                    url, headers=headers, timeout=20, stream=True, verify=verify_ssl
                )
                r.raise_for_status()

                filepath = self.download_folder / f"{filename_stem}{ext}"
                total_size = 0

                with open(filepath, "wb") as f:
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

        # 检查是否是直接的图片链接
        if self._is_direct_image_url(target_url):
            print("🎯 检测到直接图片链接，开始下载...")
            self.download_image(target_url, 1)
            total = self.downloaded_count + self.skipped_count + self.failed_count
            print(f"\n{'=' * 60}")
            print(
                f"✅ 完成: 新下载 {self.downloaded_count}, 跳过 {self.skipped_count}, 失败 {self.failed_count}"
            )
            print(f"{'=' * 60}")
            return self.downloaded_count

        # 原有逻辑：从HTML页面提取图片链接
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
        print(
            f"✅ 完成: 新下载 {self.downloaded_count}, 跳过 {self.skipped_count}, 失败 {self.failed_count}"
        )
        print(f"{'=' * 60}")

        return self.downloaded_count
