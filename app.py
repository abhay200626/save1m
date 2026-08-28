import os
import re
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
            f.write("1")
        return 1
    try:
        with open(VISITOR_FILE, "r", encoding="utf-8") as f:
            count = int(f.read().strip() or "0")
        count += 1
        with open(VISITOR_FILE, "w", encoding="utf-8") as f:
            f.write(str(count))
        return count
    except Exception:
        return 1

@app.route('/', methods=['GET'])
def health_check():
    return jsonify({"status": "Save1M Engine is Running Online!"}), 200

@app.route('/api/visitors', methods=['GET'])
def visitor_tracker():
    count = get_visitor_count()
    return jsonify({"count": count})

@app.route('/download', methods=['POST'])
def fetch_media():
    data = request.get_json() or {}
    url = data.get('url', '').strip()
    mode = data.get('mode', 'video').strip().lower()

    if not url or 'instagram.com' not in url:
        return jsonify({"error": "Please provide a valid Instagram URL"}), 400

    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False,
        'skip_download': True,
        'format': 'best',
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info:
                return jsonify({"error": "Could not extract media. Post might be private or removed."}), 404

            title = info.get('title') or info.get('description') or 'Instagram_Media'
            # First line of description/caption if available
            title = title.split('\n')[0][:50].strip()

            media_list = []

            # Handle carousel/multi-items
            if 'entries' in info and info['entries']:
                for entry in info['entries']:
                    dl_url = entry.get('url') or entry.get('webpage_url')
                    thumb = entry.get('thumbnail') or ''
                    if dl_url:
                        media_list.append({
                            "download_url": dl_url,
                            "preview_url": thumb
                        })
            else:
                dl_url = info.get('url')
                thumb = info.get('thumbnail') or ''
                if dl_url:
                    media_list.append({
                        "download_url": dl_url,
                        "preview_url": thumb
                    })

            if not media_list:
                return jsonify({"error": "No direct media stream found. Make sure post is public."}), 404

            return jsonify({
                "title": title,
                "media_list": media_list
            })

    except Exception as e:
        return jsonify({"error": f"Failed to fetch content: {str(e)}"}), 500


@app.route('/proxy-image', methods=['GET'])
def proxy_image():
    img_url = request.args.get('url')
    if not img_url:
        return "Missing URL", 400
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        res = requests.get(img_url, headers=headers, stream=True, timeout=10)
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
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        req = requests.get(media_url, headers=headers, stream=True, timeout=15)
        
        response = Response(
            req.iter_content(chunk_size=8192),
            content_type=req.headers.get('content-type', 'application/octet-stream')
        )
        response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
    except Exception as e:
        return str(e), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)