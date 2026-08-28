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

def get_shortcode(url):
    match = re.search(r'/(?:p|reel|reels|tv)/([A-Za-z0-9_-]+)', url)
    return match.group(1) if match else None

def extract_instagram_photo_bulletproof(url):
    """Multi-layer extractor for single photos and multi-image carousels"""
    shortcode = get_shortcode(url)
    headers = {
        'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1',
        'Accept': '*/*',
        'Accept-Language': 'en-US,en;q=0.9',
        'Referer': 'https://www.instagram.com/',
        'Sec-Fetch-Mode': 'cors',
    }

    # Method 1: GraphQL Shortcode Query
    if shortcode:
        try:
            gql_url = f"https://www.instagram.com/graphql/query/?query_hash=b3055c01b4b222b8a47dc12b090e4e64&variables={json.dumps({'shortcode': shortcode})}"
            r = requests.get(gql_url, headers=headers, timeout=8)
            if r.status_code == 200:
                data = r.json()
                media = data.get('data', {}).get('shortcode_media', {})
                if media:
                    caption = "Instagram_Photo"
                    edges = media.get('edge_media_to_caption', {}).get('edges', [])
                    if edges:
                        caption = edges[0].get('node', {}).get('text', 'Instagram_Photo').split('\n')[0][:50]

                    media_list = []
                    # Check carousel children
                    sidecar = media.get('edge_sidecar_to_children', {}).get('edges', [])
                    if sidecar:
                        for item in sidecar:
                            node = item.get('node', {})
                            img_url = node.get('display_url') or (node.get('display_resources', [{}])[-1].get('src'))
                            if img_url:
                                media_list.append({"download_url": img_url, "preview_url": img_url})
                    else:
                        img_url = media.get('display_url') or (media.get('display_resources', [{}])[-1].get('src'))
                        if img_url:
                            media_list.append({"download_url": img_url, "preview_url": img_url})

                    if media_list:
                        return {"title": caption, "media_list": media_list}
        except Exception:
            pass

    # Method 2: Embed Scraper with Regex Token Matching
    try:
        embed_url = f"https://www.instagram.com/p/{shortcode}/embed/captioned/" if shortcode else url.split('?')[0] + "embed/captioned/"
        r = requests.get(embed_url, headers=headers, timeout=8)
        if r.status_code == 200:
            html = r.text
            
            # Find high-res image matches
            img_urls = re.findall(r'class="EmbeddedMediaImage"[^>]*src="([^"]+)"', html)
            if not img_urls:
                img_urls = re.findall(r'src="(https://[^"]*cdninstagram\.com/[^"]*)"', html)

            # Caption matching
            caption = "Instagram_Photo"
            cap_match = re.search(r'<div class="Caption"[^>]*>(.*?)</div>', html, re.DOTALL)
            if cap_match:
                clean_caption = re.sub('<[^<]+?>', '', cap_match.group(1)).strip()
                if clean_caption:
                    caption = clean_caption.split('\n')[0][:50]

            if img_urls:
                clean_imgs = list(dict.fromkeys([u.replace('&amp;', '&') for u in img_urls]))
                return {
                    "title": caption,
                    "media_list": [{"download_url": u, "preview_url": u} for u in clean_imgs]
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

    # 1. Directly handle photo mode with specialized photo engine
    if mode == 'photo':
        photo_data = extract_instagram_photo_bulletproof(url)
        if photo_data and photo_data.get('media_list'):
            return jsonify(photo_data)

    # 2. For Video / Reels / Audio (or Photo fallback), execute yt-dlp
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
                photo_data = extract_instagram_photo_bulletproof(url)
                if photo_data and photo_data.get('media_list'):
                    return jsonify(photo_data)
                return jsonify({"error": "Unable to extract media. Please ensure post is public."}), 404

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
                photo_data = extract_instagram_photo_bulletproof(url)
                if photo_data and photo_data.get('media_list'):
                    return jsonify(photo_data)
                return jsonify({"error": "No media stream found for this URL."}), 404

            return jsonify({
                "title": title,
                "media_list": media_list
            })

    except Exception:
        photo_data = extract_instagram_photo_bulletproof(url)
        if photo_data and photo_data.get('media_list'):
            return jsonify(photo_data)
        return jsonify({"error": "Could not fetch content. Make sure post is public and retry."}), 500


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