import requests
from bs4 import BeautifulSoup
import re
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

        # ========== 修改这里：添加你的 PHPSESSID ==========
        # 你只有这一个值，其他字段不是必须的，PHPSESSID 是核心
        self.pixiv_cookie = "PHPSESSID=88843137_JNDfSY4N0W1gND6Hu4Iuq3qCO2pFzRh3"
        # ================================================

        self.session.headers.update(
            {
                "User-Agent": self.user_agents[0],
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9",
                # 不要在这里加 Cookie 和 Referer！
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

    def _is_photos18_url(self, url):
        """检查是否是Photos18相关URL"""
        return "photos18.com" in url.lower()

    def _is_foamgirl_url(self, url):
        """检查是否是FoamGirl相关URL"""
        return "foamgirl.net" in url.lower()

    def _get_headers_for_url(self, url, is_image=False):
        """
        根据URL获取对应的请求头
        针对Pixiv和Photos18特殊处理：添加Referer和Cookie
        """
        headers = {
            "User-Agent": random.choice(self.user_agents),
        }

        if self._is_pixiv_url(url):
            # Pixiv 必须添加 Referer，否则图片服务器会返回 403
            headers["Referer"] = "https://www.pixiv.net/"

            # ========== 修改这里：添加你的 Cookie ==========
            headers["Cookie"] = self.pixiv_cookie
            # ===========================================

            if is_image:
                headers["Accept"] = "image/webp,image/apng,image/*,*/*;q=0.8"
            else:
                headers["Accept"] = (
                    "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8"
                )
        elif self._is_photos18_url(url):
            # Photos18 特殊处理
            headers["Referer"] = "https://www.photos18.com/"

            if is_image:
                headers["Accept"] = "image/avif,image/webp,image/apng,image/*,*/*;q=0.8"
            else:
                headers["Accept"] = (
                    "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8"
                )
        elif self._is_foamgirl_url(url):
            # FoamGirl 特殊处理
            headers["Referer"] = "https://foamgirl.net/"

            if is_image:
                headers["Accept"] = "image/webp,image/apng,image/*,*/*;q=0.8"
            else:
                headers["Accept"] = (
                    "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8"
                )
        else:
            # 其他网站不加 Referer 和 Cookie
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
                    time.sleep(2**attempt)
        return None

    def extract_images(self, html, base_url=None):
        """
        修改版：优先使用 Pixiv Ajax API 获取高清原图，其他网站使用通用解析
        """
        if not base_url:
            return []

        images = []

        # === Photos18.com 特殊处理 ===
        if "photos18.com" in base_url.lower():
            print(" ⚙️ 检测到 Photos18.com，使用特定解析规则...")
            soup = BeautifulSoup(html, "html.parser")

            # 查找所有包含图片的div
            img_holders = soup.find_all("div", class_="imgHolder")
            if not img_holders:
                # 如果没有找到imgHolder，尝试其他可能的类名
                img_holders = soup.find_all(
                    "div", class_=lambda x: x and "img" in x.lower()
                )

            for holder in img_holders:
                # 查找img标签
                img_tag = holder.find("img")
                if img_tag:
                    src = (
                        img_tag.get("src")
                        or img_tag.get("data-src")
                        or img_tag.get("data-original")
                    )
                    if src and "photos18.com" in src:
                        # 处理URL，确保是完整URL
                        if src.startswith("//"):
                            src = "https:" + src
                        elif src.startswith("/"):
                            from urllib.parse import urljoin

                            src = urljoin(base_url, src)

                        # 确保是avif格式
                        if ".avif" in src:
                            images.append(src)

                # 也检查a标签的href
                a_tag = holder.find("a")
                if a_tag:
                    href = a_tag.get("href")
                    if href and "photos18.com" in href and ".avif" in href:
                        # 处理URL，确保是完整URL
                        if href.startswith("//"):
                            href = "https:" + href
                        elif href.startswith("/"):
                            from urllib.parse import urljoin

                            href = urljoin(base_url, href)

                        if href not in images:
                            images.append(href)

            # 如果上面的方法没找到图片，尝试正则匹配
            if not images:
                # 使用正则表达式匹配photos18.com的avif图片
                pattern = r'https?://(?:www\.)?photos18\.com[^\s<>"{}|\\^`\[\]]*?\.avif[^\s<>"{}|\\^`\[\]]*?'
                matches = re.findall(pattern, html, re.IGNORECASE)
                for url in matches:
                    if url not in images:
                        images.append(url)

            if images:
                print(f"  ✓ Photos18.com 解析找到 {len(images)} 张图片")
                # 去重后返回
                seen = set()
                cleaned = []
                for url in images:
                    if url and url not in seen:
                        seen.add(url)
                        cleaned.append(url)
                return cleaned

        # === FoamGirl.net 特殊处理 ===
        if "foamgirl.net" in base_url.lower():
            print(" ⚙️ 检测到 FoamGirl.net，使用特定解析规则...")
            soup = BeautifulSoup(html, "html.parser")

            # 查找所有带有 imageclick-imgbox 类的 a 标签
            img_links = soup.find_all("a", class_="imageclick-imgbox")

            for link in img_links:
                # 获取 href 属性
                href = link.get("href")
                if href and "cdn.foamgirl.net" in href:
                    # 处理URL，确保是完整URL
                    if href.startswith("//"):
                        href = "https:" + href
                    elif href.startswith("/"):
                        from urllib.parse import urljoin

                        href = urljoin(base_url, href)

                    # 确保是webp格式
                    if any(
                        ext in href.lower()
                        for ext in [".webp", ".jpg", ".jpeg", ".png"]
                    ):
                        images.append(href)

                # 也检查img标签的src
                img_tag = link.find("img")
                if img_tag:
                    src = (
                        img_tag.get("src")
                        or img_tag.get("data-src")
                        or img_tag.get("data-original")
                    )
                    if src and "cdn.foamgirl.net" in src:
                        # 处理URL，确保是完整URL
                        if src.startswith("//"):
                            src = "https:" + src
                        elif src.startswith("/"):
                            from urllib.parse import urljoin

                            src = urljoin(base_url, src)

                        # 确保是webp格式
                        if any(
                            ext in src.lower()
                            for ext in [".webp", ".jpg", ".jpeg", ".png"]
                        ):
                            if src not in images:
                                images.append(src)

            # 如果上面的方法没找到图片，尝试正则匹配
            if not images:
                # 使用正则表达式匹配foamgirl.net的图片
                pattern = r'https?://cdn\.foamgirl\.net[^\s<>"{}|\\^`\[\]]*?\.(?:webp|jpg|jpeg|png)[^\s<>"{}|\\^`\[\]]*?'
                matches = re.findall(pattern, html, re.IGNORECASE)
                for url in matches:
                    if url not in images:
                        images.append(url)

            if images:
                print(f"  ✓ FoamGirl.net 解析找到 {len(images)} 张图片")
                # 去重后返回
                seen = set()
                cleaned = []
                for url in images:
                    if url and url not in seen:
                        seen.add(url)
                        cleaned.append(url)
                return cleaned
        if self._is_pixiv_url(base_url):
            illust_id = None
            match = re.search(r"artworks/(\d+)", base_url)
            if match:
                illust_id = match.group(1)
            else:
                match = re.search(r"illust_id=(\d+)", base_url)
                if match:
                    illust_id = match.group(1)

            if illust_id:
                print(f" ⚙️ 检测到 Pixiv ID: {illust_id}，正在调用 API...")
                try:
                    # 注意：这里有个空格！删除它
                    api_url = (
                        f"https://www.pixiv.net/ajax/illust/{illust_id}/pages?lang=zh"
                    )
                    headers = self._get_headers_for_url(base_url)
                    api_res = self.session.get(api_url, headers=headers, timeout=10)
                    api_res.raise_for_status()
                    data = api_res.json()

                    if not data.get("error"):
                        for page in data.get("body", []):
                            urls = page.get("urls", {})
                            img_url = (
                                urls.get("original_pic_url")
                                or urls.get("original")
                                or urls.get("regular")
                            )
                            if img_url:
                                images.append(img_url)

                        if images:
                            print(f"  ✓ API 调用成功，获取到 {len(images)} 张原图")
                            return images  # Pixiv 成功直接返回
                    else:
                        print(f"  ⚠️ API 返回错误: {data.get('message')}")

                except Exception as e:
                    print(f"  ⚠️ API 调用失败，尝试回退到 HTML 解析: {e}")
                    # Pixiv API 失败继续走下面的通用解析，不要 return

        # === 通用网站解析（百度、Google 等）===
        if not images:  # Pixiv 没成功或不是 Pixiv，执行通用解析
            print("  🔍 使用通用解析规则...")

            # 方法1: 从 img 标签提取
            soup = BeautifulSoup(html, "html.parser")
            for img in soup.find_all("img"):
                src = img.get("src") or img.get("data-src") or img.get("data-original")
                if src:
                    # 补全相对路径
                    if src.startswith("//"):
                        src = "https:" + src
                    elif src.startswith("/"):
                        from urllib.parse import urljoin

                        src = urljoin(base_url, src)

                    # 过滤小图标和无效链接
                    if any(
                        ext in src.lower()
                        for ext in [".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"]
                    ):
                        if not any(
                            x in src
                            for x in ["icon", "logo", "avatar", "thumb", "sprite"]
                        ):
                            images.append(src)

            # 方法2: 正则匹配 URL 模式的图片
            if not images:
                url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+?\.(?:jpg|jpeg|png|webp|gif|bmp)(?:\?[^"\s<>]*)?'
                matches = re.findall(url_pattern, html, re.IGNORECASE)
                for url in matches:
                    if url not in images and not any(
                        x in url for x in ["icon", "logo", "avatar"]
                    ):
                        images.append(url)

            if images:
                print(f"  ✓ 通用解析找到 {len(images)} 张图片")

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
                    time.sleep(2**attempt + random.uniform(0, 1))
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
