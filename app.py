from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import instaloader
import yt_dlp
import requests
import re
import os

app = Flask(__name__)
CORS(app)

# Instaloader configuration
L = instaloader.Instaloader(
    download_pictures=False,
    download_videos=False, 
    download_video_thumbnails=False,
    save_metadata=False,
    quiet=True
)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
    'Accept': '*/*',
    'Accept-Language': 'en-US,en;q=0.9',
}

def extract_shortcode(url):
    match = re.search(r'instagram\.com/(?:p|reel|tv)/([^/?#&]+)', url)
    return match.group(1) if match else None

def get_photos_via_instaloader(url):
    try:
        shortcode = extract_shortcode(url)
        if not shortcode:
            return None, None
        
        post = instaloader.Post.from_shortcode(L.context, shortcode)
        media_list = []
        
        # Carousel / Multiple photos post
        if post.typename == 'GraphSidecar':
            for node in post.get_sidecar_nodes():
                media_list.append({
                    "preview_url": node.display_url,
                    "download_url": node.video_url if node.is_video else node.display_url,
                    "is_video": node.is_video
                })
        # Single photo / video
        else:
            media_list.append({
                "preview_url": post.url,
                "download_url": post.video_url if post.is_video else post.url,
                "is_video": post.is_video
            })
            
        return media_list, post.caption
    except Exception as e:
        print("Instaloader Error:", e)
    return None, None

def get_media_ytdlp(url, mode='video'):
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False,
    }
    
    if mode == 'audio':
        ydl_opts['format'] = 'bestaudio/best'

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        title = info.get('title', 'Instagram Media')
        thumbnail = info.get('thumbnail')
        media_url = None

        if mode == 'audio':
            if 'requested_formats' in info:
                for f in info['requested_formats']:
                    if f.get('acodec') != 'none' and f.get('vcodec') == 'none':
                        media_url = f.get('url')
                        break
            if not media_url:
                media_url = info.get('url')
        else:
            media_url = info.get('url')
            if not media_url and 'formats' in info and len(info['formats']) > 0:
                media_url = info['formats'][-1].get('url')

        if not media_url:
            media_url = thumbnail

        return [{
            "preview_url": thumbnail or media_url,
            "download_url": media_url,
            "is_video": (mode == 'video')
        }], title

@app.route('/', methods=['GET'])
def home():
    return jsonify({"status": "Save1M Engine Online"}), 200

@app.route('/download', methods=['POST'])
def get_media():
    data = request.json or {}
    url = data.get('url', '').strip()
    mode = data.get('mode', 'video')

    if not url:
        return jsonify({"error": "Please provide a valid Instagram URL."}), 400

    # 1. PHOTO MODE (Instaloader First)
    if mode == 'photo':
        media_list, caption = get_photos_via_instaloader(url)
        if media_list:
            return jsonify({
                "title": caption[:60] if caption else "Instagram Photos",
                "media_list": media_list,
                "mode": "photo"
            })

    # 2. VIDEO / AUDIO MODE (yt-dlp)
    if mode in ['video', 'audio']:
        try:
            media_list, title = get_media_ytdlp(url, mode)
            if media_list and media_list[0]['download_url']:
                return jsonify({
                    "title": title or "Instagram Media",
                    "media_list": media_list,
                    "mode": mode
                })
        except Exception:
            pass

    # 3. UNIVERSAL FALLBACK (Instaloader)
    media_list, caption = get_photos_via_instaloader(url)
    if media_list:
        return jsonify({
            "title": caption[:60] if caption else f"Instagram {mode.capitalize()}",
            "media_list": media_list,
            "mode": mode
        })

    return jsonify({"error": "Unable to fetch media. Please make sure the account/post is PUBLIC."}), 500

# Proxy Image Preview to prevent CORS broken icons
@app.route('/proxy-image')
def proxy_image():
    img_url = request.args.get('url')
    if not img_url:
        return "Missing URL", 400
    try:
        r = requests.get(img_url, headers=HEADERS, stream=True, timeout=10)
        return Response(r.content, content_type=r.headers.get('content-type', 'image/jpeg'))
    except Exception:
        return "Image Load Failed", 500

# Direct Download Proxy
@app.route('/proxy-download')
def proxy_download():
    media_url = request.args.get('url')
    filename = request.args.get('filename', 'media_file.mp4')
    
    if not media_url:
        return "Missing URL", 400

    try:
        r = requests.get(media_url, headers=HEADERS, stream=True, timeout=25)
        return Response(
            r.iter_content(chunk_size=65536),
            content_type=r.headers.get('content-type', 'application/octet-stream'),
            headers={'Content-Disposition': f'attachment; filename="{filename}"'}
        )
    except Exception as e:
        return str(e), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)