import os
import re
import json
import requests
from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import yt_dlp

app = Flask(__name__)
CORS(app)

VISITOR_FILE = "visitor_count.txt"

def get_visitor_count():
    if not os.path.exists(VISITOR_FILE):
        with open(VISITOR_FILE, "w", encoding="utf-8") as f:
            f.write("50")
        return 50
    try:
        with open(VISITOR_FILE, "r", encoding="utf-8") as f:
            content = f.read().strip()
            count = int(content) if content else 50
        count += 1
        with open(VISITOR_FILE, "w", encoding="utf-8") as f:
            f.write(str(count))
        return count
    except Exception:
        return 50

@app.route('/', methods=['GET'])
def health_check():
    return jsonify({"status": "Save1M Engine is Running Online!"}), 200

@app.route('/api/visitors', methods=['GET'])
def visitor_tracker():
    count = get_visitor_count()
    return jsonify({"count": count})

def extract_photo_fallback(url):
    """Deep scraper for Instagram Photos/Carousels using multiple direct methods"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
    }

    clean_url = url.split('?')[0].rstrip('/')

    # Method 1: Embed Page Scrape (Bypasses Instagram Login Wall for Photos)
    try:
        embed_url = f"{clean_url}/embed/captioned/"
        r = requests.get(embed_url, headers=headers, timeout=8)
        if r.status_code == 200:
            html = r.text
            # Find embedded images
            img_matches = re.findall(r'class="EmbeddedMediaImage"[^>]*src="([^"]+)"', html)
            if not img_matches:
                img_matches = re.findall(r'<img[^>]+src="([^"]+)"', html)

            # Filter valid instagram cdn links
            valid_imgs = [img.replace('&amp;', '&') for img in img_matches if 'cdninstagram.com' in img or 'fbcdn.net' in img]
            
            # Extract caption
            caption = "Instagram_Photo"
            caption_match = re.search(r'<div class="Caption"[^>]*>(.*?)</div>', html, re.DOTALL)
            if caption_match:
                clean_caption = re.sub('<[^<]+?>', '', caption_match.group(1)).strip()
                if clean_caption:
                    caption = clean_caption.split('\n')[0][:50]

            if valid_imgs:
                # Remove duplicates while preserving order
                unique_imgs = list(dict.fromkeys(valid_imgs))
                media_list = [{"download_url": img, "preview_url": img} for img in unique_imgs]
                return {"title": caption, "media_list": media_list}
    except Exception:
        pass

    # Method 2: OpenGraph Meta Tags
    try:
        r = requests.get(clean_url, headers=headers, timeout=8)
        if r.status_code == 200:
            html = r.text
            og_image = re.search(r'<meta property="og:image" content="([^"]+)"', html)
            og_title = re.search(r'<meta property="og:title" content="([^"]+)"', html)
            
            caption = "Instagram_Photo"
            if og_title:
                caption = og_title.group(1).split(':')[0][:50]

            if og_image:
                img_url = og_image.group(1).replace('&amp;', '&')
                return {
                    "title": caption,
                    "media_list": [{"download_url": img_url, "preview_url": img_url}]
                }
    except Exception:
        pass

    return None

@app.route('/download', methods=['POST'])
def fetch_media():
    data = request.get_json() or {}
    url = data.get('url', '').strip()
    mode = data.get('mode', 'video').strip().lower()

    if not url or 'instagram.com' not in url:
        return jsonify({"error": "Please provide a valid Instagram URL"}), 400

    # If mode is photo, run dedicated photo scraper first
    if mode == 'photo':
        photo_res = extract_photo_fallback(url)
        if photo_res and photo_res.get('media_list'):
            return jsonify(photo_res)

    # For Video / Reels / Audio, use yt-dlp
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False,
        'skip_download': True,
        'ignoreerrors': True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            if not info:
                # Fallback to photo parser if yt-dlp returns nothing
                photo_res = extract_photo_fallback(url)
                if photo_res and photo_res.get('media_list'):
                    return jsonify(photo_res)
                return jsonify({"error": "Unable to fetch content. Make sure the Instagram account is public."}), 404

            title = info.get('title') or info.get('description') or 'Instagram_Media'
            title = title.split('\n')[0][:50].strip()
            media_list = []

            if 'entries' in info and info['entries']:
                for entry in info['entries']:
                    if not entry:
                        continue
                    dl_url = entry.get('url') or entry.get('thumbnail')
                    thumb = entry.get('thumbnail') or dl_url
                    if dl_url:
                        media_list.append({"download_url": dl_url, "preview_url": thumb})
            else:
                dl_url = info.get('url') or info.get('thumbnail')
                thumb = info.get('thumbnail') or dl_url
                if dl_url:
                    media_list.append({"download_url": dl_url, "preview_url": thumb})

            if not media_list:
                photo_res = extract_photo_fallback(url)
                if photo_res and photo_res.get('media_list'):
                    return jsonify(photo_res)
                return jsonify({"error": "No media stream available for this post."}), 404

            return jsonify({
                "title": title,
                "media_list": media_list
            })

    except Exception as e:
        photo_res = extract_photo_fallback(url)
        if photo_res and photo_res.get('media_list'):
            return jsonify(photo_res)
        return jsonify({"error": "Failed to fetch content. Server is updating, please retry in 10s."}), 500


@app.route('/proxy-image', methods=['GET'])
def proxy_image():
    img_url = request.args.get('url')
    if not img_url:
        return "Missing URL", 400
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
            'Referer': 'https://www.instagram.com/'
        }
        res = requests.get(img_url, headers=headers, stream=True, timeout=12)
        return Response(res.content, content_type=res.headers.get('content-type', 'image/jpeg'))
    except Exception as e:
        return str(e), 500


@app.route('/proxy-download', methods=['GET'])
def proxy_download():
    media_url = request.args.get('url')
    filename = request.args.get('filename', 'save1m_media.mp4')
    if not media_url:
        return "Missing URL", 400

    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
            'Referer': 'https://www.instagram.com/'
        }
        req = requests.get(media_url, headers=headers, stream=True, timeout=25)

        content_type = req.headers.get('content-type', 'application/octet-stream')
        if filename.endswith('.jpg') or filename.endswith('.jpeg'):
            content_type = 'image/jpeg'
        elif filename.endswith('.mp4'):
            content_type = 'video/mp4'
        elif filename.endswith('.mp3'):
            content_type = 'audio/mpeg'

        response = Response(
            req.iter_content(chunk_size=8192),
            content_type=content_type
        )
        response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
    except Exception as e:
        return str(e), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)