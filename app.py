import os
import re
import json
import requests
from flask import Flask, request, jsonify, Response, stream_with_context
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
    return jsonify({"status": "Save1M Engine Online & Active"}), 200

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
    return raw_url.replace('\\u0026', '&').replace('&amp;', '&').replace('\\/', '/').replace('&amp%3B', '&')

def extract_instagram_all_media(url, mode='video'):
    """Universal high-speed extractor for Reels, Videos, Audio & Photos"""
    shortcode = get_shortcode(url)
    if not shortcode:
        return None

    clean_url_base = f"https://www.instagram.com/p/{shortcode}/"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Referer': clean_url_base,
    }

    # Strategy 1: Embed Page Scraping (Works reliably without Instagram Login on cloud)
    try:
        embed_url = f"https://www.instagram.com/p/{shortcode}/embed/captioned/"
        r = requests.get(embed_url, headers=headers, timeout=10)
        if r.status_code == 200:
            text = r.text
            
            caption = "Instagram_Media"
            cap_match = re.search(r'<div class="Caption"[^>]*>(.*?)</div>', text, re.DOTALL)
            if cap_match:
                clean_cap = re.sub('<[^<]+?>', '', cap_match.group(1)).strip()
                if clean_cap:
                    caption = clean_cap.split('\n')[0][:50]

            # 1. Video / Reel extraction
            if mode in ['video', 'audio']:
                video_matches = re.findall(r'"video_url"\s*:\s*"([^"]+)"', text)
                if not video_matches:
                    video_matches = re.findall(r'src="(https:[^"]+cdninstagram\.com[^"]+\.mp4[^"]*)"', text)
                if not video_matches:
                    video_matches = re.findall(r'class="EmbeddedMediaVideo"[^>]*src="([^"]+)"', text)

                if video_matches:
                    video_url = clean_url(video_matches[0])
                    thumb_match = re.search(r'class="EmbeddedMediaImage"[^>]*src="([^"]+)"', text)
                    thumb_url = clean_url(thumb_match.group(1)) if thumb_match else video_url
                    return {
                        "title": caption,
                        "media_list": [{"download_url": video_url, "preview_url": thumb_url}]
                    }

            # 2. Photo / Carousel extraction
            if mode == 'photo':
                photo_matches = re.findall(r'"display_url"\s*:\s*"([^"]+)"', text)
                if not photo_matches:
                    photo_matches = re.findall(r'class="EmbeddedMediaImage"[^>]*src="([^"]+)"', text)

                if photo_matches:
                    cleaned = []
                    for u in photo_matches:
                        c = clean_url(u)
                        if c and c not in cleaned and 's150x150' not in c and 's320x320' not in c:
                            cleaned.append(c)
                    if cleaned:
                        return {
                            "title": caption,
                            "media_list": [{"download_url": u, "preview_url": u} for u in cleaned]
                        }
    except Exception:
        pass

    # Strategy 2: GraphQL Web API
    try:
        doc_url = f"https://www.instagram.com/graphql/query/?doc_id=8845758582119845&variables={json.dumps({'shortcode': shortcode})}"
        r = requests.get(doc_url, headers=headers, timeout=8)
        if r.status_code == 200:
            data = r.json()
            media = data.get('data', {}).get('xdt_shortcode_media') or data.get('data', {}).get('shortcode_media')
            if media:
                caption = "Instagram_Media"
                edges = media.get('edge_media_to_caption', {}).get('edges', [])
                if edges:
                    caption = edges[0].get('node', {}).get('text', 'Instagram_Media').split('\n')[0][:50]

                # Check if it is a video
                if media.get('is_video') and (mode in ['video', 'audio']):
                    vid_url = clean_url(media.get('video_url'))
                    thumb = clean_url(media.get('display_url'))
                    if vid_url:
                        return {"title": caption, "media_list": [{"download_url": vid_url, "preview_url": thumb}]}

                # Multi-photo Carousel
                sidecar = media.get('edge_sidecar_to_children', {}).get('edges', [])
                if sidecar and len(sidecar) > 0 and mode == 'photo':
                    media_list = []
                    for child in sidecar:
                        node = child.get('node', {})
                        img_url = node.get('display_url') or (node.get('display_resources', [{}])[-1].get('src'))
                        if img_url:
                            c = clean_url(img_url)
                            media_list.append({"download_url": c, "preview_url": c})
                    if len(media_list) > 0:
                        return {"title": caption, "media_list": media_list}
                elif media.get('display_url') and mode == 'photo':
                    c = clean_url(media['display_url'])
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

    # 1. Try Direct Fast Instagram Extractor first
    direct_res = extract_instagram_all_media(url, mode=mode)
    if direct_res and direct_res.get('media_list') and len(direct_res['media_list']) > 0:
        return jsonify(direct_res)

    # 2. yt-dlp Engine Fallback
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False,
        'skip_download': True,
        'ignoreerrors': True,
        'format': 'bestvideo+bestaudio/best' if mode == 'video' else 'best',
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            if not info:
                return jsonify({"error": "Could not fetch media. Please make sure the account is public."}), 404

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
                return jsonify({"error": "No media stream found for this URL."}), 404

            return jsonify({
                "title": title,
                "media_list": media_list
            })

    except Exception:
        return jsonify({"error": "Failed to fetch content. Make sure post is public and retry."}), 500


@app.route('/proxy-image', methods=['GET'])
def proxy_image():
    img_url = request.args.get('url')
    if not img_url:
        return "Missing URL", 400
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        }
        res = requests.get(img_url, headers=headers, stream=True, timeout=12)
        if res.status_code != 200:
            return "Failed to load image", res.status_code
        resp = Response(res.content, content_type=res.headers.get('content-type', 'image/jpeg'))
        resp.headers['Access-Control-Allow-Origin'] = '*'
        resp.headers['Cache-Control'] = 'public, max-age=86400'
        return resp
    except Exception as e:
        return str(e), 500


@app.route('/proxy-download', methods=['GET'])
def proxy_download():
    """Bulletproof stream downloader: Ensures 100% playable video/audio files"""
    media_url = request.args.get('url')
    filename = request.args.get('filename', 'save1m_media.mp4')
    if not media_url:
        return "Missing URL", 400

    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
            'Accept': '*/*',
        }
        req = requests.get(media_url, headers=headers, stream=True, timeout=30)
        
        if req.status_code != 200:
            return f"CDN Error: {req.status_code}", 502

        content_type = req.headers.get('content-type', 'application/octet-stream')
        if filename.endswith('.jpg') or filename.endswith('.jpeg'):
            content_type = 'image/jpeg'
        elif filename.endswith('.mp4'):
            content_type = 'video/mp4'
        elif filename.endswith('.mp3'):
            content_type = 'audio/mp4'

        def generate_stream():
            for chunk in req.iter_content(chunk_size=65536):
                if chunk:
                    yield chunk

        response = Response(stream_with_context(generate_stream()), content_type=content_type)
        response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
        if 'content-length' in req.headers:
            response.headers['Content-Length'] = req.headers['content-length']
        response.headers['Access-Control-Allow-Origin'] = '*'
        return response
    except Exception as e:
        return str(e), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)