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

def extract_instagram_direct(url):
    """Direct fetcher for Instagram Photos and Carousels without yt-dlp error."""
    clean_url = url.split('?')[0].rstrip('/')
    api_url = f"{clean_url}/?__a=1&__d=dis"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none'
    }
    
    try:
        r = requests.get(api_url, headers=headers, timeout=10)
        if r.status_code == 200:
            data = r.json()
            items = data.get('items', [])
            if items:
                item = items[0]
                caption = "Instagram_Photo"
                if item.get('caption') and item['caption'].get('text'):
                    caption = item['caption']['text'].split('\n')[0][:50].strip()

                media_list = []
                # Carousel
                if 'carousel_media' in item:
                    for media in item['carousel_media']:
                        img_versions = media.get('image_versions2', {}).get('candidates', [])
                        if img_versions:
                            best_img = img_versions[0]['url']
                            media_list.append({"download_url": best_img, "preview_url": best_img})
                # Single Image
                elif 'image_versions2' in item:
                    img_versions = item['image_versions2'].get('candidates', [])
                    if img_versions:
                        best_img = img_versions[0]['url']
                        media_list.append({"download_url": best_img, "preview_url": best_img})

                if media_list:
                    return {"title": caption, "media_list": media_list}
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

    # 1. For photos, try direct extraction first
    if mode == 'photo':
        direct_data = extract_instagram_direct(url)
        if direct_data and direct_data.get('media_list'):
            return jsonify(direct_data)

    # 2. Extract with yt-dlp fallback (for Reels, Videos, Audio)
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False,
        'skip_download': True,
        'ignoreerrors': True,
        'check_formats': False
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            # If yt-dlp fails or finds nothing, try direct extractor
            if not info:
                direct_data = extract_instagram_direct(url)
                if direct_data and direct_data.get('media_list'):
                    return jsonify(direct_data)
                return jsonify({"error": "Could not extract media. Ensure post is from a public account."}), 404

            title = info.get('title') or info.get('description') or 'Instagram_Media'
            title = title.split('\n')[0][:50].strip()

            media_list = []

            # Carousel entries
            if 'entries' in info and info['entries']:
                for entry in info['entries']:
                    if not entry:
                        continue
                    if mode == 'photo':
                        dl_url = entry.get('thumbnail') or entry.get('url')
                    else:
                        dl_url = entry.get('url') or entry.get('thumbnail')
                    
                    thumb = entry.get('thumbnail') or dl_url
                    if dl_url:
                        media_list.append({
                            "download_url": dl_url,
                            "preview_url": thumb
                        })
            else:
                if mode == 'photo':
                    thumbnails = info.get('thumbnails', [])
                    if thumbnails:
                        dl_url = thumbnails[-1].get('url') or info.get('thumbnail') or info.get('url')
                    else:
                        dl_url = info.get('thumbnail') or info.get('url')
                    thumb = dl_url
                else:
                    dl_url = info.get('url') or info.get('thumbnail')
                    thumb = info.get('thumbnail') or dl_url

                if dl_url:
                    media_list.append({
                        "download_url": dl_url,
                        "preview_url": thumb
                    })

            if not media_list:
                # Final fallback check
                direct_data = extract_instagram_direct(url)
                if direct_data and direct_data.get('media_list'):
                    return jsonify(direct_data)
                return jsonify({"error": "No media stream available for this URL."}), 404

            return jsonify({
                "title": title,
                "media_list": media_list
            })

    except Exception as e:
        # Fallback to direct fetcher on yt-dlp crash
        direct_data = extract_instagram_direct(url)
        if direct_data and direct_data.get('media_list'):
            return jsonify(direct_data)
        return jsonify({"error": f"Failed to fetch content: {str(e)}"}), 500


@app.route('/proxy-image', methods=['GET'])
def proxy_image():
    img_url = request.args.get('url')
    if not img_url:
        return "Missing URL", 400
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            'Referer': 'https://www.instagram.com/'
        }
        res = requests.get(img_url, headers=headers, stream=True, timeout=15)
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
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
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