#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════╗
║          🌊 MERGOHYDROX 🌊                                ║
║     Backup & Convertitore vBulletin — Edizione Acquatica  ║
╚══════════════════════════════════════════════════════════╝
"""

import os
import re
import time
import json
import gc
import base64
import mimetypes
import threading
import multiprocessing as mp
from datetime import datetime
from pathlib import Path
from collections import defaultdict
from urllib.parse import urljoin, urlparse, urldefrag
from queue import Queue

import requests
from bs4 import BeautifulSoup
from pypdf import PdfWriter, PdfReader

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import tkinter.font as tkfont

# ─────────────────────────────────────────────
#  COLORI & TEMA ACQUATICO
# ─────────────────────────────────────────────
BG_DEEP     = "#031420"
BG_MID      = "#04202f"
BG_PANEL    = "#0a2e3f"
ACCENT_GOLD = "#4fd9e8"
ACCENT_PURP = "#1f8fb0"
ACCENT_TEAL = "#3ecfcf"
RUNE_RED    = "#c0392b"
TEXT_MAIN   = "#dff6fa"
TEXT_DIM    = "#6f9fae"
BORDER_GLOW = "#0e5a72"

RUNE_SYMBOLS = ["○","◌","∘","•","◦","⚬","𓂀","≈","∽","〰","◯","⊙","○","∘",
                "◌","•","≈","〰","∽","⚬","◦","○","∘","◌","•"]

# Estensioni trattate come contenuti multimediali scaricabili
IMAGE_EXTS = {'.jpg','.jpeg','.png','.gif','.webp','.bmp','.svg','.tiff','.avif'}
VIDEO_EXTS = {'.mp4','.webm','.mov','.avi','.mkv','.ogv','.flv','.m4v'}
AUDIO_EXTS = {'.mp3','.ogg','.wav','.aac','.flac','.m4a','.opus'}
MEDIA_EXTS = IMAGE_EXTS | VIDEO_EXTS | AUDIO_EXTS

# ─────────────────────────────────────────────
#  FUNZIONI DI SUPPORTO
# ─────────────────────────────────────────────

def clean_text(text):
    return ' '.join(text.strip().replace('\r','').replace('\xa0',' ').split())
def parse_date(text):
    if not text:
        return None
    text = text.strip()
    try:
        cleaned = text.replace('Z', '+00:00')
        return datetime.fromisoformat(cleaned)
    except:
        pass
    try:
        return datetime.strptime(text, '%b %d, %Y at %I:%M %p')
    except:
        pass
    for fmt in ('%b %d, %Y', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%d-%m-%Y', '%m/%d/%Y'):
        try:
            return datetime.strptime(text, fmt)
        except:
            pass
    return None
def safe_filename(name, maxlen=80):
    return re.sub(r'[<>:"/\\|?*\n\r\t]', '_', name)[:maxlen]
def get_ext(url):
    path = urlparse(url).path
    _, ext = os.path.splitext(path)
    return ext.lower()
def guess_mime(url, data=None):
    ext = get_ext(url)
    mime = mimetypes.guess_type('file' + ext)[0]
    if mime:
        return mime
    if data and len(data) >= 4:
        sig = data[:4]
        if sig[:3] == b'\xff\xd8\xff':   return 'image/jpeg'
        if sig[:4] == b'\x89PNG':         return 'image/png'
        if sig[:6] in (b'GIF87a',b'GIF89a'[:4]): return 'image/gif'
        if sig[:4] == b'RIFF':           return 'video/webm'
    return 'application/octet-stream'
def data_uri(data_bytes, mime):
    b64 = base64.b64encode(data_bytes).decode('ascii')
    return f"data:{mime};base64,{b64}"

# ─────────────────────────────────────────────
#  DOWNLOADER MEDIA
# ─────────────────────────────────────────────

class MediaDownloader:
    def __init__(self, output_dir, delay=0.3, log_callback=None, stop_event=None):
        self.media_dir   = os.path.join(output_dir, 'media')
        self.delay       = delay
        self.log         = log_callback or print
        self._stop       = stop_event or threading.Event()
        self._index_file = os.path.join(self.media_dir, '_media_index.json')
        os.makedirs(self.media_dir, exist_ok=True)
        self._index = self._load_index()
    def _load_index(self):
        if os.path.exists(self._index_file):
            try:
                with open(self._index_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        return {}
    def _save_index(self):
        try:
            with open(self._index_file, 'w', encoding='utf-8') as f:
                json.dump(self._index, f, indent=2, ensure_ascii=False)
        except:
            pass
    def _fetch_bytes(self, url):
        try:
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
            r = requests.get(url, headers=headers, timeout=20, stream=True)
            r.raise_for_status()
            chunks = []
            for chunk in r.iter_content(65536):
                if self._stop.is_set():
                    return None
                chunks.append(chunk)
            return b''.join(chunks)
        except Exception as e:
            self.log(f"    ⚠ Media saltato ({os.path.basename(urlparse(url).path)}): {e}")
            return None
    def download_from_html(self, html_content, page_base_url):
        soup = BeautifulSoup(html_content, 'html.parser')
        urls = set()
        for tag in soup.find_all('img', src=True):
            urls.add(urljoin(page_base_url, tag['src']))
        for tag in soup.find_all(['video','audio'], src=True):
            urls.add(urljoin(page_base_url, tag['src']))
        for tag in soup.find_all('source', src=True):
            urls.add(urljoin(page_base_url, tag['src']))
        for tag in soup.find_all('a', href=True):
            href = urljoin(page_base_url, tag['href'])
            if get_ext(href) in MEDIA_EXTS:
                urls.add(href)
        for tag in soup.find_all(attrs={'data-src': True}):
            urls.add(urljoin(page_base_url, tag['data-src']))
        soup.decompose()
        media_urls = [u for u in urls if get_ext(u) in MEDIA_EXTS and urlparse(u).scheme in ('http','https')]
        downloaded = 0
        for url in media_urls:
            if self._stop.is_set():
                break
            if url in self._index:
                continue
            data = self._fetch_bytes(url)
            if data is None:
                continue
            ext  = get_ext(url) or '.bin'
            fname = safe_filename(os.path.basename(urlparse(url).path) or 'media', 120)
            if not fname.lower().endswith(ext):
                fname += ext
            fpath = os.path.join(self.media_dir, fname)
            counter = 1
            while os.path.exists(fpath):
                base, e = os.path.splitext(fname)
                fpath = os.path.join(self.media_dir, f"{base}_{counter}{e}")
                counter += 1
            try:
                with open(fpath, 'wb') as f:
                    f.write(data)
                self._index[url] = os.path.basename(fpath)
                downloaded += 1
                self.log(f"    📥 Media: {os.path.basename(fpath)}")
                time.sleep(self.delay)
            except Exception as e:
                self.log(f"    ⚠ Impossibile salvare il media: {e}")
        self._save_index()
        return downloaded
    def get_local_path(self, url):
        fname = self._index.get(url)
        if fname:
            return os.path.join(self.media_dir, fname)
        return None
    def get_base64_uri(self, url):
        path = self.get_local_path(url)
        if path and os.path.exists(path):
            try:
                with open(path, 'rb') as f:
                    data = f.read()
                mime = guess_mime(url, data)
                return data_uri(data, mime)
            except:
                pass
        return None

# ─────────────────────────────────────────────
#  LOGICA DI BACKUP
# ─────────────────────────────────────────────

class VBulletinBackup:
    def __init__(self, base_url, output_dir="backup", delay=1.0, max_workers=10,
                 start_page=1, log_callback=None, download_media=False, stop_event=None):
        self.base_url       = base_url.rstrip('/')
        self.output_dir     = output_dir
        self.delay          = delay
        self.max_workers    = max_workers
        self.start_page     = start_page
        self.log            = log_callback or print
        self.download_media = download_media
        os.makedirs(output_dir, exist_ok=True)
        self.metadata_file  = os.path.join(output_dir, 'backup_metadata.json')
        self.metadata       = self.load_metadata()
        self._stop_event    = stop_event or threading.Event()
        self._media_dl      = MediaDownloader(output_dir, delay=delay*0.5,
                                              log_callback=log_callback,
                                              stop_event=self._stop_event) if download_media else None
        self.force_gc()
    def force_gc(self):
        for _ in range(3): gc.collect()
    def load_metadata(self):
        if os.path.exists(self.metadata_file):
            try:
                with open(self.metadata_file,'r',encoding='utf-8') as f:
                    return json.load(f)
            except: pass
        return {'threads':{},'last_backup':None,'total_threads':0,'completed_threads':0}
    def save_metadata(self):
        self.metadata['last_backup'] = datetime.now().isoformat()
        with open(self.metadata_file,'w',encoding='utf-8') as f:
            json.dump(self.metadata, f, indent=2, ensure_ascii=False)
        self.force_gc()
    def get_page(self, url):
        session = response = None
        try:
            session = requests.Session()
            session.headers.update({'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})
            response = session.get(url, timeout=30, stream=True)
            response.raise_for_status()
            content = ""
            for chunk in response.iter_content(chunk_size=8192, decode_unicode=True):
                if chunk: content += chunk
            return content
        except Exception as e:
            self.log(f"  ⚠ Errore durante lo scaricamento di {url}: {e}")
            return None
        finally:
            if response: response.close(); del response
            if session:  session.close();  del session
            self.force_gc()
    def extract_thread_links(self, html_content, base_url):
        thread_links = []
        soup = None
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            for pattern in ['a[href*="showthread.php"]','a[href*="/threads/"]','a[href*="viewtopic.php"]']:
                for link in soup.select(pattern):
                    href = link.get('href')
                    if href:
                        full_url  = urljoin(base_url, href)
                        thread_id = self.extract_thread_id(full_url)
                        if thread_id:
                            thread_links.append({'id':thread_id,'url':full_url,'title':link.get_text(strip=True)})
        finally:
            if soup: soup.decompose(); del soup
            del html_content
            self.force_gc()
        seen, unique = set(), []
        for t in thread_links:
            if t['id'] not in seen:
                seen.add(t['id']); unique.append(t)
        return unique
    def extract_thread_id(self, url):
        for p in [r'showthread\.php.*[?&]t=(\d+)',r'/threads/[^/]*\.(\d+)',r'viewtopic\.php.*[?&]t=(\d+)']:
            m = re.search(p, url)
            if m: return m.group(1)
        return None
    def get_all_pages_urls(self, section_url):
        pages = [section_url]
        html_content = soup = None
        try:
            html_content = self.get_page(section_url)
            if not html_content: return pages
            soup = BeautifulSoup(html_content, 'html.parser')
            page_numbers = set()
            for link in soup.find_all("a", href=True):
                m = re.search(r'(?:[?&]page=|/page-)(\d+)', link["href"])
                if m: page_numbers.add(int(m.group(1)))
            if page_numbers:
                for page_num in range(self.start_page, max(page_numbers)+1):
                    if page_num == 1:
                        pages.append(section_url)
                    elif "/page-" in section_url:
                        pages.append(re.sub(r'/page-\d+','',section_url.rstrip('/'))+f"/page-{page_num}")
                    elif '?' in section_url:
                        pages.append(f"{section_url}&page={page_num}")
                    else:
                        pages.append(f"{section_url}?page={page_num}")
        finally:
            if soup: soup.decompose(); del soup
            if html_content: del html_content
            self.force_gc()
        return pages
    def discover_all_threads(self):
        self.log(f"🌊 Scansione della sezione: {self.base_url}")
        all_threads = []
        pages = self.get_all_pages_urls(self.base_url)
        self.log(f"📄 Trovate {len(pages)} pagine da scansionare...")
        def process_page(page_url):
            if self._stop_event.is_set(): return []
            try:
                self.log(f"  → Scansione: {page_url}")
                html_content = self.get_page(page_url)
                if not html_content: return []
                threads = self.extract_thread_links(html_content, self.base_url)
                self.log(f"  💧 Trovate {len(threads)} discussioni in questa pagina")
                time.sleep(self.delay)
                return threads
            except Exception as e:
                self.log(f"  ⚠ Errore: {e}"); return []
            finally: self.force_gc()
        from concurrent.futures import ThreadPoolExecutor, as_completed
        with ThreadPoolExecutor(max_workers=min(self.max_workers,6)) as executor:
            futures = [executor.submit(process_page, url) for url in pages]
            for future in as_completed(futures):
                if self._stop_event.is_set(): break
                try: all_threads.extend(future.result())
                except Exception as e: self.log(f"⚠ {e}")
                finally: self.force_gc()
        seen, unique = set(), []
        for t in all_threads:
            if t['id'] not in seen:
                seen.add(t['id']); unique.append(t)
        self.log(f"🌟 Totale discussioni uniche trovate: {len(unique)}")
        return unique
    def get_thread_pages(self, thread_url, html_content):
        pages = [thread_url]; soup = None
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            page_numbers = set()
            selectors = ['div.pagenav a[href]','div.pagination a[href]','div.pageNav a[href]',
                         'div.pages a[href]','td.pagenav a[href]','table.pagenav a[href]',
                         'ul.pagenav a[href]','nav.pagination a[href]',
                         'a[href*="page="]','a[href*="&page="]','a[href*="/page-"]']
            hrefs = set()
            for sel in selectors:
                for link in soup.select(sel):
                    href = link.get('href')
                    if href: hrefs.add(href)
            for href in hrefs:
                m = re.search(r'(?:[?&/](?:page|p)[=-]?)(\d+)', href)
                if m: page_numbers.add(int(m.group(1)))
            if page_numbers:
                base = re.sub(r'([?&/](?:page|p)[=-]?\d+)','',thread_url).rstrip('/')
                for i in range(2, max(page_numbers)+1):
                    if re.search(r'/page-\d+', thread_url):
                        pages.append(re.sub(r'/page-\d+','',base)+f"/page-{i}")
                    else:
                        sep = '&' if '?' in base else '?'
                        pages.append(f"{base}{sep}page={i}")
        finally:
            if soup: soup.decompose(); del soup
            self.force_gc()
        return pages
    def download_thread(self, thread):
        if self._stop_event.is_set(): return False
        thread_id    = thread['id']
        thread_url   = thread['url']
        thread_title = thread['title']
        stitle       = safe_filename(thread_title)
        self.log(f"  ⬇ Discussione {thread_id}: {thread_title[:55]}...")
        html_content = thread_pages = None
        try:
            html_content = self.get_page(thread_url)
            if not html_content: return False
            thread_pages = self.get_thread_pages(thread_url, html_content)
        finally:
            if html_content: del html_content
            self.force_gc()
        downloaded_pages = 0; previous_size = None
        for page_num, page_url in enumerate(thread_pages, 1):
            if self._stop_event.is_set(): break
            filename = f"thread_{thread_id}_{stitle}__page{page_num}.html"
            filepath = os.path.join(self.output_dir, filename)
            page_content = None
            try:
                if os.path.exists(filepath):
                    downloaded_pages += 1
                    previous_size = os.path.getsize(filepath)
                    if self._media_dl and previous_size:
                        with open(filepath,'r',encoding='utf-8',errors='ignore') as f:
                            saved_html = f.read()
                        self._media_dl.download_from_html(saved_html, page_url)
                    continue
                page_content = self.get_page(page_url)
                if not page_content: continue
                current_size = len(page_content.encode('utf-8'))
                if previous_size is not None and current_size == previous_size: break
                with open(filepath,'w',encoding='utf-8') as f:
                    f.write(page_content)
                downloaded_pages += 1; previous_size = current_size
                if self._media_dl:
                    self._media_dl.download_from_html(page_content, page_url)
                time.sleep(self.delay)
            except Exception as e:
                self.log(f"  ⚠ Errore alla pagina {page_num}: {e}")
            finally:
                if page_content: del page_content
                self.force_gc()
        self.metadata['threads'][thread_id] = {
            'title':thread_title,'url':thread_url,
            'pages':downloaded_pages,'downloaded_at':datetime.now().isoformat()
        }
        return True
    def run_backup(self, progress_callback=None):
        from concurrent.futures import ThreadPoolExecutor, as_completed
        self.log("✨ Avvio del backup della sezione vBulletin...")
        threads = self.discover_all_threads()
        if not threads:
            self.log("⚠ Nessuna discussione trovata!"); return 0
        self.metadata['total_threads'] = len(threads)
        threads_to_download = [t for t in threads if t['id'] not in self.metadata['threads']]
        self.log(f"📚 Discussioni da scaricare: {len(threads_to_download)}")
        successful = completed = 0
        def download_single(thread):
            try:
                result = self.download_thread(thread)
                if not result:
                    time.sleep(self.delay*2)
                    result = self.download_thread(thread)
                return result, thread
            except Exception as e:
                self.log(f"⚠ Errore nella discussione {thread['id']}: {e}")
                return False, thread
            finally: self.force_gc()
        with ThreadPoolExecutor(max_workers=min(self.max_workers,8)) as executor:
            future_to_thread = {executor.submit(download_single,t):t for t in threads_to_download}
            for future in as_completed(future_to_thread):
                if self._stop_event.is_set(): break
                completed += 1
                try:
                    result, _ = future.result()
                    if result:
                        successful += 1
                        self.metadata['completed_threads'] = successful
                        self.save_metadata()
                    if progress_callback:
                        progress_callback(completed, len(threads_to_download))
                    self.log(f"  💧 Avanzamento: {completed}/{len(threads_to_download)} discussioni")
                except Exception as e:
                    self.log(f"⚠ {e}")
                finally: self.force_gc()
        self.log(f"🏆 Backup completato! {successful}/{len(threads)} discussioni scaricate.")
        self.save_metadata()
        return successful


# ─────────────────────────────────────────────
#  CONVERTITORE HTML
# ─────────────────────────────────────────────

HTML_CSS = """
:root {
  --bg:        #041420;
  --bg2:       #06202f;
  --bg3:       #0a2e3f;
  --gold:      #4fd9e8;
  --gold2:     #7ce8f2;
  --purp:      #1f8fb0;
  --teal:      #3ecfcf;
  --text:      #dff6fa;
  --dim:       #6f9fae;
  --border:    #0e5a72;
  --op-bg:     #0a2c3d;
  --re-bg:     #072330;
  --tag:       #0e5a72;
}
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
html { scroll-behavior: smooth; }
body {
  background: var(--bg);
  color: var(--text);
  font-family: 'Palatino Linotype', Palatino, Georgia, serif;
  font-size: 16px;
  line-height: 1.75;
  min-height: 100vh;
}
/* ── INTESTAZIONE ── */
#site-header {
  background: linear-gradient(160deg, #031824 0%, #0a2e45 60%, #031420 100%);
  border-bottom: 1px solid var(--border);
  padding: 48px 32px 36px;
  text-align: center;
  position: relative;
  overflow: hidden;
}
#site-header::before {
  content: '○ ◦ ∘ ◌ 〰 ≈ ○ ◦ ∘ ◌ 〰 ≈ ○ ◦ ∘ ◌ 〰 ≈ ○ ◦ ∘ ◌ 〰 ≈';
  position: absolute; top: 8px; left: 0; right: 0;
  font-size: 14px; letter-spacing: 10px; color: #123a4a;
  pointer-events: none; white-space: nowrap; overflow: hidden;
}
#site-header::after {
  content: '≈ 〰 ◌ ∘ ◦ ○ ≈ 〰 ◌ ∘ ◦ ○ ≈ 〰 ◌ ∘ ◦ ○ ≈ 〰 ◌ ∘ ◦ ○';
  position: absolute; bottom: 6px; left: 0; right: 0;
  font-size: 14px; letter-spacing: 10px; color: #123a4a;
  pointer-events: none; white-space: nowrap; overflow: hidden;
}
.header-sigil { font-size: 36px; margin-bottom: 10px; opacity: 0.6; }
h1.site-title {
  font-size: clamp(22px, 4vw, 36px);
  color: var(--gold);
  letter-spacing: 3px;
  font-weight: bold;
  text-shadow: 0 0 30px rgba(201,168,76,0.4);
}
.site-sub {
  margin-top: 8px;
  font-size: 14px;
  color: var(--dim);
  font-style: italic;
  letter-spacing: 1px;
}
/* ── LAYOUT ── */
.container { max-width: 1100px; margin: 0 auto; padding: 32px 20px 60px; }
/* ── INDEX ── */
#toc {
  background: var(--bg2);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 28px 32px;
  margin-bottom: 48px;
}
#toc h2 {
  color: var(--gold);
  font-size: 18px;
  letter-spacing: 2px;
  margin-bottom: 18px;
  display: flex;
  align-items: center;
  gap: 10px;
}
#toc h2::before { content: '≈'; color: var(--purp); }
.toc-list { list-style: none; columns: 2; column-gap: 32px; }
@media (max-width: 700px) { .toc-list { columns: 1; } }
.toc-list li { margin-bottom: 8px; break-inside: avoid; }
.toc-list a {
  color: var(--teal);
  text-decoration: none;
  font-size: 14px;
  transition: color .2s;
  display: flex; align-items: flex-start; gap: 6px;
}
.toc-list a::before { content: '○'; font-size: 11px; color: var(--purp); flex-shrink: 0; margin-top: 3px; }
.toc-list a:hover { color: var(--gold2); }
/* ── THREAD BLOCK ── */
.thread-block {
  margin-bottom: 56px;
  border: 1px solid var(--border);
  border-radius: 14px;
  overflow: hidden;
  box-shadow: 0 4px 32px rgba(0,0,0,0.5);
}
.thread-header {
  background: linear-gradient(135deg, #0a2e45 0%, #0e4560 100%);
  padding: 22px 28px;
  display: flex;
  align-items: center;
  gap: 14px;
  border-bottom: 1px solid var(--border);
}
.thread-sigil { font-size: 22px; color: var(--purp); flex-shrink: 0; }
.thread-title {
  font-size: 20px;
  color: var(--gold2);
  font-weight: bold;
  letter-spacing: 0.5px;
  word-break: break-word;
}
.thread-count {
  margin-left: auto; flex-shrink: 0;
  font-size: 12px; color: var(--dim);
  background: var(--tag);
  padding: 4px 10px; border-radius: 20px;
}
/* ── POST ── */
.post {
  padding: 24px 28px;
  border-bottom: 1px solid #0a2c3d;
  transition: background .2s;
}
.post:last-child { border-bottom: none; }
.post:hover { background: rgba(255,255,255,0.015); }
.post.original { background: var(--op-bg); }
.post.reply    { background: var(--re-bg); }
.post-meta {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-bottom: 14px;
  flex-wrap: wrap;
}
.post-badge {
  font-size: 10px; letter-spacing: 1.5px; text-transform: uppercase;
  padding: 3px 10px; border-radius: 20px; font-weight: bold;
}
.badge-original { background: var(--purp); color: #f0e8ff; }
.badge-reply    { background: var(--tag);  color: var(--teal); }
.post-author {
  color: var(--gold);
  font-weight: bold;
  font-size: 15px;
}
.post-author::before { content: '≈ '; color: var(--purp); font-size: 12px; }
.post-date {
  color: var(--dim);
  font-size: 13px;
  font-style: italic;
}
.post-date::before { content: '· '; }
.post-body {
  color: var(--text);
  font-size: 15px;
  line-height: 1.8;
  white-space: pre-wrap;
  word-break: break-word;
}
/* ── MEDIA ── */
.post-media {
  margin-top: 16px;
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}
.post-media img {
  max-width: 480px; max-height: 360px;
  border-radius: 8px;
  border: 1px solid var(--border);
  cursor: zoom-in;
  object-fit: contain;
  background: #031420;
  transition: transform .2s, box-shadow .2s;
}
.post-media img:hover {
  transform: scale(1.02);
  box-shadow: 0 0 20px rgba(31,143,176,0.5);
}
.post-media video {
  max-width: 560px;
  border-radius: 8px;
  border: 1px solid var(--border);
}
.post-media audio {
  width: 100%;
  max-width: 480px;
  filter: invert(0.8) hue-rotate(220deg);
}
.media-link {
  display: inline-flex; align-items: center; gap: 6px;
  color: var(--teal); text-decoration: none;
  font-size: 13px;
  background: var(--tag); padding: 6px 14px; border-radius: 20px;
  transition: background .2s;
}
.media-link:hover { background: var(--purp); }
/* ── LIGHTBOX ── */
#lightbox {
  display: none; position: fixed; inset: 0;
  background: rgba(0,0,0,0.92);
  z-index: 9999;
  justify-content: center; align-items: center;
  cursor: zoom-out;
}
#lightbox.open { display: flex; }
#lightbox img {
  max-width: 92vw; max-height: 92vh;
  border-radius: 10px;
  box-shadow: 0 0 60px rgba(31,143,176,0.6);
}
/* ── SCROLL TOP ── */
#scroll-top {
  position: fixed; bottom: 28px; right: 28px;
  background: var(--purp); color: var(--gold);
  border: none; border-radius: 50%;
  width: 46px; height: 46px; font-size: 20px;
  cursor: pointer;
  box-shadow: 0 0 16px rgba(31,143,176,0.5);
  display: none; align-items: center; justify-content: center;
  transition: background .2s;
  z-index: 100;
}
#scroll-top:hover { background: var(--gold); color: var(--bg); }
/* ── FOOTER ── */
footer {
  text-align: center; padding: 28px;
  font-size: 13px; color: var(--dim);
  border-top: 1px solid var(--border);
  letter-spacing: 1px;
}
footer span { color: var(--purp); }
"""

HTML_JS = """
// Lightbox
const lb = document.getElementById('lightbox');
const lbImg = lb.querySelector('img');
document.querySelectorAll('.post-media img').forEach(img => {
  img.addEventListener('click', () => {
    lbImg.src = img.src;
    lb.classList.add('open');
  });
});
lb.addEventListener('click', () => lb.classList.remove('open'));

// Scroll-to-top
const btn = document.getElementById('scroll-top');
window.addEventListener('scroll', () => {
  btn.style.display = window.scrollY > 400 ? 'flex' : 'none';
});
btn.addEventListener('click', () => window.scrollTo({top:0, behavior:'smooth'}));
"""

def _render_media_tag(url, local_path, embed_base64, media_dl):
    ext = get_ext(url)
    if embed_base64 and media_dl:
        src = media_dl.get_base64_uri(url)
    else:
        src = None
    if not src:
        if local_path and os.path.exists(local_path):
            src = 'media/' + os.path.basename(local_path)
        else:
            src = url
    if ext in IMAGE_EXTS:
        return f'<img src="{src}" alt="image" loading="lazy">'
    elif ext in VIDEO_EXTS:
        return f'<video src="{src}" controls preload="metadata"></video>'
    elif ext in AUDIO_EXTS:
        return f'<audio src="{src}" controls></audio>'
    else:
        fname = os.path.basename(urlparse(url).path) or 'file'
        return f'<a class="media-link" href="{src}" download="{fname}">⬇ {fname}</a>'
def extract_posts_html(file_path, media_dl=None, embed_base64=False):
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        raw = f.read()
    soup = BeautifulSoup(raw, 'html.parser')
    
    # Extract base_url from og:url or canonical link before decomposing anything
    base_url = ""
    og = soup.find('meta', property='og:url')
    if og and og.get('content'):
        base_url = og['content']
    else:
        canonical = soup.find('link', rel='canonical')
        if canonical and canonical.get('href'):
            base_url = canonical['href']
            
    # Now decompose unwanted tags
    for tag in soup(['script','style','noscript']):
        tag.decompose()
        
    title_tag    = soup.find('title')
    thread_title = clean_text(title_tag.text) if title_tag else "Senza titolo"
    if " - " in thread_title:
        thread_title = thread_title.rsplit(" - ", 1)[0]
    elif " | " in thread_title:
        thread_title = thread_title.rsplit(" | ", 1)[0]
    thread_title = clean_text(thread_title)
    if not thread_title or thread_title.lower() == "untitled":
        h1_el = soup.find("h1")
        if h1_el:
            thread_title = clean_text(h1_el.get_text())

    post_containers = []
    
    # Try finding articles with numeric IDs or class names containing post/message but not reply/sidebar/widget
    for art in soup.find_all("article"):
        art_id = art.get("id")
        classes = art.get("class", [])
        if isinstance(classes, str):
            classes = [classes]
        
        # Numeric ID indicates a post
        if art_id and art_id.isdigit():
            post_containers.append(art)
            continue
            
        # Class check
        is_post_class = any("post" in cls.lower() or "message" in cls.lower() for cls in classes)
        is_sidebar_class = any("reply" in cls.lower() or "sidebar" in cls.lower() or "widget" in cls.lower() for cls in classes)
        if is_post_class and not is_sidebar_class:
            post_containers.append(art)
            continue
            
    # Fallback A: If no article post containers found, look for div elements with similar constraints
    if not post_containers:
        for div in soup.find_all("div"):
            div_id = div.get("id")
            classes = div.get("class", [])
            if isinstance(classes, str):
                classes = [classes]
                
            if div_id and div_id.isdigit():
                post_containers.append(div)
                continue
                
            is_post_class = any("post" in cls.lower() or "message-inner" in cls.lower() for cls in classes)
            is_sidebar_class = any("reply" in cls.lower() or "sidebar" in cls.lower() or "widget" in cls.lower() for cls in classes)
            if is_post_class and not is_sidebar_class:
                post_containers.append(div)
                continue

    # Fallback B: If still nothing, check original message_blocks
    if not post_containers:
        post_containers = soup.find_all('div', class_='message-userContent')
        
    # Fallback C: If still nothing, just grab all <article> elements to ensure we get SOMETHING
    if not post_containers:
        post_containers = soup.find_all('article')
        
    posts = []
    for block in post_containers:
        author = "Autore sconosciuto"
        date = "Data sconosciuta"
        date_obj = None
        
        # 1. Author Extraction
        member_links = block.find_all("a", href=lambda h: h and ("/members/" in h or "/member" in h))
        for a in member_links:
            if a.get("aria-label"):
                author = a["aria-label"].strip()
                break
            for attr in ["data-text", "data-username"]:
                val = a.get(attr)
                if val:
                    author = val.strip()
                    break
            if author and author != "Autore sconosciuto":
                break
            txt = a.get_text().strip()
            if txt:
                author = txt.split('\n')[0].strip()
                break
                
        if author == "Autore sconosciuto":
            author_el = block.find(class_=lambda c: c and any(kw in c.lower() for kw in ["authorname", "username", "author-name"]))
            if author_el:
                author = author_el.get_text().strip().split('\n')[0].strip()
                
        if author == "Autore sconosciuto":
            desc = block.get('data-lb-caption-desc', '') or block.get('data-caption-desc', '')
            if desc and '·' in desc:
                parts = desc.split('·')
                author = clean_text(parts[0])
                
        # 2. Date Extraction
        time_tags = block.find_all("time")
        correct_time_tag = None
        for t in time_tags:
            is_author_time = False
            for parent in t.parents:
                parent_class = parent.get("class", [])
                if isinstance(parent_class, str):
                    parent_class = [parent_class]
                if parent.name == "aside" or any("author" in cls.lower() for cls in parent_class):
                    is_author_time = True
                    break
            if not is_author_time:
                correct_time_tag = t
                break
                
        date_text = None
        if correct_time_tag:
            date_text = correct_time_tag.text.strip()
            dt_attr = correct_time_tag.get("datetime")
            if dt_attr:
                date_obj = parse_date(dt_attr)
            if not date_obj:
                date_obj = parse_date(date_text)
                
        if not date_text:
            date_el = block.find(class_=lambda c: c and any(kw in c.lower() for kw in ["post-date", "date", "time"]))
            if date_el:
                date_text = date_el.text.strip()
                date_obj = parse_date(date_text)
                
        if not date_text:
            desc = block.get('data-lb-caption-desc', '') or block.get('data-caption-desc', '')
            if desc and '·' in desc:
                parts = desc.split('·')
                if len(parts) >= 2:
                    date_text = clean_text(parts[1])
                    date_obj = parse_date(date_text)
                    
        if not date_text:
            date_text = "Data sconosciuta"
            
        # 3. Post Body Extraction
        body_div = None
        for kw in ["posttext", "fulltext", "bbcode", "bbwrapper", "message-body", "message-content"]:
            body_div = block.find(class_=lambda c: c and kw in c.lower())
            if body_div:
                break
                
        if not body_div:
            body_div = block.find(class_=lambda c: c and "content" in c.lower() and "user" not in c.lower())
            
        if not body_div:
            body_div = block.find_next('div', class_='bbWrapper')
            
        if not body_div:
            body_div = block
            
        body_text = clean_text(body_div.get_text()) if body_div else ""
        
        # 4. Media Extraction
        media_tags = []
        media_container = body_div if body_div else block
        
        for img in media_container.find_all('img', src=True):
            img_src = img['src']
            if any(x in img_src.lower() for x in ["/avatar", "/badge", "/reaction", "like.png"]):
                continue
            full_url = urljoin(base_url, img_src) if base_url else img_src
            local = media_dl.get_local_path(full_url) if media_dl else None
            if local or (media_dl and get_ext(full_url) in MEDIA_EXTS):
                media_tags.append(_render_media_tag(full_url, local, embed_base64, media_dl))
                
        for tag in media_container.find_all(['video','audio'], src=True):
            full_url = urljoin(base_url, tag['src']) if base_url else tag['src']
            local = media_dl.get_local_path(full_url) if media_dl else None
            media_tags.append(_render_media_tag(full_url, local, embed_base64, media_dl))
            
        posts.append({
            'date_obj': date_obj,
            'author':   author,
            'date':     date_text,
            'body':     body_text,
            'media':    media_tags,
        })
    posts.sort(key=lambda x: (x['date_obj'] is None, x['date_obj']))
    soup.decompose()
    return thread_title, posts
def build_html_output(all_threads, generated_at, forum_url=""):
    toc_items = ""
    for idx, (title, _posts) in enumerate(all_threads):
        anchor = f"thread-{idx}"
        toc_items += f'<li><a href="#{anchor}">{title}</a></li>\n'
    thread_blocks = ""
    for idx, (title, posts) in enumerate(all_threads):
        anchor    = f"thread-{idx}"
        post_html = ""
        for pi, post in enumerate(posts):
            is_op   = pi == 0
            cls     = "post original" if is_op else "post reply"
            badge   = '<span class="post-badge badge-original">Messaggio Originale</span>' if is_op \
                      else '<span class="post-badge badge-reply">Risposta</span>'
            media_html = ""
            if post['media']:
                media_html = '<div class="post-media">' + '\n'.join(post['media']) + '</div>'
            safe_body = post['body'].replace('&','&amp;').replace('<','&lt;').replace('>','&gt;')

            post_html += f"""
<div class="{cls}">
  <div class="post-meta">
    {badge}
    <span class="post-author">{post['author']}</span>
    <span class="post-date">{post['date']}</span>
  </div>
  <div class="post-body">{safe_body}</div>
  {media_html}
</div>"""
        thread_blocks += f"""
<div class="thread-block" id="{anchor}">
  <div class="thread-header">
    <span class="thread-sigil">○</span>
    <div class="thread-title">{title}</div>
    <span class="thread-count">{len(posts)} messagg{'io' if len(posts)==1 else 'i'}</span>
  </div>
  {post_html}
</div>"""
    forum_line = f'<br><span style="color:var(--teal);font-size:12px">{forum_url}</span>' if forum_url else ""
    return f"""<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<link rel="shortcut icon" href="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAgAAAAICAYAAADED76LAAAANElEQVR42mOAg+uv/qNgCEBIxn76/3/9DzAGs0Fi6JJwXSiKgASKJEIRkQoIWkHQkQS9CQBfIn0lgSVMDgAAAABJRU5ErkJggg==" />
<title>🌊 Mergohydrox — Archivio Forum 🌊</title>
<style type="text/css">{HTML_CSS}</style>
</head>
<body>
<header id="site-header">
  <div class="header-sigil">〰 ≈ ○ ≈ 〰</div>
  <h1 class="site-title">✦ Mrg FORUM ARCHIVE ✦</h1>
  <div class="site-sub">Conservazione fluida della conoscenza digitale &nbsp;·&nbsp; {generated_at}{forum_line}</div>
</header>
<div class="container">
  <nav id="toc">
    <h2>Indice Discussioni — {len(all_threads)} documenti</h2>
    <ul class="toc-list">
{toc_items}
    </ul>
  </nav>
{thread_blocks}

</div>
<div id="lightbox"><img src="" alt=""></div>
<button id="scroll-top" title="Torna in cima">↑</button>
<footer>
  🌊 &nbsp; Generato da <span>Mergohydrox</span> &nbsp;·&nbsp; {generated_at} &nbsp; 🌊
</footer>
<script type="text/javascript">{HTML_JS}</script>
</body>
</html>"""
def convert_html_folder(input_dir, output_file, log_callback=None, progress_callback=None,
                        stop_event=None, media_dl=None, embed_base64=False, forum_url=""):
    log = log_callback or print
    html_files = [os.path.join(input_dir, f)
                  for f in os.listdir(input_dir) if f.lower().endswith('.html')
                  and not f.startswith('_')]  # skip index files
    if not html_files:
        log("⚠ Nessun file HTML trovato nella cartella.")
        return 0
    log(f"📄 Trovati {len(html_files)} file HTML da convertire...")
    all_threads = []
    for i, filepath in enumerate(sorted(html_files), 1):
        if stop_event and stop_event.is_set():
            break
        try:
            title, posts = extract_posts_html(filepath, media_dl=media_dl, embed_base64=embed_base64)
            if posts:
                all_threads.append((title, posts))
        except Exception as e:
            log(f"  ⚠ Errore in {os.path.basename(filepath)}: {e}")
        if progress_callback:
            progress_callback(i, len(html_files))
        log(f"  💧 Analizzato {i}/{len(html_files)}: {os.path.basename(filepath)}")
    log("🎨 Composizione dell'archivio HTML...")
    generated_at = datetime.now().strftime("%B %d, %Y at %H:%M")
    html_out = build_html_output(all_threads, generated_at, forum_url)
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html_out)
    size_mb = os.path.getsize(output_file) / 1024 / 1024
    log(f"✅ Archivio HTML completato! {output_file}  ({size_mb:.1f} MB,  {len(all_threads)} discussioni)")
    return len(all_threads)


# ─────────────────────────────────────────────
#  MOTORE DI RIPRISTINO
# ─────────────────────────────────────────────

import csv
import os
import random
import string

def _html_to_bbcode(element):
    from bs4 import NavigableString, Tag

    if isinstance(element, NavigableString):
        return str(element)

    if not isinstance(element, Tag):
        return ""
    tag  = element.name.lower() if element.name else ""
    inner = "".join(_html_to_bbcode(c) for c in element.children)
    if tag in ("b", "strong"):
        return f"[B]{inner}[/B]"
    if tag in ("i", "em"):
        return f"[I]{inner}[/I]"
    if tag == "u":
        return f"[U]{inner}[/U]"
    if tag in ("s", "strike", "del"):
        return f"[S]{inner}[/S]"
    if tag == "a":
        href = element.get("href", "")
        return f"[URL={href}]{inner}[/URL]" if href else inner
    if tag == "img":
        src = element.get("src", "")
        if src.startswith("data:"):
            return "[IMG]<embedded>[/IMG]"
        return f"[IMG]{src}[/IMG]"
    if tag == "blockquote":
        return f"[QUOTE]{inner}[/QUOTE]"
    if tag in ("code", "pre"):
        return f"[CODE]{inner}[/CODE]"
    if tag in ("h1","h2","h3","h4","h5","h6"):
        size = {"h1":"6","h2":"5","h3":"4","h4":"3","h5":"2","h6":"1"}.get(tag,"4")
        return f"[SIZE={size}][B]{inner}[/B][/SIZE]\n"
    if tag == "br":
        return "\n"
    if tag == "p":
        return inner.strip() + "\n\n"
    if tag in ("ul", "ol"):
        return f"[LIST]\n{inner}[/LIST]\n"
    if tag == "li":
        return f"[*]{inner.strip()}\n"
    if tag in ("div", "span", "section", "article"):
        return inner
    if tag in ("script","style","head","meta","link","noscript"):
        return ""
    return inner
def _clean_bbcode(text):
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()
def _random_media_name(ext):
    hex_part = ''.join(random.choices(string.hexdigits[:16], k=14))
    digit_part = ''.join(random.choices(string.digits, k=8))
    name = hex_part + digit_part
    return name + ext
def _extract_b64_media(src_attr, recovered_dir, log):
    if not src_attr.startswith("data:"):
        return None, None
    try:
        header, b64data = src_attr.split(",", 1)
        mime = header.split(":")[1].split(";")[0].strip()
        ext  = mimetypes.guess_extension(mime) or ".bin"
        ext  = {".jpe": ".jpg", ".jpeg": ".jpg"}.get(ext, ext)
        fname = _random_media_name(ext)
        fpath = os.path.join(recovered_dir, fname)
        raw   = base64.b64decode(b64data + "==")
        with open(fpath, "wb") as f:
            f.write(raw)
        log(f"    💧 Materializzato {mime} → {fname}")
        return fpath, mime
    except Exception as e:
        log(f"    ⚠ Decodifica Base64 fallita: {e}")
        return None, None
def _parse_single_html(html_filepath, log, se):
    html_dir      = os.path.dirname(os.path.abspath(html_filepath))
    recovered_dir = os.path.join(html_dir, "recovered_media")
    os.makedirs(recovered_dir, exist_ok=True)

    log(f"🌊  Apertura del documento: {os.path.basename(html_filepath)}")
    try:
        with open(html_filepath, "r", encoding="utf-8", errors="ignore") as f:
            raw_html = f.read()
    except Exception as e:
        log(f"⚠  Impossibile aprire il file: {e}")
        return [], [], 0, recovered_dir
    all_threads = []
    csv_rows    = []
    total_posts = 0
    try:
        soup = BeautifulSoup(raw_html, "html.parser")
        mgr_threads = soup.find_all("div", class_="thread-block")
        is_mgr = len(mgr_threads) > 0
        if is_mgr:
            log(f"🌊  Formato archivio Mergohydrox rilevato — {len(mgr_threads)} blocco/i di discussione")
            for t_idx, t_block in enumerate(mgr_threads):
                if se.is_set(): break
                title_el     = t_block.find(class_="thread-title")
                thread_title = clean_text(title_el.get_text()) if title_el else f"Discussione {t_idx+1}"
                post_divs  = t_block.find_all("div", class_="post")
                posts_data = []
                for p_idx, post_div in enumerate(post_divs):
                    if se.is_set(): break
                    author_el = post_div.find(class_="post-author")
                    date_el   = post_div.find(class_="post-date")
                    body_el   = post_div.find(class_="post-body")
                    author   = clean_text(author_el.get_text()) if author_el else "Autore sconosciuto"
                    author   = author.lstrip("≈ ").strip()
                    date_str = clean_text(date_el.get_text()) if date_el else "Data sconosciuta"
                    date_str = date_str.lstrip("· ").strip()
                    bbcode_body = ""
                    media_refs  = []
                    if body_el:
                        media_container = post_div.find(class_="post-media")
                        if media_container:
                            for img_tag in media_container.find_all("img"):
                                src = img_tag.get("src","")
                                if src.startswith("data:"):
                                    fpath, mime = _extract_b64_media(src, recovered_dir, log)
                                    if fpath:
                                        rel = os.path.join("recovered_media", os.path.basename(fpath))
                                        media_refs.append({"type":"image","source":"base64","mime":mime,"local_path":rel})
                                elif src:
                                    media_refs.append({"type":"image","source":"url","url":src})
                            for vid in media_container.find_all(["video","source"]):
                                src = vid.get("src","")
                                if src.startswith("data:"):
                                    fpath, mime = _extract_b64_media(src, recovered_dir, log)
                                    if fpath:
                                        rel = os.path.join("recovered_media", os.path.basename(fpath))
                                        media_refs.append({"type":"video","source":"base64","mime":mime,"local_path":rel})
                                elif src:
                                    media_refs.append({"type":"video","source":"url","url":src})
                        raw_body = body_el.get_text()
                        bbcode_body = _clean_bbcode(raw_body)
                    is_op = "original" in (post_div.get("class") or [])
                    posts_data.append({
                        "index": p_idx, "author": author, "date": date_str,
                        "bbcode": bbcode_body, "media": media_refs, "is_original": is_op,
                    })
                    media_str = " | ".join(r.get("local_path") or r.get("url","") for r in media_refs)
                    csv_rows.append({
                        "thread_title": thread_title, "post_author": author,
                        "post_date": date_str, "post_content_bbcode": bbcode_body[:2000],
                        "media_references": media_str,
                    })
                if posts_data:
                    log(f"  💧 Discussione '{thread_title[:55]}' — {len(posts_data)} messaggi")
                all_threads.append({
                    "thread_title": thread_title,
                    "source_file":  os.path.basename(html_filepath),
                    "post_count":   len(posts_data),
                    "posts":        posts_data,
                })
                total_posts += len(posts_data)
        else:
            log("🌊  Formato vBulletin grezzo rilevato")
            # Extract base_url from og:url or canonical link before decomposing
            base_url = ""
            og = soup.find('meta', property='og:url')
            if og and og.get('content'):
                base_url = og['content']
            else:
                canonical = soup.find('link', rel='canonical')
                if canonical and canonical.get('href'):
                    base_url = canonical['href']
                    
            title_tag    = soup.find("title")
            thread_title = clean_text(title_tag.get_text()) if title_tag else "Documento senza titolo"
            if " - " in thread_title:
                thread_title = thread_title.rsplit(" - ", 1)[0]
            elif " | " in thread_title:
                thread_title = thread_title.rsplit(" | ", 1)[0]
            thread_title = clean_text(thread_title)
            if not thread_title or thread_title.lower() == "documento senza titolo":
                h1_el = soup.find("h1")
                if h1_el:
                    thread_title = clean_text(h1_el.get_text())

            post_containers = []
            
            # Try finding articles with numeric IDs or class names containing post/message but not reply/sidebar/widget
            for art in soup.find_all("article"):
                art_id = art.get("id")
                classes = art.get("class", [])
                if isinstance(classes, str):
                    classes = [classes]
                
                # Numeric ID indicates a post
                if art_id and art_id.isdigit():
                    post_containers.append(art)
                    continue
                    
                # Class check
                is_post_class = any("post" in cls.lower() or "message" in cls.lower() for cls in classes)
                is_sidebar_class = any("reply" in cls.lower() or "sidebar" in cls.lower() or "widget" in cls.lower() for cls in classes)
                if is_post_class and not is_sidebar_class:
                    post_containers.append(art)
                    continue
                    
            # Fallback A: If no article post containers found, look for div elements with similar constraints
            if not post_containers:
                for div in soup.find_all("div"):
                    div_id = div.get("id")
                    classes = div.get("class", [])
                    if isinstance(classes, str):
                        classes = [classes]
                        
                    if div_id and div_id.isdigit():
                        post_containers.append(div)
                        continue
                        
                    is_post_class = any("post" in cls.lower() or "message-inner" in cls.lower() for cls in classes)
                    is_sidebar_class = any("reply" in cls.lower() or "sidebar" in cls.lower() or "widget" in cls.lower() for cls in classes)
                    if is_post_class and not is_sidebar_class:
                        post_containers.append(div)
                        continue

            # Fallback B: If still nothing, check original message_blocks
            if not post_containers:
                post_containers = soup.find_all('div', class_='message-userContent')
                
            # Fallback C: If still nothing, just grab all <article> elements to ensure we get SOMETHING
            if not post_containers:
                post_containers = soup.find_all('article')
                
            log(f"🌊  Trovati {len(post_containers)} blocco/i di messaggi")
            posts_data = []
            
            for block_idx, block in enumerate(post_containers):
                if se.is_set(): break
                
                # 1. Author Extraction
                author = "Autore sconosciuto"
                member_links = block.find_all("a", href=lambda h: h and ("/members/" in h or "/member" in h))
                for a in member_links:
                    if a.get("aria-label"):
                        author = a["aria-label"].strip()
                        break
                    for attr in ["data-text", "data-username"]:
                        val = a.get(attr)
                        if val:
                            author = val.strip()
                            break
                    if author and author != "Autore sconosciuto":
                        break
                    txt = a.get_text().strip()
                    if txt:
                        author = txt.split('\n')[0].strip()
                        break
                        
                if author == "Autore sconosciuto":
                    author_el = block.find(class_=lambda c: c and any(kw in c.lower() for kw in ["authorname", "username", "author-name"]))
                    if author_el:
                        author = author_el.get_text().strip().split('\n')[0].strip()
                        
                if author == "Autore sconosciuto":
                    desc = block.get('data-lb-caption-desc', '') or block.get('data-caption-desc', '')
                    if desc and '·' in desc:
                        parts = desc.split('·')
                        author = clean_text(parts[0])
                        
                # 2. Date Extraction
                time_tags = block.find_all("time")
                correct_time_tag = None
                for t in time_tags:
                    is_author_time = False
                    for parent in t.parents:
                        parent_class = parent.get("class", [])
                        if isinstance(parent_class, str):
                            parent_class = [parent_class]
                        if parent.name == "aside" or any("author" in cls.lower() for cls in parent_class):
                            is_author_time = True
                            break
                    if not is_author_time:
                        correct_time_tag = t
                        break
                        
                date_str = "Data sconosciuta"
                if correct_time_tag:
                    date_str = correct_time_tag.text.strip()
                else:
                    date_el = block.find(class_=lambda c: c and any(kw in c.lower() for kw in ["post-date", "date", "time"]))
                    if date_el:
                        date_str = date_el.text.strip()
                    else:
                        desc = block.get('data-lb-caption-desc', '') or block.get('data-caption-desc', '')
                        if desc and '·' in desc:
                            parts = desc.split('·')
                            if len(parts) >= 2:
                                date_str = clean_text(parts[1])
                                
                # 3. Post Body / Content Extraction
                body_div = None
                for kw in ["posttext", "fulltext", "bbcode", "bbwrapper", "message-body", "message-content"]:
                    body_div = block.find(class_=lambda c: c and kw in c.lower())
                    if body_div:
                        break
                        
                if not body_div:
                    body_div = block.find(class_=lambda c: c and "content" in c.lower() and "user" not in c.lower())
                    
                if not body_div:
                    body_div = block.find_next('div', class_='bbWrapper')
                    
                if not body_div:
                    body_div = block
                    
                bbcode_body = ""
                media_refs = []
                
                if body_div:
                    # Media References Finder
                    for img_tag in body_div.find_all("img"):
                        src = img_tag.get("src", "")
                        if any(x in src.lower() for x in ["/avatar", "/badge", "/reaction", "like.png"]):
                            continue
                        if src.startswith("data:"):
                            fpath, mime = _extract_b64_media(src, recovered_dir, log)
                            if fpath:
                                rel = os.path.join("recovered_media", os.path.basename(fpath))
                                media_refs.append({"type": "image", "source": "base64", "mime": mime, "local_path": rel})
                                img_tag["src"] = rel
                        elif src:
                            media_refs.append({"type": "image", "source": "url", "url": src})
                            
                    for vid_tag in body_div.find_all(["video", "source"]):
                        src = vid_tag.get("src", "")
                        if src.startswith("data:"):
                            fpath, mime = _extract_b64_media(src, recovered_dir, log)
                            if fpath:
                                rel = os.path.join("recovered_media", os.path.basename(fpath))
                                media_refs.append({"type": "video", "source": "base64", "mime": mime, "local_path": rel})
                                vid_tag["src"] = rel
                        elif src:
                            media_refs.append({"type": "video", "source": "url", "url": src})
                            
                    for a_tag in body_div.find_all("a", href=True):
                        href = a_tag["href"]
                        if get_ext(href) in MEDIA_EXTS and not href.startswith("data:"):
                            media_refs.append({"type": "file", "source": "url", "url": href})
                            
                    try:
                        bbcode_body = _clean_bbcode(_html_to_bbcode(body_div))
                    except Exception as e:
                        log(f"    ⚠ Errore BBCode: {e}")
                        bbcode_body = clean_text(body_div.get_text())
                        
                posts_data.append({
                    "index": block_idx, "author": author, "date": date_str,
                    "bbcode": bbcode_body, "media": media_refs, "is_original": block_idx == 0,
                })
                
                media_str = " | ".join(r.get("local_path") or r.get("url", "") for r in media_refs)
                csv_rows.append({
                    "thread_title": thread_title, "post_author": author,
                    "post_date": date_str, "post_content_bbcode": bbcode_body[:2000],
                    "media_references": media_str,
                })
            all_threads.append({
                "thread_title": thread_title,
                "source_file":  os.path.basename(html_filepath),
                "post_count":   len(posts_data),
                "posts":        posts_data,
            })
            total_posts += len(posts_data)
            log(f"  💧 Estratti {total_posts} messaggi da '{thread_title[:55]}'")
        soup.decompose()
    except Exception as e:
        log(f"⚠  Errore di analisi: {e}")
    return all_threads, csv_rows, total_posts, recovered_dir
def restoration_write_json(all_threads, total_posts, out_path, log):
    log("🌊  Scrittura del codice JSON...")
    try:
        payload = {
            "generated_at":  datetime.now().isoformat(),
            "total_threads": len(all_threads),
            "total_posts":   total_posts,
            "threads":       all_threads,
        }
        with open(out_path, "w", encoding="utf-8") as jf:
            json.dump(payload, jf, indent=2, ensure_ascii=False)
        size_kb = os.path.getsize(out_path) / 1024
        log(f"  ✅ File JSON completato: {os.path.basename(out_path)}  ({size_kb:.1f} KB)")
        return out_path
    except Exception as e:
        log(f"  ⚠ Scrittura JSON fallita: {e}")
        return None
def restoration_write_csv(csv_rows, out_path, log):
    log("🌊  Scrittura della tabella CSV...")
    try:
        fieldnames = ["thread_title","post_author","post_date","post_content_bbcode","media_references"]
        with open(out_path, "w", encoding="utf-8", newline="") as cf:
            writer = csv.DictWriter(cf, fieldnames=fieldnames, quoting=csv.QUOTE_ALL)
            writer.writeheader()
            writer.writerows(csv_rows)
        size_kb = os.path.getsize(out_path) / 1024
        log(f"  ✅ File CSV completato: {os.path.basename(out_path)}  ({size_kb:.1f} KB)")
        return out_path
    except Exception as e:
        log(f"  ⚠ Scrittura CSV fallita: {e}")
        return None


# ─────────────────────────────────────────────
#  MOTORE DI MIRRORING SITO WEB  (🌊)
# ─────────────────────────────────────────────

class MirrorCrawler:
    def __init__(self, base_url, output_dir="mirror",
                 max_workers=8, delay=0.5,
                 log_callback=None, stop_event=None,
                 progress_callback=None):
        self.base_url          = base_url.rstrip("/")
        self.base_domain       = urlparse(base_url).netloc
        self.output_dir        = output_dir
        self.max_workers       = max_workers
        self.delay             = delay
        self.log               = log_callback or print
        self._stop             = stop_event or threading.Event()
        self._progress_cb      = progress_callback
        self.visited           = set()
        self.visited_lock      = threading.Lock()
        self.queue             = Queue()
        self._downloaded       = 0
        self._count_lock       = threading.Lock()
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
    def _normalize(self, url):
        url, _ = urldefrag(url)
        return url.rstrip("/")
    def _url_to_path(self, url):
        parsed = urlparse(url)
        path   = parsed.path or "/"
        if path == "" or path.endswith("/"):
            path += "index.html"
        elif "." not in os.path.basename(path):
            path = path.rstrip("/") + "/index.html"
        elif path.lower().endswith(".php"):
            path = path + ".html"
        return os.path.join(self.output_dir, parsed.netloc.replace(":", "_") + path)

    def _save(self, path, content):
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as f:
                f.write(content)
        except Exception as e:
            self.log(f"  ⚠ Errore di salvataggio ({os.path.basename(path)}): {e}")
    def _worker(self):
        while not self._stop.is_set():
            try:
                url = self.queue.get(timeout=2)
            except Exception:
                if self._stop.is_set():
                    break
                continue
            if url is None:
                self.queue.task_done()
                break
            url = self._normalize(url)
            with self.visited_lock:
                if url in self.visited:
                    self.queue.task_done()
                    continue
                self.visited.add(url)
            try:
                resp = self.session.get(url, timeout=12, stream=False)
                time.sleep(self.delay)
            except Exception as e:
                self.log(f"  ⚠ Errore di scaricamento: {url}  ({e})")
                self.queue.task_done()
                continue
            if resp.status_code != 200:
                self.log(f"  ⚠ HTTP {resp.status_code}: {url}")
                self.queue.task_done()
                continue
            ctype     = resp.headers.get("Content-Type", "")
            local_out = self._url_to_path(url)
            if "text/html" in ctype:
                try:
                    soup = BeautifulSoup(resp.text, "html.parser")
                    for tag in soup.find_all(["a", "link", "script", "img",
                                              "video", "audio", "source"]):
                        attr = "href" if tag.name in ("a", "link") else "src"
                        link = tag.get(attr)
                        if not link or link.startswith(("mailto:", "tel:", "javascript:", "#", "data:")):
                            continue
                        absolute = self._normalize(urljoin(url, link))
                        if urlparse(absolute).netloc != self.base_domain:
                            continue
                        child_path = self._url_to_path(absolute)
                        try:
                            rel = os.path.relpath(child_path,
                                                  os.path.dirname(self._url_to_path(url)))
                            tag[attr] = rel.replace("\\", "/")
                        except ValueError:
                            pass
                        self.queue.put(absolute)
                    self._save(local_out, soup.encode())
                except Exception as e:
                    self.log(f"  ⚠ Errore di analisi HTML: {e}")
                    self._save(local_out, resp.content)
            else:
                self._save(local_out, resp.content)
            with self._count_lock:
                self._downloaded += 1
                n = self._downloaded
            self.log(f"  💧 [{n}] {url}")
            if self._progress_cb:
                self._progress_cb(n)
            self.queue.task_done()
    def run(self):
        self.log(f"🌐 Avvio del mirroring di: {self.base_url}")
        self.log(f"📁 Cartella di destinazione: {self.output_dir}")
        os.makedirs(self.output_dir, exist_ok=True)
        self.queue.put(self.base_url)
        threads = []
        for _ in range(self.max_workers):
            t = threading.Thread(target=self._worker, daemon=True)
            t.start()
            threads.append(t)
        while not self._stop.is_set():
            if self.queue.empty() and self.queue.unfinished_tasks == 0:
                break
            time.sleep(0.4)
        if self._stop.is_set():
            self.log("⏹  Interruzione richiesta — svuotamento della coda...")
            with self.queue.mutex:
                self.queue.queue.clear()
                self.queue.all_tasks_done.notify_all()
                self.queue.unfinished_tasks = 0
        for _ in threads:
            self.queue.put(None)
        for t in threads:
            t.join(timeout=6)
        n = self._downloaded
        self.log(f"🏆 Mirroring completato — {n} file salvati in: {self.output_dir}")
        return n


# ─────────────────────────────────────────────
#  ANIMATORE BOLLE
# ─────────────────────────────────────────────

class BubbleAnimator:
    def __init__(self, canvas, width, height):
        import random
        self.canvas   = canvas
        self.width    = width
        self.height   = height
        self.bubbles  = []
        self._running = True
        for _ in range(28):
            x      = random.randint(0, width)
            y      = random.randint(0, height)
            symbol = random.choice(RUNE_SYMBOLS)
            color  = random.choice([BORDER_GLOW, ACCENT_PURP, "#0a3a4a", "#0e2e3a"])
            size   = random.randint(13, 28)
            speed  = random.uniform(0.25, 0.9)
            item   = canvas.create_text(x, y, text=symbol, fill=color, font=("Segoe UI", size))
            self.bubbles.append({'item': item, 'dy': random.choice([-1,1]) * speed})
        self._animate()
    def resize(self, new_width, new_height):
        import random
        self.width  = new_width
        self.height = new_height
        for bubble in self.bubbles:
            coords = self.canvas.coords(bubble['item'])
            if coords and (coords[0] < 0 or coords[0] > new_width):
                self.canvas.coords(bubble['item'],
                    random.randint(0, new_width), coords[1])
    def _animate(self):
        if not self._running: return
        for bubble in self.bubbles:
            self.canvas.move(bubble['item'], 0, bubble['dy'])
            coords = self.canvas.coords(bubble['item'])
            if coords:
                y = coords[1]
                if y < -30 or y > self.height + 30:
                    bubble['dy'] = -bubble['dy']
        self.canvas.after(55, self._animate)
    def stop(self):
        self._running = False


# ═════════════════════════════════════════════
#  MOTORE DI FUSIONE SITO STATICO
#  Unisce un sito statico scaricato (centinaia di pagine .html/.php.html +
#  immagini, audio, pdf, css, js) in UN UNICO file HTML autonomo: ogni
#  risorsa incorporata come Base64, link interni riscritti come rotte hash SPA,
#  barra laterale per categorie, ricerca lato client, tema acquatico.
# ═════════════════════════════════════════════

mimetypes.add_type("image/webp", ".webp")
mimetypes.add_type("image/x-icon", ".ico")
mimetypes.add_type("audio/mpeg", ".mp3")

SKIP_PAGES = {"search.php.html", "search_ai.php.html"}

# ─────────────────────────────────────────────
#  REGOLE DI CATEGORIZZAZIONE (raggruppamento barra laterale)
#  Le categorie sono estratte dinamicamente dagli attributi data-prof-section di index.html
# ─────────────────────────────────────────────

def _extract_categories_from_index(src_folder: Path) -> dict:
    """Extract category mappings from index.html data-prof-section attributes."""
    index_path = src_folder / "index.html"
    categories = {}
    if not index_path.is_file():
        return categories
    try:
        raw = index_path.read_text(encoding="utf-8", errors="replace")
        soup = BeautifulSoup(raw, "html.parser")
        for article in soup.find_all("article", attrs={"data-prof-section": True}):
            section_key = article["data-prof-section"]
            title_el = article.find(class_="title-text")
            if title_el:
                title_text = clean_text(title_el.get_text())
                if title_text:
                    categories[section_key] = title_text
    except Exception:
        pass
    return categories

# Global cache for categories (populated on first use)
_CATEGORY_CACHE = None

def _get_categories(src_folder: Path) -> dict:
    """Get categories, using cache if available."""
    global _CATEGORY_CACHE
    if _CATEGORY_CACHE is None:
        _CATEGORY_CACHE = _extract_categories_from_index(src_folder)
    return _CATEGORY_CACHE

def categorize(page: dict, src_folder: Path = None) -> str:
    """Determine the category label for a page dynamically."""
    key = page["key"]
    filename = key.split("/")[-1]
    
    # Get dynamic categories from index.html
    categories = _get_categories(src_folder) if src_folder else {}
    
    # Check if filename matches any category key
    filename_base = filename.replace(".php.html", "").replace(".html", "").replace(".php", "")
    if filename_base in categories:
        return categories[filename_base]
    
    # Check folder-based categorization
    if "/" in key:
        folder = key.split("/")[0]
        folder_base = folder.replace(".php.html", "").replace(".html", "").replace(".php", "")
        if folder_base in categories:
            return categories[folder_base]
        # Fallback: use folder name as category
        return folder.replace("_", " ").title()
    
    # Check breadcrumb
    bc = [b.lstrip("./") for b in page.get("breadcrumb", [])]
    bc = [b for b in bc if b not in ("home", "title", "")]
    if bc:
        first = bc[0]
        if first in categories:
            return categories[first]
        return first.replace("_", " ").title()
    
    return "Altri Scritti"


def esc(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;")
             .replace(">", "&gt;").replace('"', "&quot;"))


# ─────────────────────────────────────────────
#  MOTORE PRINCIPALE
# ─────────────────────────────────────────────

class StaticSiteFusionEngine:
    """
    Usage:
        engine = StaticSiteFusionEngine(
            src_folder="path/to/downloaded/site",
            out_file="path/to/OUTPUT.html",
            log_callback=lambda msg: print(msg),
            stop_event=threading.Event(),
        )
        engine.run()
    """

    def __init__(self, src_folder, out_file, log_callback=None, stop_event=None):
        self.src = Path(src_folder).resolve()
        self.out_file = Path(out_file).resolve()
        self.log = log_callback or print
        self._stop_event = stop_event
        self.asset_cache = {}
        self.asset_stats = {"count": 0, "bytes_in": 0, "bytes_out": 0, "missing": []}

    def _stopped(self):
        return self._stop_event is not None and self._stop_event.is_set()

    # ---- asset embedding ----

    def _to_data_uri(self, abs_path: Path):
        key = str(abs_path.resolve())
        if key in self.asset_cache:
            return self.asset_cache[key]
        if not abs_path.is_file():
            self.asset_stats["missing"].append(str(abs_path))
            return None
        mime, _ = mimetypes.guess_type(str(abs_path))
        if mime is None:
            mime = "application/octet-stream"
        raw = abs_path.read_bytes()
        b64 = base64.b64encode(raw).decode("ascii")
        uri = f"data:{mime};base64,{b64}"
        self.asset_cache[key] = uri
        self.asset_stats["count"] += 1
        self.asset_stats["bytes_in"] += len(raw)
        self.asset_stats["bytes_out"] += len(uri)
        return uri

    def _resolve_ref(self, ref: str, page_dir: Path):
        if ref.startswith(("http://", "https://", "mailto:", "#", "data:", "javascript:")):
            return None
        ref = ref.split("#")[0].split("?")[0]
        if not ref:
            return None
        if ref.startswith("/"):
            candidate = self.src / ref.lstrip("/")
        else:
            candidate = (page_dir / ref)
        try:
            candidate = candidate.resolve()
        except Exception:
            return None
        try:
            candidate.relative_to(self.src.resolve())
        except ValueError:
            return None
        return candidate

    def _embed_assets_in_soup(self, soup, page_dir: Path):
        tag_attrs = [
            ("img", "src"), ("source", "src"), ("audio", "src"),
            ("video", "src"), ("link", "href"), ("script", "src"),
        ]
        for tag_name, attr in tag_attrs:
            for tag in soup.find_all(tag_name):
                ref = tag.get(attr)
                if not ref:
                    continue
                if tag_name == "link" and tag.get("rel") not in (None, ["stylesheet"], ["icon"]):
                    continue
                abs_path = self._resolve_ref(ref, page_dir)
                if abs_path is None:
                    continue
                uri = self._to_data_uri(abs_path)
                if uri:
                    tag[attr] = uri

        embeddable_ext = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".pdf", ".mp3", ".ico"}
        for a in soup.find_all("a", href=True):
            ref = a["href"]
            ext = os.path.splitext(ref.split("#")[0].split("?")[0])[1].lower()
            if ext in embeddable_ext:
                abs_path = self._resolve_ref(ref, page_dir)
                if abs_path is not None:
                    uri = self._to_data_uri(abs_path)
                    if uri:
                        a["href"] = uri
                        a["download"] = os.path.basename(ref)

    def _path_to_key(self, abs_path: Path) -> str:
        rel = abs_path.resolve().relative_to(self.src.resolve())
        key = str(rel).replace("\\", "/")
        key = re.sub(r"\.php\.html$", "", key, flags=re.IGNORECASE)
        key = re.sub(r"\.php$", "", key, flags=re.IGNORECASE)
        key = re.sub(r"[^a-zA-Z0-9/_\-]", "_", key)
        return key

    def _rewrite_internal_page_links(self, soup, key_index: dict, page_dir: Path):
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href.startswith(("http://", "https://", "mailto:", "#", "javascript:")):
                continue
            clean = href.split("#")[0].split("?")[0]
            if not clean.endswith((".php.html", ".php", ".html")):
                continue
            abs_path = self._resolve_ref(clean, page_dir)
            if abs_path is None:
                continue
            target_key = self._path_to_key(abs_path)
            if target_key in key_index:
                a["href"] = f"#page/{target_key}"
                a["data-internal-link"] = "1"
                if a.get("target"):
                    del a["target"]

    def _collect_pages(self):
        pages = (sorted(self.src.glob("*.php.html")) + sorted(self.src.glob("*/*.php.html")) +
                 sorted(self.src.glob("*.html")) + sorted(self.src.glob("*/*.html")))
        # de-dup while preserving order (in case both patterns matched the same file)
        seen = set()
        unique = []
        for p in pages:
            rp = str(p.resolve())
            if rp not in seen:
                seen.add(rp)
                unique.append(p)
        pages = [p for p in unique if p.name not in SKIP_PAGES]
        return pages

    # ---- parsing ----

    def parse_all_pages(self):
        if not self.src.is_dir():
            raise FileNotFoundError(f"Cartella sorgente non trovata: {self.src}")

        self.log(f"🌊  Cartella sorgente: {self.src}")
        self.log("📄  Scansione delle pagine sorgente...")
        pages = self._collect_pages()
        self.log(f"💧  Trovate {len(pages)} pagine")

        key_index = {}
        for p in pages:
            key_index[self._path_to_key(p)] = p

        parsed_pages = []
        errors = []

        for i, p in enumerate(pages, 1):
            if self._stopped():
                self.log("⏹  Interrotto dall'utente durante l'analisi.")
                break
            rel = p.relative_to(self.src)
            try:
                raw = p.read_text(encoding="utf-8", errors="replace")
                soup = BeautifulSoup(raw, "lxml")
            except Exception as e:
                errors.append((str(rel), str(e)))
                continue

            title_tag = soup.find("title")
            title = title_tag.text.strip() if title_tag else rel.stem

            content = soup.select_one("div.content")
            if content is None:
                content = soup.find("body")
            if content is None:
                errors.append((str(rel), "no content/body found"))
                continue

            h1 = content.find("h1")
            h1_text = h1.get_text(strip=True) if h1 else title

            bc = soup.select_one("nav.breadcrumbs")
            bc_path = []
            if bc and bc.get("data-path"):
                bc_path = [s.strip() for s in bc["data-path"].split(",")]

            page_dir = p.parent

            self._embed_assets_in_soup(content, page_dir)

            key = self._path_to_key(p)
            self._rewrite_internal_page_links(content, key_index, page_dir)

            for bad in content.select("form, .search-form, #ai-widget-btn, #ai-widget-panel, script"):
                bad.decompose()

            parsed_pages.append({
                "key": key,
                "title": title,
                "h1": h1_text,
                "breadcrumb": bc_path,
                "content_html": content.decode_contents(),
                "rel_path": str(rel),
            })

            if i % 50 == 0 or i == len(pages):
                self.log(f"   → elaborate {i}/{len(pages)}  (risorse incorporate finora: {self.asset_stats['count']})")

        self.log(f"✅  Analisi completata: {len(parsed_pages)} pagine ok, {len(errors)} errori.")
        if errors:
            self.log(f"⚠  {len(errors)} pagina/e con problemi (mostrate fino a 5): {errors[:5]}")
        self.log(f"🖼  Risorse incorporate: {self.asset_stats['count']}  "
                  f"({round(self.asset_stats['bytes_in']/1e6,1)} MB raw → "
                  f"{round(self.asset_stats['bytes_out']/1e6,1)} MB as base64)")
        if self.asset_stats["missing"]:
            self.log(f"⚠  {len(self.asset_stats['missing'])} risorsa/e referenziate ma non trovate su disco "
                      f"(probabilmente link già interrotti nel sito sorgente).")

        return parsed_pages

    # ---- rendering ----

    def _build_nav_tree(self, pages):
        cats = defaultdict(list)
        for p in pages:
            cats[categorize(p, self.src)].append(p)
        for cat in cats:
            cats[cat].sort(key=lambda p: p["h1"] or p["title"])
        return dict(sorted(cats.items(), key=lambda kv: (-len(kv[1]), kv[0])))

    def render_html(self, pages):
        if self._stopped():
            self.log("⏹  Interrotto dall'utente prima della generazione.")
            return None

        nav_tree = self._build_nav_tree(pages)
        self.log(f"🗂  Costruite {len(nav_tree)} categorie")

        search_index = []
        for p in pages:
            plain = re.sub(r"<[^>]+>", " ", p["content_html"])
            plain = re.sub(r"\s+", " ", plain).strip()
            search_index.append({"key": p["key"], "title": p["h1"] or p["title"], "snippet": plain[:220]})

        sections_html = []
        for p in pages:
            cat = categorize(p, self.src)
            sections_html.append(
                f'<section class="prof-page" id="page-{esc(p["key"])}" '
                f'data-key="{esc(p["key"])}" data-cat="{esc(cat)}" hidden>'
                f'<div class="prof-page-inner">'
                f'<div class="prof-page-crumb"><a href="#" class="prof-crumb-home">Archivio</a> '
                f'<span class="sep">&rsaquo;</span> '
                f'<a href="#cat/{esc(cat)}" class="prof-crumb-cat">{esc(cat)}</a></div>'
                f'<article>{p["content_html"]}</article>'
                f'</div></section>'
            )
        sections_joined = "\n".join(sections_html)

        nav_html_parts = []
        for cat, plist in nav_tree.items():
            items = "".join(
                f'<li><a href="#page/{esc(p["key"])}" data-key="{esc(p["key"])}" '
                f'class="prof-nav-link">{esc(p["h1"] or p["title"])}</a></li>'
                for p in plist
            )
            nav_html_parts.append(
                f'<div class="prof-nav-group" data-cat="{esc(cat)}">'
                f'<button class="prof-nav-cat-btn" type="button">'
                f'<span class="prof-nav-cat-icon">&#9760;</span>'
                f'<span class="prof-nav-cat-label">{esc(cat)}</span>'
                f'<span class="prof-nav-count">{len(plist)}</span>'
                f'<span class="prof-nav-caret">&#9662;</span>'
                f'</button>'
                f'<ul class="prof-nav-list">{items}</ul>'
                f'</div>'
            )
        nav_html = "\n".join(nav_html_parts)

        html = HTML_TEMPLATE.format(
            total_pages=len(pages),
            total_cats=len(nav_tree),
            nav_html=nav_html,
            sections_html=sections_joined,
            search_index_json=json.dumps(search_index, ensure_ascii=False),
        )

        self.out_file.parent.mkdir(parents=True, exist_ok=True)
        self.out_file.write_text(html, encoding="utf-8")
        size_mb = self.out_file.stat().st_size / 1e6
        self.log(f"💾  Scritto: {self.out_file}  ({size_mb:.1f} MB)")
        return self.out_file

    def run(self):
        """Pipeline completa: analisi + generazione. Restituisce il percorso di output, o None se interrotto/fallito."""
        pages = self.parse_all_pages()
        if not pages or self._stopped():
            return None
        return self.render_html(pages)


# ─────────────────────────────────────────────
#  HTML TEMPLATE (theme, sidebar, search, routing)
# ─────────────────────────────────────────────
HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="shortcut icon" href="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAABIElEQVR42t3SsWpUQRTH4e9M7t7VmFikENL6BtY2NiJYWWgdSGXjY/gEYmEl1qJlLCwsrHwUbUJQYlh2798plgVhBSGp8oPDxzBwphmXrW5/CAC8mF/YnS8YftM1dsfufG2fc7wCaADLWw4bY4uT8Ez16Va3uulO/a4mYy0cAgwLgKXj8CnlXvFegISgwk6/U76Mk2O8hOECDuztnpul3NHcT6hGV2tU0JjirvgRZje/28OvAdrKUTUfKz4nZgqhioS/zuVJ4+HyhiO8HqB4uprsD/FWEVSBjdYGE4934tFmAR5Un81LrBJv8BMS++I5WkEoQLO9M+UbTqfJaTVfcWZLg+0diHdQhfhnzX91rRcMIE6KEQJb/kCtlbUsXEV/AJ8jZX4xOVC9AAAAAElFTkSuQmCC" />
<title>Home — Grande Archivio</title>
<style type="text/css">
:root {{
  --ocean-deep: #0a1a2f;
  --ocean-mid: #0f2b4a;
  --ocean-light: #1e4a6b;
  --wave: #2a7d9e;
  --wave-bright: #4ecdc4;
  --wave-glow: #67e8d8;
  --foam: #e0f2f7;
  --foam-dim: #a8d4e0;
  --coral: #ff6b6b;
  --text: #e0f2f7;
  --text-dim: #8ab4c8;
  --border: #1e4a6b;
  --radius: 12px;
  --shadow-glow: 0 0 28px rgba(78, 205, 196, 0.22);
}}
* {{ box-sizing: border-box; }}

html, body {{
  margin: 0;
  padding: 0;
  background: var(--ocean-deep);
  color: var(--text);
  font-family: 'Georgia', 'Times New Roman', serif;
  scroll-behavior: smooth;
}}

body {{
  min-height: 100vh;
  background:
    radial-gradient(ellipse at 15% -20%, rgba(78,205,196,0.12) 0%, transparent 60%),
    radial-gradient(ellipse at 85% 30%, rgba(103,232,216,0.09) 0%, transparent 55%),
    linear-gradient(180deg, #05101f 0%, #0a1a2f 45%, #0a1a2f 100%);
  background-attachment: fixed;
}}

/* ---------- Decorative ocean texture ---------- */
.prof-bg-glyphs {{
  position: fixed;
  inset: 0;
  pointer-events: none;
  opacity: 0.07;
  z-index: 0;
  background-image:
    repeating-linear-gradient(35deg, var(--wave) 0px, transparent 2px, transparent 55px),
    repeating-linear-gradient(-35deg, var(--wave-bright) 0px, transparent 2px, transparent 70px);
}}

.prof-sun-glow {{
  position: fixed;
  top: -180px;
  left: 50%;
  transform: translateX(-50%);
  width: 920px;
  height: 920px;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(103,232,216,0.18) 0%, rgba(78,205,196,0.04) 55%, transparent 70%);
  pointer-events: none;
  z-index: 0;
  animation: sunPulse 9s ease-in-out infinite;
}}

@keyframes sunPulse {{
  0%, 100% {{ opacity: 0.65; }}
  50% {{ opacity: 1; }}
}}

/* ---------- Top bar ---------- */
#prof-topbar {{
  position: sticky;
  top: 0;
  z-index: 50;
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 12px 18px;
  background: linear-gradient(180deg, rgba(10,26,47,0.96) 0%, rgba(10,26,47,0.91) 100%);
  border-bottom: 1px solid var(--border);
  backdrop-filter: blur(8px);
}}

#prof-menu-toggle {{
  background: transparent;
  border: 1px solid var(--wave);
  color: var(--wave-bright);
  width: 40px;
  height: 40px;
  border-radius: 8px;
  cursor: pointer;
  font-size: 18px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
  flex-shrink: 0;
}}

#prof-menu-toggle:hover {{ background: rgba(78,205,196,0.15); box-shadow: var(--shadow-glow); }}

.prof-brand {{
  display: flex;
  align-items: center;
  gap: 10px;
  cursor: pointer;
  user-select: none;
}}

.prof-brand-sigil {{
  width: 34px;
  height: 34px;
  flex-shrink: 0;
  color: var(--wave-bright);
}}

.prof-brand-text {{
  display: flex;
  flex-direction: column;
  line-height: 1.1;
}}

.prof-brand-title {{
  font-family: 'Cinzel', 'Georgia', serif;
  letter-spacing: 0.08em;
  font-size: 17px;
  color: var(--wave-glow);
  text-shadow: 0 0 18px rgba(103,232,216,0.4);
}}

.prof-brand-sub {{
  font-size: 10.5px;
  letter-spacing: 0.14em;
  color: var(--text-dim);
  text-transform: uppercase;
}}

#prof-search-wrap {{
  flex: 1;
  max-width: 520px;
  margin-left: auto;
  position: relative;
}}

#prof-search-input {{
  width: 100%;
  padding: 10px 14px 10px 38px;
  background: var(--ocean-mid);
  border: 1px solid var(--border);
  border-radius: 8px;
  color: var(--text);
  font-family: inherit;
  font-size: 14px;
  outline: none;
  transition: border-color 0.2s, box-shadow 0.2s;
}}

#prof-search-input:focus {{
  border-color: var(--wave);
  box-shadow: var(--shadow-glow);
}}

#prof-search-icon {{
  position: absolute;
  left: 12px;
  top: 50%;
  transform: translateY(-50%);
  color: var(--text-dim);
  font-size: 14px;
  pointer-events: none;
}}

#prof-search-results {{
  position: absolute;
  top: calc(100% + 6px);
  left: 0;
  right: 0;
  max-height: 420px;
  overflow-y: auto;
  background: var(--ocean-light);
  border: 1px solid var(--border);
  border-radius: 10px;
  box-shadow: 0 12px 40px rgba(0,0,0,0.7);
  display: none;
  z-index: 60;
}}

#prof-search-results.open {{ display: block; }}

.prof-search-result {{
  display: block;
  padding: 10px 14px;
  border-bottom: 1px solid var(--border);
  cursor: pointer;
  text-decoration: none;
  color: var(--text);
}}

.prof-search-result:last-child {{ border-bottom: none; }}

.prof-search-result:hover, .prof-search-result.active {{
  background: rgba(78,205,196,0.12);
}}

.prof-search-result-title {{
  color: var(--wave-bright);
  font-size: 14px;
  margin-bottom: 3px;
}}

.prof-search-result-snip {{
  font-size: 12px;
  color: var(--text-dim);
  line-height: 1.4;
}}

.prof-search-empty {{
  padding: 16px;
  color: var(--text-dim);
  font-size: 13px;
  text-align: center;
}}

.prof-stats-pill {{
  display: none;
}}

@media (min-width: 900px) {{
  .prof-stats-pill {{
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-size: 11px;
    letter-spacing: 0.06em;
    color: var(--text-dim);
    border: 1px solid var(--border);
    padding: 6px 10px;
    border-radius: 999px;
    white-space: nowrap;
    margin-left: 8px;
  }}
}}

/* ---------- Layout ---------- */
#prof-layout {{
  position: relative;
  z-index: 1;
  display: flex;
  min-height: calc(100vh - 62px);
}}

#prof-sidebar {{
  width: 300px;
  flex-shrink: 0;
  border-right: 1px solid var(--border);
  background: rgba(10,26,47,0.65);
  padding: 16px 10px 60px;
  overflow-y: auto;
  max-height: calc(100vh - 62px);
  position: sticky;
  top: 62px;
  transition: transform 0.25s ease, margin-left 0.25s ease;
}}

#prof-sidebar.collapsed {{
  margin-left: -300px;
}}

.prof-nav-group {{
  margin-bottom: 4px;
  border-radius: 8px;
  overflow: hidden;
}}

.prof-nav-cat-btn {{
  width: 100%;
  display: flex;
  align-items: center;
  gap: 8px;
  background: transparent;
  border: none;
  color: var(--text);
  padding: 9px 10px;
  cursor: pointer;
  font-family: inherit;
  font-size: 13.5px;
  text-align: left;
  border-radius: 7px;
  transition: background 0.15s;
}}

.prof-nav-cat-btn:hover {{ background: rgba(78,205,196,0.1); }}

.prof-nav-cat-icon {{ color: var(--wave); font-size: 13px; flex-shrink: 0; }}

.prof-nav-cat-label {{
  flex: 1;
  color: var(--foam);
  letter-spacing: 0.02em;
}}

.prof-nav-count {{
  font-size: 10.5px;
  color: var(--text-dim);
  background: var(--ocean-light);
  padding: 1px 7px;
  border-radius: 999px;
}}

.prof-nav-caret {{
  color: var(--text-dim);
  font-size: 10px;
  transition: transform 0.2s;
}}

.prof-nav-group.open .prof-nav-caret {{ transform: rotate(180deg); }}

.prof-nav-list {{
  list-style: none;
  margin: 0;
  padding: 2px 0 8px 26px;
  display: none;
  border-left: 1px solid var(--border);
  margin-left: 14px;
}}

.prof-nav-group.open .prof-nav-list {{ display: block; }}

.prof-nav-list li {{ margin: 0; }}

.prof-nav-link {{
  display: block;
  padding: 6px 10px;
  font-size: 12.8px;
  color: var(--text-dim);
  text-decoration: none;
  border-radius: 6px;
  line-height: 1.35;
  transition: color 0.15s, background 0.15s;
}}

.prof-nav-link:hover {{ color: var(--wave-bright); background: rgba(78,205,196,0.08); }}

.prof-nav-link.active {{
  color: var(--ocean-deep);
  background: linear-gradient(90deg, var(--wave), var(--wave-bright));
  font-weight: 600;
}}

/* ---------- Main content ---------- */
#prof-main {{
  flex: 1;
  min-width: 0;
  padding: 0;
  position: relative;
}}

#prof-home-view {{
  padding: 60px 40px 80px;
  max-width: 980px;
  margin: 0 auto;
}}

.prof-hero {{
  text-align: center;
  margin-bottom: 56px;
}}

.prof-hero-sigil {{
  width: 90px;
  height: 90px;
  margin: 0 auto 22px;
  color: var(--wave-bright);
  filter: drop-shadow(0 0 28px rgba(103,232,216,0.45));
  animation: sigilFloat 6.5s ease-in-out infinite;
}}

@keyframes sigilFloat {{
  0%, 100% {{ transform: translateY(0) rotate(0deg); }}
  50% {{ transform: translateY(-8px) rotate(-2deg); }}
}}

.prof-hero h1 {{
  font-family: 'Cinzel', 'Georgia', serif;
  font-size: clamp(28px, 5vw, 46px);
  letter-spacing: 0.05em;
  margin: 0 0 14px;
  background: linear-gradient(180deg, #e0f2f7 0%, var(--wave-bright) 100%);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
  text-shadow: 0 0 40px rgba(103,232,216,0.3);
}}

.prof-hero p {{
  color: var(--text-dim);
  font-size: 15.5px;
  max-width: 600px;
  margin: 0 auto;
  line-height: 1.7;
}}

.prof-hero-divider {{
  width: 220px;
  height: 1px;
  margin: 28px auto;
  background: linear-gradient(90deg, transparent, var(--wave), transparent);
  position: relative;
}}

.prof-hero-divider::after {{
  content: '⚓';
  position: absolute;
  left: 50%;
  top: 50%;
  transform: translate(-50%,-50%);
  background: var(--ocean-deep);
  padding: 0 12px;
  color: var(--wave-bright);
  font-size: 18px;
}}

.prof-cats-grid {{
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(230px, 1fr));
  gap: 14px;
}}

.prof-cat-card {{
  display: block;
  text-decoration: none;
  padding: 18px;
  border-radius: var(--radius);
  border: 1px solid var(--border);
  background: linear-gradient(180deg, rgba(30,74,107,0.75) 0%, rgba(15,43,74,0.8) 100%);
  transition: transform 0.2s, border-color 0.2s, box-shadow 0.2s;
  position: relative;
  overflow: hidden;
}}

.prof-cat-card::before {{
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(135deg, rgba(78,205,196,0.09), transparent 65%);
  opacity: 0;
  transition: opacity 0.2s;
}}

.prof-cat-card:hover {{
  transform: translateY(-4px);
  border-color: var(--wave);
  box-shadow: 0 12px 35px rgba(0,0,0,0.5), var(--shadow-glow);
}}

.prof-cat-card:hover::before {{ opacity: 1; }}

.prof-cat-card-title {{
  color: var(--wave-bright);
  font-size: 15px;
  font-weight: 600;
  margin-bottom: 6px;
  letter-spacing: 0.02em;
}}

.prof-cat-card-count {{
  color: var(--text-dim);
  font-size: 12px;
}}

/* ---------- Page view ---------- */
.prof-page {{
  padding: 40px 48px 100px;
  max-width: 880px;
  margin: 0 auto;
  animation: pageIn 0.35s ease;
}}

@keyframes pageIn {{
  from {{ opacity: 0; transform: translateY(8px); }}
  to {{ opacity: 1; transform: translateY(0); }}
}}

.prof-page[hidden] {{ display: none; }}

.prof-page-crumb {{
  font-size: 12px;
  color: var(--text-dim);
  margin-bottom: 26px;
  letter-spacing: 0.02em;
}}

.prof-page-crumb a {{
  color: var(--wave-bright);
  text-decoration: none;
}}

.prof-page-crumb a:hover {{ text-decoration: underline; }}

.prof-page-crumb .sep {{ margin: 0 6px; opacity: 0.5; }}

.prof-page article {{
  color: var(--text);
  line-height: 1.8;
  font-size: 16px;
}}

.prof-page article h1 {{
  font-family: 'Cinzel', 'Georgia', serif;
  color: var(--wave-glow);
  font-size: clamp(24px, 4vw, 32px);
  letter-spacing: 0.02em;
  margin: 0 0 26px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--border);
  text-shadow: 0 0 24px rgba(103,232,216,0.25);
}}

.prof-page article h2, .prof-page article h3 {{
  font-family: 'Cinzel', 'Georgia', serif;
  color: var(--wave-bright);
  margin: 34px 0 14px;
  letter-spacing: 0.01em;
}}

.prof-page article p {{ margin: 0 0 18px; }}

.prof-page article a {{
  color: var(--wave-glow);
  text-decoration: underline;
  text-decoration-color: rgba(103,232,216,0.4);
}}

.prof-page article a:hover {{ text-decoration-color: var(--wave-bright); }}

.prof-page article img {{
  max-width: 100%;
  height: auto;
  border-radius: 8px;
  border: 1px solid var(--border);
  margin: 10px 0;
}}

.prof-page article ul, .prof-page article ol {{ padding-left: 26px; margin: 0 0 18px; }}

.prof-page article li {{ margin: 6px 0; }}

.prof-page article blockquote {{
  border-left: 3px solid var(--wave);
  margin: 20px 0;
  padding: 4px 0 4px 18px;
  color: var(--foam);
  font-style: italic;
}}

.prof-page article table {{
  width: 100%;
  border-collapse: collapse;
  margin: 20px 0;
  font-size: 14px;
}}

.prof-page article th, .prof-page article td {{
  border: 1px solid var(--border);
  padding: 8px 10px;
  text-align: left;
}}

.prof-page article th {{ background: var(--ocean-light); color: var(--wave-bright); }}

.prof-page article audio {{
  width: 100%;
  max-width: 420px;
  margin: 10px 0;
  filter: hue-rotate(190deg) saturate(1.3);
}}

.prof-page article b, .prof-page article strong {{ color: var(--wave-bright); }}

.prof-page article .columns {{
  display: flex;
  gap: 24px;
  flex-wrap: wrap;
  align-items: flex-start;
  margin: 18px 0;
}}

.prof-page article .columns .image {{ flex: 0 0 auto; }}
.prof-page article .columns .text {{ flex: 1 1 260px; }}

.prof-page article .spacer-m {{ height: 20px; }}
.prof-page article .left-image {{ display: block; }}

.prof-page article hr {{ border: none; border-top: 1px solid var(--border); margin: 30px 0; }}

.prof-page article .further-read {{
  margin-top: 40px;
  padding-top: 20px;
  border-top: 1px dashed var(--border);
}}

.prof-page article .further-read a {{ font-size: 14px; }}

/* nav footer buttons */
.prof-page-nav-footer {{
  display: flex;
  justify-content: space-between;
  gap: 12px;
  margin-top: 50px;
  padding-top: 24px;
  border-top: 1px solid var(--border);
}}

.prof-page-nav-footer button {{
  background: var(--ocean-light);
  border: 1px solid var(--border);
  color: var(--text-dim);
  padding: 9px 16px;
  border-radius: 8px;
  cursor: pointer;
  font-family: inherit;
  font-size: 13px;
  transition: all 0.2s;
}}

.prof-page-nav-footer button:hover {{
  border-color: var(--wave);
  color: var(--wave-bright);
}}

/* ---------- Scrollbars ---------- */
::-webkit-scrollbar {{ width: 10px; height: 10px; }}
::-webkit-scrollbar-track {{ background: var(--ocean-mid); }}
::-webkit-scrollbar-thumb {{ background: var(--wave); border-radius: 6px; }}
::-webkit-scrollbar-thumb:hover {{ background: var(--wave-bright); }}

/* ---------- Back to top ---------- */
#prof-top-btn {{
  position: fixed;
  bottom: 24px;
  right: 24px;
  width: 44px;
  height: 44px;
  border-radius: 50%;
  background: var(--ocean-light);
  border: 1px solid var(--wave);
  color: var(--wave-bright);
  cursor: pointer;
  font-size: 18px;
  display: none;
  align-items: center;
  justify-content: center;
  box-shadow: 0 6px 24px rgba(0,0,0,0.6);
  z-index: 40;
  transition: transform 0.2s;
}}

#prof-top-btn.visible {{ display: flex; }}
#prof-top-btn:hover {{ transform: translateY(-3px); }}

/* ---------- Mobile ---------- */
@media (max-width: 860px) {{
  #prof-sidebar {{
    position: fixed;
    left: 0;
    top: 62px;
    bottom: 0;
    z-index: 45;
    max-height: none;
    width: 300px;
    background: #0a1f38;
    box-shadow: 12px 0 40px rgba(0,0,0,0.7);
  }}
  #prof-sidebar.collapsed {{ margin-left: -320px; }}
  #prof-sidebar:not(.collapsed) {{ margin-left: 0; }}
  .prof-page {{ padding: 28px 20px 80px; }}
  #prof-home-view {{ padding: 40px 18px 60px; }}
  #prof-search-wrap {{ max-width: none; }}
  .prof-brand-sub {{ display: none; }}
}}

/* ---------- Overlay ---------- */
#prof-overlay {{
  display: none;
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.55);
  z-index: 44;
}}

#prof-overlay.visible {{ display: block; }}
</style>
</head>
<body>

<div class="prof-bg-glyphs"></div>
<div class="prof-sun-glow"></div>

<header id="prof-topbar">
  <button id="prof-menu-toggle" title="Menu" aria-label="Apri/chiudi menu">&#9776;</button>
  <div class="prof-brand" id="prof-brand-home">
<svg class="prof-brand-sigil" viewBox="0 0 64 64" fill="none">
  <path d="M16 32C22 24 38 24 46 32C38 40 22 40 16 32Z" stroke="currentColor" stroke-width="2"/>
  <path d="M46 32L56 24V40L46 32Z" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/>
  <circle cx="24" cy="30" r="1.5" fill="currentColor"/>
  <path d="M30 32H38" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
</svg>
    <div class="prof-brand-text">
      <span class="prof-brand-title">GRANDE ARCHIVIO</span>
      <span class="prof-brand-sub">Fusione Sito Statico</span>
    </div>
  </div>
  <div id="prof-search-wrap">
    <span id="prof-search-icon">&#128269;</span>
    <input id="prof-search-input" type="search" placeholder="Cerca tra {total_pages} pagine dell'archivio..." autocomplete="off">
    <div id="prof-search-results"></div>
  </div>
  <span class="prof-stats-pill">{total_pages} pagine &middot; {total_cats} categorie &middot; offline</span>
</header>

<div id="prof-overlay"></div>

<div id="prof-layout">
  <nav id="prof-sidebar">
    {nav_html}
  </nav>

  <main id="prof-main">
    <div id="prof-home-view">
      <div class="prof-hero">
<svg class="prof-hero-sigil" viewBox="0 0 100 100" fill="none">
  <path d="M22 50C34 36 58 36 72 50C58 64 34 64 22 50Z" stroke="currentColor" stroke-width="2"/>
  <path d="M72 50L86 38V62L72 50Z" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/>
  <circle cx="36" cy="46" r="2" fill="currentColor"/>
  <path d="M44 50H58" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
  <path d="M50 20L50 10M62 24L70 16M38 24L30 16" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" opacity="0.7"/>
</svg>
        <h1>Grande Archivio</h1>
        <p>Un'unica pagina eterna che raccoglie l'intero corpus &mdash;
           testi, riflessioni, pensieri, filosofia e conoscenza &mdash;
           conservati offline, per sempre accessibili.</p>
        <div class="prof-hero-divider"></div>
      </div>
      <div class="prof-cats-grid" id="prof-cats-grid"></div>
    </div>

    {sections_html}
  </main>
</div>

<button id="prof-top-btn" title="Torna in cima">&#8593;</button>

<script type="text/javascript">
(function() {{
  "use strict";

  var SEARCH_INDEX = {search_index_json};

  var sidebar = document.getElementById('prof-sidebar');
  var overlay = document.getElementById('prof-overlay');
  var menuToggle = document.getElementById('prof-menu-toggle');
  var homeView = document.getElementById('prof-home-view');
  var mainEl = document.getElementById('prof-main');
  var allPages = Array.prototype.slice.call(document.querySelectorAll('.prof-page'));
  var pageByKey = {{}};
  allPages.forEach(function(el) {{ pageByKey[el.getAttribute('data-key')] = el; }});

  var navGroups = Array.prototype.slice.call(document.querySelectorAll('.prof-nav-group'));
  var navLinks = Array.prototype.slice.call(document.querySelectorAll('.prof-nav-link'));

  // ---------- category cards on home ----------
  var catsGrid = document.getElementById('prof-cats-grid');
  var catCounts = {{}};
  navGroups.forEach(function(g) {{
    var cat = g.getAttribute('data-cat');
    var count = g.querySelectorAll('.prof-nav-link').length;
    catCounts[cat] = count;
  }});
  Object.keys(catCounts).sort(function(a,b) {{ return catCounts[b]-catCounts[a]; }}).forEach(function(cat) {{
    var a = document.createElement('a');
    a.href = '#cat/' + encodeURIComponent(cat);
    a.className = 'prof-cat-card';
    a.innerHTML = '<div class="prof-cat-card-title">' + escapeHtml(cat) + '</div>' +
                  '<div class="prof-cat-card-count">' + catCounts[cat] + ' pages</div>';
    catsGrid.appendChild(a);
  }});

  function escapeHtml(s) {{
    var d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
  }}

  // ---------- sidebar toggle ----------
  function isMobile() {{ return window.innerWidth <= 860; }}
  function setSidebarCollapsed(collapsed) {{
    sidebar.classList.toggle('collapsed', collapsed);
    overlay.classList.toggle('visible', !collapsed && isMobile());
  }}
  // start collapsed on mobile
  setSidebarCollapsed(isMobile());

  menuToggle.addEventListener('click', function() {{
    setSidebarCollapsed(!sidebar.classList.contains('collapsed'));
  }});
  overlay.addEventListener('click', function() {{ setSidebarCollapsed(true); }});

  // ---------- category group expand/collapse ----------
  navGroups.forEach(function(g) {{
    var btn = g.querySelector('.prof-nav-cat-btn');
    btn.addEventListener('click', function() {{
      g.classList.toggle('open');
    }});
  }});

  // ---------- routing ----------
  function showHome() {{
    allPages.forEach(function(el) {{ el.hidden = true; }});
    homeView.style.display = '';
    navLinks.forEach(function(l) {{ l.classList.remove('active'); }});
    document.title = "Grande Archivio";
    mainEl.scrollTop = 0;
    window.scrollTo(0,0);
  }}

  function showCategory(cat) {{
    // Filters the home grid, or rather opens that group and shows its first page? 
    // For a clearer UX: we show the home layout but with that category highlighted/open in the sidebar
    allPages.forEach(function(el) {{ el.hidden = true; }});
    homeView.style.display = 'none';

    var container = document.createElement('div');
    container.id = 'prof-cat-view-tmp';
    container.className = 'prof-page';
    container.hidden = false;
    var group = document.querySelector('.prof-nav-group[data-cat="' + cssEscape(cat) + '"]');
    var links = group ? Array.prototype.slice.call(group.querySelectorAll('.prof-nav-link')) : [];
    var itemsHtml = links.map(function(l) {{
      return '<li><a href="' + l.getAttribute('href') + '" class="prof-search-result" style="border-radius:8px;margin-bottom:6px;display:block;">' +
             '<div class="prof-search-result-title">' + l.textContent + '</div></a></li>';
    }}).join('');
    container.innerHTML = '<div class="prof-page-inner">' +
      '<div class="prof-page-crumb"><a href="#" class="prof-crumb-home">Archivio</a> <span class="sep">&rsaquo;</span> ' + escapeHtml(cat) + '</div>' +
      '<article><h1>' + escapeHtml(cat) + '</h1><ul style="list-style:none;padding:0;">' + itemsHtml + '</ul></article>' +
      '</div>';

    var old = document.getElementById('prof-cat-view-tmp');
    if (old) old.remove();
    mainEl.appendChild(container);

    if (group) {{
      navGroups.forEach(function(g) {{ g.classList.remove('open'); }});
      group.classList.add('open');
    }}
    document.title = cat + " — Grande Archivio";
    window.scrollTo(0,0);
  }}

  function cssEscape(s) {{
    return s.replace(/["\\]/g, '\\$&');
  }}

  function showPage(key) {{
    var old = document.getElementById('prof-cat-view-tmp');
    if (old) old.remove();
    var el = pageByKey[key];
    if (!el) {{ showHome(); return; }}
    allPages.forEach(function(p) {{ p.hidden = (p !== el); }});
    homeView.style.display = 'none';

    navLinks.forEach(function(l) {{
      var active = l.getAttribute('data-key') === key;
      l.classList.toggle('active', active);
      if (active) {{
        var group = l.closest('.prof-nav-group');
        if (group) group.classList.add('open');
      }}
    }});

    var h1 = el.querySelector('h1');
    document.title = (h1 ? h1.textContent : key) + " — Grande Archivio";
    mainEl.scrollTop = 0;
    window.scrollTo(0,0);
    if (isMobile()) setSidebarCollapsed(true);
  }}

  function route() {{
    var hash = window.location.hash.replace(/^#/, '');
    if (!hash) {{ showHome(); return; }}
    var m = hash.match(/^page\/(.+)$/);
    if (m) {{ showPage(decodeURIComponent(m[1])); return; }}
    var m2 = hash.match(/^cat\/(.+)$/);
    if (m2) {{ showCategory(decodeURIComponent(m2[1])); return; }}
    showHome();
  }}

  window.addEventListener('hashchange', route);
  document.getElementById('prof-brand-home').addEventListener('click', function() {{
    window.location.hash = '';
  }});
  document.addEventListener('click', function(e) {{
    var crumbHome = e.target.closest('.prof-crumb-home');
    if (crumbHome) {{ e.preventDefault(); window.location.hash = ''; }}
  }});

  route();

  // ---------- search ----------
  var searchInput = document.getElementById('prof-search-input');
  var searchResults = document.getElementById('prof-search-results');
  var searchTimer = null;

  function runSearch(q) {{
    q = q.trim().toLowerCase();
    if (!q) {{ searchResults.classList.remove('open'); searchResults.innerHTML=''; return; }}
    var terms = q.split(/\s+/).filter(Boolean);
    var scored = [];
    for (var i=0; i<SEARCH_INDEX.length; i++) {{
      var item = SEARCH_INDEX[i];
      var hay = (item.title + ' ' + item.snippet).toLowerCase();
      var score = 0;
      var ok = true;
      for (var t=0; t<terms.length; t++) {{
        var idx = hay.indexOf(terms[t]);
        if (idx === -1) {{ ok = false; break; }}
        score += (item.title.toLowerCase().indexOf(terms[t]) !== -1) ? 10 : 1;
      }}
      if (ok) scored.push({{item: item, score: score}});
    }}
    scored.sort(function(a,b) {{ return b.score - a.score; }});
    scored = scored.slice(0, 25);

    if (scored.length === 0) {{
      searchResults.innerHTML = '<div class="prof-search-empty">No results found.</div>';
    }} else {{
      searchResults.innerHTML = scored.map(function(s) {{
        return '<a class="prof-search-result" href="#page/' + encodeURIComponent(s.item.key) + '">' +
          '<div class="prof-search-result-title">' + escapeHtml(s.item.title) + '</div>' +
          '<div class="prof-search-result-snip">' + escapeHtml(s.item.snippet) + '&hellip;</div>' +
          '</a>';
      }}).join('');
    }}
    searchResults.classList.add('open');
  }}

  searchInput.addEventListener('input', function() {{
    clearTimeout(searchTimer);
    var v = searchInput.value;
    searchTimer = setTimeout(function() {{ runSearch(v); }}, 120);
  }});
  searchInput.addEventListener('focus', function() {{
    if (searchInput.value.trim()) searchResults.classList.add('open');
  }});
  document.addEventListener('click', function(e) {{
    if (!e.target.closest('#prof-search-wrap')) {{
      searchResults.classList.remove('open');
    }}
  }});
  searchResults.addEventListener('click', function() {{
    searchInput.value = '';
    searchResults.classList.remove('open');
  }});

  // ---------- internal links inside article content ----------
  document.addEventListener('click', function(e) {{
    var a = e.target.closest('a[data-internal-link]');
    if (a) {{
      // href is already #page/... so default anchor behavior works;
      // just ensure scroll-to-top happens via hashchange handler
    }}
  }});

  // ---------- back to top ----------
  var topBtn = document.getElementById('prof-top-btn');
  window.addEventListener('scroll', function() {{
    topBtn.classList.toggle('visible', window.scrollY > 400);
  }});
  topBtn.addEventListener('click', function() {{
    window.scrollTo({{top:0, behavior:'smooth'}});
  }});

}})();
</script>
</body>
</html>
"""



# ═════════════════════════════════════════════
#  PDF UNIFIER ENGINE
#  Unisce ogni file PDF in una cartella in un unico PDF, con un segnalibro
#  outline entry per source file pointing to where it starts.
# ═════════════════════════════════════════════

class PdfUnifierEngine:
    """
    Usage:
        engine = PdfUnifierEngine(
            src_folder="path/with/pdfs",
            out_file="path/PDF_Unified.pdf",
            log_callback=lambda msg: print(msg),
            stop_event=threading.Event(),
        )
        engine.run()
    """

    def __init__(self, src_folder, out_file, log_callback=None, stop_event=None):
        self.src = Path(src_folder).resolve()
        self.out_file = Path(out_file).resolve()
        self.log = log_callback or print
        self._stop_event = stop_event

    def _stopped(self):
        return self._stop_event is not None and self._stop_event.is_set()

    def run(self):
        if not self.src.is_dir():
            raise FileNotFoundError(f"Cartella sorgente non trovata: {self.src}")

        pdfs = sorted(self.src.glob("*.pdf"))
        pdfs = [p for p in pdfs if p.resolve() != self.out_file.resolve()]

        if not pdfs:
            self.log("⚠  Nessun file PDF trovato in quella cartella.")
            return None

        self.log(f"📄  Trovati {len(pdfs)} file PDF in: {self.src}")

        writer = PdfWriter()
        page_count = 0
        sections = []

        for pdf in pdfs:
            if self._stopped():
                self.log("⏹  Interrotto dall'utente.")
                return None
            try:
                reader = PdfReader(str(pdf))
                num_pages = len(reader.pages)
                writer.append(str(pdf))
                sections.append({"name": pdf.stem, "page": page_count})
                page_count += num_pages
                self.log(f"   ⚕  Aggiunto: {pdf.name}  ({num_pages} pagine)")
            except Exception as e:
                self.log(f"   ⚠  Saltato {pdf.name}: {e}")

        if page_count == 0:
            self.log("⚠  Nessun file unito (lettura fallita per tutti i file).")
            return None

        self.log("🔖  Creazione dei segnalibri...")
        for section in sections:
            writer.add_outline_item(section["name"], section["page"])

        self.log("🗜  Compressione degli oggetti identici...")
        writer.compress_identical_objects()

        self.out_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.out_file, "wb") as f:
            writer.write(f)

        size_mb = self.out_file.stat().st_size / 1e6
        self.log(f"💾  Scritto: {self.out_file}  ({size_mb:.1f} MB)")
        self.log(f"✅  Pagine totali: {page_count}  |  Sezioni: {len(sections)}")
        return self.out_file



# ─────────────────────────────────────────────
#  MAIN GUI
# ─────────────────────────────────────────────

class Mergohydrox(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("🌊 Mergohydrox 🌊")
        self.geometry("1100x940")
        self.minsize(950, 800)
        self.configure(bg=BG_DEEP)
        self.resizable(True, True)
        self._stop_event       = threading.Event()
        self._backup_obj       = None
        self._mi_stop          = threading.Event()
        self._fu_stop          = threading.Event()
        self._pu_stop          = threading.Event()
        self._bubble_initialized = False
        self._title_ids        = []
        self._setup_fonts()
        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
    def _setup_fonts(self):
        try:
            fam = "Palatino Linotype"
            self.font_title  = tkfont.Font(family=fam, size=26, weight="bold")
            self.font_sub    = tkfont.Font(family=fam, size=14, slant="italic")
            self.font_label  = tkfont.Font(family=fam, size=14)
            self.font_btn    = tkfont.Font(family=fam, size=14, weight="bold")
            self.font_log    = tkfont.Font(family="Courier New", size=12)
            self.font_tab    = tkfont.Font(family=fam, size=14, weight="bold")
            self.font_spin   = tkfont.Font(family="Courier New", size=13)
            self.font_status = tkfont.Font(family=fam, size=13)
            self.font_phase  = tkfont.Font(family=fam, size=13, slant="italic")
            self.font_chk    = tkfont.Font(family=fam, size=13)
        except:
            self.font_title  = tkfont.Font(size=24, weight="bold")
            self.font_sub    = tkfont.Font(size=13, slant="italic")
            self.font_label  = tkfont.Font(size=13)
            self.font_btn    = tkfont.Font(size=13, weight="bold")
            self.font_log    = tkfont.Font(family="Courier", size=12)
            self.font_tab    = tkfont.Font(size=14, weight="bold")
            self.font_spin   = tkfont.Font(family="Courier", size=12)
            self.font_status = tkfont.Font(size=12)
            self.font_phase  = tkfont.Font(size=12, slant="italic")
            self.font_chk    = tkfont.Font(size=12)
    def _build_ui(self):
        self.header_canvas = tk.Canvas(self, height=140, bg=BG_DEEP, highlightthickness=0)
        self.header_canvas.pack(fill="x")
        self.header_canvas.bind("<Configure>", self._on_header_resize)
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("Mergo.TNotebook",
            background=BG_DEEP, borderwidth=0, tabmargins=[6,6,0,0])
        style.configure("Mergo.TNotebook.Tab",
            background=BG_PANEL, foreground=TEXT_DIM,
            font=self.font_tab, padding=[26,12], borderwidth=0)
        style.map("Mergo.TNotebook.Tab",
            background=[("selected", ACCENT_PURP)],
            foreground=[("selected", ACCENT_GOLD)])
        self.notebook = ttk.Notebook(self, style="Mergo.TNotebook")
        self.notebook.pack(fill="both", expand=True, padx=14, pady=10)
        self.tab_backup  = tk.Frame(self.notebook, bg=BG_MID)
        self.tab_convert = tk.Frame(self.notebook, bg=BG_MID)
        self.tab_fullop  = tk.Frame(self.notebook, bg=BG_MID)
        self.tab_restore = tk.Frame(self.notebook, bg=BG_DEEP)
        self.tab_mirror  = tk.Frame(self.notebook, bg=BG_MID)
        self.tab_fusion  = tk.Frame(self.notebook, bg=BG_MID)
        self.tab_pdf     = tk.Frame(self.notebook, bg=BG_MID)
        self.notebook.add(self.tab_backup,  text="  🌊  Backup Forum  ")
        self.notebook.add(self.tab_convert, text="  💧  Converti → HTML  ")
        self.notebook.add(self.tab_fullop,  text="  🌀  Backup + Conversione  ")
        self.notebook.add(self.tab_restore, text="  🫧  Ripristino Dati  ")
        self.notebook.add(self.tab_mirror,  text="  🌐  Mirror Sito Web  ")
        self.notebook.add(self.tab_fusion,  text="  🌊  Fusione Sito Statico  ")
        self.notebook.add(self.tab_pdf,     text="  📚  Unione PDF  ")
        self._build_tab_backup()
        self._build_tab_convert()
        self._build_tab_fullop()
        self._build_tab_restore()
        self._build_tab_mirror()
        self._build_tab_fusion()
        self._build_tab_pdf()
        self.status_var = tk.StringVar(value="🌊   Pronto per l'immersione   🌊")
        tk.Label(self, textvariable=self.status_var,
            bg=BG_PANEL, fg=ACCENT_TEAL, font=self.font_status,
            anchor="w", padx=18, pady=8, bd=0, relief="flat"
        ).pack(fill="x", side="bottom")
    def _on_header_resize(self, event):
        w = event.width; cx = w // 2
        for tid in self._title_ids:
            self.header_canvas.delete(tid)
        self._title_ids = []
        self._title_ids.append(self.header_canvas.create_text(
            cx, 48, text="🌊   MERGOHYDROX   🌊",
            fill=ACCENT_GOLD, font=self.font_title, anchor="center"))
        self._title_ids.append(self.header_canvas.create_text(
            cx, 92, text="Backup & Conversione vBulletin  —  L'Arte Fluida della Conservazione dei Dati",
            fill=TEXT_DIM, font=self.font_sub, anchor="center"))
        self._title_ids.append(self.header_canvas.create_line(
            30, 120, w-30, 120, fill=BORDER_GLOW, width=1))
        if not self._bubble_initialized and w > 100:
            self._bubble_initialized = True
            self.bubble_animator = BubbleAnimator(self.header_canvas, w, 140)
        elif self._bubble_initialized:
            self.bubble_animator.resize(w, 140)
    def _section(self, parent, title):
        lf = tk.LabelFrame(parent, text=f"   {title}   ",
            bg=BG_MID, fg=ACCENT_GOLD, font=self.font_sub,
            bd=1, relief="groove",
            highlightbackground=BORDER_GLOW, highlightthickness=1, labelanchor="nw")
        lf.pack(fill="x", padx=20, pady=10)
        return lf
    def _label(self, parent, text):
        return tk.Label(parent, text=text, bg=BG_MID, fg=TEXT_MAIN, font=self.font_label)
    def _entry(self, parent, textvariable=None, width=46):
        return tk.Entry(parent, textvariable=textvariable, width=width,
            bg=BG_PANEL, fg=ACCENT_TEAL, insertbackground=ACCENT_GOLD,
            relief="flat", bd=8, font=self.font_log)
    def _btn(self, parent, text, command, color=ACCENT_PURP):
        return tk.Button(parent, text=text, command=command,
            bg=color, fg=TEXT_MAIN,
            activebackground=ACCENT_GOLD, activeforeground=BG_DEEP,
            font=self.font_btn, relief="flat", bd=0,
            padx=22, pady=12, cursor="hand2")
    def _spinbox(self, parent, from_, to, textvariable, width=7, increment=1.0):
        return tk.Spinbox(parent, from_=from_, to=to, increment=increment,
            textvariable=textvariable, width=width,
            bg=BG_PANEL, fg=ACCENT_TEAL, buttonbackground=BORDER_GLOW,
            font=self.font_spin)
    def _checkbox(self, parent, text, variable, accent=ACCENT_TEAL):
        frame = tk.Frame(parent, bg=BG_MID)
        cb = tk.Checkbutton(frame, text=text, variable=variable,
            bg=BG_MID, fg=TEXT_MAIN,
            activebackground=BG_MID, activeforeground=ACCENT_GOLD,
            selectcolor=BG_PANEL,
            font=self.font_chk,
            bd=0, relief="flat",
            cursor="hand2")
        cb.pack(side="left")
        return frame
    def _logbox(self, parent, height=9):
        frame = tk.Frame(parent, bg=BG_PANEL, bd=1, relief="groove")
        frame.pack(fill="both", expand=True, padx=20, pady=8)
        sb = tk.Scrollbar(frame, bg=BORDER_GLOW, troughcolor=BG_DEEP, activebackground=ACCENT_PURP)
        sb.pack(side="right", fill="y")
        box = tk.Text(frame, height=height, font=self.font_log,
            bg=BG_PANEL, fg=TEXT_MAIN, insertbackground=ACCENT_GOLD,
            yscrollcommand=sb.set, state="disabled", bd=0, wrap="word")
        box.pack(fill="both", expand=True, padx=6, pady=6)
        sb.config(command=box.yview)
        return box
    def _progressbar(self, parent):
        style = ttk.Style()
        style.configure("Mergo.Horizontal.TProgressbar",
            troughcolor=BG_PANEL, background=ACCENT_PURP, borderwidth=0, thickness=22)
        pb = ttk.Progressbar(parent, style="Mergo.Horizontal.TProgressbar",
            orient="horizontal", mode="determinate")
        pb.pack(fill="x", padx=20, pady=6)
        return pb
    def _log_write(self, box, msg):
        def _do():
            box.config(state="normal")
            box.insert("end", msg + "\n")
            box.see("end")
            box.config(state="disabled")
        self.after(0, _do)

    def _set_status(self, msg):
        self.after(0, lambda: self.status_var.set(msg))
    def _build_tab_backup(self):
        p = self.tab_backup
        sec = self._section(p, "🌊  Configurazione Backup")
        sec.columnconfigure(1, weight=1)
        self._label(sec, "URL della Sezione Forum:").grid(row=0, column=0, sticky="w", padx=14, pady=10)
        self.bu_url = tk.StringVar()
        self._entry(sec, self.bu_url, width=52).grid(row=0, column=1, columnspan=2, sticky="ew", padx=14, pady=10)
        self._label(sec, "Cartella di Destinazione:").grid(row=1, column=0, sticky="w", padx=14, pady=10)
        self.bu_outdir = tk.StringVar(value="backup_forum")
        self._entry(sec, self.bu_outdir, width=40).grid(row=1, column=1, sticky="ew", padx=14, pady=10)
        self._btn(sec, "📁  Browse", self._pick_bu_dir, BORDER_GLOW).grid(row=1, column=2, padx=10, pady=10)
        row2 = tk.Frame(sec, bg=BG_MID)
        row2.grid(row=2, column=0, columnspan=3, sticky="ew", padx=14, pady=8)
        self._label(row2, "Pagina Iniziale:").pack(side="left", padx=(0,8))
        self.bu_startpage = tk.IntVar(value=1)
        self._spinbox(row2, 1, 9999, self.bu_startpage, width=6).pack(side="left")
        self._label(row2, "    Ritardo (sec):").pack(side="left", padx=(18,8))
        self.bu_delay = tk.DoubleVar(value=0.5)
        self._spinbox(row2, 0.1, 10.0, self.bu_delay, width=6, increment=0.1).pack(side="left")
        self._label(row2, "    Processi:").pack(side="left", padx=(18,8))
        self.bu_workers = tk.IntVar(value=8)
        self._spinbox(row2, 1, 64, self.bu_workers, width=5).pack(side="left")
        opt_frame = tk.Frame(sec, bg=BG_MID)
        opt_frame.grid(row=3, column=0, columnspan=3, sticky="ew", padx=14, pady=8)
        self.bu_media = tk.BooleanVar(value=False)
        self._checkbox(opt_frame, "  📥  Scarica anche immagini, video e tutti i file multimediali", self.bu_media).pack(side="left")
        bf = tk.Frame(p, bg=BG_MID)
        bf.pack(pady=12)
        self._btn(bf, "⚡   AVVIA BACKUP", self._start_backup, ACCENT_PURP).pack(side="left", padx=12)
        self._btn(bf, "⏹   STOP", self._stop_operation, RUNE_RED).pack(side="left", padx=12)
        self.bu_progress = self._progressbar(p)
        self.bu_log      = self._logbox(p, height=10)
    def _pick_bu_dir(self):
        d = filedialog.askdirectory(title="Scegli la cartella di backup")
        if d: self.bu_outdir.set(d)
    def _start_backup(self):
        url = self.bu_url.get().strip()
        if not url:
            messagebox.showwarning("Attenzione", "Inserisci l'URL della sezione forum!")
            return
        self._stop_event.clear()
        self.bu_progress["value"] = 0
        self._log_write(self.bu_log, "=" * 65)
        self._log_write(self.bu_log, "✨ Avvio del backup in corso...")
        if self.bu_media.get():
            self._log_write(self.bu_log, "📥 Scaricamento media: ATTIVO")
        self._set_status("🌊   Backup in corso...")
        def run():
            backup = VBulletinBackup(
                base_url=url,
                output_dir=self.bu_outdir.get(),
                delay=self.bu_delay.get(),
                max_workers=self.bu_workers.get(),
                start_page=self.bu_startpage.get(),
                log_callback=lambda m: self._log_write(self.bu_log, m),
                download_media=self.bu_media.get(),
                stop_event=self._stop_event,
            )
            self._backup_obj = backup
            def on_progress(done, total):
                pct = (done/total*100) if total else 0
                self.after(0, lambda: self.bu_progress.configure(value=pct))
            result = backup.run_backup(progress_callback=on_progress)
            self._set_status(f"✅   Backup completato — {result} discussioni scaricate")
            self.after(0, lambda: self.bu_progress.configure(value=100))
        threading.Thread(target=run, daemon=True).start()
    def _build_tab_convert(self):
        p = self.tab_convert
        sec = self._section(p, "💧  Impostazioni Archivio HTML")
        sec.columnconfigure(1, weight=1)
        self._label(sec, "Cartella Sorgente HTML:").grid(row=0, column=0, sticky="w", padx=14, pady=10)
        self.co_indir = tk.StringVar()
        self._entry(sec, self.co_indir, width=40).grid(row=0, column=1, sticky="ew", padx=14, pady=10)
        self._btn(sec, "📁  Browse", self._pick_co_indir, BORDER_GLOW).grid(row=0, column=2, padx=10, pady=10)
        self._label(sec, "File di Destinazione (.html):").grid(row=1, column=0, sticky="w", padx=14, pady=10)
        self.co_outfile = tk.StringVar(value="archivio_forum.html")
        self._entry(sec, self.co_outfile, width=40).grid(row=1, column=1, sticky="ew", padx=14, pady=10)
        self._btn(sec, "💾  Salva come", self._pick_co_outfile, BORDER_GLOW).grid(row=1, column=2, padx=10, pady=10)
        opt_frame = tk.Frame(sec, bg=BG_MID)
        opt_frame.grid(row=2, column=0, columnspan=3, sticky="ew", padx=14, pady=8)
        self.co_embed = tk.BooleanVar(value=False)
        self._checkbox(opt_frame,
            "  🖼  Incorpora i media come Base64 (file autonomo — può essere grande)",
            self.co_embed).pack(side="left")
        bf = tk.Frame(p, bg=BG_MID)
        bf.pack(pady=12)
        self._btn(bf, "🌀   CREA ARCHIVIO HTML", self._start_convert, ACCENT_PURP).pack(side="left", padx=12)
        self._btn(bf, "⏹   STOP", self._stop_operation, RUNE_RED).pack(side="left", padx=12)
        self.co_progress = self._progressbar(p)
        self.co_log      = self._logbox(p, height=12)
    def _pick_co_indir(self):
        d = filedialog.askdirectory(title="Scegli la cartella contenente i file HTML")
        if d: self.co_indir.set(d)
    def _pick_co_outfile(self):
        f = filedialog.asksaveasfilename(
            title="Salva archivio HTML", defaultextension=".html",
            filetypes=[("File HTML", "*.html"), ("Tutti i file", "*.*")])
        if f: self.co_outfile.set(f)
    def _start_convert(self):
        indir   = self.co_indir.get().strip()
        outfile = self.co_outfile.get().strip()
        if not indir:
            messagebox.showwarning("Attenzione", "Scegli la cartella sorgente HTML!"); return
        if not outfile:
            messagebox.showwarning("Attenzione", "Specifica un file di destinazione!"); return
        self._stop_event.clear()
        self.co_progress["value"] = 0
        self._log_write(self.co_log, "=" * 65)
        self._log_write(self.co_log, "🌀 Composizione dell'archivio HTML...")
        if self.co_embed.get():
            self._log_write(self.co_log, "🖼  Incorporamento Base64: ATTIVO (il file potrebbe essere grande)")
        self._set_status("💧   Conversione in corso...")
        def run():
            media_dl = MediaDownloader(indir,
                log_callback=lambda m: self._log_write(self.co_log, m),
                stop_event=self._stop_event) if self.co_embed.get() else None
            def on_progress(done, total):
                pct = (done/total*100) if total else 0
                self.after(0, lambda: self.co_progress.configure(value=pct))
            result = convert_html_folder(
                input_dir=indir,
                output_file=outfile,
                log_callback=lambda m: self._log_write(self.co_log, m),
                progress_callback=on_progress,
                stop_event=self._stop_event,
                media_dl=media_dl,
                embed_base64=self.co_embed.get(),
            )
            self._set_status(f"✅   Archivio completato — {result} discussioni archiviate")
            self.after(0, lambda: self.co_progress.configure(value=100))
        threading.Thread(target=run, daemon=True).start()
    def _build_tab_fullop(self):
        p = self.tab_fullop
        sec = self._section(p, "⚡  Backup + Conversione Automatica")
        sec.columnconfigure(1, weight=1)
        self._label(sec, "URL della Sezione Forum:").grid(row=0, column=0, sticky="w", padx=14, pady=10)
        self.fu_url = tk.StringVar()
        self._entry(sec, self.fu_url, width=52).grid(row=0, column=1, columnspan=2, sticky="ew", padx=14, pady=10)
        self._label(sec, "Cartella di Destinazione:").grid(row=1, column=0, sticky="w", padx=14, pady=10)
        self.fu_outdir = tk.StringVar(value="backup_forum")
        self._entry(sec, self.fu_outdir, width=40).grid(row=1, column=1, sticky="ew", padx=14, pady=10)
        self._btn(sec, "📁  Browse", self._pick_fu_dir, BORDER_GLOW).grid(row=1, column=2, padx=10, pady=10)
        self._label(sec, "File HTML di Destinazione:").grid(row=2, column=0, sticky="w", padx=14, pady=10)
        self.fu_outfile = tk.StringVar(value="archivio_forum.html")
        self._entry(sec, self.fu_outfile, width=40).grid(row=2, column=1, sticky="ew", padx=14, pady=10)
        self._btn(sec, "💾  Salva come", self._pick_fu_outfile, BORDER_GLOW).grid(row=2, column=2, padx=10, pady=10)
        row_extra = tk.Frame(sec, bg=BG_MID)
        row_extra.grid(row=3, column=0, columnspan=3, sticky="ew", padx=14, pady=8)
        self._label(row_extra, "Pagina Iniziale:").pack(side="left", padx=(0,8))
        self.fu_startpage = tk.IntVar(value=1)
        self._spinbox(row_extra, 1, 9999, self.fu_startpage, width=6).pack(side="left")
        self._label(row_extra, "    Ritardo (sec):").pack(side="left", padx=(18,8))
        self.fu_delay = tk.DoubleVar(value=0.5)
        self._spinbox(row_extra, 0.1, 10.0, self.fu_delay, width=6, increment=0.1).pack(side="left")
        self._label(row_extra, "    Processi:").pack(side="left", padx=(18,8))
        self.fu_workers = tk.IntVar(value=8)
        self._spinbox(row_extra, 1, 64, self.fu_workers, width=5).pack(side="left")
        opt_frame = tk.Frame(sec, bg=BG_MID)
        opt_frame.grid(row=4, column=0, columnspan=3, sticky="ew", padx=14, pady=4)
        self.fu_media  = tk.BooleanVar(value=False)
        self.fu_embed  = tk.BooleanVar(value=False)
        self._checkbox(opt_frame, "  📥  Scarica i file multimediali", self.fu_media).pack(side="left", padx=(0,24))
        self._checkbox(opt_frame, "  🖼  Incorpora i media come Base64 nell'HTML", self.fu_embed).pack(side="left")
        bf = tk.Frame(p, bg=BG_MID)
        bf.pack(pady=10)
        self._btn(bf, "⚡   BACKUP + CONVERTI", self._start_fullop, "#4a1f7a").pack(side="left", padx=12)
        self._btn(bf, "⏹   STOP", self._stop_operation, RUNE_RED).pack(side="left", padx=12)
        phase_frame = tk.Frame(p, bg=BG_MID)
        phase_frame.pack(anchor="w", padx=20, pady=4)
        tk.Label(phase_frame, text="Fase:  ", bg=BG_MID, fg=TEXT_DIM, font=self.font_label).pack(side="left")
        self.fu_phase_var = tk.StringVar(value="In attesa di iniziare...")
        tk.Label(phase_frame, textvariable=self.fu_phase_var,
            bg=BG_MID, fg=ACCENT_GOLD, font=self.font_phase).pack(side="left")
        self.fu_progress = self._progressbar(p)
        self.fu_log      = self._logbox(p, height=9)
    def _pick_fu_dir(self):
        d = filedialog.askdirectory(title="Scegli la cartella di destinazione")
        if d: self.fu_outdir.set(d)
    def _pick_fu_outfile(self):
        f = filedialog.asksaveasfilename(
            title="Salva archivio HTML", defaultextension=".html",
            filetypes=[("File HTML", "*.html"), ("Tutti i file", "*.*")])
        if f: self.fu_outfile.set(f)
    def _start_fullop(self):
        url     = self.fu_url.get().strip()
        outdir  = self.fu_outdir.get().strip()
        outfile = self.fu_outfile.get().strip()
        if not url:
            messagebox.showwarning("Attenzione", "Inserisci l'URL della sezione forum!"); return
        self._stop_event.clear()
        self.fu_progress["value"] = 0
        self._log_write(self.fu_log, "=" * 65)
        self._log_write(self.fu_log, "✨ Avvio processo completo: Backup + Conversione")
        embed_b64 = self.fu_embed.get()
        dl_media  = self.fu_media.get() or embed_b64
        def run():
            self.after(0, lambda: self.fu_phase_var.set("🌊  Fase 1/2 — Scaricamento del Forum..."))
            self._set_status("🌊   Fase 1/2: Backup in corso...")
            backup = VBulletinBackup(
                base_url=url,
                output_dir=outdir,
                delay=self.fu_delay.get(),
                max_workers=self.fu_workers.get(),
                start_page=self.fu_startpage.get(),
                log_callback=lambda m: self._log_write(self.fu_log, m),
                download_media=dl_media,
                stop_event=self._stop_event,
            )
            self._backup_obj = backup
            def on_progress_bu(done, total):
                pct = (done/total*50) if total else 0
                self.after(0, lambda: self.fu_progress.configure(value=pct))
            backup_count = backup.run_backup(progress_callback=on_progress_bu)
            if self._stop_event.is_set():
                self._set_status("⏹  Operazione interrotta."); return
            self.after(0, lambda: self.fu_phase_var.set("💧  Fase 2/2 — Composizione Archivio HTML..."))
            self._set_status("💧   Fase 2/2: Conversione in corso...")
            media_dl = MediaDownloader(outdir,
                log_callback=lambda m: self._log_write(self.fu_log, m),
                stop_event=self._stop_event) if embed_b64 else None
            def on_progress_co(done, total):
                pct = 50 + (done/total*50) if total else 50
                self.after(0, lambda: self.fu_progress.configure(value=pct))
            convert_count = convert_html_folder(
                input_dir=outdir,
                output_file=outfile,
                log_callback=lambda m: self._log_write(self.fu_log, m),
                progress_callback=on_progress_co,
                stop_event=self._stop_event,
                media_dl=media_dl,
                embed_base64=embed_b64,
                forum_url=url,
            )
            self.after(0, lambda: self.fu_phase_var.set("✅  Completato — L'archivio è pronto!"))
            self._set_status(f"✅   Fatto — {backup_count} discussioni scaricate, {convert_count} archiviate")
            self.after(0, lambda: self.fu_progress.configure(value=100))
        threading.Thread(target=run, daemon=True).start()
    def _build_tab_restore(self):
        p = self.tab_restore
        banner = tk.Canvas(p, height=58, bg=BG_DEEP, highlightthickness=0)
        banner.pack(fill="x")
        def _draw_banner(event):
            banner.delete("all")
            w = event.width
            banner.create_text(w//2, 18,
                text="〰 ≈ ○ ◦ ∘ ◌ 〰 ≈ ○ ◦ ∘ ◌ 〰 ≈ ○ ◦ ∘ ◌ 〰 ≈ ○ ◦ ∘",
                fill=BORDER_GLOW, font=self.font_log, anchor="center")
            banner.create_text(w//2, 40,
                text="🫧   RIPRISTINO DATI  —  Analisi Inversa & Recupero Dati   🫧",
                fill=ACCENT_GOLD, font=self.font_sub, anchor="center")
        banner.bind("<Configure>", _draw_banner)
        sec = tk.LabelFrame(p, text="   🫧  Sorgente — File Archivio HTML Convertito   ",
            bg=BG_DEEP, fg=ACCENT_GOLD, font=self.font_sub,
            bd=1, relief="groove",
            highlightbackground=BORDER_GLOW, highlightthickness=1, labelanchor="nw")
        sec.pack(fill="x", padx=20, pady=10)
        sec.columnconfigure(1, weight=1)
        tk.Label(sec, text="File Archivio HTML:", bg=BG_DEEP, fg=TEXT_MAIN,
            font=self.font_label).grid(row=0, column=0, sticky="w", padx=14, pady=12)
        self.re_infile = tk.StringVar()
        tk.Entry(sec, textvariable=self.re_infile, width=46,
            bg=BG_PANEL, fg=ACCENT_TEAL, insertbackground=ACCENT_GOLD,
            relief="flat", bd=8, font=self.font_log
            ).grid(row=0, column=1, sticky="ew", padx=14, pady=12)
        tk.Button(sec, text="📂  Apri File",
            command=self._pick_re_infile,
            bg=BORDER_GLOW, fg=TEXT_MAIN,
            activebackground=ACCENT_GOLD, activeforeground=BG_DEEP,
            font=self.font_btn, relief="flat", bd=0,
            padx=18, pady=10, cursor="hand2"
            ).grid(row=0, column=2, padx=10, pady=12)
        tk.Label(sec,
            text="Accetta: il singolo file HTML generato da questo programma (con o senza media incorporati).\n"
                 "I file di output verranno salvati nella stessa cartella del file HTML.",
            bg=BG_DEEP, fg=TEXT_DIM, font=self.font_phase, justify="left", anchor="w"
            ).grid(row=1, column=0, columnspan=3, sticky="ew", padx=14, pady=(0,10))
        self.re_phase_var = tk.StringVar(value="In attesa di avvio...")
        tk.Label(p, textvariable=self.re_phase_var,
            bg=BG_DEEP, fg=ACCENT_GOLD, font=self.font_phase, anchor="w"
            ).pack(anchor="w", padx=22, pady=(4,0))
        re_style = ttk.Style()
        re_style.configure("Restore.Horizontal.TProgressbar",
            troughcolor=BG_PANEL, background=ACCENT_GOLD, borderwidth=0, thickness=22)
        self.re_progress = ttk.Progressbar(p, style="Restore.Horizontal.TProgressbar",
            orient="horizontal", mode="determinate")
        self.re_progress.pack(fill="x", padx=20, pady=6)
        btn_sec = tk.LabelFrame(p, text="   💧  Scegli il Formato di Uscita   ",
            bg=BG_DEEP, fg=ACCENT_GOLD, font=self.font_sub,
            bd=1, relief="groove",
            highlightbackground=BORDER_GLOW, highlightthickness=1, labelanchor="nw")
        btn_sec.pack(fill="x", padx=20, pady=8)
        btn_inner = tk.Frame(btn_sec, bg=BG_DEEP)
        btn_inner.pack(pady=14)
        tk.Button(btn_inner,
            text="{ }   Converti in JSON",
            command=self._start_restore_json,
            bg="#2d0b5a", fg=ACCENT_GOLD,
            activebackground=ACCENT_GOLD, activeforeground=BG_DEEP,
            font=self.font_btn, relief="flat", bd=0,
            padx=28, pady=14, cursor="hand2"
            ).pack(side="left", padx=16)
        tk.Button(btn_inner,
            text="⊞   Converti in CSV",
            command=self._start_restore_csv,
            bg="#063a3a", fg=ACCENT_TEAL,
            activebackground=ACCENT_TEAL, activeforeground=BG_DEEP,
            font=self.font_btn, relief="flat", bd=0,
            padx=28, pady=14, cursor="hand2"
            ).pack(side="left", padx=16)
        tk.Button(btn_inner,
            text="⏹   STOP",
            command=self._stop_operation,
            bg=RUNE_RED, fg=TEXT_MAIN,
            activebackground=ACCENT_GOLD, activeforeground=BG_DEEP,
            font=self.font_btn, relief="flat", bd=0,
            padx=22, pady=14, cursor="hand2"
            ).pack(side="left", padx=16)
        tk.Label(p, text="🌊  Registro Operazioni:", bg=BG_DEEP,
            fg=ACCENT_GOLD, font=self.font_sub, anchor="w"
            ).pack(anchor="w", padx=22, pady=(6,0))
        log_frame = tk.Frame(p, bg=BG_PANEL, bd=1, relief="groove")
        log_frame.pack(fill="both", expand=True, padx=20, pady=6)
        re_sb = tk.Scrollbar(log_frame, bg=BORDER_GLOW, troughcolor=BG_DEEP, activebackground=ACCENT_PURP)
        re_sb.pack(side="right", fill="y")
        self.re_log = tk.Text(log_frame, font=self.font_log,
            bg="#09060f", fg=ACCENT_GOLD,
            insertbackground=ACCENT_GOLD,
            yscrollcommand=re_sb.set,
            state="disabled", bd=0, wrap="word")
        self.re_log.pack(fill="both", expand=True, padx=6, pady=6)
        re_sb.config(command=self.re_log.yview)
        self.re_log.tag_config("head",  foreground=ACCENT_GOLD,  font=self.font_btn)
        self.re_log.tag_config("ok",    foreground=ACCENT_TEAL)
        self.re_log.tag_config("warn",  foreground=RUNE_RED)
        self.re_log.tag_config("dim",   foreground=TEXT_DIM)
        self.re_log.tag_config("media", foreground=ACCENT_PURP)
        self.re_result_var = tk.StringVar(value="")
        tk.Label(p, textvariable=self.re_result_var,
            bg=BG_DEEP, fg=ACCENT_TEAL, font=self.font_status, anchor="center"
            ).pack(fill="x", padx=20, pady=(2,8))
    def _pick_re_infile(self):
        f = filedialog.askopenfilename(
            title="Seleziona il file Archivio HTML",
            filetypes=[("File HTML", "*.html *.htm"), ("Tutti i file", "*.*")])
        if f:
            self.re_infile.set(f)
    def _re_log_write(self, msg):
        def _do():
            self.re_log.config(state="normal")
            if msg.startswith("  ✅") or msg.startswith("✅"):
                tag = "ok"
            elif msg.startswith("  ⚠") or msg.startswith("⚠"):
                tag = "warn"
            elif msg.startswith("    ✦") or msg.startswith("    📥"):
                tag = "media"
            elif any(msg.startswith(pfx) for pfx in ["🌊","💧","🫧","✨","🜂"]):
                tag = "head"
            elif "⏹" in msg:
                tag = "warn"
            else:
                tag = "dim"
            self.re_log.insert("end", msg + "\n", tag)
            self.re_log.see("end")
            self.re_log.config(state="disabled")
        self.after(0, _do)
    def _re_validate(self):
        path = self.re_infile.get().strip()
        if not path:
            messagebox.showwarning("Attenzione",
                "Seleziona prima il file archivio HTML!")
            return None
        if not os.path.isfile(path):
            messagebox.showerror("Errore",
                "Il percorso selezionato non è un file valido.")
            return None
        if not path.lower().endswith((".html", ".htm")):
            if not messagebox.askyesno("Attenzione",
                    "Il file non ha estensione .html.\nProcedere comunque?"):
                return None
        return path
    def _re_parse_phase(self, html_path):
        self._re_cache = None
        self.after(0, lambda: self.re_phase_var.set("🌊  Analisi del documento in corso..."))
        self._re_log_write("=" * 60)
        self._re_log_write(f"🜂  File selezionato: {os.path.basename(html_path)}")
        self._re_log_write("🌊  Estrazione dei dati in corso...")
        all_threads, csv_rows, total_posts, recovered_dir = _parse_single_html(
            html_path, self._re_log_write, self._stop_event)
        if self._stop_event.is_set():
            self.after(0, lambda: self.re_phase_var.set("⏹  Interrotto."))
            self._set_status("⏹   Ripristino interrotto.")
            return False
        if not all_threads:
            self._re_log_write("⚠  Nessuna discussione estratta da questo file.")
            self.after(0, lambda: self.re_phase_var.set("⚠  Nessun dato trovato."))
            return False
        self._re_log_write(
            f"  💧 Analizzate {len(all_threads)} discussione/i, {total_posts} messaggio/i totali")
        self._re_cache = {
            "all_threads":    all_threads,
            "csv_rows":       csv_rows,
            "total_posts":    total_posts,
            "recovered_dir":  recovered_dir,
            "html_dir":       os.path.dirname(os.path.abspath(html_path)),
        }
        return True
    def _start_restore_json(self):
        html_path = self._re_validate()
        if not html_path: return
        self._stop_event.clear()
        self.re_progress["value"] = 0
        self.re_result_var.set("")
        self._set_status("{ }   Conversione JSON in corso...")
        def run():
            ok = self._re_parse_phase(html_path)
            if not ok: return
            self.after(0, lambda: self.re_progress.configure(value=60))
            self.after(0, lambda: self.re_phase_var.set("🌊  Scrittura del codice JSON..."))
            cache    = self._re_cache
            out_path = os.path.join(cache["html_dir"], "vbulletin_recovery.json")
            result   = restoration_write_json(
                cache["all_threads"], cache["total_posts"], out_path, self._re_log_write)
            self.after(0, lambda: self.re_progress.configure(value=100))
            if result:
                n = len(cache["all_threads"]); p = cache["total_posts"]
                summary = f"✅   JSON completato — {n} discussione/i, {p} messaggio/i  →  {os.path.basename(result)}"
                self.after(0, lambda: self.re_phase_var.set("✅  File JSON completato — Dati pronti per il database."))
                self.after(0, lambda: self.re_result_var.set(summary))
                self._set_status(f"✅   JSON completato — {n} discussioni, {p} messaggi")
                self._re_log_write(f"✅  Salvato: {result}")
                self._re_log_write("🌊  Operazione completata: dati pronti per il database.")
            else:
                self.after(0, lambda: self.re_phase_var.set("⚠  Scrittura JSON fallita."))
                self._set_status("⚠   Scrittura JSON fallita — controlla il registro.")
        threading.Thread(target=run, daemon=True).start()
    def _start_restore_csv(self):
        html_path = self._re_validate()
        if not html_path: return
        self._stop_event.clear()
        self.re_progress["value"] = 0
        self.re_result_var.set("")
        self._set_status("⊞   Conversione CSV in corso...")
        def run():
            ok = self._re_parse_phase(html_path)
            if not ok: return
            self.after(0, lambda: self.re_progress.configure(value=60))
            self.after(0, lambda: self.re_phase_var.set("🌊  Scrittura della tabella CSV..."))
            cache    = self._re_cache
            out_path = os.path.join(cache["html_dir"], "vbulletin_recovery.csv")
            result   = restoration_write_csv(
                cache["csv_rows"], out_path, self._re_log_write)
            self.after(0, lambda: self.re_progress.configure(value=100))
            if result:
                n = len(cache["all_threads"]); p = cache["total_posts"]
                summary = f"✅   CSV completato — {n} discussione/i, {p} messaggio/i  →  {os.path.basename(result)}"
                self.after(0, lambda: self.re_phase_var.set("✅  File CSV completato — Dati pronti per il database."))
                self.after(0, lambda: self.re_result_var.set(summary))
                self._set_status(f"✅   CSV completato — {n} discussioni, {p} messaggi")
                self._re_log_write(f"✅  Salvato: {result}")
                self._re_log_write("🌊  Operazione completata: dati pronti per il database.")
            else:
                self.after(0, lambda: self.re_phase_var.set("⚠  Scrittura CSV fallita."))
                self._set_status("⚠   Scrittura CSV fallita — controlla il registro.")
        threading.Thread(target=run, daemon=True).start()
    def _build_tab_mirror(self):
        p = self.tab_mirror
        sec = self._section(p, "🌐  Configurazione Mirror Sito Web")
        sec.columnconfigure(1, weight=1)
        self._label(sec, "URL del Sito Web:").grid(
            row=0, column=0, sticky="w", padx=14, pady=10)
        self.mi_url = tk.StringVar()
        self._entry(sec, self.mi_url, width=52).grid(
            row=0, column=1, columnspan=2, sticky="ew", padx=14, pady=10)
        self._label(sec, "Cartella di Destinazione:").grid(
            row=1, column=0, sticky="w", padx=14, pady=10)
        self.mi_outdir = tk.StringVar(value="mirror")
        self._entry(sec, self.mi_outdir, width=40).grid(
            row=1, column=1, sticky="ew", padx=14, pady=10)
        self._btn(sec, "📁  Browse", self._pick_mi_dir, BORDER_GLOW).grid(
            row=1, column=2, padx=10, pady=10)
        row_opts = tk.Frame(sec, bg=BG_MID)
        row_opts.grid(row=2, column=0, columnspan=3, sticky="ew", padx=14, pady=8)
        self._label(row_opts, "Processi:").pack(side="left", padx=(0, 8))
        self.mi_workers = tk.IntVar(value=8)
        self._spinbox(row_opts, 1, 32, self.mi_workers, width=5).pack(side="left")
        self._label(row_opts, "    Ritardo (sec):").pack(side="left", padx=(18, 8))
        self.mi_delay = tk.DoubleVar(value=0.5)
        self._spinbox(row_opts, 0.0, 10.0, self.mi_delay, width=6, increment=0.1).pack(side="left")
        tk.Label(sec,
            text="Scarica l'intero sito web — pagine HTML, immagini, CSS, JS, media —\n"
                 "e riscrive i link interni in modo che il mirror funzioni completamente offline.",
            bg=BG_MID, fg=TEXT_DIM, font=self.font_phase, justify="left", anchor="w"
        ).grid(row=3, column=0, columnspan=3, sticky="ew", padx=14, pady=(0, 10))
        bf = tk.Frame(p, bg=BG_MID)
        bf.pack(pady=12)
        self._btn(bf, "🌐   AVVIA MIRROR", self._start_mirror, "#1a3a5c").pack(side="left", padx=12)
        self._btn(bf, "⏹   STOP",          self._stop_mirror,  RUNE_RED ).pack(side="left", padx=12)
        self.mi_count_var = tk.StringVar(value="")
        tk.Label(p, textvariable=self.mi_count_var,
            bg=BG_MID, fg=ACCENT_GOLD, font=self.font_phase, anchor="w"
        ).pack(anchor="w", padx=22, pady=(0, 4))
        mi_style = ttk.Style()
        mi_style.configure("Mirror.Horizontal.TProgressbar",
            troughcolor=BG_PANEL, background=ACCENT_TEAL, borderwidth=0, thickness=22)
        self.mi_progress = ttk.Progressbar(p, style="Mirror.Horizontal.TProgressbar",
            orient="horizontal", mode="indeterminate")
        self.mi_progress.pack(fill="x", padx=20, pady=6)
        self.mi_log = self._logbox(p, height=13)
    def _pick_mi_dir(self):
        d = filedialog.askdirectory(title="Scegli la cartella di destinazione del mirror")
        if d:
            self.mi_outdir.set(d)
    def _stop_mirror(self):
        self._mi_stop.set()
        self._set_status("⏹   Interruzione mirror richiesta...")
        self._log_write(self.mi_log, "⏹  Interruzione richiesta — completamento degli scaricamenti in corso...")
        try:
            self.mi_progress.stop()
        except Exception:
            pass
    def _start_mirror(self):
        url    = self.mi_url.get().strip()
        outdir = self.mi_outdir.get().strip()
        if not url:
            messagebox.showwarning("Attenzione", "Inserisci l'URL del sito web!"); return
        if not url.startswith(("http://", "https://")):
            messagebox.showwarning("Attenzione",
                "L'URL deve iniziare con http:// o https://"); return
        if not outdir:
            messagebox.showwarning("Attenzione", "Scegli una cartella di destinazione!"); return
        self._mi_stop = threading.Event()
        self._log_write(self.mi_log, "=" * 65)
        self._log_write(self.mi_log, f"🌐 Avvio mirroring: {url}")
        self._log_write(self.mi_log, f"📁 Cartella di destinazione: {outdir}")
        self._log_write(self.mi_log, f"⚙  Processi: {self.mi_workers.get()}  |  Ritardo: {self.mi_delay.get()}s")
        self.mi_count_var.set("🌐  Scansione in corso…  (0 file scaricati)")
        self.mi_progress.start(12)
        self._set_status("🌐   Mirroring del sito in corso…")
        def on_progress(n):
            self.after(0, lambda: self.mi_count_var.set(
                f"🌐  Scansione in corso…  {n} file scaricati finora"))
        def run():
            crawler = MirrorCrawler(
                base_url=url,
                output_dir=outdir,
                max_workers=self.mi_workers.get(),
                delay=self.mi_delay.get(),
                log_callback=lambda m: self._log_write(self.mi_log, m),
                stop_event=self._mi_stop,
                progress_callback=on_progress,
            )
            n = crawler.run()
            def _finish():
                self.mi_progress.stop()
                self.mi_progress["value"] = 100
                self.mi_count_var.set(f"✅  Mirroring completato — {n} file salvati in: {outdir}")
            self.after(0, _finish)
            if self._mi_stop.is_set():
                self._set_status(f"⏹   Mirroring interrotto — {n} file salvati")
                self._log_write(self.mi_log, f"⏹  Interrotto. {n} file salvati.")
            else:
                self._set_status(f"✅   Mirroring completato — {n} file salvati in: {outdir}")
        threading.Thread(target=run, daemon=True).start()
    def _build_tab_fusion(self):
        p = self.tab_fusion
        sec = self._section(p, "🌊  Configurazione Fusione Sito Statico")
        sec.columnconfigure(1, weight=1)
        self._label(sec, "Cartella Sito Sorgente:").grid(
            row=0, column=0, sticky="w", padx=14, pady=10)
        self.ss_srcdir = tk.StringVar()
        self._entry(sec, self.ss_srcdir, width=52).grid(
            row=0, column=1, sticky="ew", padx=14, pady=10)
        self._btn(sec, "📁  Browse", self._pick_ss_src, BORDER_GLOW).grid(
            row=0, column=2, padx=10, pady=10)
        self._label(sec, "File HTML di Destinazione:").grid(
            row=1, column=0, sticky="w", padx=14, pady=10)
        self.ss_outfile = tk.StringVar(value="ARCHIVIO_SUPREMO.html")
        self._entry(sec, self.ss_outfile, width=52).grid(
            row=1, column=1, sticky="ew", padx=14, pady=10)
        self._btn(sec, "📁  Browse", self._pick_ss_outfile, BORDER_GLOW).grid(
            row=1, column=2, padx=10, pady=10)
        tk.Label(sec,
            text="Unisce un intero sito statico scaricato (centinaia di pagine .html/.php.html\n"
                 "+ immagini, audio, pdf, css, js) in UN UNICO file HTML autonomo — ogni risorsa\n"
                 "incorporata come Base64, barra laterale per categorie, ricerca lato client, nessuna dipendenza esterna.",
            bg=BG_MID, fg=TEXT_DIM, font=self.font_phase, justify="left", anchor="w"
        ).grid(row=2, column=0, columnspan=3, sticky="ew", padx=14, pady=(0, 10))
        bf = tk.Frame(p, bg=BG_MID)
        bf.pack(pady=12)
        self._btn(bf, "🌊   AVVIA FUSIONE", self._start_fusion, "#1a3a5c").pack(side="left", padx=12)
        self._btn(bf, "⏹   STOP",          self._stop_fusion,  RUNE_RED ).pack(side="left", padx=12)
        self.ss_phase_var = tk.StringVar(value="In attesa di iniziare...")
        tk.Label(p, textvariable=self.ss_phase_var,
            bg=BG_MID, fg=ACCENT_GOLD, font=self.font_phase, anchor="w"
        ).pack(anchor="w", padx=22, pady=(0, 4))
        self.ss_progress = self._progressbar(p)
        self.ss_log = self._logbox(p, height=13)
    def _pick_ss_src(self):
        d = filedialog.askdirectory(title="Scegli la cartella del sito scaricato")
        if d:
            self.ss_srcdir.set(d)
    def _pick_ss_outfile(self):
        f = filedialog.asksaveasfilename(
            title="Scegli il file HTML di destinazione",
            defaultextension=".html",
            filetypes=[("File HTML", "*.html")],
            initialfile=os.path.basename(self.ss_outfile.get() or "ARCHIVIO_SUPREMO.html"))
        if f:
            self.ss_outfile.set(f)
    def _stop_fusion(self):
        self._fu_stop.set()
        self._set_status("⏹   Interruzione fusione richiesta...")
        self._log_write(self.ss_log, "⏹  Interruzione richiesta — completamento della pagina corrente...")
    def _start_fusion(self):
        srcdir  = self.ss_srcdir.get().strip()
        outfile = self.ss_outfile.get().strip()
        if not srcdir:
            messagebox.showwarning("Attenzione", "Scegli la cartella del sito sorgente!"); return
        if not os.path.isdir(srcdir):
            messagebox.showwarning("Attenzione", "La cartella sorgente non esiste!"); return
        if not outfile:
            messagebox.showwarning("Attenzione", "Scegli un file HTML di destinazione!"); return
        self._fu_stop = threading.Event()
        self.ss_progress["value"] = 0
        self.ss_progress.configure(mode="indeterminate")
        self.ss_progress.start(12)
        self.ss_phase_var.set("🌊  Fusione dell'archivio — scansione pagine e incorporamento risorse...")
        self._log_write(self.ss_log, "=" * 65)
        self._log_write(self.ss_log, f"🌊 Avvio Fusione Sito Statico")
        self._log_write(self.ss_log, f"📁 Sorgente: {srcdir}")
        self._log_write(self.ss_log, f"💾 Destinazione: {outfile}")
        self._set_status("🌊   Fusione Sito Statico in corso...")
        def run():
            engine = StaticSiteFusionEngine(
                src_folder=srcdir,
                out_file=outfile,
                log_callback=lambda m: self._log_write(self.ss_log, m),
                stop_event=self._fu_stop,
            )
            try:
                result = engine.run()
            except Exception as e:
                result = None
                self._log_write(self.ss_log, f"⚠  Fusione fallita: {e}")
            def _finish():
                self.ss_progress.stop()
                self.ss_progress.configure(mode="determinate")
                self.ss_progress["value"] = 100
            self.after(0, _finish)
            if self._fu_stop.is_set():
                self.ss_phase_var.set("⏹  Fusione interrotta dall'utente.")
                self._set_status("⏹   Fusione interrotta.")
            elif result:
                self.ss_phase_var.set(f"✅  Fusione completata — {result.name}")
                self._set_status(f"✅   Fusione completata — salvato in {result}")
                self._log_write(self.ss_log, f"✅  Operazione completata: {result}")
            else:
                self.ss_phase_var.set("⚠  Fusione fallita — controlla il registro.")
                self._set_status("⚠   Fusione fallita — controlla il registro.")
        threading.Thread(target=run, daemon=True).start()
    def _build_tab_pdf(self):
        p = self.tab_pdf
        sec = self._section(p, "📚  Configurazione Unione PDF")
        sec.columnconfigure(1, weight=1)
        self._label(sec, "Cartella con i file PDF:").grid(
            row=0, column=0, sticky="w", padx=14, pady=10)
        self.pu_srcdir = tk.StringVar()
        self._entry(sec, self.pu_srcdir, width=52).grid(
            row=0, column=1, sticky="ew", padx=14, pady=10)
        self._btn(sec, "📁  Browse", self._pick_pu_src, BORDER_GLOW).grid(
            row=0, column=2, padx=10, pady=10)
        self._label(sec, "File PDF di Destinazione:").grid(
            row=1, column=0, sticky="w", padx=14, pady=10)
        self.pu_outfile = tk.StringVar(value="PDF_Unito.pdf")
        self._entry(sec, self.pu_outfile, width=52).grid(
            row=1, column=1, sticky="ew", padx=14, pady=10)
        self._btn(sec, "📁  Browse", self._pick_pu_outfile, BORDER_GLOW).grid(
            row=1, column=2, padx=10, pady=10)
        tk.Label(sec,
            text="Unisce ogni file PDF trovato nella cartella scelta in un unico PDF,\n"
                 "con un segnalibro per ciascun file sorgente per poter saltare\n"
                 "direttamente al suo inizio.",
            bg=BG_MID, fg=TEXT_DIM, font=self.font_phase, justify="left", anchor="w"
        ).grid(row=2, column=0, columnspan=3, sticky="ew", padx=14, pady=(0, 10))
        bf = tk.Frame(p, bg=BG_MID)
        bf.pack(pady=12)
        self._btn(bf, "📚   AVVIA UNIONE", self._start_pdf_unify, "#1a3a5c").pack(side="left", padx=12)
        self._btn(bf, "⏹   STOP",         self._stop_pdf_unify, RUNE_RED ).pack(side="left", padx=12)
        self.pu_phase_var = tk.StringVar(value="In attesa di iniziare...")
        tk.Label(p, textvariable=self.pu_phase_var,
            bg=BG_MID, fg=ACCENT_GOLD, font=self.font_phase, anchor="w"
        ).pack(anchor="w", padx=22, pady=(0, 4))
        self.pu_progress = self._progressbar(p)
        self.pu_log = self._logbox(p, height=13)
    def _pick_pu_src(self):
        d = filedialog.askdirectory(title="Scegli la cartella contenente i file PDF")
        if d:
            self.pu_srcdir.set(d)
    def _pick_pu_outfile(self):
        f = filedialog.asksaveasfilename(
            title="Scegli il file PDF di destinazione",
            defaultextension=".pdf",
            filetypes=[("File PDF", "*.pdf")],
            initialfile=os.path.basename(self.pu_outfile.get() or "PDF_Unito.pdf"))
        if f:
            self.pu_outfile.set(f)
    def _stop_pdf_unify(self):
        self._pu_stop.set()
        self._set_status("⏹   Interruzione unione PDF richiesta...")
        self._log_write(self.pu_log, "⏹  Interruzione richiesta — completamento del file corrente...")
    def _start_pdf_unify(self):
        srcdir  = self.pu_srcdir.get().strip()
        outfile = self.pu_outfile.get().strip()
        if not srcdir:
            messagebox.showwarning("Attenzione", "Scegli la cartella contenente i file PDF!"); return
        if not os.path.isdir(srcdir):
            messagebox.showwarning("Attenzione", "La cartella sorgente non esiste!"); return
        if not outfile:
            messagebox.showwarning("Attenzione", "Scegli un file PDF di destinazione!"); return
        self._pu_stop = threading.Event()
        self.pu_progress["value"] = 0
        self.pu_progress.configure(mode="indeterminate")
        self.pu_progress.start(12)
        self.pu_phase_var.set("📚  Unione dei PDF in corso...")
        self._log_write(self.pu_log, "=" * 65)
        self._log_write(self.pu_log, f"📚 Avvio Unione PDF")
        self._log_write(self.pu_log, f"📁 Sorgente: {srcdir}")
        self._log_write(self.pu_log, f"💾 Destinazione: {outfile}")
        self._set_status("📚   Unione PDF in corso...")
        def run():
            engine = PdfUnifierEngine(
                src_folder=srcdir,
                out_file=outfile,
                log_callback=lambda m: self._log_write(self.pu_log, m),
                stop_event=self._pu_stop,
            )
            try:
                result = engine.run()
            except Exception as e:
                result = None
                self._log_write(self.pu_log, f"⚠  Unione fallita: {e}")
            def _finish():
                self.pu_progress.stop()
                self.pu_progress.configure(mode="determinate")
                self.pu_progress["value"] = 100
            self.after(0, _finish)
            if self._pu_stop.is_set():
                self.pu_phase_var.set("⏹  Unione interrotta dall'utente.")
                self._set_status("⏹   Unione PDF interrotta.")
            elif result:
                self.pu_phase_var.set(f"✅  Unione completata — {result.name}")
                self._set_status(f"✅   Unione PDF completata — salvato in {result}")
                self._log_write(self.pu_log, f"✅  Operazione completata: {result}")
            else:
                self.pu_phase_var.set("⚠  Unione fallita — controlla il registro.")
                self._set_status("⚠   Unione PDF fallita — controlla il registro.")
        threading.Thread(target=run, daemon=True).start()
    def _stop_operation(self):
        self._stop_event.set()
        self._fu_stop.set()
        self._pu_stop.set()
        self._set_status("⏹   Interruzione richiesta — completamento operazione corrente...")
        for box in [self.bu_log, self.co_log, self.fu_log, self.ss_log, self.pu_log]:
            self._log_write(box, "⏹  Operazione interrotta dall'utente.")
        try:
            self._re_log_write("⏹  Operazione interrotta dall'utente.")
        except Exception:
            pass
    def _on_close(self):
        self._stop_event.set()
        try:
            if self._bubble_initialized:
                self.rune_animator.stop()
        except: pass
        self.destroy()




# ─────────────────────────────────────────────
#  PUNTO DI INGRESSO
# ─────────────────────────────────────────────

def main():
    mp.freeze_support()
    app = Mergohydrox()
    app.mainloop()

if __name__ == "__main__":
    main()