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
    base_count = 50
    if not os.path.exists(VISITOR_FILE):
        with open(VISITOR_FILE, "w", encoding="utf-8") as f:
            f.write(str(base_count))
        return base_count
    try:
        with open(VISITOR_FILE, "r", encoding="utf-8") as f:
            content = f.read().strip()
            count = int(content) if content else base_count
        count += 1
        with open(VISITOR_FILE, "w", encoding="utf-8") as f:
            f.write(str(count))
        return count
    except Exception:
        return base_count

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

def clean_url(raw_url):
    if not raw_url:
        return None
    return raw_url.replace('\\u0026', '&').replace('&amp;', '&').replace('\\/', '/')

def shortcode_to_media_id(shortcode):
    alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_'
    media_id = 0
    for letter in shortcode:
        media_id = (media_id * 64) + alphabet.index(letter)
    return media_id

def extract_all_carousel_photos_complete(url):
    """Extracts EVERY single photo in a carousel without missing any slide"""
    shortcode = get_shortcode(url)
    if not shortcode:
        return None

    clean_url_base = f"https://www.instagram.com/p/{shortcode}/"

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'x-ig-app-id': '936619743392459',
        'x-asbd-id': '129477',
        'x-requested-with': 'XMLHttpRequest',
        'Accept': '*/*',
        'Accept-Language': 'en-US,en;q=0.9',
        'Referer': clean_url_base,
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-origin',
    }

    # Method 1: Web Post Info Endpoint
    try:
        api_url = f"https://www.instagram.com/api/v1/media/web_info_to_node/?shortcode={shortcode}"
        r = requests.get(api_url, headers=headers, timeout=8)
        if r.status_code == 200:
            data = r.json()
            media = data.get('data', {}).get('xdt_shortcode_media') or data.get('data', {}).get('shortcode_media')
            if media:
                caption = "Instagram_Photo"
                edges = media.get('edge_media_to_caption', {}).get('edges', [])
                if edges:
                    caption = edges[0].get('node', {}).get('text', 'Instagram_Photo').split('\n')[0][:50]

                sidecar = media.get('edge_sidecar_to_children', {}).get('edges', [])
                if sidecar:
                    media_list = []
                    for child in sidecar:
                        node = child.get('node', {})
                        img_url = node.get('display_url') or (node.get('display_resources', [{}])[-1].get('src'))
                        if img_url:
                            c = clean_url(img_url)
                            media_list.append({"download_url": c, "preview_url": c})
                    if media_list:
                        return {"title": caption, "media_list": media_list}
                else:
                    img_url = media.get('display_url') or (media.get('display_resources', [{}])[-1].get('src'))
                    if img_url:
                        c = clean_url(img_url)
                        return {"title": caption, "media_list": [{"download_url": c, "preview_url": c}]}
    except Exception:
        pass

    # Method 2: GraphQL Query by doc_id
    try:
        doc_url = f"https://www.instagram.com/graphql/query/?doc_id=8845758582119845&variables={json.dumps({'shortcode': shortcode})}"
        r = requests.get(doc_url, headers=headers, timeout=8)
        if r.status_code == 200:
            data = r.json()
            media = data.get('data', {}).get('xdt_shortcode_media') or data.get('data', {}).get('shortcode_media')
            if media:
                caption = "Instagram_Photo"
                edges = media.get('edge_media_to_caption', {}).get('edges', [])
                if edges:
                    caption = edges[0].get('node', {}).get('text', 'Instagram_Photo').split('\n')[0][:50]

                sidecar = media.get('edge_sidecar_to_children', {}).get('edges', [])
                if sidecar:
                    media_list = []
                    for child in sidecar:
                        node = child.get('node', {})
                        img_url = node.get('display_url') or (node.get('display_resources', [{}])[-1].get('src'))
                        if img_url:
                            c = clean_url(img_url)
                            media_list.append({"download_url": c, "preview_url": c})
                    if media_list:
                        return {"title": caption, "media_list": media_list}
                else:
                    img_url = media.get('display_url') or (media.get('display_resources', [{}])[-1].get('src'))
                    if img_url:
                        c = clean_url(img_url)
                        return {"title": caption, "media_list": [{"download_url": c, "preview_url": c}]}
    except Exception:
        pass

    # Method 3: Mobile REST info endpoint via numerical media_id
    try:
        media_id = shortcode_to_media_id(shortcode)
        mobile_headers = {
            'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 Instagram 324.0.0.18.110',
            'x-ig-app-id': '936619743392459',
            'Accept-Language': 'en-US,en;q=0.9',
        }
        r = requests.get(f"https://i.instagram.com/api/v1/media/{media_id}/info/", headers=mobile_headers, timeout=8)
        if r.status_code == 200:
            data = r.json()
            items = data.get('items', [])
            if items:
                item = items[0]
                caption = "Instagram_Photo"
                if item.get('caption') and item['caption'].get('text'):
                    caption = item['caption']['text'].split('\n')[0][:50].strip()

                if 'carousel_media' in item and len(item['carousel_media']) > 0:
                    media_list = []
                    for slide in item['carousel_media']:
                        versions = slide.get('image_versions2', {}).get('candidates', [])
                        if versions:
                            c = clean_url(versions[0]['url'])
                            media_list.append({"download_url": c, "preview_url": c})
                    if media_list:
                        return {"title": caption, "media_list": media_list}
                elif 'image_versions2' in item:
                    versions = item['image_versions2'].get('candidates', [])
                    if versions:
                        c = clean_url(versions[0]['url'])
                        return {"title": caption, "media_list": [{"download_url": c, "preview_url": c}]}
    except Exception:
        pass

    # Method 4: Embed Page Fallback (Single Image Fallback)
    try:
        embed_url = f"https://www.instagram.com/p/{shortcode}/embed/captioned/"
        r = requests.get(embed_url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}, timeout=8)
        if r.status_code == 200:
            text = r.text
            caption = "Instagram_Photo"
            cap_match = re.search(r'<div class="Caption"[^>]*>(.*?)</div>', text, re.DOTALL)
            if cap_match:
                clean_cap = re.sub('<[^<]+?>', '', cap_match.group(1)).strip()
                if clean_cap:
                    caption = clean_cap.split('\n')[0][:50]

            img_match = re.search(r'class="EmbeddedMediaImage"[^>]*src="([^"]+)"', text)
            if img_match:
                c = clean_url(img_match.group(1))
                return {"title": caption, "media_list": [{"download_url": c, "preview_url": c}]}
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

    # 1. Photo Mode Exact Handler
    if mode == 'photo':
        photo_res = extract_all_carousel_photos_complete(url)
        if photo_res and photo_res.get('media_list'):
            return jsonify(photo_res)

    # 2. Video / Reels / Audio Extractor
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
                photo_res = extract_all_carousel_photos_complete(url)
                if photo_res and photo_res.get('media_list'):
                    return jsonify(photo_res)
                return jsonify({"error": "Unable to extract media. Make sure post is public."}), 404

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
                        media_list.append({"download_url": clean_url(dl_url), "preview_url": clean_url(thumb)})
            else:
                dl_url = info.get('url') or info.get('thumbnail')
                thumb = info.get('thumbnail') or dl_url
                if dl_url:
                    media_list.append({"download_url": clean_url(dl_url), "preview_url": clean_url(thumb)})

            if not media_list:
                photo_res = extract_all_carousel_photos_complete(url)
                if photo_res and photo_res.get('media_list'):
                    return jsonify(photo_res)
                return jsonify({"error": "No media stream available for this post."}), 404

            return jsonify({
                "title": title,
                "media_list": media_list
            })

    except Exception:
        photo_res = extract_all_carousel_photos_complete(url)
        if photo_res and photo_res.get('media_list'):
            return jsonify(photo_res)
        return jsonify({"error": "Failed to fetch content. Please retry in a few moments."}), 500


@app.route('/proxy-image', methods=['GET'])
def proxy_image():
    img_url = request.args.get('url')
    if not img_url:
        return "Missing URL", 400
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
            'Referer': 'https://www.instagram.com/'
        }
        res = requests.get(img_url, headers=headers, stream=True, timeout=12)
        resp = Response(res.content, content_type=res.headers.get('content-type', 'image/jpeg'))
        resp.headers['Access-Control-Allow-Origin'] = '*'
        resp.headers['Cache-Control'] = 'public, max-age=86400'
        return resp
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
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
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
        response.headers['Access-Control-Allow-Origin'] = '*'
        return response
    except Exception as e:
        return str(e), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)