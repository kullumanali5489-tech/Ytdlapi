from flask import Flask, request, jsonify, redirect
from flask_cors import CORS
import yt_dlp
import os
import logging
from pathlib import Path

# ============================================================
#   YouTube Downloader - Railway Edition
#   Developed by @Hellfirez3643
#   No files stored on server — direct redirect to YT CDN
# ============================================================

app = Flask(__name__)
CORS(app)

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)
logging.getLogger('werkzeug').setLevel(logging.ERROR)

COOKIES_FILE = 'cookies.txt'

class QuietLogger:
    def debug(self, msg): pass
    def warning(self, msg): pass
    def error(self, msg): logger.error(f"❌ {msg}")

def base_ydl_opts():
    """Base yt-dlp options with cookies and spoofed headers"""
    opts = {
        'quiet': True,
        'no_warnings': True,
        'logger': QuietLogger(),
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept-Language': 'en-US,en;q=0.9',
        },
        # tv_embedded + ios bypass PO token requirement on datacenter IPs
        'extractor_retries': 3,
        'retries': 3,
        'extractor_args': {
            'youtube': {
                'player_client': ['tv_embedded', 'ios'],
            }
        },
    }
    if os.path.exists(COOKIES_FILE):
        opts['cookiefile'] = COOKIES_FILE
        logger.info("🍪 Using cookies.txt")
    else:
        logger.warning("⚠️  cookies.txt not found — may get bot-detected")
    return opts

def get_video_info(url):
    """Get video info and available qualities with direct CDN URLs"""
    ydl_opts = base_ydl_opts()

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

            seen_qualities = {}

            if 'formats' in info:
                # Video formats
                for f in info['formats']:
                    if f.get('height') and f.get('vcodec') != 'none' and f.get('url'):
                        quality = f'{f["height"]}p'
                        if quality not in seen_qualities or f.get('filesize', 0) > seen_qualities[quality].get('filesize', 0):
                            seen_qualities[quality] = {
                                'quality': quality,
                                'height': f['height'],
                                'ext': f.get('ext', 'mp4'),
                                'filesize': f.get('filesize', 0),
                                'direct_url': f['url'],
                                'format_note': f.get('format_note', ''),
                                'fps': f.get('fps', 0)
                            }

                # Audio formats
                for f in info['formats']:
                    if f.get('acodec') != 'none' and f.get('vcodec') == 'none' and f.get('url'):
                        if 'audio' not in seen_qualities or f.get('abr', 0) > seen_qualities.get('audio', {}).get('abr', 0):
                            seen_qualities['audio'] = {
                                'quality': 'audio',
                                'ext': f.get('ext', 'm4a'),
                                'filesize': f.get('filesize', 0),
                                'direct_url': f['url'],
                                'abr': f.get('abr', 0)
                            }

            formats = list(seen_qualities.values())
            formats.sort(key=lambda x: x.get('height', 0), reverse=True)

            return {
                'success': True,
                'title': info.get('title', 'Unknown'),
                'duration': info.get('duration', 0),
                'thumbnail': info.get('thumbnail', ''),
                'uploader': info.get('uploader', 'Unknown'),
                'view_count': info.get('view_count', 0),
                'formats': formats
            }
    except Exception as e:
        return {'success': False, 'error': str(e)}


@app.route('/', methods=['GET'])
def home():
    return '''
    <html>
    <head>
        <title>YT Downloader by @Hellfirez3643</title>
        <style>
            body { font-family: Arial, sans-serif; padding: 40px; background: #0f0f0f; color: #f1f1f1; }
            h1 { color: #ff0000; }
            code { background: #272727; padding: 4px 8px; border-radius: 4px; color: #aaffaa; }
            .section { margin-bottom: 24px; }
            .label { color: #aaa; font-size: 14px; }
            footer { margin-top: 40px; color: #555; font-size: 13px; }
        </style>
    </head>
    <body>
        <h1>🎬 YouTube Downloader</h1>
        <p class="label">No files stored on server. Direct redirect to YouTube CDN.</p>

        <div class="section">
            <h3>Step 1 — Get available qualities</h3>
            <code>/dl?url=VIDEO_URL</code>
            <p class="label">Returns JSON with title, formats, and direct CDN URLs</p>
        </div>

        <div class="section">
            <h3>Step 2 — Download with quality</h3>
            <code>/dl?url=VIDEO_URL&q=QUALITY</code>
            <p class="label">Redirects your browser directly to YouTube's CDN. Nothing stored here.</p>
        </div>

        <div class="section">
            <h3>Quality options</h3>
            <code>1080p</code> &nbsp; <code>720p</code> &nbsp; <code>480p</code> &nbsp;
            <code>360p</code> &nbsp; <code>240p</code> &nbsp; <code>audio</code>
        </div>

        <div class="section">
            <h3>Examples</h3>
            <p>Get info: <code>/dl?url=https://youtube.com/watch?v=xyz</code></p>
            <p>Download 720p: <code>/dl?url=https://youtube.com/watch?v=xyz&q=720p</code></p>
            <p>Download audio: <code>/dl?url=https://youtube.com/watch?v=xyz&q=audio</code></p>
        </div>

        <footer>Developed by @Hellfirez3643</footer>
    </body>
    </html>
    '''


@app.route('/dl', methods=['GET'])
def download_direct():
    """
    No q param  → return JSON with available qualities + direct URLs
    With q param → redirect browser straight to YouTube CDN (nothing stored on server)
    """
    url = request.args.get('url')
    quality = request.args.get('q')

    if not url:
        return jsonify({'error': 'Missing url parameter. Usage: /dl?url=VIDEO_URL'}), 400

    logger.info(f"{'📋 Info' if not quality else f'🔗 Redirect [{quality}]'}: {url}")

    info = get_video_info(url)

    if not info['success']:
        return jsonify(info), 400

    # No quality specified — return info JSON
    if not quality:
        duration = info['duration']
        return jsonify({
            'title': info['title'],
            'uploader': info['uploader'],
            'duration': f"{duration // 60}:{duration % 60:02d}",
            'views': info['view_count'],
            'thumbnail': info['thumbnail'],
            'available_qualities': [f['quality'] for f in info['formats']],
            'formats': info['formats'],
            'usage': f"/dl?url={url}&q=QUALITY",
            'example': f"/dl?url={url}&q=720p",
            'note': 'Use the direct_url from formats, or add &q=QUALITY to redirect'
        })

    # Quality specified — find matching format and redirect
    formats = {f['quality']: f for f in info['formats']}
    chosen = formats.get(quality)

    if not chosen:
        return jsonify({
            'error': f'Quality "{quality}" not available',
            'available': list(formats.keys())
        }), 400

    direct_url = chosen['direct_url']
    logger.info(f"✅ Redirecting to CDN for: {info['title']} [{quality}]")

    # 302 redirect — user downloads directly from YouTube's servers
    # Railway never touches the file
    return redirect(direct_url, code=302)


@app.route('/info', methods=['GET'])
def info_only():
    """Alias for /dl without q param"""
    url = request.args.get('url')
    if not url:
        return jsonify({'error': 'Missing url parameter'}), 400
    return download_direct()


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print("\n" + "=" * 60)
    print("  🎬 YouTube Downloader - Railway Edition")
    print("  Developed by @Hellfirez3643")
    print("=" * 60)
    print(f"  🌐 Running on port {port}")
    print(f"  🍪 Cookies: {'✅ Found' if os.path.exists(COOKIES_FILE) else '❌ Not found'}")
    print(f"  📦 Zero storage — pure CDN redirect mode")
    print("=" * 60 + "\n")

    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
